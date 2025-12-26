"""
Apache Beam ETL Pipeline for Large-Scale Data Processing

This module provides Dataflow pipelines for processing large datasets (>= 1M rows)
using Apache Beam. Supports both database and file sources.
"""

import logging
import apache_beam as beam
from apache_beam.options.pipeline_options import (
    PipelineOptions, GoogleCloudOptions, StandardOptions, WorkerOptions, SetupOptions
)
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition
from apache_beam.io.gcp.internal.clients.bigquery import TableSchema, TableFieldSchema
from typing import Dict, Any, List
import json
import csv
import io
from datetime import date, datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


def _serialize_value(value: Any) -> Any:
    """
    Serialize value to JSON-compatible format using PURE PYTHON.
    NO pandas, NO numpy - only standard Python types from database cursors.

    Database cursors return:
    - None, int, float, str, bool (pass through)
    - datetime.datetime, datetime.date (convert to ISO string)
    - decimal.Decimal (convert to float)
    - bytes (convert to base64)
    - list/tuple (for PostgreSQL arrays - recursive)
    - dict (for PostgreSQL JSON/JSONB - recursive)

    Args:
        value: Any Python value to serialize

    Returns:
        JSON-serializable value
    """
    from datetime import datetime, date
    from decimal import Decimal
    import math

    # 1. Handle None first (most common case)
    if value is None:
        return None

    # 2. Handle complex types FIRST (before any type checks)
    # PostgreSQL arrays: [1, 2, 3], BigQuery REPEATED fields
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return []
        return [_serialize_value(item) for item in value]

    # PostgreSQL JSON/JSONB, BigQuery RECORD fields
    if isinstance(value, dict):
        if len(value) == 0:
            return {}
        return {k: _serialize_value(v) for k, v in value.items()}

    # 3. Handle datetime types (from database)
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    # 4. Handle Decimal (from database NUMERIC/DECIMAL columns)
    if isinstance(value, Decimal):
        # Check for special values
        if value.is_nan():
            return None
        if value.is_infinite():
            return None
        return float(value)

    # 5. Handle floats - check for NaN/Inf (JSON doesn't support these)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    # 6. Handle bytes (from database BYTEA columns)
    if isinstance(value, bytes):
        import base64
        return base64.b64encode(value).decode('utf-8')

    # 7. Pass through JSON-safe types
    if isinstance(value, (int, bool, str)):
        return value

    # 8. Unknown type - log warning and convert to string
    logger.warning(f"Unknown type in serialization: {type(value).__name__} - value: {str(value)[:100]}")
    try:
        return str(value)
    except:
        return None


