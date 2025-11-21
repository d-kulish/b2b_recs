"""
ETL Runner Main Orchestrator

Entry point for ETL execution. Extracts data from source databases
and loads to BigQuery.
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from typing import Optional
import pandas as pd

from config import Config
from extractors.postgresql import PostgreSQLExtractor
from extractors.mysql import MySQLExtractor
from extractors.file_extractor import FileExtractor
from loaders.bigquery_loader import BigQueryLoader
from utils.logging_config import setup_logging, LogContext
from utils.error_handling import (
    handle_etl_error,
    validate_job_config,
    ExtractionError,
    LoadError,
    ConfigurationError
)

logger = logging.getLogger(__name__)


class ETLRunner:
    """Main ETL orchestrator"""

    def __init__(self, config: Config, data_source_id: int, etl_run_id: Optional[int] = None):
        """
        Initialize ETL runner.

        Args:
            config: Configuration instance
            data_source_id: DataSource ID
            etl_run_id: ETL run ID (optional, for status tracking)
        """
        self.config = config
        self.data_source_id = data_source_id
        self.etl_run_id = etl_run_id

        # Fetch job configuration from Django API
        logger.info(f"Initializing ETL runner for DataSource {data_source_id}")
        self.job_config = config.get_job_config(data_source_id)

        # Validate configuration
        validate_job_config(self.job_config)

        # Initialize components
        self.extractor = self._create_extractor()
        self.loader = self._create_loader()

        # Metrics
        self.total_rows_extracted = 0
        self.total_rows_loaded = 0
        self.start_time = None
        self.end_time = None

    def _create_extractor(self):
        """
        Create appropriate extractor based on source type.

        Returns:
            Extractor instance
        """
        source_type = self.job_config['source_type']
        connection_params = self.job_config['connection_params']

        logger.info(f"Creating {source_type} extractor")

        # Database extractors
        if source_type == 'postgresql':
            return PostgreSQLExtractor(connection_params)
        elif source_type == 'mysql':
            return MySQLExtractor(connection_params)

        # File extractors (GCS, S3, Azure Blob)
        elif source_type in ['gcs', 's3', 'azure_blob']:
            file_config = {
                'file_path_prefix': self.job_config.get('file_path_prefix', ''),
                'file_pattern': self.job_config.get('file_pattern', '*'),
                'file_format': self.job_config.get('file_format', 'csv'),
                'file_format_options': self.job_config.get('file_format_options', {}),
                'selected_files': self.job_config.get('selected_files', []),
                'load_latest_only': self.job_config.get('load_latest_only', False)
            }
            return FileExtractor(connection_params, file_config)

        else:
            raise ConfigurationError(f"Unsupported source type: {source_type}")

    def _create_loader(self):
        """
        Create BigQuery loader.

        Returns:
            BigQueryLoader instance
        """
        logger.info(f"Creating BigQuery loader for {self.job_config['dest_table_name']}")

        return BigQueryLoader(
            project_id=self.config.gcp_project_id,
            dataset_id=self.config.bigquery_dataset,
            table_name=self.job_config['dest_table_name']
        )

    def _on_batch_loaded(self, batch_num: int, rows_loaded: int):
        """
        Callback function called after each batch is loaded.

        Args:
            batch_num: Batch number
            rows_loaded: Number of rows loaded in this batch
        """
        self.total_rows_loaded += rows_loaded

        logger.info(
            f"Batch {batch_num} loaded: {rows_loaded} rows "
            f"(Total loaded: {self.total_rows_loaded:,})"
        )

        # Update progress in Django every 5 batches
        if batch_num % 5 == 0:
            self.config.update_etl_run_progress(
                etl_run_id=self.etl_run_id,
                rows_extracted=self.total_rows_extracted,
                rows_loaded=self.total_rows_loaded
            )

    def _get_bigquery_table_columns(self) -> list:
        """
        Get list of column names from BigQuery table schema.

        Returns:
            List of column names in the BigQuery table
        """
        from google.cloud import bigquery

        try:
            client = bigquery.Client(project=self.config.gcp_project_id)
            table_ref = f"{self.config.gcp_project_id}.{self.config.bigquery_dataset}.{self.job_config['dest_table_name']}"
            table = client.get_table(table_ref)
            return [field.name for field in table.schema]
        except Exception as e:
            logger.warning(f"Could not fetch BigQuery table schema: {e}. Proceeding without column filtering.")
            return []

    def _get_bigquery_table_schema(self) -> dict:
        """
        Get BigQuery table schema with column types.

        Returns:
            Dict mapping column names to their BigQuery types
        """
        from google.cloud import bigquery

        try:
            client = bigquery.Client(project=self.config.gcp_project_id)
            table_ref = f"{self.config.gcp_project_id}.{self.config.bigquery_dataset}.{self.job_config['dest_table_name']}"
            table = client.get_table(table_ref)
            return {field.name: field.field_type for field in table.schema}
        except Exception as e:
            logger.warning(f"Could not fetch BigQuery table schema: {e}. Proceeding without type conversion.")
            return {}

    def _convert_dataframe_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert DataFrame column types to match BigQuery table schema.

        Args:
            df: DataFrame with columns that may have incorrect types

        Returns:
            DataFrame with converted column types
        """
        import numpy as np

        bq_schema = self._get_bigquery_table_schema()

        if not bq_schema:
            return df

        conversions_made = []

        for column in df.columns:
            if column not in bq_schema:
                continue

            bq_type = bq_schema[column]

            try:
                if bq_type == 'INTEGER':
                    # Convert to integer, handling NaN and invalid values
                    df[column] = pd.to_numeric(df[column], errors='coerce')
                    df[column] = df[column].fillna(0).astype('Int64')  # Use nullable integer type
                    conversions_made.append(f"{column}→INT")

                elif bq_type == 'FLOAT':
                    # Convert to float, handling invalid values
                    df[column] = pd.to_numeric(df[column], errors='coerce')
                    conversions_made.append(f"{column}→FLOAT")

                elif bq_type == 'STRING':
                    # Convert to string
                    df[column] = df[column].astype(str)
                    conversions_made.append(f"{column}→STR")

                elif bq_type == 'TIMESTAMP':
                    # Convert to datetime, handling invalid values
                    df[column] = pd.to_datetime(df[column], errors='coerce')
                    conversions_made.append(f"{column}→TIMESTAMP")

            except Exception as e:
                logger.warning(f"Could not convert column '{column}' to {bq_type}: {e}")

        if conversions_made:
            logger.info(f"Converted {len(conversions_made)} column types: {', '.join(conversions_made)}")

        return df

    def _rename_dataframe_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Rename DataFrame columns from original names to sanitized BigQuery column names,
        filter to only include columns that exist in the BigQuery table,
        and convert column types to match BigQuery schema.

        For file sources, columns may have special characters that are invalid in BigQuery.
        This method:
        1. Renames columns using the column_mapping stored in the job config
        2. Filters DataFrame to only include columns that exist in BigQuery table
        3. Converts DataFrame column types to match BigQuery schema

        Args:
            df: DataFrame with original column names

        Returns:
            DataFrame with renamed, filtered, and type-converted columns
        """
        column_mapping = self.job_config.get('column_mapping', {})

        if not column_mapping:
            return df

        # Step 1: Rename columns (original -> sanitized)
        rename_dict = {}
        for original_name, sanitized_name in column_mapping.items():
            if original_name in df.columns:
                rename_dict[original_name] = sanitized_name

        if rename_dict:
            df = df.rename(columns=rename_dict)
            logger.info(f"Renamed {len(rename_dict)} columns to match BigQuery schema")

        # Step 2: Filter to only columns that exist in BigQuery table
        bq_table_columns = self._get_bigquery_table_columns()

        if bq_table_columns:
            df_columns = list(df.columns)
            columns_to_keep = [col for col in df_columns if col in bq_table_columns]
            columns_to_drop = [col for col in df_columns if col not in bq_table_columns]

            if columns_to_drop:
                df = df[columns_to_keep]
                logger.info(f"Filtered DataFrame: kept {len(columns_to_keep)} columns, dropped {len(columns_to_drop)} columns ({', '.join(columns_to_drop)})")
            else:
                logger.info(f"All {len(df_columns)} DataFrame columns exist in BigQuery table")

        # Step 3: Convert DataFrame types to match BigQuery schema
        df = self._convert_dataframe_types(df)

        return df

    def run_catalog_load(self):
        """
        Run catalog (full snapshot) load.

        Replaces all data in the destination table.
        """
        logger.info("Starting CATALOG load (full snapshot)")

        # Update status to running
        if self.etl_run_id:
            self.config.update_etl_run_status(self.etl_run_id, 'running')

        try:
            # Extract data
            logger.info("Starting data extraction...")
            df_generator = self.extractor.extract_full(
                table_name=self.job_config['source_table_name'],
                schema_name=self.job_config['schema_name'],
                selected_columns=self.job_config['selected_columns'],
                batch_size=self.config.batch_size
            )

            # Count extracted rows (generator wrapper)
            def counting_generator(gen):
                for df in gen:
                    self.total_rows_extracted += len(df)
                    yield df

            # Load to BigQuery
            logger.info("Starting data load to BigQuery...")
            result = self.loader.load_full(
                df_generator=counting_generator(df_generator),
                on_batch_loaded=self._on_batch_loaded
            )

            logger.info(
                f"Catalog load completed successfully: "
                f"{result['total_rows']:,} rows in {result['batches_loaded']} batches"
            )

            return result

        except Exception as e:
            logger.error(f"Catalog load failed: {str(e)}")
            raise LoadError(f"Catalog load failed: {str(e)}") from e

        finally:
            self.extractor.close()

    def run_transactional_load(self):
        """
        Run transactional (incremental) load.

        Appends only new/updated data based on timestamp column.
        """
        logger.info("Starting TRANSACTIONAL load (incremental)")

        # Update status to running
        if self.etl_run_id:
            self.config.update_etl_run_status(self.etl_run_id, 'running')

        try:
            # Determine starting timestamp
            since_datetime = self.job_config.get('last_sync_value') or \
                           self.job_config.get('historical_start_date')

            if not since_datetime:
                raise ConfigurationError(
                    "Either last_sync_value or historical_start_date must be provided "
                    "for transactional loads"
                )

            logger.info(f"Extracting data since: {since_datetime}")

            # Extract data
            logger.info("Starting incremental data extraction...")
            df_generator = self.extractor.extract_incremental(
                table_name=self.job_config['source_table_name'],
                schema_name=self.job_config['schema_name'],
                timestamp_column=self.job_config['timestamp_column'],
                since_datetime=since_datetime,
                selected_columns=self.job_config['selected_columns'],
                batch_size=self.config.batch_size
            )

            # Count extracted rows (generator wrapper)
            def counting_generator(gen):
                for df in gen:
                    self.total_rows_extracted += len(df)
                    yield df

            # Load to BigQuery
            logger.info("Starting incremental data load to BigQuery...")
            result = self.loader.load_incremental(
                df_generator=counting_generator(df_generator),
                on_batch_loaded=self._on_batch_loaded
            )

            logger.info(
                f"Transactional load completed successfully: "
                f"{result['total_rows']:,} rows in {result['batches_loaded']} batches"
            )

            return result

        except Exception as e:
            logger.error(f"Transactional load failed: {str(e)}")
            raise LoadError(f"Transactional load failed: {str(e)}") from e

        finally:
            self.extractor.close()

    def run_catalog_load_files(self):
        """
        Run catalog load for file sources.

        Loads selected files (latest or all) and replaces BigQuery table.
        """
        logger.info("Starting CATALOG load for FILES")

        # Update status to running
        if self.etl_run_id:
            self.config.update_etl_run_status(self.etl_run_id, 'running')

        try:
            # Get processed files from Django API (empty for catalog mode)
            processed_files = {}

            # Extract files
            logger.info("Starting file extraction...")
            file_generator = self.extractor.extract_files(
                processed_files=processed_files,
                batch_size=self.config.batch_size
            )

            # Process files
            all_dataframes = []
            files_processed = []

            for df, file_metadata in file_generator:
                self.total_rows_extracted += len(df)
                all_dataframes.append(df)
                files_processed.append(file_metadata)

                logger.info(
                    f"Extracted {len(df):,} rows from {file_metadata['file_path']}"
                )

            if not all_dataframes:
                logger.warning("No files to process")
                return {'total_rows': 0, 'batches_loaded': 0, 'files_processed': 0}

            # Combine all dataframes
            combined_df = pd.concat(all_dataframes, ignore_index=True)
            logger.info(f"Combined {len(files_processed)} files → {len(combined_df):,} total rows")

            # Rename columns to match BigQuery schema (original -> sanitized names)
            combined_df = self._rename_dataframe_columns(combined_df)

            # Load to BigQuery (full replacement)
            logger.info("Starting data load to BigQuery...")

            def df_generator():
                yield combined_df

            result = self.loader.load_full(
                df_generator=df_generator(),
                on_batch_loaded=self._on_batch_loaded
            )

            result['files_processed'] = len(files_processed)

            logger.info(
                f"Catalog load completed: "
                f"{result['total_rows']:,} rows from {len(files_processed)} files"
            )

            return result

        except Exception as e:
            logger.error(f"File catalog load failed: {str(e)}")
            raise LoadError(f"File catalog load failed: {str(e)}") from e

        finally:
            self.extractor.close()

    def run_transactional_load_files(self):
        """
        Run transactional (incremental) load for file sources.

        Loads only new or changed files, tracks in ProcessedFile table.
        """
        logger.info("Starting TRANSACTIONAL load for FILES")

        # Update status to running
        if self.etl_run_id:
            self.config.update_etl_run_status(self.etl_run_id, 'running')

        try:
            # Get processed files from Django API
            processed_files_list = self.config.get_processed_files(self.data_source_id)

            # Convert to dict for easy lookup
            processed_files = {
                f['file_path']: {
                    'file_size_bytes': f['file_size_bytes'],
                    'file_last_modified': f['file_last_modified']
                }
                for f in processed_files_list
            }

            logger.info(f"Found {len(processed_files)} previously processed files")

            # Extract files
            logger.info("Starting file extraction (new/changed files only)...")
            file_generator = self.extractor.extract_files(
                processed_files=processed_files,
                batch_size=self.config.batch_size
            )

            # Process files
            files_processed = []

            for df, file_metadata in file_generator:
                self.total_rows_extracted += len(df)

                logger.info(
                    f"Extracted {len(df):,} rows from {file_metadata['file_path']}"
                )

                # Rename columns to match BigQuery schema (original -> sanitized names)
                df = self._rename_dataframe_columns(df)

                # Load to BigQuery (append)
                def df_generator():
                    yield df

                result = self.loader.load_incremental(
                    df_generator=df_generator(),
                    on_batch_loaded=self._on_batch_loaded
                )

                # Track file as processed
                self.config.record_processed_file(
                    data_source_id=self.data_source_id,
                    file_path=file_metadata['file_path'],
                    file_size_bytes=file_metadata['file_size_bytes'],
                    file_last_modified=file_metadata['file_last_modified'].isoformat() if hasattr(file_metadata['file_last_modified'], 'isoformat') else str(file_metadata['file_last_modified']),
                    rows_loaded=len(df)
                )

                files_processed.append(file_metadata)

            if not files_processed:
                logger.info("No new or changed files to process")
                return {'total_rows': 0, 'batches_loaded': 0, 'files_processed': 0}

            logger.info(
                f"Transactional load completed: "
                f"{self.total_rows_extracted:,} rows from {len(files_processed)} files"
            )

            return {
                'total_rows': self.total_rows_extracted,
                'batches_loaded': len(files_processed),
                'files_processed': len(files_processed)
            }

        except Exception as e:
            logger.error(f"File transactional load failed: {str(e)}")
            raise LoadError(f"File transactional load failed: {str(e)}") from e

        finally:
            self.extractor.close()

    def run(self):
        """
        Execute ETL job based on load type.

        Returns:
            Dict with execution results
        """
        self.start_time = datetime.utcnow()

        logger.info("=" * 80)
        logger.info("ETL RUN STARTED")
        logger.info(f"DataSource ID: {self.data_source_id}")
        logger.info(f"ETL Run ID: {self.etl_run_id}")
        logger.info(f"Load Type: {self.job_config['load_type']}")
        logger.info(f"Source: {self.job_config['schema_name']}.{self.job_config['source_table_name']}")
        logger.info(f"Destination: {self.config.gcp_project_id}.{self.config.bigquery_dataset}.{self.job_config['dest_table_name']}")
        logger.info("=" * 80)

        try:
            # Verify BigQuery table exists
            if not self.loader.verify_table_exists():
                raise ConfigurationError(
                    f"Destination table does not exist: {self.loader.table_ref}. "
                    f"Please create the table first using the ETL wizard."
                )

            # Execute load based on source type and load type
            source_type = self.job_config['source_type']
            load_type = self.job_config['load_type']
            is_file_source = source_type in ['gcs', 's3', 'azure_blob']

            if is_file_source:
                # File-based sources
                if load_type == 'catalog':
                    result = self.run_catalog_load_files()
                elif load_type == 'transactional':
                    result = self.run_transactional_load_files()
                else:
                    raise ConfigurationError(f"Invalid load type: {load_type}")
            else:
                # Database sources
                if load_type == 'catalog':
                    result = self.run_catalog_load()
                elif load_type == 'transactional':
                    result = self.run_transactional_load()
                else:
                    raise ConfigurationError(f"Invalid load type: {load_type}")

            # Calculate duration
            self.end_time = datetime.utcnow()
            duration_seconds = int((self.end_time - self.start_time).total_seconds())

            # Update final status
            if self.etl_run_id:
                self.config.update_etl_run_status(
                    etl_run_id=self.etl_run_id,
                    status='completed',
                    rows_extracted=self.total_rows_extracted,
                    rows_loaded=self.total_rows_loaded,
                    duration_seconds=duration_seconds
                )

            logger.info("=" * 80)
            logger.info("ETL RUN COMPLETED SUCCESSFULLY")
            logger.info(f"Rows Extracted: {self.total_rows_extracted:,}")
            logger.info(f"Rows Loaded: {self.total_rows_loaded:,}")
            logger.info(f"Duration: {duration_seconds} seconds")
            logger.info("=" * 80)

            return {
                'status': 'success',
                'rows_extracted': self.total_rows_extracted,
                'rows_loaded': self.total_rows_loaded,
                'duration_seconds': duration_seconds
            }

        except Exception as e:
            # Calculate duration even on failure
            self.end_time = datetime.utcnow()
            duration_seconds = int((self.end_time - self.start_time).total_seconds())

            # Handle error
            handle_etl_error(e, self.config, self.etl_run_id)

            logger.error("=" * 80)
            logger.error("ETL RUN FAILED")
            logger.error(f"Error: {str(e)}")
            logger.error(f"Duration before failure: {duration_seconds} seconds")
            logger.error("=" * 80)

            raise


def main():
    """Main entry point"""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='ETL Runner for B2B Recommendations Platform')
    parser.add_argument(
        '--data_source_id',
        type=int,
        required=True,
        help='DataSource ID to process'
    )
    parser.add_argument(
        '--etl_run_id',
        type=int,
        required=False,
        help='ETL Run ID for status tracking (optional)'
    )
    parser.add_argument(
        '--log_level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level'
    )
    parser.add_argument(
        '--json_logs',
        action='store_true',
        default=True,
        help='Use JSON log formatting (default: True for Cloud Run)'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(log_level=args.log_level, json_format=args.json_logs)

    # Load configuration
    try:
        config = Config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {str(e)}")
        sys.exit(1)

    # Run ETL
    try:
        with LogContext(data_source_id=args.data_source_id, etl_run_id=args.etl_run_id):
            runner = ETLRunner(
                config=config,
                data_source_id=args.data_source_id,
                etl_run_id=args.etl_run_id
            )

            result = runner.run()

            logger.info("ETL runner exiting successfully")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("ETL runner interrupted by user")
        sys.exit(130)

    except Exception as e:
        logger.error(f"ETL runner failed with error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
