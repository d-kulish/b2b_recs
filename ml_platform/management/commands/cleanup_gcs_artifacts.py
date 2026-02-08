"""
Management command to selectively clean up GCS training artifacts.

Deletes artifacts for old, non-registered training runs while preserving
pushed_model/ directories for models registered in Vertex AI Model Registry.

Usage:
    # Dry run (preview what would be deleted)
    python manage.py cleanup_gcs_artifacts --dry-run

    # Delete artifacts older than 7 days (default)
    python manage.py cleanup_gcs_artifacts

    # Delete artifacts older than 14 days
    python manage.py cleanup_gcs_artifacts --days 14

    # Also delete artifacts for registered models (use with caution)
    python manage.py cleanup_gcs_artifacts --include-registered
"""
import os
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from ml_platform.training.models import TrainingRun

logger = logging.getLogger(__name__)

TRAINING_BUCKET = 'b2b-recs-training-artifacts'
STAGING_BUCKET = 'b2b-recs-pipeline-staging'


class Command(BaseCommand):
    help = 'Selectively clean up GCS training artifacts, preserving registered models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete artifacts older than N days (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--include-registered',
            action='store_true',
            help='Also delete artifacts for registered models (requires explicit opt-in)'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        include_registered = options['include_registered']

        cutoff = timezone.now() - timedelta(days=days)

        self.stdout.write(f'GCS Artifact Cleanup (cutoff: {cutoff.date()}, {days} days)\n')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no files will be deleted.\n'))

        # Get GCS client
        storage_client = self._get_storage_client()
        if not storage_client:
            return

        # Query terminal training runs older than cutoff
        terminal_statuses = [
            'completed', 'failed', 'cancelled', 'not_blessed',
            'deployed', 'deploy_failed',
        ]
        old_runs = TrainingRun.objects.filter(
            status__in=terminal_statuses,
            completed_at__lt=cutoff,
        ).select_related('registered_model')

        total_runs = old_runs.count()
        self.stdout.write(f'Found {total_runs} terminal training run(s) older than {days} days.\n')

        deleted_count = 0
        preserved_count = 0
        total_bytes_freed = 0
        errors = []

        for run in old_runs:
            # Check if run has a registered model in Vertex AI
            is_registered = bool(run.vertex_model_resource_name)

            if is_registered and not include_registered:
                preserved_count += 1
                if dry_run:
                    self.stdout.write(
                        f'  PRESERVE: TR-{run.id} #{run.run_number} '
                        f'({run.status}) - registered model'
                    )
                continue

            # Delete training artifacts
            run_bytes = 0
            gcs_path = run.gcs_artifacts_path

            if gcs_path:
                try:
                    bytes_freed = self._delete_gcs_path(
                        storage_client, gcs_path, f'TR-{run.id}', dry_run
                    )
                    run_bytes += bytes_freed
                except Exception as e:
                    errors.append(f'TR-{run.id} artifacts: {e}')
                    self.stdout.write(self.style.WARNING(
                        f'  ERROR: TR-{run.id} artifacts: {e}'
                    ))

            # Delete pipeline staging artifacts
            if run.cloud_build_run_id:
                staging_path = f'gs://{STAGING_BUCKET}/pipeline_root/{run.cloud_build_run_id}/'
                try:
                    bytes_freed = self._delete_gcs_path(
                        storage_client, staging_path, f'TR-{run.id} staging', dry_run
                    )
                    run_bytes += bytes_freed
                except Exception as e:
                    errors.append(f'TR-{run.id} staging: {e}')
                    self.stdout.write(self.style.WARNING(
                        f'  ERROR: TR-{run.id} staging: {e}'
                    ))

            if run_bytes > 0 or gcs_path:
                action = 'WOULD DELETE' if dry_run else 'DELETED'
                self.stdout.write(
                    f'  {action}: TR-{run.id} #{run.run_number} '
                    f'({run.status}) - {self._format_bytes(run_bytes)}'
                )
                deleted_count += 1
                total_bytes_freed += run_bytes

        # Clean orphaned directories in training bucket
        orphan_bytes = self._clean_orphaned_directories(
            storage_client, dry_run
        )
        total_bytes_freed += orphan_bytes

        # Summary
        self.stdout.write('')
        action = 'Would delete' if dry_run else 'Deleted'
        self.stdout.write(self.style.SUCCESS(
            f'{action} artifacts for {deleted_count} run(s), '
            f'preserved {preserved_count} registered model(s), '
            f'freed ~{self._format_bytes(total_bytes_freed)}'
        ))

        if errors:
            self.stdout.write(self.style.WARNING(
                f'{len(errors)} error(s) during cleanup'
            ))

        # Don't return a dict — Django's BaseCommand.execute() calls
        # stdout.write(output) on truthy return values, which fails on dicts.

    def _get_storage_client(self):
        """Get GCS client with error handling."""
        try:
            from google.cloud import storage
            project_id = getattr(
                settings, 'GCP_PROJECT_ID',
                os.getenv('GCP_PROJECT_ID', 'b2b-recs')
            )
            return storage.Client(project=project_id)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to create GCS client: {e}'))
            return None

    def _delete_gcs_path(self, storage_client, gcs_path, display_name, dry_run):
        """
        Delete all objects under a GCS path. Returns bytes freed.

        Args:
            storage_client: google.cloud.storage.Client
            gcs_path: Full GCS URI (gs://bucket/prefix)
            display_name: Display name for logging
            dry_run: If True, only count bytes without deleting
        """
        if not gcs_path.startswith('gs://'):
            gcs_path = f'gs://{TRAINING_BUCKET}/{gcs_path}'

        path_parts = gcs_path[5:].split('/', 1)
        bucket_name = path_parts[0]
        prefix = path_parts[1].rstrip('/') if len(path_parts) > 1 else ''

        if not prefix:
            return 0

        bucket = storage_client.bucket(bucket_name)
        blobs = list(bucket.list_blobs(prefix=prefix))

        if not blobs:
            return 0

        total_bytes = sum(b.size or 0 for b in blobs)

        if not dry_run:
            for blob in blobs:
                try:
                    blob.delete()
                except Exception as e:
                    logger.warning(f'Failed to delete blob {blob.name}: {e}')

        return total_bytes

    def _clean_orphaned_directories(self, storage_client, dry_run):
        """
        Find and clean directories in the training bucket that don't match
        any TrainingRun in the database.
        """
        bucket = storage_client.bucket(TRAINING_BUCKET)

        # List top-level prefixes (tr-{id}-{timestamp}/)
        known_prefixes = set()
        for run in TrainingRun.objects.exclude(gcs_artifacts_path=''):
            path = run.gcs_artifacts_path
            if path.startswith('gs://'):
                parts = path[5:].split('/', 2)
                if len(parts) >= 2 and parts[0] == TRAINING_BUCKET:
                    known_prefixes.add(parts[1])
            else:
                top = path.split('/')[0]
                if top:
                    known_prefixes.add(top)

        # List actual top-level directories in bucket
        orphan_bytes = 0
        orphan_count = 0
        iterator = bucket.list_blobs(delimiter='/')
        # Consume the iterator to populate prefixes
        list(iterator)

        for prefix in iterator.prefixes:
            dir_name = prefix.rstrip('/')
            if dir_name not in known_prefixes:
                blobs = list(bucket.list_blobs(prefix=prefix))
                dir_bytes = sum(b.size or 0 for b in blobs)

                if blobs:
                    action = 'WOULD DELETE' if dry_run else 'DELETED'
                    self.stdout.write(
                        f'  {action} orphan: {dir_name}/ '
                        f'({len(blobs)} objects, {self._format_bytes(dir_bytes)})'
                    )

                    if not dry_run:
                        for blob in blobs:
                            try:
                                blob.delete()
                            except Exception as e:
                                logger.warning(f'Failed to delete orphan blob {blob.name}: {e}')

                    orphan_bytes += dir_bytes
                    orphan_count += 1

        if orphan_count:
            self.stdout.write(
                f'  Found {orphan_count} orphaned director(ies) '
                f'({self._format_bytes(orphan_bytes)})'
            )

        return orphan_bytes

    @staticmethod
    def _format_bytes(num_bytes):
        """Format bytes into human-readable string."""
        if num_bytes < 1024:
            return f'{num_bytes} B'
        elif num_bytes < 1024 ** 2:
            return f'{num_bytes / 1024:.1f} KB'
        elif num_bytes < 1024 ** 3:
            return f'{num_bytes / 1024 ** 2:.1f} MB'
        else:
            return f'{num_bytes / 1024 ** 3:.2f} GB'
