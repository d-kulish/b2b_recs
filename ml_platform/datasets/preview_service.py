"""
Dataset Preview Service

Handles sample loading and preview generation for the Visual Schema Builder.
Uses pandas for in-memory joins to provide instant feedback during dataset configuration.

Key features:
- Load random samples (100 rows) from BigQuery tables
- Cache samples in memory during wizard session
- Generate previews using pandas joins
- Auto-detect join keys between tables
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd

from django.core.cache import cache
from django.conf import settings

from .services import BigQueryService, BigQueryServiceError

logger = logging.getLogger(__name__)

# Cache settings
PREVIEW_CACHE_TIMEOUT = 30 * 60  # 30 minutes
PREVIEW_CACHE_PREFIX = 'dataset_preview:'
SAMPLE_SIZE = 100  # Rows per table


class DatasetPreviewService:
    """
    Service for generating dataset previews using cached sample data.

    Workflow:
    1. load_samples() - Fetch random samples from BigQuery, cache them
    2. generate_preview() - Apply joins and column selection using pandas
    3. detect_joins() - Suggest join configurations based on column names
    4. cleanup_session() - Remove cached data
    """

    def __init__(self, model_endpoint):
        """
        Initialize preview service for a model endpoint.

        Args:
            model_endpoint: ModelEndpoint instance
        """
        self.model_endpoint = model_endpoint
        self.bq_service = BigQueryService(model_endpoint)
        self._session_cache = {}  # In-memory fallback if Django cache unavailable

    def _get_cache_key(self, session_id: str) -> str:
        """Generate cache key for a session."""
        return f"{PREVIEW_CACHE_PREFIX}{session_id}"

    def _get_from_cache(self, session_id: str) -> Optional[Dict]:
        """
        Get cached session data.

        Args:
            session_id: Session identifier

        Returns:
            Cached data dict or None
        """
        cache_key = self._get_cache_key(session_id)

        # Try Django cache first
        try:
            data = cache.get(cache_key)
            if data:
                return data
        except Exception as e:
            logger.warning(f"Django cache unavailable: {e}")

        # Fallback to in-memory
        return self._session_cache.get(session_id)

    def _set_to_cache(self, session_id: str, data: Dict) -> None:
        """
        Store session data in cache.

        Args:
            session_id: Session identifier
            data: Data to cache
        """
        cache_key = self._get_cache_key(session_id)

        # Try Django cache first
        try:
            cache.set(cache_key, data, PREVIEW_CACHE_TIMEOUT)
        except Exception as e:
            logger.warning(f"Django cache unavailable, using in-memory: {e}")

        # Always store in-memory as fallback
        self._session_cache[session_id] = data

    def _delete_from_cache(self, session_id: str) -> None:
        """
        Remove session data from cache.

        Args:
            session_id: Session identifier
        """
        cache_key = self._get_cache_key(session_id)

        try:
            cache.delete(cache_key)
        except Exception:
            pass

        self._session_cache.pop(session_id, None)

    # =========================================================================
    # SAMPLE LOADING
    # =========================================================================

    def load_samples(self, table_names: List[str]) -> Dict[str, Any]:
        """
        Load samples from BigQuery tables using seeded sampling.

        Uses "seeded sampling" approach:
        1. Sample primary table (first in list) randomly
        2. Extract foreign key values from primary sample
        3. Sample secondary tables filtered by those foreign keys

        This ensures that joined tables have matching keys for meaningful previews.

        Args:
            table_names: List of table names. First is primary, rest are secondary.
                        e.g., ["raw_data.transactions", "raw_data.products", "raw_data.customers"]

        Returns:
            Dict with session_id and table metadata
        """
        session_id = str(uuid.uuid4())[:8]
        tables_data = {}
        dataframes = {}

        if not table_names:
            return {
                'session_id': session_id,
                'tables': {},
                'created_at': datetime.now().isoformat(),
            }

        primary_table = table_names[0]
        secondary_tables = table_names[1:] if len(table_names) > 1 else []

        # Step 1: Load primary table sample (random)
        try:
            primary_schema = self.bq_service.get_table_schema(primary_table)
            primary_df = self._load_table_sample_random(primary_table, SAMPLE_SIZE)
            dataframes[primary_table] = primary_df

            # Build column metadata for primary table
            tables_data[primary_table] = self._build_table_metadata(
                primary_table, primary_schema, primary_df
            )

        except Exception as e:
            logger.error(f"Error loading primary table sample for {primary_table}: {e}")
            tables_data[primary_table] = {
                'columns': [],
                'row_count': 0,
                'error': str(e),
            }
            primary_df = pd.DataFrame()

        # Step 2: Extract potential foreign keys from primary table
        # Look for columns that might be join keys (contain 'id', '_key', etc.)
        primary_join_keys = self._extract_join_key_values(primary_df, primary_schema if 'primary_schema' in dir() else [])

        # Step 3: Load secondary tables using seeded sampling
        for table_name in secondary_tables:
            try:
                schema = self.bq_service.get_table_schema(table_name)

                # Find matching join key between primary and this secondary table
                df = self._load_table_sample_seeded(
                    table_name, schema, primary_join_keys, SAMPLE_SIZE
                )

                dataframes[table_name] = df
                tables_data[table_name] = self._build_table_metadata(
                    table_name, schema, df
                )

            except Exception as e:
                logger.error(f"Error loading sample for {table_name}: {e}")
                tables_data[table_name] = {
                    'columns': [],
                    'row_count': 0,
                    'error': str(e),
                }

        # Cache the session data
        session_data = {
            'session_id': session_id,
            'model_id': self.model_endpoint.id,
            'tables': tables_data,
            'dataframes': {k: df.to_dict('records') for k, df in dataframes.items()},
            'primary_table': primary_table,
            'created_at': datetime.now().isoformat(),
        }

        self._set_to_cache(session_id, session_data)

        return {
            'session_id': session_id,
            'tables': tables_data,
            'created_at': session_data['created_at'],
        }

    def _build_table_metadata(self, table_name: str, schema: List[Dict], df: pd.DataFrame) -> Dict:
        """Build metadata dict for a table."""
        columns = []
        for col in schema:
            col_info = {
                'name': col['name'],
                'type': col['type'],
                'dtype': str(df[col['name']].dtype) if col['name'] in df.columns else 'unknown',
                'is_potential_join_key': col.get('is_potential_join_key', False),
            }
            if col.get('suggested_role'):
                col_info['suggested_role'] = col['suggested_role']
            columns.append(col_info)

        return {
            'columns': columns,
            'row_count': len(df),
            'sample_preview': self._dataframe_to_preview(df.head(5)),
        }

    def _extract_join_key_values(self, df: pd.DataFrame, schema: List[Dict]) -> Dict[str, set]:
        """
        Extract unique values from potential join key columns.

        Args:
            df: Primary table DataFrame
            schema: Table schema

        Returns:
            Dict mapping column names to sets of unique values
        """
        join_keys = {}

        # Identify potential join key columns
        key_patterns = ['_id', 'id_', '_key', 'key_', '_code', 'code_']

        for col in df.columns:
            col_lower = col.lower()
            is_potential_key = any(pattern in col_lower for pattern in key_patterns)

            # Also check schema for marked join keys
            schema_col = next((c for c in schema if c['name'] == col), None)
            if schema_col and schema_col.get('is_potential_join_key'):
                is_potential_key = True

            if is_potential_key:
                # Get unique non-null values
                unique_vals = df[col].dropna().unique()
                if len(unique_vals) > 0:
                    join_keys[col] = set(unique_vals.tolist())

        return join_keys

    def _load_table_sample_random(self, table_name: str, limit: int) -> pd.DataFrame:
        """
        Load a random sample of rows from a BigQuery table.

        Args:
            table_name: Table name
            limit: Number of rows to sample

        Returns:
            pandas DataFrame with sample data
        """
        if '.' not in table_name:
            table_name = f"raw_data.{table_name}"

        full_ref = f"{self.bq_service.project_id}.{table_name}"

        query = f"""
        SELECT *
        FROM `{full_ref}`
        ORDER BY RAND()
        LIMIT {limit}
        """

        return self._execute_sample_query(query, table_name)

    def _load_table_sample_seeded(
        self,
        table_name: str,
        schema: List[Dict],
        primary_join_keys: Dict[str, set],
        limit: int
    ) -> pd.DataFrame:
        """
        Load a sample from a secondary table filtered by primary table's join keys.

        Attempts to find a matching column between this table and the primary table's
        join keys, then filters the sample to only include matching rows.

        Args:
            table_name: Table name
            schema: Table schema
            primary_join_keys: Dict of column -> set of values from primary table
            limit: Number of rows to sample

        Returns:
            pandas DataFrame with sample data
        """
        if '.' not in table_name:
            table_name = f"raw_data.{table_name}"

        full_ref = f"{self.bq_service.project_id}.{table_name}"

        # Find matching column between secondary table and primary join keys
        secondary_columns = [col['name'] for col in schema]
        matching_column = None
        matching_values = None

        for sec_col in secondary_columns:
            sec_col_lower = sec_col.lower()

            for prim_col, values in primary_join_keys.items():
                prim_col_lower = prim_col.lower()

                # Check for exact match or common pattern match
                if sec_col_lower == prim_col_lower:
                    matching_column = sec_col
                    matching_values = values
                    break

                # Check for pattern matches like 'customer_id' matching 'id' in customers table
                # or 'product_id' matching 'id' in products table
                table_short = table_name.split('.')[-1].lower().rstrip('s')  # 'customers' -> 'customer'
                if prim_col_lower == f"{table_short}_id" and sec_col_lower == 'id':
                    matching_column = sec_col
                    matching_values = values
                    break
                if prim_col_lower == f"{table_short}id" and sec_col_lower == 'id':
                    matching_column = sec_col
                    matching_values = values
                    break

            if matching_column:
                break

        if matching_column and matching_values:
            # Build filtered query
            # Convert values to proper SQL format
            if len(matching_values) > 0:
                sample_val = next(iter(matching_values))
                if isinstance(sample_val, str):
                    values_str = ', '.join(f"'{v}'" for v in list(matching_values)[:1000])  # Limit to 1000 values
                else:
                    values_str = ', '.join(str(v) for v in list(matching_values)[:1000])

                query = f"""
                SELECT *
                FROM `{full_ref}`
                WHERE {matching_column} IN ({values_str})
                ORDER BY RAND()
                LIMIT {limit}
                """

                logger.info(f"Seeded sampling {table_name} on column {matching_column}")
                return self._execute_sample_query(query, table_name)

        # Fallback to random sampling if no matching key found
        logger.warning(f"No matching join key found for {table_name}, using random sampling")
        return self._load_table_sample_random(table_name, limit)

    def _execute_sample_query(self, query: str, table_name: str) -> pd.DataFrame:
        """
        Execute a sample query and return DataFrame.

        Args:
            query: SQL query
            table_name: Table name (for error messages)

        Returns:
            pandas DataFrame
        """
        try:
            result = self.bq_service.client.query(query).result()

            rows = []
            columns = [field.name for field in result.schema]

            for row in result:
                row_data = {}
                for col in columns:
                    val = getattr(row, col, None)
                    if hasattr(val, 'isoformat'):
                        row_data[col] = val.isoformat()
                    elif pd.isna(val):
                        row_data[col] = None
                    else:
                        row_data[col] = val
                rows.append(row_data)

            return pd.DataFrame(rows, columns=columns)

        except Exception as e:
            logger.error(f"Error sampling table {table_name}: {e}")
            raise BigQueryServiceError(f"Failed to sample table {table_name}: {e}")

    def _dataframe_to_preview(self, df: pd.DataFrame) -> List[Dict]:
        """
        Convert DataFrame to list of dicts for JSON response.

        Args:
            df: pandas DataFrame

        Returns:
            List of row dicts
        """
        records = df.to_dict('records')
        # Ensure all values are JSON-serializable
        for record in records:
            for key, val in record.items():
                if pd.isna(val):
                    record[key] = None
                elif hasattr(val, 'isoformat'):
                    record[key] = val.isoformat()
        return records

    # =========================================================================
    # PREVIEW GENERATION
    # =========================================================================

    def generate_preview(
        self,
        session_id: str,
        primary_table: str,
        joins: List[Dict],
        selected_columns: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Generate a preview of the dataset based on current configuration.

        Args:
            session_id: Session identifier from load_samples()
            primary_table: Primary table name
            joins: List of join configurations:
                [{"table": "raw_data.products", "left_col": "product_id",
                  "right_col": "product_id", "type": "left"}, ...]
            selected_columns: Dict of table -> list of column names:
                {"raw_data.transactions": ["id", "amount"], ...}

        Returns:
            Dict with preview data:
            {
                "preview_rows": [...10 rows...],
                "column_order": ["transactions_id", "transactions_amount", "products_name"],
                "stats": {
                    "total_rows": 87,
                    "null_counts": {"products_name": 3},
                    "warnings": []
                }
            }
        """
        # Get cached session data
        session_data = self._get_from_cache(session_id)
        if not session_data:
            raise ValueError(f"Session {session_id} not found or expired")

        # Reconstruct DataFrames from cached data
        dataframes = {}
        for table_name, records in session_data.get('dataframes', {}).items():
            dataframes[table_name] = pd.DataFrame(records)

        if primary_table not in dataframes:
            raise ValueError(f"Primary table {primary_table} not found in session")

        # Start with primary table
        result_df = dataframes[primary_table].copy()
        primary_short = primary_table.split('.')[-1]

        # Rename columns with table prefix
        result_df = result_df.rename(columns={
            col: f"{primary_short}_{col}" for col in result_df.columns
        })

        # Track original sample size for duplicate detection
        original_row_count = len(result_df)

        # Apply joins
        warnings = []
        for join_config in joins:
            join_table = join_config.get('table')
            left_col = join_config.get('left_col')
            right_col = join_config.get('right_col')
            join_type = join_config.get('type', 'left').lower()

            if join_table not in dataframes:
                warnings.append(f"Table {join_table} not found in session")
                continue

            right_df = dataframes[join_table].copy()
            right_short = join_table.split('.')[-1]

            # Rename right table columns with prefix
            right_df = right_df.rename(columns={
                col: f"{right_short}_{col}" for col in right_df.columns
            })

            # Determine join columns with prefixes
            left_join_col = f"{primary_short}_{left_col}"
            right_join_col = f"{right_short}_{right_col}"

            # Check if join columns exist
            if left_join_col not in result_df.columns:
                # Try without prefix (might be from a previous join)
                left_join_col = left_col
                if left_join_col not in result_df.columns:
                    warnings.append(f"Left join column {left_col} not found")
                    continue

            if right_join_col not in right_df.columns:
                warnings.append(f"Right join column {right_col} not found in {join_table}")
                continue

            # Perform the join
            try:
                result_df = result_df.merge(
                    right_df,
                    left_on=left_join_col,
                    right_on=right_join_col,
                    how=join_type,
                    suffixes=('', '_dup')
                )

                # Remove duplicate join column from right table
                dup_col = f"{right_join_col}_dup"
                if dup_col in result_df.columns:
                    result_df = result_df.drop(columns=[dup_col])

            except Exception as e:
                warnings.append(f"Join failed for {join_table}: {str(e)}")

        # Select columns based on configuration
        final_columns = []
        for table_name, columns in selected_columns.items():
            table_short = table_name.split('.')[-1]
            for col in columns:
                prefixed_col = f"{table_short}_{col}"
                if prefixed_col in result_df.columns:
                    final_columns.append(prefixed_col)

        # If no columns selected, use all
        if not final_columns:
            final_columns = list(result_df.columns)

        # Filter to selected columns
        available_columns = [c for c in final_columns if c in result_df.columns]
        if available_columns:
            result_df = result_df[available_columns]

        # Calculate null counts
        null_counts = {}
        for col in result_df.columns:
            null_count = result_df[col].isna().sum()
            if null_count > 0:
                null_counts[col] = int(null_count)

        # Generate preview (first 10 rows)
        preview_rows = self._dataframe_to_preview(result_df.head(10))

        return {
            'preview_rows': preview_rows,
            'column_order': list(result_df.columns),
            'stats': {
                'total_rows': len(result_df),
                'original_rows': original_row_count,
                'null_counts': null_counts,
                'warnings': warnings,
                'column_count': len(result_df.columns),
            }
        }

    # =========================================================================
    # JOIN DETECTION
    # =========================================================================

    def detect_joins(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Auto-detect potential joins between tables in the session.

        Args:
            session_id: Session identifier

        Returns:
            List of suggested join configurations:
            [
                {
                    "left_table": "raw_data.transactions",
                    "left_col": "product_id",
                    "right_table": "raw_data.products",
                    "right_col": "product_id",
                    "confidence": "high",
                    "reason": "Exact column name match"
                },
                ...
            ]
        """
        session_data = self._get_from_cache(session_id)
        if not session_data:
            raise ValueError(f"Session {session_id} not found or expired")

        tables = session_data.get('tables', {})
        table_names = list(tables.keys())

        if len(table_names) < 2:
            return []

        # Use the existing BigQuery service for join detection
        # It analyzes column names and types
        try:
            detected = self.bq_service.detect_join_keys(table_names)

            # Convert to list format expected by frontend
            suggestions = []
            primary_table = table_names[0]

            for secondary_table, join_info in detected.items():
                suggestions.append({
                    'left_table': primary_table,
                    'left_col': join_info.get('primary_column') or join_info.get('join_key'),
                    'right_table': secondary_table,
                    'right_col': join_info.get('secondary_column') or join_info.get('join_key'),
                    'confidence': join_info.get('confidence', 'medium'),
                    'reason': join_info.get('reason', 'Column name match'),
                })

            return suggestions

        except Exception as e:
            logger.error(f"Error detecting joins: {e}")
            return []

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    def cleanup_session(self, session_id: str) -> bool:
        """
        Remove cached session data.

        Args:
            session_id: Session identifier

        Returns:
            True if session was found and removed
        """
        session_data = self._get_from_cache(session_id)
        if session_data:
            self._delete_from_cache(session_id)
            return True
        return False

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        Get information about a cached session.

        Args:
            session_id: Session identifier

        Returns:
            Session info dict or None if not found
        """
        session_data = self._get_from_cache(session_id)
        if not session_data:
            return None

        return {
            'session_id': session_id,
            'model_id': session_data.get('model_id'),
            'tables': list(session_data.get('tables', {}).keys()),
            'created_at': session_data.get('created_at'),
        }

    def refresh_session(self, session_id: str) -> bool:
        """
        Refresh session TTL without reloading data.

        Args:
            session_id: Session identifier

        Returns:
            True if session was found and refreshed
        """
        session_data = self._get_from_cache(session_id)
        if session_data:
            self._set_to_cache(session_id, session_data)
            return True
        return False
