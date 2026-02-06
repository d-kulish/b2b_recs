"""
Management command to backfill ResourceMetrics with historical data.

Collects current-day real data from GCP services, then generates historical
entries with realistic growth curves. GPU data is derived from actual
TrainingRun records per day.

Usage:
    python manage.py backfill_resource_metrics

    # Backfill specific number of days
    python manage.py backfill_resource_metrics --days 60

    # Dry run
    python manage.py backfill_resource_metrics --dry-run
"""
import os
import logging
import random
from datetime import date, datetime, timedelta
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection
from django.utils import timezone

from ml_platform.models import ResourceMetrics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill ResourceMetrics with historical data (30 days by default)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to backfill (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be generated without saving'
        )

    def handle(self, *args, **options):
        num_days = options['days']
        dry_run = options['dry_run']

        today = date.today()
        self.stdout.write(f'Backfilling {num_days} days of ResourceMetrics...\n')

        # Step 1: Collect current real data as baseline
        self.stdout.write('Collecting current baseline data...')
        baseline = self._collect_baseline()

        # Step 2: Collect real GPU data per day from TrainingRun
        self.stdout.write('Collecting GPU data from TrainingRun records...')
        gpu_by_day = self._collect_gpu_by_day(today, num_days)

        # Step 2b: Collect real ETL data per day from ETLRun
        self.stdout.write('Collecting ETL data from ETLRun records...')
        etl_by_day = self._collect_etl_by_day(today, num_days)

        # Step 2c: Collect real Cloud Run request data from Cloud Monitoring
        self.stdout.write('Collecting Cloud Run request data from Cloud Monitoring...')
        requests_by_day = self._collect_requests_by_day(today, num_days)

        # Step 3: Generate entries for each day
        created_count = 0
        updated_count = 0

        for days_ago in range(num_days, -1, -1):  # Oldest to newest, including today
            target_date = today - timedelta(days=days_ago)
            progress = 1.0 - (days_ago / max(num_days, 1))  # 0.0 at oldest, 1.0 at today

            # Apply growth curves to baseline data
            data = self._generate_day_data(baseline, target_date, progress, gpu_by_day, requests_by_day, etl_by_day)

            if dry_run:
                self.stdout.write(
                    f'  {target_date}: BQ={data["bq_total_bytes"]:,}B '
                    f'DB={data["db_size_bytes"]:,}B '
                    f'GCS={data["gcs_total_bytes"]:,}B '
                    f'ETL={data["etl_jobs_completed"]}c/{data["etl_jobs_failed"]}f '
                    f'GPU={data["gpu_training_hours"]:.1f}h '
                    f'({data["gpu_jobs_completed"]}c/{data["gpu_jobs_failed"]}f)'
                )
                continue

            obj, created = ResourceMetrics.objects.update_or_create(
                date=target_date,
                defaults=data
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - no changes saved.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nDone: {created_count} created, {updated_count} updated'
            ))

    def _collect_baseline(self):
        """Collect current real data as baseline for historical extrapolation."""
        baseline = {
            'bq_total_bytes': 0,
            'bq_table_details': [],
            'cloud_run_services': [],
            'cloud_run_active_services': 0,
            'db_size_bytes': 0,
            'db_table_details': [],
            'gcs_bucket_details': [],
            'gcs_total_bytes': 0,
        }

        # BigQuery
        try:
            project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
            from ml_platform.utils.bigquery_manager import BigQueryTableManager
            manager = BigQueryTableManager(project_id=project_id)
            result = manager.list_tables()
            if result.get('success') and result.get('tables'):
                total_bytes = 0
                table_details = []
                for t in result['tables']:
                    table_details.append({
                        'name': t['name'],
                        'bytes': t.get('num_bytes', 0),
                        'rows': t.get('num_rows', 0),
                    })
                    total_bytes += t.get('num_bytes', 0)
                baseline['bq_total_bytes'] = total_bytes
                baseline['bq_table_details'] = table_details
                self.stdout.write(f'  BQ: {len(table_details)} tables, {total_bytes:,} bytes')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  BQ failed: {e}'))

        # Cloud Run
        try:
            from google.cloud import run_v2
            project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
            client = run_v2.ServicesClient()
            parent = f"projects/{project_id}/locations/europe-central2"
            services = []
            active_count = 0
            for svc in client.list_services(parent=parent):
                name = svc.name.split('/')[-1]
                status = 'Unknown'
                if svc.terminal_condition:
                    if svc.terminal_condition.state == run_v2.Condition.State.CONDITION_SUCCEEDED:
                        status = 'Ready'
                        active_count += 1
                    elif svc.terminal_condition.state == run_v2.Condition.State.CONDITION_FAILED:
                        status = 'Not Ready'
                services.append({'name': name, 'status': status, 'is_ml_serving': name.endswith('-serving')})
            baseline['cloud_run_services'] = services
            baseline['cloud_run_active_services'] = active_count
            self.stdout.write(f'  Cloud Run: {len(services)} services, {active_count} active')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Cloud Run failed: {e}'))

        # Database
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_database_size(current_database())")
                baseline['db_size_bytes'] = cursor.fetchone()[0]
                cursor.execute("""
                    SELECT relname, pg_total_relation_size(relid), n_live_tup
                    FROM pg_stat_user_tables
                    ORDER BY pg_total_relation_size(relid) DESC LIMIT 20
                """)
                baseline['db_table_details'] = [
                    {'name': r[0], 'size_bytes': r[1], 'row_count': r[2]}
                    for r in cursor.fetchall()
                ]
                self.stdout.write(f'  DB: {baseline["db_size_bytes"]:,} bytes')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  DB failed: {e}'))

        # GCS
        try:
            from google.cloud import storage
            project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
            client = storage.Client(project=project_id)
            total_bytes = 0
            bucket_details = []
            for bucket in client.list_buckets():
                bucket_info = {'name': bucket.name, 'total_bytes': 0, 'object_count': 0}
                try:
                    blobs = list(bucket.list_blobs(max_results=1000))
                    bucket_bytes = sum(b.size or 0 for b in blobs)
                    bucket_info['total_bytes'] = bucket_bytes
                    bucket_info['object_count'] = len(blobs)
                    total_bytes += bucket_bytes
                except Exception:
                    pass
                bucket_details.append(bucket_info)
            baseline['gcs_bucket_details'] = bucket_details
            baseline['gcs_total_bytes'] = total_bytes
            self.stdout.write(f'  GCS: {len(bucket_details)} buckets, {total_bytes:,} bytes')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  GCS failed: {e}'))

        return baseline

    def _collect_gpu_by_day(self, today, num_days):
        """Collect actual GPU usage per day from TrainingRun records."""
        from ml_platform.training.models import TrainingRun

        start_date = today - timedelta(days=num_days)
        gpu_by_day = {}

        for days_ago in range(num_days, -1, -1):
            target_date = today - timedelta(days=days_ago)
            day_start = timezone.make_aware(datetime.combine(target_date, datetime.min.time()))
            day_end = day_start + timedelta(days=1)

            completed = TrainingRun.objects.filter(
                completed_at__gte=day_start,
                completed_at__lt=day_end,
                status__in=['completed', 'deployed', 'not_blessed']
            ).count()

            failed = TrainingRun.objects.filter(
                completed_at__gte=day_start,
                completed_at__lt=day_end,
                status__in=['failed', 'cancelled', 'deploy_failed']
            ).count()

            running = TrainingRun.objects.filter(
                started_at__lt=day_end,
                status='running'
            ).count() if target_date == today else 0

            # GPU hours
            total_gpu_hours = 0.0
            gpu_type_stats = defaultdict(lambda: {'count': 0, 'hours': 0.0})

            runs_on_day = TrainingRun.objects.filter(
                started_at__lt=day_end,
                started_at__gte=day_start - timedelta(days=7),
            ).exclude(
                completed_at__lt=day_start
            )

            for run in runs_on_day:
                gpu_config = run.gpu_config or {}
                gpu_type = gpu_config.get('gpu_type', 'UNKNOWN')
                gpu_count = gpu_config.get('gpu_count', 1)

                run_start = max(run.started_at, day_start)
                run_end = run.completed_at if run.completed_at and run.completed_at < day_end else day_end
                if run_end > run_start:
                    hours = (run_end - run_start).total_seconds() / 3600.0
                    gpu_hours = hours * gpu_count
                    total_gpu_hours += gpu_hours
                    gpu_type_stats[gpu_type]['count'] += 1
                    gpu_type_stats[gpu_type]['hours'] += gpu_hours

            gpu_by_day[target_date] = {
                'gpu_training_hours': round(total_gpu_hours, 2),
                'gpu_jobs_completed': completed,
                'gpu_jobs_failed': failed,
                'gpu_jobs_running': running,
                'gpu_jobs_by_type': [
                    {'gpu_type': k, 'count': v['count'], 'hours': round(v['hours'], 2)}
                    for k, v in gpu_type_stats.items()
                ],
            }

        return gpu_by_day

    def _collect_etl_by_day(self, today, num_days):
        """Collect actual ETL job counts per day from ETLRun records."""
        from ml_platform.models import ETLRun

        etl_by_day = {}

        for days_ago in range(num_days, -1, -1):
            target_date = today - timedelta(days=days_ago)
            day_start = timezone.make_aware(datetime.combine(target_date, datetime.min.time()))
            day_end = day_start + timedelta(days=1)

            completed = ETLRun.objects.filter(
                started_at__gte=day_start,
                started_at__lt=day_end,
                status='completed'
            ).count()

            failed = ETLRun.objects.filter(
                started_at__gte=day_start,
                started_at__lt=day_end,
                status__in=['failed', 'partial']
            ).count()

            etl_by_day[target_date] = {
                'etl_jobs_completed': completed,
                'etl_jobs_failed': failed,
            }

        days_with_data = sum(1 for d in etl_by_day.values() if d['etl_jobs_completed'] + d['etl_jobs_failed'] > 0)
        self.stdout.write(f'  ETL: {days_with_data} days with ETL data')
        return etl_by_day

    def _collect_requests_by_day(self, today, num_days):
        """Collect Cloud Run request counts per day from Cloud Monitoring API."""
        try:
            from google.cloud import monitoring_v3
            from google.protobuf import timestamp_pb2

            project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))

            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{project_id}"

            # Query the full date range in one API call
            start_date = today - timedelta(days=num_days)
            range_start = datetime.combine(start_date, datetime.min.time())
            range_end = datetime.combine(today + timedelta(days=1), datetime.min.time())

            start_time = timestamp_pb2.Timestamp()
            start_time.FromDatetime(range_start)
            end_time = timestamp_pb2.Timestamp()
            end_time.FromDatetime(range_end)

            interval = monitoring_v3.TimeInterval(
                start_time=start_time,
                end_time=end_time,
            )

            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": (
                        'metric.type = "run.googleapis.com/request_count" '
                        'AND resource.type = "cloud_run_revision" '
                        'AND resource.labels.service_name = monitoring.regex.full_match(".*-serving")'
                    ),
                    "interval": interval,
                    "aggregation": monitoring_v3.Aggregation(
                        alignment_period={"seconds": 86400},
                        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_DELTA,
                        cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
                        group_by_fields=[
                            "resource.labels.service_name",
                            "metric.labels.response_code_class",
                        ],
                    ),
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )

            # Build per-day, per-service aggregation
            # day_data[date][service] = {requests, errors}
            day_data = defaultdict(lambda: defaultdict(lambda: {'requests': 0, 'errors': 0}))

            for ts in results:
                service_name = ts.resource.labels.get("service_name", "unknown")
                response_class = ts.metric.labels.get("response_code_class", "")
                for point in ts.points:
                    # point.interval.start_time gives the start of the alignment period
                    point_date = point.interval.start_time.date()
                    count = point.value.int64_value
                    day_data[point_date][service_name]['requests'] += count
                    if response_class != "2xx":
                        day_data[point_date][service_name]['errors'] += count

            # Convert to the expected format
            requests_by_day = {}
            for d, services in day_data.items():
                total = sum(s['requests'] for s in services.values())
                details = [
                    {'name': name, 'requests': stats['requests'], 'errors': stats['errors']}
                    for name, stats in sorted(services.items())
                ]
                requests_by_day[d] = {
                    'cloud_run_total_requests': total,
                    'cloud_run_request_details': details,
                }

            days_with_data = sum(1 for d in requests_by_day.values() if d['cloud_run_total_requests'] > 0)
            self.stdout.write(f'  Cloud Monitoring: {days_with_data} days with request data')
            return requests_by_day

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Cloud Monitoring request collection failed: {e}'))
            return None

    def _generate_day_data(self, baseline, target_date, progress, gpu_by_day, requests_by_day=None, etl_by_day=None):
        """Generate a single day's data based on baseline + growth curve."""
        # Growth factor: storage grows ~15% over the period
        # Older days had less data
        growth = 0.85 + 0.15 * progress
        # Add small daily variation (+-2%)
        jitter = random.uniform(0.98, 1.02)
        factor = growth * jitter

        # BQ storage with per-table scaling
        bq_table_details = []
        bq_total = 0
        for t in baseline['bq_table_details']:
            scaled_bytes = int(t['bytes'] * factor)
            scaled_rows = int(t['rows'] * factor)
            bq_table_details.append({
                'name': t['name'],
                'bytes': scaled_bytes,
                'rows': scaled_rows,
            })
            bq_total += scaled_bytes

        # BQ jobs: random daily variation
        bq_jobs_completed = random.randint(2, 12)
        bq_jobs_failed = random.choice([0, 0, 0, 0, 1])  # Mostly 0, occasionally 1
        bq_bytes_billed = random.randint(100_000_000, 2_000_000_000)

        # DB size with growth
        db_size = int(baseline['db_size_bytes'] * factor)
        db_table_details = [
            {
                'name': t['name'],
                'size_bytes': int(t['size_bytes'] * factor),
                'row_count': int(t['row_count'] * factor),
            }
            for t in baseline['db_table_details']
        ]

        # GCS with growth
        gcs_bucket_details = []
        gcs_total = 0
        for b in baseline['gcs_bucket_details']:
            scaled = int(b['total_bytes'] * factor)
            gcs_bucket_details.append({
                'name': b['name'],
                'total_bytes': scaled,
                'object_count': int(b['object_count'] * factor),
            })
            gcs_total += scaled

        # GPU data from actual TrainingRun records
        gpu_data = gpu_by_day.get(target_date, {
            'gpu_training_hours': 0,
            'gpu_jobs_completed': 0,
            'gpu_jobs_failed': 0,
            'gpu_jobs_running': 0,
            'gpu_jobs_by_type': [],
        })

        # ETL data from actual ETLRun records
        etl_data = (etl_by_day or {}).get(target_date, {
            'etl_jobs_completed': 0,
            'etl_jobs_failed': 0,
        })

        # Cloud Run request data from Cloud Monitoring
        # When requests_by_day is None (collection failed), omit request fields
        # so update_or_create won't overwrite existing data
        request_data = {}
        if requests_by_day is not None:
            request_data = requests_by_day.get(target_date, {
                'cloud_run_total_requests': 0,
                'cloud_run_request_details': [],
            })

        return {
            'bq_total_bytes': bq_total,
            'bq_table_details': bq_table_details,
            'bq_jobs_completed': bq_jobs_completed,
            'bq_jobs_failed': bq_jobs_failed,
            'bq_bytes_billed': bq_bytes_billed,
            'cloud_run_services': baseline['cloud_run_services'],
            'cloud_run_active_services': baseline['cloud_run_active_services'],
            **request_data,
            **etl_data,
            'db_size_bytes': db_size,
            'db_table_details': db_table_details,
            'gcs_bucket_details': gcs_bucket_details,
            'gcs_total_bytes': gcs_total,
            **gpu_data,
        }
