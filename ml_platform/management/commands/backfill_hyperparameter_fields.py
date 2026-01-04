"""
Management command to backfill denormalized hyperparameter fields for existing experiments.

These fields enable fast TPE-based hyperparameter analysis without joins.

Usage:
    python manage.py backfill_hyperparameter_fields

    # Limit to specific number
    python manage.py backfill_hyperparameter_fields --limit 10

    # Dry run (show what would be processed)
    python manage.py backfill_hyperparameter_fields --dry-run

    # Force re-populate even if fields already exist
    python manage.py backfill_hyperparameter_fields --force
"""
import time
from django.core.management.base import BaseCommand
from ml_platform.models import QuickTest
from ml_platform.experiments.hyperparameter_analyzer import (
    get_l2_category, get_tower_structure, get_primary_activation,
    get_max_l2_reg, estimate_tower_params
)


class Command(BaseCommand):
    help = 'Backfill denormalized hyperparameter fields for experiments'

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
            help='Re-populate even if fields already have values'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        force = options['force']

        # Find experiments that need field population
        # Look for experiments where optimizer is null (one of the new fields)
        queryset = QuickTest.objects.filter(
            model_config__isnull=False,
            feature_config__isnull=False,
        ).select_related(
            'model_config',
            'feature_config',
            'feature_config__dataset',
        )

        if not force:
            # Only process experiments missing the new fields
            queryset = queryset.filter(optimizer__isnull=True)

        queryset = queryset.order_by('-created_at')

        if limit:
            queryset = queryset[:limit]

        experiments = list(queryset)
        total = len(experiments)

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                'No experiments need field population.'
            ))
            return

        self.stdout.write(f'Found {total} experiment(s) to process.\n')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made.\n'))
            for qt in experiments:
                self.stdout.write(f'  Would populate: QuickTest {qt.id} - {qt.display_name}')
            return

        success_count = 0
        error_count = 0

        for i, qt in enumerate(experiments, 1):
            self.stdout.write(f'[{i}/{total}] Processing QuickTest {qt.id} - {qt.display_name}...')

            try:
                start_time = time.time()
                self._populate_fields(qt)
                qt.save()
                elapsed = time.time() - start_time

                success_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  Populated in {elapsed:.2f}s'
                ))

            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(
                    f'  Error: {e}'
                ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Completed: {success_count} populated, {error_count} errors'
        ))

    def _populate_fields(self, qt):
        """Populate denormalized fields for a single QuickTest."""
        model_config = qt.model_config
        feature_config = qt.feature_config

        if not model_config or not feature_config:
            return

        # From ModelConfig - Training params
        qt.optimizer = model_config.optimizer
        qt.output_embedding_dim = model_config.output_embedding_dim
        qt.retrieval_algorithm = model_config.retrieval_algorithm
        qt.top_k = model_config.top_k

        # From ModelConfig - Architecture (derived)
        buyer_layers = model_config.buyer_tower_layers or []
        product_layers = model_config.product_tower_layers or []

        qt.buyer_tower_structure = get_tower_structure(buyer_layers)
        qt.product_tower_structure = get_tower_structure(product_layers)
        qt.buyer_activation = get_primary_activation(buyer_layers)
        qt.product_activation = get_primary_activation(product_layers)

        # L2 regularization as category
        buyer_l2 = get_max_l2_reg(buyer_layers)
        product_l2 = get_max_l2_reg(product_layers)
        qt.buyer_l2_category = get_l2_category(buyer_l2)
        qt.product_l2_category = get_l2_category(product_l2)

        # From FeatureConfig
        qt.buyer_tensor_dim = feature_config.buyer_tensor_dim
        qt.product_tensor_dim = feature_config.product_tensor_dim

        buyer_features = feature_config.buyer_model_features or []
        product_features = feature_config.product_model_features or []
        buyer_crosses = feature_config.buyer_model_crosses or []
        product_crosses = feature_config.product_model_crosses or []

        qt.buyer_feature_count = len(buyer_features)
        qt.product_feature_count = len(product_features)
        qt.buyer_cross_count = len(buyer_crosses)
        qt.product_cross_count = len(product_crosses)

        # Estimate tower params
        if feature_config.buyer_tensor_dim:
            qt.buyer_total_params = estimate_tower_params(
                buyer_layers, feature_config.buyer_tensor_dim
            )
        if feature_config.product_tensor_dim:
            qt.product_total_params = estimate_tower_params(
                product_layers, feature_config.product_tensor_dim
            )

        # From Dataset (via FeatureConfig)
        dataset = feature_config.dataset
        if dataset:
            qt.dataset_row_count = dataset.row_count_estimate
            qt.dataset_unique_users = dataset.unique_users_estimate
            qt.dataset_unique_products = dataset.unique_products_estimate

            # Calculate date range days
            if dataset.date_range_start and dataset.date_range_end:
                delta = dataset.date_range_end - dataset.date_range_start
                qt.dataset_date_range_days = delta.days
