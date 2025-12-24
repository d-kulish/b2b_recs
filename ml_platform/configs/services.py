"""
Configs Domain Services

Contains business logic for Feature & Model Configuration:
- SmartDefaultsService: Auto-configures features based on column mapping and statistics
- TensorDimensionCalculator: Calculates tensor dimensions for preview
- PreprocessingFnGenerator: Generates TFX Transform preprocessing_fn code
- TrainerModuleGenerator: Generates TFX Trainer module code
- validate_python_code: Validates generated Python code syntax
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def validate_python_code(code: str, code_type: str = 'unknown') -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Validate that generated Python code is syntactically correct.

    Uses Python's compile() to check syntax without executing the code.

    Args:
        code: Python code string to validate
        code_type: Type of code for logging ('transform', 'trainer', etc.)

    Returns:
        Tuple of (is_valid, error_message, error_line):
        - is_valid: True if code compiles successfully
        - error_message: Error description if invalid, None if valid
        - error_line: Line number where error occurred, None if valid
    """
    if not code or not code.strip():
        return False, "Code is empty", None

    try:
        compile(code, f'<generated_{code_type}>', 'exec')
        return True, None, None
    except SyntaxError as e:
        error_msg = f"{e.msg}" if e.msg else "Syntax error"
        if e.text:
            error_msg += f": {e.text.strip()}"
        logger.warning(f"Code validation failed for {code_type}: {error_msg} at line {e.lineno}")
        return False, error_msg, e.lineno
    except Exception as e:
        logger.warning(f"Code validation error for {code_type}: {str(e)}")
        return False, str(e), None