def serialize_value_for_schema(value: Any, target_type: str) -> Any:
    """
    Convert a value to match the target BigQuery field type.

    Handles schema mismatches by converting values to the expected type:
    - ARRAY value → STRING type: Convert to JSON string
    - STRING value → INTEGER type: Parse to int
    - Etc.

    Args:
        value: The value to convert
        target_type: BigQuery field type (STRING, INTEGER, etc.)

    Returns:
        Value converted to match target type
    """
    import json

    # Handle None/null values
    if value is None:
        return None

    # Handle schema mismatches
    if target_type == 'STRING':
        # If destination is STRING but value is array/dict, convert to JSON
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        # Otherwise convert to string
        return str(value) if not isinstance(value, str) else value

    elif target_type in ('INTEGER', 'INT64'):
        # If destination is INTEGER, ensure we have int
        if isinstance(value, str):
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        return int(value) if not isinstance(value, int) else value

    elif target_type in ('FLOAT', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'):
        # If destination is FLOAT, ensure we have float
        if isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return float(value) if not isinstance(value, float) else value

    # For other types, return as-is (already serialized by _serialize_value)
    return value


def serialize_row_for_bigquery(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert row dict to BigQuery-compatible JSON-serializable dict.

    This function handles all types that can come from database cursors:
    - datetime.date → 'YYYY-MM-DD' string
    - datetime.datetime → 'YYYY-MM-DDTHH:MM:SS' ISO string
    - Decimal → float
    - Lists (PostgreSQL arrays, BigQuery REPEATED) → Recursively serialized list
    - Dicts (PostgreSQL JSON, BigQuery RECORD) → Recursively serialized dict
    - bytes → base64 string
    - None → None
    - float NaN/Inf → None

    Args:
        row_dict: Dictionary representing a row from database cursor

    Returns:
        JSON-serializable dictionary safe for BigQuery WriteToBigQuery

    Examples:
        >>> from datetime import date
        >>> from decimal import Decimal
        >>> row = {'date': date(2025, 11, 23), 'amount': Decimal('123.45')}
        >>> serialize_row_for_bigquery(row)
        {'date': '2025-11-23', 'amount': 123.45}

        >>> # Arrays (PostgreSQL array type)
        >>> row = {'tags': ['python', 'bigquery', 'dataflow'], 'count': 3}
        >>> serialize_row_for_bigquery(row)
        {'tags': ['python', 'bigquery', 'dataflow'], 'count': 3}

        >>> # Nested dicts (PostgreSQL JSONB)
        >>> row = {'user': {'name': 'Alice', 'age': 30}, 'active': True}
        >>> serialize_row_for_bigquery(row)
        {'user': {'name': 'Alice', 'age': 30}, 'active': True}
    """
    # Use the recursive pure Python serialization for each field
    return {key: _serialize_value(value) for key, value in row_dict.items()}


class SchemaAwareConverter(beam.DoFn):
    """
    Schema-aware converter that matches values to BigQuery destination schema types.

    This is CRITICAL for handling schema mismatches:
    - Source has array → Destination expects STRING → Convert array to JSON string
    - Source has dict → Destination expects STRING → Convert dict to JSON string
    - Source has string datetime → Destination expects TIMESTAMP → Keep as ISO string

    This DoFn runs AFTER pure Python serialization (_serialize_value) which handles
    datetime/Decimal/NaN conversion. This DoFn ONLY handles type mismatches.
    """

    def __init__(self, schema_map: Dict[str, str]):
        """
        Initialize with destination schema type mapping.

        Args:
            schema_map: Dict of {field_name: field_type} from BigQuery schema
        """
        self.schema_map = schema_map

    def process(self, row_dict: Dict[str, Any]):
        """
        Convert row values to match destination schema types.

        Args:
            row_dict: Row dictionary (already serialized by _serialize_value)

        Yields:
            Schema-matched dictionary ready for BigQuery
        """
        import json

        schema_matched_row = {}
        for key, value in row_dict.items():
            if value is None:
                schema_matched_row[key] = None
                continue

            # Get expected type from schema
            target_type = self.schema_map.get(key)

            if target_type == 'STRING':
                # If destination is STRING but value is array/dict, convert to JSON string
                if isinstance(value, (list, dict)):
                    schema_matched_row[key] = json.dumps(value)
                else:
                    # Already a string or will be converted to string
                    schema_matched_row[key] = str(value) if not isinstance(value, str) else value

            elif target_type in ('INTEGER', 'INT64'):
                # Ensure integer type
                if isinstance(value, str):
                    try:
                        schema_matched_row[key] = int(value)
                    except (ValueError, TypeError):
                        schema_matched_row[key] = None
                else:
                    schema_matched_row[key] = int(value) if value is not None else None

            elif target_type in ('FLOAT', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'):
                # Ensure float type
                if isinstance(value, str):
                    try:
                        schema_matched_row[key] = float(value)
                    except (ValueError, TypeError):
                        schema_matched_row[key] = None
                else:
                    schema_matched_row[key] = float(value) if value is not None else None

            elif target_type == 'TIMESTAMP':
                # Convert date strings to timestamp format for BigQuery
                if isinstance(value, str):
                    # If it's a date-only string (YYYY-MM-DD), add time component
                    if len(value) == 10 and '-' in value:
                        schema_matched_row[key] = f"{value}T00:00:00"
                    else:
                        schema_matched_row[key] = value
                else:
                    schema_matched_row[key] = value

            elif target_type in ('DATE', 'DATETIME'):
                # These should already be ISO strings from _serialize_value
                schema_matched_row[key] = value

            elif target_type == 'BOOLEAN':
                # Ensure boolean type
                if isinstance(value, str):
                    schema_matched_row[key] = value.lower() in ('true', '1', 'yes')
                else:
                    schema_matched_row[key] = bool(value) if value is not None else None

            else:
                # Unknown or RECORD/REPEATED type - pass through
                schema_matched_row[key] = value

        yield schema_matched_row


class ParseCSVLine(beam.DoFn):
    """
    Parse CSV lines using Python's csv module for robust handling.

    Handles:
    - Quoted fields with commas inside (e.g., "Smith, John")
    - Escaped quotes
    - Custom delimiters and encodings

    Skipped records (parsing errors, field count mismatch) are logged
    and counted but don't fail the pipeline.
    """

    def __init__(self, column_names: List[str], delimiter: str = ',', encoding: str = 'utf-8'):
        """
        Initialize CSV parser with schema information.

        Args:
            column_names: List of column names from wizard schema
            delimiter: CSV delimiter (default ',')
            encoding: File encoding (default 'utf-8')
        """
        self.column_names = column_names
        self.delimiter = delimiter
        self.encoding = encoding

    def setup(self):
        """Initialize counters for monitoring."""
        self.rows_parsed = 0
        self.rows_skipped = 0

    def process(self, line: str):
        """
        Parse a single CSV line and yield a dict.

        Args:
            line: Raw CSV line string

        Yields:
            Dict mapping column names to values
        """
        # Skip empty lines
        if not line or not line.strip():
            return

        try:
            # Use csv.reader for robust parsing (handles quotes, escapes)
            reader = csv.reader([line], delimiter=self.delimiter)
            fields = next(reader)

            # Validate field count matches schema
            if len(fields) != len(self.column_names):
                self.rows_skipped += 1
                logger.warning(
                    f"Field count mismatch: expected {len(self.column_names)}, "
                    f"got {len(fields)}. Line skipped."
                )
                # Increment Beam counter for visibility in Dataflow UI
                from apache_beam.metrics import Metrics
                Metrics.counter('ParseCSVLine', 'rows_skipped_field_mismatch').inc()
                return

            # Create dict mapping column names to values
            row_dict = {}
            for col_name, value in zip(self.column_names, fields):
                # Handle empty strings as None
                row_dict[col_name] = value if value != '' else None

            self.rows_parsed += 1
            yield row_dict

        except csv.Error as e:
            self.rows_skipped += 1
            logger.warning(f"CSV parsing error: {e}. Line skipped.")
            from apache_beam.metrics import Metrics
            Metrics.counter('ParseCSVLine', 'rows_skipped_parse_error').inc()
        except Exception as e:
            self.rows_skipped += 1
            logger.warning(f"Unexpected error parsing CSV line: {e}. Line skipped.")
            from apache_beam.metrics import Metrics
            Metrics.counter('ParseCSVLine', 'rows_skipped_unexpected_error').inc()

    def teardown(self):
        """Log final statistics."""
        logger.info(f"ParseCSVLine complete: {self.rows_parsed} parsed, {self.rows_skipped} skipped")


class ParseJSONLine(beam.DoFn):
    """
    Parse JSON Lines (JSONL) format - one JSON object per line.

    Skipped records (invalid JSON) are logged and counted
    but don't fail the pipeline.
    """

    def __init__(self, column_names: List[str] = None):
        """
        Initialize JSON parser.

        Args:
            column_names: Optional list of columns to extract (None = all)
        """
        self.column_names = column_names

    def setup(self):
        """Initialize counters for monitoring."""
        self.rows_parsed = 0
        self.rows_skipped = 0

    def process(self, line: str):
        """
        Parse a single JSON line and yield a dict.

        Args:
            line: Raw JSON line string

        Yields:
            Dict from parsed JSON
        """
        # Skip empty lines
        if not line or not line.strip():
            return

        try:
            row_dict = json.loads(line)

            # Filter to selected columns if specified
            if self.column_names:
                row_dict = {k: row_dict.get(k) for k in self.column_names}

            self.rows_parsed += 1
            yield row_dict

        except json.JSONDecodeError as e:
            self.rows_skipped += 1
            logger.warning(f"JSON parsing error: {e}. Line skipped.")
            from apache_beam.metrics import Metrics
            Metrics.counter('ParseJSONLine', 'rows_skipped_json_error').inc()
        except Exception as e:
            self.rows_skipped += 1
            logger.warning(f"Unexpected error parsing JSON line: {e}. Line skipped.")
            from apache_beam.metrics import Metrics
            Metrics.counter('ParseJSONLine', 'rows_skipped_unexpected_error').inc()

    def teardown(self):
        """Log final statistics."""
        logger.info(f"ParseJSONLine complete: {self.rows_parsed} parsed, {self.rows_skipped} skipped")


class UnifiedExtractor(beam.DoFn):
    """
    Unified DoFn that processes any work unit type without pandas.

    This DoFn replaces DatabaseToDataFrame and FileToRows with a single,
    source-agnostic implementation that:
    1. Processes different work unit types (date ranges, ID ranges, files, etc.)
    2. Extracts data WITHOUT pandas (uses database cursors, file readers directly)
    3. Yields JSON-serializable dicts
    4. Runs in parallel across Dataflow workers

    Supported work unit types:
    - db_date_range: Database extraction filtered by date range
    - db_id_range: Database extraction filtered by ID range
    - db_hash_partition: Database extraction using hash partitioning
    - file: File extraction (CSV, Parquet, JSON)
    - bigquery_native: Handled by ReadFromBigQuery (not used by this DoFn)
    """

    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize extractor with connection parameters.

        Args:
            connection_params: Connection details (varies by source type)
        """
        self.connection_params = connection_params
        self.source_type = connection_params.get('source_type')

    def setup(self):
        """
        Initialize connections (runs once per worker).

        For databases: Establish connection pool
        For files: Initialize cloud storage client
        """
        logger.info(f"UnifiedExtractor.setup() - Source type: {self.source_type}")

        if self.source_type in ('postgresql', 'mysql', 'bigquery'):
            # Database connections will be created per work unit
            # (lighter weight than maintaining persistent connections)
            self.db_connection = None
        elif self.source_type in ('gcs', 's3', 'azure_blob'):
            # Initialize file storage client
            from extractors.file_extractor import FileExtractor
            # Create temporary extractor for client initialization
            self.storage_client = None

        logger.info("UnifiedExtractor setup complete")

    def process(self, work_unit: Dict[str, Any]):
        """
        Process a single work unit and yield rows.

        Args:
            work_unit: Dict describing what to extract
                      {'type': 'db_date_range', 'table_name': '...', ...}

        Yields:
            Dicts representing rows (JSON-serializable, ready for BigQuery)
        """
        work_type = work_unit.get('type')
        logger.info(f"Processing work unit type: {work_type}")

        try:
            if work_type == 'db_date_range':
                yield from self._process_db_date_range(work_unit)
            elif work_type == 'db_date_range_full':
                yield from self._process_db_full(work_unit)
            elif work_type == 'db_id_range':
                yield from self._process_db_id_range(work_unit)
            elif work_type == 'db_hash_partition':
                yield from self._process_db_hash_partition(work_unit)
            elif work_type == 'file':
                yield from self._process_file(work_unit)
            else:
                raise ValueError(f"Unknown work unit type: {work_type}")

        except Exception as e:
            logger.error(f"Failed to process work unit: {work_unit}")
            logger.error(f"Error: {e}", exc_info=True)
            raise

    def _process_db_date_range(self, work_unit: Dict[str, Any]):
        """
        Process database work unit with date range filter.

        Extracts rows where timestamp BETWEEN start_date AND end_date.
        Uses database cursor directly (no pandas).
        """
        table_name = work_unit['table_name']
        schema_name = work_unit['schema_name']
        timestamp_column = work_unit['timestamp_column']
        start_date = work_unit['start_date']
        end_date = work_unit['end_date']
        selected_columns = work_unit.get('selected_columns', [])

        logger.info(f"Extracting {schema_name}.{table_name} where {timestamp_column} between {start_date} and {end_date}")

        # Get database extractor
        extractor = self._get_database_extractor()

        # Use RAW cursor-based extraction (NO PANDAS - yields dicts directly)
        row_gen = extractor.extract_incremental_raw(
            table_name=table_name,
            schema_name=schema_name,
            timestamp_column=timestamp_column,
            since_datetime=start_date,
            selected_columns=selected_columns,
            batch_size=10000
        )

        row_count = 0
        for row_dict in row_gen:
            # Filter to end_date (extractor only filters >= start)
            row_timestamp = row_dict.get(timestamp_column)
            if row_timestamp and row_timestamp >= end_date:
                continue  # Skip rows beyond end_date

            # Serialize using pure Python (no pandas)
            serialized_row = {key: _serialize_value(value) for key, value in row_dict.items()}
            yield serialized_row
            row_count += 1

        logger.info(f"Extracted {row_count} rows from work unit")

    def _process_db_full(self, work_unit: Dict[str, Any]):
        """Process full table extraction (no date filter)"""
        table_name = work_unit['table_name']
        schema_name = work_unit['schema_name']
        timestamp_column = work_unit.get('timestamp_column')
        selected_columns = work_unit.get('selected_columns', [])

        logger.info(f"Extracting full table {schema_name}.{table_name}")

        extractor = self._get_database_extractor()

        # Use RAW cursor-based extraction (NO PANDAS - yields dicts directly)
        row_gen = extractor.extract_full_raw(
            table_name=table_name,
            schema_name=schema_name,
            selected_columns=selected_columns,
            batch_size=10000
        )

        row_count = 0
        for row_dict in row_gen:
            # Serialize using pure Python (no pandas)
            serialized_row = {key: _serialize_value(value) for key, value in row_dict.items()}
            yield serialized_row
            row_count += 1

        logger.info(f"Extracted {row_count} rows from work unit")

    def _process_db_id_range(self, work_unit: Dict[str, Any]):
        """
        Process database work unit with ID range filter.

        Extracts rows where id BETWEEN min_id AND max_id.
        """
        # Similar to date range, but filter by ID
        # TODO: Implement when ID range partitioning is fully supported
        logger.warning("ID range partitioning not yet fully implemented, using hash partition")
        yield from self._process_db_hash_partition(work_unit)

    def _process_db_hash_partition(self, work_unit: Dict[str, Any]):
        """
        Process database work unit with hash partitioning.

        Extracts rows where MOD(HASH(id), total_partitions) = partition_id.
        This distributes rows evenly across workers.
        """
        table_name = work_unit['table_name']
        schema_name = work_unit['schema_name']
        partition_id = work_unit['partition_id']
        total_partitions = work_unit['total_partitions']
        selected_columns = work_unit.get('selected_columns', [])

        logger.info(f"Extracting partition {partition_id}/{total_partitions} from {schema_name}.{table_name}")

        extractor = self._get_database_extractor()

        # Use RAW cursor-based extraction and filter in-memory
        # TODO: Push filter to database query for better performance
        row_gen = extractor.extract_full_raw(
            table_name=table_name,
            schema_name=schema_name,
            selected_columns=selected_columns,
            batch_size=10000
        )

        row_count = 0
        idx = 0
        for row_dict in row_gen:
            # Simple hash partition: row_number % total_partitions == partition_id
            # This is inefficient (loads all rows), but works as fallback
            if hash(str(idx)) % total_partitions == partition_id:
                # Serialize using pure Python (no pandas)
                serialized_row = {key: _serialize_value(value) for key, value in row_dict.items()}
                yield serialized_row
                row_count += 1
            idx += 1

        logger.info(f"Extracted {row_count} rows from partition {partition_id}")

    def _process_file(self, work_unit: Dict[str, Any]):
        """
        Process file work unit.

        Reads file from cloud storage and yields rows.
        Uses file extractor (which uses pandas for now).
        """
        file_path = work_unit['file_path']
        file_format = work_unit.get('file_format')
        format_options = work_unit.get('format_options', {})

        logger.info(f"Extracting file: {file_path} (format: {file_format})")

        # Use existing file extractor
        from extractors.file_extractor import FileExtractor

        file_config = {
            'file_pattern': file_path,
            'file_format': file_format,
            'file_format_options': format_options,
        }

        extractor = FileExtractor(self.connection_params, file_config)

        # Extract file (may still use pandas for file parsing - CSV/Parquet)
        df = extractor.extract_file(file_path)

        row_count = 0
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            # Serialize using pure Python (no pandas/numpy in serialization)
            serialized_row = {key: _serialize_value(value) for key, value in row_dict.items()}
            yield serialized_row
            row_count += 1

        logger.info(f"Extracted {row_count} rows from file")

    def _get_database_extractor(self):
        """Get appropriate database extractor based on source type"""
        if self.source_type == 'postgresql':
            from extractors.postgresql import PostgreSQLExtractor
            return PostgreSQLExtractor(self.connection_params)
        elif self.source_type == 'mysql':
            from extractors.mysql import MySQLExtractor
            return MySQLExtractor(self.connection_params)
        elif self.source_type == 'bigquery':
            from extractors.bigquery import BigQueryExtractor
            return BigQueryExtractor(self.connection_params)
        else:
            raise ValueError(f"Unsupported database type: {self.source_type}")

    def teardown(self):
        """Cleanup resources"""
        logger.info("UnifiedExtractor.teardown()")
        # Close any open connections
        if hasattr(self, 'db_connection') and self.db_connection:
            self.db_connection.close()


# DEPRECATED: Old DoFns kept for backward compatibility during migration
# Will be removed once UnifiedExtractor is fully tested


class DatabaseToDataFrame(beam.DoFn):
    """
    DoFn to extract rows from database and convert to dict format.

    This runs in parallel across Dataflow workers.
    """

    def __init__(self, connection_params, table_name, schema_name, selected_columns,
                 load_type, timestamp_column=None, since_datetime=None):
        self.connection_params = connection_params
        self.table_name = table_name
        self.schema_name = schema_name
        self.selected_columns = selected_columns
        self.load_type = load_type
        self.timestamp_column = timestamp_column
        self.since_datetime = since_datetime

    def setup(self):
        """Initialize database connection (runs once per worker)"""
        source_type = self.connection_params.get('source_type')

        if source_type == 'postgresql':
            from extractors.postgresql import PostgreSQLExtractor
            self.extractor = PostgreSQLExtractor(self.connection_params)
        elif source_type == 'mysql':
            from extractors.mysql import MySQLExtractor
            self.extractor = MySQLExtractor(self.connection_params)
        elif source_type == 'bigquery':
            from extractors.bigquery import BigQueryExtractor
            self.extractor = BigQueryExtractor(self.connection_params)
        else:
            raise ValueError(f"Unsupported source type for Dataflow: {source_type}")

    def process(self, element):
        """
        Process batch of rows.
        Element is a tuple: (batch_number, batch_size)
        """
        batch_num, batch_size = element
        offset = batch_num * batch_size

        # Use extractor to fetch batch
        # Note: This is simplified - full implementation would need pagination
        if self.load_type == 'transactional' and self.timestamp_column:
            df_gen = self.extractor.extract_incremental(
                table_name=self.table_name,
                schema_name=self.schema_name,
                timestamp_column=self.timestamp_column,
                since_datetime=self.since_datetime,
                selected_columns=self.selected_columns,
                batch_size=batch_size
            )
        else:
            df_gen = self.extractor.extract_full(
                table_name=self.table_name,
                schema_name=self.schema_name,
                selected_columns=self.selected_columns,
                batch_size=batch_size
            )

        # Convert DataFrame rows to dicts and yield
        # IMPORTANT: Serialize datetime types to JSON-compatible strings
        for df in df_gen:
            for _, row in df.iterrows():
                try:
                    row_dict = row.to_dict()
                    serialized_row = serialize_row_for_bigquery(row_dict)
                    yield serialized_row
                except Exception as e:
                    logger.error(f"Failed to serialize row: {row_dict}")
                    logger.error(f"Serialization error: {e}")
                    raise

    def teardown(self):
        """Close database connection"""
        if hasattr(self, 'extractor'):
            self.extractor.close()


class FileToRows(beam.DoFn):
    """
    DoFn to read files from cloud storage and yield rows.
    """

    def __init__(self, connection_params, file_config):
        self.connection_params = connection_params
        self.file_config = file_config

    def setup(self):
        """Initialize cloud storage client"""
        from extractors.file_extractor import FileExtractor
        self.extractor = FileExtractor(self.connection_params, self.file_config)

    def process(self, file_metadata):
        """
        Process a single file and yield its rows.
        file_metadata: dict with file_path, file_size_bytes, file_last_modified
        """
        file_path = file_metadata['file_path']
        logger.info(f"Processing file: {file_path}")

        # Extract file
        df = self.extractor.extract_file(file_path)

        # Convert DataFrame rows to dicts
        # IMPORTANT: Serialize datetime types to JSON-compatible strings
        for _, row in df.iterrows():
            try:
                row_dict = row.to_dict()
                serialized_row = serialize_row_for_bigquery(row_dict)
                yield serialized_row
            except Exception as e:
                logger.error(f"Failed to serialize row from file {file_path}: {row_dict}")
                logger.error(f"Serialization error: {e}")
                raise


def create_pipeline_options(job_config: Dict[str, Any], gcp_config: Dict[str, Any]) -> PipelineOptions:
    """
    Create Beam pipeline options optimized for cost and performance.

    Args:
        job_config: ETL job configuration
        gcp_config: GCP project configuration (project_id, region, bucket, etc.)

    Returns:
        PipelineOptions configured for Dataflow
    """
    import os

    options = PipelineOptions()

    # Google Cloud options
    google_cloud_options = options.view_as(GoogleCloudOptions)
    google_cloud_options.project = gcp_config['project_id']
    google_cloud_options.region = gcp_config.get('region', 'europe-central2')
    google_cloud_options.staging_location = f"gs://{gcp_config['bucket']}/dataflow-staging"
    google_cloud_options.temp_location = f"gs://{gcp_config['bucket']}/dataflow-temp"
    google_cloud_options.job_name = f"etl-{job_config['data_source_id']}-{job_config['etl_run_id']}"

    # Standard options
    standard_options = options.view_as(StandardOptions)
    standard_options.runner = 'DataflowRunner'

    # Worker options (optimized for cost)
    worker_options = options.view_as(WorkerOptions)
    worker_options.machine_type = 'n1-standard-2'  # Cheap workers for development
    worker_options.max_num_workers = 10  # Scale up to 10 workers
    worker_options.autoscaling_algorithm = 'THROUGHPUT_BASED'
    worker_options.use_public_ips = True

    # Cost optimization: Use preemptible workers (80% cheaper!)
    # Note: Only use for non-critical jobs during development
    # For production, consider removing this or using a mix (some preemptible, some regular)
    worker_options.use_public_ips = True
    options.view_as(beam.options.pipeline_options.WorkerOptions).num_workers = 2  # Start with 2 workers

    # CRITICAL: Package custom code for Dataflow workers
    # This uploads all custom modules (dataflow_pipelines, extractors, loaders, utils) to workers
    setup_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'setup.py')
    if os.path.exists(setup_file_path):
        options.view_as(beam.options.pipeline_options.SetupOptions).setup_file = setup_file_path
        logger.info(f"Using setup.py for custom code packaging: {setup_file_path}")
    else:
        logger.warning(f"setup.py not found at {setup_file_path} - custom code may not be available on workers!")

    logger.info(f"Created Dataflow pipeline options: {google_cloud_options.job_name}")

    return options


def _map_bq_type_to_beam_type(bq_type: str) -> str:
    """
    Map BigQuery field type to Beam-compatible type.

    Args:
        bq_type: BigQuery field type (e.g., 'DATE', 'STRING', 'INT64')

    Returns:
        Beam-compatible type string
    """
    # BigQuery types that need mapping to Beam types
    type_mapping = {
        # Temporal types -> STRING (Beam doesn't support DATE/TIME/DATETIME directly)
        'DATE': 'STRING',
        'TIME': 'STRING',
        'DATETIME': 'STRING',

        # Numeric types
        'INT64': 'INTEGER',
        'INTEGER': 'INTEGER',
        'FLOAT64': 'FLOAT',
        'FLOAT': 'FLOAT',

        # Other types (pass through)
        'STRING': 'STRING',
        'BYTES': 'BYTES',
        'BOOL': 'BOOLEAN',
        'BOOLEAN': 'BOOLEAN',
        'TIMESTAMP': 'TIMESTAMP',
        'NUMERIC': 'NUMERIC',
        'BIGNUMERIC': 'NUMERIC',
        'GEOGRAPHY': 'GEOGRAPHY',
        'RECORD': 'RECORD',
    }

    mapped_type = type_mapping.get(bq_type, bq_type)
    if mapped_type != bq_type:
        logger.debug(f"Mapped BigQuery type '{bq_type}' to Beam type '{mapped_type}'")

    return mapped_type


def get_bq_table_schema(project_id: str, dataset_id: str, table_name: str) -> TableSchema:
    """
    Fetch BigQuery table schema and convert to Beam's TableSchema format.

    Args:
        project_id: GCP project ID
        dataset_id: BigQuery dataset ID
        table_name: BigQuery table name

    Returns:
        TableSchema object for use with WriteToBigQuery
    """
    from google.cloud import bigquery

    # Initialize BigQuery client
    client = bigquery.Client(project=project_id)

    # Get table schema
    table_ref = f"{project_id}.{dataset_id}.{table_name}"
    table = client.get_table(table_ref)

    # Convert BigQuery schema to Beam TableSchema
    beam_schema = TableSchema()
    beam_fields = []

    for field in table.schema:
        # Map BigQuery type to Beam type
        beam_type = _map_bq_type_to_beam_type(field.field_type)

        beam_field = TableFieldSchema(
            name=field.name,
            type=beam_type,
            mode=field.mode or 'NULLABLE'
        )

        # Handle nested/repeated fields
        if field.fields:
            beam_field.fields = []
            for subfield in field.fields:
                # Map subfield type as well
                beam_subtype = _map_bq_type_to_beam_type(subfield.field_type)

                beam_subfield = TableFieldSchema(
                    name=subfield.name,
                    type=beam_subtype,
                    mode=subfield.mode or 'NULLABLE'
                )
                beam_field.fields.append(beam_subfield)

        beam_fields.append(beam_field)

    beam_schema.fields = beam_fields

    logger.info(f"Fetched schema for {table_ref}: {len(beam_fields)} fields")
    return beam_schema


def run_database_pipeline(job_config: Dict[str, Any], gcp_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create and run Beam pipeline for database sources.

    Args:
        job_config: ETL job configuration from Django API
        gcp_config: GCP configuration (project, bucket, etc.)

    Returns:
        Dict with execution results
    """
    options = create_pipeline_options(job_config, gcp_config)

    # Build BigQuery table reference
    table_ref = f"{gcp_config['project_id']}:{gcp_config['dataset_id']}.{job_config['dest_table_name']}"

    # Determine write disposition based on load type
    write_disposition = (
        BigQueryDisposition.WRITE_TRUNCATE if job_config['load_type'] == 'catalog'
        else BigQueryDisposition.WRITE_APPEND
    )

    logger.info(f"Starting Dataflow pipeline for database source")
    logger.info(f"Destination: {table_ref}, Write mode: {write_disposition}")
    logger.info(f"Using FILE_LOADS method (schema inferred from existing table)")

    with beam.Pipeline(options=options) as pipeline:
        # For simplicity, we'll use Beam's built-in JDBC connector
        # In production, you might want to use custom DoFn for better control

        rows = (
            pipeline
            | 'CreateBatches' >> beam.Create([(0, 10000)])  # Simplified: single batch
            | 'ExtractFromDB' >> beam.ParDo(
                DatabaseToDataFrame(
                    connection_params=job_config['connection_params'],
                    table_name=job_config['source_table_name'],
                    schema_name=job_config['schema_name'],
                    selected_columns=job_config['selected_columns'],
                    load_type=job_config['load_type'],
                    timestamp_column=job_config.get('timestamp_column'),
                    since_datetime=job_config.get('last_sync_value') or job_config.get('historical_start_date')
                )
            )
            | 'WriteToBigQuery' >> WriteToBigQuery(
                table=table_ref,
                write_disposition=write_disposition,
                create_disposition=BigQueryDisposition.CREATE_NEVER,  # Table must exist
                method='FILE_LOADS'  # Batch-optimized method, no Java dependency
            )
        )

    logger.info("Dataflow pipeline submitted successfully")

    return {
        'status': 'submitted',
        'job_name': options.view_as(GoogleCloudOptions).job_name,
        'message': 'Dataflow job submitted - check GCP console for progress'
    }


def run_file_pipeline(job_config: Dict[str, Any], gcp_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create and run Beam pipeline for cloud storage file sources.

    Args:
        job_config: ETL job configuration from Django API
        gcp_config: GCP configuration (project, bucket, etc.)

    Returns:
        Dict with execution results
    """
    options = create_pipeline_options(job_config, gcp_config)

    # Build BigQuery table reference
    table_ref = f"{gcp_config['project_id']}:{gcp_config['dataset_id']}.{job_config['dest_table_name']}"

    # Determine write disposition
    write_disposition = (
        BigQueryDisposition.WRITE_TRUNCATE if job_config['load_type'] == 'catalog'
        else BigQueryDisposition.WRITE_APPEND
    )

    logger.info(f"Starting Dataflow pipeline for file source")
    logger.info(f"File pattern: {job_config['file_pattern']}, Format: {job_config['file_format']}")
    logger.info(f"Destination: {table_ref}, Write mode: {write_disposition}")
    logger.info(f"Using FILE_LOADS method with schema-aware conversion")

    # Fetch destination schema for type conversion
    table_schema = get_bq_table_schema(
        project_id=gcp_config['project_id'],
        dataset_id=gcp_config['dataset_id'],
        table_name=job_config['dest_table_name']
    )
    schema_map = {field.name: field.type for field in table_schema.fields}
    logger.info(f"Fetched schema: {len(schema_map)} fields for type conversion")

    # Get list of files to process
    from extractors.file_extractor import FileExtractor
    temp_extractor = FileExtractor(job_config['connection_params'], job_config)
    files_list = temp_extractor.list_files()
    temp_extractor.close()

    logger.info(f"Found {len(files_list)} files to process")

    with beam.Pipeline(options=options) as pipeline:
        rows = (
            pipeline
            | 'CreateFileList' >> beam.Create(files_list)
            | 'ReadFiles' >> beam.ParDo(
                FileToRows(
                    connection_params=job_config['connection_params'],
                    file_config=job_config
                )
            )
            # Normalize column names to lowercase (BigQuery schema uses lowercase)
            | 'NormalizeColumnNames' >> beam.Map(
                lambda row: {key.lower(): value for key, value in row.items()}
            )
            # Serialize datetime/Decimal/NaN with pure Python
            | 'SerializeValues' >> beam.Map(
                lambda row: {key: _serialize_value(value) for key, value in row.items()}
            )
            # Convert types to match destination schema (e.g., array → JSON string, date → timestamp)
            | 'ConvertToSchema' >> beam.ParDo(SchemaAwareConverter(schema_map))
            | 'WriteToBigQuery' >> WriteToBigQuery(
                table=table_ref,
                write_disposition=write_disposition,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                method='FILE_LOADS'
            )
        )

    logger.info("Dataflow pipeline submitted successfully")

    return {
        'status': 'submitted',
        'job_name': options.view_as(GoogleCloudOptions).job_name,
        'message': 'Dataflow job submitted - check GCP console for progress',
        'files_count': len(files_list)
    }


# ============================================================================
# NEW SCALABLE DATAFLOW PIPELINES WITH WORK PARTITIONING
# ============================================================================


def run_scalable_pipeline(
    job_config: Dict[str, Any],
    gcp_config: Dict[str, Any],
    work_units: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Run scalable Dataflow pipeline with work partitioning.

    This is the NEW recommended pipeline that:
    1. Uses work_units for true parallel processing
    2. Uses UnifiedExtractor (source-agnostic)
    3. Scales linearly with worker count
    4. Works for ALL source types (databases, files)

    Args:
        job_config: ETL job configuration
        gcp_config: GCP configuration (project, bucket, etc.)
        work_units: List of work unit dicts (from partitioning module)

    Returns:
        Dict with execution results

    Example work_units:
        [
            {'type': 'db_date_range', 'table_name': 'events', 'start_date': '2024-01-01', ...},
            {'type': 'db_date_range', 'table_name': 'events', 'start_date': '2024-01-02', ...},
            ...
        ]
    """

    logger.info("=" * 80)
    logger.info("STARTING SCALABLE DATAFLOW PIPELINE")
    logger.info("=" * 80)
    logger.info(f"Work units: {len(work_units)}")
    logger.info(f"Source type: {job_config.get('connection_params', {}).get('source_type')}")

    # Create pipeline options
    options = create_pipeline_options(job_config, gcp_config)

    # Build BigQuery table reference
    table_ref = f"{gcp_config['project_id']}:{gcp_config['dataset_id']}.{job_config['dest_table_name']}"

    # Determine write disposition
    write_disposition = (
        BigQueryDisposition.WRITE_TRUNCATE if job_config['load_type'] == 'catalog'
        else BigQueryDisposition.WRITE_APPEND
    )

    logger.info(f"Destination: {table_ref}")
    logger.info(f"Write mode: {write_disposition}")
    logger.info(f"Workers: 2 initial, up to 10 max (autoscaling)")
    logger.info(f"Method: FILE_LOADS with schema-aware conversion")
    logger.info("=" * 80)

    # Fetch destination schema for type conversion
    table_schema = get_bq_table_schema(
        project_id=gcp_config['project_id'],
        dataset_id=gcp_config['dataset_id'],
        table_name=job_config['dest_table_name']
    )
    schema_map = {field.name: field.type for field in table_schema.fields}
    logger.info(f"Fetched schema: {len(schema_map)} fields for type conversion")

    with beam.Pipeline(options=options) as pipeline:
        (
            pipeline
            # Create PCollection from work units (MULTIPLE elements!)
            | 'CreateWorkUnits' >> beam.Create(work_units)

            # Each worker processes its assigned work units
            # UnifiedExtractor uses raw cursor methods (no pandas) and pure Python serialization
            | 'ExtractData' >> beam.ParDo(
                UnifiedExtractor(
                    connection_params=job_config['connection_params']
                )
            )

            # Normalize column names to lowercase (BigQuery schema uses lowercase)
            | 'NormalizeColumnNames' >> beam.Map(
                lambda row: {key.lower(): value for key, value in row.items()}
            )

            # Serialize datetime/Decimal/NaN with pure Python
            | 'SerializeValues' >> beam.Map(
                lambda row: {key: _serialize_value(value) for key, value in row.items()}
            )

            # Convert types to match destination schema (e.g., array → JSON string, date → timestamp)
            | 'ConvertToSchema' >> beam.ParDo(SchemaAwareConverter(schema_map))

            # Write all rows to BigQuery
            | 'WriteToBigQuery' >> WriteToBigQuery(
                table=table_ref,
                write_disposition=write_disposition,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                method='FILE_LOADS'
            )
        )

    logger.info("Dataflow pipeline submitted successfully")
    logger.info("=" * 80)

    return {
        'status': 'submitted',
        'job_name': options.view_as(GoogleCloudOptions).job_name,
        'message': 'Dataflow job submitted - check GCP console for progress',
        'work_units_count': len(work_units)
    }


def run_bigquery_native_pipeline(
    job_config: Dict[str, Any],
    gcp_config: Dict[str, Any],
    work_units: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Run Dataflow pipeline for BigQuery sources using native Beam I/O.

    This is optimized for BigQuery-to-BigQuery ETL:
    - Uses beam.io.ReadFromBigQuery (automatic partitioning)
    - No custom extractors needed
    - Handles complex types (RECORD, ARRAY) natively
    - Better performance than custom extraction

    Args:
        job_config: ETL job configuration
        gcp_config: GCP configuration
        work_units: Should contain single work unit with BigQuery query

    Returns:
        Dict with execution results
    """

    logger.info("=" * 80)
    logger.info("STARTING BIGQUERY NATIVE DATAFLOW PIPELINE")
    logger.info("=" * 80)

    # Extract query from work unit
    if not work_units or work_units[0].get('type') != 'bigquery_native':
        raise ValueError("BigQuery native pipeline requires work_unit with type='bigquery_native'")

    work_unit = work_units[0]
    query = work_unit['query']
    use_standard_sql = work_unit.get('use_standard_sql', True)

    logger.info(f"Query: {query}")

    # Create pipeline options
    options = create_pipeline_options(job_config, gcp_config)

    # Build BigQuery table reference
    table_ref = f"{gcp_config['project_id']}:{gcp_config['dataset_id']}.{job_config['dest_table_name']}"

    # Determine write disposition
    write_disposition = (
        BigQueryDisposition.WRITE_TRUNCATE if job_config['load_type'] == 'catalog'
        else BigQueryDisposition.WRITE_APPEND
    )

    logger.info(f"Destination: {table_ref}")
    logger.info(f"Write mode: {write_disposition}")
    logger.info("=" * 80)

    # Fetch destination schema for type conversion (array → string, etc.)
    table_schema = get_bq_table_schema(
        project_id=gcp_config['project_id'],
        dataset_id=gcp_config['dataset_id'],
        table_name=job_config['dest_table_name']
    )
    schema_map = {field.name: field.type for field in table_schema.fields}
    logger.info(f"Fetched schema: {len(schema_map)} fields for type conversion")

    with beam.Pipeline(options=options) as pipeline:
        (
            pipeline
            # Read from BigQuery using native I/O
            # Beam automatically partitions using BigQuery Storage Read API
            | 'ReadFromBigQuery' >> beam.io.ReadFromBigQuery(
                query=query,
                use_standard_sql=use_standard_sql,
                # BigQuery Storage API automatically parallelizes reads
            )

            # Serialize datetime/Decimal/NaN with pure Python
            | 'SerializeValues' >> beam.Map(
                lambda row: {key: _serialize_value(value) for key, value in row.items()}
            )

            # Convert types to match destination schema (e.g., array → JSON string)
            | 'ConvertToSchema' >> beam.ParDo(SchemaAwareConverter(schema_map))

            # Write to destination table
            | 'WriteToBigQuery' >> WriteToBigQuery(
                table=table_ref,
                write_disposition=write_disposition,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                method='FILE_LOADS'  # Simple, reliable, no Java dependency
            )
        )

    logger.info("BigQuery native pipeline submitted successfully")
    logger.info("=" * 80)

    return {
        'status': 'submitted',
        'job_name': options.view_as(GoogleCloudOptions).job_name,
        'message': 'Dataflow job submitted - check GCP console for progress',
        'method': 'bigquery_native'
    }


def run_file_pipeline(
    job_config: Dict[str, Any],
    gcp_config: Dict[str, Any],
    file_paths: List[str]
) -> Dict[str, Any]:
    """
    Run Dataflow pipeline for file sources using native Beam I/O.

    This is the NEW recommended pipeline for large files that:
    1. Uses beam.io.ReadFromText for streaming (no pandas, no memory issues)
    2. Automatically splits large files into ~64MB bundles
    3. Processes files in parallel across workers
    4. Handles files of ANY size efficiently

    Args:
        job_config: ETL job configuration including:
            - file_format: 'csv', 'json', or 'parquet'
            - file_format_options: {delimiter, encoding, has_header}
            - selected_columns: List of column names from wizard schema
            - dest_table_name: Destination BigQuery table
            - load_type: 'catalog' or 'transactional'
        gcp_config: GCP configuration (project, bucket, etc.)
        file_paths: List of GCS file paths to process

    Returns:
        Dict with execution results
    """

    logger.info("=" * 80)
    logger.info("STARTING FILE PIPELINE WITH NATIVE BEAM I/O")
    logger.info("=" * 80)
    logger.info(f"Files to process: {len(file_paths)}")
    for fp in file_paths:
        logger.info(f"  - {fp}")

    file_format = job_config.get('file_format', 'csv')
    format_options = job_config.get('file_format_options', {})
    selected_columns = job_config.get('selected_columns', [])

    delimiter = format_options.get('delimiter', ',')
    encoding = format_options.get('encoding', 'utf-8')
    has_header = format_options.get('has_header', True)

    logger.info(f"File format: {file_format}")
    logger.info(f"Delimiter: '{delimiter}', Encoding: {encoding}, Has header: {has_header}")
    logger.info(f"Schema columns from config: {len(selected_columns)} columns")

    # Create pipeline options
    options = create_pipeline_options(job_config, gcp_config)

    # Build BigQuery table reference
    table_ref = f"{gcp_config['project_id']}:{gcp_config['dataset_id']}.{job_config['dest_table_name']}"

    # Determine write disposition
    write_disposition = (
        BigQueryDisposition.WRITE_TRUNCATE if job_config['load_type'] == 'catalog'
        else BigQueryDisposition.WRITE_APPEND
    )

    logger.info(f"Destination: {table_ref}")
    logger.info(f"Write mode: {write_disposition}")
    logger.info("=" * 80)

    # Fetch destination schema for type conversion
    table_schema = get_bq_table_schema(
        project_id=gcp_config['project_id'],
        dataset_id=gcp_config['dataset_id'],
        table_name=job_config['dest_table_name']
    )
    schema_map = {field.name: field.type for field in table_schema.fields}
    logger.info(f"Fetched BigQuery schema: {len(schema_map)} fields")

    # If selected_columns is empty, derive from BigQuery destination schema
    # This handles file sources where columns are defined in BigQuery but not in selected_columns
    if not selected_columns:
        # Get column names from BigQuery schema (excluding internal ETL columns)
        internal_columns = {'_etl_loaded_at', '_etl_file_name', '_etl_file_path', '_etl_source'}
        selected_columns = [field.name for field in table_schema.fields if field.name not in internal_columns]
        logger.info(f"Derived {len(selected_columns)} columns from BigQuery schema: {selected_columns}")

    # Validate we have column names for CSV
    if file_format == 'csv' and not selected_columns:
        raise ValueError("CSV processing requires columns - none found in config or BigQuery schema")

    # Build file pattern for Beam
    # For multiple files, we read them all and flatten
    if len(file_paths) == 1:
        file_pattern = file_paths[0]
    else:
        # Multiple files - we'll use beam.Flatten to combine
        file_pattern = None  # Will handle multiple files differently

    with beam.Pipeline(options=options) as pipeline:
        if file_format == 'csv':
            # CSV: Use ReadFromText with skip_header_lines + ParseCSVLine
            if len(file_paths) == 1:
                # Single file - simple case
                rows = (
                    pipeline
                    | 'ReadCSV' >> beam.io.ReadFromText(
                        file_pattern=file_paths[0],
                        skip_header_lines=1 if has_header else 0
                    )
                    | 'ParseCSVLines' >> beam.ParDo(
                        ParseCSVLine(
                            column_names=selected_columns,
                            delimiter=delimiter,
                            encoding=encoding
                        )
                    )
                )
            else:
                # Multiple files - read each and flatten
                file_pcollections = []
                for i, file_path in enumerate(file_paths):
                    file_rows = (
                        pipeline
                        | f'ReadCSV_{i}' >> beam.io.ReadFromText(
                            file_pattern=file_path,
                            skip_header_lines=1 if has_header else 0
                        )
                    )
                    file_pcollections.append(file_rows)

                # Flatten all files into single PCollection, then parse
                rows = (
                    file_pcollections
                    | 'FlattenFiles' >> beam.Flatten()
                    | 'ParseCSVLines' >> beam.ParDo(
                        ParseCSVLine(
                            column_names=selected_columns,
                            delimiter=delimiter,
                            encoding=encoding
                        )
                    )
                )

        elif file_format == 'json':
            # JSON Lines: Use ReadFromText + ParseJSONLine
            if len(file_paths) == 1:
                rows = (
                    pipeline
                    | 'ReadJSON' >> beam.io.ReadFromText(file_pattern=file_paths[0])
                    | 'ParseJSONLines' >> beam.ParDo(
                        ParseJSONLine(column_names=selected_columns if selected_columns else None)
                    )
                )
            else:
                file_pcollections = []
                for i, file_path in enumerate(file_paths):
                    file_rows = (
                        pipeline
                        | f'ReadJSON_{i}' >> beam.io.ReadFromText(file_pattern=file_path)
                    )
                    file_pcollections.append(file_rows)

                rows = (
                    file_pcollections
                    | 'FlattenFiles' >> beam.Flatten()
                    | 'ParseJSONLines' >> beam.ParDo(
                        ParseJSONLine(column_names=selected_columns if selected_columns else None)
                    )
                )

        elif file_format == 'parquet':
            # Parquet: Use ReadFromParquet (native Beam support)
            # Note: ReadFromParquet returns dicts directly, no parsing needed
            if len(file_paths) == 1:
                rows = (
                    pipeline
                    | 'ReadParquet' >> beam.io.ReadFromParquet(file_pattern=file_paths[0])
                )
            else:
                file_pcollections = []
                for i, file_path in enumerate(file_paths):
                    file_rows = (
                        pipeline
                        | f'ReadParquet_{i}' >> beam.io.ReadFromParquet(file_pattern=file_path)
                    )
                    file_pcollections.append(file_rows)

                rows = (
                    file_pcollections
                    | 'FlattenFiles' >> beam.Flatten()
                )

            # Filter to selected columns if specified
            if selected_columns:
                rows = rows | 'FilterColumns' >> beam.Map(
                    lambda row: {k: row.get(k) for k in selected_columns}
                )
        else:
            raise ValueError(f"Unsupported file format for native Beam I/O: {file_format}")

        # Continue with common pipeline stages (same as other pipelines)
        (
            rows
            # Normalize column names to lowercase (BigQuery schema uses lowercase)
            | 'NormalizeColumnNames' >> beam.Map(
                lambda row: {key.lower(): value for key, value in row.items()}
            )

            # Serialize values (handles any special types)
            | 'SerializeValues' >> beam.Map(
                lambda row: {key: _serialize_value(value) for key, value in row.items()}
            )

            # Convert types to match destination schema
            | 'ConvertToSchema' >> beam.ParDo(SchemaAwareConverter(schema_map))

            # Write to BigQuery
            | 'WriteToBigQuery' >> WriteToBigQuery(
                table=table_ref,
                write_disposition=write_disposition,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                method='FILE_LOADS'
            )
        )

    logger.info("File pipeline submitted successfully")
    logger.info("=" * 80)

    return {
        'status': 'submitted',
        'job_name': options.view_as(GoogleCloudOptions).job_name,
        'message': 'Dataflow job submitted - check GCP console for progress',
        'method': 'native_file_io',
        'files_processed': len(file_paths)
    }
