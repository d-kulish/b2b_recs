"""
Experiments Domain Services

Core business logic for running ML experiments (Quick Tests):
- Code generation orchestration (Transform + Trainer modules)
- TFX pipeline compilation and submission to Vertex AI
- Status monitoring and results extraction
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ExperimentServiceError(Exception):
    """Custom exception for experiment service errors."""
    pass


class ExperimentService:
    """
    Service for orchestrating ML experiments (Quick Tests).

    Handles the complete lifecycle:
    1. Generate transform code from FeatureConfig
    2. Generate trainer code from FeatureConfig + ModelConfig
    3. Generate SQL query with split/sampling
    4. Upload code to GCS
    5. Compile and submit TFX pipeline to Vertex AI
    6. Monitor status and extract results
    """

    # GCS bucket names
    ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
    STAGING_BUCKET = 'b2b-recs-pipeline-staging'

    # Vertex AI configuration
    REGION = 'europe-central2'
    PIPELINE_DISPLAY_NAME_PREFIX = 'quicktest'

    def __init__(self, model_endpoint):
        """
        Initialize with a ModelEndpoint instance.

        Args:
            model_endpoint: ModelEndpoint instance for GCP configuration
        """
        self.model_endpoint = model_endpoint
        self.project_id = model_endpoint.gcp_project_id or getattr(
            settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs')
        )
        self._storage_client = None
        self._aiplatform_initialized = False

    @property
    def storage_client(self):
        """Lazy-load GCS client."""
        if self._storage_client is None:
            try:
                from google.cloud import storage
                self._storage_client = storage.Client(project=self.project_id)
            except ImportError:
                raise ExperimentServiceError(
                    "google-cloud-storage package not installed"
                )
        return self._storage_client

    def _init_aiplatform(self):
        """Initialize Vertex AI SDK."""
        if not self._aiplatform_initialized:
            try:
                from google.cloud import aiplatform
                aiplatform.init(
                    project=self.project_id,
                    location=self.REGION,
                    staging_bucket=f'gs://{self.STAGING_BUCKET}'
                )
                self._aiplatform_initialized = True
            except ImportError:
                raise ExperimentServiceError(
                    "google-cloud-aiplatform package not installed"
                )

    def submit_quick_test(
        self,
        feature_config,
        model_config,
        user=None,
        split_strategy: str = 'random',
        holdout_days: int = 1,
        date_column: str = '',
        data_sample_percent: int = 100,
        epochs: int = None,
        batch_size: int = None,
        learning_rate: float = None,
        train_days: int = 60,
        val_days: int = 7,
        test_days: int = 7,
        machine_type: str = 'n1-standard-4',
        experiment_name: str = '',
        experiment_description: str = '',
    ):
        """
        Submit a new Quick Test pipeline to Vertex AI.

        Args:
            feature_config: FeatureConfig instance
            model_config: ModelConfig instance
            user: User who initiated the test (optional)
            split_strategy: 'random', 'time_holdout', or 'strict_time'
            holdout_days: Days to exclude for time-based strategies
            date_column: Column name for temporal split
            data_sample_percent: Percentage of data to use
            epochs: Override ModelConfig epochs
            batch_size: Override ModelConfig batch_size
            learning_rate: Override ModelConfig learning_rate
            train_days: Number of days for training data (strict_time)
            val_days: Number of days for validation data (strict_time)
            test_days: Number of days for test data - held out (strict_time)
            machine_type: Compute machine type for Trainer and Dataflow workers

        Returns:
            QuickTest instance
        """
        from ml_platform.models import QuickTest
        from ml_platform.experiments.hyperparameter_analyzer import (
            get_l2_category, get_tower_structure, get_primary_activation,
            get_max_l2_reg, estimate_tower_params
        )

        # Create QuickTest record
        quick_test = QuickTest(
            feature_config=feature_config,
            model_config=model_config,
            created_by=user,
            split_strategy=split_strategy,
            holdout_days=holdout_days,
            date_column=date_column,
            data_sample_percent=data_sample_percent,
            epochs=epochs or model_config.epochs,
            batch_size=batch_size or model_config.batch_size,
            learning_rate=learning_rate or model_config.learning_rate,
            train_days=train_days,
            val_days=val_days,
            test_days=test_days,
            machine_type=machine_type,
            experiment_name=experiment_name,
            experiment_description=experiment_description,
            status=QuickTest.STATUS_SUBMITTING,
        )

        # Populate denormalized fields for hyperparameter analysis
        self._populate_denormalized_fields(quick_test, feature_config, model_config)

        # Assign sequential experiment number before saving
        quick_test.assign_experiment_number()
        quick_test.save()

        try:
            # Generate code and submit pipeline
            self._submit_pipeline(quick_test, feature_config, model_config)

            # Pipeline submitted to Cloud Build - keep status as SUBMITTING
            # Initialize stage_details with Compile stage running
            # Status will transition to RUNNING when Cloud Build completes
            # and Vertex AI job is created (handled by _check_cloud_build_result)
            quick_test.stage_details = [
                {'name': 'Compile', 'status': 'running', 'duration_seconds': None},
                {'name': 'Examples', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Stats', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Schema', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Transform', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Train', 'status': 'pending', 'duration_seconds': None},
            ]
            quick_test.current_stage = 'compile'
            quick_test.save(update_fields=['stage_details', 'current_stage'])

        except Exception as e:
            logger.exception(f"Error submitting quick test: {e}")
            quick_test.status = QuickTest.STATUS_FAILED
            quick_test.error_message = str(e)
            quick_test.save(update_fields=['status', 'error_message'])

        return quick_test

    def _populate_denormalized_fields(self, quick_test, feature_config, model_config):
        """
        Populate denormalized fields for hyperparameter analysis.

        These fields are copied/derived from ModelConfig, FeatureConfig, and Dataset
        at experiment creation time to enable fast querying without joins.

        Args:
            quick_test: QuickTest instance to populate
            feature_config: FeatureConfig instance
            model_config: ModelConfig instance
        """
        from ml_platform.experiments.hyperparameter_analyzer import (
            get_l2_category, get_tower_structure, get_primary_activation,
            get_max_l2_reg, estimate_tower_params
        )

        try:
            # From ModelConfig - Training params
            quick_test.optimizer = model_config.optimizer
            quick_test.output_embedding_dim = model_config.output_embedding_dim
            quick_test.retrieval_algorithm = model_config.retrieval_algorithm
            quick_test.top_k = model_config.top_k

            # From ModelConfig - Architecture (derived)
            buyer_layers = model_config.buyer_tower_layers or []
            product_layers = model_config.product_tower_layers or []

            quick_test.buyer_tower_structure = get_tower_structure(buyer_layers)
            quick_test.product_tower_structure = get_tower_structure(product_layers)
            quick_test.buyer_activation = get_primary_activation(buyer_layers)
            quick_test.product_activation = get_primary_activation(product_layers)

            # L2 regularization as category
            buyer_l2 = get_max_l2_reg(buyer_layers)
            product_l2 = get_max_l2_reg(product_layers)
            quick_test.buyer_l2_category = get_l2_category(buyer_l2)
            quick_test.product_l2_category = get_l2_category(product_l2)

            # From FeatureConfig
            quick_test.buyer_tensor_dim = feature_config.buyer_tensor_dim
            quick_test.product_tensor_dim = feature_config.product_tensor_dim

            buyer_features = feature_config.buyer_model_features or []
            product_features = feature_config.product_model_features or []
            buyer_crosses = feature_config.buyer_model_crosses or []
            product_crosses = feature_config.product_model_crosses or []

            quick_test.buyer_feature_count = len(buyer_features)
            quick_test.product_feature_count = len(product_features)
            quick_test.buyer_cross_count = len(buyer_crosses)
            quick_test.product_cross_count = len(product_crosses)

            # Extract feature details (name + dimension) for TPE analysis
            quick_test.buyer_feature_details = self._extract_feature_details(buyer_features)
            quick_test.product_feature_details = self._extract_feature_details(product_features)
            quick_test.buyer_cross_details = self._extract_cross_details(buyer_crosses)
            quick_test.product_cross_details = self._extract_cross_details(product_crosses)

            # Estimate tower params
            if feature_config.buyer_tensor_dim:
                quick_test.buyer_total_params = estimate_tower_params(
                    buyer_layers, feature_config.buyer_tensor_dim
                )
            if feature_config.product_tensor_dim:
                quick_test.product_total_params = estimate_tower_params(
                    product_layers, feature_config.product_tensor_dim
                )

            # From Dataset (via FeatureConfig)
            dataset = feature_config.dataset
            if dataset:
                # Row count - prefer row_count_estimate, fallback to summary_snapshot
                quick_test.dataset_row_count = dataset.row_count_estimate
                if not quick_test.dataset_row_count and dataset.summary_snapshot:
                    quick_test.dataset_row_count = dataset.summary_snapshot.get('total_rows')

                quick_test.dataset_unique_users = dataset.unique_users_estimate
                quick_test.dataset_unique_products = dataset.unique_products_estimate

                # Calculate date range days
                if dataset.date_range_start and dataset.date_range_end:
                    delta = dataset.date_range_end - dataset.date_range_start
                    quick_test.dataset_date_range_days = delta.days

                # Extract filter parameters from Dataset.filters
                self._populate_dataset_filter_fields(quick_test, dataset)

        except Exception as e:
            # Log but don't fail - these fields are for analysis only
            logger.warning(f"Error populating denormalized fields: {e}")

    def _extract_feature_details(self, features):
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

    def _extract_cross_details(self, crosses):
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

    def _populate_dataset_filter_fields(self, quick_test, dataset):
        """
        Extract filter descriptions from Dataset.filters and populate QuickTest fields.

        This enables TPE-based hyperparameter analysis for dataset filtering strategies.
        Each filter is converted to a human-readable description string.

        Args:
            quick_test: QuickTest instance to populate
            dataset: Dataset instance with filters JSONField
        """
        filters = dataset.filters or {}

        # Extract date filter descriptions
        quick_test.dataset_date_filters = self._extract_date_filter_descriptions(filters)

        # Extract customer filter descriptions
        quick_test.dataset_customer_filters = self._extract_customer_filter_descriptions(filters)

        # Extract product filter descriptions
        quick_test.dataset_product_filters = self._extract_product_filter_descriptions(filters)

    def _extract_date_filter_descriptions(self, filters):
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

    def _extract_customer_filter_descriptions(self, filters):
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
            column = cat_filter.get('column', '').split('.')[-1]  # Get column name without table prefix
            mode = cat_filter.get('mode', 'include')
            values = cat_filter.get('values', [])

            if column and values:
                values_str = ', '.join(str(v) for v in values[:3])  # Limit to 3 values
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

    def _extract_product_filter_descriptions(self, filters):
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

    def _submit_pipeline(self, quick_test, feature_config, model_config):
        """
        Internal method to generate code and submit pipeline.

        Args:
            quick_test: QuickTest instance
            feature_config: FeatureConfig instance
            model_config: ModelConfig instance
        """
        from ml_platform.configs.services import PreprocessingFnGenerator, TrainerModuleGenerator
        from ml_platform.datasets.services import BigQueryService

        # 0. Validate FeatureConfig column names match BigQuery output
        logger.info("Validating FeatureConfig column names against BigQuery output")
        self._validate_column_names(feature_config)

        # 1. Generate transform code from FeatureConfig
        logger.info(f"Generating transform code for FeatureConfig {feature_config.id}")
        transform_generator = PreprocessingFnGenerator(feature_config)
        transform_code = transform_generator.generate()

        # 2. Generate trainer code from FeatureConfig + ModelConfig
        logger.info(f"Generating trainer code for ModelConfig {model_config.id}")
        trainer_generator = TrainerModuleGenerator(feature_config, model_config)
        trainer_code, is_valid, error_msg, error_line = trainer_generator.generate_and_validate()

        if not is_valid:
            raise ExperimentServiceError(
                f"Generated trainer code has syntax error at line {error_line}: {error_msg}"
            )

        # 3. Generate SQL query with split/sampling
        logger.info("Generating BigQuery SQL with split strategy")
        dataset = feature_config.dataset
        bq_service = BigQueryService(self.model_endpoint, dataset)

        # For temporal strategies, generate separate queries for each split
        # This avoids the buggy partition_feature_name code path in TFX
        split_queries = None
        if quick_test.split_strategy in ('time_holdout', 'strict_time'):
            logger.info(f"Generating split-specific queries for {quick_test.split_strategy}")
            split_queries = bq_service.generate_split_queries(
                dataset=dataset,
                split_strategy=quick_test.split_strategy,
                holdout_days=quick_test.holdout_days,
                date_column=quick_test.date_column,
                sample_percent=quick_test.data_sample_percent,
                train_days=quick_test.train_days,
                val_days=quick_test.val_days,
                test_days=quick_test.test_days,
            )
            # Use train query as the main query (for logging/debugging)
            bigquery_query = split_queries['train']
            logger.info(f"Generated 3 split queries: train={len(split_queries['train'])} chars, "
                       f"eval={len(split_queries['eval'])} chars, test={len(split_queries['test'])} chars")
        else:
            # Random strategy: single query, TFX does hash-based splitting
            bigquery_query = bq_service.generate_training_query(
                dataset=dataset,
                split_strategy=quick_test.split_strategy,
                holdout_days=quick_test.holdout_days,
                date_column=quick_test.date_column,
                sample_percent=quick_test.data_sample_percent,
                train_days=quick_test.train_days,
                val_days=quick_test.val_days,
                test_days=quick_test.test_days,
            )

        # 4. Create unique paths for this run
        # Use hyphens (not underscores) - Vertex AI pipeline names require [a-z0-9-]
        run_id = f"qt-{quick_test.id}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        gcs_base_path = f"gs://{self.ARTIFACTS_BUCKET}/{run_id}"

        # 5. Upload code to GCS
        logger.info(f"Uploading code to GCS: {gcs_base_path}")
        transform_module_path = self._upload_to_gcs(
            content=transform_code,
            blob_path=f"{run_id}/transform_module.py"
        )
        trainer_module_path = self._upload_to_gcs(
            content=trainer_code,
            blob_path=f"{run_id}/trainer_module.py"
        )

        # Save GCS paths to quick_test
        quick_test.gcs_artifacts_path = gcs_base_path
        quick_test.save(update_fields=['gcs_artifacts_path'])

        # 6. Submit TFX pipeline to Vertex AI (async - triggers Cloud Build and returns immediately)
        logger.info("Triggering TFX pipeline compilation via Cloud Build")
        build_id = self._submit_vertex_pipeline(
            quick_test=quick_test,
            bigquery_query=bigquery_query,
            split_queries=split_queries,  # None for random, dict for temporal
            transform_module_path=transform_module_path,
            trainer_module_path=trainer_module_path,
            gcs_output_path=gcs_base_path,
            run_id=run_id,
            machine_type=quick_test.machine_type,
        )

        # Save Cloud Build info for async tracking
        # The Vertex AI job info will be populated by refresh_status() after Cloud Build completes
        quick_test.cloud_build_id = build_id
        quick_test.cloud_build_run_id = run_id
        quick_test.save(update_fields=['cloud_build_id', 'cloud_build_run_id'])

        logger.info(f"Cloud Build triggered: {build_id} (run_id: {run_id})")

    def _upload_to_gcs(self, content: str, blob_path: str) -> str:
        """
        Upload content to GCS.

        Args:
            content: String content to upload
            blob_path: Path within the artifacts bucket

        Returns:
            Full GCS path (gs://bucket/path)
        """
        bucket = self.storage_client.bucket(self.ARTIFACTS_BUCKET)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(content, content_type='text/plain')

        return f"gs://{self.ARTIFACTS_BUCKET}/{blob_path}"

    def _validate_column_names(self, feature_config):
        """
        Validate that FeatureConfig column names match the expected BigQuery output.

        This prevents runtime errors in the Transform stage where preprocessing_fn
        tries to access columns that don't exist in the TFRecords.

        The column names must match because:
        1. BigQuery query outputs columns with specific names (handles duplicates with table_alias_col)
        2. FeatureConfig's features reference columns by name
        3. Generated transform_module.py uses inputs[column_name]
        4. If there's a mismatch, Transform fails with KeyError

        Raises:
            ExperimentServiceError: If column names don't match
        """
        dataset = feature_config.dataset
        if not dataset:
            return  # Can't validate without dataset

        # Get column names from FeatureConfig features
        # IMPORTANT: Use display_name if present, falling back to column
        # This matches how PreprocessingFnGenerator uses column names:
        #   col = feature.get('display_name') or feature.get('column')
        # The display_name contains the aliased name that matches BigQuery output
        feature_columns = set()
        for feature in (feature_config.buyer_model_features or []):
            col = feature.get('display_name') or feature.get('column')
            if col:
                feature_columns.add(col)
        for feature in (feature_config.product_model_features or []):
            col = feature.get('display_name') or feature.get('column')
            if col:
                feature_columns.add(col)

        if not feature_columns:
            return  # No features to validate

        # Calculate expected BigQuery output column names
        # This mirrors the logic in BigQueryService.generate_query()
        # IMPORTANT: Must apply column_aliases since the SQL outputs aliased names
        selected_columns = dataset.selected_columns or {}
        column_aliases = dataset.column_aliases or {}
        seen_cols = set()
        expected_columns = set()

        for table, cols in selected_columns.items():
            table_alias = table.split('.')[-1]
            for col in cols:
                if col in seen_cols:
                    # Duplicate column - uses table_alias_col format
                    output_name = f"{table_alias}_{col}"
                else:
                    # First occurrence - uses raw column name
                    output_name = col
                    seen_cols.add(col)

                # Apply column aliases (same logic as generate_query in datasets/services.py)
                # The SQL outputs columns with aliased names via AS clause
                alias_key = f"{table_alias}_{col}"
                alias_key_dot = f"{table_alias}.{col}"
                final_name = (
                    column_aliases.get(alias_key) or
                    column_aliases.get(alias_key_dot) or
                    output_name
                )
                expected_columns.add(final_name)

        # Check if all FeatureConfig columns exist in BigQuery output
        missing_columns = feature_columns - expected_columns
        if missing_columns:
            # Provide helpful error message with suggestions
            suggestions = []
            for missing in missing_columns:
                # Check if this column was renamed via column_aliases (original name used instead of alias)
                # Look through all aliases to find if the missing column is an original name
                alias_match = None
                for alias_key, alias_value in column_aliases.items():
                    # alias_key format is "table_col" or "table.col", check if it ends with the missing column
                    if alias_key.endswith(f"_{missing}") or alias_key.endswith(f".{missing}"):
                        alias_match = alias_value
                        break

                if alias_match:
                    suggestions.append(f"  - '{missing}' -> try '{alias_match}' (column was renamed in Dataset)")
                # Check if this column exists with a table alias prefix
                elif any(c.endswith(f"_{missing}") for c in expected_columns):
                    aliased_versions = [c for c in expected_columns if c.endswith(f"_{missing}")]
                    suggestions.append(f"  - '{missing}' -> try '{aliased_versions[0]}' (column exists in multiple tables)")
                else:
                    # Check for case-insensitive match
                    case_matches = [c for c in expected_columns if c.lower() == missing.lower()]
                    if case_matches:
                        suggestions.append(f"  - '{missing}' -> try '{case_matches[0]}' (case mismatch)")

            error_msg = (
                f"FeatureConfig column names don't match BigQuery output.\n"
                f"Missing columns: {sorted(missing_columns)}\n"
                f"Available columns: {sorted(expected_columns)}"
            )
            if suggestions:
                error_msg += f"\n\nSuggestions:\n" + "\n".join(suggestions)
            error_msg += (
                f"\n\nThis usually happens when:\n"
                f"1. A column name appears in multiple tables (gets prefixed with table name)\n"
                f"2. The FeatureConfig was created before changes to the Dataset\n"
                f"3. Column names were renamed in the Dataset but FeatureConfig uses old names\n"
                f"\nPlease update the FeatureConfig to use the correct column names."
            )

            raise ExperimentServiceError(error_msg)

        logger.info(f"Column validation passed: {len(feature_columns)} columns verified")

    def _submit_vertex_pipeline(
        self,
        quick_test,
        bigquery_query: str,
        split_queries: dict,
        transform_module_path: str,
        trainer_module_path: str,
        gcs_output_path: str,
        run_id: str,
        machine_type: str = 'n1-standard-4',
    ):
        """
        Submit the TFX pipeline to Vertex AI via Cloud Build (async).

        Cloud Build is used to compile the TFX pipeline (requires Python 3.10)
        and submit it to Vertex AI. This method returns immediately after
        triggering Cloud Build - the result will be polled by refresh_status().

        Args:
            quick_test: QuickTest instance
            bigquery_query: SQL query for data extraction (for random split)
            split_queries: Dict with train/eval/test queries (for temporal splits), or None
            transform_module_path: GCS path to transform_module.py
            trainer_module_path: GCS path to trainer_module.py
            gcs_output_path: GCS path for output artifacts
            run_id: Unique identifier for this run
            machine_type: Compute machine type for Trainer and Dataflow workers

        Returns:
            build_id: Cloud Build ID for tracking
        """
        logger.info(f"Triggering Cloud Build for TFX pipeline compilation: {run_id}")

        # Trigger Cloud Build
        build_id = self._trigger_cloud_build(
            run_id=run_id,
            bigquery_query=bigquery_query,
            split_queries=split_queries,
            transform_module_path=transform_module_path,
            trainer_module_path=trainer_module_path,
            output_path=gcs_output_path,
            epochs=quick_test.epochs,
            batch_size=quick_test.batch_size,
            learning_rate=quick_test.learning_rate,
            split_strategy=quick_test.split_strategy,
            machine_type=machine_type,
        )

        logger.info(f"Cloud Build triggered: {build_id} - returning immediately (async)")

        # Return immediately - don't wait for Cloud Build to complete
        # The refresh_status() method will poll for completion
        return build_id

    def _trigger_cloud_build(
        self,
        run_id: str,
        bigquery_query: str,
        split_queries: dict,
        transform_module_path: str,
        trainer_module_path: str,
        output_path: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        split_strategy: str = 'random',
        machine_type: str = 'n1-standard-4',
    ) -> str:
        """
        Trigger Cloud Build to compile and submit TFX pipeline.

        Args:
            run_id: Unique run identifier
            bigquery_query: BigQuery SQL query (for random split)
            split_queries: Dict with train/eval/test queries (for temporal splits), or None
            transform_module_path: GCS path to transform module
            trainer_module_path: GCS path to trainer module
            output_path: GCS path for outputs
            epochs: Training epochs
            batch_size: Batch size
            learning_rate: Learning rate
            split_strategy: Split strategy ('random', 'time_holdout', 'strict_time')
            machine_type: Compute machine type for Trainer and Dataflow workers

        Returns:
            Cloud Build build ID
        """
        import base64
        from google.cloud.devtools import cloudbuild_v1

        client = cloudbuild_v1.CloudBuildClient()

        import json

        # Base64 encode queries to avoid shell escaping issues
        query_b64 = base64.b64encode(bigquery_query.encode()).decode()

        bucket = self.storage_client.bucket(self.STAGING_BUCKET)

        # Upload the compile script to GCS (avoid Cloud Build arg length limit)
        script_path = f"build_scripts/{run_id}/compile_and_submit.py"
        blob = bucket.blob(script_path)
        blob.upload_from_string(self._get_compile_script(), content_type='text/plain')
        script_gcs_path = f"gs://{self.STAGING_BUCKET}/{script_path}"
        logger.info(f"Uploaded compile script to {script_gcs_path}")

        # For temporal strategies, upload split queries to GCS as JSON (too large for CLI args)
        split_queries_blob_path = ""
        if split_queries:
            split_queries_blob_path = f"build_scripts/{run_id}/split_queries.json"
            split_blob = bucket.blob(split_queries_blob_path)
            split_blob.upload_from_string(json.dumps(split_queries), content_type='application/json')
            logger.info(f"Uploaded split queries to gs://{self.STAGING_BUCKET}/{split_queries_blob_path}")

        # Build configuration - downloads script from GCS using Python (gsutil not available in python:3.10)
        # Parse bucket and blob path from script_gcs_path
        script_bucket = self.STAGING_BUCKET
        script_blob = script_path

        # Use pre-built TFX compiler image for fast compilation (1-2 min vs 12-15 min)
        # The image is hosted in the central platform project and contains all TFX dependencies
        tfx_compiler_image = getattr(
            settings, 'TFX_COMPILER_IMAGE',
            'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest'
        )
        logger.info(f"Using TFX compiler image: {tfx_compiler_image}")

        # Build command with optional split queries GCS path
        split_args = ""
        if split_queries_blob_path:
            split_args = f'    --split-queries-gcs-path="{split_queries_blob_path}" \\\n'

        build = cloudbuild_v1.Build(
            steps=[
                cloudbuild_v1.BuildStep(
                    name=tfx_compiler_image,
                    entrypoint='bash',
                    args=[
                        '-c',
                        f'''
set -e
echo "TFX Compiler Image - dependencies pre-installed"
python -c "import tfx; print(f'TFX version: {{tfx.__version__}}')"
python -c "from google.cloud import storage; storage.Client().bucket('{script_bucket}').blob('{script_blob}').download_to_filename('/tmp/compile_and_submit.py')"
python /tmp/compile_and_submit.py \\
    --run-id="{run_id}" \\
    --staging-bucket="{self.STAGING_BUCKET}" \\
    --bigquery-query-b64="{query_b64}" \\
{split_args}    --transform-module-path="{transform_module_path}" \\
    --trainer-module-path="{trainer_module_path}" \\
    --output-path="{output_path}" \\
    --epochs="{epochs}" \\
    --batch-size="{batch_size}" \\
    --learning-rate="{learning_rate}" \\
    --split-strategy="{split_strategy}" \\
    --machine-type="{machine_type}" \\
    --project-id="{self.project_id}" \\
    --region="{self.REGION}"
'''
                    ],
                )
            ],
            timeout={'seconds': 600},  # Reduced from 1800s - pre-built image is much faster
            options=cloudbuild_v1.BuildOptions(
                logging=cloudbuild_v1.BuildOptions.LoggingMode.CLOUD_LOGGING_ONLY,
                machine_type=cloudbuild_v1.BuildOptions.MachineType.E2_HIGHCPU_8,
            ),
        )

        # Trigger build
        operation = client.create_build(project_id=self.project_id, build=build)

        # Get build ID from operation metadata
        build_id = operation.metadata.build.id
        logger.info(f"Cloud Build started: {build_id}")

        return build_id

    def _get_compile_script(self) -> str:
        """Return the TFX compile and submit script content."""
        return '''
import argparse
import json
import logging
import os
import tempfile
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_tfx_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    bigquery_query: str,
    split_queries: Optional[dict],
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    project_id: str,
    region: str = 'europe-central2',
    epochs: int = 10,
    batch_size: int = 4096,
    learning_rate: float = 0.001,
    split_strategy: str = 'random',
    machine_type: str = 'n1-standard-4',
    train_steps: Optional[int] = None,
    eval_steps: Optional[int] = None,
):
    from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
    from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer
    from tfx.proto import example_gen_pb2, trainer_pb2, transform_pb2
    from tfx.orchestration import pipeline as tfx_pipeline

    logger.info(f"Creating TFX pipeline: {pipeline_name}, split_strategy={split_strategy}")

    # Configure split based on strategy
    # - 'random': Hash-based 80/15/5 split (train/eval/test) - single query
    # - 'time_holdout'/'strict_time': Multiple queries via input_config (avoids buggy partition_feature_name)
    if split_strategy == 'random':
        # Random: hash-based 80/15/5 split with single query
        logger.info("Using hash-based 80/15/5 split (train/eval/test)")
        output_config = example_gen_pb2.Output(
            split_config=example_gen_pb2.SplitConfig(
                splits=[
                    example_gen_pb2.SplitConfig.Split(name="train", hash_buckets=16),
                    example_gen_pb2.SplitConfig.Split(name="eval", hash_buckets=3),
                    example_gen_pb2.SplitConfig.Split(name="test", hash_buckets=1),
                ]
            )
        )
        # Configure BigQueryExampleGen with single query
        logger.info(f"BigQueryExampleGen configured with single query, project={project_id}")
        example_gen = BigQueryExampleGen(
            query=bigquery_query,
            output_config=output_config,
            custom_config={'project': project_id}
        )
    else:
        # time_holdout and strict_time: Use multiple input splits (one query per split)
        # This avoids the buggy partition_feature_name code path in TFX
        if not split_queries:
            raise ValueError(f"split_queries required for split_strategy={split_strategy}")

        logger.info(f"Using multiple input splits for {split_strategy} (avoids partition_feature_name bug)")
        input_config = example_gen_pb2.Input(splits=[
            example_gen_pb2.Input.Split(name='train', pattern=split_queries['train']),
            example_gen_pb2.Input.Split(name='eval', pattern=split_queries['eval']),
            example_gen_pb2.Input.Split(name='test', pattern=split_queries['test']),
        ])
        # Configure BigQueryExampleGen with multiple input splits
        # Pass empty output_config to avoid TFX calling make_default_output_config()
        # which has protobuf 5.x compatibility issues (deprecated 'including_default_value_fields')
        logger.info(f"BigQueryExampleGen configured with 3 input splits, project={project_id}")
        example_gen = BigQueryExampleGen(
            input_config=input_config,
            output_config=example_gen_pb2.Output(),
            custom_config={'project': project_id}
        )
    statistics_gen = StatisticsGen(examples=example_gen.outputs["examples"])
    schema_gen = SchemaGen(statistics=statistics_gen.outputs["statistics"])
    # IMPORTANT: Configure splits_config correctly to avoid data leakage:
    # - analyze=['train', 'eval']: Build vocabularies ONLY from data model sees during training
    # - transform=['train', 'eval', 'test']: Create TFRecords for all splits including test
    # Test-only IDs will correctly map to OOV embedding (honest evaluation)
    transform = Transform(
        examples=example_gen.outputs["examples"],
        schema=schema_gen.outputs["schema"],
        module_file=transform_module_path,
        splits_config=transform_pb2.SplitsConfig(
            analyze=['train', 'eval'],  # NO test - avoid data leakage
            transform=['train', 'eval', 'test']  # But transform all for evaluation
        ),
    )

    train_args = trainer_pb2.TrainArgs(num_steps=train_steps)
    eval_args = trainer_pb2.EvalArgs(num_steps=eval_steps)

    custom_config = {
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "gcs_output_path": output_path,  # For MetricsCollector to save training_metrics.json
    }

    trainer = Trainer(
        module_file=trainer_module_path,
        examples=transform.outputs["transformed_examples"],
        transform_graph=transform.outputs["transform_graph"],
        schema=schema_gen.outputs["schema"],
        train_args=train_args,
        eval_args=eval_args,
        custom_config=custom_config,
    )

    components = [example_gen, statistics_gen, schema_gen, transform, trainer]

    # Configure Dataflow for StatisticsGen and Transform components
    # This ensures scalable processing for large datasets
    staging_bucket = f'{project_id}-pipeline-staging'
    beam_pipeline_args = [
        '--runner=DataflowRunner',
        f'--project={project_id}',
        f'--region={region}',
        f'--zone={region}-b',  # Explicitly set zone to avoid exhausted zones (a and c are exhausted)
        f'--temp_location=gs://{staging_bucket}/dataflow_temp',
        f'--staging_location=gs://{staging_bucket}/dataflow_staging',
        f'--machine_type={machine_type}',
        '--disk_size_gb=50',
        '--experiments=use_runner_v2',
        '--max_num_workers=10',
        '--autoscaling_algorithm=THROUGHPUT_BASED',
    ]
    logger.info(f"Dataflow configured with machine_type={machine_type}, region={region}")

    pipeline = tfx_pipeline.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=components,
        enable_cache=False,
        beam_pipeline_args=beam_pipeline_args,
    )
    logger.info(f"TFX pipeline created with {len(components)} components using DataflowRunner")
    return pipeline


def compile_pipeline(pipeline, output_file: str, project_id: str = 'b2b-recs') -> str:
    from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner
    logger.info(f"Compiling pipeline to: {output_file}")

    # Use custom TFX image with tensorflow-recommenders pre-installed
    # This image extends gcr.io/tfx-oss-public/tfx:1.15.0 with TFRS
    custom_image = f'europe-central2-docker.pkg.dev/{project_id}/tfx-builder/tfx-trainer:latest'
    logger.info(f"Using custom TFX image: {custom_image}")

    runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
        config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(
            default_image=custom_image
        ),
        output_filename=output_file
    )
    runner.run(pipeline)
    logger.info("Pipeline compiled successfully")
    return output_file


def submit_to_vertex_ai(template_path: str, display_name: str, project_id: str, region: str) -> str:
    from google.cloud import aiplatform
    logger.info(f"Initializing Vertex AI: project={project_id}, region={region}")
    aiplatform.init(project=project_id, location=region)
    logger.info(f"Creating pipeline job: {display_name}")
    pipeline_job = aiplatform.PipelineJob(
        display_name=display_name[:128],
        template_path=template_path,
        enable_caching=False,
    )
    logger.info("Submitting pipeline job to Vertex AI...")
    pipeline_job.submit()
    resource_name = pipeline_job.resource_name
    logger.info(f"Pipeline submitted: {resource_name}")
    return resource_name


def write_result_to_gcs(bucket_name: str, blob_path: str, result: dict):
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    content = json.dumps(result, indent=2)
    blob.upload_from_string(content, content_type="application/json")
    logger.info(f"Result written to gs://{bucket_name}/{blob_path}")


def main():
    import base64
    parser = argparse.ArgumentParser(description="Compile and submit TFX pipeline")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--staging-bucket", required=True)
    parser.add_argument("--bigquery-query-b64", required=True, help="Base64 encoded BigQuery SQL")
    parser.add_argument("--split-queries-gcs-path", default="", help="GCS blob path to split_queries.json (temporal strategies)")
    parser.add_argument("--transform-module-path", required=True)
    parser.add_argument("--trainer-module-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--split-strategy", default="random", help="Split strategy: random, time_holdout, strict_time")
    parser.add_argument("--machine-type", default="n1-standard-4", help="Machine type for Trainer and Dataflow workers")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", default="europe-central2")
    args = parser.parse_args()

    # Decode the base64 query
    bigquery_query = base64.b64decode(args.bigquery_query_b64).decode("utf-8")
    logger.info(f"Decoded BigQuery query: {bigquery_query[:100]}...")

    # Download split queries from GCS for temporal strategies
    split_queries = None
    if args.split_queries_gcs_path:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(args.staging_bucket)
        blob = bucket.blob(args.split_queries_gcs_path)
        split_queries = json.loads(blob.download_as_text())
        logger.info(f"Downloaded split queries from gs://{args.staging_bucket}/{args.split_queries_gcs_path}: "
                   f"train={len(split_queries['train'])} chars, "
                   f"eval={len(split_queries['eval'])} chars, test={len(split_queries['test'])} chars")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_file = os.path.join(temp_dir, f"pipeline_{args.run_id}.json")
            pipeline = create_tfx_pipeline(
                pipeline_name=f"quicktest-{args.run_id}",
                pipeline_root=f"gs://{args.staging_bucket}/pipeline_root/{args.run_id}",
                bigquery_query=bigquery_query,
                split_queries=split_queries,
                transform_module_path=args.transform_module_path,
                trainer_module_path=args.trainer_module_path,
                output_path=args.output_path,
                project_id=args.project_id,
                region=args.region,
                epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.learning_rate,
                split_strategy=args.split_strategy,
                machine_type=args.machine_type,
            )
            compile_pipeline(pipeline, pipeline_file, project_id=args.project_id)
            display_name = f"quicktest-{args.run_id}"
            resource_name = submit_to_vertex_ai(pipeline_file, display_name, args.project_id, args.region)
            result = {"success": True, "run_id": args.run_id, "vertex_pipeline_job_name": resource_name, "display_name": display_name}
            write_result_to_gcs(args.staging_bucket, f"build_results/{args.run_id}.json", result)
            logger.info("Pipeline compilation and submission completed successfully")
            print(f"PIPELINE_JOB_NAME={resource_name}")
    except Exception as e:
        logger.error(f"Pipeline compilation/submission failed: {e}")
        error_result = {"success": False, "run_id": args.run_id, "error": str(e)}
        try:
            write_result_to_gcs(args.staging_bucket, f"build_results/{args.run_id}.json", error_result)
        except Exception as gcs_error:
            logger.error(f"Failed to write error to GCS: {gcs_error}")
        raise


if __name__ == "__main__":
    main()
'''

    def _wait_for_build_result(self, run_id: str, timeout_seconds: int = 1800) -> dict:
        """
        Wait for Cloud Build to complete and read result from GCS.

        The compile_and_submit.py script writes result to:
        gs://{STAGING_BUCKET}/build_results/{run_id}.json

        Args:
            run_id: Unique run identifier
            timeout_seconds: Maximum time to wait

        Returns:
            Result dictionary with success, vertex_pipeline_job_name, or error
        """
        import time

        result_blob_path = f"build_results/{run_id}.json"
        bucket = self.storage_client.bucket(self.STAGING_BUCKET)
        blob = bucket.blob(result_blob_path)

        start_time = time.time()
        poll_interval = 10  # seconds

        logger.info(f"Waiting for build result: gs://{self.STAGING_BUCKET}/{result_blob_path}")

        while (time.time() - start_time) < timeout_seconds:
            if blob.exists():
                content = blob.download_as_string().decode('utf-8')
                result = json.loads(content)
                logger.info(f"Build result received: {result}")
                return result

            time.sleep(poll_interval)

        # Timeout
        return {
            'success': False,
            'error': f'Build timeout after {timeout_seconds} seconds'
        }

    def refresh_status(self, quick_test) -> 'QuickTest':
        """
        Refresh the status of a QuickTest from Cloud Build and/or Vertex AI.

        This handles two phases:
        1. Cloud Build phase (compilation): Check if Cloud Build completed and
           read the Vertex AI job name from GCS
        2. Vertex AI phase (pipeline execution): Check pipeline status and
           update stage details

        Args:
            quick_test: QuickTest instance

        Returns:
            Updated QuickTest instance
        """
        logger.info(f"{quick_test.display_name} (id={quick_test.id}): Refreshing status (current: {quick_test.status})")

        # Phase 1: If no Vertex AI job yet, check Cloud Build status
        if not quick_test.vertex_pipeline_job_name:
            logger.info(f"{quick_test.display_name} (id={quick_test.id}): No Vertex AI job yet, checking Cloud Build")
            if quick_test.cloud_build_run_id:
                self._check_cloud_build_result(quick_test)
            else:
                logger.warning(f"{quick_test.display_name} (id={quick_test.id}): No cloud_build_run_id, cannot check Cloud Build")
            # If still no vertex_pipeline_job_name after checking, return
            if not quick_test.vertex_pipeline_job_name:
                logger.info(f"{quick_test.display_name} (id={quick_test.id}): Still no Vertex AI job, Cloud Build may still be running")
                return quick_test

        logger.info(f"{quick_test.display_name} (id={quick_test.id}): Checking Vertex AI pipeline {quick_test.vertex_pipeline_job_id}")

        # Phase 2: Check Vertex AI pipeline status
        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            # Get pipeline job status
            pipeline_job = aiplatform.PipelineJob.get(
                quick_test.vertex_pipeline_job_name
            )

            state = pipeline_job.state.name

            # Map Vertex AI states to QuickTest states
            state_mapping = {
                'PIPELINE_STATE_PENDING': quick_test.STATUS_RUNNING,  # Pipeline submitted, waiting to start
                'PIPELINE_STATE_RUNNING': quick_test.STATUS_RUNNING,
                'PIPELINE_STATE_SUCCEEDED': quick_test.STATUS_COMPLETED,
                'PIPELINE_STATE_FAILED': quick_test.STATUS_FAILED,
                'PIPELINE_STATE_CANCELLED': quick_test.STATUS_CANCELLED,
                'PIPELINE_STATE_CANCELLING': quick_test.STATUS_RUNNING,
            }

            new_status = state_mapping.get(state, quick_test.status)

            if new_status != quick_test.status:
                logger.info(f"{quick_test.display_name} (id={quick_test.id}): Status changing from {quick_test.status} to {new_status}")
                quick_test.status = new_status

                if new_status == quick_test.STATUS_COMPLETED:
                    quick_test.completed_at = timezone.now()
                    logger.info(f"{quick_test.display_name} (id={quick_test.id}): Pipeline completed, extracting results")
                    # Extract results from GCS
                    self._extract_results(quick_test)
                    # Cache training history from MLflow for fast loading
                    self._cache_training_history(quick_test)

                elif new_status == quick_test.STATUS_FAILED:
                    quick_test.completed_at = timezone.now()
                    # Try to extract error message
                    if hasattr(pipeline_job, 'error') and pipeline_job.error:
                        quick_test.error_message = str(pipeline_job.error)
                    logger.warning(f"{quick_test.display_name} (id={quick_test.id}): Pipeline failed: {quick_test.error_message}")

                quick_test.save()

            # Update progress from pipeline tasks
            self._update_progress(quick_test, pipeline_job)

        except Exception as e:
            logger.exception(f"Error refreshing status for {quick_test.display_name} (id={quick_test.id}): {e}")

        return quick_test

    def _check_cloud_build_result(self, quick_test):
        """
        Check if Cloud Build has completed and read the result from GCS.

        The compile_and_submit.py script writes result to:
        gs://{STAGING_BUCKET}/build_results/{run_id}.json

        If Cloud Build completed successfully, this populates:
        - vertex_pipeline_job_name
        - vertex_pipeline_job_id
        - status -> STATUS_RUNNING
        - started_at

        If Cloud Build failed, this sets:
        - status -> STATUS_FAILED
        - error_message

        Args:
            quick_test: QuickTest instance
        """
        run_id = quick_test.cloud_build_run_id
        if not run_id:
            return

        result_blob_path = f"build_results/{run_id}.json"
        bucket = self.storage_client.bucket(self.STAGING_BUCKET)
        blob = bucket.blob(result_blob_path)

        try:
            if not blob.exists():
                # Cloud Build still running - no result yet
                logger.debug(f"Cloud Build result not ready yet: {result_blob_path}")
                return

            # Read result
            content = blob.download_as_string().decode('utf-8')
            result = json.loads(content)
            logger.info(f"Cloud Build result for {run_id}: {result}")

            if result.get('success'):
                # Cloud Build succeeded - pipeline was submitted to Vertex AI
                quick_test.vertex_pipeline_job_name = result['vertex_pipeline_job_name']
                quick_test.vertex_pipeline_job_id = result['vertex_pipeline_job_name'].split('/')[-1]
                quick_test.status = quick_test.STATUS_RUNNING
                quick_test.started_at = timezone.now()

                # Update stage_details: Compile completed, Examples starting
                quick_test.stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None},
                    {'name': 'Examples', 'status': 'running', 'duration_seconds': None},
                    {'name': 'Stats', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Schema', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Transform', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Train', 'status': 'pending', 'duration_seconds': None},
                ]
                quick_test.current_stage = 'examples'
                quick_test.progress_percent = 17  # ~1/6 stages complete

                quick_test.save(update_fields=[
                    'vertex_pipeline_job_name',
                    'vertex_pipeline_job_id',
                    'status',
                    'started_at',
                    'stage_details',
                    'current_stage',
                    'progress_percent'
                ])
                logger.info(f"{quick_test.display_name} (id={quick_test.id}) pipeline submitted: {quick_test.vertex_pipeline_job_id}")
            else:
                # Cloud Build failed
                quick_test.status = quick_test.STATUS_FAILED
                quick_test.error_message = result.get('error', 'Cloud Build failed')
                quick_test.completed_at = timezone.now()

                # Update stage_details: Compile failed
                quick_test.stage_details = [
                    {'name': 'Compile', 'status': 'failed', 'duration_seconds': None},
                    {'name': 'Examples', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Stats', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Schema', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Transform', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Train', 'status': 'pending', 'duration_seconds': None},
                ]
                quick_test.current_stage = 'failed'

                quick_test.save(update_fields=[
                    'status',
                    'error_message',
                    'completed_at',
                    'stage_details',
                    'current_stage'
                ])
                logger.warning(f"{quick_test.display_name} (id={quick_test.id}) Cloud Build failed: {quick_test.error_message}")

        except Exception as e:
            logger.warning(f"Error checking Cloud Build result for {quick_test.display_name} (id={quick_test.id}): {e}")

    def _extract_results(self, quick_test):
        """
        Extract results and metrics from GCS after pipeline completion.

        Args:
            quick_test: QuickTest instance
        """
        if not quick_test.gcs_artifacts_path:
            return

        try:
            # Read training_metrics.json from output path
            metrics_path = f"{quick_test.gcs_artifacts_path}/training_metrics.json"
            blob_path = metrics_path.replace(f"gs://{self.ARTIFACTS_BUCKET}/", "")

            bucket = self.storage_client.bucket(self.ARTIFACTS_BUCKET)
            blob = bucket.blob(blob_path)

            if blob.exists():
                metrics_content = blob.download_as_string().decode('utf-8')
                training_metrics = json.loads(metrics_content)

                # Extract final_metrics from the training metrics JSON
                final_metrics = training_metrics.get('final_metrics', {})

                # Map metrics to QuickTest model fields
                update_fields = []

                # Extract loss
                if 'test_loss' in final_metrics:
                    quick_test.loss = final_metrics['test_loss']
                    update_fields.append('loss')
                elif 'final_loss' in final_metrics:
                    quick_test.loss = final_metrics['final_loss']
                    update_fields.append('loss')

                # Extract recall metrics
                if 'test_recall_at_5' in final_metrics:
                    quick_test.recall_at_5 = final_metrics['test_recall_at_5']
                    update_fields.append('recall_at_5')

                if 'test_recall_at_10' in final_metrics:
                    quick_test.recall_at_10 = final_metrics['test_recall_at_10']
                    update_fields.append('recall_at_10')

                if 'test_recall_at_50' in final_metrics:
                    quick_test.recall_at_50 = final_metrics['test_recall_at_50']
                    update_fields.append('recall_at_50')

                if 'test_recall_at_100' in final_metrics:
                    quick_test.recall_at_100 = final_metrics['test_recall_at_100']
                    update_fields.append('recall_at_100')

                if update_fields:
                    quick_test.save(update_fields=update_fields)

                logger.info(f"Extracted results for {quick_test.display_name} (id={quick_test.id}): {list(final_metrics.keys())}")

        except Exception as e:
            logger.warning(f"Error extracting results for {quick_test.display_name} (id={quick_test.id}): {e}")

        # Extract MLflow run ID from mlflow_info.json
        try:
            mlflow_info_path = f"{quick_test.gcs_artifacts_path}/mlflow_info.json"
            mlflow_blob_path = mlflow_info_path.replace(f"gs://{self.ARTIFACTS_BUCKET}/", "")

            mlflow_blob = bucket.blob(mlflow_blob_path)

            if mlflow_blob.exists():
                mlflow_content = mlflow_blob.download_as_string().decode('utf-8')
                mlflow_info = json.loads(mlflow_content)

                mlflow_update_fields = []

                if 'run_id' in mlflow_info:
                    quick_test.mlflow_run_id = mlflow_info['run_id']
                    mlflow_update_fields.append('mlflow_run_id')

                if 'experiment_name' in mlflow_info:
                    quick_test.mlflow_experiment_name = mlflow_info['experiment_name']
                    mlflow_update_fields.append('mlflow_experiment_name')

                if mlflow_update_fields:
                    quick_test.save(update_fields=mlflow_update_fields)

                logger.info(f"Extracted MLflow info for {quick_test.display_name} (id={quick_test.id}): run_id={mlflow_info.get('run_id')}")
            else:
                logger.info(f"No mlflow_info.json found for {quick_test.display_name} (id={quick_test.id})")

        except Exception as e:
            logger.warning(f"Error extracting MLflow info for {quick_test.display_name} (id={quick_test.id}): {e}")

    def _cache_training_history(self, quick_test):
        """
        Cache training history from MLflow into Django DB for fast loading.

        This is called after training completion. Caching happens asynchronously
        and errors are logged but don't fail the completion process.

        Args:
            quick_test: QuickTest instance with mlflow_run_id set
        """
        if not quick_test.mlflow_run_id:
            logger.info(
                f"{quick_test.display_name} (id={quick_test.id}): "
                f"Skipping training history cache - no MLflow run ID"
            )
            return

        try:
            from .training_cache_service import TrainingCacheService

            cache_service = TrainingCacheService()
            success = cache_service.cache_training_history(quick_test)

            if success:
                logger.info(
                    f"{quick_test.display_name} (id={quick_test.id}): "
                    f"Training history cached successfully"
                )
            else:
                logger.warning(
                    f"{quick_test.display_name} (id={quick_test.id}): "
                    f"Training history caching failed (non-fatal)"
                )

        except Exception as e:
            # Don't fail completion if caching fails - it can be retried later
            logger.exception(
                f"{quick_test.display_name} (id={quick_test.id}): "
                f"Error caching training history (non-fatal): {e}"
            )

    # Mapping from TFX component names to short display names
    STAGE_NAME_MAP = {
        'bigqueryexamplegen': 'Examples',
        'statisticsgen': 'Stats',
        'schemagen': 'Schema',
        'transform': 'Transform',
        'trainer': 'Train',
    }

    # Order of stages for display
    STAGE_ORDER = ['Compile', 'Examples', 'Stats', 'Schema', 'Transform', 'Train']

    def _update_progress(self, quick_test, pipeline_job):
        """
        Update progress and stage details from Vertex AI pipeline tasks.

        Queries the pipeline job's task_details to get per-component status,
        maps TFX component names to short display names, and builds the
        stage_details structure for the UI.

        Args:
            quick_test: QuickTest instance
            pipeline_job: Vertex AI PipelineJob instance
        """
        try:
            pipeline_state = pipeline_job.state.name
            logger.info(f"{quick_test.display_name} (id={quick_test.id}): Pipeline state is {pipeline_state}")

            # Handle terminal pipeline states first (most reliable)
            if pipeline_state == 'PIPELINE_STATE_SUCCEEDED':
                # Pipeline completed successfully - mark all stages as completed
                stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None},
                    {'name': 'Examples', 'status': 'completed', 'duration_seconds': None},
                    {'name': 'Stats', 'status': 'completed', 'duration_seconds': None},
                    {'name': 'Schema', 'status': 'completed', 'duration_seconds': None},
                    {'name': 'Transform', 'status': 'completed', 'duration_seconds': None},
                    {'name': 'Train', 'status': 'completed', 'duration_seconds': None},
                ]
                current_stage = 'completed'
                progress_percent = 100
                logger.info(f"{quick_test.display_name} (id={quick_test.id}): Pipeline SUCCEEDED, marking all stages complete")

            elif pipeline_state in ('PIPELINE_STATE_FAILED', 'PIPELINE_STATE_CANCELLED'):
                # Pipeline failed or cancelled - try to get task details to find which stage failed
                task_statuses = self._get_task_statuses(pipeline_job)

                stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None}
                ]

                # Build stage details from task statuses or use defaults
                failed_stage_found = False
                for stage_name in self.STAGE_ORDER[1:]:  # Skip 'Compile'
                    task_info = task_statuses.get(stage_name, {})
                    status = task_info.get('status', 'pending')
                    duration = task_info.get('duration_seconds')

                    # If we've already found a failed stage, mark rest as pending
                    if failed_stage_found:
                        status = 'pending'
                        duration = None
                    elif status == 'failed':
                        failed_stage_found = True

                    stage_details.append({
                        'name': stage_name,
                        'status': status,
                        'duration_seconds': duration
                    })

                # If no specific failed stage found, mark the first pending/running as failed
                if not failed_stage_found:
                    for stage in stage_details:
                        if stage['name'] != 'Compile' and stage['status'] in ('pending', 'running'):
                            stage['status'] = 'failed'
                            break

                current_stage = 'failed' if 'FAILED' in pipeline_state else 'cancelled'
                completed_count = sum(1 for s in stage_details if s['status'] == 'completed')
                progress_percent = int((completed_count / len(stage_details)) * 100)
                logger.info(f"{quick_test.display_name} (id={quick_test.id}): Pipeline {pipeline_state}")

            else:
                # Pipeline is still running - get detailed task status
                task_statuses = self._get_task_statuses(pipeline_job)

                # Initialize stage details with Compile already completed
                stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None}
                ]

                # Initialize remaining stages from task statuses or as pending
                for stage_name in self.STAGE_ORDER[1:]:  # Skip 'Compile'
                    task_info = task_statuses.get(stage_name, {})
                    stage_details.append({
                        'name': stage_name,
                        'status': task_info.get('status', 'pending'),
                        'duration_seconds': task_info.get('duration_seconds')
                    })

                # Log task statuses for debugging
                if task_statuses:
                    logger.info(f"{quick_test.display_name} (id={quick_test.id}): Task statuses: {task_statuses}")
                else:
                    logger.warning(f"{quick_test.display_name} (id={quick_test.id}): No task statuses available from Vertex AI")

                # Determine current stage (first non-completed stage)
                current_stage = 'completed'
                for stage in stage_details:
                    if stage['status'] == 'running':
                        current_stage = stage['name'].lower()
                        break
                    elif stage['status'] == 'pending':
                        current_stage = stage['name'].lower()
                        break
                    elif stage['status'] == 'failed':
                        current_stage = 'failed'
                        break

                # Calculate progress
                completed_count = sum(1 for s in stage_details if s['status'] == 'completed')
                progress_percent = int((completed_count / len(stage_details)) * 100)

            # Update QuickTest
            quick_test.stage_details = stage_details
            quick_test.current_stage = current_stage
            quick_test.progress_percent = progress_percent
            quick_test.save(update_fields=['stage_details', 'current_stage', 'progress_percent'])

            logger.info(f"{quick_test.display_name} (id={quick_test.id}): Updated progress - stage={current_stage}, progress={progress_percent}%")

        except Exception as e:
            logger.exception(f"Error updating progress for {quick_test.display_name} (id={quick_test.id}): {e}")

    def _get_task_statuses(self, pipeline_job) -> dict:
        """
        Extract task statuses from Vertex AI pipeline job.

        Args:
            pipeline_job: Vertex AI PipelineJob instance

        Returns:
            Dict mapping short stage names to status info:
            {
                'Examples': {'status': 'completed', 'duration_seconds': 120},
                'Stats': {'status': 'running', 'duration_seconds': None},
                ...
            }
        """
        try:
            # Access the underlying gRPC resource to get task details
            gca_resource = pipeline_job._gca_resource

            if not hasattr(gca_resource, 'job_detail'):
                logger.info(f"Pipeline {pipeline_job.name}: _gca_resource has no job_detail attribute")
                return {}

            if not gca_resource.job_detail:
                logger.info(f"Pipeline {pipeline_job.name}: job_detail is empty/None")
                return {}

            task_details = gca_resource.job_detail.task_details
            if not task_details:
                logger.info(f"Pipeline {pipeline_job.name}: task_details is empty")
                return {}

            logger.info(f"Pipeline {pipeline_job.name}: Found {len(task_details)} task(s)")

            result = {}

            for task in task_details:
                # Get the task name (e.g., 'bigqueryexamplegen', 'statisticsgen')
                task_name = task.task_name.lower() if task.task_name else ''

                # Map to short stage name
                short_name = self.STAGE_NAME_MAP.get(task_name)
                if not short_name:
                    # Try partial matching for component names like 'BigQueryExampleGen'
                    for tfx_name, display_name in self.STAGE_NAME_MAP.items():
                        if tfx_name in task_name:
                            short_name = display_name
                            break

                if not short_name:
                    # Log unrecognized tasks at debug level (artifacts, etc.)
                    logger.debug(f"Pipeline {pipeline_job.name}: Skipping unrecognized task '{task_name}'")
                    continue

                # Get task state
                task_state = task.state.name if task.state else 'PENDING'

                # Map Vertex AI task states to our status
                state_mapping = {
                    'PENDING': 'pending',
                    'RUNNING': 'running',
                    'SUCCEEDED': 'completed',
                    'SKIPPED': 'completed',
                    'FAILED': 'failed',
                    'CANCELLED': 'failed',
                    'CANCELLING': 'running',
                    'NOT_TRIGGERED': 'pending',
                }
                status = state_mapping.get(task_state, 'pending')

                # Calculate duration if we have timestamps
                duration_seconds = None
                if task.start_time and task.end_time:
                    duration = task.end_time - task.start_time
                    duration_seconds = int(duration.total_seconds())
                elif task.start_time and status == 'running':
                    # For running tasks, calculate elapsed time
                    from datetime import datetime, timezone as dt_timezone
                    now = datetime.now(dt_timezone.utc)
                    start = task.start_time
                    if hasattr(start, 'timestamp'):
                        duration_seconds = int(now.timestamp() - start.timestamp())

                result[short_name] = {
                    'status': status,
                    'duration_seconds': duration_seconds,
                }
                logger.debug(f"Pipeline {pipeline_job.name}: Task '{task_name}' -> {short_name}: {status}")

            logger.info(f"Pipeline {pipeline_job.name}: Extracted {len(result)} stage statuses")
            return result

        except Exception as e:
            logger.exception(f"Error extracting task statuses from pipeline {pipeline_job.name}: {e}")
            return {}

    def cancel_quick_test(self, quick_test) -> 'QuickTest':
        """
        Cancel a running Quick Test pipeline.

        Handles two phases:
        1. SUBMITTING phase: Cancel Cloud Build (compilation)
        2. RUNNING phase: Cancel Vertex AI pipeline

        Args:
            quick_test: QuickTest instance

        Returns:
            Updated QuickTest instance
        """
        cloud_build_cancelled = False
        vertex_pipeline_cancelled = False

        # Phase 1: Cancel Cloud Build if still in compilation phase
        if quick_test.cloud_build_id and not quick_test.vertex_pipeline_job_name:
            try:
                from google.cloud.devtools import cloudbuild_v1

                client = cloudbuild_v1.CloudBuildClient()
                client.cancel_build(
                    project_id=self.project_id,
                    id=quick_test.cloud_build_id
                )
                cloud_build_cancelled = True
                logger.info(
                    f"Cancelled Cloud Build {quick_test.cloud_build_id} for "
                    f"{quick_test.display_name} (id={quick_test.id})"
                )
            except Exception as e:
                # Cloud Build may have already completed or failed
                logger.warning(
                    f"Could not cancel Cloud Build {quick_test.cloud_build_id} for "
                    f"{quick_test.display_name} (id={quick_test.id}): {e}"
                )
                # Check if Vertex pipeline was submitted in the meantime
                self._check_cloud_build_result(quick_test)
                quick_test.refresh_from_db()

        # Phase 2: Cancel Vertex AI pipeline if it exists
        if quick_test.vertex_pipeline_job_name:
            self._init_aiplatform()
            try:
                from google.cloud import aiplatform

                pipeline_job = aiplatform.PipelineJob.get(
                    quick_test.vertex_pipeline_job_name
                )
                pipeline_job.cancel()
                vertex_pipeline_cancelled = True
                logger.info(
                    f"Cancelled Vertex AI pipeline {quick_test.vertex_pipeline_job_name} for "
                    f"{quick_test.display_name} (id={quick_test.id})"
                )
            except Exception as e:
                logger.warning(
                    f"Error cancelling Vertex AI pipeline for "
                    f"{quick_test.display_name} (id={quick_test.id}): {e}"
                )

        # Update status
        quick_test.status = quick_test.STATUS_CANCELLED
        quick_test.completed_at = timezone.now()
        quick_test.save(update_fields=['status', 'completed_at'])

        # Log summary
        if cloud_build_cancelled and vertex_pipeline_cancelled:
            logger.info(f"Cancelled both Cloud Build and Vertex AI pipeline for {quick_test.display_name}")
        elif cloud_build_cancelled:
            logger.info(f"Cancelled during compilation phase for {quick_test.display_name}")
        elif vertex_pipeline_cancelled:
            logger.info(f"Cancelled during pipeline execution phase for {quick_test.display_name}")
        else:
            logger.warning(f"No active jobs found to cancel for {quick_test.display_name}")

        return quick_test

    def delete_quick_test(self, quick_test) -> None:
        """
        Delete a Quick Test and its associated GCS artifacts.

        Only experiments in terminal states (completed, failed, cancelled) can be deleted.
        Running or submitting experiments must be cancelled first.

        Args:
            quick_test: QuickTest instance to delete

        Raises:
            ExperimentServiceError: If experiment is still running or deletion fails
        """
        from ml_platform.models import QuickTest

        # Verify experiment is in terminal state
        if quick_test.status in (QuickTest.STATUS_RUNNING, QuickTest.STATUS_SUBMITTING):
            raise ExperimentServiceError(
                f"Cannot delete experiment in '{quick_test.status}' state. "
                "Please cancel the experiment first."
            )

        experiment_display = f"{quick_test.display_name} (id={quick_test.id})"
        logger.info(f"Deleting experiment {experiment_display}")

        # Delete GCS artifacts if path exists
        if quick_test.gcs_artifacts_path:
            self._delete_gcs_artifacts(quick_test.gcs_artifacts_path, experiment_display)

        # Delete the Django database record
        try:
            quick_test.delete()
            logger.info(f"Successfully deleted experiment {experiment_display} from database")
        except Exception as e:
            logger.error(f"Failed to delete experiment {experiment_display} from database: {e}")
            raise ExperimentServiceError(f"Failed to delete experiment: {e}")

    def _delete_gcs_artifacts(self, gcs_path: str, experiment_display: str) -> None:
        """
        Delete all objects under a GCS path.

        Args:
            gcs_path: GCS path (e.g., 'gs://bucket/path/to/artifacts' or 'path/to/artifacts')
            experiment_display: Display name for logging
        """
        try:
            # Parse GCS path - handle both 'gs://bucket/path' and 'path' formats
            if gcs_path.startswith('gs://'):
                # Extract bucket and prefix from full GCS URI
                path_parts = gcs_path[5:].split('/', 1)
                bucket_name = path_parts[0]
                prefix = path_parts[1] if len(path_parts) > 1 else ''
            else:
                # Assume it's a path within the artifacts bucket
                bucket_name = self.ARTIFACTS_BUCKET
                prefix = gcs_path

            bucket = self.storage_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))

            if not blobs:
                logger.info(f"No GCS artifacts found at {gcs_path} for {experiment_display}")
                return

            # Delete all blobs under the prefix
            for blob in blobs:
                try:
                    blob.delete()
                except Exception as e:
                    logger.warning(f"Failed to delete GCS blob {blob.name}: {e}")

            logger.info(
                f"Deleted {len(blobs)} GCS artifacts from {bucket_name}/{prefix} "
                f"for {experiment_display}"
            )

        except Exception as e:
            # Log warning but don't fail the deletion - DB cleanup is more important
            logger.warning(
                f"Failed to delete GCS artifacts at {gcs_path} for {experiment_display}: {e}. "
                "Continuing with database deletion."
            )