class SmartDefaultsService:
    """
    Auto-configures feature engineering based on dataset column mapping and statistics.

    Uses column statistics to determine appropriate transformations:
    - Embedding dimensions based on cardinality
    - Default transforms based on data type
    - Sensible cross feature suggestions
    """

    # Cardinality to embedding dimension mapping
    # (min_cardinality, max_cardinality, recommended_dim)
    CARDINALITY_TO_DIM = [
        (0, 50, 8),
        (50, 500, 16),
        (500, 5000, 32),
        (5000, 50000, 64),
        (50000, 500000, 96),
        (500000, float('inf'), 128),
    ]

    # Column role to model assignment
    # Maps column mapping keys to their target model
    BUYER_MODEL_MAPPINGS = [
        'user_id', 'customer_id', 'buyer_id',
        'user_city', 'user_region', 'user_country',
        'customer_segment', 'customer_tier',
    ]

    PRODUCT_MODEL_MAPPINGS = [
        'product_id', 'item_id', 'sku',
        'category', 'subcategory', 'brand',
        'product_name', 'product_description',
    ]

    CONTEXT_MAPPINGS = [
        'timestamp', 'transaction_date', 'event_date',
        'revenue', 'amount', 'price',
        'quantity', 'units',
    ]

    def __init__(self, dataset):
        """
        Initialize with a Dataset instance.

        Args:
            dataset: Dataset model instance with selected_columns, column_mapping, and column_stats
        """
        self.dataset = dataset
        self.selected_columns = dataset.selected_columns or {}
        self.column_mapping = dataset.column_mapping or {}
        self.column_stats = dataset.column_stats or {}

    def get_embedding_recommendation(self, cardinality: int) -> int:
        """Get recommended embedding dimension for a given cardinality."""
        for min_card, max_card, dim in self.CARDINALITY_TO_DIM:
            if min_card <= cardinality < max_card:
                return dim
        return 128

    def generate(self) -> Dict[str, Any]:
        """
        Generate smart default feature configuration.

        Returns:
            dict with keys:
            - buyer_model_features: List of feature configs for BuyerModel
            - product_model_features: List of feature configs for ProductModel
            - buyer_model_crosses: List of cross feature configs for BuyerModel
            - product_model_crosses: List of cross feature configs for ProductModel
        """
        buyer_features = []
        product_features = []

        # Get flat list of all columns with their info
        all_columns = self._get_all_columns_with_info()

        for col_info in all_columns:
            col_name = col_info['name']
            col_type = col_info['type']
            stats = col_info.get('stats', {})
            mapping_role = col_info.get('mapping_role')

            # Determine target model based on mapping role
            target_model = self._determine_target_model(col_name, mapping_role)

            if target_model is None:
                continue  # Skip unmapped columns

            # Create feature config based on type
            feature = self._create_feature_config(col_name, col_type, stats, mapping_role)

            if feature:
                if target_model == 'buyer':
                    buyer_features.append(feature)
                else:
                    product_features.append(feature)

        # Generate default cross features
        buyer_crosses = self._generate_default_crosses(buyer_features, 'buyer')
        product_crosses = self._generate_default_crosses(product_features, 'product')

        return {
            'buyer_model_features': buyer_features,
            'product_model_features': product_features,
            'buyer_model_crosses': buyer_crosses,
            'product_model_crosses': product_crosses,
        }

    def _get_all_columns_with_info(self) -> List[Dict[str, Any]]:
        """
        Get all selected columns with their type and statistics.

        IMPORTANT: This method handles duplicate column names across tables
        the same way the BigQuery query generator does:
        - First occurrence: uses raw column name
        - Subsequent occurrences: uses {table_alias}_{column_name}

        This ensures FeatureConfig column names match the BigQuery output.
        """
        columns = []
        seen_cols = set()  # Track seen column names to handle duplicates

        # Reverse column mapping to get role by column name
        reverse_mapping = {v: k for k, v in self.column_mapping.items()}

        for table, cols in self.selected_columns.items():
            table_alias = table.split('.')[-1]  # Get just the table name without dataset

            for col in cols:
                # Get column stats if available
                stats_key = f"{table_alias}.{col}"
                stats = self.column_stats.get(stats_key, {})

                # Determine column type from stats or default to STRING
                col_type = stats.get('type', 'STRING')

                # Handle duplicate column names across tables
                # This mirrors the logic in BigQueryService.generate_query()
                if col in seen_cols:
                    # Duplicate column - use table_alias_col format
                    output_name = f"{table_alias}_{col}"
                else:
                    # First occurrence - use raw column name
                    output_name = col
                    seen_cols.add(col)

                columns.append({
                    'name': output_name,  # This is what TFX will see
                    'original_name': col,  # Keep original for reference
                    'table': table,
                    'type': col_type,
                    'stats': stats,
                    'mapping_role': reverse_mapping.get(col),
                })

        return columns

    def _determine_target_model(self, col_name: str, mapping_role: Optional[str]) -> Optional[str]:
        """
        Determine which model a column should be assigned to.

        Returns:
            'buyer', 'product', or None if column should be skipped
        """
        # Check explicit mapping role first
        if mapping_role:
            if mapping_role in self.BUYER_MODEL_MAPPINGS or mapping_role.startswith('customer_') or mapping_role.startswith('user_'):
                return 'buyer'
            if mapping_role in self.PRODUCT_MODEL_MAPPINGS or mapping_role.startswith('product_'):
                return 'product'
            if mapping_role in self.CONTEXT_MAPPINGS:
                return 'buyer'  # Context features go to query tower

        # Fallback: check column name patterns
        col_lower = col_name.lower()

        if any(pattern in col_lower for pattern in ['customer', 'user', 'buyer']):
            return 'buyer'
        if any(pattern in col_lower for pattern in ['product', 'item', 'sku', 'category']):
            return 'product'
        if any(pattern in col_lower for pattern in ['date', 'time', 'revenue', 'amount', 'quantity']):
            return 'buyer'  # Context features go to query tower

        return None  # Skip unmapped columns

    def _create_feature_config(self, col_name: str, col_type: str, stats: Dict, mapping_role: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Create feature configuration based on column type and statistics.

        Args:
            col_name: Column name
            col_type: BigQuery column type (STRING, INTEGER, FLOAT, TIMESTAMP, etc.)
            stats: Column statistics from BigQuery
            mapping_role: ML role mapping (e.g., 'customer_id', 'product_id')

        Returns:
            Feature configuration dict or None if column should be skipped
        """
        # Normalize type
        col_type_upper = col_type.upper()

        # String columns -> vocabulary embedding
        if col_type_upper in ['STRING', 'BYTES']:
            cardinality = stats.get('cardinality', stats.get('unique_count', 1000))
            is_primary_id = mapping_role in ['user_id', 'customer_id', 'product_id', 'item_id']

            return {
                'column': col_name,
                'type': 'string_embedding',
                'embedding_dim': self.get_embedding_recommendation(cardinality),
                'vocab_settings': {
                    'max_size': min(int(cardinality * 1.5), 500000) if cardinality else 100000,
                    'oov_buckets': 10,
                    'min_frequency': 5 if is_primary_id else 1,
                }
            }

        # Numeric columns -> normalize + optional bucketize
        if col_type_upper in ['INTEGER', 'INT64', 'FLOAT', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC']:
            # Check if numeric has high cardinality (might benefit from embedding)
            cardinality = stats.get('cardinality', stats.get('unique_count', 0))
            has_high_cardinality = cardinality > 100

            return {
                'column': col_name,
                'type': 'numeric',
                'transforms': {
                    'normalize': {'enabled': True, 'range': [-1, 1]},
                    'bucketize': {
                        'enabled': has_high_cardinality,
                        'buckets': 100,
                        'embedding_dim': 32,
                    },
                    'log_transform': False,
                }
            }

        # Timestamp columns -> normalize + cyclical
        if col_type_upper in ['TIMESTAMP', 'DATETIME', 'DATE']:
            return {
                'column': col_name,
                'type': 'timestamp',
                'transforms': {
                    'normalize': {'enabled': True, 'range': [-1, 1]},
                    'bucketize': {'enabled': False},
                    'cyclical': {
                        'annual': False,
                        'quarterly': True,
                        'monthly': True,
                        'weekly': True,
                        'daily': False,
                    }
                }
            }

        # Skip other types (BOOL, ARRAY, STRUCT, etc.)
        return None

    def _generate_default_crosses(self, features: List[Dict], model_type: str) -> List[Dict]:
        """
        Generate sensible default cross features.

        Args:
            features: List of feature configs
            model_type: 'buyer' or 'product'

        Returns:
            List of cross feature configurations
        """
        crosses = []
        feature_names = [f['column'] for f in features]

        if model_type == 'buyer':
            # Customer × City cross
            customer_cols = [n for n in feature_names if 'customer' in n.lower() or 'user' in n.lower()]
            city_cols = [n for n in feature_names if 'city' in n.lower() or 'region' in n.lower()]

            if customer_cols and city_cols:
                crosses.append({
                    'features': [customer_cols[0], city_cols[0]],
                    'hash_bucket_size': 5000,
                    'embedding_dim': 16,
                })

        elif model_type == 'product':
            # Category × Subcategory cross
            category_cols = [n for n in feature_names if n.lower() == 'category']
            subcategory_cols = [n for n in feature_names if 'subcategory' in n.lower() or 'sub_category' in n.lower()]

            if category_cols and subcategory_cols:
                crosses.append({
                    'features': [category_cols[0], subcategory_cols[0]],
                    'hash_bucket_size': 1000,
                    'embedding_dim': 16,
                })

        return crosses


class TensorDimensionCalculator:
    """
    Calculates tensor dimensions for feature configurations.
    Used for real-time preview in the UI.
    """

    def calculate(self, features: List[Dict], crosses: List[Dict]) -> Dict[str, Any]:
        """
        Calculate total dimensions and breakdown by feature.

        Args:
            features: List of feature configurations
            crosses: List of cross feature configurations

        Returns:
            dict with keys:
            - total: Total tensor dimensions
            - breakdown: List of {name, dim} dicts for each feature
        """
        breakdown = []
        total = 0

        for feature in features:
            dims = self._feature_dims(feature)
            for name, dim in dims.items():
                breakdown.append({'name': name, 'dim': dim})
                total += dim

        for cross in crosses:
            name = ' × '.join(cross.get('features', []))
            dim = cross.get('embedding_dim', 16)
            breakdown.append({'name': name, 'dim': dim, 'is_cross': True})
            total += dim

        return {'total': total, 'breakdown': breakdown}

    def _feature_dims(self, feature: Dict) -> Dict[str, int]:
        """
        Get dimension breakdown for a single feature.

        Supports both:
        - Old format: feature.type = 'string_embedding'/'numeric'/'timestamp'
        - New format: feature.data_type = 'numeric'/'text'/'temporal'

        Args:
            feature: Feature configuration dict

        Returns:
            Dict mapping feature name variants to their dimensions
        """
        result = {}
        col = feature.get('column', 'unknown')
        transforms = feature.get('transforms', {})

        # Check for new data_type format first, fall back to old type format
        data_type = feature.get('data_type')
        feature_type = feature.get('type', '')

        # Handle new format (data_type = 'numeric', 'text', 'temporal')
        if data_type == 'text' or (not data_type and feature_type == 'string_embedding'):
            # Text/Embedding type
            if data_type == 'text':
                # New format: embedding settings in transforms
                if transforms.get('embedding', {}).get('enabled'):
                    result[col] = transforms['embedding'].get('embedding_dim', 32)
            else:
                # Old format: embedding_dim at top level
                result[col] = feature.get('embedding_dim', 32)

        elif data_type == 'numeric' or (not data_type and feature_type == 'numeric'):
            # Numeric type
            if transforms.get('normalize', {}).get('enabled'):
                result[f'{col}_norm'] = 1
            if transforms.get('bucketize', {}).get('enabled'):
                result[f'{col}_bucket'] = transforms['bucketize'].get('embedding_dim', 32)

        elif data_type == 'temporal' or (not data_type and feature_type == 'timestamp'):
            # Temporal/Timestamp type
            if transforms.get('normalize', {}).get('enabled'):
                result[f'{col}_norm'] = 1
            if transforms.get('bucketize', {}).get('enabled'):
                result[f'{col}_bucket'] = transforms['bucketize'].get('embedding_dim', 32)

            cyclical = transforms.get('cyclical', {})
            if data_type == 'temporal':
                # New format: cyclical.enabled + sub-options
                if cyclical.get('enabled'):
                    cyclical_dims = sum(2 for c in ['quarterly', 'monthly', 'weekly', 'daily']
                                       if cyclical.get(c))
                    if cyclical_dims > 0:
                        result[f'{col}_cyclical'] = cyclical_dims
            else:
                # Old format: direct cyclical options
                cyclical_dims = sum(2 for c in ['annual', 'quarterly', 'monthly', 'weekly', 'daily']
                                   if cyclical.get(c))
                if cyclical_dims > 0:
                    result[f'{col}_cyclical'] = cyclical_dims

        return result


def serialize_feature_config(fc, include_details: bool = False) -> Dict[str, Any]:
    """
    Serialize a FeatureConfig model instance to a dictionary.

    Args:
        fc: FeatureConfig model instance
        include_details: Include full feature arrays if True

    Returns:
        Serialized dictionary
    """
    data = {
        'id': fc.id,
        'name': fc.name,
        'description': fc.description,
        'dataset_id': fc.dataset_id,
        'dataset_name': fc.dataset.name,
        'version': fc.version,
        'buyer_tensor_dim': fc.buyer_tensor_dim,
        'product_tensor_dim': fc.product_tensor_dim,
        'buyer_features_count': len(fc.buyer_model_features or []),
        'product_features_count': len(fc.product_model_features or []),
        'buyer_crosses_count': len(fc.buyer_model_crosses or []),
        'product_crosses_count': len(fc.product_model_crosses or []),
        'columns_in_both_models': fc.get_columns_in_both_models(),
        'created_at': fc.created_at.isoformat() if fc.created_at else None,
        'updated_at': fc.updated_at.isoformat() if fc.updated_at else None,
        'created_by': fc.created_by.username if fc.created_by else None,
        'has_transform_code': bool(fc.generated_transform_code),
    }

    if include_details:
        data['buyer_model_features'] = fc.buyer_model_features
        data['product_model_features'] = fc.product_model_features
        data['buyer_model_crosses'] = fc.buyer_model_crosses
        data['product_model_crosses'] = fc.product_model_crosses

        # Add dataset info for View modal
        data['dataset_info'] = get_dataset_info_for_view(fc.dataset)

    return data


def validate_feature_config(data: Dict, dataset, exclude_config_id: Optional[int] = None) -> Tuple[bool, Dict]:
    """
    Validate feature config data before save.

    Args:
        data: Feature config data dict
        dataset: Dataset model instance
        exclude_config_id: Config ID to exclude from uniqueness check (for updates)

    Returns:
        Tuple of (is_valid, errors_dict)
    """
    from ml_platform.models import FeatureConfig

    errors = {}

    # Required fields
    if not data.get('name', '').strip():
        errors['name'] = 'Name is required'

    # Name uniqueness check
    if data.get('name'):
        existing = FeatureConfig.objects.filter(
            dataset=dataset,
            name=data['name'].strip()
        )
        if exclude_config_id:
            existing = existing.exclude(id=exclude_config_id)
        if existing.exists():
            errors['name'] = 'A feature config with this name already exists for this dataset'

    # Validate features have required fields
    for feature_list_key in ['buyer_model_features', 'product_model_features']:
        features = data.get(feature_list_key, [])
        if features:
            for i, f in enumerate(features):
                if not f.get('column'):
                    errors[f'{feature_list_key}[{i}]'] = 'Feature must have a column name'
                # Support both old 'type' and new 'data_type' format
                if not f.get('type') and not f.get('data_type'):
                    errors[f'{feature_list_key}[{i}]'] = 'Feature must have a type'

    # Validate crosses have required fields
    for cross_list_key in ['buyer_model_crosses', 'product_model_crosses']:
        crosses = data.get(cross_list_key, [])
        if crosses:
            for i, c in enumerate(crosses):
                if not c.get('features') or len(c['features']) < 2:
                    errors[f'{cross_list_key}[{i}]'] = 'Cross feature must have at least 2 features'

    return (len(errors) == 0, errors)


class SemanticTypeService:
    """
    Infers semantic types from BigQuery types and column statistics.

    Semantic Types (user-friendly names):
    - "number"    : Continuous numeric values → Normalize, Bucketize, Log
    - "id"        : Categorical IDs/codes    → Embedding
    - "category"  : Categorical text         → Embedding
    - "date"      : Timestamps/dates         → Normalize, Cyclical
    - "cyclical"  : Periodic numeric values  → Sin/Cos encoding
    """

    SEMANTIC_TYPES = {
        'number': {
            'label': 'Number',
            'description': 'Continuous numeric values',
            'transforms': ['normalize', 'bucketize', 'log_transform'],
            'feature_type': 'numeric',
        },
        'id': {
            'label': 'ID / Code',
            'description': 'Categorical identifiers',
            'transforms': ['embedding'],
            'feature_type': 'string_embedding',
        },
        'category': {
            'label': 'Category',
            'description': 'Categorical text values',
            'transforms': ['embedding'],
            'feature_type': 'string_embedding',
        },
        'date': {
            'label': 'Date / Time',
            'description': 'Temporal values',
            'transforms': ['normalize', 'cyclical'],
            'feature_type': 'timestamp',
        },
        'cyclical': {
            'label': 'Cyclical',
            'description': 'Periodic numeric values (hour, day, month)',
            'transforms': ['cyclical_encoding'],
            'feature_type': 'cyclical',
        }
    }

    # Patterns that indicate ID columns
    ID_PATTERNS = ['_id', 'id_', '_key', 'key_', '_code', 'code_', 'zip', 'postal', 'sku']

    # BigQuery type mappings
    BQ_NUMERIC_TYPES = ['INT64', 'INTEGER', 'FLOAT64', 'FLOAT', 'NUMERIC', 'BIGNUMERIC']
    BQ_STRING_TYPES = ['STRING', 'BYTES']
    BQ_TIMESTAMP_TYPES = ['TIMESTAMP', 'DATETIME', 'DATE', 'TIME']

    @classmethod
    def get_type_label(cls, semantic_type: str) -> str:
        """Get user-friendly label for a semantic type."""
        return cls.SEMANTIC_TYPES.get(semantic_type, {}).get('label', semantic_type)

    @classmethod
    def get_type_options(cls, bq_type: str) -> List[str]:
        """
        Get available semantic type options based on BigQuery type.

        Args:
            bq_type: BigQuery column type (e.g., 'INT64', 'STRING')

        Returns:
            List of valid semantic type keys
        """
        bq_type_upper = bq_type.upper() if bq_type else 'STRING'

        if bq_type_upper in cls.BQ_NUMERIC_TYPES:
            return ['number', 'id', 'cyclical']
        elif bq_type_upper in cls.BQ_STRING_TYPES:
            return ['category', 'id', 'date']
        elif bq_type_upper in cls.BQ_TIMESTAMP_TYPES:
            return ['date', 'category']
        else:
            return ['category', 'id']

    @classmethod
    def infer_semantic_type(
        cls,
        col_name: str,
        bq_type: str,
        stats: Optional[Dict] = None,
        sample_values: Optional[List] = None
    ) -> str:
        """
        Infer semantic type from column name, BigQuery type, and statistics.

        Args:
            col_name: Column name
            bq_type: BigQuery column type
            stats: Column statistics (cardinality, min, max, etc.)
            sample_values: Sample values from the column

        Returns:
            Inferred semantic type key
        """
        stats = stats or {}
        bq_type_upper = bq_type.upper() if bq_type else 'STRING'
        col_lower = col_name.lower()

        # String types
        if bq_type_upper in cls.BQ_STRING_TYPES:
            # Check if it looks like a timestamp
            if sample_values and cls._looks_like_timestamp(sample_values):
                return 'date'
            # Check if column name suggests ID
            if any(pattern in col_lower for pattern in cls.ID_PATTERNS):
                return 'id'
            return 'category'

        # Timestamp types
        if bq_type_upper in cls.BQ_TIMESTAMP_TYPES:
            return 'date'

        # Numeric types - need more analysis
        if bq_type_upper in cls.BQ_NUMERIC_TYPES:
            # Check for ID patterns in name
            if any(pattern in col_lower for pattern in cls.ID_PATTERNS):
                return 'id'

            # Check for high cardinality (likely an ID)
            cardinality = stats.get('cardinality') or stats.get('unique_count', 0)
            total_rows = stats.get('total_rows', 1)
            if total_rows > 0 and cardinality > 100:
                # If >10% unique values, probably an ID
                if cardinality / total_rows > 0.1:
                    return 'id'

            # Check for cyclical patterns based on value range
            min_val = stats.get('min')
            max_val = stats.get('max')
            if min_val is not None and max_val is not None:
                try:
                    min_val = float(min_val)
                    max_val = float(max_val)
                    # Hour of day
                    if 0 <= min_val and max_val <= 23 and max_val - min_val >= 10:
                        return 'cyclical'
                    # Day of week
                    if 0 <= min_val and max_val <= 6:
                        return 'cyclical'
                    # Month
                    if 1 <= min_val and max_val <= 12 and max_val - min_val >= 6:
                        return 'cyclical'
                    # Day of month
                    if 1 <= min_val and max_val <= 31 and max_val - min_val >= 15:
                        return 'cyclical'
                except (TypeError, ValueError):
                    pass

            return 'number'

        # Default to category for unknown types
        return 'category'

    @classmethod
    def _looks_like_timestamp(cls, sample_values: List) -> bool:
        """
        Check if sample values look like timestamps.

        Args:
            sample_values: List of sample values

        Returns:
            True if values appear to be timestamps
        """
        import re

        # Date patterns to check
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}',           # 2024-01-15
            r'^\d{2}/\d{2}/\d{4}',           # 01/15/2024
            r'^\d{2}-\d{2}-\d{4}',           # 15-01-2024
            r'^\d{4}/\d{2}/\d{2}',           # 2024/01/15
            r'^\d{8}$',                       # 20240115
        ]

        # Check at least 3 non-null values
        valid_values = [v for v in sample_values if v is not None and str(v).strip()][:5]
        if len(valid_values) < 2:
            return False

        matches = 0
        for val in valid_values:
            val_str = str(val).strip()
            for pattern in date_patterns:
                if re.match(pattern, val_str):
                    matches += 1
                    break

        # If majority of values match date patterns
        return matches >= len(valid_values) * 0.6

    @classmethod
    def detect_cyclical_period(cls, col_name: str, stats: Optional[Dict] = None) -> int:
        """
        Detect the period for cyclical encoding based on column stats.

        Args:
            col_name: Column name
            stats: Column statistics

        Returns:
            Detected period (e.g., 24 for hours, 7 for days, 12 for months)
        """
        stats = stats or {}
        col_lower = col_name.lower()

        min_val = stats.get('min')
        max_val = stats.get('max')

        # Try to detect from column name first
        if 'hour' in col_lower:
            return 24
        if 'day_of_week' in col_lower or 'weekday' in col_lower:
            return 7
        if 'month' in col_lower:
            return 12
        if 'day_of_month' in col_lower or 'day' in col_lower:
            return 31
        if 'quarter' in col_lower:
            return 4

        # Try to detect from value range
        if min_val is not None and max_val is not None:
            try:
                min_val = float(min_val)
                max_val = float(max_val)
                if 0 <= min_val and max_val <= 23:
                    return 24
                if 0 <= min_val and max_val <= 6:
                    return 7
                if 1 <= min_val and max_val <= 12:
                    return 12
                if 1 <= min_val and max_val <= 31:
                    return 31
                if 1 <= min_val and max_val <= 4:
                    return 4
            except (TypeError, ValueError):
                pass

        return 12  # Default to monthly

    @classmethod
    def get_feature_type(cls, semantic_type: str) -> str:
        """
        Get the internal feature type for a semantic type.

        Args:
            semantic_type: Semantic type key

        Returns:
            Internal feature type (e.g., 'string_embedding', 'numeric')
        """
        return cls.SEMANTIC_TYPES.get(semantic_type, {}).get('feature_type', 'string_embedding')


class PreprocessingFnGenerator:
    """
    Generates TFX Transform preprocessing_fn from FeatureConfig.

    The generated code:
    - Creates vocabularies for text features (tft.compute_and_apply_vocabulary)
    - Normalizes numeric features (tft.scale_to_z_score)
    - Bucketizes numeric/temporal features (tft.bucketize)
    - Extracts cyclical patterns from temporal features (sin/cos)
    - Creates cross feature hashes (tf.sparse.cross_hashed)

    All embedding creation happens in Trainer, not Transform.
    Transform outputs indices/floats, Trainer creates embeddings from those.

    Output naming convention:
    - Text: {column} (vocab index)
    - Numeric normalize: {column}_norm (float)
    - Numeric/Temporal bucketize: {column}_bucket (bucket index)
    - Temporal cyclical: {column}_{cycle}_sin, {column}_{cycle}_cos (floats)
    - Cross bucketize (for numeric/temporal): {column}_cross_bucket (bucket index)
    - Cross hash: {col1}_x_{col2}_cross (hash index)
    """

    NUM_OOV_BUCKETS = 1

    def __init__(self, feature_config: 'FeatureConfig'):
        """
        Initialize with a FeatureConfig instance.

        Args:
            feature_config: FeatureConfig model instance
        """
        self.config = feature_config
        self.buyer_features = feature_config.buyer_model_features or []
        self.product_features = feature_config.product_model_features or []
        self.buyer_crosses = feature_config.buyer_model_crosses or []
        self.product_crosses = feature_config.product_model_crosses or []

    def generate(self) -> str:
        """
        Generate complete preprocessing_fn module as Python code string.

        Returns:
            Python code string containing the preprocessing_fn function
        """
        # Collect all features organized by type
        all_features = self._collect_all_features()

        # Build code sections
        header = self._generate_header()
        imports = self._generate_imports()
        constants = self._generate_constants()

        fn_start = self._generate_function_start()
        text_code = self._generate_text_transforms(all_features['text'])
        numeric_code = self._generate_numeric_transforms(all_features['numeric'])
        temporal_code = self._generate_temporal_transforms(all_features['temporal'])
        cross_code = self._generate_cross_transforms()
        fn_end = self._generate_function_end()

        # Combine all sections
        sections = [
            header,
            imports,
            constants,
            fn_start,
        ]

        if text_code:
            sections.append(text_code)
        if numeric_code:
            sections.append(numeric_code)
        if temporal_code:
            sections.append(temporal_code)
        if cross_code:
            sections.append(cross_code)

        sections.append(fn_end)

        return '\n'.join(sections)

    def _collect_all_features(self) -> Dict[str, List[Dict]]:
        """
        Organize all features by type for code generation.

        Merges buyer and product features, deduplicating by column name.
        Supports both old format (type=string_embedding/numeric/timestamp)
        and new format (data_type=text/numeric/temporal).

        Returns:
            Dict with keys 'text', 'numeric', 'temporal', each containing list of features
        """
        all_features = {'text': [], 'numeric': [], 'temporal': []}
        seen_columns = set()

        for feature in self.buyer_features + self.product_features:
            col = feature.get('column')
            if col in seen_columns:
                continue
            seen_columns.add(col)

            # Determine feature type (support both old and new format)
            data_type = feature.get('data_type')
            feature_type = feature.get('type', '')

            if data_type == 'text' or feature_type == 'string_embedding':
                all_features['text'].append(feature)
            elif data_type == 'numeric' or feature_type == 'numeric':
                all_features['numeric'].append(feature)
            elif data_type == 'temporal' or feature_type == 'timestamp':
                all_features['temporal'].append(feature)

        return all_features

    def _generate_header(self) -> str:
        """Generate file header with metadata."""
        buyer_cols = [f.get('column', '?') for f in self.buyer_features]
        product_cols = [f.get('column', '?') for f in self.product_features]

        buyer_cross_desc = []
        for c in self.buyer_crosses:
            features = c.get('features', [])
            if isinstance(features[0], dict):
                names = [f.get('column', '?') for f in features]
            else:
                names = features
            buyer_cross_desc.append(' × '.join(names))

        product_cross_desc = []
        for c in self.product_crosses:
            features = c.get('features', [])
            if isinstance(features[0], dict):
                names = [f.get('column', '?') for f in features]
            else:
                names = features
            product_cross_desc.append(' × '.join(names))

        return f'''# Auto-generated TFX Transform preprocessing_fn
# FeatureConfig: "{self.config.name}" (ID: {self.config.id})
# Generated at: {datetime.utcnow().isoformat()}Z
#
# BuyerModel features: {', '.join(buyer_cols) if buyer_cols else 'none'}
# ProductModel features: {', '.join(product_cols) if product_cols else 'none'}
# Buyer crosses: {', '.join(buyer_cross_desc) if buyer_cross_desc else 'none'}
# Product crosses: {', '.join(product_cross_desc) if product_cross_desc else 'none'}
'''

    def _generate_imports(self) -> str:
        """Generate import statements."""
        return '''import math
import tensorflow as tf
import tensorflow_transform as tft
'''

    def _generate_constants(self) -> str:
        """Generate module constants."""
        return f'''NUM_OOV_BUCKETS = {self.NUM_OOV_BUCKETS}
'''

    def _generate_function_start(self) -> str:
        """Generate function definition and docstring."""
        return '''
def preprocessing_fn(inputs):
    """
    TFX Transform preprocessing function.

    Outputs vocabulary indices for text features, normalized values for numeric,
    cyclical encodings for temporal, and hashed indices for crosses.

    Embeddings are created in the Trainer module, not here.
    """
    outputs = {}
'''

    def _generate_function_end(self) -> str:
        """Generate function return statement."""
        return '''
    return outputs
'''

    def _generate_text_transforms(self, features: List[Dict]) -> str:
        """
        Generate tft.compute_and_apply_vocabulary() calls for text features.

        Args:
            features: List of text feature configurations

        Returns:
            Python code string for text transforms
        """
        if not features:
            return ''

        lines = [
            '    # =========================================================================',
            '    # TEXT FEATURES → Vocabulary lookup (outputs: vocab indices)',
            '    # =========================================================================',
            ''
        ]

        for feature in features:
            col = feature.get('column')
            bq_type = feature.get('bq_type', 'STRING')

            # Get embedding dim for comment (used in Trainer, not here)
            transforms = feature.get('transforms', {})
            if transforms.get('embedding', {}).get('embedding_dim'):
                embed_dim = transforms['embedding']['embedding_dim']
            else:
                embed_dim = feature.get('embedding_dim', 32)

            lines.append(f"    # {col}: {bq_type} → vocab index (embedding_dim={embed_dim} in Trainer)")
            lines.append(f"    outputs['{col}'] = tft.compute_and_apply_vocabulary(")
            lines.append(f"        inputs['{col}'],")
            lines.append(f"        num_oov_buckets=NUM_OOV_BUCKETS,")
            lines.append(f"        vocab_filename='{col}_vocab'")
            lines.append(f"    )")
            lines.append('')

        return '\n'.join(lines)

    def _generate_numeric_transforms(self, features: List[Dict]) -> str:
        """
        Generate normalize/bucketize calls for numeric features.

        Args:
            features: List of numeric feature configurations

        Returns:
            Python code string for numeric transforms
        """
        if not features:
            return ''

        lines = [
            '    # =========================================================================',
            '    # NUMERIC FEATURES → Normalize / Bucketize',
            '    # =========================================================================',
            ''
        ]

        for feature in features:
            col = feature.get('column')
            bq_type = feature.get('bq_type', 'FLOAT64')
            transforms = feature.get('transforms', {})

            normalize = transforms.get('normalize', {})
            bucketize = transforms.get('bucketize', {})

            has_normalize = normalize.get('enabled', False)
            has_bucketize = bucketize.get('enabled', False)

            if not has_normalize and not has_bucketize:
                continue

            # Describe transforms
            transform_desc = []
            if has_normalize:
                transform_desc.append('normalize')
            if has_bucketize:
                transform_desc.append(f"bucketize({bucketize.get('buckets', 100)})")

            lines.append(f"    # {col}: {bq_type} → {' + '.join(transform_desc)}")

            # Cast to float
            lines.append(f"    {col}_float = tf.cast(inputs['{col}'], tf.float32)")

            if has_normalize:
                lines.append(f"    outputs['{col}_norm'] = tft.scale_to_z_score({col}_float)")

            if has_bucketize:
                buckets = bucketize.get('buckets', 100)
                lines.append(f"    outputs['{col}_bucket'] = tft.bucketize({col}_float, num_buckets={buckets})")

            lines.append('')

        return '\n'.join(lines)

    def _generate_temporal_transforms(self, features: List[Dict]) -> str:
        """
        Generate normalize/cyclical/bucketize for temporal features.

        Args:
            features: List of temporal feature configurations

        Returns:
            Python code string for temporal transforms
        """
        if not features:
            return ''

        lines = [
            '    # =========================================================================',
            '    # TEMPORAL FEATURES → Normalize / Cyclical / Bucketize',
            '    # =========================================================================',
            ''
        ]

        for feature in features:
            col = feature.get('column')
            bq_type = feature.get('bq_type', 'TIMESTAMP')
            transforms = feature.get('transforms', {})

            normalize = transforms.get('normalize', {})
            cyclical = transforms.get('cyclical', {})
            bucketize = transforms.get('bucketize', {})

            has_normalize = normalize.get('enabled', False)
            has_bucketize = bucketize.get('enabled', False)

            # Check cyclical options (support both old and new format)
            cyclical_options = []
            if cyclical.get('enabled') or cyclical.get('yearly') or cyclical.get('weekly'):
                # New format has 'enabled' flag, old format has direct options
                for cycle in ['yearly', 'quarterly', 'monthly', 'weekly', 'daily']:
                    if cyclical.get(cycle):
                        cyclical_options.append(cycle)
            # Also check old 'annual' key
            if cyclical.get('annual'):
                cyclical_options.append('yearly')

            has_cyclical = len(cyclical_options) > 0

            if not has_normalize and not has_cyclical and not has_bucketize:
                continue

            # Describe transforms
            transform_desc = []
            if has_normalize:
                transform_desc.append('normalize')
            if has_cyclical:
                transform_desc.append(f"cyclical({', '.join(cyclical_options)})")
            if has_bucketize:
                transform_desc.append(f"bucketize({bucketize.get('buckets', 100)})")

            lines.append(f"    # {col}: {bq_type} → {' + '.join(transform_desc)}")
            lines.append(f"    # Convert timestamp to float seconds since epoch")
            lines.append(f"    {col}_seconds = tf.cast(")
            lines.append(f"        tf.cast(inputs['{col}'], tf.int64),")
            lines.append(f"        tf.float32")
            lines.append(f"    )")
            lines.append('')

            if has_normalize:
                lines.append(f"    # Normalize")
                lines.append(f"    outputs['{col}_norm'] = tft.scale_to_z_score({col}_seconds)")
                lines.append('')

            if has_cyclical:
                lines.append(f"    # Cyclical encoding")
                lines.append(f"    SECONDS_PER_DAY = 86400.0")
                lines.append(f"    days_since_epoch = {col}_seconds / SECONDS_PER_DAY")
                lines.append('')

                if 'yearly' in cyclical_options:
                    lines.append(f"    # Yearly: month of year (approximated via day of year)")
                    lines.append(f"    day_of_year_frac = tf.math.mod(days_since_epoch, 365.25) / 365.25")
                    lines.append(f"    outputs['{col}_yearly_sin'] = tf.sin(2.0 * math.pi * day_of_year_frac)")
                    lines.append(f"    outputs['{col}_yearly_cos'] = tf.cos(2.0 * math.pi * day_of_year_frac)")
                    lines.append('')

                if 'quarterly' in cyclical_options:
                    lines.append(f"    # Quarterly: month of quarter (approximated)")
                    lines.append(f"    quarter_frac = tf.math.mod(days_since_epoch, 91.31) / 91.31")
                    lines.append(f"    outputs['{col}_quarterly_sin'] = tf.sin(2.0 * math.pi * quarter_frac)")
                    lines.append(f"    outputs['{col}_quarterly_cos'] = tf.cos(2.0 * math.pi * quarter_frac)")
                    lines.append('')

                if 'monthly' in cyclical_options:
                    lines.append(f"    # Monthly: day of month (approximated via 30.44 days)")
                    lines.append(f"    day_of_month_frac = tf.math.mod(days_since_epoch, 30.44) / 30.44")
                    lines.append(f"    outputs['{col}_monthly_sin'] = tf.sin(2.0 * math.pi * day_of_month_frac)")
                    lines.append(f"    outputs['{col}_monthly_cos'] = tf.cos(2.0 * math.pi * day_of_month_frac)")
                    lines.append('')

                if 'weekly' in cyclical_options:
                    lines.append(f"    # Weekly: day of week (Monday=0)")
                    lines.append(f"    # Unix epoch (1970-01-01) was Thursday, so +4 to align Monday=0")
                    lines.append(f"    day_of_week_frac = tf.math.mod(days_since_epoch + 4, 7.0) / 7.0")
                    lines.append(f"    outputs['{col}_weekly_sin'] = tf.sin(2.0 * math.pi * day_of_week_frac)")
                    lines.append(f"    outputs['{col}_weekly_cos'] = tf.cos(2.0 * math.pi * day_of_week_frac)")
                    lines.append('')

                if 'daily' in cyclical_options:
                    lines.append(f"    # Daily: hour of day")
                    lines.append(f"    hour_frac = tf.math.mod({col}_seconds, SECONDS_PER_DAY) / SECONDS_PER_DAY")
                    lines.append(f"    outputs['{col}_daily_sin'] = tf.sin(2.0 * math.pi * hour_frac)")
                    lines.append(f"    outputs['{col}_daily_cos'] = tf.cos(2.0 * math.pi * hour_frac)")
                    lines.append('')

            if has_bucketize:
                buckets = bucketize.get('buckets', 100)
                lines.append(f"    # Bucketize")
                lines.append(f"    outputs['{col}_bucket'] = tft.bucketize({col}_seconds, num_buckets={buckets})")
                lines.append('')

        return '\n'.join(lines)

    def _generate_cross_transforms(self) -> str:
        """
        Generate cross feature hashing (with bucketization for numeric/temporal).

        Uses tft.hash_strings() to produce DENSE integer indices (not sparse).
        This makes it easy for Trainer to create embeddings from these indices.

        Returns:
            Python code string for cross transforms
        """
        all_crosses = []

        for cross in self.buyer_crosses:
            all_crosses.append(('buyer', cross))
        for cross in self.product_crosses:
            all_crosses.append(('product', cross))

        if not all_crosses:
            return ''

        lines = [
            '    # =========================================================================',
            '    # CROSS FEATURES → Bucketize (for numeric/temporal) + Hash (dense output)',
            '    # =========================================================================',
            ''
        ]

        # Track bucketized columns to avoid duplicates
        bucketized_for_cross = set()

        for model, cross in all_crosses:
            features = cross.get('features', [])
            hash_bucket_size = cross.get('hash_bucket_size', 5000)
            embedding_dim = cross.get('embedding_dim', 16)

            # Build feature names and string representations for hashing
            feature_names = []
            string_parts = []

            for f in features:
                # Handle both old format (string) and new format (dict)
                if isinstance(f, str):
                    col = f
                    f_type = 'text'
                    crossing_buckets = None
                else:
                    col = f.get('column', '')
                    f_type = f.get('type', 'text')
                    crossing_buckets = f.get('crossing_buckets')

                feature_names.append(col)

                if f_type in ['numeric', 'temporal'] and crossing_buckets:
                    # Need to bucketize this column for crossing
                    bucket_var = f"{col}_cross_bucket"

                    if bucket_var not in bucketized_for_cross:
                        bucketized_for_cross.add(bucket_var)
                        lines.append(f"    # Bucketize {col} for crossing ({crossing_buckets} buckets)")
                        lines.append(f"    {bucket_var} = tft.bucketize(")
                        lines.append(f"        tf.cast(inputs['{col}'], tf.float32),")
                        lines.append(f"        num_buckets={crossing_buckets}")
                        lines.append(f"    )")
                        lines.append('')

                    string_parts.append(f"tf.strings.as_string({bucket_var})")
                else:
                    # Text feature - use directly (ensure it's string type)
                    string_parts.append(f"tf.strings.as_string(inputs['{col}'])")

            # Generate cross name
            cross_name = '_x_'.join(feature_names) + '_cross'

            lines.append(f"    # Cross: {' × '.join(feature_names)} ({model}Model)")
            lines.append(f"    # Hash buckets: {hash_bucket_size}, embedding_dim: {embedding_dim} (in Trainer)")

            # Concatenate features with separator and hash to dense index
            if len(string_parts) == 2:
                lines.append(f"    {cross_name}_concat = tf.strings.join([")
                lines.append(f"        {string_parts[0]},")
                lines.append(f"        tf.constant('_x_'),")
                lines.append(f"        {string_parts[1]}")
                lines.append(f"    ])")
            else:
                # For 3+ features, join with separator
                lines.append(f"    {cross_name}_parts = [")
                for i, part in enumerate(string_parts):
                    comma = ',' if i < len(string_parts) - 1 else ''
                    lines.append(f"        {part}{comma}")
                lines.append(f"    ]")
                lines.append(f"    {cross_name}_concat = tf.strings.reduce_join(")
                lines.append(f"        {cross_name}_parts, separator='_x_'")
                lines.append(f"    )")

            # Hash to dense integer index
            lines.append(f"    outputs['{cross_name}'] = tft.hash_strings(")
            lines.append(f"        {cross_name}_concat,")
            lines.append(f"        hash_buckets={hash_bucket_size}")
            lines.append(f"    )")
            lines.append('')

        return '\n'.join(lines)

    def generate_and_save(self) -> Tuple[str, bool, Optional[str]]:
        """
        Generate code, validate it, and save to the FeatureConfig model.

        Returns:
            Tuple of (code, is_valid, error_message):
            - code: Generated Python code string
            - is_valid: True if code passes syntax validation
            - error_message: Error description if invalid, None if valid
        """
        code = self.generate()

        # Validate the generated code
        is_valid, error_msg, error_line = validate_python_code(code, 'transform')

        if not is_valid:
            logger.error(
                f"Generated transform code for config {self.config.id} has syntax error: "
                f"{error_msg} at line {error_line}"
            )

        self.config.generated_transform_code = code
        self.config.generated_at = datetime.utcnow()
        self.config.save(update_fields=['generated_transform_code', 'generated_at'])

        return code, is_valid, error_msg


class TrainerModuleGenerator:
    """
    Generates TFX Trainer module from FeatureConfig + ModelConfig.

    The generated code:
    - Loads vocabularies from Transform artifacts
    - Creates embeddings for text features (Embedding on vocab indices from Transform)
    - Uses normalized/cyclical values from Transform for numeric/temporal
    - Creates embeddings for bucket indices and cross features
    - Builds two-tower TFRS model with configurable architecture from ModelConfig
    - Supports multiple layer types: Dense, Dropout, BatchNorm, LayerNorm with L2 regularization
    - Supports multiple optimizers: Adagrad, Adam, SGD, RMSprop, AdamW, FTRL
    - Supports retrieval algorithms: BruteForce, ScaNN
    - Implements run_fn() for TFX Trainer component
    - Provides serving signature for raw input → recommendations

    Output naming convention (must match PreprocessingFnGenerator):
    - Text: {column} (vocab index from Transform)
    - Numeric: {column}_norm (float), {column}_bucket (index)
    - Temporal: {column}_norm, {column}_{cycle}_sin/cos, {column}_bucket
    - Cross: {col1}_x_{col2}_cross (hash index)
    """

    # Optimizer mapping for code generation
    OPTIMIZER_CODE = {
        'adagrad': 'tf.keras.optimizers.Adagrad',
        'adam': 'tf.keras.optimizers.Adam',
        'sgd': 'tf.keras.optimizers.SGD',
        'rmsprop': 'tf.keras.optimizers.RMSprop',
        'adamw': 'tf.keras.optimizers.AdamW',
        'ftrl': 'tf.keras.optimizers.Ftrl',
    }

    def __init__(self, feature_config: 'FeatureConfig', model_config: 'ModelConfig'):
        """
        Initialize with FeatureConfig and ModelConfig instances.

        Args:
            feature_config: FeatureConfig model instance (defines feature transformations)
            model_config: ModelConfig model instance (defines neural network architecture)
        """
        self.feature_config = feature_config
        self.model_config = model_config

        # Feature config data
        self.buyer_features = feature_config.buyer_model_features or []
        self.product_features = feature_config.product_model_features or []
        self.buyer_crosses = feature_config.buyer_model_crosses or []
        self.product_crosses = feature_config.product_model_crosses or []

        # Model config data
        self.buyer_tower_layers = model_config.buyer_tower_layers or []
        self.product_tower_layers = model_config.product_tower_layers or []
        self.output_embedding_dim = model_config.output_embedding_dim
        self.optimizer = model_config.optimizer
        self.learning_rate = model_config.learning_rate
        self.batch_size = model_config.batch_size
        self.epochs = model_config.epochs
        self.retrieval_algorithm = model_config.retrieval_algorithm
        self.top_k = model_config.top_k
        self.scann_num_leaves = model_config.scann_num_leaves
        self.scann_leaves_to_search = model_config.scann_leaves_to_search

    def generate(self) -> str:
        """
        Generate complete trainer_module.py as Python code string.

        Returns:
            Python code string containing the full trainer module
        """
        # Collect all features organized by type
        buyer_by_type = self._collect_features_by_type(self.buyer_features)
        product_by_type = self._collect_features_by_type(self.product_features)

        # Build code sections
        sections = [
            self._generate_header(),
            self._generate_imports(),
            self._generate_constants(),
            self._generate_input_fn(),
            self._generate_buyer_model(buyer_by_type),
            self._generate_product_model(product_by_type),
            self._generate_retrieval_model(),
            self._generate_serve_fn(),
            self._generate_mlflow_callback(),
            self._generate_run_fn(),
        ]

        return '\n'.join(sections)

    def _collect_features_by_type(self, features: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Organize features by type for code generation.

        Args:
            features: List of feature configurations

        Returns:
            Dict with keys 'text', 'numeric', 'temporal', each containing list of features
        """
        result = {'text': [], 'numeric': [], 'temporal': []}

        for feature in features:
            # Determine feature type (support both old and new format)
            data_type = feature.get('data_type')
            feature_type = feature.get('type', '')

            if data_type == 'text' or feature_type == 'string_embedding':
                result['text'].append(feature)
            elif data_type == 'numeric' or feature_type == 'numeric':
                result['numeric'].append(feature)
            elif data_type == 'temporal' or feature_type == 'timestamp':
                result['temporal'].append(feature)

        return result

    def _generate_header(self) -> str:
        """Generate file header with metadata from both configs."""
        buyer_cols = [f.get('column', '?') for f in self.buyer_features]
        product_cols = [f.get('column', '?') for f in self.product_features]

        # Format tower layers for header
        buyer_layer_summary = self._summarize_layers(self.buyer_tower_layers)
        product_layer_summary = self._summarize_layers(self.product_tower_layers)

        return f'''# Auto-generated TFX Trainer Module
# FeatureConfig: "{self.feature_config.name}" (ID: {self.feature_config.id})
# ModelConfig: "{self.model_config.name}" (ID: {self.model_config.id})
# Generated at: {datetime.utcnow().isoformat()}Z
#
# === Feature Configuration ===
# BuyerModel features: {', '.join(buyer_cols) if buyer_cols else 'none'}
# ProductModel features: {', '.join(product_cols) if product_cols else 'none'}
# Buyer crosses: {len(self.buyer_crosses)}
# Product crosses: {len(self.product_crosses)}
#
# === Model Architecture ===
# Buyer tower: {buyer_layer_summary}
# Product tower: {product_layer_summary}
# Output embedding dim: {self.output_embedding_dim}
#
# === Training Configuration ===
# Optimizer: {self.optimizer} (lr={self.learning_rate})
# Batch size: {self.batch_size}
# Epochs: {self.epochs}
# Retrieval: {self.retrieval_algorithm} (top_k={self.top_k})
#
# This module is designed for TFX Trainer component.
# It loads Transform artifacts and creates a two-tower TFRS retrieval model.
'''

    def _summarize_layers(self, layers: List[Dict]) -> str:
        """Summarize layer configuration for header comment."""
        if not layers:
            return 'none'

        parts = []
        for layer in layers:
            layer_type = layer.get('type', 'unknown')
            if layer_type == 'dense':
                units = layer.get('units', '?')
                parts.append(f"Dense({units})")
            elif layer_type == 'dropout':
                rate = layer.get('rate', '?')
                parts.append(f"Dropout({rate})")
            elif layer_type == 'batch_norm':
                parts.append("BatchNorm")
            elif layer_type == 'layer_norm':
                parts.append("LayerNorm")
            else:
                parts.append(layer_type)

        return ' → '.join(parts) if parts else 'none'

    def _generate_imports(self) -> str:
        """Generate import statements."""
        return '''import os
import json
import glob
from typing import Dict, List, Text

import tensorflow as tf
import tensorflow_transform as tft
import tensorflow_recommenders as tfrs

from tfx import v1 as tfx
from tfx.types import artifact_utils
from tfx_bsl.public import tfxio

from absl import logging

# MLflow tracking via direct REST API (no mlflow library needed - zero dependencies)
# Includes GCP identity token authentication for Cloud Run services
import time
import urllib.request
import urllib.error
import urllib.parse

class MLflowRestClient:
    """Lightweight MLflow client using REST API with GCP identity token auth."""

    def __init__(self, tracking_uri):
        self.tracking_uri = tracking_uri.rstrip('/')
        self.run_id = None
        self.experiment_id = None
        self._token = None
        self._token_expiry = 0

    def _get_identity_token(self):
        """
        Fetch identity token for Cloud Run service authentication.

        Uses GCP metadata server (available on all GCP compute).
        Tokens are cached for ~1 hour and auto-refreshed.
        """
        # Return cached token if still valid (with 60s buffer)
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        # Method 1: Try google-auth library (preferred, handles token refresh)
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token
            auth_req = google.auth.transport.requests.Request()
            self._token = google.oauth2.id_token.fetch_id_token(auth_req, self.tracking_uri)
            self._token_expiry = time.time() + 3600
            logging.info("MLflow: Got identity token via google-auth")
            return self._token
        except ImportError:
            pass  # google-auth not available, try metadata server
        except Exception as e:
            logging.debug(f"MLflow: google-auth failed ({e}), trying metadata server")

        # Method 2: GCP metadata server (always available on Vertex AI)
        try:
            audience = self.tracking_uri
            url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={urllib.parse.quote(audience)}"
            req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._token = resp.read().decode()
                self._token_expiry = time.time() + 3600
                logging.info("MLflow: Got identity token via metadata server")
                return self._token
        except Exception as e:
            logging.warning(f"MLflow: Could not get identity token: {e}")
            return None

    def _get_auth_headers(self):
        """Get headers with authentication for API requests."""
        headers = {"Content-Type": "application/json"}
        token = self._get_identity_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, endpoint, data, timeout=30):
        """Make authenticated POST request to MLflow API with retry."""
        url = f"{self.tracking_uri}/api/2.0/mlflow/{endpoint}"
        headers = self._get_auth_headers()
        last_error = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                logging.warning(f"MLflow API error ({endpoint}): HTTP {e.code} - {e.reason}")
                return None  # Don't retry HTTP errors
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = (attempt + 1) * 5  # 5s, 10s
                    logging.info(f"MLflow request failed ({e}), retrying in {wait}s...")
                    time.sleep(wait)
        logging.warning(f"MLflow API error ({endpoint}): {last_error}")
        return None

    def set_experiment(self, name):
        """Get or create experiment by name with retry for cold starts."""
        logging.info(f"MLFLOW: Setting experiment '{name}'")
        last_error = None

        for attempt in range(3):
            try:
                url = f"{self.tracking_uri}/api/2.0/mlflow/experiments/get-by-name?experiment_name={urllib.parse.quote(name)}"
                headers = self._get_auth_headers()
                req = urllib.request.Request(url, headers=headers)
                # Use 60s timeout on first attempt (cold start), 30s after
                timeout = 60 if attempt == 0 else 30

                logging.info(f"  Attempt {attempt + 1}/3: Looking up experiment...")
                request_start = time.time()
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    request_time = time.time() - request_start
                    result = json.loads(resp.read().decode())
                    self.experiment_id = result.get("experiment", {}).get("experiment_id")
                    logging.info(f"  Found existing experiment: id={self.experiment_id} ({request_time:.2f}s)")
                    return self.experiment_id

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    # Create new experiment
                    logging.info(f"  Experiment not found, creating new one...")
                    result = self._request("experiments/create", {"name": name}, timeout=60)
                    if result:
                        self.experiment_id = result.get("experiment_id")
                        logging.info(f"  Created new experiment: id={self.experiment_id}")
                    else:
                        logging.error(f"  Failed to create experiment")
                    return self.experiment_id
                logging.warning(f"  HTTP Error: {e.code} - {e.reason}")
                return None

            except Exception as e:
                last_error = e
                logging.warning(f"  Attempt {attempt + 1} failed: {type(e).__name__}: {e}")
                if attempt < 2:
                    wait = (attempt + 1) * 10  # 10s, 20s backoff
                    logging.info(f"  Retrying in {wait}s...")
                    time.sleep(wait)

        logging.error(f"MLFLOW: set_experiment FAILED after 3 attempts: {last_error}")
        return None

    def start_run(self, run_name=None):
        """Start a new run."""
        logging.info(f"MLFLOW: Starting run")
        logging.info(f"  Experiment ID: {self.experiment_id}")
        logging.info(f"  Run name: {run_name}")

        if not self.experiment_id:
            logging.error("  Cannot start run: experiment_id is None")
            return None

        data = {"experiment_id": self.experiment_id}
        if run_name:
            data["run_name"] = run_name

        result = self._request("runs/create", data)
        if result:
            self.run_id = result.get("run", {}).get("info", {}).get("run_id")
            logging.info(f"  Run started successfully: {self.run_id}")
        else:
            logging.error(f"  Failed to start run - no response from server")

        return self.run_id

    def log_param(self, key, value):
        """Log a parameter."""
        if self.run_id:
            self._request("runs/log-parameter", {"run_id": self.run_id, "key": key, "value": str(value)})

    def log_params(self, params):
        """Log multiple parameters."""
        for key, value in params.items():
            self.log_param(key, value)

    def log_metric(self, key, value, step=None):
        """Log a metric."""
        if self.run_id:
            data = {"run_id": self.run_id, "key": key, "value": float(value), "timestamp": int(time.time() * 1000)}
            if step is not None:
                data["step"] = step
            self._request("runs/log-metric", data)

    def set_tag(self, key, value):
        """Set a tag."""
        if self.run_id:
            self._request("runs/set-tag", {"run_id": self.run_id, "key": key, "value": str(value)})

    def set_tags(self, tags):
        """Set multiple tags."""
        for key, value in tags.items():
            self.set_tag(key, value)

    def end_run(self, status="FINISHED"):
        """End the run."""
        if self.run_id:
            self._request("runs/update", {"run_id": self.run_id, "status": status, "end_time": int(time.time() * 1000)})

    def wait_for_ready(self, max_wait_seconds=120):
        """
        Wait for MLflow server to be ready (handles cold starts).

        Pings the health endpoint with exponential backoff until the server
        responds. This ensures the server is fully initialized before
        attempting any MLflow operations.

        Args:
            max_wait_seconds: Maximum time to wait for server (default 120s)

        Returns:
            True if server is ready

        Raises:
            RuntimeError if server is not ready after max_wait_seconds
        """
        health_url = f"{self.tracking_uri}/health"
        start_time = time.time()
        attempt = 0

        logging.info("-" * 50)
        logging.info("MLFLOW CONNECTION: Starting server health check")
        logging.info(f"  Server URL: {self.tracking_uri}")
        logging.info(f"  Health endpoint: {health_url}")
        logging.info(f"  Max wait time: {max_wait_seconds}s")
        logging.info("-" * 50)

        while (time.time() - start_time) < max_wait_seconds:
            attempt += 1
            elapsed = time.time() - start_time
            remaining = max_wait_seconds - elapsed

            logging.info(f"MLFLOW CONNECTION: Attempt {attempt}")
            logging.info(f"  Elapsed: {elapsed:.1f}s | Remaining: {remaining:.1f}s")

            try:
                # Get auth token
                logging.info("  Getting authentication token...")
                headers = self._get_auth_headers()
                has_auth = "Authorization" in headers
                logging.info(f"  Auth token obtained: {has_auth}")

                req = urllib.request.Request(health_url, headers=headers)
                # Use longer timeout for cold start (first attempt)
                timeout = 60 if attempt == 1 else 30
                logging.info(f"  Sending health check request (timeout={timeout}s)...")

                request_start = time.time()
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    request_time = time.time() - request_start
                    total_elapsed = time.time() - start_time
                    logging.info(f"  Response received: HTTP {resp.status}")
                    logging.info(f"  Request time: {request_time:.2f}s")
                    logging.info("-" * 50)
                    logging.info(f"MLFLOW CONNECTION: SUCCESS after {total_elapsed:.1f}s ({attempt} attempts)")
                    logging.info("-" * 50)
                    return True

            except urllib.error.HTTPError as e:
                request_time = time.time() - request_start if 'request_start' in dir() else 0
                logging.warning(f"  HTTP Error: {e.code} - {e.reason}")
                logging.warning(f"  Request time: {request_time:.2f}s")

                # Server responded but with error - still means it's up
                if e.code in (401, 403):
                    logging.warning(f"  Server is UP but has authentication issues")
                    logging.warning(f"  This may indicate IAM permission problems")
                    return True
                elif e.code >= 500:
                    logging.warning(f"  Server error (5xx) - may be starting up")

            except urllib.error.URLError as e:
                logging.warning(f"  Connection failed: {e.reason}")
                if "timed out" in str(e.reason).lower():
                    logging.warning(f"  TIMEOUT - Server may be experiencing cold start")
                elif "refused" in str(e.reason).lower():
                    logging.warning(f"  CONNECTION REFUSED - Server may not be running")
                elif "name or service not known" in str(e.reason).lower():
                    logging.error(f"  DNS RESOLUTION FAILED - Check server URL")

            except Exception as e:
                logging.warning(f"  Unexpected error: {type(e).__name__}: {e}")

            # Exponential backoff: 5s, 10s, 15s, 20s, then cap at 20s
            wait_time = min(20, 5 * attempt)
            if (time.time() - start_time + wait_time) < max_wait_seconds:
                logging.info(f"  Waiting {wait_time}s before next attempt...")
                time.sleep(wait_time)
            else:
                logging.warning(f"  No time remaining for another attempt")
                break

        # Final failure
        total_elapsed = time.time() - start_time
        logging.error("-" * 50)
        logging.error("MLFLOW CONNECTION: FAILED")
        logging.error(f"  Total time: {total_elapsed:.1f}s")
        logging.error(f"  Attempts: {attempt}")
        logging.error(f"  Server URL: {self.tracking_uri}")
        logging.error("-" * 50)

        raise RuntimeError(
            f"MLflow server not ready after {total_elapsed:.0f}s ({attempt} attempts). "
            f"Training cannot proceed without MLflow tracking. "
            f"Server URL: {self.tracking_uri}. "
            f"Check Cloud Run logs for mlflow-server service."
        )

# Global MLflow client instance (initialized in run_fn)
_mlflow_client = None
MLFLOW_AVAILABLE = True  # Always available - uses REST API with no dependencies
'''

    def _generate_constants(self) -> str:
        """Generate module constants from ModelConfig."""
        # Extract L2 regularization from layers (use first dense layer's l2_reg or default)
        l2_reg = 0.0
        for layer in self.buyer_tower_layers:
            if layer.get('type') == 'dense' and 'l2_reg' in layer:
                l2_reg = layer.get('l2_reg', 0.0)
                break

        # Get model endpoint name for MLflow experiment
        model_endpoint_name = self.feature_config.dataset.model_endpoint.name

        return f'''
# =============================================================================
# CONFIGURATION (from ModelConfig: "{self.model_config.name}")
# =============================================================================

# Training hyperparameters
LEARNING_RATE = {self.learning_rate}
EPOCHS = {self.epochs}
BATCH_SIZE = {self.batch_size}

# Output embedding dimension (must match between towers)
OUTPUT_EMBEDDING_DIM = {self.output_embedding_dim}

# Regularization
L2_REGULARIZATION = {l2_reg}

# Retrieval configuration
TOP_K = {self.top_k}

# OOV buckets (must match Transform preprocessing)
NUM_OOV_BUCKETS = 1

# =============================================================================
# MLFLOW CONFIGURATION
# =============================================================================

MLFLOW_TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', '')
MLFLOW_EXPERIMENT_NAME = '{model_endpoint_name}'
MLFLOW_RUN_NAME = os.environ.get('MLFLOW_RUN_NAME', 'quick-test')
'''

    def _generate_input_fn(self) -> str:
        """Generate _input_fn for loading transformed data."""
        return '''
# =============================================================================
# DATA LOADING
# =============================================================================

def _input_fn(
    file_pattern: List[Text],
    data_accessor: tfx.components.DataAccessor,
    tf_transform_output: tft.TFTransformOutput,
    batch_size: int = BATCH_SIZE
) -> tf.data.Dataset:
    """
    Load transformed data from TFRecords.

    Args:
        file_pattern: List of paths to TFRecord files
        data_accessor: TFX DataAccessor for reading data
        tf_transform_output: Transform output with schema
        batch_size: Batch size for training

    Returns:
        tf.data.Dataset with transformed features
    """
    return data_accessor.tf_dataset_factory(
        file_pattern,
        tfxio.TensorFlowDatasetOptions(batch_size=batch_size, num_epochs=1),
        tf_transform_output.transformed_metadata.schema
    )
'''

    def _generate_buyer_model(self, features_by_type: Dict[str, List[Dict]]) -> str:
        """
        Generate BuyerModel class (Query Tower).

        Args:
            features_by_type: Features organized by type (text, numeric, temporal)

        Returns:
            Python code string for BuyerModel class
        """
        lines = [
            '',
            '# =============================================================================',
            '# BUYER MODEL (Query Tower)',
            '# =============================================================================',
            '',
            'class BuyerModel(tf.keras.Model):',
            '    """',
            '    Query tower for buyer/user features.',
            '    ',
            '    Loads vocabularies from Transform and creates embeddings.',
            '    Concatenates all feature representations into a single vector.',
            '    """',
            '',
            '    def __init__(self, tf_transform_output: tft.TFTransformOutput):',
            '        super().__init__()',
            '        self.tf_transform_output = tf_transform_output',
            '',
        ]

        # Generate embedding layers for text features
        for feature in features_by_type['text']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            if transforms.get('embedding', {}).get('embedding_dim'):
                embed_dim = transforms['embedding']['embedding_dim']
            else:
                embed_dim = feature.get('embedding_dim', 32)

            lines.append(f"        # {col}: vocab index → embedding ({embed_dim}D)")
            lines.append(f"        # Transform already converted text to indices via tft.compute_and_apply_vocabulary")
            lines.append(f"        {col}_vocab_size = tf_transform_output.vocabulary_size_by_name('{col}_vocab')")
            lines.append(f"        self.{col}_embedding = tf.keras.layers.Embedding({col}_vocab_size + NUM_OOV_BUCKETS, {embed_dim})")
            lines.append('')

        # Generate embedding layers for numeric bucket features
        for feature in features_by_type['numeric']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            bucketize = transforms.get('bucketize', {})

            if bucketize.get('enabled'):
                buckets = bucketize.get('buckets', 100)
                embed_dim = bucketize.get('embedding_dim', 32)
                lines.append(f"        # {col}: bucket index → embedding ({embed_dim}D)")
                lines.append(f"        self.{col}_bucket_embedding = tf.keras.layers.Embedding({buckets + 1}, {embed_dim})")
                lines.append('')

        # Generate embedding layers for temporal bucket features
        for feature in features_by_type['temporal']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            bucketize = transforms.get('bucketize', {})

            if bucketize.get('enabled'):
                buckets = bucketize.get('buckets', 100)
                embed_dim = bucketize.get('embedding_dim', 32)
                lines.append(f"        # {col}: bucket index → embedding ({embed_dim}D)")
                lines.append(f"        self.{col}_bucket_embedding = tf.keras.layers.Embedding({buckets + 1}, {embed_dim})")
                lines.append('')

        # Generate embedding layers for cross features
        for cross in self.buyer_crosses:
            features = cross.get('features', [])
            hash_buckets = cross.get('hash_bucket_size', 5000)
            embed_dim = cross.get('embedding_dim', 16)

            # Build cross name
            if isinstance(features[0], dict):
                feature_names = [f.get('column', '') for f in features]
            else:
                feature_names = features
            cross_name = '_x_'.join(feature_names) + '_cross'

            lines.append(f"        # {' × '.join(feature_names)}: cross → embedding ({embed_dim}D)")
            lines.append(f"        self.{cross_name}_embedding = tf.keras.layers.Embedding({hash_buckets}, {embed_dim})")
            lines.append('')

        # Generate call method
        lines.append('    def call(self, inputs):')
        lines.append('        """Concatenate all feature embeddings."""')
        lines.append('        features = []')
        lines.append('')

        # Text features - use vocab index from transform
        for feature in features_by_type['text']:
            col = feature.get('column')
            lines.append(f"        # {col}: lookup embedding from vocab index")
            lines.append(f"        features.append(self.{col}_embedding(inputs['{col}']))")
            lines.append('')

        # Numeric features - normalized value + optional bucket embedding
        for feature in features_by_type['numeric']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            normalize = transforms.get('normalize', {})
            bucketize = transforms.get('bucketize', {})

            if normalize.get('enabled'):
                lines.append(f"        # {col}: normalized value (1D)")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_norm'], (-1, 1)))")

            if bucketize.get('enabled'):
                lines.append(f"        # {col}: bucket embedding")
                lines.append(f"        features.append(self.{col}_bucket_embedding(inputs['{col}_bucket']))")
            lines.append('')

        # Temporal features - normalized + cyclical + optional bucket
        for feature in features_by_type['temporal']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            normalize = transforms.get('normalize', {})
            cyclical = transforms.get('cyclical', {})
            bucketize = transforms.get('bucketize', {})

            if normalize.get('enabled'):
                lines.append(f"        # {col}: normalized value (1D)")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_norm'], (-1, 1)))")

            # Cyclical features
            cyclical_opts = []
            if cyclical.get('enabled') or cyclical.get('yearly') or cyclical.get('weekly'):
                for cycle in ['yearly', 'quarterly', 'monthly', 'weekly', 'daily']:
                    if cyclical.get(cycle):
                        cyclical_opts.append(cycle)
            if cyclical.get('annual'):
                cyclical_opts.append('yearly')

            for cycle in cyclical_opts:
                lines.append(f"        # {col}: {cycle} cyclical (sin/cos)")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_{cycle}_sin'], (-1, 1)))")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_{cycle}_cos'], (-1, 1)))")

            if bucketize.get('enabled'):
                lines.append(f"        # {col}: bucket embedding")
                lines.append(f"        features.append(self.{col}_bucket_embedding(inputs['{col}_bucket']))")
            lines.append('')

        # Cross features
        for cross in self.buyer_crosses:
            features = cross.get('features', [])
            if isinstance(features[0], dict):
                feature_names = [f.get('column', '') for f in features]
            else:
                feature_names = features
            cross_name = '_x_'.join(feature_names) + '_cross'

            lines.append(f"        # {' × '.join(feature_names)}: cross embedding")
            lines.append(f"        features.append(self.{cross_name}_embedding(inputs['{cross_name}']))")
            lines.append('')

        # Flatten embeddings from [batch, 1, dim] to [batch, dim] before concatenating
        lines.append('        # Flatten embeddings to [batch, dim] for concatenation')
        lines.append('        # Use squeeze for 3D tensors to preserve static shape (required for tf.data.Dataset.map)')
        lines.append('        flattened = [tf.squeeze(f, axis=1) if len(f.shape) == 3 else f for f in features]')
        lines.append('        return tf.concat(flattened, axis=1)')
        lines.append('')

        return '\n'.join(lines)

    def _generate_product_model(self, features_by_type: Dict[str, List[Dict]]) -> str:
        """
        Generate ProductModel class (Candidate Tower).

        Args:
            features_by_type: Features organized by type (text, numeric, temporal)

        Returns:
            Python code string for ProductModel class
        """
        lines = [
            '',
            '# =============================================================================',
            '# PRODUCT MODEL (Candidate Tower)',
            '# =============================================================================',
            '',
            'class ProductModel(tf.keras.Model):',
            '    """',
            '    Candidate tower for product/item features.',
            '    ',
            '    Loads vocabularies from Transform and creates embeddings.',
            '    Concatenates all feature representations into a single vector.',
            '    """',
            '',
            '    def __init__(self, tf_transform_output: tft.TFTransformOutput):',
            '        super().__init__()',
            '        self.tf_transform_output = tf_transform_output',
            '',
        ]

        # Generate embedding layers for text features
        for feature in features_by_type['text']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            if transforms.get('embedding', {}).get('embedding_dim'):
                embed_dim = transforms['embedding']['embedding_dim']
            else:
                embed_dim = feature.get('embedding_dim', 32)

            lines.append(f"        # {col}: vocab index → embedding ({embed_dim}D)")
            lines.append(f"        # Transform already converted text to indices via tft.compute_and_apply_vocabulary")
            lines.append(f"        {col}_vocab_size = tf_transform_output.vocabulary_size_by_name('{col}_vocab')")
            lines.append(f"        self.{col}_embedding = tf.keras.layers.Embedding({col}_vocab_size + NUM_OOV_BUCKETS, {embed_dim})")
            lines.append('')

        # Generate embedding layers for numeric bucket features
        for feature in features_by_type['numeric']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            bucketize = transforms.get('bucketize', {})

            if bucketize.get('enabled'):
                buckets = bucketize.get('buckets', 100)
                embed_dim = bucketize.get('embedding_dim', 32)
                lines.append(f"        # {col}: bucket index → embedding ({embed_dim}D)")
                lines.append(f"        self.{col}_bucket_embedding = tf.keras.layers.Embedding({buckets + 1}, {embed_dim})")
                lines.append('')

        # Generate embedding layers for temporal bucket features
        for feature in features_by_type['temporal']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            bucketize = transforms.get('bucketize', {})

            if bucketize.get('enabled'):
                buckets = bucketize.get('buckets', 100)
                embed_dim = bucketize.get('embedding_dim', 32)
                lines.append(f"        # {col}: bucket index → embedding ({embed_dim}D)")
                lines.append(f"        self.{col}_bucket_embedding = tf.keras.layers.Embedding({buckets + 1}, {embed_dim})")
                lines.append('')

        # Generate embedding layers for cross features
        for cross in self.product_crosses:
            features = cross.get('features', [])
            hash_buckets = cross.get('hash_bucket_size', 5000)
            embed_dim = cross.get('embedding_dim', 16)

            if isinstance(features[0], dict):
                feature_names = [f.get('column', '') for f in features]
            else:
                feature_names = features
            cross_name = '_x_'.join(feature_names) + '_cross'

            lines.append(f"        # {' × '.join(feature_names)}: cross → embedding ({embed_dim}D)")
            lines.append(f"        self.{cross_name}_embedding = tf.keras.layers.Embedding({hash_buckets}, {embed_dim})")
            lines.append('')

        # Generate call method
        lines.append('    def call(self, inputs):')
        lines.append('        """Concatenate all feature embeddings."""')
        lines.append('        features = []')
        lines.append('')

        # Text features
        for feature in features_by_type['text']:
            col = feature.get('column')
            lines.append(f"        # {col}: lookup embedding from vocab index")
            lines.append(f"        features.append(self.{col}_embedding(inputs['{col}']))")
            lines.append('')

        # Numeric features
        for feature in features_by_type['numeric']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            normalize = transforms.get('normalize', {})
            bucketize = transforms.get('bucketize', {})

            if normalize.get('enabled'):
                lines.append(f"        # {col}: normalized value (1D)")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_norm'], (-1, 1)))")

            if bucketize.get('enabled'):
                lines.append(f"        # {col}: bucket embedding")
                lines.append(f"        features.append(self.{col}_bucket_embedding(inputs['{col}_bucket']))")
            lines.append('')

        # Temporal features
        for feature in features_by_type['temporal']:
            col = feature.get('column')
            transforms = feature.get('transforms', {})
            normalize = transforms.get('normalize', {})
            cyclical = transforms.get('cyclical', {})
            bucketize = transforms.get('bucketize', {})

            if normalize.get('enabled'):
                lines.append(f"        # {col}: normalized value (1D)")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_norm'], (-1, 1)))")

            cyclical_opts = []
            if cyclical.get('enabled') or cyclical.get('yearly') or cyclical.get('weekly'):
                for cycle in ['yearly', 'quarterly', 'monthly', 'weekly', 'daily']:
                    if cyclical.get(cycle):
                        cyclical_opts.append(cycle)
            if cyclical.get('annual'):
                cyclical_opts.append('yearly')

            for cycle in cyclical_opts:
                lines.append(f"        # {col}: {cycle} cyclical (sin/cos)")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_{cycle}_sin'], (-1, 1)))")
                lines.append(f"        features.append(tf.reshape(inputs['{col}_{cycle}_cos'], (-1, 1)))")

            if bucketize.get('enabled'):
                lines.append(f"        # {col}: bucket embedding")
                lines.append(f"        features.append(self.{col}_bucket_embedding(inputs['{col}_bucket']))")
            lines.append('')

        # Cross features
        for cross in self.product_crosses:
            features = cross.get('features', [])
            if isinstance(features[0], dict):
                feature_names = [f.get('column', '') for f in features]
            else:
                feature_names = features
            cross_name = '_x_'.join(feature_names) + '_cross'

            lines.append(f"        # {' × '.join(feature_names)}: cross embedding")
            lines.append(f"        features.append(self.{cross_name}_embedding(inputs['{cross_name}']))")
            lines.append('')

        # Flatten embeddings from [batch, 1, dim] to [batch, dim] before concatenating
        lines.append('        # Flatten embeddings to [batch, dim] for concatenation')
        lines.append('        # Use squeeze for 3D tensors to preserve static shape (required for tf.data.Dataset.map)')
        lines.append('        flattened = [tf.squeeze(f, axis=1) if len(f.shape) == 3 else f for f in features]')
        lines.append('        return tf.concat(flattened, axis=1)')
        lines.append('')

        return '\n'.join(lines)

    def _generate_retrieval_model(self) -> str:
        """Generate RetrievalModel class with configurable tower architecture."""
        # Generate layer code for each tower
        buyer_layers_code = self._generate_tower_layers_code(self.buyer_tower_layers, 'query')
        product_layers_code = self._generate_tower_layers_code(self.product_tower_layers, 'candidate')

        return f'''
# =============================================================================
# RETRIEVAL MODEL (TFRS Two-Tower)
# =============================================================================

class RetrievalModel(tfrs.Model):
    """
    Two-tower retrieval model using TensorFlow Recommenders.

    Query tower (BuyerModel) processes buyer/user features.
    Candidate tower (ProductModel) processes product/item features.
    Configurable dense/dropout/batchnorm layers project both to embedding space.
    Final output dimension: {self.output_embedding_dim}
    """

    def __init__(
        self,
        tf_transform_output: tft.TFTransformOutput
    ):
        super().__init__()

        # Feature extraction models
        self.buyer_model = BuyerModel(tf_transform_output)
        self.product_model = ProductModel(tf_transform_output)

        # Query tower: BuyerModel → Configurable layers
        query_layers = [self.buyer_model]
{buyer_layers_code}
        self.query_tower = tf.keras.Sequential(query_layers)

        # Candidate tower: ProductModel → Configurable layers
        candidate_layers = [self.product_model]
{product_layers_code}
        self.candidate_tower = tf.keras.Sequential(candidate_layers)

        # TFRS Retrieval task (without FactorizedTopK metrics during training)
        # FactorizedTopK requires pre-computed embeddings which causes serialization issues
        # with tf.data.Dataset.map() due to stateful Embedding layers
        self.task = tfrs.tasks.Retrieval()

    def compute_loss(self, features: Dict[Text, tf.Tensor], training: bool = False) -> tf.Tensor:
        """Compute retrieval loss."""
        query_embeddings = self.query_tower(features)
        candidate_embeddings = self.candidate_tower(features)
        return self.task(query_embeddings, candidate_embeddings)
'''

    def _generate_tower_layers_code(self, layers: List[Dict], tower_name: str) -> str:
        """
        Generate code for tower layers from ModelConfig layer specification.

        Args:
            layers: List of layer configurations from ModelConfig
            tower_name: 'query' or 'candidate' for variable naming

        Returns:
            Python code string for layer construction
        """
        if not layers:
            # Default fallback if no layers configured
            return f'''        # Default layers (no custom layers configured)
        {tower_name}_layers.append(tf.keras.layers.Dense(64, activation='relu'))
        {tower_name}_layers.append(tf.keras.layers.Dense(OUTPUT_EMBEDDING_DIM))'''

        lines = []
        var_name = f"{tower_name}_layers"

        for i, layer in enumerate(layers):
            layer_type = layer.get('type', 'dense')

            if layer_type == 'dense':
                units = layer.get('units', 64)
                activation = layer.get('activation', 'relu')
                l1_reg = layer.get('l1_reg', 0.0)
                l2_reg = layer.get('l2_reg', 0.0)

                # Handle activation - last layer may have None
                if activation and activation.lower() != 'none':
                    activation_str = f"activation='{activation}'"
                else:
                    activation_str = "activation=None"

                # Handle regularization: L1, L2, or L1+L2 (elastic net)
                has_l1 = l1_reg and l1_reg > 0
                has_l2 = l2_reg and l2_reg > 0

                if has_l1 and has_l2:
                    # Combined L1+L2 regularization (elastic net)
                    reg_str = f", kernel_regularizer=tf.keras.regularizers.l1_l2(l1={l1_reg}, l2={l2_reg})"
                elif has_l1:
                    reg_str = f", kernel_regularizer=tf.keras.regularizers.l1({l1_reg})"
                elif has_l2:
                    reg_str = f", kernel_regularizer=tf.keras.regularizers.l2({l2_reg})"
                else:
                    reg_str = ""

                lines.append(f"        {var_name}.append(tf.keras.layers.Dense({units}, {activation_str}{reg_str}))")

            elif layer_type == 'dropout':
                rate = layer.get('rate', 0.2)
                lines.append(f"        {var_name}.append(tf.keras.layers.Dropout({rate}))")

            elif layer_type == 'batch_norm':
                lines.append(f"        {var_name}.append(tf.keras.layers.BatchNormalization())")

            elif layer_type == 'layer_norm':
                epsilon = layer.get('epsilon', 1e-6)
                lines.append(f"        {var_name}.append(tf.keras.layers.LayerNormalization(epsilon={epsilon}))")

        # Add final projection layer to output_embedding_dim if not already matching
        # Check if last dense layer already outputs the correct dim
        last_dense_units = None
        for layer in reversed(layers):
            if layer.get('type') == 'dense':
                last_dense_units = layer.get('units')
                break

        if last_dense_units != self.output_embedding_dim:
            lines.append(f"        # Final projection to output embedding dimension")
            lines.append(f"        {var_name}.append(tf.keras.layers.Dense(OUTPUT_EMBEDDING_DIM))")

        return '\n'.join(lines)

    def _generate_serve_fn(self) -> str:
        """Generate serving function for inference."""
        # Get primary product ID column for candidate indexing
        product_id_col = None
        for feature in self.product_features:
            col = feature.get('column', '')
            if 'product' in col.lower() or 'item' in col.lower() or 'sku' in col.lower():
                product_id_col = col
                break

        if not product_id_col and self.product_features:
            product_id_col = self.product_features[0].get('column', 'product_id')

        return f'''
# =============================================================================
# SERVING FUNCTION
# =============================================================================

class ServingModel(tf.keras.Model):
    """
    Wrapper model for serving that properly tracks all TFX Transform resources.

    This class ensures that vocabulary hash tables and other TFT resources
    are tracked by the model and saved correctly.
    """

    def __init__(self, retrieval_model, tf_transform_output, product_ids, product_embeddings):
        super().__init__()
        # Track the retrieval model
        self.retrieval_model = retrieval_model

        # Track the TFT layer (contains vocabulary hash tables)
        self.tft_layer = tf_transform_output.transform_features_layer()

        # Store feature spec for parsing
        self._raw_feature_spec = tf_transform_output.raw_feature_spec()

        # Track product data as model variables
        self.product_ids = tf.Variable(product_ids, trainable=False, name='product_ids')
        self.product_embeddings = tf.Variable(product_embeddings, trainable=False, name='product_embeddings')

    @tf.function(input_signature=[
        tf.TensorSpec(shape=[None], dtype=tf.string, name='examples')
    ])
    def serve(self, serialized_examples):
        """
        Serving function that accepts serialized tf.Examples.

        Returns top-100 product recommendations with scores.
        """
        # Parse raw features
        parsed_features = tf.io.parse_example(serialized_examples, self._raw_feature_spec)

        # Apply transform preprocessing
        transformed_features = self.tft_layer(parsed_features)

        # Get query embeddings
        query_embeddings = self.retrieval_model.query_tower(transformed_features)

        # Compute similarities with all candidates
        similarities = tf.linalg.matmul(
            query_embeddings,
            self.product_embeddings,
            transpose_b=True
        )

        # Get top-100 recommendations
        top_scores, top_indices = tf.nn.top_k(similarities, k=100)

        # Map indices to product IDs
        recommended_products = tf.gather(self.product_ids, top_indices)

        return {{
            'product_ids': recommended_products,
            'scores': top_scores
        }}


def _precompute_candidate_embeddings(model, candidates_dataset, batch_size=128):
    """
    Pre-compute embeddings for all candidates.

    Args:
        model: RetrievalModel with candidate_tower
        candidates_dataset: Dataset of candidate features
        batch_size: Batch size for embedding computation

    Returns:
        Tuple of (product_ids, embeddings tensor)
    """
    product_ids = []
    embeddings = []

    for batch in candidates_dataset.batch(batch_size):
        # Get product ID from batch
        if '{product_id_col}' in batch:
            batch_ids = batch['{product_id_col}'].numpy()
            if hasattr(batch_ids[0], 'decode'):
                batch_ids = [b.decode() for b in batch_ids]
            product_ids.extend(batch_ids)

        # Compute embeddings
        batch_embeddings = model.candidate_tower(batch)
        embeddings.append(batch_embeddings)

    return product_ids, tf.concat(embeddings, axis=0)


def _evaluate_recall_on_test_set(model, test_dataset, product_ids, product_embeddings, steps=50):
    """
    Evaluate recall@k metrics on the test set.

    Args:
        model: The trained retrieval model
        test_dataset: TF dataset for test examples
        product_ids: List of all product IDs
        product_embeddings: Pre-computed embeddings for all products
        steps: Number of batches to evaluate

    Returns:
        Dict with recall metrics
    """
    logging.info("=" * 60)
    logging.info("EVALUATING RECALL ON TEST SET")
    logging.info("=" * 60)

    # Create product ID to index mapping
    product_to_idx = {{pid: i for i, pid in enumerate(product_ids)}}

    # Initialize counters
    total_recall_5 = 0.0
    total_recall_10 = 0.0
    total_recall_50 = 0.0
    total_recall_100 = 0.0
    total_batches = 0

    try:
        for batch in test_dataset.take(steps):
            # Get query embeddings for this batch
            query_embeddings = model.query_tower(batch)

            # Compute similarities with all candidates
            # query_embeddings: [batch_size, embedding_dim]
            # product_embeddings: [num_products, embedding_dim]
            similarities = tf.linalg.matmul(
                query_embeddings,
                product_embeddings,
                transpose_b=True
            )  # [batch_size, num_products]

            # Get top-100 indices
            _, top_indices = tf.nn.top_k(similarities, k=min(100, len(product_ids)))
            top_indices = top_indices.numpy()

            # Get actual product IDs from batch
            if '{product_id_col}' in batch:
                actual_products = batch['{product_id_col}'].numpy()
                if hasattr(actual_products[0], 'decode'):
                    actual_products = [p.decode() for p in actual_products]
            else:
                continue

            batch_size = len(actual_products)

            # Calculate recall for each K
            for k in [5, 10, 50, 100]:
                hits = 0
                for i in range(batch_size):
                    actual_product = actual_products[i]
                    if actual_product in product_to_idx:
                        actual_idx = product_to_idx[actual_product]
                        if actual_idx in top_indices[i, :k]:
                            hits += 1

                batch_recall = hits / batch_size
                if k == 5:
                    total_recall_5 += batch_recall
                elif k == 10:
                    total_recall_10 += batch_recall
                elif k == 50:
                    total_recall_50 += batch_recall
                elif k == 100:
                    total_recall_100 += batch_recall

            total_batches += 1

            if total_batches % 10 == 0:
                logging.info(f"  Evaluated {{total_batches}} batches...")

        if total_batches == 0:
            logging.warning("No batches evaluated for recall")
            return {{}}

        # Calculate final averages
        results = {{
            'recall_at_5': total_recall_5 / total_batches,
            'recall_at_10': total_recall_10 / total_batches,
            'recall_at_50': total_recall_50 / total_batches,
            'recall_at_100': total_recall_100 / total_batches,
        }}

        logging.info("=" * 60)
        logging.info("TEST SET RECALL RESULTS:")
        logging.info(f"  Recall@5:   {{results['recall_at_5']:.4f}} ({{results['recall_at_5']*100:.2f}}%)")
        logging.info(f"  Recall@10:  {{results['recall_at_10']:.4f}} ({{results['recall_at_10']*100:.2f}}%)")
        logging.info(f"  Recall@50:  {{results['recall_at_50']:.4f}} ({{results['recall_at_50']*100:.2f}}%)")
        logging.info(f"  Recall@100: {{results['recall_at_100']:.4f}} ({{results['recall_at_100']*100:.2f}}%)")
        logging.info(f"  Batches evaluated: {{total_batches}}")
        logging.info("=" * 60)

        return results

    except Exception as e:
        logging.error(f"Error evaluating recall: {{e}}")
        import traceback
        traceback.print_exc()
        return {{}}
'''

    def _generate_mlflow_callback(self) -> str:
        """Generate MLflow callback class for per-epoch metric logging."""
        return '''
# =============================================================================
# MLFLOW CALLBACK
# =============================================================================

class MLflowCallback(tf.keras.callbacks.Callback):
    """Log metrics to MLflow after each epoch using REST API."""

    def on_epoch_end(self, epoch, logs=None):
        if _mlflow_client and logs:
            for metric_name, value in logs.items():
                _mlflow_client.log_metric(metric_name, float(value), step=epoch)


def _write_mlflow_info(gcs_output_path: str, run_id: str):
    """Write MLflow run ID to GCS for Django to retrieve."""
    if not gcs_output_path or not gcs_output_path.startswith('gs://'):
        logging.warning(f"Cannot write MLflow info: invalid GCS path: {gcs_output_path}")
        return

    try:
        from google.cloud import storage

        path = gcs_output_path[5:]  # Remove 'gs://'
        bucket_name = path.split('/')[0]
        blob_path = '/'.join(path.split('/')[1:]) + '/mlflow_info.json'

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json.dumps({
            'run_id': run_id,
            'experiment_name': MLFLOW_EXPERIMENT_NAME,
        }))
        logging.info(f"Wrote MLflow info to gs://{bucket_name}/{blob_path}")
    except Exception as e:
        logging.warning(f"Could not write MLflow info: {e}")


def _write_mlflow_status(gcs_output_path: str, status: str, details: dict = None):
    """
    Write MLflow initialization status to GCS for Django diagnostics.

    This file is written at various stages of MLflow initialization so Django
    can understand exactly what happened if something goes wrong.

    Args:
        gcs_output_path: GCS path for artifacts (e.g., gs://bucket/qt-XX-YYYYMMDD-HHMMSS)
        status: One of 'starting', 'waiting', 'connected', 'ready', 'failed'
        details: Optional dict with additional status information
    """
    if not gcs_output_path or not gcs_output_path.startswith('gs://'):
        return

    try:
        from google.cloud import storage
        from datetime import datetime

        path = gcs_output_path[5:]  # Remove 'gs://'
        bucket_name = path.split('/')[0]
        blob_path = '/'.join(path.split('/')[1:]) + '/mlflow_status.json'

        status_data = {
            'status': status,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'tracking_uri': MLFLOW_TRACKING_URI,
        }
        if details:
            status_data.update(details)

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json.dumps(status_data, indent=2))

        logging.info(f"MLflow status [{status}] written to gs://{bucket_name}/{blob_path}")
    except Exception as e:
        logging.debug(f"Could not write MLflow status: {e}")
'''

    def _generate_run_fn(self) -> str:
        """Generate run_fn() - the TFX Trainer entry point with configurable optimizer and MLflow tracking."""
        # Get optimizer code
        optimizer_class = self.OPTIMIZER_CODE.get(self.optimizer, 'tf.keras.optimizers.Adam')

        # Get IDs for MLflow parameter logging
        feature_config_id = self.feature_config.id
        model_config_id = self.model_config.id
        dataset_id = self.feature_config.dataset.id
        feature_config_name = self.feature_config.name
        model_config_name = self.model_config.name
        dataset_name = self.feature_config.dataset.name
        model_type = self.model_config.model_type

        return f'''
# =============================================================================
# TFX TRAINER ENTRY POINT
# =============================================================================

def run_fn(fn_args: tfx.components.FnArgs):
    """
    TFX Trainer entry point with MLflow tracking.

    Args:
        fn_args: Training arguments from TFX including:
            - train_files: Training data paths
            - eval_files: Evaluation data paths
            - transform_output: Transform artifact path
            - serving_model_dir: Where to save the model
            - custom_config: Optional configuration overrides
    """
    logging.info("Starting TFX Trainer...")

    # Load Transform output
    tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)
    logging.info(f"Loaded Transform output from: {{fn_args.transform_output}}")

    # Get configuration from custom_config or use module defaults
    custom_config = fn_args.custom_config or {{}}
    epochs = custom_config.get('epochs', EPOCHS)
    learning_rate = custom_config.get('learning_rate', LEARNING_RATE)
    batch_size = custom_config.get('batch_size', BATCH_SIZE)
    gcs_output_path = custom_config.get('gcs_output_path', '')

    # MLflow tracking URI - prefer custom_config (for Vertex AI) over env var
    mlflow_tracking_uri = custom_config.get('mlflow_tracking_uri', MLFLOW_TRACKING_URI)

    logging.info(f"Training config: epochs={{epochs}}, lr={{learning_rate}}, batch={{batch_size}}")
    logging.info(f"Output embedding dim: {{OUTPUT_EMBEDDING_DIM}}")

    # Load datasets
    train_dataset = _input_fn(
        fn_args.train_files,
        fn_args.data_accessor,
        tf_transform_output,
        batch_size
    )

    eval_dataset = _input_fn(
        fn_args.eval_files,
        fn_args.data_accessor,
        tf_transform_output,
        batch_size
    )

    # =========================================================================
    # MLflow Initialization (MANDATORY - training will not proceed without it)
    # =========================================================================
    global _mlflow_client
    mlflow_run_id = None

    if not mlflow_tracking_uri:
        _write_mlflow_status(gcs_output_path, 'failed', {{
            'error': 'MLflow tracking URI not configured',
            'stage': 'config_check'
        }})
        raise RuntimeError(
            "MLflow tracking URI not configured. "
            "Training cannot proceed without experiment tracking. "
            "Set mlflow_tracking_uri in custom_config or MLFLOW_TRACKING_URI env var."
        )

    # Write initial status
    _write_mlflow_status(gcs_output_path, 'starting', {{
        'stage': 'initialization',
        'experiment_name': MLFLOW_EXPERIMENT_NAME,
        'run_name': MLFLOW_RUN_NAME
    }})

    # Step 1: Wait for MLflow server to be ready (handles cold starts)
    logging.info("=" * 60)
    logging.info("MLflow Initialization")
    logging.info("=" * 60)

    try:
        _mlflow_client = MLflowRestClient(mlflow_tracking_uri)

        _write_mlflow_status(gcs_output_path, 'waiting', {{
            'stage': 'health_check',
            'message': 'Waiting for MLflow server to be ready (may take up to 120s for cold start)'
        }})

        _mlflow_client.wait_for_ready(max_wait_seconds=120)

        _write_mlflow_status(gcs_output_path, 'connected', {{
            'stage': 'server_ready',
            'message': 'MLflow server is ready'
        }})

    except Exception as e:
        _write_mlflow_status(gcs_output_path, 'failed', {{
            'error': str(e),
            'stage': 'health_check'
        }})
        raise

    # Step 2: Create/get experiment
    try:
        experiment_id = _mlflow_client.set_experiment(MLFLOW_EXPERIMENT_NAME)
        if not experiment_id:
            _write_mlflow_status(gcs_output_path, 'failed', {{
                'error': f"Failed to create/get experiment '{{MLFLOW_EXPERIMENT_NAME}}'",
                'stage': 'set_experiment'
            }})
            raise RuntimeError(
                f"Failed to create/get MLflow experiment '{{MLFLOW_EXPERIMENT_NAME}}'. "
                f"Training cannot proceed without experiment tracking."
            )
        logging.info(f"MLflow experiment: {{MLFLOW_EXPERIMENT_NAME}} (id={{experiment_id}})")
    except RuntimeError:
        raise
    except Exception as e:
        _write_mlflow_status(gcs_output_path, 'failed', {{
            'error': str(e),
            'stage': 'set_experiment'
        }})
        raise

    # Step 3: Start run
    try:
        mlflow_run_id = _mlflow_client.start_run(run_name=MLFLOW_RUN_NAME)
        if not mlflow_run_id:
            _write_mlflow_status(gcs_output_path, 'failed', {{
                'error': f"Failed to start run. experiment_id={{experiment_id}}",
                'stage': 'start_run'
            }})
            raise RuntimeError(
                f"Failed to start MLflow run. experiment_id={{experiment_id}}. "
                f"Training cannot proceed without experiment tracking."
            )
        logging.info(f"MLflow run started: {{mlflow_run_id}}")
    except RuntimeError:
        raise
    except Exception as e:
        _write_mlflow_status(gcs_output_path, 'failed', {{
            'error': str(e),
            'stage': 'start_run'
        }})
        raise

    # Step 4: Log parameters
    _mlflow_client.log_params({{
        'epochs': epochs,
        'batch_size': batch_size,
        'learning_rate': learning_rate,
        'optimizer': '{self.optimizer}',
        'embedding_dim': OUTPUT_EMBEDDING_DIM,
        'feature_config_id': {feature_config_id},
        'model_config_id': {model_config_id},
        'dataset_id': {dataset_id},
    }})

    # Step 5: Log tags for filtering
    _mlflow_client.set_tags({{
        'feature_config_name': '{feature_config_name}',
        'model_config_name': '{model_config_name}',
        'dataset_name': '{dataset_name}',
        'model_type': '{model_type}',
    }})

    # Write ready status - MLflow is fully initialized
    _write_mlflow_status(gcs_output_path, 'ready', {{
        'stage': 'initialized',
        'experiment_id': experiment_id,
        'run_id': mlflow_run_id,
        'message': 'MLflow fully initialized, training may proceed'
    }})

    logging.info("MLflow initialization complete - training may proceed")
    logging.info("=" * 60)

    try:

        # Build model
        logging.info("Building RetrievalModel...")
        model = RetrievalModel(
            tf_transform_output=tf_transform_output
        )

        # Compile with configured optimizer: {self.optimizer}
        optimizer = {optimizer_class}(learning_rate=learning_rate)
        model.compile(optimizer=optimizer)
        logging.info(f"Using optimizer: {self.optimizer} with lr={{learning_rate}}")

        # Calculate steps
        train_steps = custom_config.get('train_steps', fn_args.train_steps)
        eval_steps = custom_config.get('eval_steps', fn_args.eval_steps)

        # Training callbacks
        callbacks = []

        # MLflow callback for per-epoch metrics (always added - MLflow is mandatory)
        callbacks.append(MLflowCallback())

        # TensorBoard logging
        if fn_args.model_run_dir:
            tensorboard_callback = tf.keras.callbacks.TensorBoard(
                log_dir=fn_args.model_run_dir,
                update_freq='epoch'
            )
            callbacks.append(tensorboard_callback)

        # Train
        logging.info(f"Starting training for {{epochs}} epochs...")
        history = model.fit(
            train_dataset,
            validation_data=eval_dataset,
            epochs=epochs,
            steps_per_epoch=train_steps,
            validation_steps=eval_steps,
            callbacks=callbacks
        )
        logging.info("Training completed.")

        # Log final metrics to MLflow
        if _mlflow_client:
            for metric_name, values in history.history.items():
                _mlflow_client.log_metric(f'final_{{metric_name}}', float(values[-1]))

        # Pre-compute candidate embeddings (needed for both test eval and serving)
        logging.info("Pre-computing candidate embeddings...")
        candidates_for_serving = _input_fn(
            fn_args.eval_files,
            fn_args.data_accessor,
            tf_transform_output,
            batch_size
        ).unbatch()

        product_ids, product_embeddings = _precompute_candidate_embeddings(
            model, candidates_for_serving
        )
        logging.info(f"Pre-computed embeddings for {{len(product_ids)}} products")

        # Evaluate on test set
        # All split strategies now have test data:
        # - Random: 5% hash-based test split
        # - Time Holdout: Last N days as test (temporal)
        # - Strict Temporal: Explicit test_days as test (temporal)
        try:
            transformed_examples_dir = os.path.dirname(fn_args.train_files[0])
            test_split_dir = os.path.join(os.path.dirname(transformed_examples_dir), 'Split-test')

            if tf.io.gfile.exists(test_split_dir):
                test_files = tf.io.gfile.glob(os.path.join(test_split_dir, '*'))
                if test_files:
                    logging.info(f"Test split found at {{test_split_dir}} - running final evaluation...")
                    test_dataset = _input_fn(
                        test_files,
                        fn_args.data_accessor,
                        tf_transform_output,
                        batch_size
                    )

                    # 1. Basic loss evaluation
                    test_loss_results = model.evaluate(test_dataset, return_dict=True)
                    logging.info("=== TEST SET LOSS ===")
                    for metric_name, metric_value in test_loss_results.items():
                        logging.info(f"  test_{{metric_name}}: {{metric_value:.6f}}")
                        if _mlflow_client:
                            _mlflow_client.log_metric(f'test_{{metric_name}}', float(metric_value))

                    # 2. Recall evaluation (Recall@5, @10, @50, @100)
                    # Reload test dataset for recall evaluation
                    test_dataset_for_recall = _input_fn(
                        test_files,
                        fn_args.data_accessor,
                        tf_transform_output,
                        batch_size
                    )
                    recall_results = _evaluate_recall_on_test_set(
                        model,
                        test_dataset_for_recall,
                        product_ids,
                        product_embeddings,
                        steps=50
                    )

                    # Log recall metrics to MLflow
                    if _mlflow_client and recall_results:
                        for metric_name, metric_value in recall_results.items():
                            _mlflow_client.log_metric(f'test_{{metric_name}}', float(metric_value))
                else:
                    logging.info("Test split directory exists but is empty - skipping test evaluation")
            else:
                logging.warning("No test split found - skipping test evaluation")
        except Exception as e:
            logging.warning(f"Could not evaluate on test set: {{e}}")
            import traceback
            traceback.print_exc()

        # Build serving model that properly tracks all resources
        logging.info("Building serving model...")
        serving_model = ServingModel(
            retrieval_model=model,
            tf_transform_output=tf_transform_output,
            product_ids=product_ids,
            product_embeddings=product_embeddings
        )

        # Save serving model with signature
        logging.info(f"Saving model to: {{fn_args.serving_model_dir}}")
        tf.saved_model.save(
            serving_model,
            fn_args.serving_model_dir,
            signatures={{'serving_default': serving_model.serve}}
        )
        logging.info("Model saved successfully!")

        # Write MLflow run ID to GCS for Django to retrieve
        if mlflow_run_id and gcs_output_path:
            _write_mlflow_info(gcs_output_path, mlflow_run_id)

    finally:
        # Clean up MLflow run
        if _mlflow_client:
            try:
                _mlflow_client.end_run()
                logging.info("MLflow run completed successfully")
            except Exception as e:
                logging.warning(f"Error closing MLflow run: {{e}}")
'''

    def generate_and_validate(self) -> Tuple[str, bool, Optional[str], Optional[int]]:
        """
        Generate code and validate it (no saving - trainer code is generated at runtime).

        Returns:
            Tuple of (code, is_valid, error_message, error_line):
            - code: Generated Python code string
            - is_valid: True if code passes syntax validation
            - error_message: Error description if invalid, None if valid
            - error_line: Line number where error occurred, None if valid
        """
        code = self.generate()

        # Validate the generated code
        is_valid, error_msg, error_line = validate_python_code(code, 'trainer')

        if not is_valid:
            logger.error(
                f"Generated trainer code for FeatureConfig {self.feature_config.id} + "
                f"ModelConfig {self.model_config.id} has syntax error: "
                f"{error_msg} at line {error_line}"
            )

        return code, is_valid, error_msg, error_line


