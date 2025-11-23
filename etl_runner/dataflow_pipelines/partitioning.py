"""
Work Partitioning for Scalable Dataflow Pipelines

This module calculates how to split large datasets into independent work units
that can be processed in parallel across Dataflow workers.

Key Concepts:
- Work Unit: A dict describing one partition of work (e.g., date range, file path)
- Partitioning Strategy: Algorithm to split data (by date, ID range, hash, files)
- Partition Calculator: Class that implements a specific strategy

Strategies:
1. DateRangePartitionCalculator - For tables with timestamp columns
2. IdRangePartitionCalculator - For tables with sequential integer PKs
3. HashPartitionCalculator - For tables without good partitioning keys
4. FilePartitionCalculator - For cloud storage files (each file = partition)
5. BigQueryNativeCalculator - For BigQuery sources (uses native Beam I/O)
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WorkUnit:
    """
    Describes a single unit of work to be processed by a Dataflow worker.

    Each work unit contains enough information for a worker to independently
    extract and process its partition of data without coordinating with other workers.
    """
    work_type: str  # 'db_date_range', 'db_id_range', 'db_hash_partition', 'file', 'bigquery_native'
    params: Dict[str, Any]  # Type-specific parameters

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for Beam serialization"""
        return {
            'type': self.work_type,
            **self.params
        }


class PartitionCalculator(ABC):
    """
    Abstract base class for all partition calculation strategies.

    Subclasses implement specific partitioning logic for different scenarios
    (date ranges, ID ranges, file lists, etc.)
    """

    @abstractmethod
    def calculate_partitions(
        self,
        job_config: Dict[str, Any],
        extractor: Any,
        estimated_rows: int
    ) -> List[WorkUnit]:
        """
        Calculate work units for parallel processing.

        Args:
            job_config: ETL job configuration (table name, columns, filters, etc.)
            extractor: Database/file extractor instance (for querying metadata)
            estimated_rows: Estimated total rows to process

        Returns:
            List of WorkUnit objects, each describing one partition
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return human-readable name of this strategy"""
        pass


class DateRangePartitionCalculator(PartitionCalculator):
    """
    Partition database table by date/timestamp ranges.

    Best for: Tables with indexed timestamp columns (created_at, updated_at, event_date)

    Algorithm:
    1. Query MIN(timestamp), MAX(timestamp) from table
    2. Determine interval (daily, hourly, etc.) based on data volume
    3. Create one work unit per interval

    Example work unit:
    {
        'type': 'db_date_range',
        'table_name': 'transactions',
        'schema_name': 'public',
        'timestamp_column': 'created_at',
        'start_date': '2024-01-01T00:00:00',
        'end_date': '2024-01-02T00:00:00',
        'selected_columns': ['id', 'amount', 'created_at']
    }
    """

    def __init__(self, target_rows_per_partition: int = 50000):
        """
        Args:
            target_rows_per_partition: Target number of rows per partition
                                      (actual may vary based on data distribution)
        """
        self.target_rows_per_partition = target_rows_per_partition

    def calculate_partitions(
        self,
        job_config: Dict[str, Any],
        extractor: Any,
        estimated_rows: int
    ) -> List[WorkUnit]:
        """Calculate date range partitions"""

        table_name = job_config['source_table_name']
        schema_name = job_config['schema_name']
        timestamp_column = job_config.get('timestamp_column')
        selected_columns = job_config.get('selected_columns', [])

        if not timestamp_column:
            raise ValueError("DateRangePartitionCalculator requires timestamp_column")

        logger.info(f"Calculating date range partitions for {schema_name}.{table_name}")

        # For incremental loads, use since_datetime as start
        since_datetime = job_config.get('last_sync_value') or job_config.get('historical_start_date')

        if since_datetime:
            # Incremental load: partition from since_datetime to now
            start_date = datetime.fromisoformat(since_datetime.replace('Z', '+00:00'))
            end_date = datetime.utcnow()
        else:
            # Full load: query table for date range
            # This would need extractor.get_min_max_timestamp() method
            # For now, fallback to single partition
            logger.warning("Full load date partitioning not yet implemented, using single partition")
            return [WorkUnit(
                work_type='db_date_range_full',
                params={
                    'table_name': table_name,
                    'schema_name': schema_name,
                    'timestamp_column': timestamp_column,
                    'selected_columns': selected_columns,
                }
            )]

        # Determine interval based on estimated rows
        total_days = (end_date - start_date).days + 1

        if total_days == 0:
            total_days = 1

        rows_per_day = estimated_rows / total_days if total_days > 0 else estimated_rows

        # Choose interval to get close to target partition size
        if rows_per_day <= self.target_rows_per_partition:
            # Daily partitions
            interval_hours = 24
            interval_name = "daily"
        elif rows_per_day <= self.target_rows_per_partition * 24:
            # Hourly partitions
            interval_hours = 1
            interval_name = "hourly"
        else:
            # 15-minute partitions for very high volume
            interval_hours = 0.25
            interval_name = "15-minute"

        logger.info(f"Using {interval_name} partitions (estimated {rows_per_day:.0f} rows/day)")

        # Generate partitions
        work_units = []
        current_start = start_date

        while current_start < end_date:
            current_end = current_start + timedelta(hours=interval_hours)
            if current_end > end_date:
                current_end = end_date

            work_units.append(WorkUnit(
                work_type='db_date_range',
                params={
                    'table_name': table_name,
                    'schema_name': schema_name,
                    'timestamp_column': timestamp_column,
                    'start_date': current_start.isoformat(),
                    'end_date': current_end.isoformat(),
                    'selected_columns': selected_columns,
                }
            ))

            current_start = current_end

        logger.info(f"Created {len(work_units)} date range partitions")
        return work_units

    def get_strategy_name(self) -> str:
        return "Date Range Partitioning"


