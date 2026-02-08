"""
Management command to clean up orphaned RegisteredModel records.

Deletes RegisteredModel records that were never registered to Vertex AI
(empty vertex_model_resource_name) and have no active training runs.

Usage:
    # Dry run (preview what would be deleted)
    python manage.py cleanup_orphan_models --dry-run

    # Delete orphans older than 7 days (default)
    python manage.py cleanup_orphan_models

    # Delete orphans older than 14 days
    python manage.py cleanup_orphan_models --days 14
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from ml_platform.training.models import RegisteredModel, TrainingRun

logger = logging.getLogger(__name__)

# Non-terminal statuses — a training run in one of these states may still
# succeed and register the model, so we must not delete its RegisteredModel.
NON_TERMINAL_STATUSES = [
    TrainingRun.STATUS_PENDING,
    TrainingRun.STATUS_SCHEDULED,
    TrainingRun.STATUS_SUBMITTING,
    TrainingRun.STATUS_RUNNING,
    TrainingRun.STATUS_DEPLOYING,
]


class Command(BaseCommand):
    help = 'Clean up orphaned RegisteredModel records (never registered to Vertex AI)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete orphans older than N days (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        cutoff = timezone.now() - timedelta(days=days)

        self.stdout.write(f'Orphan RegisteredModel Cleanup (cutoff: {cutoff.date()}, {days} days)\n')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no records will be deleted.\n'))

        # Find orphans: no vertex_model_resource_name, older than cutoff
        orphans = RegisteredModel.objects.filter(
            Q(vertex_model_resource_name='') | Q(vertex_model_resource_name__isnull=True),
            created_at__lt=cutoff,
        )

        total_orphans = orphans.count()
        self.stdout.write(f'Found {total_orphans} orphaned RegisteredModel(s) older than {days} days.\n')

        deleted_count = 0
        skipped_count = 0

        for orphan in orphans:
            # Check for linked training runs in non-terminal states
            active_runs = TrainingRun.objects.filter(
                registered_model=orphan,
                status__in=NON_TERMINAL_STATUSES,
            )

            if active_runs.exists():
                skipped_count += 1
                if dry_run:
                    self.stdout.write(
                        f'  SKIP: "{orphan.model_name}" (id={orphan.id}) '
                        f'- {active_runs.count()} active training run(s)'
                    )
                continue

            # List linked training runs for audit trail
            linked_runs = TrainingRun.objects.filter(registered_model=orphan)
            run_summary = ', '.join(
                f'TR-{r.id} ({r.status})' for r in linked_runs[:5]
            )
            if linked_runs.count() > 5:
                run_summary += f' ... and {linked_runs.count() - 5} more'

            action = 'WOULD DELETE' if dry_run else 'DELETED'
            self.stdout.write(
                f'  {action}: "{orphan.model_name}" (id={orphan.id}, '
                f'created={orphan.created_at.date()}, '
                f'runs: {run_summary or "none"})'
            )

            if not dry_run:
                orphan.delete()

            deleted_count += 1

        # Summary
        self.stdout.write('')
        action = 'Would delete' if dry_run else 'Deleted'
        self.stdout.write(self.style.SUCCESS(
            f'{action} {deleted_count} orphaned RegisteredModel(s), '
            f'skipped {skipped_count} with active training runs'
        ))