# =============================================================================
# DATASET INFO HELPERS FOR VIEW MODAL
# =============================================================================

def _format_joins_summary(join_config: dict) -> list:
    """
    Format joins as simple text strings for View modal display.

    Args:
        join_config: Join configuration from Dataset model

    Returns:
        List of formatted join strings, e.g.:
        ["transactions.customer_id ↔ customers.customer_id (LEFT)"]
    """
    if not join_config:
        return []

    joins = join_config.get('joins', [])
    result = []

    for join in joins:
        left_table = join.get('left_table', '')
        left_column = join.get('left_column', '')
        right_table = join.get('right_table', '')
        right_column = join.get('right_column', '')
        join_type = join.get('join_type', 'LEFT').upper()

        if left_table and left_column and right_table and right_column:
            result.append(
                f"{left_table}.{left_column} ↔ {right_table}.{right_column} ({join_type})"
            )

    return result


def _format_date_filter_summary(date_filter: dict) -> Optional[str]:
    """
    Format date filter as summary text for View modal display.

    Args:
        date_filter: Date filter from summary_snapshot.filters_applied.dates

    Returns:
        Summary string, e.g.: "Last 30 days" or "From 2024-01-01" or None
    """
    if not date_filter:
        return None

    filter_type = date_filter.get('type')

    if filter_type == 'rolling':
        days = date_filter.get('days', 30)
        return f"Last {days} days"
    elif filter_type == 'fixed' or date_filter.get('start_date'):
        start_date = date_filter.get('start_date')
        if start_date:
            return f"From {start_date}"

    return None


