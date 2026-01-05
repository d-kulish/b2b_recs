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

        # Extract feature details (name + dimension) for TPE analysis
        qt.buyer_feature_details = extract_feature_details(buyer_features)
        qt.product_feature_details = extract_feature_details(product_features)
        qt.buyer_cross_details = extract_cross_details(buyer_crosses)
        qt.product_cross_details = extract_cross_details(product_crosses)

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
            # Row count - prefer row_count_estimate, fallback to summary_snapshot
            qt.dataset_row_count = dataset.row_count_estimate
            if not qt.dataset_row_count and dataset.summary_snapshot:
                qt.dataset_row_count = dataset.summary_snapshot.get('total_rows')

            qt.dataset_unique_users = dataset.unique_users_estimate
            qt.dataset_unique_products = dataset.unique_products_estimate

            # Calculate date range days
            if dataset.date_range_start and dataset.date_range_end:
                delta = dataset.date_range_end - dataset.date_range_start
                qt.dataset_date_range_days = delta.days

            # Extract dataset filter descriptions for TPE analysis
            populate_dataset_filter_fields(qt, dataset)


def populate_dataset_filter_fields(qt, dataset):
    """
    Extract filter descriptions from Dataset.filters and populate QuickTest fields.

    This enables TPE-based hyperparameter analysis for dataset filtering strategies.
    Each filter is converted to a human-readable description string.

    Args:
        qt: QuickTest instance to populate
        dataset: Dataset instance with filters JSONField
    """
    filters = dataset.filters or {}

    qt.dataset_date_filters = extract_date_filter_descriptions(filters)
    qt.dataset_customer_filters = extract_customer_filter_descriptions(filters)
    qt.dataset_product_filters = extract_product_filter_descriptions(filters)


def extract_date_filter_descriptions(filters):
    """Extract human-readable date filter descriptions."""
    descriptions = []
    date_filter = filters.get('date_filter') or filters.get('history', {})

    if date_filter:
        rolling_days = date_filter.get('rolling_days') or date_filter.get('days')
        if rolling_days:
            descriptions.append(f"Rolling {rolling_days} days")

        start_date = date_filter.get('start_date')
        if start_date:
            descriptions.append(f"From {start_date}")

    return descriptions if descriptions else None


def extract_customer_filter_descriptions(filters):
    """Extract human-readable customer filter descriptions."""
    descriptions = []
    customer_filter = filters.get('customer_filter', {})

    if not customer_filter:
        return None

    # Top revenue filter
    top_revenue = customer_filter.get('top_revenue', {})
    if top_revenue and top_revenue.get('enabled'):
        percent = (
            top_revenue.get('percent') or
            top_revenue.get('threshold_percent') or
            top_revenue.get('threshold')
        )
        if percent:
            descriptions.append(f"Top {int(percent)}% customers")

    # Aggregation filters (transaction count, spending)
    for agg_filter in customer_filter.get('aggregation_filters', []):
        filter_type = agg_filter.get('type')
        filter_op = agg_filter.get('filterType') or agg_filter.get('filter_type', '')
        value = agg_filter.get('value')

        if filter_type == 'transaction_count' and value is not None:
            op_symbol = '>' if filter_op == 'greater_than' else '<' if filter_op == 'less_than' else '='
            descriptions.append(f"Transaction count {op_symbol} {value}")
        elif filter_type == 'spending' and value is not None:
            op_symbol = '>' if filter_op == 'greater_than' else '<' if filter_op == 'less_than' else '='
            descriptions.append(f"Spending {op_symbol} {value}")

    # Category filters (city, etc.)
    for cat_filter in customer_filter.get('category_filters', []):
        column = cat_filter.get('column', '').split('.')[-1]
        mode = cat_filter.get('mode', 'include')
        values = cat_filter.get('values', [])

        if column and values:
            values_str = ', '.join(str(v) for v in values[:3])
            if len(values) > 3:
                values_str += f" (+{len(values) - 3})"
            op = '=' if mode == 'include' else '≠'
            descriptions.append(f"{column} {op} {values_str}")

    # Numeric filters
    for num_filter in customer_filter.get('numeric_filters', []):
        column = num_filter.get('column', '').split('.')[-1]
        filter_type = num_filter.get('filter_type', '')
        value = num_filter.get('value')
        min_val = num_filter.get('min')
        max_val = num_filter.get('max')

        if column:
            if filter_type == 'range' and min_val is not None and max_val is not None:
                descriptions.append(f"{column}: {min_val} - {max_val}")
            elif filter_type in ('greater_than', 'less_than', 'equals') and value is not None:
                op_symbol = '>' if filter_type == 'greater_than' else '<' if filter_type == 'less_than' else '='
                descriptions.append(f"{column} {op_symbol} {value}")

    return descriptions if descriptions else None


