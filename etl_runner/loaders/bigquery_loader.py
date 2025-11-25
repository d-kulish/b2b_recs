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

            # CRITICAL FIX: Convert all values to strings to prevent PyArrow errors
            logger.info("Converting all columns to prevent PyArrow errors...")
            for col in df.columns:
                # Check if column contains complex types
                if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
                    logger.warning(f"Column '{col}' contains lists/dicts, converting to JSON strings")
                    df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (list, dict)) else x)

                # Convert object dtypes to string
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str)
                    logger.info(f"Converted column '{col}' to string dtype")

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