def _get_date_filter_days(date_filter: dict) -> Optional[int]:
    """
    Extract the number of days from a date filter for split strategy calculations.

    Args:
        date_filter: Date filter from summary_snapshot.filters_applied.dates

    Returns:
        Number of days in the dataset, or None if not determinable
    """
    if not date_filter:
        return None

    filter_type = date_filter.get('type')

    if filter_type == 'rolling':
        return date_filter.get('days')

    return None


def _format_customer_filter_summary(customer_filter: dict) -> Optional[str]:
    """
    Format customer filters as summary text for View modal display.

    Args:
        customer_filter: Customer filter from summary_snapshot.filters_applied.customers

    Returns:
        Summary string, e.g.: "Top 80% by revenue" or "2 filters" or None
    """
    if not customer_filter:
        return None

    filter_count = customer_filter.get('count', 0)
    filters = customer_filter.get('filters', [])

    if filter_count == 0 and not filters:
        return None

    # Check for top revenue filter
    for f in filters:
        if f.get('type') == 'top_revenue':
            percent = f.get('percent', 80)
            return f"Top {percent}% customers"

    # Multiple filters
    if filter_count > 1:
        return f"{filter_count} customer filters"
    elif filter_count == 1 or len(filters) == 1:
        # Single filter - try to describe it
        if filters:
            f = filters[0]
            f_type = f.get('type', '')
            if f_type == 'transaction_count':
                return "By transaction count"
            elif f_type == 'spending':
                return "By spending"
        return "1 customer filter"

    return None


