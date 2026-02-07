"""
Management command to create/delete a Cloud Scheduler job for daily GCS artifact cleanup.

Usage:
    # Create the scheduler job
    python manage.py setup_cleanup_scheduler --url https://your-app.run.app

    # Delete the scheduler job
    python manage.py setup_cleanup_scheduler --delete
"""
import os
import json
import logging
from urllib.parse import urlparse

from django.core.management.base import BaseCommand
from django.conf import settings
from google.cloud import scheduler_v1
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger(__name__)

JOB_NAME = 'cleanup-gcs-artifacts'
SCHEDULE = '0 3 * * *'  # Daily at 03:00 UTC


class Command(BaseCommand):
    help = 'Create or delete a Cloud Scheduler job for daily GCS artifact cleanup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--url',
            type=str,
            default=None,
            help='Cloud Run service base URL (e.g. https://your-app.run.app)'
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Delete the scheduler job instead of creating it'
        )

    def handle(self, *args, **options):
        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs'))
        region = getattr(settings, 'GCP_SCHEDULER_REGION', os.getenv('CLOUD_SCHEDULER_REGION', 'europe-central2'))

        from ml_platform.utils.cloud_scheduler import CloudSchedulerManager
        manager = CloudSchedulerManager(project_id=project_id, region=region)

        full_job_name = f"{manager.parent}/jobs/{JOB_NAME}"

        if options['delete']:
            self._delete_job(manager.client, full_job_name)
            return

        base_url = options['url']
        if not base_url:
            self.stderr.write(self.style.ERROR(
                'Please provide the Cloud Run service URL with --url'
            ))
            return

        # Build webhook URL
        base_url = base_url.rstrip('/')
        webhook_url = f"{base_url}/api/system/cleanup-artifacts-webhook/"

        # Service account for OIDC authentication
        service_account = (
            getattr(settings, 'GCP_SERVICE_ACCOUNT_EMAIL', None)
            or os.getenv('GCP_SERVICE_ACCOUNT_EMAIL')
            or f'{project_id}@appspot.gserviceaccount.com'
        )

        # OIDC audience is the base URL (scheme + netloc)
        parsed = urlparse(webhook_url)
        audience = f"{parsed.scheme}://{parsed.netloc}"

        http_target = scheduler_v1.HttpTarget(
            uri=webhook_url,
            http_method=scheduler_v1.HttpMethod.POST,
            headers={'Content-Type': 'application/json'},
            body=json.dumps({'trigger': 'scheduled'}).encode('utf-8'),
            oidc_token=scheduler_v1.OidcToken(
                service_account_email=service_account,
                audience=audience,
            ),
        )

        job = scheduler_v1.Job(
            name=full_job_name,
            description='Daily GCS artifact cleanup for ML Platform (preserves registered models)',
            schedule=SCHEDULE,
            time_zone='UTC',
            http_target=http_target,
        )

        try:
            # Try to create; if exists, update
            try:
                created_job = manager.client.create_job(
                    request=scheduler_v1.CreateJobRequest(
                        parent=manager.parent,
                        job=job,
                    )
                )
                self.stdout.write(self.style.SUCCESS(
                    f'Created scheduler job: {created_job.name}\n'
                    f'  Schedule: {SCHEDULE} (daily at 03:00 UTC)\n'
                    f'  Target: {webhook_url}\n'
                    f'  Auth: OIDC ({service_account})'
                ))
            except google_exceptions.AlreadyExists:
                updated_job = manager.client.update_job(
                    request=scheduler_v1.UpdateJobRequest(job=job)
                )
                self.stdout.write(self.style.SUCCESS(
                    f'Updated existing scheduler job: {updated_job.name}\n'
                    f'  Schedule: {SCHEDULE} (daily at 03:00 UTC)\n'
                    f'  Target: {webhook_url}\n'
                    f'  Auth: OIDC ({service_account})'
                ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to create scheduler job: {e}'))

    def _delete_job(self, client, full_job_name):
        try:
            client.delete_job(
                request=scheduler_v1.DeleteJobRequest(name=full_job_name)
            )
            self.stdout.write(self.style.SUCCESS(f'Deleted scheduler job: {full_job_name}'))
        except google_exceptions.NotFound:
            self.stdout.write(self.style.WARNING(f'Scheduler job not found (already deleted): {full_job_name}'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to delete scheduler job: {e}'))
