"""
Management command to backfill RMSE/MAE metrics for completed training runs.

Due to a bug in the extraction logic, validation RMSE and MAE were looked up
under incorrect keys in final_metrics (bare 'rmse'/'mae' instead of
'val_rmse'/'val_mae' from the loss dict). This command re-extracts those
metrics from the cached training_history_json.

Usage:
    python manage.py backfill_ranking_metrics

    # Dry run (show what would be updated)
    python manage.py backfill_ranking_metrics --dry-run

    # Force re-populate even if fields already have values
    python manage.py backfill_ranking_metrics --force

    # Limit to specific number
    python manage.py backfill_ranking_metrics --limit 10
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from ml_platform.training.models import TrainingRun


class Command(BaseCommand):
    help = 'Backfill RMSE/MAE validation metrics from training_history_json for ranking/multitask training runs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of training runs to process'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-populate even if rmse/mae fields already have values'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        force = options['force']

        # Find completed ranking/multitask training runs with cached history
        queryset = TrainingRun.objects.filter(
            status=TrainingRun.STATUS_COMPLETED,
            model_type__in=[TrainingRun.MODEL_TYPE_RANKING, TrainingRun.MODEL_TYPE_MULTITASK],
        ).exclude(
            training_history_json__isnull=True,
        ).exclude(
            training_history_json={},
        )

        # If not force, only process records missing rmse or mae
        if not force:
            queryset = queryset.filter(
                Q(rmse__isnull=True) | Q(mae__isnull=True)
            )

        queryset = queryset.order_by('-created_at')

        if limit:
            queryset = queryset[:limit]

        runs = list(queryset)
        total = len(runs)

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                'No training runs need RMSE/MAE backfill.'
            ))
            return

        self.stdout.write(f'Found {total} training run(s) to process.\n')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made.\n'))

        success_count = 0
        error_count = 0
        skipped_count = 0

        for i, run in enumerate(runs, 1):
            self.stdout.write(
                f'[{i}/{total}] Processing TrainingRun {run.id} '
                f'({run.display_name}, type={run.model_type})...'
            )

            try:
                history = run.training_history_json if isinstance(run.training_history_json, dict) else {}
                loss_data = history.get('loss', {})

                if not loss_data:
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(
                        '  Skipped: No loss data in training_history_json'
                    ))
                    continue

                val_rmse_arr = loss_data.get('val_rmse')
                val_mae_arr = loss_data.get('val_mae')

                rmse_val = val_rmse_arr[-1] if val_rmse_arr else None
                mae_val = val_mae_arr[-1] if val_mae_arr else None

                if rmse_val is None and mae_val is None:
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(
                        '  Skipped: No val_rmse or val_mae in loss data'
                    ))
                    continue

                rmse_str = f'{rmse_val:.4f}' if rmse_val is not None else 'N/A'
                mae_str = f'{mae_val:.4f}' if mae_val is not None else 'N/A'

                if dry_run:
                    self.stdout.write(
                        f'  Would update: RMSE={rmse_str}, MAE={mae_str} '
                        f'(current: RMSE={run.rmse}, MAE={run.mae})'
                    )
                    success_count += 1
                    continue

                update_fields = []

                if rmse_val is not None:
                    run.rmse = rmse_val
                    update_fields.append('rmse')

                if mae_val is not None:
                    run.mae = mae_val
                    update_fields.append('mae')

                if update_fields:
                    run.save(update_fields=update_fields)
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  Updated: RMSE={rmse_str}, MAE={mae_str}'
                    ))
                else:
                    skipped_count += 1

            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(
                    f'  Error: {e}'
                ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Completed: {success_count} updated, {skipped_count} skipped, {error_count} errors'
        ))
