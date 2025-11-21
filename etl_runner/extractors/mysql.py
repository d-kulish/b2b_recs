"""
MySQL Extractor

Extracts data from MySQL databases using SSCursor for streaming results.
"""

from typing import Generator, List, Dict, Any, Optional
import pandas as pd
import logging
import pymysql
from pymysql.cursors import SSCursor
from .base import BaseExtractor

logger = logging.getLogger(__name__)


class MySQLExtractor(BaseExtractor):
    """Extractor for MySQL databases"""

    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize MySQL extractor.

        Args:
            connection_params: Dictionary with connection details
                - host: MySQL host
                - port: MySQL port (default: 3306)
                - database: Database name
                - username: Database username
                - password: Database password
                - ssl: Enable SSL (optional, default: False)
        """
        super().__init__(connection_params)
        self.port = self.port or 3306
        self.ssl = connection_params.get('ssl', False)
        self._connection = None

    def _get_connection(self):
        """
        Get or create a database connection.

        Returns:
            pymysql connection object
        """
        if self._connection is None or not self._connection.open:
            connect_args = {
                'host': self.host,
                'port': self.port,
                'database': self.database,
                'user': self.username,
                'password': self.password,
                'charset': 'utf8mb4',
                'cursorclass': pymysql.cursors.DictCursor
            }

            if self.ssl:
                connect_args['ssl'] = {'ssl': True}

            self._connection = pymysql.connect(**connect_args)
            logger.info(f"Connected to MySQL: {self.host}:{self.port}/{self.database}")

        return self._connection

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the MySQL connection.

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION();")
                version = cursor.fetchone()['VERSION()']

            return {
                'success': True,
                'message': f'Connected successfully. MySQL {version}'
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
        Extract all data from a MySQL table.

        Args:
            table_name: Name of the source table
            schema_name: Schema/database name (MySQL uses database, not schema)
            selected_columns: List of column names to extract
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            pandas DataFrame containing batches of rows
        """
        conn = self._get_connection()
        column_list = self._build_column_list(selected_columns)

        # MySQL uses backticks for identifiers
        query = f"""
            SELECT {column_list.replace('"', '`')}
            FROM `{schema_name}`.`{table_name}`
        """

        logger.info(f"Starting full extraction: {schema_name}.{table_name}")
        logger.debug(f"Query: {query}")

        try:
            # Use SSCursor for streaming results (unbuffered)
            with conn.cursor(SSCursor) as cursor:
                cursor.execute(query)

                batch_num = 0
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    batch_num += 1
                    # Convert rows to list of dicts if needed
                    if isinstance(rows[0], tuple):
                        rows_data = [dict(zip(selected_columns, row)) for row in rows]
                    else:
                        rows_data = rows

                    df = pd.DataFrame(rows_data)
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
        Extract data incrementally from a MySQL table.

        Args:
            table_name: Name of the source table
            schema_name: Schema/database name
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

        # MySQL uses backticks for identifiers
        query = f"""
            SELECT {column_list.replace('"', '`')}
            FROM `{schema_name}`.`{table_name}`
            WHERE `{timestamp_col_sanitized}` >= %s
            ORDER BY `{timestamp_col_sanitized}`
        """

        logger.info(f"Starting incremental extraction: {schema_name}.{table_name}")
        logger.info(f"Timestamp column: {timestamp_column}, Since: {since_datetime}")
        logger.debug(f"Query: {query}")

        try:
            # Use SSCursor for streaming results
            with conn.cursor(SSCursor) as cursor:
                cursor.execute(query, (since_datetime,))

                batch_num = 0
                total_rows = 0
                while True:
                    rows = cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    batch_num += 1
                    total_rows += len(rows)

                    # Convert rows to list of dicts if needed
                    if isinstance(rows[0], tuple):
                        rows_data = [dict(zip(selected_columns, row)) for row in rows]
                    else:
                        rows_data = rows

                    df = pd.DataFrame(rows_data)
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
        Get total row count for a MySQL table.

        Args:
            table_name: Name of the source table
            schema_name: Schema/database name
            where_clause: Optional WHERE clause (without 'WHERE' keyword)

        Returns:
            Total number of rows
        """
        conn = self._get_connection()

        if where_clause:
            query = f'SELECT COUNT(*) as count FROM `{schema_name}`.`{table_name}` WHERE {where_clause}'
        else:
            query = f'SELECT COUNT(*) as count FROM `{schema_name}`.`{table_name}`'

        logger.debug(f"Row count query: {query}")

        try:
            with conn.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchone()
                count = result['count']

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
            schema_name: Schema/database name
            timestamp_column: Column name for incremental filtering (optional)
            since_datetime: Start datetime for incremental filtering (optional)

        Returns:
            Estimated number of rows to be extracted
        """
        if timestamp_column and since_datetime:
            # Incremental load: count rows since last sync
            timestamp_col_sanitized = self._sanitize_column_name(timestamp_column)
            where_clause = f'`{timestamp_col_sanitized}` >= \'{since_datetime}\''
            logger.info(f"Estimating incremental row count: {where_clause}")
            return self.get_row_count(table_name, schema_name, where_clause)
        else:
            # Full load: count all rows
            logger.info(f"Estimating full row count for {schema_name}.{table_name}")
            return self.get_row_count(table_name, schema_name)

    def close(self):
        """Close the MySQL connection"""
        if self._connection and self._connection.open:
            self._connection.close()
            logger.info("MySQL connection closed")
