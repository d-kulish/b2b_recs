"""
Datasets BigQuery Services

Handles all BigQuery interactions for the Datasets domain:
- Table discovery (list tables in raw_data.*)
- Schema analysis
- Column statistics (full table scan for accuracy)
- Join key detection
- Dataset analysis and preview
- Query generation
- Column suggestions for ML concepts
"""
from django.conf import settings
import logging
import os
import re

logger = logging.getLogger(__name__)


# =============================================================================
# COLUMN SUGGESTION PATTERNS
# =============================================================================

# Patterns for auto-detecting ML column roles
ML_COLUMN_PATTERNS = {
    'user_id': [
        r'^customer_id$', r'^user_id$', r'^userid$', r'^client_id$',
        r'^buyer_id$', r'^member_id$', r'^account_id$', r'^person_id$',
    ],
    'product_id': [
        r'^product_id$', r'^productid$', r'^item_id$', r'^itemid$',
        r'^sku$', r'^sku_id$', r'^article_id$', r'^goods_id$',
    ],
    'revenue': [
        r'^amount$', r'^revenue$', r'^price$', r'^total$', r'^value$',
        r'^sales$', r'^order_total$', r'^transaction_amount$', r'^spend$',
    ],
}

# Patterns for potential join keys
JOIN_KEY_PATTERNS = [
    (r'_id$', 5),           # Columns ending in _id
    (r'^id$', 4),           # Exact match 'id'
    (r'_key$', 3),          # Columns ending in _key
    (r'_code$', 2),         # Columns ending in _code
]

# High-value join column names
HIGH_VALUE_JOIN_COLS = {
    'customer_id', 'user_id', 'product_id', 'item_id', 'order_id',
    'transaction_id', 'sku', 'sku_id', 'category_id', 'brand_id',
}


class BigQueryServiceError(Exception):
    """Custom exception for BigQuery service errors."""
    pass