def extract_product_filter_descriptions(filters):
    """Extract human-readable product filter descriptions."""
    descriptions = []
    product_filter = filters.get('product_filter', {})

    if not product_filter:
        return None

    # Top revenue filter
    top_revenue = product_filter.get('top_revenue', {})
    if top_revenue and top_revenue.get('enabled'):
        threshold = (
            top_revenue.get('threshold_percent') or
            top_revenue.get('threshold') or
            top_revenue.get('percent')
        )
        if threshold:
            descriptions.append(f"Top {int(threshold)}% products")

    # Category filters
    for cat_filter in product_filter.get('category_filters', []):
        column = cat_filter.get('column', '').split('.')[-1]
        mode = cat_filter.get('mode', 'include')
        values = cat_filter.get('values', [])

        if column and values:
            values_str = ', '.join(str(v) for v in values[:3])
            if len(values) > 3:
                values_str += f" (+{len(values) - 3})"
            op = '=' if mode == 'include' else '≠'
            descriptions.append(f"{column} {op} {values_str}")

    # Numeric filters
    for num_filter in product_filter.get('numeric_filters', []):
        column = num_filter.get('column', '').split('.')[-1]
        filter_type = num_filter.get('filter_type', '')
        value = num_filter.get('value')
        min_val = num_filter.get('min')
        max_val = num_filter.get('max')

        if column:
            if filter_type == 'range' and min_val is not None and max_val is not None:
                descriptions.append(f"{column}: {min_val} - {max_val}")
            elif filter_type in ('greater_than', 'less_than', 'equals') and value is not None:
                op_symbol = '>' if filter_type == 'greater_than' else '<' if filter_type == 'less_than' else '='
                descriptions.append(f"{column} {op_symbol} {value}")

    return descriptions if descriptions else None


def extract_feature_details(features):
    """
    Extract feature name and dimension from feature config list.

    Args:
        features: List of feature config dicts from FeatureConfig

    Returns:
        List of {"name": "column_name", "dim": embedding_dim}
    """
    details = []
    for f in features:
        name = f.get('column') or f.get('display_name', 'unknown')
        dim = 0

        transforms = f.get('transforms', {})

        # Text embedding dimension
        embedding = transforms.get('embedding', {})
        if embedding.get('enabled'):
            dim = embedding.get('embedding_dim', 32)

        # Numeric bucketization dimension
        bucketize = transforms.get('bucketize', {})
        if bucketize.get('enabled'):
            dim = bucketize.get('embedding_dim', 32)

        # Numeric normalization (1D)
        normalize = transforms.get('normalize', {})
        if normalize.get('enabled'):
            dim = 1

        # Cyclical encoding (count 2D per cycle)
        cyclical = transforms.get('cyclical', {})
        cycle_dim = 0
        for cycle in ['annual', 'quarterly', 'monthly', 'weekly', 'daily']:
            if cyclical.get(cycle):
                cycle_dim += 2
        if cycle_dim > 0:
            dim = cycle_dim

        if dim > 0:
            details.append({'name': name, 'dim': dim})

    return details


def extract_cross_details(crosses):
    """
    Extract cross feature names and dimensions.

    Args:
        crosses: List of cross feature config dicts

    Returns:
        List of {"name": "col1 × col2", "dim": hash_bucket_size or embedding_dim}
    """
    details = []
    for c in crosses:
        # Cross features typically have 'columns' list or 'feature1'/'feature2' keys
        columns = c.get('columns', [])
        if not columns:
            # Try alternate format
            f1 = c.get('feature1', c.get('column1', ''))
            f2 = c.get('feature2', c.get('column2', ''))
            if f1 and f2:
                columns = [f1, f2]

        name = ' × '.join(columns) if columns else 'cross'
        dim = c.get('embedding_dim') or c.get('hash_bucket_size', 16)

        details.append({'name': name, 'dim': dim})

    return details
