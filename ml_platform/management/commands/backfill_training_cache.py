"""
Management command to backfill training_history_json cache for completed experiments.

Usage:
    python manage.py backfill_training_cache

    # Limit to specific number
    python manage.py backfill_training_cache --limit 10

    # Dry run (show what would be processed)
    python manage.py backfill_training_cache --dry-run

    # Force re-cache even if already cached
    python manage.py backfill_training_cache --force
"""
import time
from django.core.management.base import BaseCommand
from ml_platform.models import QuickTest
from ml_platform.experiments.training_cache_service import TrainingCacheService


class Command(BaseCommand):
    help = 'Backfill training_history_json for completed experiments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of experiments to process'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-cache even if training_history_json already exists'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        force = options['force']

        # Find completed experiments that need caching
        queryset = QuickTest.objects.filter(
            status='completed',
            mlflow_run_id__isnull=False,
        ).exclude(
            mlflow_run_id=''
        )

        if not force:
            queryset = queryset.filter(training_history_json__isnull=True)

        queryset = queryset.order_by('-created_at')

        if limit:
            queryset = queryset[:limit]

        experiments = list(queryset)
        total = len(experiments)

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                'No experiments need caching.'
            ))
            return

        self.stdout.write(f'Found {total} experiment(s) to process.\n')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made.\n'))
            for qt in experiments:
                self.stdout.write(f'  Would cache: QuickTest {qt.id} - {qt.display_name}')
            return

        cache_service = TrainingCacheService()
        success_count = 0
        error_count = 0

        for i, qt in enumerate(experiments, 1):
            self.stdout.write(f'[{i}/{total}] Processing QuickTest {qt.id} - {qt.display_name}...')

            try:
                start_time = time.time()
                success = cache_service.cache_training_history(qt)
                elapsed = time.time() - start_time

                if success:
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  Cached in {elapsed:.1f}s'
                    ))
                else:
                    error_count += 1
                    self.stdout.write(self.style.WARNING(
                        f'  Failed to cache (non-fatal)'
                    ))

            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(
                    f'  Error: {e}'
                ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Completed: {success_count} cached, {error_count} errors'
        ))