class BigQueryService:
    """
    Service class for BigQuery operations related to datasets.
    """

    def __init__(self, model_endpoint):
        """
        Initialize BigQuery service for a model endpoint.

        Args:
            model_endpoint: ModelEndpoint instance
        """
        self.model_endpoint = model_endpoint
        self.project_id = model_endpoint.gcp_project_id or getattr(
            settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID')
        )
        self.location = getattr(
            settings, 'GCP_LOCATION', os.getenv('GCP_LOCATION', 'europe-central2')
        )
        self.dataset_name = 'raw_data'  # Only allow raw_data.* tables
        self._client = None

        if not self.project_id:
            raise BigQueryServiceError(
                "GCP Project ID not configured. Set gcp_project_id on the model "
                "or configure GCP_PROJECT_ID in settings/environment."
            )

    @property
    def client(self):
        """Lazy-load BigQuery client with configured location."""
        if self._client is None:
            try:
                from google.cloud import bigquery
                self._client = bigquery.Client(
                    project=self.project_id,
                    location=self.location
                )
            except ImportError:
                raise BigQueryServiceError(
                    "google-cloud-bigquery package not installed. "
                    "Run: pip install google-cloud-bigquery"
                )
            except Exception as e:
                logger.error(f"Failed to initialize BigQuery client: {e}")
                raise BigQueryServiceError(f"Failed to connect to BigQuery: {e}")
        return self._client

    def _normalize_table_name(self, table_name):
        """
        Normalize table name to include dataset prefix.

        Args:
            table_name: Table name (e.g., "transactions" or "raw_data.transactions")

        Returns:
            Normalized table name with dataset prefix
        """
        if '.' not in table_name:
            return f"{self.dataset_name}.{table_name}"
        return table_name

    def _get_full_table_ref(self, table_name):
        """
        Get fully qualified table reference.

        Args:
            table_name: Table name

        Returns:
            Full table reference (project.dataset.table)
        """
        normalized = self._normalize_table_name(table_name)
        return f"{self.project_id}.{normalized}"

    # =========================================================================
    # TABLE DISCOVERY
    # =========================================================================

    def list_tables(self):
        """
        List all tables in the raw_data dataset.

        Returns:
            List of table info dicts: [
                {
                    "table_id": "transactions",
                    "full_name": "raw_data.transactions",
                    "row_count": 1234567,
                    "size_bytes": 123456789,
                    "size_mb": 117.74,
                    "last_modified": "2024-11-28T10:30:00Z",
                    "column_count": 15
                }
            ]
        """
        try:
            dataset_ref = f"{self.project_id}.{self.dataset_name}"

            # Check if dataset exists
            try:
                self.client.get_dataset(dataset_ref)
            except Exception:
                logger.warning(f"Dataset {dataset_ref} not found")
                return []

            tables = list(self.client.list_tables(dataset_ref))

            result = []
            for table in tables:
                try:
                    # Get table metadata for row count and size
                    table_ref = self.client.get_table(table.reference)
                    size_bytes = table_ref.num_bytes or 0

                    result.append({
                        'table_id': table.table_id,
                        'full_name': f"{self.dataset_name}.{table.table_id}",
                        'row_count': table_ref.num_rows or 0,
                        'size_bytes': size_bytes,
                        'size_mb': round(size_bytes / (1024 * 1024), 2),
                        'last_modified': table_ref.modified.isoformat() if table_ref.modified else None,
                        'column_count': len(table_ref.schema) if table_ref.schema else 0,
                    })
                except Exception as e:
                    logger.warning(f"Error getting metadata for table {table.table_id}: {e}")
                    result.append({
                        'table_id': table.table_id,
                        'full_name': f"{self.dataset_name}.{table.table_id}",
                        'row_count': None,
                        'size_bytes': None,
                        'size_mb': None,
                        'last_modified': None,
                        'column_count': None,
                        'error': str(e),
                    })

            # Sort by row count (largest first)
            result.sort(key=lambda x: x.get('row_count') or 0, reverse=True)
            return result

        except Exception as e:
            logger.error(f"Error listing tables: {e}")
            raise BigQueryServiceError(f"Failed to list tables: {e}")

    # =========================================================================
    # SCHEMA ANALYSIS
    # =========================================================================

    def get_table_schema(self, table_name):
        """
        Get schema for a BigQuery table.

        Args:
            table_name: Table name (e.g., "transactions" or "raw_data.transactions")

        Returns:
            List of column info dicts: [
                {
                    "name": "customer_id",
                    "type": "STRING",
                    "mode": "NULLABLE",
                    "description": "...",
                    "suggested_role": "user_id"  # ML role suggestion
                }
            ]
        """
        try:
            full_ref = self._get_full_table_ref(table_name)
            table = self.client.get_table(full_ref)

            schema = []
            for field in table.schema:
                col_info = {
                    'name': field.name,
                    'type': field.field_type,
                    'mode': field.mode,
                    'description': field.description or '',
                }

                # Add ML role suggestion
                suggested_role = self._suggest_column_role(field.name, field.field_type)
                if suggested_role:
                    col_info['suggested_role'] = suggested_role

                # Add join key indicator
                if self._is_potential_join_key(field.name, field.field_type):
                    col_info['is_potential_join_key'] = True

                schema.append(col_info)

            return schema

        except Exception as e:
            logger.error(f"Error getting table schema for {table_name}: {e}")
            raise BigQueryServiceError(f"Failed to get schema for {table_name}: {e}")

    def _suggest_column_role(self, column_name, column_type):
        """
        Suggest an ML role for a column based on its name and type.

        Args:
            column_name: Column name
            column_type: BigQuery column type

        Returns:
            Suggested role name or None
        """
        col_lower = column_name.lower()

        for role, patterns in ML_COLUMN_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, col_lower):
                    # Verify type compatibility
                    if role == 'revenue' and column_type not in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'):
                        continue
                    return role

        return None

    def _is_potential_join_key(self, column_name, column_type):
        """
        Check if a column is a potential join key.

        Args:
            column_name: Column name
            column_type: BigQuery column type

        Returns:
            Boolean indicating if column is a potential join key
        """
        # Only STRING and INT64 types can be good join keys
        if column_type not in ('STRING', 'INT64'):
            return False

        col_lower = column_name.lower()

        # Check high-value join columns
        if col_lower in HIGH_VALUE_JOIN_COLS:
            return True

        # Check patterns
        for pattern, _ in JOIN_KEY_PATTERNS:
            if re.search(pattern, col_lower):
                return True

        return False

    # =========================================================================
    # COLUMN STATISTICS
    # =========================================================================

    def get_column_stats(self, table_name, columns=None):
        """
        Get column statistics for a BigQuery table.
        Uses full table scan for accurate statistics.

        Args:
            table_name: Table name (e.g., "transactions" or "raw_data.transactions")
            columns: Optional list of specific columns to analyze (None = all)

        Returns:
            Dict of column stats: {
                "customer_id": {
                    "type": "STRING",
                    "cardinality": 125234,
                    "null_count": 12,
                    "null_percent": 0.001,
                    "sample_values": ["C001", "C002", "C003"]
                },
                "amount": {
                    "type": "FLOAT64",
                    "min": 0.5,
                    "max": 12450.0,
                    "mean": 45.67,
                    "null_count": 0,
                    "null_percent": 0.0
                }
            }
        """
        try:
            full_ref = self._get_full_table_ref(table_name)
            table = self.client.get_table(full_ref)
            total_rows = table.num_rows

            if total_rows == 0:
                return {'_meta': {'total_rows': 0, 'table': table_name}}

            # Filter to requested columns
            fields_to_analyze = table.schema
            if columns:
                columns_set = set(columns)
                fields_to_analyze = [f for f in table.schema if f.name in columns_set]

            if not fields_to_analyze:
                return {'_meta': {'total_rows': total_rows, 'table': table_name}}

            # Build stats query for each column
            stats_parts = ["COUNT(*) AS __total_rows__"]

            for field in fields_to_analyze:
                col_name = field.name
                col_type = field.field_type

                # Null count for all columns
                stats_parts.append(f"COUNTIF(`{col_name}` IS NULL) AS `{col_name}__null_count`")

                # Type-specific stats
                if col_type in ('STRING', 'BYTES'):
                    stats_parts.append(f"COUNT(DISTINCT `{col_name}`) AS `{col_name}__cardinality`")
                    stats_parts.append(f"MAX(LENGTH(`{col_name}`)) AS `{col_name}__max_length`")
                elif col_type in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'):
                    stats_parts.append(f"MIN(`{col_name}`) AS `{col_name}__min`")
                    stats_parts.append(f"MAX(`{col_name}`) AS `{col_name}__max`")
                    stats_parts.append(f"AVG(CAST(`{col_name}` AS FLOAT64)) AS `{col_name}__mean`")
                    stats_parts.append(f"STDDEV(CAST(`{col_name}` AS FLOAT64)) AS `{col_name}__stddev`")
                elif col_type in ('DATE', 'DATETIME', 'TIMESTAMP'):
                    stats_parts.append(f"MIN(`{col_name}`) AS `{col_name}__min`")
                    stats_parts.append(f"MAX(`{col_name}`) AS `{col_name}__max`")
                elif col_type == 'BOOL':
                    stats_parts.append(f"COUNTIF(`{col_name}` = TRUE) AS `{col_name}__true_count`")
                    stats_parts.append(f"COUNTIF(`{col_name}` = FALSE) AS `{col_name}__false_count`")

            # Run stats query
            query = f"SELECT {', '.join(stats_parts)} FROM `{full_ref}`"
            logger.debug(f"Running stats query: {query[:200]}...")

            result = self.client.query(query).result()
            row = list(result)[0]

            # Parse results into column stats dict
            stats = {
                '_meta': {
                    'total_rows': total_rows,
                    'table': table_name,
                }
            }

            for field in fields_to_analyze:
                col_name = field.name
                col_type = field.field_type

                null_count = getattr(row, f'{col_name}__null_count', 0) or 0

                col_stats = {
                    'type': col_type,
                    'null_count': null_count,
                    'null_percent': round(null_count / total_rows * 100, 2) if total_rows > 0 else 0,
                }

                if col_type in ('STRING', 'BYTES'):
                    col_stats['cardinality'] = getattr(row, f'{col_name}__cardinality', 0) or 0
                    col_stats['max_length'] = getattr(row, f'{col_name}__max_length', 0) or 0
                    # Calculate uniqueness ratio
                    if total_rows > 0:
                        col_stats['uniqueness'] = round(col_stats['cardinality'] / total_rows * 100, 2)

                elif col_type in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'):
                    min_val = getattr(row, f'{col_name}__min', None)
                    max_val = getattr(row, f'{col_name}__max', None)
                    mean_val = getattr(row, f'{col_name}__mean', None)
                    stddev_val = getattr(row, f'{col_name}__stddev', None)

                    col_stats['min'] = float(min_val) if min_val is not None else None
                    col_stats['max'] = float(max_val) if max_val is not None else None
                    col_stats['mean'] = round(float(mean_val), 2) if mean_val is not None else None
                    col_stats['stddev'] = round(float(stddev_val), 2) if stddev_val is not None else None

                elif col_type in ('DATE', 'DATETIME', 'TIMESTAMP'):
                    min_val = getattr(row, f'{col_name}__min', None)
                    max_val = getattr(row, f'{col_name}__max', None)
                    col_stats['min'] = min_val.isoformat() if min_val else None
                    col_stats['max'] = max_val.isoformat() if max_val else None
                    # Calculate date range in days
                    if min_val and max_val:
                        if hasattr(min_val, 'date'):
                            date_range = (max_val.date() - min_val.date()).days
                        else:
                            date_range = (max_val - min_val).days
                        col_stats['range_days'] = date_range

                elif col_type == 'BOOL':
                    true_count = getattr(row, f'{col_name}__true_count', 0) or 0
                    false_count = getattr(row, f'{col_name}__false_count', 0) or 0
                    col_stats['true_count'] = true_count
                    col_stats['false_count'] = false_count
                    col_stats['true_percent'] = round(true_count / total_rows * 100, 2) if total_rows > 0 else 0

                stats[col_name] = col_stats

            return stats

        except Exception as e:
            logger.error(f"Error getting column stats for {table_name}: {e}")
            raise BigQueryServiceError(f"Failed to get column statistics: {e}")

    def get_sample_values(self, table_name, column_name, limit=10):
        """
        Get sample distinct values for a column.

        Args:
            table_name: Table name
            column_name: Column name
            limit: Max number of sample values

        Returns:
            List of sample values
        """
        try:
            full_ref = self._get_full_table_ref(table_name)
            query = f"""
                SELECT DISTINCT `{column_name}` as val
                FROM `{full_ref}`
                WHERE `{column_name}` IS NOT NULL
                LIMIT {limit}
            """
            result = self.client.query(query).result()
            return [str(row.val) for row in result]

        except Exception as e:
            logger.warning(f"Error getting sample values: {e}")
            return []

    # =========================================================================
    # JOIN KEY DETECTION
    # =========================================================================

    def detect_join_keys(self, tables):
        """
        Auto-detect potential join keys between tables.

        Args:
            tables: List of table names (first is primary table)

        Returns:
            Dict of detected joins: {
                "raw_data.products": {
                    "join_key": "product_id",
                    "primary_column": "product_id",
                    "secondary_column": "product_id",
                    "join_type": "left",
                    "confidence": "high",
                    "reason": "Exact column name match on 'product_id'"
                }
            }
        """
        if len(tables) < 2:
            return {}

        try:
            # Get schemas for all tables
            schemas = {}
            for table in tables:
                schema = self.get_table_schema(table)
                schemas[table] = {
                    col['name']: {
                        'type': col['type'],
                        'is_join_key': col.get('is_potential_join_key', False)
                    }
                    for col in schema
                }

            # Primary table
            primary_table = tables[0]
            primary_cols = schemas[primary_table]

            detected_joins = {}

            for secondary_table in tables[1:]:
                secondary_cols = schemas[secondary_table]

                best_match = None
                best_score = 0
                best_reason = ""

                # Find matching columns
                for pri_col, pri_info in primary_cols.items():
                    for sec_col, sec_info in secondary_cols.items():
                        score = 0
                        reasons = []

                        # Exact name match
                        if pri_col.lower() == sec_col.lower():
                            score += 10
                            reasons.append(f"Exact column name match on '{pri_col}'")

                        # Same type
                        if pri_info['type'] == sec_info['type']:
                            score += 2
                            reasons.append("Same data type")

                        # Both marked as potential join keys
                        if pri_info['is_join_key'] and sec_info['is_join_key']:
                            score += 3
                            reasons.append("Both columns identified as join keys")

                        # High-value column names
                        if pri_col.lower() in HIGH_VALUE_JOIN_COLS:
                            score += 4
                            reasons.append(f"'{pri_col}' is a common join column")

                        # Pattern matching for related columns
                        # e.g., primary has 'product_id', secondary has 'id'
                        sec_table_name = secondary_table.split('.')[-1].rstrip('s')  # products -> product
                        if pri_col.lower() == f"{sec_table_name}_id" and sec_col.lower() == 'id':
                            score += 8
                            reasons.append(f"FK pattern: '{pri_col}' matches '{sec_table_name}.id'")

                        if score > best_score:
                            best_score = score
                            best_match = {
                                'join_key': pri_col,  # For backward compatibility
                                'primary_column': pri_col,
                                'secondary_column': sec_col,
                                'join_type': 'left',
                                'reason': '; '.join(reasons),
                            }

                if best_match:
                    # Determine confidence
                    if best_score >= 12:
                        confidence = 'high'
                    elif best_score >= 6:
                        confidence = 'medium'
                    else:
                        confidence = 'low'

                    best_match['confidence'] = confidence
                    best_match['score'] = best_score
                    detected_joins[secondary_table] = best_match

            return detected_joins

        except Exception as e:
            logger.error(f"Error detecting join keys: {e}")
            raise BigQueryServiceError(f"Failed to detect join keys: {e}")

    # =========================================================================
    # COLUMN SUGGESTIONS
    # =========================================================================

    def suggest_columns(self, tables):
        """
        Suggest column mappings for ML concepts based on all selected tables.

        Args:
            tables: List of table names

        Returns:
            Dict of suggestions: {
                "user_id": {
                    "suggested_column": "customer_id",
                    "table": "raw_data.transactions",
                    "confidence": "high",
                    "alternatives": [...]
                },
                ...
            }
        """
        suggestions = {}

        try:
            all_columns = []
            for table in tables:
                schema = self.get_table_schema(table)
                for col in schema:
                    all_columns.append({
                        'table': table,
                        'name': col['name'],
                        'type': col['type'],
                        'suggested_role': col.get('suggested_role'),
                    })

            # Find best match for each ML concept
            for role in ML_COLUMN_PATTERNS.keys():
                matches = [c for c in all_columns if c.get('suggested_role') == role]

                if matches:
                    # Prefer columns from primary table (first in list)
                    primary_matches = [m for m in matches if m['table'] == tables[0]]
                    best = primary_matches[0] if primary_matches else matches[0]

                    suggestions[role] = {
                        'suggested_column': best['name'],
                        'table': best['table'],
                        'confidence': 'high' if primary_matches else 'medium',
                        'alternatives': [
                            {'column': m['name'], 'table': m['table']}
                            for m in matches if m != best
                        ][:3],  # Max 3 alternatives
                    }

            return suggestions

        except Exception as e:
            logger.error(f"Error suggesting columns: {e}")
            return {}

    # =========================================================================
    # DATASET ANALYSIS
    # =========================================================================

    def analyze_dataset(self, dataset):
        """
        Analyze a dataset configuration to get statistics for TFRS.

        Args:
            dataset: Dataset model instance

        Returns:
            Dict with analysis results (row_count, unique_users, unique_products)
        """
        try:
            column_mapping = dataset.column_mapping or {}

            # Helper to extract column name from potential "table.column" format
            def extract_col_name(value):
                if not value:
                    return None
                # Handle "table.column" format - extract just the column part
                if '.' in value:
                    return value.split('.')[-1]
                return value

            # Get actual column names from mapping
            user_col = extract_col_name(column_mapping.get('user_id'))
            product_col = extract_col_name(column_mapping.get('product_id'))

            # Generate the base query
            query = self.generate_query(dataset)

            # Build SELECT clause based on available mappings
            select_parts = ['COUNT(*) as row_count']

            if user_col:
                select_parts.append(f'COUNT(DISTINCT `{user_col}`) as unique_users')
            else:
                select_parts.append('NULL as unique_users')

            if product_col:
                select_parts.append(f'COUNT(DISTINCT `{product_col}`) as unique_products')
            else:
                select_parts.append('NULL as unique_products')

            # Wrap in analysis query
            analysis_query = f"""
            WITH dataset AS (
                {query}
            )
            SELECT
                {',\n                '.join(select_parts)}
            FROM dataset
            """

            logger.debug(f"Running analysis query...")
            result = self.client.query(analysis_query).result()
            row = list(result)[0]

            return {
                'row_count': row.row_count,
                'unique_users': row.unique_users,
                'unique_products': row.unique_products,
                'avg_items_per_user': round(row.row_count / row.unique_users, 2) if row.unique_users else 0,
                'avg_users_per_product': round(row.row_count / row.unique_products, 2) if row.unique_products else 0,
            }

        except Exception as e:
            logger.error(f"Error analyzing dataset: {e}")
            raise BigQueryServiceError(f"Failed to analyze dataset: {e}")

    def preview_dataset(self, dataset, limit=100):
        """
        Preview sample data from a dataset.

        Args:
            dataset: Dataset model instance
            limit: Max rows to return

        Returns:
            Dict with columns and rows
        """
        try:
            query = self.generate_query(dataset)
            query = f"{query}\nLIMIT {limit}"

            result = self.client.query(query).result()

            # Get column info
            columns = []
            for field in result.schema:
                columns.append({
                    'name': field.name,
                    'type': field.field_type,
                })

            # Get rows
            rows = []
            for row in result:
                row_data = []
                for val in row.values():
                    if val is None:
                        row_data.append(None)
                    elif hasattr(val, 'isoformat'):
                        row_data.append(val.isoformat())
                    else:
                        row_data.append(str(val))
                rows.append(row_data)

            return {
                'columns': columns,
                'rows': rows,
                'total': len(rows),
                'limited': len(rows) >= limit,
            }

        except Exception as e:
            logger.error(f"Error previewing dataset: {e}")
            raise BigQueryServiceError(f"Failed to preview dataset: {e}")

    # =========================================================================
    # QUERY GENERATION
    # =========================================================================

    def generate_query(self, dataset, for_analysis=False, split=None):
        """
        Generate BigQuery SQL from dataset configuration.

        Args:
            dataset: Dataset model instance
            for_analysis: If True, use mapped column names (user_id, product_id, etc.)
            split: Optional split type ('train', 'eval', or None for full dataset)

        Returns:
            SQL query string
        """
        try:
            selected_columns = dataset.selected_columns or {}
            column_mapping = dataset.column_mapping or {}
            filters = dataset.filters or {}

            # If no columns selected, select all from primary table
            if not selected_columns:
                schema = self.get_table_schema(dataset.primary_table)
                selected_columns = {
                    dataset.primary_table: [col['name'] for col in schema]
                }

            # Helper to extract column name from potential "table.column" format
            def extract_col(value):
                if not value:
                    return None
                if '.' in value:
                    return value.split('.')[-1]
                return value

            # Get column references (handle table.column format from legacy data)
            primary_alias = dataset.primary_table.split('.')[-1]
            user_col = extract_col(column_mapping.get('user_id'))
            product_col = extract_col(column_mapping.get('product_id'))
            revenue_col = extract_col(column_mapping.get('revenue'))

            # Build SELECT clause
            select_cols = []
            reverse_mapping = {v: k for k, v in column_mapping.items()}

            for table, columns in selected_columns.items():
                table_alias = table.split('.')[-1]
                for col in columns:
                    if for_analysis and col in reverse_mapping:
                        mapped_name = reverse_mapping[col]
                        select_cols.append(f"`{table_alias}`.`{col}` AS `{mapped_name}`")
                    else:
                        select_cols.append(f"`{table_alias}`.`{col}`")

            if not select_cols:
                select_cols = ['*']

            # Build FROM clause
            from_clause = f"`{self.project_id}.{dataset.primary_table}` AS `{primary_alias}`"

            # Build JOIN clauses
            join_clauses = []
            for secondary_table in (dataset.secondary_tables or []):
                join_config = dataset.join_config.get(secondary_table, {})
                join_key = join_config.get('join_key', 'id')
                join_type = join_config.get('join_type', 'LEFT').upper()
                secondary_col = join_config.get('secondary_column', join_key)

                secondary_alias = secondary_table.split('.')[-1]
                join_clauses.append(
                    f"{join_type} JOIN `{self.project_id}.{secondary_table}` AS `{secondary_alias}` "
                    f"ON `{primary_alias}`.`{join_key}` = `{secondary_alias}`.`{secondary_col}`"
                )

            # Build WHERE clauses
            where_clauses = []

            # Check if we need CTEs for complex filters
            ctes = []
            product_filter = filters.get('product_filter', {})
            customer_filter = filters.get('customer_filter', {})

            # Product filter (top N% by revenue) - requires product and revenue columns
            if product_filter.get('type') == 'top_revenue_percent' and product_col and revenue_col:
                percent = product_filter.get('value', 80)
                cte = self._generate_top_products_cte(
                    primary_alias, product_col, revenue_col, percent
                )
                ctes.append(('top_products', cte))
                where_clauses.append(
                    f"`{primary_alias}`.`{product_col}` IN (SELECT {product_col} FROM top_products)"
                )

            # Customer filter (min transactions) - requires user column
            if customer_filter.get('type') == 'min_transactions' and user_col:
                min_count = customer_filter.get('value', 2)
                cte = self._generate_active_users_cte(
                    primary_alias, user_col, min_count
                )
                ctes.append(('active_users', cte))
                where_clauses.append(
                    f"`{primary_alias}`.`{user_col}` IN (SELECT {user_col} FROM active_users)"
                )

            # Build final query
            query_parts = []

            # Add CTEs if needed
            if ctes:
                cte_strs = [f"{name} AS (\n{cte}\n)" for name, cte in ctes]
                query_parts.append(f"WITH {',\n'.join(cte_strs)}")

            # Main SELECT
            query_parts.append(f"SELECT\n  {',\n  '.join(select_cols)}")
            query_parts.append(f"FROM {from_clause}")

            if join_clauses:
                query_parts.append("\n".join(join_clauses))

            if where_clauses:
                query_parts.append(f"WHERE {' AND '.join(where_clauses)}")

            return "\n".join(query_parts)

        except Exception as e:
            logger.error(f"Error generating query: {e}")
            raise BigQueryServiceError(f"Failed to generate query: {e}")

    def _generate_top_products_cte(self, primary_alias, product_col, revenue_col, percent):
        """
        Generate CTE for top N% products by revenue.

        Returns:
            SQL CTE query string
        """
        return f"""
    SELECT {product_col}
    FROM (
        SELECT
            `{product_col}`,
            SUM(`{revenue_col}`) as total_revenue,
            SUM(SUM(`{revenue_col}`)) OVER () as grand_total,
            SUM(SUM(`{revenue_col}`)) OVER (ORDER BY SUM(`{revenue_col}`) DESC) as running_total
        FROM `{self.project_id}.{self.dataset_name}.{primary_alias}`
        GROUP BY `{product_col}`
    )
    WHERE running_total <= grand_total * {percent / 100}
       OR running_total - total_revenue < grand_total * {percent / 100}"""

    def _generate_active_users_cte(self, primary_alias, user_col, min_count):
        """
        Generate CTE for users with minimum transaction count.

        Returns:
            SQL CTE query string
        """
        return f"""
    SELECT `{user_col}`
    FROM `{self.project_id}.{self.dataset_name}.{primary_alias}`
    GROUP BY `{user_col}`
    HAVING COUNT(*) >= {min_count}"""

    def generate_train_query(self, dataset, for_analysis=False):
        """
        Generate query for training data only.

        Args:
            dataset: Dataset model instance
            for_analysis: If True, use mapped column names

        Returns:
            SQL query string for training data
        """
        return self.generate_query(dataset, for_analysis=for_analysis, split='train')

    def generate_eval_query(self, dataset, for_analysis=False):
        """
        Generate query for evaluation data only.

        Args:
            dataset: Dataset model instance
            for_analysis: If True, use mapped column names

        Returns:
            SQL query string for evaluation data
        """
        return self.generate_query(dataset, for_analysis=for_analysis, split='eval')

    def generate_tfx_queries(self, dataset):
        """
        Generate queries formatted for TFX ExampleGen component.

        Returns:
            Dict with train and eval queries ready for TFX
        """
        column_mapping = dataset.column_mapping or {}

        # TFX needs specific column names
        train_query = self.generate_query(dataset, for_analysis=True, split='train')
        eval_query = self.generate_query(dataset, for_analysis=True, split='eval')

        return {
            'train_query': train_query,
            'eval_query': eval_query,
            'column_mapping': column_mapping,
            'split_config': dataset.split_config,
            'tfx_config': {
                'query_based': True,
                'input_config': {
                    'splits': [
                        {'name': 'train', 'pattern': 'train_query'},
                        {'name': 'eval', 'pattern': 'eval_query'},
                    ]
                }
            }
        }

    def validate_query(self, query):
        """
        Validate a BigQuery query without executing it (dry run).

        Args:
            query: SQL query string

        Returns:
            Dict with validation result
        """
        try:
            from google.cloud.bigquery import QueryJobConfig

            job_config = QueryJobConfig(dry_run=True, use_query_cache=False)
            query_job = self.client.query(query, job_config=job_config)

            return {
                'valid': True,
                'total_bytes_processed': query_job.total_bytes_processed,
                'estimated_cost_usd': round(query_job.total_bytes_processed / (1024**4) * 5, 4),  # $5 per TB
            }

        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
            }