def _format_product_filter_summary(product_filter: dict) -> Optional[str]:
    """
    Format product filters as summary text for View modal display.

    Args:
        product_filter: Product filter from summary_snapshot.filters_applied.products

    Returns:
        Summary string, e.g.: "Top 75% by revenue" or "3 filters" or None
    """
    if not product_filter:
        return None

    filter_count = product_filter.get('count', 0)
    filters = product_filter.get('filters', [])

    if filter_count == 0 and not filters:
        return None

    # Check for top revenue filter
    for f in filters:
        if f.get('type') == 'top_revenue':
            percent = f.get('percent', 80)
            return f"Top {percent}% products"

    # Multiple filters
    if filter_count > 1:
        return f"{filter_count} product filters"
    elif filter_count == 1 or len(filters) == 1:
        # Single filter - try to describe it
        if filters:
            f = filters[0]
            f_type = f.get('type', '')
            if f_type == 'transaction_count':
                return "By transaction count"
            elif f_type == 'category':
                return "By category"
        return "1 product filter"

    return None


def _count_selected_columns(selected_columns: dict) -> int:
    """
    Count total selected columns across all tables.

    Args:
        selected_columns: Dict of table_name -> list of column names

    Returns:
        Total count of selected columns
    """
    if not selected_columns:
        return 0

    total = 0
    for table_columns in selected_columns.values():
        if isinstance(table_columns, list):
            total += len(table_columns)

    return total