class IdRangePartitionCalculator(PartitionCalculator):
    """
    Partition database table by primary key ID ranges.

    Best for: Tables with sequential integer primary keys, no timestamp column

    Algorithm:
    1. Query MIN(id), MAX(id) from table
    2. Calculate range_size = (max - min) / num_partitions
    3. Create one work unit per ID range

    Example work unit:
    {
        'type': 'db_id_range',
        'table_name': 'users',
        'schema_name': 'public',
        'id_column': 'id',
        'min_id': 1,
        'max_id': 100000,
        'selected_columns': ['id', 'email', 'created_at']
    }
    """

    def __init__(self, target_rows_per_partition: int = 50000):
        self.target_rows_per_partition = target_rows_per_partition

    def calculate_partitions(
        self,
        job_config: Dict[str, Any],
        extractor: Any,
        estimated_rows: int
    ) -> List[WorkUnit]:
        """Calculate ID range partitions"""

        table_name = job_config['source_table_name']
        schema_name = job_config['schema_name']
        id_column = job_config.get('primary_key_column', 'id')
        selected_columns = job_config.get('selected_columns', [])

        logger.info(f"Calculating ID range partitions for {schema_name}.{table_name}")

        # Would need extractor.get_min_max_id() method
        # For now, create partitions based on estimated rows
        num_partitions = max(1, estimated_rows // self.target_rows_per_partition)

        # Limit to reasonable number of partitions
        num_partitions = min(num_partitions, 100)

        logger.info(f"Creating {num_partitions} ID-based partitions")

        # For now, use hash partitioning as fallback
        # (requires implementing MIN/MAX query in extractors first)
        work_units = []
        for partition_id in range(num_partitions):
            work_units.append(WorkUnit(
                work_type='db_hash_partition',
                params={
                    'table_name': table_name,
                    'schema_name': schema_name,
                    'id_column': id_column,
                    'partition_id': partition_id,
                    'total_partitions': num_partitions,
                    'selected_columns': selected_columns,
                }
            ))

        return work_units

    def get_strategy_name(self) -> str:
        return "ID Range Partitioning"


class FilePartitionCalculator(PartitionCalculator):
    """
    Partition cloud storage files - each file becomes one work unit.

    Best for: Multiple files in cloud storage (GCS/S3/Azure)

    This is the simplest and most efficient partitioning strategy for files,
    since files are already naturally partitioned.

    Example work unit:
    {
        'type': 'file',
        'file_path': 'gs://bucket/data/file001.csv',
        'file_format': 'csv',
        'format_options': {'delimiter': ',', 'encoding': 'utf-8'}
    }
    """

    def calculate_partitions(
        self,
        job_config: Dict[str, Any],
        extractor: Any,
        estimated_rows: int
    ) -> List[WorkUnit]:
        """Calculate file partitions (one per file)"""

        logger.info("Calculating file partitions")

        # Get file list from extractor
        file_list = extractor.list_files()

        work_units = []
        for file_metadata in file_list:
            work_units.append(WorkUnit(
                work_type='file',
                params={
                    'file_path': file_metadata['file_path'],
                    'file_format': job_config.get('file_format'),
                    'format_options': job_config.get('file_format_options', {}),
                    'selected_columns': job_config.get('selected_columns', []),
                }
            ))

        logger.info(f"Created {len(work_units)} file partitions")
        return work_units

    def get_strategy_name(self) -> str:
        return "File-Based Partitioning"


class BigQueryNativeCalculator(PartitionCalculator):
    """
    For BigQuery sources, use Beam's native ReadFromBigQuery.

    This calculator returns a single work unit with a query.
    Beam's ReadFromBigQuery handles partitioning internally using
    BigQuery Storage Read API.

    Example work unit:
    {
        'type': 'bigquery_native',
        'query': 'SELECT * FROM `project.dataset.table` WHERE timestamp >= @since',
        'query_params': [{'name': 'since', 'type': 'TIMESTAMP', 'value': '2024-01-01'}]
    }
    """

    def calculate_partitions(
        self,
        job_config: Dict[str, Any],
        extractor: Any,
        estimated_rows: int
    ) -> List[WorkUnit]:
        """Create single work unit with BigQuery query"""

        logger.info("Using BigQuery native I/O (no manual partitioning needed)")

        # Build query
        source_project = job_config['connection_params'].get('bigquery_project')
        dataset = job_config['schema_name']
        table = job_config['source_table_name']
        selected_columns = job_config.get('selected_columns', [])

        # Build column list
        if selected_columns:
            column_list = ', '.join([f'`{col}`' for col in selected_columns])
        else:
            column_list = '*'

        # Build query with optional WHERE clause for incremental
        table_ref = f'`{source_project}.{dataset}.{table}`'

        timestamp_column = job_config.get('timestamp_column')
        since_datetime = job_config.get('last_sync_value') or job_config.get('historical_start_date')

        if timestamp_column and since_datetime:
            # Incremental load
            query = f"""
                SELECT {column_list}
                FROM {table_ref}
                WHERE `{timestamp_column}` >= TIMESTAMP('{since_datetime}')
                ORDER BY `{timestamp_column}`
            """
        else:
            # Full load
            query = f"SELECT {column_list} FROM {table_ref}"

        work_unit = WorkUnit(
            work_type='bigquery_native',
            params={
                'query': query.strip(),
                'use_standard_sql': True,
            }
        )

        logger.info(f"BigQuery query: {query.strip()}")

        return [work_unit]

    def get_strategy_name(self) -> str:
        return "BigQuery Native I/O"


def get_partition_calculator(
    job_config: Dict[str, Any],
    estimated_rows: int
) -> PartitionCalculator:
    """
    Factory function to select appropriate partitioning strategy.

    Decision logic:
    1. BigQuery source → BigQueryNativeCalculator
    2. File source → FilePartitionCalculator
    3. Database with timestamp column → DateRangePartitionCalculator
    4. Database with primary key → IdRangePartitionCalculator
    5. Fallback → Single partition (no parallelism)

    Args:
        job_config: ETL job configuration
        estimated_rows: Estimated row count

    Returns:
        PartitionCalculator instance
    """

    source_type = job_config.get('connection_params', {}).get('source_type')

    # BigQuery source - use native I/O
    if source_type == 'bigquery':
        logger.info("Selected BigQuery native I/O partitioning")
        return BigQueryNativeCalculator()

    # File source - partition by files
    if source_type in ('gcs', 's3', 'azure_blob'):
        logger.info("Selected file-based partitioning")
        return FilePartitionCalculator()

    # Database source - choose best strategy
    timestamp_column = job_config.get('timestamp_column')

    if timestamp_column:
        logger.info(f"Selected date range partitioning (using {timestamp_column})")
        return DateRangePartitionCalculator()

    # Fallback: ID-based or hash partitioning
    logger.info("Selected ID/hash-based partitioning")
    return IdRangePartitionCalculator()


def calculate_work_units(
    job_config: Dict[str, Any],
    extractor: Any,
    estimated_rows: int
) -> List[Dict[str, Any]]:
    """
    Main entry point for partition calculation.

    This function:
    1. Selects appropriate partitioning strategy
    2. Calculates work units
    3. Validates and returns them

    Args:
        job_config: ETL job configuration
        extractor: Database/file extractor instance
        estimated_rows: Estimated total rows

    Returns:
        List of work unit dicts (JSON-serializable for Beam)

    Example:
        >>> work_units = calculate_work_units(job_config, extractor, 5000000)
        >>> len(work_units)
        50
        >>> work_units[0]
        {'type': 'db_date_range', 'table_name': 'events', 'start_date': '2024-01-01', ...}
    """

    logger.info("="* 60)
    logger.info("CALCULATING WORK PARTITIONS FOR PARALLEL PROCESSING")
    logger.info("=" * 60)
    logger.info(f"Estimated rows: {estimated_rows:,}")

    # Select calculator
    calculator = get_partition_calculator(job_config, estimated_rows)
    logger.info(f"Strategy: {calculator.get_strategy_name()}")

    # Calculate partitions
    work_units = calculator.calculate_partitions(job_config, extractor, estimated_rows)

    # Validate
    if not work_units:
        raise ValueError("Partition calculator returned empty work units list")

    logger.info(f"✓ Created {len(work_units)} work units")
    logger.info(f"✓ Each worker will process ~{estimated_rows // len(work_units):,} rows")
    logger.info("=" * 60)

    # Sample first 3 for logging
    for i, wu in enumerate(work_units[:3]):
        logger.info(f"Sample partition {i+1}: {wu.to_dict()}")

    if len(work_units) > 3:
        logger.info(f"... and {len(work_units) - 3} more partitions")

    # Convert to dicts for Beam serialization
    return [wu.to_dict() for wu in work_units]
