"""
Modeling Domain Services

Contains business logic for Feature Engineering:
- SmartDefaultsService: Auto-configures features based on column mapping and statistics
- TensorDimensionCalculator: Calculates tensor dimensions for preview
"""

from typing import Dict, List, Any, Optional, Tuple


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
        """Get all selected columns with their type and statistics."""
        columns = []

        # Reverse column mapping to get role by column name
        reverse_mapping = {v: k for k, v in self.column_mapping.items()}

        for table, cols in self.selected_columns.items():
            for col in cols:
                # Get column stats if available
                stats_key = f"{table}.{col}" if '.' not in col else col
                stats = self.column_stats.get(stats_key, {})

                # Determine column type from stats or default to STRING
                col_type = stats.get('type', 'STRING')

                columns.append({
                    'name': col,
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
        'status': fc.status,
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
    }

    if include_details:
        data['buyer_model_features'] = fc.buyer_model_features
        data['product_model_features'] = fc.product_model_features
        data['buyer_model_crosses'] = fc.buyer_model_crosses
        data['product_model_crosses'] = fc.product_model_crosses

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