def get_dataset_info_for_view(dataset) -> Dict[str, Any]:
    """
    Get dataset information formatted for the Feature Config View modal.

    Args:
        dataset: Dataset model instance

    Returns:
        Dict with tables, joins, filters, and estimates
    """
    snapshot = dataset.summary_snapshot or {}
    filters_applied = snapshot.get('filters_applied', {})

    # Build secondary tables list (handle both string and list formats)
    secondary_tables = dataset.secondary_tables or []
    if isinstance(secondary_tables, str):
        secondary_tables = [secondary_tables] if secondary_tables else []

    return {
        # Tables
        'primary_table': dataset.primary_table,
        'secondary_tables': secondary_tables,

        # Joins (simplified text format)
        'joins': _format_joins_summary(dataset.join_config),

        # Filters summary
        'filters': {
            'dates': _format_date_filter_summary(filters_applied.get('dates')),
            'customers': _format_customer_filter_summary(filters_applied.get('customers')),
            'products': _format_product_filter_summary(filters_applied.get('products')),
        },

        # Raw date days for split strategy calculations
        'date_days': _get_date_filter_days(filters_applied.get('dates')),

        # Estimates
        'estimated_rows': snapshot.get('total_rows'),
        'column_count': _count_selected_columns(dataset.selected_columns),

        # BigQuery location
        'bq_location': dataset.bq_location,
    }
