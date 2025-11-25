"""
BigQuery Loader

Loads data into BigQuery tables using the BigQuery API.
"""

from typing import Dict, Any, Optional
import pandas as pd
import logging
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError

logger = logging.getLogger(__name__)


class BigQueryLoader:
    """Loader for BigQuery tables"""

    def __init__(self, project_id: str, dataset_id: str, table_name: str):
        """
        Initialize BigQuery loader.

        Args:
            project_id: GCP project ID
            dataset_id: BigQuery dataset ID (e.g., 'raw_data')
            table_name: BigQuery table name (e.g., 'bq_transactions')
        """
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_name = table_name
        self.table_ref = f"{project_id}.{dataset_id}.{table_name}"

        # Initialize BigQuery client
        self.client = bigquery.Client(project=project_id)
        logger.info(f"Initialized BigQuery loader for {self.table_ref}")

        # Cache for table schema
        self._schema_cache = None

    def _get_table_schema(self) -> dict:
        """
        Get BigQuery table schema as a dict mapping column names to types.

        Returns:
            Dict like {'column_name': 'INTEGER', 'other_column': 'STRING', ...}
        """
        if self._schema_cache is not None:
            return self._schema_cache

        try:
            table = self.client.get_table(self.table_ref)
            self._schema_cache = {field.name: field.field_type for field in table.schema}
            # Also cache required fields for null handling
            self._required_fields = {field.name for field in table.schema if field.mode == 'REQUIRED'}
            return self._schema_cache
        except Exception as e:
            logger.warning(f"Failed to fetch BigQuery schema: {e}")
            self._required_fields = set()
            return {}

    def _convert_to_integer(self, value):
        """
        Convert a value to integer, handling ISO datetime strings.

        Args:
            value: The value to convert (could be string, datetime, int, etc.)

        Returns:
            Integer value or None if conversion fails
        """
        from datetime import datetime
        from dateutil import parser as date_parser

        if value is None or (isinstance(value, str) and value.lower() in ['none', 'nan', '']):
            return None

        # Already an integer
        if isinstance(value, (int, float)):
            return int(value)

        # Try to parse as ISO datetime string and convert to Unix timestamp
        if isinstance(value, str):
            try:
                # Try parsing as ISO datetime
                dt = date_parser.isoparse(value)
                return int(dt.timestamp())
            except (ValueError, TypeError):
                pass

            # Try parsing as plain integer string
            try:
                return int(value)
            except (ValueError, TypeError):
                pass

        # If it's a datetime object, convert to timestamp
        if hasattr(value, 'timestamp'):
            return int(value.timestamp())

        logger.warning(f"Could not convert value to integer: {value} (type: {type(value).__name__})")
        return None

    def load_batch(
        self,
        df: pd.DataFrame,
        write_mode: str = 'WRITE_APPEND'
    ) -> Dict[str, Any]:
        """
        Load a batch of data (DataFrame) to BigQuery.

        Args:
            df: pandas DataFrame to load
            write_mode: Write disposition:
                - 'WRITE_APPEND': Append to existing table (default)
                - 'WRITE_TRUNCATE': Replace table contents
                - 'WRITE_EMPTY': Only write if table is empty

        Returns:
            Dict with load statistics:
                - rows_loaded: Number of rows successfully loaded
                - errors: Any errors encountered
                - job_id: BigQuery job ID
        """
        if df.empty:
            logger.warning("Empty DataFrame provided, skipping load")
            return {
                'rows_loaded': 0,
                'errors': None,
                'job_id': None
            }

        logger.info(f"Loading batch to {self.table_ref}: {len(df)} rows")

        # DIAGNOSTIC: Print DataFrame info
        logger.info(f"DataFrame dtypes: {df.dtypes.to_dict()}")

        # Check for problematic columns
        for col in df.columns:
            sample_value = df[col].iloc[0] if len(df) > 0 else None
            value_type = type(sample_value).__name__
            logger.info(f"Column '{col}': dtype={df[col].dtype}, sample_value_type={value_type}")
            if isinstance(sample_value, (list, dict)):
                logger.error(f"PROBLEM: Column '{col}' contains {value_type} values: {sample_value}")

        try:
            # Configure load job
            job_config = bigquery.LoadJobConfig(
                write_disposition=write_mode,
                create_disposition='CREATE_NEVER',  # Table must exist (created by wizard)
                autodetect=False  # Use existing table schema
            )

            # Fetch BigQuery table schema to match types correctly
            bq_schema = self._get_table_schema()
            logger.info(f"BigQuery table schema: {bq_schema}")

            # CRITICAL FIX: Drop columns not in BigQuery schema
            cols_to_drop = [col for col in df.columns if col not in bq_schema]
            if cols_to_drop:
                logger.warning(f"Dropping columns not in BigQuery schema: {cols_to_drop}")
                df = df.drop(columns=cols_to_drop)

            # Convert values to match BigQuery schema types
            logger.info("Converting columns to match BigQuery schema...")
            for col in df.columns:
                target_type = bq_schema.get(col)
                if not target_type:
                    continue  # Shouldn't happen after dropping above, but safety check

                # Check if column contains complex types (lists, dicts)
                if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
                    logger.warning(f"Column '{col}' contains lists/dicts, converting to JSON strings")
                    df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (list, dict)) else x)

                # DEFENSIVE FIX: Check for datetime-like objects that PyArrow can't handle
                # This catches Firestore's DatetimeWithNanoseconds and similar types
                if df[col].dtype == 'object':
                    # Check if any values have isoformat method (datetime-like but not pure datetime)
                    has_datetime_like = df[col].apply(
                        lambda x: hasattr(x, 'isoformat') and not isinstance(x, str)
                    ).any()

                    if has_datetime_like:
                        logger.warning(f"Column '{col}' contains datetime-like objects")
                        # Convert based on target BigQuery type
                        if target_type == 'INTEGER':
                            # Convert datetime to Unix timestamp (integer)
                            logger.info(f"Converting '{col}' datetime to INTEGER (Unix timestamp)")
                            df[col] = df[col].apply(
                                lambda x: int(x.timestamp()) if hasattr(x, 'timestamp') else x
                            )
                        elif target_type == 'TIMESTAMP':
                            # Keep as datetime for TIMESTAMP type
                            logger.info(f"Converting '{col}' to TIMESTAMP format")
                            df[col] = pd.to_datetime(df[col], errors='coerce')
                        else:
                            # Convert to string for STRING or other types
                            logger.info(f"Converting '{col}' datetime to STRING")
                            df[col] = df[col].apply(
                                lambda x: x.strftime('%Y-%m-%dT%H:%M:%S.%f') if hasattr(x, 'strftime')
                                else (str(x.isoformat()) if hasattr(x, 'isoformat') else x)
                            )

                # Schema-aware type conversion for object columns
                if df[col].dtype == 'object' and target_type:
                    if target_type == 'INTEGER':
                        # Try to convert ISO datetime strings to Unix timestamps
                        logger.info(f"Converting '{col}' (object) to INTEGER")
                        df[col] = df[col].apply(self._convert_to_integer)
                    elif target_type == 'FLOAT':
                        logger.info(f"Converting '{col}' (object) to FLOAT")
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    elif target_type == 'TIMESTAMP':
                        logger.info(f"Converting '{col}' (object) to TIMESTAMP")
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                    else:
                        # Default: convert to string
                        df[col] = df[col].astype(str)
                        logger.info(f"Converted column '{col}' to string dtype")

            # Fill nulls for REQUIRED fields (NoSQL data may have missing fields)
            required_fields = getattr(self, '_required_fields', set())
            for col in df.columns:
                if col in required_fields and df[col].isnull().any():
                    target_type = bq_schema.get(col)
                    null_count = df[col].isnull().sum()
                    if target_type in ('INTEGER', 'INT64'):
                        logger.info(f"Filling {null_count} nulls in REQUIRED field '{col}' with 0")
                        df[col] = df[col].fillna(0).astype(int)
                    elif target_type in ('FLOAT', 'FLOAT64', 'NUMERIC'):
                        logger.info(f"Filling {null_count} nulls in REQUIRED field '{col}' with 0.0")
                        df[col] = df[col].fillna(0.0)
                    elif target_type == 'BOOLEAN':
                        logger.info(f"Filling {null_count} nulls in REQUIRED field '{col}' with False")
                        df[col] = df[col].fillna(False)
                    elif target_type == 'TIMESTAMP':
                        logger.info(f"Filling {null_count} nulls in REQUIRED field '{col}' with epoch")
                        df[col] = df[col].fillna(pd.Timestamp('1970-01-01'))
                    else:
                        # STRING or other types
                        logger.info(f"Filling {null_count} nulls in REQUIRED field '{col}' with empty string")
                        df[col] = df[col].fillna('')

            # Load DataFrame to BigQuery
            load_job = self.client.load_table_from_dataframe(
                df,
                self.table_ref,
                job_config=job_config
            )

            # Wait for job to complete
            load_job.result()

            # Get job statistics
            rows_loaded = load_job.output_rows or len(df)
            errors = load_job.errors

            if errors:
                logger.error(f"Load job completed with errors: {errors}")
            else:
                logger.info(f"Successfully loaded {rows_loaded} rows to {self.table_ref}")

            return {
                'rows_loaded': rows_loaded,
                'errors': errors,
                'job_id': load_job.job_id
            }

        except GoogleCloudError as e:
            logger.error(f"BigQuery load failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during load: {str(e)}")
            raise

    def load_full(
        self,
        df_generator,
        on_batch_loaded: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Load full dataset from a generator of DataFrames (catalog mode).

        First batch uses WRITE_TRUNCATE, subsequent batches use WRITE_APPEND.

        Args:
            df_generator: Generator yielding pandas DataFrames
            on_batch_loaded: Optional callback function called after each batch
                             Receives batch_num and rows_loaded as arguments

        Returns:
            Dict with aggregate statistics:
                - total_rows: Total rows loaded
                - batches_loaded: Number of batches processed
                - errors: List of any errors encountered
        """
        logger.info(f"Starting full load to {self.table_ref}")

        total_rows = 0
        batch_num = 0
        all_errors = []
        first_batch = True

        try:
            for df in df_generator:
                batch_num += 1

                # First batch: truncate table, subsequent: append
                write_mode = 'WRITE_TRUNCATE' if first_batch else 'WRITE_APPEND'

                result = self.load_batch(df, write_mode=write_mode)

                total_rows += result['rows_loaded']

                if result['errors']:
                    all_errors.extend(result['errors'])

                # Call callback if provided
                if on_batch_loaded:
                    on_batch_loaded(batch_num, result['rows_loaded'])

                first_batch = False

            logger.info(f"Full load completed: {total_rows:,} total rows in {batch_num} batches")

            return {
                'total_rows': total_rows,
                'batches_loaded': batch_num,
                'errors': all_errors if all_errors else None
            }

        except Exception as e:
            logger.error(f"Full load failed at batch {batch_num}: {str(e)}")
            raise

    def load_incremental(
        self,
        df_generator,
        on_batch_loaded: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Load incremental data from a generator of DataFrames (transactional mode).

        All batches use WRITE_APPEND.

        Args:
            df_generator: Generator yielding pandas DataFrames
            on_batch_loaded: Optional callback function called after each batch
                             Receives batch_num and rows_loaded as arguments

        Returns:
            Dict with aggregate statistics:
                - total_rows: Total rows loaded
                - batches_loaded: Number of batches processed
                - errors: List of any errors encountered
        """
        logger.info(f"Starting incremental load to {self.table_ref}")

        total_rows = 0
        batch_num = 0
        all_errors = []

        try:
            for df in df_generator:
                batch_num += 1

                result = self.load_batch(df, write_mode='WRITE_APPEND')

                total_rows += result['rows_loaded']

                if result['errors']:
                    all_errors.extend(result['errors'])

                # Call callback if provided
                if on_batch_loaded:
                    on_batch_loaded(batch_num, result['rows_loaded'])

            logger.info(f"Incremental load completed: {total_rows:,} total rows in {batch_num} batches")

            return {
                'total_rows': total_rows,
                'batches_loaded': batch_num,
                'errors': all_errors if all_errors else None
            }

        except Exception as e:
            logger.error(f"Incremental load failed at batch {batch_num}: {str(e)}")
            raise

    def get_table_info(self) -> Dict[str, Any]:
        """
        Get information about the BigQuery table.

        Returns:
            Dict with table information:
                - num_rows: Number of rows in table
                - num_bytes: Size in bytes
                - created: Creation time
                - modified: Last modified time
        """
        try:
            table = self.client.get_table(self.table_ref)

            return {
                'num_rows': table.num_rows,
                'num_bytes': table.num_bytes,
                'created': table.created,
                'modified': table.modified
            }

        except Exception as e:
            logger.error(f"Failed to get table info: {str(e)}")
            raise

    def verify_table_exists(self) -> bool:
        """
        Verify that the target table exists.

        Returns:
            True if table exists, False otherwise
        """
        try:
            self.client.get_table(self.table_ref)
            logger.info(f"Table {self.table_ref} exists")
            return True
        except Exception:
            logger.warning(f"Table {self.table_ref} does not exist")
            return False
