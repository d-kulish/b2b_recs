"""
PostgreSQL Extractor

Extracts data from PostgreSQL databases using server-side cursors for memory efficiency.
"""

from typing import Generator, List, Dict, Any, Optional
import pandas as pd
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from .base import BaseExtractor

logger = logging.getLogger(__name__)


class PostgreSQLExtractor(BaseExtractor):
    """Extractor for PostgreSQL databases"""

    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize PostgreSQL extractor.

        Args:
            connection_params: Dictionary with connection details
                - host: PostgreSQL host
                - port: PostgreSQL port (default: 5432)
                - database: Database name
                - username: Database username
                - password: Database password
                - sslmode: SSL mode (optional, default: 'prefer')
        """
        super().__init__(connection_params)
        self.port = self.port or 5432
        self.sslmode = connection_params.get('sslmode', 'prefer')
        self._connection = None

    def _get_connection(self):
        """
        Get or create a database connection.

        Returns:
            psycopg2 connection object
        """
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
                sslmode=self.sslmode
            )
            logger.info(f"Connected to PostgreSQL: {self.host}:{self.port}/{self.database}")

        return self._connection

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the PostgreSQL connection.

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]

            return {
                'success': True,
                'message': f'Connected successfully. {version}'
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
        Extract all data from a PostgreSQL table.

        Args:
            table_name: Name of the source table
            schema_name: Schema name
            selected_columns: List of column names to extract
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            pandas DataFrame containing batches of rows
        """
        conn = self._get_connection()
        column_list = self._build_column_list(selected_columns)

        query = f"""
            SELECT {column_list}
            FROM "{schema_name}"."{table_name}"
        """

        logger.info(f"Starting full extraction: {schema_name}.{table_name}")
        logger.debug(f"Query: {query}")

        try:
            # Use server-side cursor for memory efficiency
            with conn.cursor(name='etl_full_cursor') as cursor:
                cursor.itersize = batch_size
                cursor.execute(query)

                batch_num = 0
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    batch_num += 1
                    df = pd.DataFrame(rows, columns=selected_columns)
                    logger.info(f"Extracted batch {batch_num}: {len(df)} rows")
                    yield df

            logger.info(f"Full extraction completed: {schema_name}.{table_name}")

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
        Extract data incrementally from a PostgreSQL table.

        Args:
            table_name: Name of the source table
            schema_name: Schema name
            timestamp_column: Column name for filtering (e.g., 'created_at')
            since_datetime: Start datetime in ISO format (e.g., '2024-01-01T00:00:00')
            selected_columns: List of column names to extract
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            pandas DataFrame containing batches of rows
        """
        conn = self._get_connection()
        column_list = self._build_column_list(selected_columns)
        timestamp_col_sanitized = self._sanitize_column_name(timestamp_column)

        query = f"""
            SELECT {column_list}
            FROM "{schema_name}"."{table_name}"
            WHERE "{timestamp_col_sanitized}" >= %s
            ORDER BY "{timestamp_col_sanitized}"
        """

        logger.info(f"Starting incremental extraction: {schema_name}.{table_name}")
        logger.info(f"Timestamp column: {timestamp_column}, Since: {since_datetime}")
        logger.debug(f"Query: {query}")

        try:
            # Use server-side cursor for memory efficiency
            with conn.cursor(name='etl_incremental_cursor') as cursor:
                cursor.itersize = batch_size
                cursor.execute(query, (since_datetime,))

                batch_num = 0
                total_rows = 0
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    batch_num += 1
                    total_rows += len(rows)
                    df = pd.DataFrame(rows, columns=selected_columns)
                    logger.info(f"Extracted batch {batch_num}: {len(df)} rows (total: {total_rows})")
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
        Get total row count for a PostgreSQL table.

        Args:
            table_name: Name of the source table
            schema_name: Schema name
            where_clause: Optional WHERE clause (without 'WHERE' keyword)

        Returns:
            Total number of rows
        """
        conn = self._get_connection()

        if where_clause:
            query = f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}" WHERE {where_clause}'
        else:
            query = f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"'

        logger.debug(f"Row count query: {query}")

        try:
            with conn.cursor() as cursor:
                cursor.execute(query)
                count = cursor.fetchone()[0]

            logger.info(f"Row count for {schema_name}.{table_name}: {count:,}")
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
            schema_name: Schema name
            timestamp_column: Column name for incremental filtering (optional)
            since_datetime: Start datetime for incremental filtering (optional)

        Returns:
            Estimated number of rows to be extracted
        """
        if timestamp_column and since_datetime:
            # Incremental load: count rows since last sync
            timestamp_col_sanitized = self._sanitize_column_name(timestamp_column)
            where_clause = f'"{timestamp_col_sanitized}" >= \'{since_datetime}\''
            logger.info(f"Estimating incremental row count: {where_clause}")
            return self.get_row_count(table_name, schema_name, where_clause)
        else:
            # Full load: count all rows
            logger.info(f"Estimating full row count for {schema_name}.{table_name}")
            return self.get_row_count(table_name, schema_name)

    def extract_incremental_raw(
        self,
        table_name: str,
        schema_name: str,
        timestamp_column: str,
        since_datetime: str,
        selected_columns: List[str],
        batch_size: int = 10000
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Extract data incrementally, yielding dicts (NO PANDAS).

        This is optimized for Dataflow - no DataFrame overhead.
        Each row is yielded as a dict immediately after fetching from cursor.

        Args:
            table_name: Name of the source table
            schema_name: Schema name
            timestamp_column: Column name for filtering (e.g., 'created_at')
            since_datetime: Start datetime in ISO format (e.g., '2024-01-01T00:00:00')
            selected_columns: List of column names to extract
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            Dict representing a single row (keys are column names)
        """
        conn = self._get_connection()
        column_list = self._build_column_list(selected_columns)
        timestamp_col_sanitized = self._sanitize_column_name(timestamp_column)

        query = f"""
            SELECT {column_list}
            FROM "{schema_name}"."{table_name}"
            WHERE "{timestamp_col_sanitized}" >= %s
            ORDER BY "{timestamp_col_sanitized}"
        """

        logger.info(f"Starting raw incremental extraction: {schema_name}.{table_name}")
        logger.info(f"Timestamp column: {timestamp_column}, Since: {since_datetime}")
        logger.debug(f"Query: {query}")

        try:
            # Use server-side cursor for memory efficiency
            with conn.cursor(name='etl_raw_incremental_cursor') as cursor:
                cursor.itersize = batch_size
                cursor.execute(query, (since_datetime,))

                # Get column names from cursor description
                column_names = [desc[0] for desc in cursor.description]

                row_count = 0
                batch_num = 0
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    batch_num += 1
                    # Convert each tuple to dict and yield immediately
                    for row_tuple in rows:
                        row_dict = dict(zip(column_names, row_tuple))
                        row_count += 1
                        yield row_dict

                    if batch_num % 10 == 0:  # Log every 10 batches
                        logger.info(f"Extracted {row_count} rows (batch {batch_num})")

            logger.info(f"Raw incremental extraction completed: {row_count} total rows")

        except Exception as e:
            logger.error(f"Raw incremental extraction failed: {str(e)}")
            raise

    def extract_full_raw(
        self,
        table_name: str,
        schema_name: str,
        selected_columns: List[str],
        batch_size: int = 10000
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Extract all data from table, yielding dicts (NO PANDAS).

        This is optimized for Dataflow - no DataFrame overhead.
        Each row is yielded as a dict immediately after fetching from cursor.

        Args:
            table_name: Name of the source table
            schema_name: Schema name
            selected_columns: List of column names to extract
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            Dict representing a single row (keys are column names)
        """
        conn = self._get_connection()
        column_list = self._build_column_list(selected_columns)

        query = f"""
            SELECT {column_list}
            FROM "{schema_name}"."{table_name}"
        """

        logger.info(f"Starting raw full extraction: {schema_name}.{table_name}")
        logger.debug(f"Query: {query}")

        try:
            # Use server-side cursor for memory efficiency
            with conn.cursor(name='etl_raw_full_cursor') as cursor:
                cursor.itersize = batch_size
                cursor.execute(query)

                # Get column names from cursor description
                column_names = [desc[0] for desc in cursor.description]

                row_count = 0
                batch_num = 0
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    batch_num += 1
                    # Convert each tuple to dict and yield immediately
                    for row_tuple in rows:
                        row_dict = dict(zip(column_names, row_tuple))
                        row_count += 1
                        yield row_dict

                    if batch_num % 10 == 0:  # Log every 10 batches
                        logger.info(f"Extracted {row_count} rows (batch {batch_num})")

            logger.info(f"Raw full extraction completed: {row_count} total rows")

        except Exception as e:
            logger.error(f"Raw full extraction failed: {str(e)}")
            raise

    def close(self):
        """Close the PostgreSQL connection"""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.info("PostgreSQL connection closed")
