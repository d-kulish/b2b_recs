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

    def __init__(self, model_endpoint, dataset=None):
        """
        Initialize BigQuery service for a model endpoint.

        Args:
            model_endpoint: ModelEndpoint instance
            dataset: Optional Dataset instance. If provided, uses the dataset's
                     bq_location for BigQuery operations. This is important because
                     BigQuery datasets are region-locked and queries must be executed
                     in the same region where the data resides.
        """
        self.model_endpoint = model_endpoint
        self.dataset = dataset
        self.project_id = model_endpoint.gcp_project_id or getattr(
            settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID')
        )
        # Use dataset's bq_location if available, otherwise fall back to global config
        if dataset and hasattr(dataset, 'bq_location') and dataset.bq_location:
            self.location = dataset.bq_location
        else:
            self.location = getattr(
                settings, 'GCP_LOCATION', os.getenv('GCP_LOCATION', 'US')
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

    def get_dataset_location(self):
        """
        Get the location (region) of the BigQuery dataset.

        BigQuery datasets are region-locked and queries must be executed in
        the same region where the data resides. This method detects the
        actual location of the raw_data dataset.

        Returns:
            str: Dataset location (e.g., 'US', 'EU', 'europe-central2')

        Raises:
            BigQueryServiceError: If unable to get dataset location
        """
        try:
            from google.cloud import bigquery
            # Use a simple client without location to query dataset metadata
            client = bigquery.Client(project=self.project_id)
            dataset_ref = f"{self.project_id}.{self.dataset_name}"
            dataset = client.get_dataset(dataset_ref)
            location = dataset.location
            logger.info(f"Detected BigQuery dataset location: {location}")
            return location
        except Exception as e:
            logger.error(f"Error getting dataset location: {e}")
            raise BigQueryServiceError(f"Failed to get dataset location: {e}")

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

    def check_join_key_uniqueness(self, table_name, column_name):
        """
        Check if a column has unique values (suitable as a join key).

        A non-unique join key will cause row multiplication in JOINs.

        Args:
            table_name: Table name (e.g., "products" or "raw_data.products")
            column_name: Column name to check

        Returns:
            Dict with uniqueness info: {
                "table": "raw_data.products",
                "column": "product_code",
                "total_rows": 16,
                "unique_values": 4,
                "is_unique": False,
                "duplication_factor": 4.0,
                "warning": "Column has 4 unique values but 16 rows. Joining on this column will multiply rows by ~4x."
            }
        """
        try:
            full_ref = self._get_full_table_ref(table_name)

            query = f"""
                SELECT
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT `{column_name}`) as unique_values,
                    COUNT(*) - COUNT(DISTINCT `{column_name}`) as duplicate_count
                FROM `{full_ref}`
                WHERE `{column_name}` IS NOT NULL
            """

            result = list(self.client.query(query).result())[0]

            total_rows = result.total_rows
            unique_values = result.unique_values
            is_unique = total_rows == unique_values

            # Calculate how much row multiplication would occur
            duplication_factor = round(total_rows / unique_values, 2) if unique_values > 0 else 0

            response = {
                "table": table_name,
                "column": column_name,
                "total_rows": total_rows,
                "unique_values": unique_values,
                "is_unique": is_unique,
                "duplication_factor": duplication_factor
            }

            if not is_unique:
                response["warning"] = (
                    f"Column '{column_name}' has {unique_values:,} unique values but {total_rows:,} rows. "
                    f"Joining on this column will multiply rows by ~{duplication_factor}x."
                )

            return response

        except Exception as e:
            logger.error(f"Error checking join key uniqueness for {table_name}.{column_name}: {e}")
            raise BigQueryServiceError(f"Failed to check join key uniqueness: {e}")

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
            select_clause = ',\n                '.join(select_parts)
            analysis_query = f"""
            WITH dataset AS (
                {query}
            )
            SELECT
                {select_clause}
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

    def _build_cross_filter_where_clauses(self, filters, primary_alias, exclude_filter=None):
        """
        Build WHERE clauses from cross-sub-chapter filters (category and numeric).

        This method extracts category and numeric filters from customer_filter and
        product_filter, converting them to SQL WHERE clauses. These clauses are used
        to filter the base data BEFORE calculating top products/customers.

        Args:
            filters: Full filters dict from dataset config
            primary_alias: Table alias for column references
            exclude_filter: 'customer' or 'product' - skip this filter type
                           (used when we don't want to apply filters from a specific sub-chapter)

        Returns:
            List of WHERE clause strings
        """
        where_clauses = []

        # Process customer_filter (category and numeric filters only, not top_revenue or aggregations)
        if exclude_filter != 'customer':
            customer_filter = filters.get('customer_filter', {})

            # Customer category filters (e.g., city IN ('CHERNIGIV'))
            for cat_filter in customer_filter.get('category_filters', []):
                col_ref = cat_filter.get('column', '')
                col_name = col_ref.split('.')[-1] if '.' in col_ref else col_ref
                if '.' in col_ref:
                    table_alias = col_ref.split('.')[0]
                else:
                    table_alias = primary_alias

                values = cat_filter.get('values', [])
                if values and col_name:
                    escaped = [v.replace("'", "''") for v in values]
                    values_sql = ", ".join(f"'{v}'" for v in escaped)

                    if cat_filter.get('mode') == 'exclude':
                        where_clauses.append(f"{table_alias}.{col_name} NOT IN ({values_sql})")
                    else:
                        where_clauses.append(f"{table_alias}.{col_name} IN ({values_sql})")

            # Customer numeric filters
            for num_filter in customer_filter.get('numeric_filters', []):
                col_ref = num_filter.get('column', '')
                col_name = col_ref.split('.')[-1] if '.' in col_ref else col_ref
                if '.' in col_ref:
                    table_alias = col_ref.split('.')[0]
                else:
                    table_alias = primary_alias

                filter_type = num_filter.get('filter_type', num_filter.get('type', 'range'))
                include_nulls = num_filter.get('include_nulls', False)

                if col_name:
                    conditions = []
                    if filter_type == 'range':
                        min_val = num_filter.get('min')
                        max_val = num_filter.get('max')
                        if min_val is not None:
                            conditions.append(f"{table_alias}.{col_name} >= {min_val}")
                        if max_val is not None:
                            conditions.append(f"{table_alias}.{col_name} <= {max_val}")
                    elif filter_type == 'greater_than':
                        val = num_filter.get('value')
                        if val is not None:
                            conditions.append(f"{table_alias}.{col_name} > {val}")
                    elif filter_type == 'less_than':
                        val = num_filter.get('value')
                        if val is not None:
                            conditions.append(f"{table_alias}.{col_name} < {val}")
                    elif filter_type == 'equals':
                        val = num_filter.get('value')
                        if val is not None:
                            conditions.append(f"{table_alias}.{col_name} = {val}")

                    if conditions:
                        cond_str = " AND ".join(conditions)
                        if include_nulls:
                            where_clauses.append(f"(({cond_str}) OR {table_alias}.{col_name} IS NULL)")
                        else:
                            where_clauses.append(f"({cond_str})")

        # Process product_filter (category and numeric filters only, not top_revenue or aggregations)
        if exclude_filter != 'product':
            product_filter = filters.get('product_filter', {})

            # Product category filters
            for cat_filter in product_filter.get('category_filters', []):
                col_ref = cat_filter.get('column', '')
                col_name = col_ref.split('.')[-1] if '.' in col_ref else col_ref
                if '.' in col_ref:
                    table_alias = col_ref.split('.')[0]
                else:
                    table_alias = primary_alias

                values = cat_filter.get('values', [])
                if values and col_name:
                    escaped = [v.replace("'", "''") for v in values]
                    values_sql = ", ".join(f"'{v}'" for v in escaped)

                    if cat_filter.get('mode') == 'exclude':
                        where_clauses.append(f"{table_alias}.{col_name} NOT IN ({values_sql})")
                    else:
                        where_clauses.append(f"{table_alias}.{col_name} IN ({values_sql})")

            # Product numeric filters
            for num_filter in product_filter.get('numeric_filters', []):
                col_ref = num_filter.get('column', '')
                col_name = col_ref.split('.')[-1] if '.' in col_ref else col_ref
                if '.' in col_ref:
                    table_alias = col_ref.split('.')[0]
                else:
                    table_alias = primary_alias

                filter_type = num_filter.get('filter_type', num_filter.get('type', 'range'))
                include_nulls = num_filter.get('include_nulls', False)

                if col_name:
                    conditions = []
                    if filter_type == 'range':
                        min_val = num_filter.get('min')
                        max_val = num_filter.get('max')
                        if min_val is not None:
                            conditions.append(f"{table_alias}.{col_name} >= {min_val}")
                        if max_val is not None:
                            conditions.append(f"{table_alias}.{col_name} <= {max_val}")
                    elif filter_type == 'greater_than':
                        val = num_filter.get('value')
                        if val is not None:
                            conditions.append(f"{table_alias}.{col_name} > {val}")
                    elif filter_type == 'less_than':
                        val = num_filter.get('value')
                        if val is not None:
                            conditions.append(f"{table_alias}.{col_name} < {val}")
                    elif filter_type == 'equals':
                        val = num_filter.get('value')
                        if val is not None:
                            conditions.append(f"{table_alias}.{col_name} = {val}")

                    if conditions:
                        cond_str = " AND ".join(conditions)
                        if include_nulls:
                            where_clauses.append(f"(({cond_str}) OR {table_alias}.{col_name} IS NULL)")
                        else:
                            where_clauses.append(f"({cond_str})")

        return where_clauses

    def generate_query(self, dataset, for_analysis=False, for_tfx=False):
        """
        Generate BigQuery SQL from dataset configuration.

        Args:
            dataset: Dataset model instance
            for_analysis: If True, use mapped column names (user_id, product_id, etc.)
            for_tfx: If True, convert TIMESTAMP/DATE/DATETIME columns to INT64 (Unix epoch)
                     for TFX BigQueryExampleGen compatibility

        Returns:
            SQL query string

        Note: Train/eval split is now handled by the Training domain (TFX ExampleGen).
        This method generates the base query without split logic.

        Supports filters from Step 4 of the Dataset Wizard:
        - history: Date filter with rolling window or fixed start date
        - product_filter: top_revenue, category_filters, numeric_filters
        - customer_filter: top_revenue, aggregation_filters, category_filters, numeric_filters

        IMPORTANT: Date filter is applied FIRST via a filtered_data CTE, so that
        top products/customers are calculated from the date-filtered data, not all history.
        """
        try:
            selected_columns = dataset.selected_columns or {}
            column_mapping = dataset.column_mapping or {}
            column_aliases = dataset.column_aliases or {}  # User-defined display aliases
            filters = dataset.filters or {}
            primary_table = dataset.primary_table

            # If no columns selected, select all from primary table
            if not selected_columns:
                schema = self.get_table_schema(primary_table)
                selected_columns = {
                    primary_table: [col['name'] for col in schema]
                }

            # Get table alias (last part of table name)
            primary_alias = primary_table.split('.')[-1]

            # Build column type lookup for TFX TIMESTAMP conversion
            # TFX BigQueryExampleGen doesn't support TIMESTAMP/DATE/DATETIME types
            column_types = {}
            if for_tfx and dataset.summary_snapshot:
                column_stats = dataset.summary_snapshot.get('column_stats', {})
                for col_key, stats in column_stats.items():
                    column_types[col_key] = stats.get('type', 'STRING')

            # Build SELECT clause with full table.column references
            # IMPORTANT: Handle duplicate column names the same way as the filtered_data CTE
            # to ensure FeatureConfig column names match BigQuery output.
            select_cols = []
            reverse_mapping = {v: k for k, v in column_mapping.items()}
            seen_cols = set()  # Track seen column names to handle duplicates

            for table, columns in selected_columns.items():
                table_alias = table.split('.')[-1]
                for col in columns:
                    # Check if this column needs TIMESTAMP conversion for TFX
                    col_key = f"{table_alias}.{col}"
                    col_type = column_types.get(col_key, 'STRING')
                    needs_conversion = for_tfx and col_type in ('TIMESTAMP', 'DATE', 'DATETIME')

                    if for_analysis and col in reverse_mapping:
                        mapped_name = reverse_mapping[col]
                        if needs_conversion:
                            select_cols.append(f"UNIX_SECONDS(CAST({table_alias}.{col} AS TIMESTAMP)) AS {mapped_name}")
                        else:
                            select_cols.append(f"{table_alias}.{col} AS {mapped_name}")
                    else:
                        # Handle duplicate column names across tables
                        # First occurrence uses raw name, subsequent use table_alias_col
                        if col in seen_cols:
                            # Duplicate column - use table_alias_col format
                            output_name = f"{table_alias}_{col}"
                        else:
                            # First occurrence - use raw column name
                            output_name = col
                            seen_cols.add(col)

                        # Check if user has defined an alias for this column
                        # Alias keys are in format: "tablename_column" or "tablename.column"
                        alias_key = f"{table_alias}_{col}"
                        alias_key_dot = f"{table_alias}.{col}"
                        final_name = column_aliases.get(alias_key) or column_aliases.get(alias_key_dot) or output_name

                        if needs_conversion:
                            # Convert TIMESTAMP to Unix epoch seconds (INT64)
                            select_cols.append(f"UNIX_SECONDS(CAST({table_alias}.{col} AS TIMESTAMP)) AS {final_name}")
                        else:
                            select_cols.append(f"{table_alias}.{col} AS {final_name}")

            if not select_cols:
                select_cols = ['*']

            # =========================================================
            # BUILD CTEs - Date filter FIRST, then product/customer filters
            # =========================================================
            ctes = []
            final_where_clauses = []

            # 1. Check if we have a date filter - this becomes the base filtered_data CTE
            history_filter = filters.get('history')
            has_date_filter = False
            date_filter_clause = None

            if history_filter:
                date_filter_clause = self._generate_date_filter(history_filter, primary_table)
                if date_filter_clause:
                    has_date_filter = True

            # 2. Build the filtered_data CTE if we have a date filter
            # This CTE includes the primary table with JOINs, filtered by date
            if has_date_filter:
                # Build SELECT clause for filtered_data with unique aliases to avoid ambiguity
                filtered_select_cols = []
                seen_cols = set()
                for table, columns in selected_columns.items():
                    table_alias = table.split('.')[-1]
                    for col in columns:
                        # Check if this column needs TIMESTAMP conversion for TFX
                        col_key = f"{table_alias}.{col}"
                        col_type = column_types.get(col_key, 'STRING')
                        needs_conversion = for_tfx and col_type in ('TIMESTAMP', 'DATE', 'DATETIME')

                        # Use table_col as alias if column name is duplicated
                        if col in seen_cols:
                            if needs_conversion:
                                filtered_select_cols.append(f"UNIX_SECONDS(CAST({table_alias}.{col} AS TIMESTAMP)) AS {table_alias}_{col}")
                            else:
                                filtered_select_cols.append(f"{table_alias}.{col} AS {table_alias}_{col}")
                        else:
                            if needs_conversion:
                                filtered_select_cols.append(f"UNIX_SECONDS(CAST({table_alias}.{col} AS TIMESTAMP)) AS {col}")
                            else:
                                filtered_select_cols.append(f"{table_alias}.{col}")
                            seen_cols.add(col)

                if not filtered_select_cols:
                    filtered_select_cols = [f"{primary_alias}.*"]

                filtered_select_str = ',\n        '.join(filtered_select_cols)

                # Build JOIN clauses for the filtered_data CTE
                filtered_data_joins = []
                for secondary_table in (dataset.secondary_tables or []):
                    join_config = dataset.join_config.get(secondary_table, {})
                    join_key = join_config.get('join_key', 'id')
                    join_type = join_config.get('join_type', 'LEFT').upper()
                    secondary_col = join_config.get('secondary_column', join_key)
                    secondary_alias = secondary_table.split('.')[-1]

                    filtered_data_joins.append(
                        f"    {join_type} JOIN `{self.project_id}.{secondary_table}` AS {secondary_alias} "
                        f"ON {primary_alias}.{join_key} = {secondary_alias}.{secondary_col}"
                    )

                join_clause_str = '\n'.join(filtered_data_joins) if filtered_data_joins else ''

                # Build complete WHERE clause including cross-sub-chapter filters
                # This ensures top_products and top_customers are calculated from the
                # correctly filtered subset (e.g., only CHERNIGIV data, not all cities)
                all_where_clauses = [date_filter_clause]

                # Add cross-sub-chapter category and numeric filters
                cross_filter_clauses = self._build_cross_filter_where_clauses(
                    filters, primary_alias, exclude_filter=None
                )
                all_where_clauses.extend(cross_filter_clauses)

                # Combine all WHERE clauses
                combined_where_clause = ' AND\n        '.join(all_where_clauses)

                filtered_data_cte = f"""
    SELECT
        {filtered_select_str}
    FROM `{self.project_id}.{primary_table}` AS {primary_alias}
{join_clause_str}
    WHERE {combined_where_clause}"""
                ctes.append(('filtered_data', filtered_data_cte))

            # 3. Product filters - use filtered_data if available
            # When using filtered_data, skip row filters (category/numeric/date) as they're
            # already applied in the CTE. Only generate CTEs for top_revenue and aggregations.
            product_filter = filters.get('product_filter', {})
            if product_filter:
                source_table = 'filtered_data' if has_date_filter else f'`{self.project_id}.{primary_table}`'
                product_ctes, product_wheres = self._generate_product_filter_clauses_v2(
                    product_filter, source_table, primary_table,
                    skip_row_filters=has_date_filter  # Skip if filters already in filtered_data
                )
                ctes.extend(product_ctes)
                final_where_clauses.extend(product_wheres)

            # 4. Customer filters - use filtered_data if available
            # When using filtered_data, skip row filters (category/numeric/date) as they're
            # already applied in the CTE. Only generate CTEs for top_revenue and aggregations.
            customer_filter = filters.get('customer_filter', {})
            if customer_filter:
                source_table = 'filtered_data' if has_date_filter else f'`{self.project_id}.{primary_table}`'
                customer_ctes, customer_wheres = self._generate_customer_filter_clauses_v2(
                    customer_filter, source_table, primary_table,
                    skip_row_filters=has_date_filter  # Skip if filters already in filtered_data
                )
                ctes.extend(customer_ctes)
                final_where_clauses.extend(customer_wheres)

            # =========================================================
            # LEGACY FILTER SUPPORT (backward compatibility)
            # =========================================================
            def extract_col(value):
                if not value:
                    return None
                if '.' in value:
                    return value.split('.')[-1]
                return value

            user_col = extract_col(column_mapping.get('user_id'))
            product_col = extract_col(column_mapping.get('product_id'))
            revenue_col = extract_col(column_mapping.get('revenue'))

            # Legacy product filter (type == 'top_revenue_percent')
            if product_filter.get('type') == 'top_revenue_percent' and product_col and revenue_col:
                percent = product_filter.get('value', 80)
                source = 'filtered_data' if has_date_filter else f'`{self.project_id}.{self.dataset_name}.{primary_alias}`'
                cte = self._generate_top_products_cte_legacy(
                    source, product_col, revenue_col, percent
                )
                ctes.append(('legacy_top_products', cte))
                final_where_clauses.append(
                    f"{primary_alias}.{product_col} IN (SELECT {product_col} FROM legacy_top_products)"
                )

            # Legacy customer filter (type == 'min_transactions')
            if customer_filter.get('type') == 'min_transactions' and user_col:
                min_count = customer_filter.get('value', 2)
                source = 'filtered_data' if has_date_filter else f'`{self.project_id}.{self.dataset_name}.{primary_alias}`'
                cte = self._generate_active_users_cte_legacy(
                    source, user_col, min_count
                )
                ctes.append(('legacy_active_users', cte))
                final_where_clauses.append(
                    f"{primary_alias}.{user_col} IN (SELECT {user_col} FROM legacy_active_users)"
                )

            # =========================================================
            # BUILD FINAL QUERY
            # =========================================================
            query_parts = []

            # Add CTEs if needed
            if ctes:
                cte_strs = [f"{name} AS (\n{cte}\n)" for name, cte in ctes]
                cte_joined = ',\n'.join(cte_strs)
                query_parts.append(f"WITH {cte_joined}")

            # Main SELECT - when using filtered_data, use plain column names (with aliases for duplicates)
            if has_date_filter:
                # Build SELECT with same aliasing used in filtered_data CTE
                plain_select_cols = []
                seen_cols = set()
                for table, columns in selected_columns.items():
                    table_alias = table.split('.')[-1]
                    for col in columns:
                        if col in seen_cols:
                            # Use the aliased name from filtered_data
                            plain_select_cols.append(f"{table_alias}_{col}")
                        else:
                            plain_select_cols.append(col)
                            seen_cols.add(col)
                if not plain_select_cols:
                    plain_select_cols = ['*']
                select_joined = ',\n  '.join(plain_select_cols)
            else:
                select_joined = ',\n  '.join(select_cols)

            query_parts.append(f"SELECT\n  {select_joined}")

            # FROM clause - use filtered_data if we have date filter, otherwise original tables
            if has_date_filter:
                query_parts.append("FROM filtered_data")
            else:
                from_clause = f"`{self.project_id}.{primary_table}` AS {primary_alias}"
                query_parts.append(f"FROM {from_clause}")

                # Add JOINs only if not using filtered_data (which already has joins)
                join_clauses = []
                for secondary_table in (dataset.secondary_tables or []):
                    join_config = dataset.join_config.get(secondary_table, {})
                    join_key = join_config.get('join_key', 'id')
                    join_type = join_config.get('join_type', 'LEFT').upper()
                    secondary_col = join_config.get('secondary_column', join_key)
                    secondary_alias = secondary_table.split('.')[-1]

                    join_clauses.append(
                        f"{join_type} JOIN `{self.project_id}.{secondary_table}` AS {secondary_alias} "
                        f"ON {primary_alias}.{join_key} = {secondary_alias}.{secondary_col}"
                    )

                if join_clauses:
                    query_parts.append("\n".join(join_clauses))

            # WHERE clause for product/customer filters
            if final_where_clauses:
                where_joined = ' AND\n  '.join(final_where_clauses)
                query_parts.append(f"WHERE\n  {where_joined}")

            return "\n".join(query_parts)

        except Exception as e:
            logger.error(f"Error generating query: {e}")
            raise BigQueryServiceError(f"Failed to generate query: {e}")

    def generate_training_query(
        self,
        dataset,
        split_strategy: str = 'random',
        holdout_days: int = 1,
        date_column: str = None,
        sample_percent: int = 100,
        train_days: int = 60,
        val_days: int = 7,
        test_days: int = 7,
    ) -> str:
        """
        Generate BigQuery SQL for training with split strategy and sampling.

        This wraps generate_query() and applies additional filters:
        1. Holdout filter - excludes recent data for time-based strategies
        2. Sampling - random sample of data for quick tests

        Args:
            dataset: Dataset model instance
            split_strategy: 'random', 'time_holdout', or 'strict_time'
            holdout_days: Days to exclude from training (for time_holdout)
            date_column: Column name for temporal split (required for time-based strategies)
            sample_percent: Percentage of data to use (5, 10, 25, 100)
            train_days: Number of days for training data (strict_time only)
            val_days: Number of days for validation data (strict_time only)
            test_days: Number of days for test data - held out (strict_time only)

        Returns:
            SQL query string with holdout and sampling applied

        Order of operations:
        1. Base query (from generate_query) with dataset filters
        2. Holdout filter (exclude recent N days) - applied AFTER dataset filters
        3. Sampling (random %) - applied LAST so holdout is always complete

        Example for time_holdout with 1 day holdout and 10% sampling:
            WITH base_data AS (
                <original generate_query output>
            ),
            holdout_filtered AS (
                SELECT * FROM base_data
                WHERE trans_date < DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
            )
            SELECT * FROM holdout_filtered
            WHERE RAND() < 0.1
        """
        try:
            # Get base query with TFX-compatible type conversions (TIMESTAMP -> INT64)
            base_query = self.generate_query(dataset, for_analysis=False, for_tfx=True)

            # If no modifications needed, return base query
            if split_strategy == 'random' and sample_percent >= 100:
                return base_query

            # Build CTEs for holdout and sampling
            query_parts = []
            current_source = 'base_data'

            # Wrap base query in CTE
            query_parts.append(f"WITH base_data AS (\n{base_query}\n)")

            # Apply holdout filter for time-based strategies
            if split_strategy in ('time_holdout', 'strict_time') and date_column:
                holdout_cte = self._generate_holdout_cte(
                    source_table=current_source,
                    date_column=date_column,
                    holdout_days=holdout_days,
                    strategy=split_strategy,
                    train_days=train_days,
                    val_days=val_days,
                    test_days=test_days,
                )
                query_parts[0] += f",\nholdout_filtered AS (\n{holdout_cte}\n)"
                current_source = 'holdout_filtered'

            # Apply sampling if needed
            if sample_percent < 100:
                # Final SELECT with sampling
                sample_fraction = sample_percent / 100.0
                query_parts.append(
                    f"SELECT * FROM {current_source}\n"
                    f"WHERE RAND() < {sample_fraction}"
                )
            else:
                # No sampling, just select all
                query_parts.append(f"SELECT * FROM {current_source}")

            return "\n".join(query_parts)

        except Exception as e:
            logger.error(f"Error generating training query: {e}")
            raise BigQueryServiceError(f"Failed to generate training query: {e}")

    def _generate_holdout_cte(
        self,
        source_table: str,
        date_column: str,
        holdout_days: int,
        strategy: str,
        train_days: int = 60,
        val_days: int = 7,
        test_days: int = 7,
    ) -> str:
        """
        Generate CTE for temporal splitting based on date column.

        All date calculations are relative to the MAX date in the dataset,
        NOT CURRENT_DATE(). This ensures splits work correctly with historical data.

        Adds a 'split' column for TFX to use with partition_feature_name.

        Args:
            source_table: Source CTE or table name
            date_column: Column name containing dates (Unix epoch INT64)
            holdout_days: Number of days for test split (for time_holdout)
            strategy: 'time_holdout' or 'strict_time'
            train_days: Number of days for training data (strict_time only)
            val_days: Number of days for validation data (strict_time only)
            test_days: Number of days for test data (strict_time only)

        Returns:
            SQL for the holdout CTE body (without the AS wrapper)

        For time_holdout:
            - Last N days (holdout_days) → 'test' split (temporal)
            - Remaining days → 80% 'train', 20% 'eval' (random via hash)
            Uses FARM_FINGERPRINT for deterministic random assignment.

        For strict_time:
            True temporal split with data ordered by time:
            - Timeline: |<-- train_days -->|<-- val_days -->|<-- test_days -->| MAX_DATE
            - Each section assigned to corresponding split
            Pure temporal ordering, no random component.
        """
        if strategy == 'time_holdout':
            # Time holdout: last N days = test, remaining = 80/20 train/eval (random)
            # Note: date_column is already converted to Unix epoch (INT64) by for_tfx=True
            # We use FARM_FINGERPRINT for deterministic 80/20 split on non-test data
            return f"""    WITH max_date_ref AS (
        SELECT DATE(TIMESTAMP_SECONDS(MAX({date_column}))) AS ref_date
        FROM {source_table}
    )
    SELECT
        base.*,
        CASE
            -- Last {holdout_days} days = test (temporal)
            WHEN base.{date_column} >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {holdout_days} DAY)))
                THEN 'test'
            -- Remaining days: 80% train, 20% eval (deterministic random via hash)
            WHEN MOD(ABS(FARM_FINGERPRINT(CAST(base.{date_column} AS STRING))), 100) < 80
                THEN 'train'
            ELSE 'eval'
        END AS split
    FROM {source_table} base, max_date_ref"""

        elif strategy == 'strict_time':
            # Strict temporal: explicit day-based splits
            # Timeline (relative to MAX date):
            #   |<-- train_days -->|<-- val_days -->|<-- test_days -->| MAX_DATE
            #
            # All data in the window gets a split assignment based on date
            total_window = train_days + val_days + test_days
            val_test_days = val_days + test_days
            return f"""    WITH max_date_ref AS (
        SELECT DATE(TIMESTAMP_SECONDS(MAX({date_column}))) AS ref_date
        FROM {source_table}
    )
    SELECT
        base.*,
        CASE
            -- Last {test_days} days = test
            WHEN base.{date_column} >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {test_days} DAY)))
                THEN 'test'
            -- Next {val_days} days (before test) = eval
            WHEN base.{date_column} >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {val_test_days} DAY)))
                THEN 'eval'
            -- Remaining days in window = train
            WHEN base.{date_column} >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {total_window} DAY)))
                THEN 'train'
            -- Data outside window (older than total_window days) - exclude
            ELSE NULL
        END AS split
    FROM {source_table} base, max_date_ref
    WHERE base.{date_column} >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {total_window} DAY)))"""

        else:
            # Random - no holdout filter, no split column (TFX does hash-based split)
            return f"    SELECT * FROM {source_table}"

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

    # =========================================================================
    # NEW FILTER GENERATION METHODS (Step 4 filters)
    # =========================================================================

    def _generate_date_filter(self, history_config, primary_table):
        """
        Generate WHERE clause for date/history filter.

        Args:
            history_config: Dict with timestamp_column, rolling_days, start_date
            primary_table: Primary table name for reference

        Returns:
            SQL WHERE clause string or None

        Note: Rolling window uses the MAX date in the dataset as reference point,
        not the current date. This ensures consistent results and works with
        historical data.
        """
        if not history_config:
            return None

        timestamp_col = history_config.get('timestamp_column')
        if not timestamp_col:
            return None

        rolling_days = history_config.get('rolling_days')
        start_date = history_config.get('start_date')

        # Extract just the column name for the subquery
        col_name = timestamp_col.split('.')[-1] if '.' in timestamp_col else timestamp_col

        # Use rolling window relative to MAX date in the dataset
        if rolling_days:
            return f"{timestamp_col} >= TIMESTAMP_SUB((SELECT MAX({col_name}) FROM `{self.project_id}.{primary_table}`), INTERVAL {rolling_days} DAY)"

        # Use fixed start date - convert to timestamp for comparison
        if start_date:
            return f"{timestamp_col} >= TIMESTAMP('{start_date}')"

        return None

    def _generate_product_filter_clauses(self, product_filter, primary_table):
        """
        Generate CTEs and WHERE clauses for product filters.

        Args:
            product_filter: Dict with top_revenue, aggregation_filters, category_filters, numeric_filters
            primary_table: Primary table name

        Returns:
            Tuple of (list of CTE tuples, list of WHERE clauses)
        """
        ctes = []
        where_clauses = []

        if not product_filter:
            return ctes, where_clauses

        # Top revenue filter (top N% products by revenue)
        top_revenue = product_filter.get('top_revenue', {})
        if top_revenue.get('enabled'):
            product_col = top_revenue.get('product_column')
            revenue_col = top_revenue.get('revenue_column')
            threshold = top_revenue.get('threshold_percent', 80)

            if product_col and revenue_col:
                cte = self._generate_top_products_cte_v2(
                    primary_table, product_col, revenue_col, threshold
                )
                ctes.append(('top_products', cte))
                where_clauses.append(
                    f"{product_col} IN (SELECT product_id FROM top_products)"
                )

        # Aggregation filters (transaction count, total revenue per product)
        aggregation_filters = product_filter.get('aggregation_filters', [])
        for af in aggregation_filters:
            agg_type = af.get('type')
            product_col = af.get('product_column')
            amount_col = af.get('amount_column')
            filter_type = af.get('filter_type', 'greater_than')
            value = af.get('value')
            min_val = af.get('min')
            max_val = af.get('max')

            if not product_col:
                continue

            cte_name = f"filtered_products_{len(ctes)}"
            cte = self._generate_product_aggregation_cte(
                primary_table, product_col, amount_col, agg_type, filter_type, value, min_val, max_val
            )
            if cte:
                ctes.append((cte_name, cte))
                where_clauses.append(
                    f"{product_col} IN (SELECT product_id FROM {cte_name})"
                )

        # Category filters (include/exclude specific values)
        category_filters = product_filter.get('category_filters', [])
        for cf in category_filters:
            column = cf.get('column')
            mode = cf.get('mode', 'include')
            values = cf.get('values', [])

            if column and values:
                # Escape values for SQL
                escaped_values = [f"'{v}'" for v in values]
                values_str = ', '.join(escaped_values)

                if mode == 'include':
                    where_clauses.append(f"{column} IN ({values_str})")
                else:  # exclude
                    where_clauses.append(f"{column} NOT IN ({values_str})")

        # Numeric filters (range, greater_than, less_than, equals)
        numeric_filters = product_filter.get('numeric_filters', [])
        for nf in numeric_filters:
            column = nf.get('column')
            filter_type = nf.get('type', 'range')
            min_val = nf.get('min')
            max_val = nf.get('max')
            value = nf.get('value')
            include_nulls = nf.get('include_nulls', False)

            if not column:
                continue

            condition = None
            if filter_type == 'range' and min_val is not None and max_val is not None:
                condition = f"{column} BETWEEN {min_val} AND {max_val}"
            elif filter_type == 'greater_than' and value is not None:
                condition = f"{column} > {value}"
            elif filter_type == 'less_than' and value is not None:
                condition = f"{column} < {value}"
            elif filter_type == 'equals' and value is not None:
                condition = f"{column} = {value}"
            elif min_val is not None:
                condition = f"{column} >= {min_val}"
            elif max_val is not None:
                condition = f"{column} <= {max_val}"

            if condition:
                if include_nulls:
                    where_clauses.append(f"({condition} OR {column} IS NULL)")
                else:
                    where_clauses.append(condition)

        return ctes, where_clauses

    def _generate_top_products_cte_v2(self, primary_table, product_col, revenue_col, percent):
        """
        Generate CTE for top N% products by revenue (new format with full column names).

        Args:
            primary_table: Full table name (e.g., 'raw_data.transactions')
            product_col: Full column reference (e.g., 'transactions.product_id')
            revenue_col: Full column reference (e.g., 'transactions.amount')
            percent: Percentage threshold (e.g., 80 for top 80%)

        Returns:
            SQL CTE query string
        """
        # Extract just the column names (without table prefix) for the CTE query
        product_col_name = product_col.split('.')[-1] if '.' in product_col else product_col
        revenue_col_name = revenue_col.split('.')[-1] if '.' in revenue_col else revenue_col

        return f"""
    SELECT {product_col_name} as product_id
    FROM (
        SELECT
            {product_col_name} as product_id,
            SUM({revenue_col_name}) as total_revenue,
            SUM(SUM({revenue_col_name})) OVER () as grand_total,
            SUM(SUM({revenue_col_name})) OVER (ORDER BY SUM({revenue_col_name}) DESC) as running_total
        FROM `{self.project_id}.{primary_table}`
        GROUP BY {product_col_name}
    )
    WHERE running_total <= grand_total * {percent / 100}
       OR running_total - total_revenue < grand_total * {percent / 100}"""

    def _generate_product_aggregation_cte(self, primary_table, product_col, amount_col,
                                          agg_type, filter_type, value, min_val, max_val):
        """
        Generate CTE for product aggregation filters (transaction count, total revenue, etc.).

        Args:
            primary_table: Full table name
            product_col: Product column reference
            amount_col: Amount/revenue column reference (optional for count)
            agg_type: 'transaction_count' or 'total_revenue'
            filter_type: 'greater_than', 'less_than', 'between', 'equals'
            value: Single value for comparison
            min_val: Min value for range
            max_val: Max value for range

        Returns:
            SQL CTE query string or None
        """
        product_col_name = product_col.split('.')[-1] if '.' in product_col else product_col

        # Determine aggregation function
        if agg_type == 'transaction_count':
            agg_expr = 'COUNT(*)'
        elif agg_type == 'total_revenue' and amount_col:
            amount_col_name = amount_col.split('.')[-1] if '.' in amount_col else amount_col
            agg_expr = f'SUM({amount_col_name})'
        else:
            return None

        # Build HAVING condition
        if filter_type == 'greater_than' and value is not None:
            having = f"HAVING {agg_expr} > {value}"
        elif filter_type == 'less_than' and value is not None:
            having = f"HAVING {agg_expr} < {value}"
        elif filter_type == 'equals' and value is not None:
            having = f"HAVING {agg_expr} = {value}"
        elif filter_type == 'between' and min_val is not None and max_val is not None:
            having = f"HAVING {agg_expr} BETWEEN {min_val} AND {max_val}"
        elif filter_type == 'range' and min_val is not None and max_val is not None:
            having = f"HAVING {agg_expr} BETWEEN {min_val} AND {max_val}"
        elif min_val is not None:
            having = f"HAVING {agg_expr} >= {min_val}"
        elif max_val is not None:
            having = f"HAVING {agg_expr} <= {max_val}"
        else:
            return None

        return f"""
    SELECT {product_col_name} as product_id
    FROM `{self.project_id}.{primary_table}`
    GROUP BY {product_col_name}
    {having}"""

    def _generate_customer_filter_clauses(self, customer_filter, primary_table):
        """
        Generate CTEs and WHERE clauses for customer filters.

        Args:
            customer_filter: Dict with top_revenue, aggregation_filters, category_filters, numeric_filters
            primary_table: Primary table name

        Returns:
            Tuple of (list of CTE tuples, list of WHERE clauses)
        """
        ctes = []
        where_clauses = []

        if not customer_filter:
            return ctes, where_clauses

        # Top revenue filter (top N% customers by revenue)
        top_revenue = customer_filter.get('top_revenue', {})
        if top_revenue.get('enabled'):
            customer_col = top_revenue.get('customer_column')
            revenue_col = top_revenue.get('revenue_column')
            percent = top_revenue.get('percent', 80)

            if customer_col and revenue_col:
                cte = self._generate_top_customers_cte(
                    primary_table, customer_col, revenue_col, percent
                )
                ctes.append(('top_customers', cte))
                where_clauses.append(
                    f"{customer_col} IN (SELECT customer_id FROM top_customers)"
                )

        # Aggregation filters (min transactions, min/max spend, etc.)
        aggregation_filters = customer_filter.get('aggregation_filters', [])
        for af in aggregation_filters:
            agg_type = af.get('type')
            customer_col = af.get('customer_column')
            amount_col = af.get('amount_column')
            filter_type = af.get('filter_type', 'greater_than')
            value = af.get('value')
            min_val = af.get('min')
            max_val = af.get('max')

            if not customer_col:
                continue

            cte_name = f"filtered_customers_{len(ctes)}"
            cte = self._generate_customer_aggregation_cte(
                primary_table, customer_col, amount_col, agg_type, filter_type, value, min_val, max_val
            )
            if cte:
                ctes.append((cte_name, cte))
                where_clauses.append(
                    f"{customer_col} IN (SELECT customer_id FROM {cte_name})"
                )

        # Category filters
        category_filters = customer_filter.get('category_filters', [])
        for cf in category_filters:
            column = cf.get('column')
            mode = cf.get('mode', 'include')
            values = cf.get('values', [])

            if column and values:
                escaped_values = [f"'{v}'" for v in values]
                values_str = ', '.join(escaped_values)

                if mode == 'include':
                    where_clauses.append(f"{column} IN ({values_str})")
                else:
                    where_clauses.append(f"{column} NOT IN ({values_str})")

        # Numeric filters
        numeric_filters = customer_filter.get('numeric_filters', [])
        for nf in numeric_filters:
            column = nf.get('column')
            filter_type = nf.get('type', 'range')
            min_val = nf.get('min')
            max_val = nf.get('max')
            value = nf.get('value')
            include_nulls = nf.get('include_nulls', False)

            if not column:
                continue

            condition = None
            if filter_type == 'range' and min_val is not None and max_val is not None:
                condition = f"{column} BETWEEN {min_val} AND {max_val}"
            elif filter_type == 'greater_than' and value is not None:
                condition = f"{column} > {value}"
            elif filter_type == 'less_than' and value is not None:
                condition = f"{column} < {value}"
            elif filter_type == 'equals' and value is not None:
                condition = f"{column} = {value}"
            elif min_val is not None:
                condition = f"{column} >= {min_val}"
            elif max_val is not None:
                condition = f"{column} <= {max_val}"

            if condition:
                if include_nulls:
                    where_clauses.append(f"({condition} OR {column} IS NULL)")
                else:
                    where_clauses.append(condition)

        return ctes, where_clauses

    def _generate_top_customers_cte(self, primary_table, customer_col, revenue_col, percent):
        """
        Generate CTE for top N% customers by revenue.

        Args:
            primary_table: Full table name
            customer_col: Full column reference for customer ID (e.g., 'customers.customer_id')
            revenue_col: Full column reference for revenue (e.g., 'transactions.total_amount')
            percent: Percentage threshold

        Returns:
            SQL CTE query string

        Note: The CTE queries only the primary table. If customer_col references a different table
        (e.g., 'customers.customer_id'), we use just the column name since customer_id exists
        in the transactions table as a foreign key.
        """
        # Extract just the column names (without table prefix) for the CTE query
        customer_col_name = customer_col.split('.')[-1] if '.' in customer_col else customer_col
        revenue_col_name = revenue_col.split('.')[-1] if '.' in revenue_col else revenue_col

        return f"""
    SELECT {customer_col_name} as customer_id
    FROM (
        SELECT
            {customer_col_name} as customer_id,
            SUM({revenue_col_name}) as total_revenue,
            SUM(SUM({revenue_col_name})) OVER () as grand_total,
            SUM(SUM({revenue_col_name})) OVER (ORDER BY SUM({revenue_col_name}) DESC) as running_total
        FROM `{self.project_id}.{primary_table}`
        GROUP BY {customer_col_name}
    )
    WHERE running_total <= grand_total * {percent / 100}
       OR running_total - total_revenue < grand_total * {percent / 100}"""

    def _generate_customer_aggregation_cte(self, primary_table, customer_col, amount_col,
                                            agg_type, filter_type, value, min_val, max_val):
        """
        Generate CTE for customer aggregation filters (transaction count, total spend, etc.).

        Args:
            primary_table: Full table name
            customer_col: Customer column reference
            amount_col: Amount/revenue column reference (optional for count)
            agg_type: 'transaction_count', 'total_spend', 'avg_spend'
            filter_type: 'greater_than', 'less_than', 'between', 'equals'
            value: Single value for comparison
            min_val: Min value for range
            max_val: Max value for range

        Returns:
            SQL CTE query string or None
        """
        customer_col_name = customer_col.split('.')[-1] if '.' in customer_col else customer_col

        # Determine aggregation function
        if agg_type == 'transaction_count':
            agg_expr = 'COUNT(*)'
        elif agg_type == 'total_spend' and amount_col:
            agg_expr = f'SUM({amount_col})'
        elif agg_type == 'avg_spend' and amount_col:
            agg_expr = f'AVG({amount_col})'
        else:
            return None

        # Build HAVING condition
        if filter_type == 'greater_than' and value is not None:
            having = f"HAVING {agg_expr} > {value}"
        elif filter_type == 'less_than' and value is not None:
            having = f"HAVING {agg_expr} < {value}"
        elif filter_type == 'equals' and value is not None:
            having = f"HAVING {agg_expr} = {value}"
        elif filter_type == 'between' and min_val is not None and max_val is not None:
            having = f"HAVING {agg_expr} BETWEEN {min_val} AND {max_val}"
        elif min_val is not None:
            having = f"HAVING {agg_expr} >= {min_val}"
        elif max_val is not None:
            having = f"HAVING {agg_expr} <= {max_val}"
        else:
            return None

        return f"""
    SELECT {customer_col_name} as customer_id
    FROM `{self.project_id}.{primary_table}`
    GROUP BY {customer_col}
    {having}"""

    # NOTE: generate_train_query, generate_eval_query, and generate_tfx_queries
    # have been removed. Train/eval split is now handled by the Training domain
    # using TFX ExampleGen's built-in split functionality.
    # The base generate_query() method should be used instead.

    # =========================================================================
    # V2 FILTER METHODS - Use source_table parameter for filtered_data CTE support
    # =========================================================================

    def _generate_product_filter_clauses_v2(self, product_filter, source_table, primary_table, skip_row_filters=False):
        """
        Generate CTEs and WHERE clauses for product filters.
        V2: Accepts source_table parameter to use filtered_data CTE when date filter is applied.

        Args:
            product_filter: Dict with top_revenue, aggregation_filters, category_filters,
                           numeric_filters, date_filters
            source_table: Either 'filtered_data' or full table reference
            primary_table: Original primary table name (for column references)
            skip_row_filters: If True, skip category/numeric/date filters (they're already
                             in filtered_data CTE). Only process top_revenue and aggregation
                             filters which need separate CTEs.

        Returns:
            Tuple of (list of CTE tuples, list of WHERE clauses)

        Supported filters:
            - top_revenue: Top N% products by revenue
            - aggregation_filters: Filter by aggregated metrics per product
              (transaction_count, total_revenue)
            - category_filters: Include/exclude specific categorical values (skipped if skip_row_filters)
            - numeric_filters: Range, greater_than, less_than, equals for numeric columns (skipped if skip_row_filters)
            - date_filters: Per-column date filtering (relative or fixed date ranges) (skipped if skip_row_filters)
        """
        ctes = []
        where_clauses = []

        if not product_filter:
            return ctes, where_clauses

        # Top revenue filter (top N% products by revenue)
        top_revenue = product_filter.get('top_revenue', {})
        if top_revenue.get('enabled'):
            product_col = top_revenue.get('product_column')
            revenue_col = top_revenue.get('revenue_column')
            threshold = top_revenue.get('threshold_percent', 80)

            if product_col and revenue_col:
                # Extract just the column names
                product_col_name = product_col.split('.')[-1] if '.' in product_col else product_col
                revenue_col_name = revenue_col.split('.')[-1] if '.' in revenue_col else revenue_col

                cte = f"""
    SELECT {product_col_name} as product_id
    FROM (
        SELECT
            {product_col_name} as product_id,
            SUM({revenue_col_name}) as total_revenue,
            SUM(SUM({revenue_col_name})) OVER () as grand_total,
            SUM(SUM({revenue_col_name})) OVER (ORDER BY SUM({revenue_col_name}) DESC) as running_total
        FROM {source_table}
        GROUP BY {product_col_name}
    )
    WHERE running_total <= grand_total * {threshold / 100}
       OR running_total - total_revenue < grand_total * {threshold / 100}"""
                ctes.append(('top_products', cte))
                where_clauses.append(
                    f"{product_col_name} IN (SELECT product_id FROM top_products)"
                )

        # Aggregation filters (transaction count, total revenue per product)
        aggregation_filters = product_filter.get('aggregation_filters', [])
        for idx, af in enumerate(aggregation_filters):
            agg_type = af.get('type')
            product_col = af.get('product_column')
            amount_col = af.get('amount_column')
            filter_type = af.get('filter_type', 'greater_than')
            value = af.get('value')
            min_val = af.get('min')
            max_val = af.get('max')

            if not product_col:
                continue

            product_col_name = product_col.split('.')[-1] if '.' in product_col else product_col

            # Determine aggregation function
            if agg_type == 'transaction_count':
                agg_expr = 'COUNT(*)'
            elif agg_type == 'total_revenue' and amount_col:
                amount_col_name = amount_col.split('.')[-1] if '.' in amount_col else amount_col
                agg_expr = f'SUM({amount_col_name})'
            else:
                continue

            # Build HAVING condition
            if filter_type == 'greater_than' and value is not None:
                having = f"HAVING {agg_expr} > {value}"
            elif filter_type == 'less_than' and value is not None:
                having = f"HAVING {agg_expr} < {value}"
            elif filter_type == 'equals' and value is not None:
                having = f"HAVING {agg_expr} = {value}"
            elif filter_type in ('between', 'range') and min_val is not None and max_val is not None:
                having = f"HAVING {agg_expr} BETWEEN {min_val} AND {max_val}"
            elif min_val is not None:
                having = f"HAVING {agg_expr} >= {min_val}"
            elif max_val is not None:
                having = f"HAVING {agg_expr} <= {max_val}"
            else:
                continue

            cte_name = f"filtered_products_{len(ctes)}"
            cte = f"""
    SELECT {product_col_name} as product_id
    FROM {source_table}
    GROUP BY {product_col_name}
    {having}"""
            ctes.append((cte_name, cte))
            where_clauses.append(
                f"{product_col_name} IN (SELECT product_id FROM {cte_name})"
            )

        # Category filters (include/exclude specific values)
        # Skip if already applied in filtered_data CTE
        if not skip_row_filters:
            category_filters = product_filter.get('category_filters', [])
            for cf in category_filters:
                column = cf.get('column')
                mode = cf.get('mode', 'include')
                values = cf.get('values', [])

                if column and values:
                    col_name = column.split('.')[-1] if '.' in column else column
                    escaped_values = [f"'{v}'" for v in values]
                    values_str = ', '.join(escaped_values)

                    if mode == 'include':
                        where_clauses.append(f"{col_name} IN ({values_str})")
                    else:
                        where_clauses.append(f"{col_name} NOT IN ({values_str})")

        # Numeric filters
        # Skip if already applied in filtered_data CTE
        if not skip_row_filters:
            numeric_filters = product_filter.get('numeric_filters', [])
            for nf in numeric_filters:
                column = nf.get('column')
                filter_type = nf.get('type', 'range')
                min_val = nf.get('min')
                max_val = nf.get('max')
                value = nf.get('value')
                include_nulls = nf.get('include_nulls', False)

                if not column:
                    continue

                col_name = column.split('.')[-1] if '.' in column else column
                condition = None

                if filter_type == 'range' and min_val is not None and max_val is not None:
                    condition = f"{col_name} BETWEEN {min_val} AND {max_val}"
                elif filter_type == 'greater_than' and value is not None:
                    condition = f"{col_name} > {value}"
                elif filter_type == 'less_than' and value is not None:
                    condition = f"{col_name} < {value}"
                elif filter_type == 'equals' and value is not None:
                    condition = f"{col_name} = {value}"
                elif min_val is not None:
                    condition = f"{col_name} >= {min_val}"
                elif max_val is not None:
                    condition = f"{col_name} <= {max_val}"

                if condition:
                    if include_nulls:
                        where_clauses.append(f"({condition} OR {col_name} IS NULL)")
                    else:
                        where_clauses.append(condition)

        # Date filters (per-column date filtering)
        # Skip if already applied in filtered_data CTE
        if skip_row_filters:
            return ctes, where_clauses
        date_filters = product_filter.get('date_filters', [])
        for df in date_filters:
            column = df.get('column')
            date_type = df.get('date_type', 'fixed')
            relative_option = df.get('relative_option')
            start_date = df.get('start_date')
            end_date = df.get('end_date')
            include_nulls = df.get('include_nulls', False)

            if not column:
                continue

            col_name = column.split('.')[-1] if '.' in column else column
            condition = None

            if date_type == 'relative' and relative_option:
                # Relative date filter using MAX date in source_table
                days_map = {
                    'last_7_days': 7,
                    'last_14_days': 14,
                    'last_30_days': 30,
                    'last_60_days': 60,
                    'last_90_days': 90,
                    'last_180_days': 180,
                    'last_365_days': 365,
                    'last_year': 365,
                    'last_month': 30,
                    'last_week': 7
                }
                days = days_map.get(relative_option)
                if days:
                    condition = f"{col_name} >= TIMESTAMP_SUB((SELECT MAX({col_name}) FROM {source_table}), INTERVAL {days} DAY)"
            elif date_type == 'fixed':
                # Fixed date range
                conditions = []
                if start_date:
                    conditions.append(f"{col_name} >= TIMESTAMP('{start_date}')")
                if end_date:
                    conditions.append(f"{col_name} <= TIMESTAMP('{end_date}')")
                if conditions:
                    condition = ' AND '.join(conditions)

            if condition:
                if include_nulls:
                    where_clauses.append(f"({condition} OR {col_name} IS NULL)")
                else:
                    where_clauses.append(condition)

        return ctes, where_clauses

    def _generate_customer_filter_clauses_v2(self, customer_filter, source_table, primary_table, skip_row_filters=False):
        """
        Generate CTEs and WHERE clauses for customer filters.
        V2: Accepts source_table parameter to use filtered_data CTE when date filter is applied.

        Args:
            customer_filter: Dict with top_revenue, aggregation_filters, category_filters,
                           numeric_filters, date_filters
            source_table: Either 'filtered_data' or full table reference
            primary_table: Original primary table name (for column references)
            skip_row_filters: If True, skip category/numeric/date filters (they're already
                             in filtered_data CTE). Only process top_revenue and aggregation
                             filters which need separate CTEs.

        Returns:
            Tuple of (list of CTE tuples, list of WHERE clauses)

        Supported filters:
            - top_revenue: Top N% customers by revenue
            - aggregation_filters: Filter by aggregated metrics per customer
              (transaction_count, total_spend, avg_spend)
            - category_filters: Include/exclude specific categorical values (skipped if skip_row_filters)
            - numeric_filters: Range, greater_than, less_than, equals for numeric columns (skipped if skip_row_filters)
            - date_filters: Per-column date filtering (relative or fixed date ranges) (skipped if skip_row_filters)
        """
        ctes = []
        where_clauses = []

        if not customer_filter:
            return ctes, where_clauses

        # Top revenue filter (top N% customers by revenue)
        top_revenue = customer_filter.get('top_revenue', {})
        if top_revenue.get('enabled'):
            customer_col = top_revenue.get('customer_column')
            revenue_col = top_revenue.get('revenue_column')
            percent = top_revenue.get('percent', 80)

            if customer_col and revenue_col:
                customer_col_name = customer_col.split('.')[-1] if '.' in customer_col else customer_col
                revenue_col_name = revenue_col.split('.')[-1] if '.' in revenue_col else revenue_col

                cte = f"""
    SELECT {customer_col_name} as customer_id
    FROM (
        SELECT
            {customer_col_name} as customer_id,
            SUM({revenue_col_name}) as total_revenue,
            SUM(SUM({revenue_col_name})) OVER () as grand_total,
            SUM(SUM({revenue_col_name})) OVER (ORDER BY SUM({revenue_col_name}) DESC) as running_total
        FROM {source_table}
        GROUP BY {customer_col_name}
    )
    WHERE running_total <= grand_total * {percent / 100}
       OR running_total - total_revenue < grand_total * {percent / 100}"""
                ctes.append(('top_customers', cte))
                where_clauses.append(
                    f"{customer_col_name} IN (SELECT customer_id FROM top_customers)"
                )

        # Aggregation filters (min transactions, spending, etc.)
        aggregation_filters = customer_filter.get('aggregation_filters', [])
        for idx, af in enumerate(aggregation_filters):
            agg_type = af.get('type')
            customer_col = af.get('customer_column')
            amount_col = af.get('amount_column')
            filter_type = af.get('filter_type', 'greater_than')
            value = af.get('value')
            min_val = af.get('min')
            max_val = af.get('max')

            if not customer_col:
                continue

            customer_col_name = customer_col.split('.')[-1] if '.' in customer_col else customer_col
            amount_col_name = amount_col.split('.')[-1] if amount_col and '.' in amount_col else amount_col

            # Determine aggregation expression
            if agg_type == 'transaction_count':
                agg_expr = 'COUNT(*)'
            elif agg_type == 'total_spend' and amount_col_name:
                agg_expr = f'SUM({amount_col_name})'
            elif agg_type == 'avg_spend' and amount_col_name:
                agg_expr = f'AVG({amount_col_name})'
            else:
                continue

            # Build HAVING condition
            if filter_type == 'greater_than' and value is not None:
                having = f"HAVING {agg_expr} > {value}"
            elif filter_type == 'less_than' and value is not None:
                having = f"HAVING {agg_expr} < {value}"
            elif filter_type == 'equals' and value is not None:
                having = f"HAVING {agg_expr} = {value}"
            elif filter_type == 'between' and min_val is not None and max_val is not None:
                having = f"HAVING {agg_expr} BETWEEN {min_val} AND {max_val}"
            elif min_val is not None:
                having = f"HAVING {agg_expr} >= {min_val}"
            elif max_val is not None:
                having = f"HAVING {agg_expr} <= {max_val}"
            else:
                continue

            cte_name = f"filtered_customers_{idx}"
            cte = f"""
    SELECT {customer_col_name} as customer_id
    FROM {source_table}
    GROUP BY {customer_col_name}
    {having}"""
            ctes.append((cte_name, cte))
            where_clauses.append(f"{customer_col_name} IN (SELECT customer_id FROM {cte_name})")

        # Category filters
        # Skip if already applied in filtered_data CTE
        if not skip_row_filters:
            category_filters = customer_filter.get('category_filters', [])
            for cf in category_filters:
                column = cf.get('column')
                mode = cf.get('mode', 'include')
                values = cf.get('values', [])

                if column and values:
                    col_name = column.split('.')[-1] if '.' in column else column
                    escaped_values = [f"'{v}'" for v in values]
                    values_str = ', '.join(escaped_values)

                    if mode == 'include':
                        where_clauses.append(f"{col_name} IN ({values_str})")
                    else:
                        where_clauses.append(f"{col_name} NOT IN ({values_str})")

        # Numeric filters
        # Skip if already applied in filtered_data CTE
        if not skip_row_filters:
            numeric_filters = customer_filter.get('numeric_filters', [])
            for nf in numeric_filters:
                column = nf.get('column')
                filter_type = nf.get('type', 'range')
                min_val = nf.get('min')
                max_val = nf.get('max')
                value = nf.get('value')
                include_nulls = nf.get('include_nulls', False)

                if not column:
                    continue

                col_name = column.split('.')[-1] if '.' in column else column
                condition = None

                if filter_type == 'range' and min_val is not None and max_val is not None:
                    condition = f"{col_name} BETWEEN {min_val} AND {max_val}"
                elif filter_type == 'greater_than' and value is not None:
                    condition = f"{col_name} > {value}"
                elif filter_type == 'less_than' and value is not None:
                    condition = f"{col_name} < {value}"
                elif filter_type == 'equals' and value is not None:
                    condition = f"{col_name} = {value}"
                elif min_val is not None:
                    condition = f"{col_name} >= {min_val}"
                elif max_val is not None:
                    condition = f"{col_name} <= {max_val}"

                if condition:
                    if include_nulls:
                        where_clauses.append(f"({condition} OR {col_name} IS NULL)")
                    else:
                        where_clauses.append(condition)

        # Date filters (per-column date filtering)
        # Skip if already applied in filtered_data CTE
        if skip_row_filters:
            return ctes, where_clauses
        date_filters = customer_filter.get('date_filters', [])
        for df in date_filters:
            column = df.get('column')
            date_type = df.get('date_type', 'fixed')
            relative_option = df.get('relative_option')
            start_date = df.get('start_date')
            end_date = df.get('end_date')
            include_nulls = df.get('include_nulls', False)

            if not column:
                continue

            col_name = column.split('.')[-1] if '.' in column else column
            condition = None

            if date_type == 'relative' and relative_option:
                # Relative date filter using MAX date in source_table
                days_map = {
                    'last_7_days': 7,
                    'last_14_days': 14,
                    'last_30_days': 30,
                    'last_60_days': 60,
                    'last_90_days': 90,
                    'last_180_days': 180,
                    'last_365_days': 365,
                    'last_year': 365,
                    'last_month': 30,
                    'last_week': 7
                }
                days = days_map.get(relative_option)
                if days:
                    condition = f"{col_name} >= TIMESTAMP_SUB((SELECT MAX({col_name}) FROM {source_table}), INTERVAL {days} DAY)"
            elif date_type == 'fixed':
                # Fixed date range
                conditions = []
                if start_date:
                    conditions.append(f"{col_name} >= TIMESTAMP('{start_date}')")
                if end_date:
                    conditions.append(f"{col_name} <= TIMESTAMP('{end_date}')")
                if conditions:
                    condition = ' AND '.join(conditions)

            if condition:
                if include_nulls:
                    where_clauses.append(f"({condition} OR {col_name} IS NULL)")
                else:
                    where_clauses.append(condition)

        return ctes, where_clauses

    def _generate_top_products_cte_legacy(self, source_table, product_col, revenue_col, percent):
        """Legacy CTE generator that accepts source_table parameter."""
        return f"""
    SELECT {product_col}
    FROM (
        SELECT
            {product_col},
            SUM({revenue_col}) as total_revenue,
            SUM(SUM({revenue_col})) OVER () as grand_total,
            SUM(SUM({revenue_col})) OVER (ORDER BY SUM({revenue_col}) DESC) as running_total
        FROM {source_table}
        GROUP BY {product_col}
    )
    WHERE running_total <= grand_total * {percent / 100}
       OR running_total - total_revenue < grand_total * {percent / 100}"""

    def _generate_active_users_cte_legacy(self, source_table, user_col, min_count):
        """Legacy CTE generator that accepts source_table parameter."""
        return f"""
    SELECT {user_col}
    FROM {source_table}
    GROUP BY {user_col}
    HAVING COUNT(*) >= {min_count}"""

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


# =============================================================================
# PRODUCT REVENUE ANALYSIS SERVICE
# =============================================================================

class ProductRevenueAnalysisService:
    """
    Service for analyzing product revenue distribution.

    Used to filter datasets to include only top-performing products
    based on cumulative revenue threshold (e.g., top 80% of revenue).
    """

    def __init__(self, model_endpoint):
        """
        Initialize the service with a model endpoint.

        Args:
            model_endpoint: ModelEndpoint instance for BigQuery connection
        """
        self.bq_service = BigQueryService(model_endpoint)

    def analyze_distribution(
        self,
        primary_table: str,
        product_column: str,
        revenue_column: str,
        timestamp_column: str = None,
        rolling_days: int = None,
        selected_columns: dict = None,
        join_config: dict = None,
        secondary_tables: list = None,
        filters: dict = None
    ) -> dict:
        """
        Analyze product revenue distribution.

        Args:
            primary_table: Primary table name (e.g., "raw_data.transactions")
            product_column: Column name for product ID (e.g., "transactions.product_id")
            revenue_column: Column name for revenue (e.g., "transactions.amount")
            timestamp_column: Column name for timestamp filtering (optional)
            rolling_days: Number of days for rolling window (optional)
            selected_columns: Dict of table -> columns selected in schema builder
            join_config: Join configuration for secondary tables
            secondary_tables: List of secondary tables
            filters: Dict of filters from other sub-chapters (customer_filter, etc.)

        Returns:
            Dict with distribution analysis:
            {
                "total_products": 48234,
                "total_revenue": 15500000.0,
                "date_range": {"start": "2024-11-03", "end": "2024-12-03"},
                "distribution": [
                    {"percent_products": 1, "cumulative_revenue_percent": 15.2},
                    {"percent_products": 5, "cumulative_revenue_percent": 42.1},
                    ...
                ],
                "thresholds": {
                    "70": {"products": 2891, "percent": 6.0},
                    "80": {"products": 4521, "percent": 9.4},
                    "90": {"products": 8234, "percent": 17.1},
                    "95": {"products": 15234, "percent": 31.6}
                }
            }
        """
        try:
            filters = filters or {}

            # Extract just the column name from "table.column" format
            product_col = self._extract_column_name(product_column)
            revenue_col = self._extract_column_name(revenue_column)
            timestamp_col = self._extract_column_name(timestamp_column) if timestamp_column else None

            # Get the table alias for the primary table
            primary_alias = primary_table.split('.')[-1]
            full_table_ref = self.bq_service._get_full_table_ref(primary_table)

            # Build WHERE clauses
            where_clauses = []
            date_range_query = ""

            # Date filter
            if timestamp_col and rolling_days:
                where_clauses.append(f"""
                    `{primary_alias}`.`{timestamp_col}` >= DATE_SUB(
                        (SELECT MAX(`{timestamp_col}`) FROM `{full_table_ref}`),
                        INTERVAL {rolling_days} DAY
                    )
                """)
                date_range_query = f"""
                SELECT
                    MIN(`{timestamp_col}`) as min_date,
                    MAX(`{timestamp_col}`) as max_date
                FROM `{full_table_ref}`
                WHERE `{timestamp_col}` >= DATE_SUB(
                    (SELECT MAX(`{timestamp_col}`) FROM `{full_table_ref}`),
                    INTERVAL {rolling_days} DAY
                )
                """

            # Customer category filters (e.g., city = 'VINNYTSYA')
            customer_filter = filters.get('customer_filter', {})
            if customer_filter.get('category_filters'):
                for cat_filter in customer_filter['category_filters']:
                    col_ref = cat_filter.get('column', '')
                    col_name = self._extract_column_name(col_ref)
                    # Determine table alias from column reference or use primary
                    if '.' in col_ref:
                        table_alias = col_ref.split('.')[0]
                    else:
                        table_alias = primary_alias

                    values = cat_filter.get('values', [])
                    if values and col_name:
                        # Escape single quotes in values
                        escaped = [v.replace("'", "''") for v in values]
                        values_sql = ", ".join(f"'{v}'" for v in escaped)

                        if cat_filter.get('mode') == 'exclude':
                            where_clauses.append(f"`{table_alias}`.`{col_name}` NOT IN ({values_sql})")
                        else:
                            where_clauses.append(f"`{table_alias}`.`{col_name}` IN ({values_sql})")

            # Customer numeric filters
            if customer_filter.get('numeric_filters'):
                for num_filter in customer_filter['numeric_filters']:
                    col_ref = num_filter.get('column', '')
                    col_name = self._extract_column_name(col_ref)
                    if '.' in col_ref:
                        table_alias = col_ref.split('.')[0]
                    else:
                        table_alias = primary_alias

                    filter_type = num_filter.get('filter_type', 'range')
                    include_nulls = num_filter.get('include_nulls', False)

                    if col_name:
                        conditions = []
                        if filter_type == 'range':
                            min_val = num_filter.get('min')
                            max_val = num_filter.get('max')
                            if min_val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` >= {min_val}")
                            if max_val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` <= {max_val}")
                        elif filter_type == 'greater_than':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` > {val}")
                        elif filter_type == 'less_than':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` < {val}")
                        elif filter_type == 'equals':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` = {val}")

                        if conditions:
                            cond_str = " AND ".join(conditions)
                            if include_nulls:
                                where_clauses.append(f"(({cond_str}) OR `{table_alias}`.`{col_name}` IS NULL)")
                            else:
                                where_clauses.append(f"({cond_str})")

            # Build the final WHERE clause
            where_clause = ""
            if where_clauses:
                where_clause = "WHERE " + " AND ".join(where_clauses)

            # Main analysis query
            analysis_query = f"""
            WITH filtered_data AS (
                SELECT
                    `{primary_alias}`.`{product_col}` as product_id,
                    `{primary_alias}`.`{revenue_col}` as revenue
                FROM `{full_table_ref}` AS `{primary_alias}`
                {where_clause}
            ),
            product_revenues AS (
                SELECT
                    product_id,
                    SUM(revenue) as total_revenue
                FROM filtered_data
                WHERE product_id IS NOT NULL AND revenue IS NOT NULL
                GROUP BY product_id
            ),
            ranked_products AS (
                SELECT
                    product_id,
                    total_revenue,
                    ROW_NUMBER() OVER (ORDER BY total_revenue DESC) as rank,
                    COUNT(*) OVER () as total_products,
                    SUM(total_revenue) OVER () as grand_total,
                    SUM(total_revenue) OVER (ORDER BY total_revenue DESC) as cumulative_revenue
                FROM product_revenues
            ),
            distribution_points AS (
                SELECT
                    rank,
                    total_products,
                    grand_total,
                    cumulative_revenue,
                    ROUND(rank * 100.0 / total_products, 2) as percent_products,
                    ROUND(cumulative_revenue * 100.0 / grand_total, 2) as cumulative_revenue_percent
                FROM ranked_products
            ),
            -- Pre-compute LAG values in a separate CTE (can't nest window functions in aggregates)
            distribution_with_prev AS (
                SELECT
                    rank,
                    total_products,
                    grand_total,
                    cumulative_revenue_percent,
                    LAG(cumulative_revenue_percent, 1, 0) OVER (ORDER BY rank) as prev_cumulative_percent
                FROM distribution_points
            ),
            -- Find first rank that crosses each threshold
            threshold_crossings AS (
                SELECT
                    MIN(CASE WHEN cumulative_revenue_percent >= 70 AND prev_cumulative_percent < 70 THEN rank END) as threshold_70_count,
                    MIN(CASE WHEN cumulative_revenue_percent >= 80 AND prev_cumulative_percent < 80 THEN rank END) as threshold_80_count,
                    MIN(CASE WHEN cumulative_revenue_percent >= 90 AND prev_cumulative_percent < 90 THEN rank END) as threshold_90_count,
                    MIN(CASE WHEN cumulative_revenue_percent >= 95 AND prev_cumulative_percent < 95 THEN rank END) as threshold_95_count
                FROM distribution_with_prev
            )
            SELECT
                -- Summary stats
                (SELECT MAX(total_products) FROM distribution_points) as total_products,
                (SELECT MAX(grand_total) FROM distribution_points) as total_revenue,
                -- Threshold calculations (products needed to reach X% revenue)
                threshold_70_count,
                threshold_80_count,
                threshold_90_count,
                threshold_95_count
            FROM threshold_crossings
            """

            logger.debug(f"Running product revenue analysis query...")
            logger.debug(f"Analysis query:\n{analysis_query}")
            result = self.bq_service.client.query(analysis_query).result()
            rows = list(result)

            if not rows:
                return {
                    'status': 'error',
                    'message': 'Query returned no results',
                    'total_products': 0,
                    'total_revenue': 0,
                }

            row = rows[0]
            logger.debug(f"Query result row: total_products={row.total_products}, total_revenue={row.total_revenue}")

            total_products = row.total_products or 0
            total_revenue = float(row.total_revenue or 0)

            if total_products == 0:
                return {
                    'status': 'error',
                    'message': 'No products found with valid revenue data',
                    'total_products': 0,
                    'total_revenue': 0,
                }

            # Calculate thresholds
            thresholds = {}
            for threshold in [70, 80, 90, 95]:
                count = getattr(row, f'threshold_{threshold}_count', None)
                if count:
                    thresholds[str(threshold)] = {
                        'products': int(count),
                        'percent': round(count * 100.0 / total_products, 2)
                    }

            # Get distribution curve points (sampled for chart)
            distribution, _, _ = self._get_distribution_curve(
                primary_table, primary_alias, product_col, revenue_col,
                timestamp_col, rolling_days, filters=filters
            )

            # Get date range if timestamp filter was applied
            date_range = None
            if date_range_query:
                try:
                    date_result = self.bq_service.client.query(date_range_query).result()
                    date_row = list(date_result)[0]
                    if date_row.min_date and date_row.max_date:
                        date_range = {
                            'start': date_row.min_date.isoformat() if hasattr(date_row.min_date, 'isoformat') else str(date_row.min_date),
                            'end': date_row.max_date.isoformat() if hasattr(date_row.max_date, 'isoformat') else str(date_row.max_date),
                        }
                except Exception as e:
                    logger.warning(f"Could not get date range: {e}")

            return {
                'status': 'success',
                'total_products': total_products,
                'total_revenue': total_revenue,
                'date_range': date_range,
                'distribution': distribution,
                'thresholds': thresholds,
            }

        except Exception as e:
            import traceback
            logger.error(f"Error analyzing product revenue distribution: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise BigQueryServiceError(f"Failed to analyze product revenue: {e}")

    def _get_distribution_curve(
        self,
        primary_table: str,
        primary_alias: str,
        product_col: str,
        revenue_col: str,
        timestamp_col: str = None,
        rolling_days: int = None,
        num_points: int = 50,
        filters: dict = None
    ) -> list:
        """
        Get sampled distribution curve points for charting.

        Returns list of {percent_products, cumulative_revenue_percent} points.
        """
        try:
            filters = filters or {}
            full_table_ref = self.bq_service._get_full_table_ref(primary_table)

            # Build WHERE clauses (same logic as analyze_distribution)
            where_clauses = []

            # Date filter
            if timestamp_col and rolling_days:
                where_clauses.append(f"""
                    `{primary_alias}`.`{timestamp_col}` >= DATE_SUB(
                        (SELECT MAX(`{timestamp_col}`) FROM `{full_table_ref}`),
                        INTERVAL {rolling_days} DAY
                    )
                """)

            # Customer category filters
            customer_filter = filters.get('customer_filter', {})
            if customer_filter.get('category_filters'):
                for cat_filter in customer_filter['category_filters']:
                    col_ref = cat_filter.get('column', '')
                    col_name = self._extract_column_name(col_ref)
                    if '.' in col_ref:
                        table_alias = col_ref.split('.')[0]
                    else:
                        table_alias = primary_alias

                    values = cat_filter.get('values', [])
                    if values and col_name:
                        escaped = [v.replace("'", "''") for v in values]
                        values_sql = ", ".join(f"'{v}'" for v in escaped)

                        if cat_filter.get('mode') == 'exclude':
                            where_clauses.append(f"`{table_alias}`.`{col_name}` NOT IN ({values_sql})")
                        else:
                            where_clauses.append(f"`{table_alias}`.`{col_name}` IN ({values_sql})")

            # Customer numeric filters
            if customer_filter.get('numeric_filters'):
                for num_filter in customer_filter['numeric_filters']:
                    col_ref = num_filter.get('column', '')
                    col_name = self._extract_column_name(col_ref)
                    if '.' in col_ref:
                        table_alias = col_ref.split('.')[0]
                    else:
                        table_alias = primary_alias

                    filter_type = num_filter.get('filter_type', 'range')
                    include_nulls = num_filter.get('include_nulls', False)

                    if col_name:
                        conditions = []
                        if filter_type == 'range':
                            min_val = num_filter.get('min')
                            max_val = num_filter.get('max')
                            if min_val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` >= {min_val}")
                            if max_val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` <= {max_val}")
                        elif filter_type == 'greater_than':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` > {val}")
                        elif filter_type == 'less_than':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` < {val}")
                        elif filter_type == 'equals':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` = {val}")

                        if conditions:
                            cond_str = " AND ".join(conditions)
                            if include_nulls:
                                where_clauses.append(f"(({cond_str}) OR `{table_alias}`.`{col_name}` IS NULL)")
                            else:
                                where_clauses.append(f"({cond_str})")

            # Build the final WHERE clause
            where_clause = ""
            if where_clauses:
                where_clause = "WHERE " + " AND ".join(where_clauses)

            # Query to get distribution curve with sampling
            curve_query = f"""
            WITH filtered_data AS (
                SELECT
                    `{primary_alias}`.`{product_col}` as product_id,
                    `{primary_alias}`.`{revenue_col}` as revenue
                FROM `{full_table_ref}` AS `{primary_alias}`
                {where_clause}
            ),
            product_revenues AS (
                SELECT
                    product_id,
                    SUM(revenue) as total_revenue
                FROM filtered_data
                WHERE product_id IS NOT NULL AND revenue IS NOT NULL
                GROUP BY product_id
            ),
            ranked_products AS (
                SELECT
                    product_id,
                    total_revenue,
                    ROW_NUMBER() OVER (ORDER BY total_revenue DESC) as rank,
                    COUNT(*) OVER () as total_products,
                    SUM(total_revenue) OVER () as grand_total,
                    SUM(total_revenue) OVER (ORDER BY total_revenue DESC) as cumulative_revenue
                FROM product_revenues
            ),
            distribution_points AS (
                SELECT
                    rank,
                    total_products,
                    cumulative_revenue,
                    grand_total,
                    ROUND(rank * 100.0 / total_products, 2) as percent_products,
                    ROUND(cumulative_revenue * 100.0 / grand_total, 2) as cumulative_revenue_percent
                FROM ranked_products
            ),
            -- Find exact threshold crossing points
            threshold_points AS (
                SELECT MIN(rank) as threshold_rank, 'p70' as threshold_type
                FROM distribution_points WHERE cumulative_revenue_percent >= 70
                UNION ALL
                SELECT MIN(rank), 'p80' FROM distribution_points WHERE cumulative_revenue_percent >= 80
                UNION ALL
                SELECT MIN(rank), 'p90' FROM distribution_points WHERE cumulative_revenue_percent >= 90
                UNION ALL
                SELECT MIN(rank), 'p95' FROM distribution_points WHERE cumulative_revenue_percent >= 95
                UNION ALL
                SELECT MIN(rank), 'p100' FROM distribution_points WHERE cumulative_revenue_percent >= 99.9
            ),
            -- Sample points: evenly distributed plus critical points
            sampled AS (
                SELECT DISTINCT dp.*
                FROM distribution_points dp
                WHERE
                    dp.rank = 1  -- First point
                    OR dp.rank = dp.total_products  -- Last point (100%)
                    OR dp.rank IN (SELECT threshold_rank FROM threshold_points WHERE threshold_rank IS NOT NULL)  -- Threshold crossings
                    OR MOD(dp.rank, GREATEST(1, CAST(dp.total_products / {num_points} AS INT64))) = 0  -- Evenly sampled
            )
            SELECT rank as product_count, cumulative_revenue, total_products, grand_total as total_revenue, percent_products, cumulative_revenue_percent
            FROM sampled
            ORDER BY rank
            LIMIT 150
            """

            result = self.bq_service.client.query(curve_query).result()

            distribution = []
            total_products = 0
            total_revenue = 0
            for row in result:
                total_products = int(row.total_products)
                total_revenue = float(row.total_revenue)
                distribution.append({
                    'product_count': int(row.product_count),
                    'cumulative_revenue': float(row.cumulative_revenue),
                    'percent_products': float(row.percent_products),
                    'cumulative_revenue_percent': float(row.cumulative_revenue_percent)
                })

            return distribution, total_products, total_revenue

        except Exception as e:
            logger.warning(f"Error getting distribution curve: {e}")
            # Return minimal distribution if query fails
            return [
                {'product_count': 0, 'cumulative_revenue': 0, 'percent_products': 0, 'cumulative_revenue_percent': 0},
                {'product_count': 1, 'cumulative_revenue': 0, 'percent_products': 100, 'cumulative_revenue_percent': 100}
            ], 0, 0

    def get_products_for_threshold(
        self,
        primary_table: str,
        product_column: str,
        revenue_column: str,
        threshold_percent: int,
        timestamp_column: str = None,
        rolling_days: int = None,
        limit: int = None
    ) -> dict:
        """
        Get the list of products that meet the cumulative revenue threshold.

        Args:
            primary_table: Primary table name
            product_column: Product ID column
            revenue_column: Revenue column
            threshold_percent: Cumulative revenue threshold (e.g., 80 for 80%)
            timestamp_column: Optional timestamp column for date filtering
            rolling_days: Optional rolling window in days
            limit: Optional limit on number of products returned

        Returns:
            Dict with product count and optionally the product list
        """
        try:
            product_col = self._extract_column_name(product_column)
            revenue_col = self._extract_column_name(revenue_column)
            timestamp_col = self._extract_column_name(timestamp_column) if timestamp_column else None
            primary_alias = primary_table.split('.')[-1]

            date_filter_clause = ""
            if timestamp_col and rolling_days:
                date_filter_clause = f"""
                WHERE `{primary_alias}`.`{timestamp_col}` >= DATE_SUB(
                    (SELECT MAX(`{timestamp_col}`) FROM `{self.bq_service._get_full_table_ref(primary_table)}`),
                    INTERVAL {rolling_days} DAY
                )
                """

            threshold_decimal = threshold_percent / 100.0
            limit_clause = f"LIMIT {limit}" if limit else ""

            query = f"""
            WITH filtered_data AS (
                SELECT
                    `{primary_alias}`.`{product_col}` as product_id,
                    `{primary_alias}`.`{revenue_col}` as revenue
                FROM `{self.bq_service._get_full_table_ref(primary_table)}` AS `{primary_alias}`
                {date_filter_clause}
            ),
            product_revenues AS (
                SELECT
                    product_id,
                    SUM(revenue) as total_revenue
                FROM filtered_data
                WHERE product_id IS NOT NULL AND revenue IS NOT NULL
                GROUP BY product_id
            ),
            ranked_products AS (
                SELECT
                    product_id,
                    total_revenue,
                    SUM(total_revenue) OVER () as grand_total,
                    SUM(total_revenue) OVER (ORDER BY total_revenue DESC) as cumulative_revenue
                FROM product_revenues
            )
            SELECT
                product_id,
                total_revenue,
                ROUND(cumulative_revenue * 100.0 / grand_total, 2) as cumulative_percent
            FROM ranked_products
            WHERE cumulative_revenue <= grand_total * {threshold_decimal}
               OR cumulative_revenue - total_revenue < grand_total * {threshold_decimal}
            ORDER BY total_revenue DESC
            {limit_clause}
            """

            result = self.bq_service.client.query(query).result()

            products = []
            for row in result:
                products.append({
                    'product_id': str(row.product_id),
                    'total_revenue': float(row.total_revenue),
                    'cumulative_percent': float(row.cumulative_percent)
                })

            return {
                'status': 'success',
                'threshold_percent': threshold_percent,
                'product_count': len(products),
                'products': products if limit else None,  # Only return list if limited
            }

        except Exception as e:
            logger.error(f"Error getting products for threshold: {e}")
            raise BigQueryServiceError(f"Failed to get products: {e}")

    def _extract_column_name(self, column_ref: str) -> str:
        """
        Extract just the column name from a 'table.column' reference.

        Args:
            column_ref: Column reference like "transactions.product_id"

        Returns:
            Just the column name like "product_id"
        """
        if not column_ref:
            return None
        if '.' in column_ref:
            return column_ref.split('.')[-1]
        return column_ref


# =============================================================================
# CUSTOMER REVENUE ANALYSIS SERVICE
# =============================================================================

class CustomerRevenueAnalysisService:
    """
    Service for analyzing customer revenue distribution using BigQuery.

    Used to filter datasets to include only top-performing customers
    based on cumulative revenue threshold (e.g., top 80% of revenue).

    This service runs aggregation queries directly in BigQuery to handle
    millions of rows efficiently, returning only the distribution curve
    and threshold statistics.
    """

    def __init__(self, model_endpoint):
        """
        Initialize the service with a model endpoint.

        Args:
            model_endpoint: ModelEndpoint instance for BigQuery connection
        """
        self.bq_service = BigQueryService(model_endpoint)

    def analyze_distribution(
        self,
        primary_table: str,
        customer_column: str,
        revenue_column: str,
        timestamp_column: str = None,
        rolling_days: int = None,
        filters: dict = None
    ) -> dict:
        """
        Analyze customer revenue distribution using BigQuery.

        Args:
            primary_table: Primary table name (e.g., "raw_data.transactions")
            customer_column: Column name for customer ID (e.g., "transactions.customer_id")
            revenue_column: Column name for revenue (e.g., "transactions.amount")
            timestamp_column: Column name for timestamp filtering (optional)
            rolling_days: Number of days for rolling window (optional)
            filters: Dict of filters from other sub-chapters (product_filter, etc.)

        Returns:
            Dict with distribution analysis:
            {
                "status": "success",
                "total_customers": 98234,
                "total_revenue": 15500000.0,
                "distribution": [
                    {"customer_percent": 1, "cumulative_revenue_percent": 8.2},
                    {"customer_percent": 5, "cumulative_revenue_percent": 28.1},
                    ...
                ],
                "thresholds": {
                    "70": {"customers": 12891, "percent": 13.1},
                    "80": {"customers": 18521, "percent": 18.9},
                    "90": {"customers": 32234, "percent": 32.8},
                    "95": {"customers": 52234, "percent": 53.2}
                }
            }
        """
        try:
            filters = filters or {}

            # Extract just the column name from "table.column" format
            customer_col = self._extract_column_name(customer_column)
            revenue_col = self._extract_column_name(revenue_column)
            timestamp_col = self._extract_column_name(timestamp_column) if timestamp_column else None

            # Get the table alias for the primary table
            primary_alias = primary_table.split('.')[-1]
            full_table_ref = self.bq_service._get_full_table_ref(primary_table)

            # Build WHERE clauses
            where_clauses = []

            # Date filter
            if timestamp_col and rolling_days:
                where_clauses.append(f"""
                    `{primary_alias}`.`{timestamp_col}` >= DATE_SUB(
                        (SELECT MAX(`{timestamp_col}`) FROM `{full_table_ref}`),
                        INTERVAL {rolling_days} DAY
                    )
                """)

            # Product category filters (e.g., category = 'Electronics')
            product_filter = filters.get('product_filter', {})
            if product_filter.get('category_filters'):
                for cat_filter in product_filter['category_filters']:
                    col_ref = cat_filter.get('column', '')
                    col_name = self._extract_column_name(col_ref)
                    if '.' in col_ref:
                        table_alias = col_ref.split('.')[0]
                    else:
                        table_alias = primary_alias

                    values = cat_filter.get('values', [])
                    if values and col_name:
                        escaped = [v.replace("'", "''") for v in values]
                        values_sql = ", ".join(f"'{v}'" for v in escaped)

                        if cat_filter.get('mode') == 'exclude':
                            where_clauses.append(f"`{table_alias}`.`{col_name}` NOT IN ({values_sql})")
                        else:
                            where_clauses.append(f"`{table_alias}`.`{col_name}` IN ({values_sql})")

            # Product numeric filters
            if product_filter.get('numeric_filters'):
                for num_filter in product_filter['numeric_filters']:
                    col_ref = num_filter.get('column', '')
                    col_name = self._extract_column_name(col_ref)
                    if '.' in col_ref:
                        table_alias = col_ref.split('.')[0]
                    else:
                        table_alias = primary_alias

                    filter_type = num_filter.get('filter_type', 'range')
                    include_nulls = num_filter.get('include_nulls', False)

                    if col_name:
                        conditions = []
                        if filter_type == 'range':
                            min_val = num_filter.get('min')
                            max_val = num_filter.get('max')
                            if min_val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` >= {min_val}")
                            if max_val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` <= {max_val}")
                        elif filter_type == 'greater_than':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` > {val}")
                        elif filter_type == 'less_than':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` < {val}")
                        elif filter_type == 'equals':
                            val = num_filter.get('value')
                            if val is not None:
                                conditions.append(f"`{table_alias}`.`{col_name}` = {val}")

                        if conditions:
                            cond_str = " AND ".join(conditions)
                            if include_nulls:
                                where_clauses.append(f"(({cond_str}) OR `{table_alias}`.`{col_name}` IS NULL)")
                            else:
                                where_clauses.append(f"({cond_str})")

            # Customer category filters (from already committed customer filters, not top_revenue)
            customer_filter = filters.get('customer_filter', {})
            if customer_filter.get('category_filters'):
                for cat_filter in customer_filter['category_filters']:
                    col_ref = cat_filter.get('column', '')
                    col_name = self._extract_column_name(col_ref)
                    if '.' in col_ref:
                        table_alias = col_ref.split('.')[0]
                    else:
                        table_alias = primary_alias

                    values = cat_filter.get('values', [])
                    if values and col_name:
                        escaped = [v.replace("'", "''") for v in values]
                        values_sql = ", ".join(f"'{v}'" for v in escaped)

                        if cat_filter.get('mode') == 'exclude':
                            where_clauses.append(f"`{table_alias}`.`{col_name}` NOT IN ({values_sql})")
                        else:
                            where_clauses.append(f"`{table_alias}`.`{col_name}` IN ({values_sql})")

            # Build the final WHERE clause
            where_clause = ""
            if where_clauses:
                where_clause = "WHERE " + " AND ".join(where_clauses)

            # Main analysis query - similar structure to ProductRevenueAnalysisService
            analysis_query = f"""
            WITH filtered_data AS (
                SELECT
                    `{primary_alias}`.`{customer_col}` as customer_id,
                    `{primary_alias}`.`{revenue_col}` as revenue
                FROM `{full_table_ref}` AS `{primary_alias}`
                {where_clause}
            ),
            customer_revenues AS (
                SELECT
                    customer_id,
                    SUM(revenue) as total_revenue
                FROM filtered_data
                WHERE customer_id IS NOT NULL AND revenue IS NOT NULL
                GROUP BY customer_id
            ),
            ranked_customers AS (
                SELECT
                    customer_id,
                    total_revenue,
                    ROW_NUMBER() OVER (ORDER BY total_revenue DESC) as rank,
                    COUNT(*) OVER () as total_customers,
                    SUM(total_revenue) OVER () as grand_total,
                    SUM(total_revenue) OVER (ORDER BY total_revenue DESC) as cumulative_revenue
                FROM customer_revenues
            ),
            distribution_points AS (
                SELECT
                    rank,
                    total_customers,
                    grand_total,
                    total_revenue,
                    cumulative_revenue,
                    ROUND(rank * 100.0 / total_customers, 2) as customer_percent,
                    ROUND(cumulative_revenue * 100.0 / grand_total, 2) as cumulative_revenue_percent
                FROM ranked_customers
            ),
            -- Sample ~100 points for chart (evenly distributed + key thresholds)
            sampled_points AS (
                SELECT * FROM distribution_points
                WHERE
                    -- First and last points
                    rank = 1 OR rank = total_customers
                    -- Every N-th point for even distribution (target ~50 points)
                    OR MOD(rank, GREATEST(1, CAST(total_customers / 50 AS INT64))) = 0
                    -- Key threshold crossings (around 70%, 80%, 90%, 95%)
                    OR (cumulative_revenue_percent >= 69.5 AND cumulative_revenue_percent <= 70.5)
                    OR (cumulative_revenue_percent >= 79.5 AND cumulative_revenue_percent <= 80.5)
                    OR (cumulative_revenue_percent >= 89.5 AND cumulative_revenue_percent <= 90.5)
                    OR (cumulative_revenue_percent >= 94.5 AND cumulative_revenue_percent <= 95.5)
            )
            SELECT
                customer_percent,
                cumulative_revenue_percent,
                rank,
                total_customers,
                grand_total as total_revenue,
                cumulative_revenue
            FROM sampled_points
            ORDER BY rank
            """

            # Execute the query
            logger.info(f"Executing customer revenue analysis query")
            logger.debug(f"Analysis query:\n{analysis_query}")
            query_result = self.bq_service.client.query(analysis_query).result()
            rows = list(query_result)

            if not rows or len(rows) == 0:
                return {
                    'status': 'error',
                    'message': 'No customer data found',
                    'total_customers': 0,
                    'total_revenue': 0,
                }

            # Extract totals from first row
            total_customers = int(rows[0].total_customers)
            total_revenue = float(rows[0].total_revenue)

            # Build distribution curve
            distribution = []
            for row in rows:
                distribution.append({
                    'customer_percent': float(row.customer_percent),
                    'cumulative_revenue_percent': float(row.cumulative_revenue_percent)
                })

            # Calculate thresholds
            thresholds = self._calculate_thresholds(rows, total_customers)

            return {
                'status': 'success',
                'total_customers': total_customers,
                'total_revenue': total_revenue,
                'distribution': distribution,
                'thresholds': thresholds,
            }

        except Exception as e:
            import traceback
            logger.error(f"Error analyzing customer revenue distribution: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return {
                'status': 'error',
                'message': f'Failed to analyze customer revenue: {str(e)}'
            }

    def _extract_column_name(self, column_ref: str) -> str:
        """Extract just the column name from 'table.column' format."""
        if '.' in column_ref:
            return column_ref.rsplit('.', 1)[1]
        return column_ref

    def _calculate_thresholds(self, rows: list, total_customers: int) -> dict:
        """
        Calculate threshold statistics from distribution results.

        For each threshold (70%, 80%, 90%, 95%), find how many customers
        are needed to cover that percentage of revenue.
        """
        thresholds = {}

        for target in [70, 80, 90, 95]:
            # Find the first row where cumulative_revenue_percent >= target
            for row in rows:
                if row.cumulative_revenue_percent >= target:
                    customers_needed = int(row.rank)
                    thresholds[str(target)] = {
                        'customers': customers_needed,
                        'percent': round(customers_needed * 100.0 / total_customers, 2)
                    }
                    break

        return thresholds


# =============================================================================
# CUSTOMER AGGREGATION SERVICE
# =============================================================================

class CustomerAggregationService:
    """
    Service for analyzing customer aggregations (transaction count, spending).

    Used to help users understand their customer base metrics and set
    appropriate filter thresholds for transaction count and spending filters.

    This service operates on cached pandas DataFrames from a session,
    enabling fast analysis without hitting BigQuery directly.
    """

    def __init__(self, session_data: dict):
        """
        Initialize the service with session data containing cached DataFrames.

        Args:
            session_data: Dict containing session data with:
                         - 'tables': metadata about tables
                         - 'dataframes': serialized DataFrames as dict records
        """
        import pandas as pd

        self.session_data = session_data
        self.tables_metadata = session_data.get('tables', {})

        # Reconstruct DataFrames from serialized records
        self.tables = {}
        dataframes = session_data.get('dataframes', {})
        for table_name, records in dataframes.items():
            if isinstance(records, list):
                self.tables[table_name] = pd.DataFrame(records)
            elif isinstance(records, pd.DataFrame):
                self.tables[table_name] = records

    def analyze_transaction_counts(self, customer_column: str) -> dict:
        """
        Analyze transaction count distribution per customer.

        Args:
            customer_column: Column name for customer ID (e.g., "transactions.customer_id")

        Returns:
            Dict with transaction count analysis:
            {
                "status": "success",
                "total_customers": 98234,
                "total_transactions": 1500000,
                "stats": {
                    "min": 1,
                    "max": 523,
                    "mean": 15.3,
                    "median": 8,
                    "percentiles": {
                        "25": 3,
                        "50": 8,
                        "75": 18,
                        "90": 32,
                        "95": 52
                    }
                },
                "distribution": [
                    {"transaction_count": 1, "customer_count": 12500, "customer_percent": 12.7},
                    {"transaction_count": 2, "customer_count": 8300, "customer_percent": 8.5},
                    ...
                ]
            }
        """
        import pandas as pd
        import numpy as np

        try:
            # Parse column reference
            customer_table, customer_col = self._parse_column_ref(customer_column)

            # Get the DataFrame
            df = self._get_dataframe_for_column(customer_table)
            if df is None:
                return {
                    'status': 'error',
                    'message': f'Table {customer_table} not found in session data'
                }

            if customer_col not in df.columns:
                return {
                    'status': 'error',
                    'message': f'Column {customer_col} not found in table'
                }

            # Count transactions per customer
            txn_counts = df.groupby(customer_col).size().reset_index(name='transaction_count')
            txn_counts = txn_counts.dropna()

            total_customers = len(txn_counts)
            total_transactions = int(txn_counts['transaction_count'].sum())

            if total_customers == 0:
                return {
                    'status': 'error',
                    'message': 'No customers found',
                    'total_customers': 0,
                    'total_transactions': 0,
                }

            # Calculate statistics
            counts = txn_counts['transaction_count']
            stats = {
                'min': int(counts.min()),
                'max': int(counts.max()),
                'mean': round(float(counts.mean()), 2),
                'median': int(counts.median()),
                'percentiles': {
                    '25': int(np.percentile(counts, 25)),
                    '50': int(np.percentile(counts, 50)),
                    '75': int(np.percentile(counts, 75)),
                    '90': int(np.percentile(counts, 90)),
                    '95': int(np.percentile(counts, 95)),
                }
            }

            # Generate distribution (group by transaction count)
            distribution = txn_counts.groupby('transaction_count').size().reset_index(name='customer_count')
            distribution['customer_percent'] = round(distribution['customer_count'] / total_customers * 100, 2)
            distribution = distribution.sort_values('transaction_count').head(50).to_dict('records')

            return {
                'status': 'success',
                'total_customers': total_customers,
                'total_transactions': total_transactions,
                'stats': stats,
                'distribution': distribution,
            }

        except Exception as e:
            logger.error(f"Error analyzing transaction counts: {e}")
            return {
                'status': 'error',
                'message': f'Failed to analyze transaction counts: {str(e)}'
            }

    def analyze_customer_spending(self, customer_column: str, amount_column: str) -> dict:
        """
        Analyze spending distribution per customer.

        Args:
            customer_column: Column name for customer ID (e.g., "transactions.customer_id")
            amount_column: Column name for amount (e.g., "transactions.amount")

        Returns:
            Dict with spending analysis:
            {
                "status": "success",
                "total_customers": 98234,
                "total_spending": 15500000.0,
                "stats": {
                    "min": 0.50,
                    "max": 152300.00,
                    "mean": 157.85,
                    "median": 82.50,
                    "percentiles": {
                        "25": 35.00,
                        "50": 82.50,
                        "75": 185.00,
                        "90": 380.00,
                        "95": 625.00
                    }
                }
            }
        """
        import pandas as pd
        import numpy as np

        try:
            # Parse column references
            customer_table, customer_col = self._parse_column_ref(customer_column)
            amount_table, amount_col = self._parse_column_ref(amount_column)

            # Get the DataFrame
            df = self._get_dataframe_for_column(customer_table)
            if df is None:
                return {
                    'status': 'error',
                    'message': f'Table {customer_table} not found in session data'
                }

            if customer_col not in df.columns:
                return {
                    'status': 'error',
                    'message': f'Column {customer_col} not found in table'
                }
            if amount_col not in df.columns:
                return {
                    'status': 'error',
                    'message': f'Column {amount_col} not found in table'
                }

            # Sum spending per customer
            spending = df.groupby(customer_col)[amount_col].sum().reset_index()
            spending.columns = ['customer_id', 'total_spending']
            spending = spending.dropna()
            spending = spending[spending['total_spending'] > 0]

            total_customers = len(spending)
            total_spending = float(spending['total_spending'].sum())

            if total_customers == 0:
                return {
                    'status': 'error',
                    'message': 'No customers found with valid spending data',
                    'total_customers': 0,
                    'total_spending': 0,
                }

            # Calculate statistics
            amounts = spending['total_spending']
            stats = {
                'min': round(float(amounts.min()), 2),
                'max': round(float(amounts.max()), 2),
                'mean': round(float(amounts.mean()), 2),
                'median': round(float(amounts.median()), 2),
                'percentiles': {
                    '25': round(float(np.percentile(amounts, 25)), 2),
                    '50': round(float(np.percentile(amounts, 50)), 2),
                    '75': round(float(np.percentile(amounts, 75)), 2),
                    '90': round(float(np.percentile(amounts, 90)), 2),
                    '95': round(float(np.percentile(amounts, 95)), 2),
                }
            }

            return {
                'status': 'success',
                'total_customers': total_customers,
                'total_spending': total_spending,
                'stats': stats,
            }

        except Exception as e:
            logger.error(f"Error analyzing customer spending: {e}")
            return {
                'status': 'error',
                'message': f'Failed to analyze customer spending: {str(e)}'
            }

    def _parse_column_ref(self, column_ref: str) -> tuple:
        """Parse a column reference like "table.column" into (table, column)."""
        if '.' in column_ref:
            parts = column_ref.rsplit('.', 1)
            return parts[0], parts[1]
        return None, column_ref

    def _get_dataframe_for_column(self, table_hint: str):
        """Get the DataFrame containing a column."""
        import pandas as pd

        for table_name, df in self.tables.items():
            if table_name == table_hint or table_name.endswith(f'.{table_hint}') or table_name.split('.')[-1] == table_hint:
                return df

        for table_name, df in self.tables.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df

        return None


# =============================================================================
# DATASET STATS SERVICE
# =============================================================================

class DatasetStatsService:
    """
    Service for calculating dataset statistics with optional filters.

    Used to show users how filter parameters impact the dataset size and
    provide high-level statistics about columns (min/max for numeric,
    unique counts for strings/dates).

    Two main use cases:
    1. Initial load (no filters) - shows raw dataset stats
    2. With filters applied - shows filtered dataset stats
    """

    def __init__(self, model_endpoint):
        """
        Initialize the service with a model endpoint.

        Args:
            model_endpoint: ModelEndpoint instance for BigQuery connection
        """
        self.bq_service = BigQueryService(model_endpoint)

    def get_dataset_stats(
        self,
        primary_table: str,
        selected_columns: dict,
        secondary_tables: list = None,
        join_config: dict = None,
        filters: dict = None
    ) -> dict:
        """
        Get comprehensive statistics for a dataset configuration.

        Args:
            primary_table: Primary table name (e.g., "raw_data.transactions")
            selected_columns: Dict of table -> list of column names selected in Schema Builder
            secondary_tables: Optional list of secondary tables
            join_config: Optional join configuration for secondary tables
            filters: Optional filters dict:
                {
                    "timestamp_column": "transactions.trans_date",
                    "date_filter": {"type": "rolling", "days": 30} | {"type": "fixed", "start_date": "2024-01-01"},
                    "customer_filter": {"type": "min_transactions", "column": "customer_id", "value": 2},
                    "product_filter": {"type": "top_revenue", "product_column": "product_id", "revenue_column": "amount", "percent": 80}
                }

        Returns:
            Dict with dataset statistics:
            {
                "status": "success",
                "filters_applied": {...},
                "summary": {
                    "total_rows": 2450000,
                    "unique_customers": 98000,
                    "unique_products": 36000,
                    "date_range": {"min": "2024-06-01", "max": "2024-12-03"}
                },
                "column_stats": {
                    "transactions.amount": {"type": "FLOAT64", "min": 0.5, "max": 12450, "avg": 45.67},
                    ...
                }
            }
        """
        try:
            filters = filters or {}
            primary_alias = primary_table.split('.')[-1]

            # Build the filtered dataset query
            base_query, applied_filters = self._build_filtered_query(
                primary_table,
                selected_columns,
                secondary_tables,
                join_config,
                filters
            )

            # Get summary statistics
            summary = self._get_summary_stats(base_query, selected_columns, filters)

            # Get column-level statistics
            column_stats = self._get_column_stats(base_query, selected_columns)

            return {
                'status': 'success',
                'filters_applied': applied_filters,
                'summary': summary,
                'column_stats': column_stats
            }

        except Exception as e:
            import traceback
            logger.error(f"Error getting dataset stats: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return {
                'status': 'error',
                'message': str(e),
                'filters_applied': self._format_applied_filters(filters or {}),
                'summary': {},
                'column_stats': {}
            }

    def _build_filtered_query(
        self,
        primary_table: str,
        selected_columns: dict,
        secondary_tables: list,
        join_config: dict,
        filters: dict
    ) -> tuple:
        """
        Build the base filtered query for stats calculation.

        Returns:
            Tuple of (query_string, applied_filters_dict)
        """
        primary_alias = primary_table.split('.')[-1]
        full_table_ref = self.bq_service._get_full_table_ref(primary_table)

        # Track what filters are actually applied
        applied_filters = {
            'dates': {'type': 'none'},
            'customers': {'type': 'none'},
            'products': {'type': 'none'}
        }

        # Build SELECT clause with all selected columns
        select_parts = []
        for table, columns in selected_columns.items():
            table_alias = table.replace('raw_data.', '')
            for col in columns:
                select_parts.append(f"`{table_alias}`.`{col}` AS `{table_alias}_{col}`")

        if not select_parts:
            select_parts = [f"`{primary_alias}`.*"]

        # Build FROM clause
        from_clause = f"`{full_table_ref}` AS `{primary_alias}`"

        # Build JOIN clauses
        join_clauses = []
        if secondary_tables and join_config:
            for sec_table in secondary_tables:
                sec_alias = sec_table.replace('raw_data.', '')
                sec_full_ref = self.bq_service._get_full_table_ref(sec_table)
                sec_config = join_config.get(sec_table, {})

                join_key = sec_config.get('join_key', 'id')
                secondary_column = sec_config.get('secondary_column', join_key)
                join_type = sec_config.get('join_type', 'LEFT').upper()

                join_clauses.append(
                    f"{join_type} JOIN `{sec_full_ref}` AS `{sec_alias}` "
                    f"ON `{primary_alias}`.`{join_key}` = `{sec_alias}`.`{secondary_column}`"
                )

        # Build WHERE clauses
        where_clauses = []
        ctes = []

        # Date filter
        timestamp_col = filters.get('timestamp_column')
        date_filter = filters.get('date_filter', {})

        if timestamp_col and date_filter.get('type'):
            ts_col_name = self._extract_column_name(timestamp_col)

            if date_filter['type'] == 'rolling':
                days = date_filter.get('days', 30)
                where_clauses.append(f"""
                    `{primary_alias}`.`{ts_col_name}` >= DATE_SUB(
                        (SELECT MAX(`{ts_col_name}`) FROM `{full_table_ref}`),
                        INTERVAL {days} DAY
                    )
                """)
                applied_filters['dates'] = {'type': 'rolling', 'days': days, 'column': timestamp_col}

            elif date_filter['type'] == 'fixed':
                start_date = date_filter.get('start_date')
                if start_date:
                    where_clauses.append(f"`{primary_alias}`.`{ts_col_name}` >= '{start_date}'")
                    applied_filters['dates'] = {'type': 'fixed', 'start_date': start_date, 'column': timestamp_col}

        # Customer filters (new structure with top_revenue, aggregation_filters, category_filters, etc.)
        customer_filter = filters.get('customer_filter', {})
        customer_filter_summary = []  # Track all applied customer filters for badge display
        customer_cte_counter = 0  # Counter for unique CTE names

        # Legacy support: handle old 'type': 'min_transactions' format
        if customer_filter.get('type') == 'min_transactions':
            customer_col = self._extract_column_name(customer_filter.get('column'))
            min_value = customer_filter.get('value', 2)

            if customer_col:
                cte = f"""
                    SELECT `{customer_col}`
                    FROM `{full_table_ref}`
                    GROUP BY `{customer_col}`
                    HAVING COUNT(*) >= {min_value}
                """
                ctes.append(('active_customers', cte))
                where_clauses.append(
                    f"`{primary_alias}`.`{customer_col}` IN (SELECT `{customer_col}` FROM active_customers)"
                )
                customer_filter_summary.append({'type': 'min_transactions', 'value': min_value})

        # New structure: top_revenue as nested object (Pareto-based customer filtering)
        top_revenue = customer_filter.get('top_revenue', {})
        if top_revenue.get('customer_column') and top_revenue.get('revenue_column'):
            customer_col = self._extract_column_name(top_revenue.get('customer_column'))
            revenue_col = self._extract_column_name(top_revenue.get('revenue_column'))
            percent = top_revenue.get('percent', 80)

            if customer_col and revenue_col:
                cte = f"""
                    SELECT `{customer_col}`
                    FROM (
                        SELECT
                            `{customer_col}`,
                            SUM(`{revenue_col}`) as total_revenue,
                            SUM(SUM(`{revenue_col}`)) OVER () as grand_total,
                            SUM(SUM(`{revenue_col}`)) OVER (ORDER BY SUM(`{revenue_col}`) DESC) as running_total
                        FROM `{full_table_ref}`
                        GROUP BY `{customer_col}`
                    )
                    WHERE running_total <= grand_total * {percent / 100}
                       OR running_total - total_revenue < grand_total * {percent / 100}
                """
                ctes.append(('top_customers', cte))
                where_clauses.append(
                    f"`{primary_alias}`.`{customer_col}` IN (SELECT `{customer_col}` FROM top_customers)"
                )
                customer_filter_summary.append({
                    'type': 'top_revenue',
                    'percent': percent,
                    'customer_column': top_revenue.get('customer_column'),
                    'revenue_column': top_revenue.get('revenue_column')
                })

        # Aggregation filters (transaction count, spending)
        aggregation_filters = customer_filter.get('aggregation_filters', [])
        for agg_filter in aggregation_filters:
            agg_type = agg_filter.get('type')  # 'transaction_count' or 'spending'
            customer_col = self._extract_column_name(agg_filter.get('customer_column'))
            filter_type = agg_filter.get('filter_type', 'greater_than')  # 'greater_than', 'less_than', 'range'

            if not customer_col:
                continue

            customer_cte_counter += 1
            cte_name = f"customer_agg_{customer_cte_counter}"

            if agg_type == 'transaction_count':
                # Build HAVING clause based on filter_type
                having_conditions = []
                if filter_type == 'greater_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"COUNT(*) > {value}")
                elif filter_type == 'less_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"COUNT(*) < {value}")
                elif filter_type == 'range':
                    min_val = agg_filter.get('min')
                    max_val = agg_filter.get('max')
                    if min_val is not None:
                        having_conditions.append(f"COUNT(*) >= {min_val}")
                    if max_val is not None:
                        having_conditions.append(f"COUNT(*) <= {max_val}")

                if having_conditions:
                    cte = f"""
                        SELECT `{customer_col}`
                        FROM `{full_table_ref}`
                        GROUP BY `{customer_col}`
                        HAVING {' AND '.join(having_conditions)}
                    """
                    ctes.append((cte_name, cte))
                    where_clauses.append(
                        f"`{primary_alias}`.`{customer_col}` IN (SELECT `{customer_col}` FROM {cte_name})"
                    )
                    customer_filter_summary.append({
                        'type': 'transaction_count',
                        'filter_type': filter_type,
                        'value': agg_filter.get('value'),
                        'min': agg_filter.get('min'),
                        'max': agg_filter.get('max')
                    })

            elif agg_type == 'spending':
                amount_col = self._extract_column_name(agg_filter.get('amount_column'))
                if not amount_col:
                    continue

                # Build HAVING clause based on filter_type
                having_conditions = []
                if filter_type == 'greater_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"SUM(`{amount_col}`) > {value}")
                elif filter_type == 'less_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"SUM(`{amount_col}`) < {value}")
                elif filter_type == 'range':
                    min_val = agg_filter.get('min')
                    max_val = agg_filter.get('max')
                    if min_val is not None:
                        having_conditions.append(f"SUM(`{amount_col}`) >= {min_val}")
                    if max_val is not None:
                        having_conditions.append(f"SUM(`{amount_col}`) <= {max_val}")

                if having_conditions:
                    cte = f"""
                        SELECT `{customer_col}`
                        FROM `{full_table_ref}`
                        GROUP BY `{customer_col}`
                        HAVING {' AND '.join(having_conditions)}
                    """
                    ctes.append((cte_name, cte))
                    where_clauses.append(
                        f"`{primary_alias}`.`{customer_col}` IN (SELECT `{customer_col}` FROM {cte_name})"
                    )
                    customer_filter_summary.append({
                        'type': 'spending',
                        'filter_type': filter_type,
                        'value': agg_filter.get('value'),
                        'min': agg_filter.get('min'),
                        'max': agg_filter.get('max')
                    })

        # Customer category filters (IN / NOT IN for STRING columns)
        customer_category_filters = customer_filter.get('category_filters', [])
        for cat_filter in customer_category_filters:
            column = cat_filter.get('column')  # Format: "table.column"
            mode = cat_filter.get('mode', 'include')  # 'include' or 'exclude'
            values = cat_filter.get('values', [])

            if column and values:
                col_name = self._extract_column_name(column)
                if '.' in column:
                    table_alias = column.split('.')[0]
                else:
                    table_alias = primary_alias

                # Build SQL values list with proper escaping
                escaped_values = [v.replace("'", "''") for v in values]
                values_sql = ", ".join(f"'{v}'" for v in escaped_values)

                if mode == 'include':
                    where_clauses.append(f"`{table_alias}`.`{col_name}` IN ({values_sql})")
                else:  # exclude
                    where_clauses.append(f"`{table_alias}`.`{col_name}` NOT IN ({values_sql})")

                customer_filter_summary.append({
                    'type': 'category',
                    'column': column,
                    'mode': mode,
                    'count': len(values)
                })

        # Customer numeric filters (range, greater_than, less_than, equals, not_equals)
        customer_numeric_filters = customer_filter.get('numeric_filters', [])
        for num_filter in customer_numeric_filters:
            column = num_filter.get('column')
            filter_type = num_filter.get('filter_type', 'range')
            include_nulls = num_filter.get('include_nulls', True)

            if not column:
                continue

            col_name = self._extract_column_name(column)
            if '.' in column:
                table_alias = column.split('.')[0]
            else:
                table_alias = primary_alias

            col_ref = f"`{table_alias}`.`{col_name}`"
            conditions = []

            if filter_type == 'range':
                min_val = num_filter.get('min')
                max_val = num_filter.get('max')

                range_conditions = []
                if min_val is not None:
                    range_conditions.append(f"{col_ref} >= {min_val}")
                if max_val is not None:
                    range_conditions.append(f"{col_ref} <= {max_val}")

                if range_conditions:
                    if include_nulls:
                        conditions.append(f"(({' AND '.join(range_conditions)}) OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({' AND '.join(range_conditions)} AND {col_ref} IS NOT NULL)")

                customer_filter_summary.append({
                    'type': 'numeric_range',
                    'column': column,
                    'min': min_val,
                    'max': max_val
                })

            elif filter_type in ('equals', 'not_equals', 'greater_than', 'less_than'):
                value = num_filter.get('value')
                if value is not None:
                    op = {'equals': '=', 'not_equals': '!=', 'greater_than': '>', 'less_than': '<'}[filter_type]
                    if include_nulls:
                        conditions.append(f"({col_ref} {op} {value} OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({col_ref} {op} {value} AND {col_ref} IS NOT NULL)")

                    customer_filter_summary.append({
                        'type': f'numeric_{filter_type}',
                        'column': column,
                        'value': value
                    })

            for cond in conditions:
                where_clauses.append(cond)

        # Customer date filters
        customer_date_filters = customer_filter.get('date_filters', [])
        for date_filter in customer_date_filters:
            column = date_filter.get('column')
            date_type = date_filter.get('date_type', 'relative')  # 'relative' or 'range'
            include_nulls = date_filter.get('include_nulls', True)

            if not column:
                continue

            col_name = self._extract_column_name(column)
            if '.' in column:
                table_alias = column.split('.')[0]
            else:
                table_alias = primary_alias

            col_ref = f"`{table_alias}`.`{col_name}`"
            conditions = []

            if date_type == 'relative':
                relative_option = date_filter.get('relative_option', 'last_30_days')
                days_map = {
                    'last_7_days': 7,
                    'last_30_days': 30,
                    'last_90_days': 90,
                    'last_365_days': 365
                }
                if relative_option in days_map:
                    days = days_map[relative_option]
                    date_condition = f"{col_ref} >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)"
                    if include_nulls:
                        conditions.append(f"({date_condition} OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({date_condition} AND {col_ref} IS NOT NULL)")

                    customer_filter_summary.append({
                        'type': 'date_relative',
                        'column': column,
                        'option': relative_option
                    })

            elif date_type == 'range':
                start_date = date_filter.get('start_date')
                end_date = date_filter.get('end_date')

                range_conditions = []
                if start_date:
                    range_conditions.append(f"{col_ref} >= '{start_date}'")
                if end_date:
                    range_conditions.append(f"{col_ref} <= '{end_date}'")

                if range_conditions:
                    if include_nulls:
                        conditions.append(f"(({' AND '.join(range_conditions)}) OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({' AND '.join(range_conditions)} AND {col_ref} IS NOT NULL)")

                    customer_filter_summary.append({
                        'type': 'date_range',
                        'column': column,
                        'start_date': start_date,
                        'end_date': end_date
                    })

            for cond in conditions:
                where_clauses.append(cond)

        # Set applied_filters['customers'] based on what was applied
        if customer_filter_summary:
            applied_filters['customers'] = {
                'type': 'multiple',
                'filters': customer_filter_summary,
                'count': len(customer_filter_summary)
            }

        # Product filters (new structure with top_revenue, category_filters, numeric_filters)
        product_filter = filters.get('product_filter', {})
        product_filter_summary = []  # Track all applied product filters for badge display

        # Legacy support: handle old 'type': 'top_revenue' format
        if product_filter.get('type') == 'top_revenue':
            product_col = self._extract_column_name(product_filter.get('product_column'))
            revenue_col = self._extract_column_name(product_filter.get('revenue_column'))
            percent = product_filter.get('percent', 80)

            if product_col and revenue_col:
                cte = f"""
                    SELECT `{product_col}`
                    FROM (
                        SELECT
                            `{product_col}`,
                            SUM(`{revenue_col}`) as total_revenue,
                            SUM(SUM(`{revenue_col}`)) OVER () as grand_total,
                            SUM(SUM(`{revenue_col}`)) OVER (ORDER BY SUM(`{revenue_col}`) DESC) as running_total
                        FROM `{full_table_ref}`
                        GROUP BY `{product_col}`
                    )
                    WHERE running_total <= grand_total * {percent / 100}
                       OR running_total - total_revenue < grand_total * {percent / 100}
                """
                ctes.append(('top_products', cte))
                where_clauses.append(
                    f"`{primary_alias}`.`{product_col}` IN (SELECT `{product_col}` FROM top_products)"
                )
                product_filter_summary.append({
                    'type': 'top_revenue',
                    'percent': percent,
                    'product_column': product_filter.get('product_column'),
                    'revenue_column': product_filter.get('revenue_column')
                })

        # New structure: top_revenue as nested object
        top_revenue = product_filter.get('top_revenue', {})
        if top_revenue.get('enabled'):
            product_col = self._extract_column_name(top_revenue.get('product_column'))
            revenue_col = self._extract_column_name(top_revenue.get('revenue_column'))
            percent = top_revenue.get('threshold_percent', 80)

            if product_col and revenue_col:
                cte = f"""
                    SELECT `{product_col}`
                    FROM (
                        SELECT
                            `{product_col}`,
                            SUM(`{revenue_col}`) as total_revenue,
                            SUM(SUM(`{revenue_col}`)) OVER () as grand_total,
                            SUM(SUM(`{revenue_col}`)) OVER (ORDER BY SUM(`{revenue_col}`) DESC) as running_total
                        FROM `{full_table_ref}`
                        GROUP BY `{product_col}`
                    )
                    WHERE running_total <= grand_total * {percent / 100}
                       OR running_total - total_revenue < grand_total * {percent / 100}
                """
                ctes.append(('top_products', cte))
                where_clauses.append(
                    f"`{primary_alias}`.`{product_col}` IN (SELECT `{product_col}` FROM top_products)"
                )
                product_filter_summary.append({
                    'type': 'top_revenue',
                    'percent': percent,
                    'product_column': top_revenue.get('product_column'),
                    'revenue_column': top_revenue.get('revenue_column')
                })

        # Aggregation filters (transaction count, total revenue per product)
        product_agg_filters = product_filter.get('aggregation_filters', [])
        product_cte_counter = 0
        for agg_filter in product_agg_filters:
            agg_type = agg_filter.get('type')  # 'transaction_count' or 'total_revenue'
            product_col = self._extract_column_name(agg_filter.get('product_column'))
            filter_type = agg_filter.get('filter_type', 'greater_than')

            if not product_col:
                continue

            product_cte_counter += 1
            cte_name = f"product_agg_{product_cte_counter}"

            if agg_type == 'transaction_count':
                # Build HAVING clause based on filter_type
                having_conditions = []
                if filter_type == 'greater_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"COUNT(*) > {value}")
                elif filter_type == 'less_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"COUNT(*) < {value}")
                elif filter_type == 'range':
                    min_val = agg_filter.get('min')
                    max_val = agg_filter.get('max')
                    if min_val is not None:
                        having_conditions.append(f"COUNT(*) >= {min_val}")
                    if max_val is not None:
                        having_conditions.append(f"COUNT(*) <= {max_val}")

                if having_conditions:
                    cte = f"""
                        SELECT `{product_col}`
                        FROM `{full_table_ref}`
                        GROUP BY `{product_col}`
                        HAVING {' AND '.join(having_conditions)}
                    """
                    ctes.append((cte_name, cte))
                    where_clauses.append(
                        f"`{primary_alias}`.`{product_col}` IN (SELECT `{product_col}` FROM {cte_name})"
                    )
                    product_filter_summary.append({
                        'type': 'transaction_count',
                        'filter_type': filter_type,
                        'value': agg_filter.get('value'),
                        'min': agg_filter.get('min'),
                        'max': agg_filter.get('max'),
                        'product_column': agg_filter.get('product_column')
                    })

            elif agg_type == 'total_revenue':
                amount_col = self._extract_column_name(agg_filter.get('amount_column'))
                if not amount_col:
                    continue

                # Build HAVING clause based on filter_type
                having_conditions = []
                if filter_type == 'greater_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"SUM(`{amount_col}`) > {value}")
                elif filter_type == 'less_than':
                    value = agg_filter.get('value', 0)
                    having_conditions.append(f"SUM(`{amount_col}`) < {value}")
                elif filter_type == 'range':
                    min_val = agg_filter.get('min')
                    max_val = agg_filter.get('max')
                    if min_val is not None:
                        having_conditions.append(f"SUM(`{amount_col}`) >= {min_val}")
                    if max_val is not None:
                        having_conditions.append(f"SUM(`{amount_col}`) <= {max_val}")

                if having_conditions:
                    cte = f"""
                        SELECT `{product_col}`
                        FROM `{full_table_ref}`
                        GROUP BY `{product_col}`
                        HAVING {' AND '.join(having_conditions)}
                    """
                    ctes.append((cte_name, cte))
                    where_clauses.append(
                        f"`{primary_alias}`.`{product_col}` IN (SELECT `{product_col}` FROM {cte_name})"
                    )
                    product_filter_summary.append({
                        'type': 'total_revenue',
                        'filter_type': filter_type,
                        'value': agg_filter.get('value'),
                        'min': agg_filter.get('min'),
                        'max': agg_filter.get('max'),
                        'product_column': agg_filter.get('product_column'),
                        'amount_column': agg_filter.get('amount_column')
                    })

        # Category filters (IN / NOT IN for STRING columns)
        category_filters = product_filter.get('category_filters', [])
        for i, cat_filter in enumerate(category_filters):
            column = cat_filter.get('column')  # Format: "table.column"
            mode = cat_filter.get('mode', 'include')  # 'include' or 'exclude'
            values = cat_filter.get('values', [])

            if column and values:
                # Parse column reference
                col_name = self._extract_column_name(column)
                # Determine table alias from column format
                if '.' in column:
                    table_alias = column.split('.')[0]
                else:
                    table_alias = primary_alias

                # Build SQL values list with proper escaping
                escaped_values = [v.replace("'", "''") for v in values]
                values_sql = ", ".join(f"'{v}'" for v in escaped_values)

                if mode == 'include':
                    where_clauses.append(f"`{table_alias}`.`{col_name}` IN ({values_sql})")
                else:  # exclude
                    where_clauses.append(f"`{table_alias}`.`{col_name}` NOT IN ({values_sql})")

                product_filter_summary.append({
                    'type': 'category',
                    'column': column,
                    'mode': mode,
                    'count': len(values)
                })

        # Numeric filters (range, greater_than, less_than, equals, not_equals for INTEGER/FLOAT columns)
        numeric_filters = product_filter.get('numeric_filters', [])
        for i, num_filter in enumerate(numeric_filters):
            column = num_filter.get('column')  # Format: "table.column"
            filter_type = num_filter.get('type', 'range')  # 'range', 'equals', 'not_equals'
            include_nulls = num_filter.get('include_nulls', True)

            if not column:
                continue

            # Parse column reference
            col_name = self._extract_column_name(column)
            if '.' in column:
                table_alias = column.split('.')[0]
            else:
                table_alias = primary_alias

            col_ref = f"`{table_alias}`.`{col_name}`"
            conditions = []

            if filter_type == 'range':
                min_val = num_filter.get('min')
                max_val = num_filter.get('max')

                range_conditions = []
                if min_val is not None:
                    range_conditions.append(f"{col_ref} >= {min_val}")
                if max_val is not None:
                    range_conditions.append(f"{col_ref} <= {max_val}")

                if range_conditions:
                    if include_nulls:
                        # Include NULLs: (condition OR column IS NULL)
                        conditions.append(f"(({' AND '.join(range_conditions)}) OR {col_ref} IS NULL)")
                    else:
                        # Exclude NULLs: condition AND column IS NOT NULL
                        conditions.append(f"({' AND '.join(range_conditions)} AND {col_ref} IS NOT NULL)")

                product_filter_summary.append({
                    'type': 'numeric_range',
                    'column': column,
                    'min': min_val,
                    'max': max_val
                })

            elif filter_type == 'equals':
                value = num_filter.get('value')
                if value is not None:
                    if include_nulls:
                        conditions.append(f"({col_ref} = {value} OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({col_ref} = {value} AND {col_ref} IS NOT NULL)")

                    product_filter_summary.append({
                        'type': 'numeric_equals',
                        'column': column,
                        'value': value
                    })

            elif filter_type == 'not_equals':
                value = num_filter.get('value')
                if value is not None:
                    if include_nulls:
                        conditions.append(f"({col_ref} != {value} OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({col_ref} != {value} AND {col_ref} IS NOT NULL)")

                    product_filter_summary.append({
                        'type': 'numeric_not_equals',
                        'column': column,
                        'value': value
                    })

            elif filter_type == 'greater_than':
                value = num_filter.get('value')
                if value is not None:
                    if include_nulls:
                        conditions.append(f"({col_ref} > {value} OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({col_ref} > {value} AND {col_ref} IS NOT NULL)")

                    product_filter_summary.append({
                        'type': 'numeric_greater_than',
                        'column': column,
                        'value': value
                    })

            elif filter_type == 'less_than':
                value = num_filter.get('value')
                if value is not None:
                    if include_nulls:
                        conditions.append(f"({col_ref} < {value} OR {col_ref} IS NULL)")
                    else:
                        conditions.append(f"({col_ref} < {value} AND {col_ref} IS NOT NULL)")

                    product_filter_summary.append({
                        'type': 'numeric_less_than',
                        'column': column,
                        'value': value
                    })

            # Add all conditions for this numeric filter
            for cond in conditions:
                where_clauses.append(cond)

        # Set applied_filters['products'] based on what was applied
        if product_filter_summary:
            applied_filters['products'] = {
                'type': 'multiple',
                'filters': product_filter_summary,
                'count': len(product_filter_summary)
            }
        else:
            applied_filters['products'] = {'type': 'none'}

        # Build final query
        query_parts = []

        if ctes:
            cte_strings = [f"{name} AS ({query})" for name, query in ctes]
            query_parts.append(f"WITH {', '.join(cte_strings)}")

        query_parts.append(f"SELECT {', '.join(select_parts)}")
        query_parts.append(f"FROM {from_clause}")

        if join_clauses:
            query_parts.append('\n'.join(join_clauses))

        if where_clauses:
            query_parts.append(f"WHERE {' AND '.join(where_clauses)}")

        query = '\n'.join(query_parts)
        return query, applied_filters

    def _get_summary_stats(self, base_query: str, selected_columns: dict, filters: dict) -> dict:
        """
        Get high-level summary statistics for the filtered dataset.
        Only returns total_rows - column-specific stats are in column_stats.
        """
        try:
            summary_query = f"""
            WITH filtered_data AS (
                {base_query}
            )
            SELECT COUNT(*) as total_rows
            FROM filtered_data
            """

            logger.debug(f"Running summary stats query...")
            result = self.bq_service.client.query(summary_query).result()
            row = list(result)[0]

            return {
                'total_rows': row.total_rows or 0,
            }

        except Exception as e:
            logger.error(f"Error getting summary stats: {e}")
            return {
                'total_rows': 0,
                'error': str(e)
            }

    def _get_column_stats(self, base_query: str, selected_columns: dict) -> dict:
        """
        Get statistics for each column in the selected columns.
        """
        try:
            # Flatten column list with aliases
            columns_with_types = []
            for table, columns in selected_columns.items():
                table_alias = table.replace('raw_data.', '')
                # Get schema to know column types
                try:
                    schema = self.bq_service.get_table_schema(table)
                    schema_dict = {col['name']: col['type'] for col in schema}
                except Exception:
                    schema_dict = {}

                for col in columns:
                    col_alias = f"{table_alias}_{col}"
                    col_type = schema_dict.get(col, 'STRING')
                    columns_with_types.append({
                        'alias': col_alias,
                        'original': col,
                        'table': table_alias,
                        'type': col_type
                    })

            if not columns_with_types:
                return {}

            # Build stats query for each column based on type
            stats_parts = []

            for col_info in columns_with_types:
                alias = col_info['alias']
                col_type = col_info['type']

                # Null count for all
                stats_parts.append(f"COUNTIF(`{alias}` IS NULL) AS `{alias}__null_count`")

                if col_type in ('STRING', 'BYTES'):
                    stats_parts.append(f"COUNT(DISTINCT `{alias}`) AS `{alias}__unique_count`")
                elif col_type in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC', 'INTEGER', 'FLOAT'):
                    stats_parts.append(f"MIN(`{alias}`) AS `{alias}__min`")
                    stats_parts.append(f"MAX(`{alias}`) AS `{alias}__max`")
                    stats_parts.append(f"AVG(CAST(`{alias}` AS FLOAT64)) AS `{alias}__avg`")
                elif col_type in ('DATE', 'DATETIME', 'TIMESTAMP'):
                    stats_parts.append(f"MIN(`{alias}`) AS `{alias}__min`")
                    stats_parts.append(f"MAX(`{alias}`) AS `{alias}__max`")
                    stats_parts.append(f"COUNT(DISTINCT `{alias}`) AS `{alias}__unique_count`")
                elif col_type == 'BOOL':
                    stats_parts.append(f"COUNTIF(`{alias}` = TRUE) AS `{alias}__true_count`")
                    stats_parts.append(f"COUNTIF(`{alias}` = FALSE) AS `{alias}__false_count`")

            stats_query = f"""
            WITH filtered_data AS (
                {base_query}
            )
            SELECT
                COUNT(*) as __total_rows__,
                {', '.join(stats_parts)}
            FROM filtered_data
            """

            logger.debug(f"Running column stats query...")
            result = self.bq_service.client.query(stats_query).result()
            row = list(result)[0]
            total_rows = row.__total_rows__ or 0

            # Parse results into column stats
            column_stats = {}

            for col_info in columns_with_types:
                alias = col_info['alias']
                col_type = col_info['type']
                display_name = f"{col_info['table']}.{col_info['original']}"

                null_count = getattr(row, f'{alias}__null_count', 0) or 0

                stats = {
                    'type': col_type,
                    'null_count': null_count,
                    'null_percent': round(null_count / total_rows * 100, 2) if total_rows > 0 else 0
                }

                if col_type in ('STRING', 'BYTES'):
                    stats['unique_count'] = getattr(row, f'{alias}__unique_count', 0) or 0

                elif col_type in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC', 'INTEGER', 'FLOAT'):
                    min_val = getattr(row, f'{alias}__min', None)
                    max_val = getattr(row, f'{alias}__max', None)
                    avg_val = getattr(row, f'{alias}__avg', None)

                    stats['min'] = float(min_val) if min_val is not None else None
                    stats['max'] = float(max_val) if max_val is not None else None
                    stats['avg'] = round(float(avg_val), 2) if avg_val is not None else None

                elif col_type in ('DATE', 'DATETIME', 'TIMESTAMP'):
                    min_val = getattr(row, f'{alias}__min', None)
                    max_val = getattr(row, f'{alias}__max', None)
                    unique_count = getattr(row, f'{alias}__unique_count', 0)

                    if min_val:
                        min_str = min_val.isoformat() if hasattr(min_val, 'isoformat') else str(min_val)
                        stats['min'] = min_str.split('T')[0] if 'T' in min_str else min_str
                    else:
                        stats['min'] = None

                    if max_val:
                        max_str = max_val.isoformat() if hasattr(max_val, 'isoformat') else str(max_val)
                        stats['max'] = max_str.split('T')[0] if 'T' in max_str else max_str
                    else:
                        stats['max'] = None

                    stats['unique_count'] = unique_count or 0

                elif col_type == 'BOOL':
                    stats['true_count'] = getattr(row, f'{alias}__true_count', 0) or 0
                    stats['false_count'] = getattr(row, f'{alias}__false_count', 0) or 0

                column_stats[display_name] = stats

            return column_stats

        except Exception as e:
            logger.error(f"Error getting column stats: {e}")
            return {'error': str(e)}

    def _format_applied_filters(self, filters: dict) -> dict:
        """Format filters into the applied_filters response structure."""
        applied = {
            'dates': {'type': 'none'},
            'customers': {'type': 'none'},
            'products': {'type': 'none'}
        }

        date_filter = filters.get('date_filter', {})
        if date_filter.get('type') == 'rolling':
            applied['dates'] = {'type': 'rolling', 'days': date_filter.get('days', 30)}
        elif date_filter.get('type') == 'fixed':
            applied['dates'] = {'type': 'fixed', 'start_date': date_filter.get('start_date')}

        customer_filter = filters.get('customer_filter', {})
        if customer_filter.get('type') == 'min_transactions':
            applied['customers'] = {'type': 'min_transactions', 'value': customer_filter.get('value', 2)}

        # Handle product filters (legacy and new format)
        product_filter = filters.get('product_filter', {})
        product_filter_summary = []

        # Legacy format: 'type': 'top_revenue'
        if product_filter.get('type') == 'top_revenue':
            applied['products'] = {'type': 'top_revenue', 'percent': product_filter.get('percent', 80)}
        else:
            # New format with top_revenue, category_filters, numeric_filters
            top_revenue = product_filter.get('top_revenue', {})
            if top_revenue.get('enabled'):
                product_filter_summary.append({
                    'type': 'top_revenue',
                    'percent': top_revenue.get('threshold_percent', 80)
                })

            category_filters = product_filter.get('category_filters', [])
            for cat_filter in category_filters:
                if cat_filter.get('column') and cat_filter.get('values'):
                    product_filter_summary.append({
                        'type': 'category',
                        'column': cat_filter['column'],
                        'mode': cat_filter.get('mode', 'include'),
                        'count': len(cat_filter['values'])
                    })

            numeric_filters = product_filter.get('numeric_filters', [])
            for num_filter in numeric_filters:
                if num_filter.get('column'):
                    filter_type = num_filter.get('type', 'range')
                    summary = {
                        'type': f'numeric_{filter_type}',
                        'column': num_filter['column']
                    }
                    if filter_type == 'range':
                        summary['min'] = num_filter.get('min')
                        summary['max'] = num_filter.get('max')
                    else:
                        summary['value'] = num_filter.get('value')
                    product_filter_summary.append(summary)

            if product_filter_summary:
                applied['products'] = {
                    'type': 'multiple',
                    'filters': product_filter_summary,
                    'count': len(product_filter_summary)
                }

        return applied

    def _extract_column_name(self, column_ref: str) -> str:
        """Extract just the column name from a 'table.column' reference."""
        if not column_ref:
            return None
        if '.' in column_ref:
            return column_ref.split('.')[-1]
        return column_ref


# =============================================================================
# COLUMN ANALYSIS SERVICE
# =============================================================================

class ColumnAnalysisService:
    """
    Service for analyzing columns from cached pandas sample data.

    Used to provide column metadata for product filters:
    - Detect column types (STRING, INTEGER, FLOAT)
    - Get unique values for STRING columns (for category filters)
    - Get min/max/null stats for numeric columns (for numeric filters)

    Uses the cached sample data from Step 3 (Schema Builder) to avoid
    additional BigQuery queries.
    """

    # Threshold for switching from list mode to autocomplete mode
    AUTOCOMPLETE_THRESHOLD = 100

    def __init__(self, session_data: dict):
        """
        Initialize the service with cached session data.

        Args:
            session_data: Dict from DatasetPreviewService cache containing:
                - dataframes: Dict of table_name -> list of row dicts
                - tables: Dict of table_name -> metadata
        """
        self.session_data = session_data
        self._dataframes = {}

        # Reconstruct pandas DataFrames from cached data
        import pandas as pd
        for table_name, records in session_data.get('dataframes', {}).items():
            self._dataframes[table_name] = pd.DataFrame(records)

    def analyze_columns(self, selected_columns: dict) -> dict:
        """
        Analyze all selected columns and return metadata for filtering.

        Args:
            selected_columns: Dict of table_name -> list of column names
                e.g., {"raw_data.transactions": ["category", "price", "amount"]}

        Returns:
            Dict with column analysis:
            {
                "status": "success",
                "columns": {
                    "transactions.category": {
                        "type": "STRING",
                        "unique_count": 12,
                        "display_mode": "list",
                        "values": [
                            {"value": "Electronics", "count": 45},
                            {"value": "Clothing", "count": 32},
                            ...
                        ],
                        "null_count": 5,
                        "null_percent": 5.0,
                        "total_rows": 100
                    },
                    "transactions.price": {
                        "type": "FLOAT",
                        "min": 0.50,
                        "max": 12450.00,
                        "mean": 245.67,
                        "null_count": 2,
                        "null_percent": 2.0,
                        "total_rows": 100
                    },
                    ...
                }
            }
        """
        import pandas as pd

        result = {
            'status': 'success',
            'columns': {}
        }

        for table_name, columns in selected_columns.items():
            if table_name not in self._dataframes:
                logger.warning(f"Table {table_name} not found in session data")
                continue

            df = self._dataframes[table_name]
            table_short = table_name.split('.')[-1]

            for col_name in columns:
                if col_name not in df.columns:
                    logger.warning(f"Column {col_name} not found in {table_name}")
                    continue

                # Use "table.column" format for column key
                col_key = f"{table_short}.{col_name}"
                col_data = df[col_name]
                total_rows = len(df)

                # Detect column type and analyze accordingly
                col_type = self._detect_column_type(col_data)
                null_count = int(col_data.isna().sum())
                null_percent = round(null_count * 100.0 / total_rows, 2) if total_rows > 0 else 0

                if col_type == 'STRING':
                    result['columns'][col_key] = self._analyze_string_column(
                        col_data, col_type, null_count, null_percent, total_rows
                    )
                elif col_type in ('INTEGER', 'FLOAT'):
                    result['columns'][col_key] = self._analyze_numeric_column(
                        col_data, col_type, null_count, null_percent, total_rows
                    )
                elif col_type in ('DATE', 'TIMESTAMP'):
                    result['columns'][col_key] = self._analyze_date_column(
                        col_data, col_type, null_count, null_percent, total_rows
                    )
                else:
                    # For other types (BOOL, etc.), provide basic info
                    result['columns'][col_key] = {
                        'type': col_type,
                        'null_count': null_count,
                        'null_percent': null_percent,
                        'total_rows': total_rows,
                        'filterable': False,
                        'reason': f'{col_type} columns not supported for product filters'
                    }

        return result

    def _detect_column_type(self, col_data) -> str:
        """
        Detect the BigQuery-compatible type from pandas Series.

        Args:
            col_data: pandas Series

        Returns:
            String type: 'STRING', 'INTEGER', 'FLOAT', 'BOOL', 'TIMESTAMP', 'DATE'
        """
        import pandas as pd
        import numpy as np

        dtype = col_data.dtype

        # Check for boolean first
        if dtype == bool or dtype == 'bool':
            return 'BOOL'

        # Check for integer types
        if pd.api.types.is_integer_dtype(dtype):
            return 'INTEGER'

        # Check for float types
        if pd.api.types.is_float_dtype(dtype):
            # Check if it's actually integer data stored as float (common with NaN)
            non_null = col_data.dropna()
            if len(non_null) > 0:
                if all(float(x).is_integer() for x in non_null):
                    return 'INTEGER'
            return 'FLOAT'

        # Check for datetime types
        if pd.api.types.is_datetime64_any_dtype(dtype):
            # Check if it's a date-only or full timestamp
            non_null = col_data.dropna().head(10)
            if len(non_null) > 0:
                sample = non_null.iloc[0]
                if hasattr(sample, 'hour') and sample.hour == 0 and sample.minute == 0 and sample.second == 0:
                    # All samples have time 00:00:00, likely a date-only column
                    return 'DATE'
            return 'TIMESTAMP'

        # Check for date in object columns (strings that look like dates)
        if dtype == object:
            # Sample non-null values to check type
            non_null = col_data.dropna().head(10)
            if len(non_null) > 0:
                sample = non_null.iloc[0]
                if isinstance(sample, (pd.Timestamp, np.datetime64)):
                    return 'TIMESTAMP'
                # Check for date strings like "2024-01-15"
                if isinstance(sample, str):
                    import re
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', sample.strip()):
                        return 'DATE'
                    if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', sample.strip()):
                        return 'TIMESTAMP'

        # Default to STRING for object dtype
        return 'STRING'

    def _analyze_string_column(
        self,
        col_data,
        col_type: str,
        null_count: int,
        null_percent: float,
        total_rows: int
    ) -> dict:
        """
        Analyze a STRING column for category filtering.

        Args:
            col_data: pandas Series
            col_type: Column type string
            null_count: Count of null values
            null_percent: Percentage of null values
            total_rows: Total row count

        Returns:
            Dict with column analysis including unique values
        """
        # Get value counts (excludes NaN by default)
        value_counts = col_data.value_counts()
        unique_count = len(value_counts)

        result = {
            'type': col_type,
            'unique_count': unique_count,
            'null_count': null_count,
            'null_percent': null_percent,
            'total_rows': total_rows,
            'filterable': True,
            'filter_type': 'category'
        }

        # Determine display mode based on unique count
        if unique_count > self.AUTOCOMPLETE_THRESHOLD:
            result['display_mode'] = 'autocomplete'
            # Provide top 20 values as sample for autocomplete
            top_values = value_counts.head(20)
            result['sample_values'] = [
                {'value': str(val), 'count': int(count)}
                for val, count in top_values.items()
            ]
        else:
            result['display_mode'] = 'list'
            # Provide all values with counts, sorted by frequency
            result['values'] = [
                {'value': str(val), 'count': int(count)}
                for val, count in value_counts.items()
            ]

        return result

    def _analyze_numeric_column(
        self,
        col_data,
        col_type: str,
        null_count: int,
        null_percent: float,
        total_rows: int
    ) -> dict:
        """
        Analyze a numeric column (INTEGER or FLOAT) for range filtering.

        Args:
            col_data: pandas Series
            col_type: Column type string ('INTEGER' or 'FLOAT')
            null_count: Count of null values
            null_percent: Percentage of null values
            total_rows: Total row count

        Returns:
            Dict with column analysis including min/max/mean
        """
        import numpy as np

        # Get numeric statistics (excludes NaN)
        non_null = col_data.dropna()

        result = {
            'type': col_type,
            'null_count': null_count,
            'null_percent': null_percent,
            'total_rows': total_rows,
            'filterable': True,
            'filter_type': 'numeric'
        }

        if len(non_null) > 0:
            min_val = non_null.min()
            max_val = non_null.max()
            mean_val = non_null.mean()

            # Convert numpy types to Python types for JSON serialization
            if col_type == 'INTEGER':
                result['min'] = int(min_val)
                result['max'] = int(max_val)
                result['mean'] = round(float(mean_val), 2)
            else:
                result['min'] = round(float(min_val), 2)
                result['max'] = round(float(max_val), 2)
                result['mean'] = round(float(mean_val), 2)

            # Add unique count for numeric columns (useful for sparse data)
            result['unique_count'] = int(non_null.nunique())
        else:
            result['min'] = None
            result['max'] = None
            result['mean'] = None
            result['unique_count'] = 0

        return result

    def _analyze_date_column(
        self,
        col_data,
        col_type: str,
        null_count: int,
        null_percent: float,
        total_rows: int
    ) -> dict:
        """
        Analyze a DATE or TIMESTAMP column for date range filtering.

        Args:
            col_data: pandas Series
            col_type: Column type string ('DATE' or 'TIMESTAMP')
            null_count: Count of null values
            null_percent: Percentage of null values
            total_rows: Total row count

        Returns:
            Dict with column analysis including min_date/max_date
        """
        import pandas as pd

        # Get date statistics (excludes NaN)
        non_null = col_data.dropna()

        result = {
            'type': col_type,
            'null_count': null_count,
            'null_percent': null_percent,
            'total_rows': total_rows,
            'filterable': True,
            'filter_type': 'date'
        }

        if len(non_null) > 0:
            try:
                # Convert to datetime if needed
                if not pd.api.types.is_datetime64_any_dtype(non_null.dtype):
                    non_null = pd.to_datetime(non_null)

                min_date = non_null.min()
                max_date = non_null.max()

                # Format dates as strings for JSON
                result['min_date'] = min_date.strftime('%Y-%m-%d')
                result['max_date'] = max_date.strftime('%Y-%m-%d')
                result['unique_count'] = int(non_null.nunique())
            except Exception as e:
                logger.warning(f"Error analyzing date column: {e}")
                result['min_date'] = None
                result['max_date'] = None
                result['unique_count'] = 0
        else:
            result['min_date'] = None
            result['max_date'] = None
            result['unique_count'] = 0

        return result

    def search_category_values(
        self,
        table_name: str,
        column_name: str,
        search_term: str,
        limit: int = 20
    ) -> list:
        """
        Search for category values matching a search term.

        Used for autocomplete mode when there are >100 unique values.

        Args:
            table_name: Table name (e.g., "raw_data.products")
            column_name: Column name (e.g., "category")
            search_term: Search string to match
            limit: Maximum number of results to return

        Returns:
            List of matching values with counts:
            [
                {"value": "Electronics", "count": 45},
                {"value": "Electrical", "count": 12},
                ...
            ]
        """
        if table_name not in self._dataframes:
            return []

        df = self._dataframes[table_name]
        if column_name not in df.columns:
            return []

        col_data = df[column_name]

        # Get value counts
        value_counts = col_data.value_counts()

        # Filter by search term (case-insensitive)
        search_lower = search_term.lower()
        matching = [
            {'value': str(val), 'count': int(count)}
            for val, count in value_counts.items()
            if search_lower in str(val).lower()
        ]

        # Sort by count descending and limit
        matching.sort(key=lambda x: x['count'], reverse=True)
        return matching[:limit]
