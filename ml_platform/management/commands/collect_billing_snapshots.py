"""
Management command to collect daily billing snapshots from GCP Billing Export.

Queries the BigQuery resource-level billing export for the previous day's costs,
classifies each row into a category (Data, Training, Inference, System),
applies platform margins from BillingConfig, and stores BillingSnapshot records.

Usage:
    python manage.py collect_billing_snapshots

    # Collect for a specific date
    python manage.py collect_billing_snapshots --date 2026-02-01

    # Backfill historical data
    python manage.py collect_billing_snapshots --backfill --days 30

    # Dry run (show what would be collected)
    python manage.py collect_billing_snapshots --dry-run
"""
import os
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from ml_platform.models import BillingConfig, BillingSnapshot, Deployment

logger = logging.getLogger(__name__)

CATEGORY_MAP = {
    'BigQuery': 'Data',
    'Cloud SQL': 'Data',
    'Cloud Dataflow': 'Data',
    'Cloud Storage': 'Data',
    'Vertex AI': 'Training',
    'Cloud Scheduler': 'System',
    'Secret Manager': 'System',
    'Cloud Build': 'System',
    'Artifact Registry': 'System',
    'Cloud Logging': 'System',
}


class Command(BaseCommand):
    help = 'Collect daily billing snapshots from GCP Billing Export'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Date to collect for (YYYY-MM-DD). Defaults to yesterday.'
        )
        parser.add_argument(
            '--backfill',
            action='store_true',
            help='Backfill historical data (use with --days)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to backfill (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be collected without saving'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        config = BillingConfig.get_solo()

        # Cache inference service names for Cloud Run classification
        self._inference_services = set(
            Deployment.objects.exclude(cloud_run_service='')
            .values_list('cloud_run_service', flat=True)
            .distinct()
        )

        if options['backfill']:
            return self._backfill(config, options['days'], dry_run)

        # Default: collect for yesterday (billing export has ~24h delay)
        target_date = (timezone.now() - timedelta(days=1)).date()
        if options['date']:
            target_date = date.fromisoformat(options['date'])

        self._collect_date(config, target_date, dry_run)

    def _backfill(self, config, days, dry_run):
        """Backfill billing snapshots for the last N days."""
        today = timezone.now().date()
        self.stdout.write(f'Backfilling billing snapshots for {days} days...\n')

        total_services = 0
        for i in range(days, 0, -1):
            target = today - timedelta(days=i)
            count = self._collect_date(config, target, dry_run)
            total_services += count

        self.stdout.write(self.style.SUCCESS(
            f'\nBackfill complete: {total_services} service-day records'
        ))

    def _classify_row(self, row):
        """
        Classify a billing row into (category, display_service_name).
        Returns a tuple of (category, service_name).
        """
        service_name = row['service_name']

        # Cloud Run: check if it's an inference service or system service
        if service_name == 'Cloud Run':
            cloud_run_service = row.get('cloud_run_service')
            if cloud_run_service and cloud_run_service in self._inference_services:
                return 'Inference', f'Cloud Run — {cloud_run_service}'
            return 'System', 'Cloud Run'

        # Vertex AI: split into GPU and CPU sub-rows
        if service_name == 'Vertex AI':
            if row.get('is_gpu'):
                return 'Training', 'Vertex AI \u2014 GPU'
            return 'Training', 'Vertex AI \u2014 CPU'

        # Everything else: look up in CATEGORY_MAP, default to System
        category = CATEGORY_MAP.get(service_name, 'System')
        return category, service_name

    def _collect_date(self, config, target_date, dry_run):
        """Collect billing data for a single date. Returns number of services found."""
        self.stdout.write(f'Collecting billing for {target_date}...')

        try:
            rows = self._query_billing_export(config, target_date)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  BigQuery query failed: {e}'))
            return 0

        if not rows:
            self.stdout.write(f'  No billing data for {target_date}')
            return 0

        snapshot_objects = []
        for row in rows:
            gcp_cost = Decimal(str(round(row['gcp_cost'], 2)))
            if gcp_cost <= 0:
                continue

            category, service_name = self._classify_row(row)
            margin_pct = config.get_margin_pct(service_name)
            platform_fee = (gcp_cost * margin_pct / 100).quantize(Decimal('0.01'))
            total_cost = gcp_cost + platform_fee

            if dry_run:
                self.stdout.write(
                    f'  [{category}] {service_name}: ${gcp_cost} + ${platform_fee} ({margin_pct}%) = ${total_cost}'
                )
            else:
                snapshot_objects.append(BillingSnapshot(
                    date=target_date,
                    category=category,
                    service_name=service_name,
                    gcp_cost=gcp_cost,
                    margin_pct=margin_pct,
                    platform_fee=platform_fee,
                    total_cost=total_cost,
                ))

        count = len(snapshot_objects) if not dry_run else sum(
            1 for r in rows if Decimal(str(round(r['gcp_cost'], 2))) > 0
        )

        if dry_run:
            self.stdout.write(self.style.WARNING(f'  DRY RUN \u2014 {count} services (not saved)'))
        else:
            # Delete-and-recreate for clean schema transition
            BillingSnapshot.objects.filter(date=target_date).delete()
            BillingSnapshot.objects.bulk_create(snapshot_objects)
            self.stdout.write(self.style.SUCCESS(f'  {count} services saved'))

        return count

    def _query_billing_export(self, config, target_date):
        """Query GCP resource-level Billing Export for a given date."""
        from google.cloud import bigquery

        project_id = getattr(
            settings, 'GCP_PROJECT_ID',
            os.getenv('GCP_PROJECT_ID', 'b2b-recs')
        )
        client = bigquery.Client(project=project_id)

        query = f"""
            SELECT
                service.description AS service_name,
                CASE
                    WHEN service.description = 'Cloud Run'
                    THEN REGEXP_EXTRACT(resource.name, r'(?:services|jobs)/([^/]+)')
                    ELSE NULL
                END AS cloud_run_service,
                CASE
                    WHEN service.description = 'Vertex AI'
                        AND (sku.description LIKE '%GPU%' OR sku.description LIKE '%Nvidia%')
                    THEN TRUE
                    ELSE FALSE
                END AS is_gpu,
                SUM(cost) + SUM(IFNULL((
                    SELECT SUM(c.amount) FROM UNNEST(credits) c
                ), 0)) AS gcp_cost
            FROM `{config.billing_export_project}.{config.billing_export_dataset}.gcp_billing_export_resource_v1_*`
            WHERE project.id = @client_project_id
                AND DATE(usage_start_time) = @target_date
            GROUP BY service_name, cloud_run_service, is_gpu
            HAVING gcp_cost > 0
            ORDER BY gcp_cost DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter('client_project_id', 'STRING', config.client_project_id),
                bigquery.ScalarQueryParameter('target_date', 'DATE', target_date),
            ]
        )

        result = client.query(query, job_config=job_config)
        return [
            {
                'service_name': row.service_name,
                'cloud_run_service': row.cloud_run_service,
                'is_gpu': row.is_gpu,
                'gcp_cost': row.gcp_cost,
            }
            for row in result
        ]
