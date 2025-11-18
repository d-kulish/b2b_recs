"""
Base Extractor Abstract Class

This module defines the base interface for all data extractors.
All source-specific extractors (PostgreSQL, MySQL, etc.) must inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import Generator, List, Dict, Any, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Abstract base class for data extractors"""

    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize the extractor with connection parameters.

        Args:
            connection_params: Dictionary containing connection details
                - host: Database host
                - port: Database port
                - database: Database name
                - username: Database username
                - password: Database password
                - Additional source-specific params
        """
        self.connection_params = connection_params
        self.host = connection_params.get('host')
        self.port = connection_params.get('port')
        self.database = connection_params.get('database')
        self.username = connection_params.get('username')
        self.password = connection_params.get('password')

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Test the database connection.

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        pass

    @abstractmethod
    def extract_full(
        self,
        table_name: str,
        schema_name: str,
        selected_columns: List[str],
        batch_size: int = 10000
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Extract all data from a table (full snapshot).

        Args:
            table_name: Name of the source table
            schema_name: Schema/database name
            selected_columns: List of column names to extract
            batch_size: Number of rows to fetch per batch (default: 10000)

        Yields:
            pandas DataFrame containing batches of rows
        """
        pass

    @abstractmethod
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
        Extract data incrementally using a timestamp column.

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
        pass

    @abstractmethod
    def get_row_count(
        self,
        table_name: str,
        schema_name: str,
        where_clause: Optional[str] = None
    ) -> int:
        """
        Get total row count for a table.

        Args:
            table_name: Name of the source table
            schema_name: Schema/database name
            where_clause: Optional WHERE clause (without 'WHERE' keyword)

        Returns:
            Total number of rows
        """
        pass

    def _sanitize_column_name(self, column_name: str) -> str:
        """
        Sanitize column name to prevent SQL injection.

        Args:
            column_name: Raw column name

        Returns:
            Sanitized column name
        """
        # Remove any quotes and validate
        column_name = column_name.replace('"', '').replace("'", '')

        # Validate: only allow alphanumeric, underscore, and limited special chars
        if not column_name.replace('_', '').replace('.', '').isalnum():
            raise ValueError(f"Invalid column name: {column_name}")

        return column_name

    def _build_column_list(self, selected_columns: List[str]) -> str:
        """
        Build a comma-separated list of quoted column names.

        Args:
            selected_columns: List of column names

        Returns:
            Comma-separated string of quoted column names
        """
        sanitized = [self._sanitize_column_name(col) for col in selected_columns]
        return ', '.join(f'"{col}"' for col in sanitized)

    def close(self):
        """
        Close any open connections.
        Override in subclasses if needed.
        """
        pass
