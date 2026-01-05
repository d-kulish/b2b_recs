"""
Management command to backfill recall metrics from training_history_json to direct DB fields.

This command populates recall_at_5, recall_at_10, recall_at_50, recall_at_100 fields
from the cached training_history_json['final_metrics'] for completed experiments.

Usage:
    python manage.py backfill_recall_metrics

    # Limit to specific number
    python manage.py backfill_recall_metrics --limit 10

    # Dry run (show what would be processed)
    python manage.py backfill_recall_metrics --dry-run

    # Force re-populate even if fields already have values
    python manage.py backfill_recall_metrics --force
"""
from django.core.management.base import BaseCommand
from ml_platform.models import QuickTest


class Command(BaseCommand):
    help = 'Backfill recall metrics from training_history_json to direct DB fields'

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
            help='Re-populate even if recall fields already have values'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        force = options['force']

        # Find completed experiments with training_history_json
        queryset = QuickTest.objects.filter(
            status='completed',
        ).exclude(
            training_history_json__isnull=True
        ).exclude(
            training_history_json={}
        )

        # If not force, only process records missing recall metrics
        if not force:
            queryset = queryset.filter(
                recall_at_5__isnull=True
            )

        queryset = queryset.order_by('-created_at')

        if limit:
            queryset = queryset[:limit]

        experiments = list(queryset)
        total = len(experiments)

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                'No experiments need recall metrics backfill.'
            ))
            return

        self.stdout.write(f'Found {total} experiment(s) to process.\n')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made.\n'))
            for qt in experiments:
                history = qt.training_history_json if isinstance(qt.training_history_json, dict) else {}
                final_metrics = history.get('final_metrics', {})
                r5 = final_metrics.get('test_recall_at_5')
                r10 = final_metrics.get('test_recall_at_10')
                r50 = final_metrics.get('test_recall_at_50')
                r100 = final_metrics.get('test_recall_at_100')
                r5_str = f'{r5:.4f}' if r5 is not None else 'N/A'
                r10_str = f'{r10:.4f}' if r10 is not None else 'N/A'
                r50_str = f'{r50:.4f}' if r50 is not None else 'N/A'
                r100_str = f'{r100:.4f}' if r100 is not None else 'N/A'
                self.stdout.write(
                    f'  Would update: QuickTest {qt.id} (Exp #{qt.experiment_number}) - '
                    f'R@5={r5_str}, R@10={r10_str}, R@50={r50_str}, R@100={r100_str}'
                )
            return

        success_count = 0
        error_count = 0
        skipped_count = 0

        for i, qt in enumerate(experiments, 1):
            self.stdout.write(f'[{i}/{total}] Processing QuickTest {qt.id} (Exp #{qt.experiment_number})...')

            try:
                history = qt.training_history_json if isinstance(qt.training_history_json, dict) else {}
                final_metrics = history.get('final_metrics', {})

                if not final_metrics:
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(
                        f'  Skipped: No final_metrics in training_history_json'
                    ))
                    continue

                update_fields = []

                # Extract recall metrics
                r5 = final_metrics.get('test_recall_at_5')
                if r5 is not None:
                    qt.recall_at_5 = r5
                    update_fields.append('recall_at_5')

                r10 = final_metrics.get('test_recall_at_10')
                if r10 is not None:
                    qt.recall_at_10 = r10
                    update_fields.append('recall_at_10')

                r50 = final_metrics.get('test_recall_at_50')
                if r50 is not None:
                    qt.recall_at_50 = r50
                    update_fields.append('recall_at_50')

                r100 = final_metrics.get('test_recall_at_100')
                if r100 is not None:
                    qt.recall_at_100 = r100
                    update_fields.append('recall_at_100')

                # Also extract loss if available
                loss = final_metrics.get('test_loss') or final_metrics.get('final_loss')
                if loss is not None:
                    qt.loss = loss
                    update_fields.append('loss')

                if update_fields:
                    qt.save(update_fields=update_fields)
                    success_count += 1
                    r5_str = f'{r5:.4f}' if r5 is not None else 'N/A'
                    r10_str = f'{r10:.4f}' if r10 is not None else 'N/A'
                    r50_str = f'{r50:.4f}' if r50 is not None else 'N/A'
                    r100_str = f'{r100:.4f}' if r100 is not None else 'N/A'
                    self.stdout.write(self.style.SUCCESS(
                        f'  Updated: R@5={r5_str}, R@10={r10_str}, R@50={r50_str}, R@100={r100_str}'
                    ))
                else:
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(
                        f'  Skipped: No recall metrics found in final_metrics'
                    ))

            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(
                    f'  Error: {e}'
                ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Completed: {success_count} updated, {skipped_count} skipped, {error_count} errors'
        ))
