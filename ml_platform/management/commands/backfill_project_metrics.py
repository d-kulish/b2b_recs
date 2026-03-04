"""
Management command to backfill ProjectMetrics with historical Cloud Monitoring data.

Queries Cloud Monitoring for all 6 metric types spanning the full date range,
maps services to projects via DeployedEndpoint, and persists to ProjectMetrics.

Usage:
    python manage.py backfill_project_metrics

    # Backfill specific number of days
    python manage.py backfill_project_metrics --days 60

    # Dry run
    python manage.py backfill_project_metrics --dry-run
"""
import os
import logging
from datetime import date, datetime, timedelta
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.conf import settings

from ml_platform.models import ProjectMetrics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill ProjectMetrics with historical Cloud Monitoring data (30 days by default)'

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
        start_date = today - timedelta(days=num_days)
        self.stdout.write(f'Backfilling {num_days} days of ProjectMetrics ({start_date} to {today})...\n')

        # Build service_name -> ModelEndpoint mapping
        from ml_platform.training.models import DeployedEndpoint

        deployed = DeployedEndpoint.objects.filter(
            service_name__endswith='-serving'
        ).select_related('registered_model__ml_model')

        service_to_project = {}
        for ep in deployed:
            service_to_project[ep.service_name] = ep.registered_model.ml_model

        if not service_to_project:
            self.stdout.write(self.style.WARNING('No serving endpoints found. Nothing to backfill.'))
            return

        self.stdout.write(f'Found {len(service_to_project)} serving endpoints across '
                          f'{len(set(p.id for p in service_to_project.values()))} projects\n')

        # Set up Cloud Monitoring client and time range
        try:
            from google.cloud import monitoring_v3
            from google.protobuf import timestamp_pb2
        except ImportError:
            self.stdout.write(self.style.ERROR('google-cloud-monitoring not installed'))
            return

        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

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

        serving_filter = 'AND resource.labels.service_name = monitoring.regex.full_match(".*-serving")'

        # Collect all 6 metric types
        # day_data[date][service_name] = {requests, errors, p50, p95, p99, inst_peak, inst_avg, ...}
        day_data = defaultdict(lambda: defaultdict(lambda: {
            'requests': 0, 'errors': 0,
            'p50': 0, 'p95': 0, 'p99': 0,
            'inst_peak': 0, 'inst_avg': 0,
            'startup_p50': 0, 'startup_p95': 0,
            'cpu': 0, 'memory': 0,
        }))

        # 1. Request counts
        self.stdout.write('Querying request counts...')
        try:
            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": (
                        'metric.type = "run.googleapis.com/request_count" '
                        f'AND resource.type = "cloud_run_revision" {serving_filter}'
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
            for ts in results:
                svc = ts.resource.labels.get("service_name", "unknown")
                response_class = ts.metric.labels.get("response_code_class", "")
                for point in ts.points:
                    d = point.interval.start_time.date()
                    count = point.value.int64_value
                    day_data[d][svc]['requests'] += count
                    if response_class != "2xx":
                        day_data[d][svc]['errors'] += count
            self.stdout.write(f'  Got request data for {len(day_data)} days')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Request count query failed: {e}'))

        # 2. Latency percentiles
        self.stdout.write('Querying latency percentiles...')
        try:
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
                            f'{serving_filter} '
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
                    for point in ts.points:
                        d = point.interval.start_time.date()
                        day_data[d][svc][key] = point.value.double_value
            self.stdout.write('  Done')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Latency query failed: {e}'))

        # 3. Container instance counts
        self.stdout.write('Querying container instance counts...')
        try:
            instance_aligners = {
                monitoring_v3.Aggregation.Aligner.ALIGN_MAX: 'inst_peak',
                monitoring_v3.Aggregation.Aligner.ALIGN_MEAN: 'inst_avg',
            }
            for aligner, key in instance_aligners.items():
                results = client.list_time_series(
                    request={
                        "name": project_name,
                        "filter": (
                            'metric.type = "run.googleapis.com/container/instance_count" '
                            f'AND resource.type = "cloud_run_revision" {serving_filter}'
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
                    for point in ts.points:
                        d = point.interval.start_time.date()
                        if key == 'inst_peak':
                            day_data[d][svc][key] = point.value.int64_value
                        else:
                            day_data[d][svc][key] = point.value.double_value
            self.stdout.write('  Done')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Instance count query failed: {e}'))

        # 4. Startup latencies
        self.stdout.write('Querying startup latencies...')
        try:
            startup_aligners = {
                monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_50: 'startup_p50',
                monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_95: 'startup_p95',
            }
            for aligner, key in startup_aligners.items():
                results = client.list_time_series(
                    request={
                        "name": project_name,
                        "filter": (
                            'metric.type = "run.googleapis.com/container/startup_latencies" '
                            f'AND resource.type = "cloud_run_revision" {serving_filter}'
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
                    for point in ts.points:
                        d = point.interval.start_time.date()
                        day_data[d][svc][key] = point.value.double_value
            self.stdout.write('  Done')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Startup latency query failed: {e}'))

        # 5. CPU utilization
        self.stdout.write('Querying CPU utilization...')
        try:
            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": (
                        'metric.type = "run.googleapis.com/container/cpu/utilizations" '
                        f'AND resource.type = "cloud_run_revision" {serving_filter}'
                    ),
                    "interval": interval,
                    "aggregation": monitoring_v3.Aggregation(
                        alignment_period={"seconds": 86400},
                        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
                        cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_NONE,
                        group_by_fields=["resource.labels.service_name"],
                    ),
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            for ts in results:
                svc = ts.resource.labels.get("service_name", "unknown")
                for point in ts.points:
                    d = point.interval.start_time.date()
                    day_data[d][svc]['cpu'] = round(point.value.double_value * 100, 1)
            self.stdout.write('  Done')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  CPU utilization query failed: {e}'))

        # 6. Memory utilization
        self.stdout.write('Querying memory utilization...')
        try:
            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": (
                        'metric.type = "run.googleapis.com/container/memory/utilizations" '
                        f'AND resource.type = "cloud_run_revision" {serving_filter}'
                    ),
                    "interval": interval,
                    "aggregation": monitoring_v3.Aggregation(
                        alignment_period={"seconds": 86400},
                        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
                        cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_NONE,
                        group_by_fields=["resource.labels.service_name"],
                    ),
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            for ts in results:
                svc = ts.resource.labels.get("service_name", "unknown")
                for point in ts.points:
                    d = point.interval.start_time.date()
                    day_data[d][svc]['memory'] = round(point.value.double_value * 100, 1)
            self.stdout.write('  Done')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Memory utilization query failed: {e}'))

        # Aggregate per project per day and persist
        self.stdout.write(f'\nAggregating data across {len(day_data)} days...')
        created_count = 0
        updated_count = 0

        for target_date in sorted(day_data.keys()):
            services_on_day = day_data[target_date]

            # Group by project
            project_agg = defaultdict(lambda: {
                'project': None,
                'requests': 0, 'errors': 0,
                'weighted_p50': 0, 'weighted_p95': 0, 'weighted_p99': 0,
                'total_weight': 0,
                'endpoint_details': [],
                'instance_details': [],
                'startup_latency_details': [],
                'peak_instances': 0, 'total_avg_instances': 0,
                'total_cpu': 0, 'total_memory': 0, 'util_count': 0,
            })

            for svc_name, metrics in services_on_day.items():
                project = service_to_project.get(svc_name)
                if not project:
                    continue

                pd = project_agg[project.id]
                pd['project'] = project

                requests = metrics['requests']
                pd['requests'] += requests
                pd['errors'] += metrics['errors']

                if requests > 0:
                    pd['weighted_p50'] += metrics['p50'] * requests
                    pd['weighted_p95'] += metrics['p95'] * requests
                    pd['weighted_p99'] += metrics['p99'] * requests
                    pd['total_weight'] += requests

                pd['endpoint_details'].append({
                    'name': svc_name,
                    'requests': requests,
                    'errors': metrics['errors'],
                    'latency_p50_ms': round(metrics['p50'], 1),
                    'latency_p95_ms': round(metrics['p95'], 1),
                    'latency_p99_ms': round(metrics['p99'], 1),
                })

                pd['instance_details'].append({
                    'name': svc_name,
                    'peak': metrics['inst_peak'],
                    'avg': round(metrics['inst_avg'], 1),
                })
                pd['peak_instances'] = max(pd['peak_instances'], metrics['inst_peak'])
                pd['total_avg_instances'] += metrics['inst_avg']

                if metrics['startup_p50'] > 0 or metrics['startup_p95'] > 0:
                    pd['startup_latency_details'].append({
                        'name': svc_name,
                        'p50_ms': round(metrics['startup_p50'], 1),
                        'p95_ms': round(metrics['startup_p95'], 1),
                    })

                if metrics['cpu'] > 0 or metrics['memory'] > 0:
                    pd['total_cpu'] += metrics['cpu']
                    pd['total_memory'] += metrics['memory']
                    pd['util_count'] += 1

            for project_id_val, pd in project_agg.items():
                w = pd['total_weight']
                uc = pd['util_count']

                defaults = {
                    'total_requests': pd['requests'],
                    'error_count': pd['errors'],
                    'latency_p50_ms': round(pd['weighted_p50'] / w, 1) if w > 0 else 0,
                    'latency_p95_ms': round(pd['weighted_p95'] / w, 1) if w > 0 else 0,
                    'latency_p99_ms': round(pd['weighted_p99'] / w, 1) if w > 0 else 0,
                    'endpoint_details': pd['endpoint_details'],
                    'instance_count_peak': pd['peak_instances'],
                    'instance_count_avg': round(pd['total_avg_instances'], 1),
                    'instance_details': pd['instance_details'],
                    'startup_latency_details': pd['startup_latency_details'],
                    'cpu_utilization_avg': round(pd['total_cpu'] / uc, 1) if uc > 0 else 0,
                    'memory_utilization_avg': round(pd['total_memory'] / uc, 1) if uc > 0 else 0,
                }

                if dry_run:
                    self.stdout.write(
                        f'  {target_date} {pd["project"].name}: '
                        f'req={pd["requests"]:,} err={pd["errors"]} '
                        f'peak_inst={pd["peak_instances"]} '
                        f'cpu={defaults["cpu_utilization_avg"]:.1f}% mem={defaults["memory_utilization_avg"]:.1f}%'
                    )
                    continue

                _, created = ProjectMetrics.objects.update_or_create(
                    date=target_date,
                    model_endpoint=pd['project'],
                    defaults=defaults,
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
