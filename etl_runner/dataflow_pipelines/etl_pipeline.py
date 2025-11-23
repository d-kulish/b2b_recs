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
from typing import Dict, Any, List
import json

logger = logging.getLogger(__name__)


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
        for df in df_gen:
            for _, row in df.iterrows():
                yield row.to_dict()

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
        for _, row in df.iterrows():
            yield row.to_dict()


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
                create_disposition=BigQueryDisposition.CREATE_NEVER  # Table must exist
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
            | 'WriteToBigQuery' >> WriteToBigQuery(
                table=table_ref,
                write_disposition=write_disposition,
                create_disposition=BigQueryDisposition.CREATE_NEVER
            )
        )

    logger.info("Dataflow pipeline submitted successfully")

    return {
        'status': 'submitted',
        'job_name': options.view_as(GoogleCloudOptions).job_name,
        'message': 'Dataflow job submitted - check GCP console for progress',
        'files_count': len(files_list)
    }
