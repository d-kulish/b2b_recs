"""
BigQuery Extractor

Extracts data from BigQuery tables (cross-project or same-project).
Supports both public datasets and private tables.
"""

from typing import Generator, List, Dict, Any, Optional
import pandas as pd
import logging
from google.cloud import bigquery
from google.oauth2 import service_account
import json
from .base import BaseExtractor

logger = logging.getLogger(__name__)


class BigQueryExtractor(BaseExtractor):
    """Extractor for BigQuery tables"""

    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize BigQuery extractor.

        Args:
            connection_params: Dictionary with connection details
                - source_project: Source BigQuery project ID
                - source_dataset: Source dataset name
                - credentials: Service account JSON (optional, uses default if not provided)
        """
        super().__init__(connection_params)

        self.source_project = connection_params.get('source_project') or connection_params.get('bigquery_project')
        self.source_dataset = connection_params.get('source_dataset') or connection_params.get('bigquery_dataset')

        # Initialize BigQuery client
        self._client = None
        self._init_client()

        logger.info(f"Initialized BigQuery extractor: {self.source_project}.{self.source_dataset}")

    def _init_client(self):
        """Initialize BigQuery client with credentials"""
        credentials_dict = self.connection_params.get('credentials', {})
        service_account_json = credentials_dict.get('service_account_json', '')

        if service_account_json:
            # Use provided service account credentials
            try:
                credentials_info = json.loads(service_account_json)
                credentials = service_account.Credentials.from_service_account_info(credentials_info)
                project_id = credentials_info.get('project_id')
                self._client = bigquery.Client(credentials=credentials, project=project_id)
                logger.info(f"Initialized BigQuery client with service account (project: {project_id})")
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse service account JSON: {e}")
                raise ValueError(f"Invalid service account credentials: {e}")
        else:
            # Use default credentials (for cross-project queries)
            self._client = bigquery.Client()
            logger.info("Initialized BigQuery client with default credentials")

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the BigQuery connection by listing tables in the dataset.

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        try:
            # Try to get dataset metadata
            dataset_ref = f"{self.source_project}.{self.source_dataset}"
            dataset = self._client.get_dataset(dataset_ref)

            # Count tables in dataset
            tables = list(self._client.list_tables(dataset))
            table_count = len(tables)

            return {
                'success': True,
                'message': f'Connected successfully to {dataset_ref}. Found {table_count} tables.'
            }
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {
                'success': False,
                'message': f'Connection failed: {str(e)}'
            }

    def extract_full(
        self,
        table_name: str,
        schema_name: str,
        selected_columns: List[str],
        batch_size: int = 10000
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Extract all data from a BigQuery table.

        Args:
            table_name: Name of the source table
            schema_name: Dataset name (used as schema_name for consistency)
            selected_columns: List of column names to extract (empty = all columns)
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            pandas DataFrame containing batches of rows
        """
        # Build column list
        column_list = self._build_column_list(selected_columns)

        # Use schema_name as dataset if provided, otherwise use connection's dataset
        dataset = schema_name if schema_name else self.source_dataset

        # Build fully qualified table reference
        table_ref = f"`{self.source_project}.{dataset}.{table_name}`"

        query = f"""
            SELECT {column_list}
            FROM {table_ref}
        """

        logger.info(f"Starting full extraction from {table_ref}")
        logger.debug(f"Query: {query}")

        try:
            # Execute query and iterate in batches
            query_job = self._client.query(query)

            batch_num = 0
            rows_buffer = []

            for row in query_job.result():
                rows_buffer.append(dict(row))

                if len(rows_buffer) >= batch_size:
                    batch_num += 1
                    df = pd.DataFrame(rows_buffer)
                    logger.info(f"Extracted batch {batch_num}: {len(df)} rows")
                    yield df
                    rows_buffer = []

            # Yield remaining rows
            if rows_buffer:
                batch_num += 1
                df = pd.DataFrame(rows_buffer)
                logger.info(f"Extracted final batch {batch_num}: {len(df)} rows")
                yield df

            logger.info(f"Full extraction completed from {table_ref}")

        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            raise

    def extract_incremental(
        self,
        table_name: str,
        schema_name: str,
        timestamp_column: str,
        since_datetime: str,
        selected_columns: List[str],
        batch_size: int = 10000
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Extract data incrementally from a BigQuery table.

        Args:
            table_name: Name of the source table
            schema_name: Dataset name (used as schema_name for consistency)
            timestamp_column: Column name for filtering (e.g., 'creation_date')
            since_datetime: Start datetime in ISO format (e.g., '2024-01-01T00:00:00')
            selected_columns: List of column names to extract
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            pandas DataFrame containing batches of rows
        """
        # Build column list
        column_list = self._build_column_list(selected_columns)

        # Use schema_name as dataset if provided, otherwise use connection's dataset
        dataset = schema_name if schema_name else self.source_dataset

        # Build fully qualified table reference
        table_ref = f"`{self.source_project}.{dataset}.{table_name}`"

        # Sanitize timestamp column (remove backticks if present)
        timestamp_col = timestamp_column.strip('`')

        query = f"""
            SELECT {column_list}
            FROM {table_ref}
            WHERE `{timestamp_col}` >= TIMESTAMP('{since_datetime}')
            ORDER BY `{timestamp_col}`
        """

        logger.info(f"Starting incremental extraction from {table_ref}")
        logger.info(f"Timestamp column: {timestamp_col}, Since: {since_datetime}")
        logger.debug(f"Query: {query}")

        try:
            # Execute query and iterate in batches
            query_job = self._client.query(query)

            batch_num = 0
            total_rows = 0
            rows_buffer = []

            for row in query_job.result():
                rows_buffer.append(dict(row))

                if len(rows_buffer) >= batch_size:
                    batch_num += 1
                    total_rows += len(rows_buffer)
                    df = pd.DataFrame(rows_buffer)
                    logger.info(f"Extracted batch {batch_num}: {len(df)} rows (total: {total_rows})")
                    yield df
                    rows_buffer = []

            # Yield remaining rows
            if rows_buffer:
                batch_num += 1
                total_rows += len(rows_buffer)
                df = pd.DataFrame(rows_buffer)
                logger.info(f"Extracted final batch {batch_num}: {len(df)} rows (total: {total_rows})")
                yield df

            logger.info(f"Incremental extraction completed: {total_rows} total rows")

        except Exception as e:
            logger.error(f"Incremental extraction failed: {str(e)}")
            raise

    def get_row_count(
        self,
        table_name: str,
        schema_name: str,
        where_clause: Optional[str] = None
    ) -> int:
        """
        Get total row count for a BigQuery table.

        Args:
            table_name: Name of the source table
            schema_name: Dataset name
            where_clause: Optional WHERE clause (without 'WHERE' keyword)

        Returns:
            Total number of rows
        """
        # Use schema_name as dataset if provided, otherwise use connection's dataset
        dataset = schema_name if schema_name else self.source_dataset

        # Build fully qualified table reference
        table_ref = f"`{self.source_project}.{dataset}.{table_name}`"

        if where_clause:
            query = f'SELECT COUNT(*) as count FROM {table_ref} WHERE {where_clause}'
        else:
            query = f'SELECT COUNT(*) as count FROM {table_ref}'

        logger.debug(f"Row count query: {query}")

        try:
            query_job = self._client.query(query)
            result = list(query_job.result())
            count = result[0]['count']

            logger.info(f"Row count for {table_ref}: {count:,}")
            return count

        except Exception as e:
            logger.error(f"Row count failed: {str(e)}")
            raise

    def estimate_row_count(
        self,
        table_name: str,
        schema_name: str,
        timestamp_column: Optional[str] = None,
        since_datetime: Optional[str] = None
    ) -> int:
        """
        Estimate row count for ETL job (handles both full and incremental loads).

        For full loads: Returns total row count
        For incremental loads: Returns count of rows since timestamp

        Args:
            table_name: Name of the source table
            schema_name: Dataset name
            timestamp_column: Column name for incremental filtering (optional)
            since_datetime: Start datetime for incremental filtering (optional)

        Returns:
            Estimated number of rows to be extracted
        """
        if timestamp_column and since_datetime:
            # Incremental load: count rows since last sync
            timestamp_col = timestamp_column.strip('`')
            where_clause = f"`{timestamp_col}` >= TIMESTAMP('{since_datetime}')"
            logger.info(f"Estimating incremental row count: {where_clause}")
            return self.get_row_count(table_name, schema_name, where_clause)
        else:
            # Full load: count all rows
            logger.info(f"Estimating full row count for {schema_name}.{table_name}")
            return self.get_row_count(table_name, schema_name)

    def close(self):
        """Close the BigQuery client connection"""
        if self._client:
            self._client.close()
            logger.info("BigQuery client connection closed")
