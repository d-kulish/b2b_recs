"""
Management command to collect daily GCP resource metrics snapshot.

Usage:
    python manage.py collect_resource_metrics

    # Collect for a specific date
    python manage.py collect_resource_metrics --date 2026-02-01

    # Dry run (show what would be collected)
    python manage.py collect_resource_metrics --dry-run
"""
import os
import logging
from datetime import date

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection
from django.utils import timezone

from ml_platform.models import ResourceMetrics, ProjectMetrics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Collect daily GCP resource metrics snapshot'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Date to collect for (YYYY-MM-DD). Defaults to today.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be collected without saving'
        )

    def handle(self, *args, **options):
        target_date = timezone.now().date()
        if options['date']:
            target_date = date.fromisoformat(options['date'])

        dry_run = options['dry_run']

        self.stdout.write(f'Collecting resource metrics for {target_date}...\n')

        data = {
            'date': target_date,
            'bq_total_bytes': 0,
            'bq_table_details': [],
            'bq_jobs_completed': 0,
            'bq_jobs_failed': 0,
            'bq_bytes_billed': 0,
            'cloud_run_services': [],
            'cloud_run_active_services': 0,
            'cloud_run_total_requests': 0,
            'cloud_run_request_details': [],
            'db_size_bytes': 0,
            'db_table_details': [],
            'gcs_bucket_details': [],
            'gcs_total_bytes': 0,
            'etl_jobs_completed': 0,
            'etl_jobs_failed': 0,
            'gpu_training_hours': 0,
            'gpu_jobs_completed': 0,
            'gpu_jobs_failed': 0,
            'gpu_jobs_running': 0,
            'gpu_jobs_by_type': [],
            'collection_errors': [],
        }

        collectors = [
            ('bigquery', lambda: self._collect_bigquery(data)),
            ('cloud_run', lambda: self._collect_cloud_run(data)),
            ('database', lambda: self._collect_database(data)),
            ('gcs', lambda: self._collect_gcs(data)),
            ('etl', lambda: self._collect_etl(data, target_date)),
            ('cloud_run_requests', lambda: self._collect_cloud_run_requests(data, target_date)),
            ('project_metrics', lambda: self._collect_project_metrics(data, target_date)),
            ('gpu', lambda: self._collect_gpu(data, target_date)),
        ]

        for name, collector in collectors:
            try:
                collector()
            except Exception as e:
                data['collection_errors'].append({'collector': name, 'error': str(e)})
                self.stdout.write(self.style.WARNING(f'  {name} collection failed: {e}'))

        if data['collection_errors']:
            self.stdout.write(self.style.WARNING(
                f'  {len(data["collection_errors"])} collector(s) had errors'
            ))

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes saved.\n'))
            self.stdout.write(f'  BQ total bytes: {data["bq_total_bytes"]:,}')
            self.stdout.write(f'  BQ tables: {len(data["bq_table_details"])}')
            self.stdout.write(f'  BQ jobs completed: {data["bq_jobs_completed"]}')
            self.stdout.write(f'  BQ jobs failed: {data["bq_jobs_failed"]}')
            self.stdout.write(f'  Cloud Run services: {len(data["cloud_run_services"])}')
            self.stdout.write(f'  Cloud Run active: {data["cloud_run_active_services"]}')
            self.stdout.write(f'  Cloud Run requests: {data["cloud_run_total_requests"]:,}')
            self.stdout.write(f'  Cloud Run serving endpoints: {len(data["cloud_run_request_details"])}')
            self.stdout.write(f'  Project metrics rows: {data.get("project_metrics_count", 0)}')
            self.stdout.write(f'  DB size bytes: {data["db_size_bytes"]:,}')
            self.stdout.write(f'  DB tables: {len(data["db_table_details"])}')
            self.stdout.write(f'  GCS buckets: {len(data["gcs_bucket_details"])}')
            self.stdout.write(f'  GCS total bytes: {data["gcs_total_bytes"]:,}')
            self.stdout.write(f'  ETL jobs completed: {data["etl_jobs_completed"]}')
            self.stdout.write(f'  ETL jobs failed: {data["etl_jobs_failed"]}')
            self.stdout.write(f'  GPU training hours: {data["gpu_training_hours"]:.1f}')
            self.stdout.write(f'  GPU jobs completed: {data["gpu_jobs_completed"]}')
            self.stdout.write(f'  GPU jobs failed: {data["gpu_jobs_failed"]}')
            self.stdout.write(f'  GPU jobs running: {data["gpu_jobs_running"]}')
            return

        # Save or update
        obj, created = ResourceMetrics.objects.update_or_create(
            date=target_date,
            defaults={k: v for k, v in data.items() if k != 'date'}
        )

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} ResourceMetrics for {target_date}'
        ))

    def _collect_bigquery(self, data):
        """Collect BigQuery storage and job metrics."""
        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
        from ml_platform.utils.bigquery_manager import BigQueryTableManager
        manager = BigQueryTableManager(project_id=project_id)
        result = manager.list_tables()

        if result.get('success') and result.get('tables'):
            table_details = []
            total_bytes = 0
            for t in result['tables']:
                table_details.append({
                    'name': t['name'],
                    'bytes': t.get('num_bytes', 0),
                    'rows': t.get('num_rows', 0),
                })
                total_bytes += t.get('num_bytes', 0)

            data['bq_table_details'] = table_details
            data['bq_total_bytes'] = total_bytes
            self.stdout.write(f'  BQ: {len(table_details)} tables, {total_bytes:,} bytes')

        # Query job stats from INFORMATION_SCHEMA (non-critical, ok to fail independently)
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=project_id)
            query = """
                SELECT
                    state,
                    COUNT(*) as job_count,
                    SUM(total_bytes_billed) as bytes_billed
                FROM `region-US`.INFORMATION_SCHEMA.JOBS
                WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
                    AND job_type = 'QUERY'
                GROUP BY state
            """
            rows = client.query(query).result()
            for row in rows:
                if row.state == 'DONE':
                    data['bq_jobs_completed'] = row.job_count
                    data['bq_bytes_billed'] = row.bytes_billed or 0
                elif row.state in ('FAILED', 'ERROR'):
                    data['bq_jobs_failed'] = row.job_count

            self.stdout.write(f'  BQ jobs: {data["bq_jobs_completed"]} completed, {data["bq_jobs_failed"]} failed')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  BQ jobs query failed: {e}'))

    def _collect_cloud_run(self, data):
        """Collect Cloud Run service status."""
        from google.cloud import run_v2

        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
        region = 'europe-central2'

        client = run_v2.ServicesClient()
        parent = f"projects/{project_id}/locations/{region}"

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

            services.append({
                'name': name,
                'status': status,
                'is_ml_serving': name.endswith('-serving'),
            })

        data['cloud_run_services'] = services
        data['cloud_run_active_services'] = active_count
        self.stdout.write(f'  Cloud Run: {len(services)} services, {active_count} active')

    def _collect_cloud_run_requests(self, data, target_date):
        """Collect Cloud Run request counts from Cloud Monitoring API."""
        from datetime import datetime, timedelta
        from google.cloud import monitoring_v3
        from google.protobuf import timestamp_pb2

        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))

        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        # Query window: full target_date day (UTC)
        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        start_time = timestamp_pb2.Timestamp()
        start_time.FromDatetime(day_start)
        end_time = timestamp_pb2.Timestamp()
        end_time.FromDatetime(day_end)

        interval = monitoring_v3.TimeInterval(
            start_time=start_time,
            end_time=end_time,
        )

        # Query request_count filtered to -serving services
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

        # Aggregate per service: total requests and errors
        from collections import defaultdict
        service_stats = defaultdict(lambda: {'requests': 0, 'errors': 0})

        for ts in results:
            service_name = ts.resource.labels.get("service_name", "unknown")
            response_class = ts.metric.labels.get("response_code_class", "")
            count = sum(p.value.int64_value for p in ts.points)

            service_stats[service_name]['requests'] += count
            if response_class != "2xx":
                service_stats[service_name]['errors'] += count

        total_requests = sum(s['requests'] for s in service_stats.values())
        request_details = [
            {'name': name, 'requests': stats['requests'], 'errors': stats['errors']}
            for name, stats in sorted(service_stats.items())
        ]

        data['cloud_run_total_requests'] = total_requests
        data['cloud_run_request_details'] = request_details
        self.stdout.write(
            f'  Cloud Run requests: {total_requests:,} across '
            f'{len(request_details)} serving endpoints'
        )

    def _collect_project_metrics(self, data, target_date):
        """Collect per-project metrics from Cloud Run serving endpoints."""
        from datetime import datetime, timedelta
        from collections import defaultdict
        from ml_platform.training.models import DeployedEndpoint
        from ml_platform.models import ModelEndpoint

        # Build service_name -> ModelEndpoint mapping
        deployed = DeployedEndpoint.objects.filter(
            service_name__endswith='-serving'
        ).select_related('registered_model__ml_model')

        service_to_project = {}
        for ep in deployed:
            service_to_project[ep.service_name] = ep.registered_model.ml_model

        if not service_to_project:
            self.stdout.write('  Project metrics: no serving endpoints found')
            data['project_metrics_count'] = 0
            return

        # Reuse request data from cloud_run_requests collector
        request_details = data.get('cloud_run_request_details', [])
        request_lookup = {d['name']: d for d in request_details}

        # Query Cloud Monitoring for latency percentiles (2xx only)
        latency_data = {}  # {service_name: {p50: val, p95: val, p99: val}}
        try:
            from google.cloud import monitoring_v3
            from google.protobuf import timestamp_pb2
            import os

            project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{project_id}"

            day_start = datetime.combine(target_date, datetime.min.time())
            day_end = day_start + timedelta(days=1)

            start_time = timestamp_pb2.Timestamp()
            start_time.FromDatetime(day_start)
            end_time = timestamp_pb2.Timestamp()
            end_time.FromDatetime(day_end)

            interval = monitoring_v3.TimeInterval(
                start_time=start_time,
                end_time=end_time,
            )

            percentile_map = {
                monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_50: 'p50',
                monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_95: 'p95',
                monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_99: 'p99',
            }

            for aligner, key in percentile_map.items():
                results = client.list_time_series(
                    request={
                        "name": project_name,
                        "filter": (
                            'metric.type = "run.googleapis.com/request_latencies" '
                            'AND resource.type = "cloud_run_revision" '
                            'AND resource.labels.service_name = monitoring.regex.full_match(".*-serving") '
                            'AND metric.labels.response_code_class = "2xx"'
                        ),
                        "interval": interval,
                        "aggregation": monitoring_v3.Aggregation(
                            alignment_period={"seconds": 86400},
                            per_series_aligner=aligner,
                            cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_NONE,
                            group_by_fields=["resource.labels.service_name"],
                        ),
                        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                    }
                )
                for ts in results:
                    svc = ts.resource.labels.get("service_name", "unknown")
                    if svc not in latency_data:
                        latency_data[svc] = {'p50': 0, 'p95': 0, 'p99': 0}
                    for point in ts.points:
                        latency_data[svc][key] = point.value.double_value

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Project metrics latency query failed: {e}'))

        # Aggregate per project
        project_data = defaultdict(lambda: {
            'requests': 0, 'errors': 0,
            'weighted_p50': 0, 'weighted_p95': 0, 'weighted_p99': 0,
            'total_weight': 0,
            'endpoint_details': []
        })

        for svc_name, project in service_to_project.items():
            req_info = request_lookup.get(svc_name, {'requests': 0, 'errors': 0})
            lat_info = latency_data.get(svc_name, {'p50': 0, 'p95': 0, 'p99': 0})
            requests = req_info['requests']
            errors = req_info['errors']

            pd = project_data[project.id]
            pd['project'] = project
            pd['requests'] += requests
            pd['errors'] += errors

            if requests > 0:
                pd['weighted_p50'] += lat_info['p50'] * requests
                pd['weighted_p95'] += lat_info['p95'] * requests
                pd['weighted_p99'] += lat_info['p99'] * requests
                pd['total_weight'] += requests

            pd['endpoint_details'].append({
                'name': svc_name,
                'requests': requests,
                'errors': errors,
                'latency_p50_ms': round(lat_info['p50'], 1),
                'latency_p95_ms': round(lat_info['p95'], 1),
                'latency_p99_ms': round(lat_info['p99'], 1),
            })

        # Persist per project
        count = 0
        for project_id_val, pd in project_data.items():
            w = pd['total_weight']
            ProjectMetrics.objects.update_or_create(
                date=target_date,
                model_endpoint=pd['project'],
                defaults={
                    'total_requests': pd['requests'],
                    'error_count': pd['errors'],
                    'latency_p50_ms': round(pd['weighted_p50'] / w, 1) if w > 0 else 0,
                    'latency_p95_ms': round(pd['weighted_p95'] / w, 1) if w > 0 else 0,
                    'latency_p99_ms': round(pd['weighted_p99'] / w, 1) if w > 0 else 0,
                    'endpoint_details': pd['endpoint_details'],
                }
            )
            count += 1

        data['project_metrics_count'] = count
        self.stdout.write(f'  Project metrics: {count} projects updated')

    def _collect_database(self, data):
        """Collect PostgreSQL database size metrics."""
        with connection.cursor() as cursor:
            # Total database size
            cursor.execute("SELECT pg_database_size(current_database())")
            db_size = cursor.fetchone()[0]
            data['db_size_bytes'] = db_size

            # Per-table sizes
            cursor.execute("""
                SELECT
                    relname as table_name,
                    pg_total_relation_size(relid) as size_bytes,
                    n_live_tup as row_count
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
                LIMIT 20
            """)
            table_details = []
            for row in cursor.fetchall():
                table_details.append({
                    'name': row[0],
                    'size_bytes': row[1],
                    'row_count': row[2],
                })

            data['db_table_details'] = table_details
            self.stdout.write(f'  DB: {db_size:,} bytes, {len(table_details)} tables')

    def _collect_gcs(self, data):
        """Collect GCS bucket usage metrics."""
        from google.cloud import storage

        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
        client = storage.Client(project=project_id)

        bucket_details = []
        total_bytes = 0

        for bucket in client.list_buckets():
            # Use bucket metadata (no blob listing)
            bucket_info = {
                'name': bucket.name,
                'total_bytes': 0,
                'object_count': 0,
            }

            # Get bucket size via a quick blob iteration with limit
            # For accuracy without full listing, count first page
            try:
                blobs = list(bucket.list_blobs(max_results=1000))
                bucket_bytes = sum(b.size or 0 for b in blobs)
                bucket_info['total_bytes'] = bucket_bytes
                bucket_info['object_count'] = len(blobs)
                total_bytes += bucket_bytes
            except Exception:
                pass

            bucket_details.append(bucket_info)

        data['gcs_bucket_details'] = bucket_details
        data['gcs_total_bytes'] = total_bytes
        self.stdout.write(f'  GCS: {len(bucket_details)} buckets, {total_bytes:,} bytes')

    def _collect_etl(self, data, target_date):
        """Collect ETL job metrics from ETLRun data."""
        from datetime import datetime, timedelta
        from django.utils import timezone as tz
        from ml_platform.models import ETLRun

        day_start = tz.make_aware(datetime.combine(target_date, datetime.min.time()))
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

        data['etl_jobs_completed'] = completed
        data['etl_jobs_failed'] = failed
        self.stdout.write(f'  ETL: {completed} completed, {failed} failed')

    def _collect_gpu(self, data, target_date):
        """Collect GPU/Compute metrics from TrainingRun data."""
        from datetime import datetime, timedelta
        from django.utils import timezone as tz
        from ml_platform.training.models import TrainingRun
        from collections import defaultdict

        day_start = tz.make_aware(datetime.combine(target_date, datetime.min.time()))
        day_end = day_start + timedelta(days=1)

        # Jobs that completed/failed on this day
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

        # Jobs running at end of this day
        running = TrainingRun.objects.filter(
            started_at__lt=day_end,
            status='running'
        ).count()

        # GPU hours: sum duration for jobs that ran on this day
        # For jobs with duration_seconds, use that; otherwise estimate from started_at/completed_at
        total_gpu_hours = 0.0
        gpu_type_stats = defaultdict(lambda: {'count': 0, 'hours': 0.0})

        runs_on_day = TrainingRun.objects.filter(
            started_at__lt=day_end,
            started_at__gte=day_start - timedelta(days=7),  # Include runs started up to 7 days before
        ).exclude(
            completed_at__lt=day_start  # Exclude runs that completed before this day
        )

        for run in runs_on_day:
            gpu_config = run.gpu_config or {}
            gpu_type = gpu_config.get('gpu_type', 'UNKNOWN')
            gpu_count = gpu_config.get('gpu_count', 1)

            # Calculate hours this run contributed to this day
            run_start = max(run.started_at, day_start)
            run_end = run.completed_at if run.completed_at and run.completed_at < day_end else day_end
            if run_end > run_start:
                hours = (run_end - run_start).total_seconds() / 3600.0
                gpu_hours = hours * gpu_count
                total_gpu_hours += gpu_hours
                gpu_type_stats[gpu_type]['count'] += 1
                gpu_type_stats[gpu_type]['hours'] += gpu_hours

        data['gpu_training_hours'] = round(total_gpu_hours, 2)
        data['gpu_jobs_completed'] = completed
        data['gpu_jobs_failed'] = failed
        data['gpu_jobs_running'] = running
        data['gpu_jobs_by_type'] = [
            {'gpu_type': k, 'count': v['count'], 'hours': round(v['hours'], 2)}
            for k, v in gpu_type_stats.items()
        ]

        self.stdout.write(
            f'  GPU: {total_gpu_hours:.1f}h, {completed} completed, '
            f'{failed} failed, {running} running'
        )
