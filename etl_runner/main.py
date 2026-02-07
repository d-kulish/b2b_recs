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
from extractors.bigquery import BigQueryExtractor
from extractors.firestore import FirestoreExtractor
from extractors.file_extractor import FileExtractor
from loaders.bigquery_loader import BigQueryLoader
from utils.logging_config import setup_logging, LogContext
from utils.error_handling import (
    handle_etl_error,
    validate_job_config,
    ExtractionError,
    LoadError,
    ConfigurationError,
    ERROR_TYPE_INIT,
    ERROR_TYPE_VALIDATION,
    ERROR_TYPE_EXTRACTION,
    ERROR_TYPE_LOAD,
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
        self.total_bytes_processed = 0  # Track bytes for KPI display
        self.start_time = None
        self.end_time = None
        self.max_extracted_timestamp = None  # Track max timestamp for transactional loads
        self._current_phase = 'init'  # Track current phase for error classification

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
        elif source_type == 'bigquery':
            return BigQueryExtractor(connection_params)

        # NoSQL extractors
        elif source_type == 'firestore':
            return FirestoreExtractor(connection_params)

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

    def estimate_row_count(self) -> int:
        """
        Estimate number of rows for this ETL job.

        For databases: Runs SELECT COUNT(*) query with WHERE clause for incremental loads
        For files: Estimates based on file size, filtering to only NEW/CHANGED files for transactional loads

        Returns:
            Estimated number of rows to be extracted
        """
        try:
            load_type = self.job_config.get('load_type', 'transactional')
            source_type = self.job_config['source_type']

            # Build parameters for estimation
            table_name = self.job_config.get('source_table_name', '')
            schema_name = self.job_config.get('schema_name', '')
            timestamp_column = self.job_config.get('timestamp_column')
            since_datetime = None

            # For transactional loads, get the last sync value
            if load_type == 'transactional' and timestamp_column:
                since_datetime = self.job_config.get('last_sync_value') or \
                               self.job_config.get('historical_start_date')

            # For file sources in transactional mode, get processed files to estimate only new files
            processed_files = None
            if source_type in ['gcs', 's3', 'azure_blob'] and load_type == 'transactional':
                logger.info("Fetching processed files for accurate volume estimation...")
                processed_files_list = self.config.get_processed_files(self.data_source_id)

                # Convert to dict format (same as in run_transactional_load_files)
                from dateutil import parser as date_parser
                processed_files = {}
                for f in processed_files_list:
                    # Parse ISO string to datetime object for comparison
                    file_last_modified = f['file_last_modified']
                    if file_last_modified and isinstance(file_last_modified, str):
                        try:
                            file_last_modified = date_parser.isoparse(file_last_modified)
                        except Exception as e:
                            logger.warning(f"Failed to parse datetime: {e}")
                            file_last_modified = None

                    processed_files[f['file_path']] = {
                        'file_size_bytes': f['file_size_bytes'],
                        'file_last_modified': file_last_modified
                    }

                logger.info(f"Found {len(processed_files)} previously processed files")

            # Call extractor's estimate_row_count method
            estimate_kwargs = {
                'table_name': table_name,
                'schema_name': schema_name,
                'timestamp_column': timestamp_column,
                'since_datetime': since_datetime,
            }
            if processed_files is not None:
                estimate_kwargs['processed_files'] = processed_files
            estimated_rows = self.extractor.estimate_row_count(**estimate_kwargs)

            logger.info(f"Estimated row count: {estimated_rows:,}")
            return estimated_rows

        except Exception as e:
            logger.warning(f"Failed to estimate row count: {str(e)}")
            # On error, return 0 (will fall back to standard processing)
            return 0

    def detect_file_changes(self) -> dict:
        """
        Detect which files have changed since last ETL run.

        For file sources, this method:
        1. Fetches previously processed files from Django API (ProcessedFile table)
        2. Lists available files in cloud storage
        3. Compares timestamps and sizes to detect changes
        4. Returns change detection results

        Returns:
            Dict with:
                - has_changes: bool - Whether any files have changed
                - changed_files: list - Files that are new or modified
                - all_files: list - All available files matching pattern
                - processed_files: dict - Previously processed files metadata
        """
        source_type = self.job_config['source_type']

        # Only applicable for file sources
        if source_type not in ['gcs', 's3', 'azure_blob']:
            return {
                'has_changes': True,  # Database sources always "have changes"
                'changed_files': [],
                'all_files': [],
                'processed_files': {}
            }

        logger.info("=" * 80)
        logger.info("DETECTING FILE CHANGES")
        logger.info("=" * 80)

        # Fetch previously processed files from Django API
        processed_files_list = self.config.get_processed_files(self.data_source_id)

        # Convert to dict for easy lookup with parsed datetimes
        from dateutil import parser as date_parser

        processed_files = {}
        for f in processed_files_list:
            file_last_modified = f['file_last_modified']
            if file_last_modified and isinstance(file_last_modified, str):
                try:
                    file_last_modified = date_parser.isoparse(file_last_modified)
                except Exception as e:
                    logger.warning(f"Failed to parse datetime for {f['file_path']}: {e}")
                    file_last_modified = None

            processed_files[f['file_path']] = {
                'file_size_bytes': f['file_size_bytes'],
                'file_last_modified': file_last_modified
            }

        logger.info(f"Found {len(processed_files)} previously processed files")

        # List available files from cloud storage
        all_files = self.extractor.list_files()
        logger.info(f"Found {len(all_files)} files matching pattern in storage")

        if not all_files:
            logger.warning("No files found matching pattern")
            return {
                'has_changes': False,
                'changed_files': [],
                'all_files': [],
                'processed_files': processed_files
            }

        # Detect changes
        changed_files = []
        for file in all_files:
            file_path = file['file_path']

            if file_path not in processed_files:
                # New file
                logger.info(f"  NEW: {file_path}")
                changed_files.append(file)
            else:
                # Check if file has changed (size or modification time)
                prev_metadata = processed_files[file_path]

                # Compare file_last_modified timestamps
                file_changed = False
                current_modified = file['file_last_modified']
                prev_modified = prev_metadata['file_last_modified']

                # Handle timezone-aware/naive datetime comparison
                if current_modified and prev_modified:
                    # Normalize to comparable format
                    if hasattr(current_modified, 'replace') and current_modified.tzinfo:
                        current_ts = current_modified.timestamp()
                    else:
                        current_ts = current_modified.timestamp() if hasattr(current_modified, 'timestamp') else 0

                    if hasattr(prev_modified, 'replace') and prev_modified.tzinfo:
                        prev_ts = prev_modified.timestamp()
                    else:
                        prev_ts = prev_modified.timestamp() if hasattr(prev_modified, 'timestamp') else 0

                    # Allow 1 second tolerance for timestamp comparison
                    if abs(current_ts - prev_ts) > 1:
                        file_changed = True
                        logger.info(f"  MODIFIED (timestamp): {file_path}")
                        logger.info(f"    Previous: {prev_modified}")
                        logger.info(f"    Current:  {current_modified}")

                # Also check size as a secondary indicator
                if file['file_size_bytes'] != prev_metadata['file_size_bytes']:
                    file_changed = True
                    logger.info(f"  MODIFIED (size): {file_path}")
                    logger.info(f"    Previous: {prev_metadata['file_size_bytes']} bytes")
                    logger.info(f"    Current:  {file['file_size_bytes']} bytes")

                if file_changed:
                    changed_files.append(file)
                else:
                    logger.debug(f"  UNCHANGED: {file_path}")

        has_changes = len(changed_files) > 0

        logger.info("=" * 80)
        if has_changes:
            logger.info(f"✓ CHANGES DETECTED: {len(changed_files)} new/modified files")
        else:
            logger.info("✓ NO CHANGES: All files are unchanged since last run")
        logger.info("=" * 80)

        # Store for use by other methods
        self._file_change_detection = {
            'has_changes': has_changes,
            'changed_files': changed_files,
            'all_files': all_files,
            'processed_files': processed_files
        }

        return self._file_change_detection

    def determine_processing_mode(self, files_to_process: list = None) -> str:
        """
        Determine whether to use standard (pandas) or dataflow (Beam) processing.

        Decision logic:
        1. If processing_mode is explicitly set to 'standard' or 'dataflow', use that
        2. If processing_mode is 'auto', estimate row count and compare to threshold
        3. Default to 'standard' if estimation fails

        Args:
            files_to_process: Optional list of files that will be processed
                              (used for more accurate row estimation)

        Returns:
            'standard' or 'dataflow'
        """
        processing_mode = self.job_config.get('processing_mode', 'auto')

        logger.info(f"Processing mode configuration: {processing_mode}")

        if processing_mode == 'standard':
            logger.info("Forcing standard processing (user configured)")
            return 'standard'
        elif processing_mode == 'dataflow':
            logger.info("Forcing Dataflow processing (user configured)")
            return 'dataflow'
        else:
            # Auto-detect based on row count
            threshold = self.job_config.get('row_count_threshold', 1_000_000)

            # If we have a specific list of files, estimate based on those
            if files_to_process:
                total_size_bytes = sum(f['file_size_bytes'] for f in files_to_process)
                total_size_mb = total_size_bytes / (1024 * 1024)
                file_format = self.job_config.get('file_format', 'csv')

                rows_per_mb = {'csv': 20000, 'parquet': 100000, 'json': 10000}
                estimated_rows = int(total_size_mb * rows_per_mb.get(file_format, 20000))

                logger.info(f"Estimating rows from {len(files_to_process)} files ({total_size_mb:.2f} MB)")
            else:
                estimated_rows = self.estimate_row_count()

            logger.info(f"Auto-detection: {estimated_rows:,} rows vs {threshold:,} threshold")

            if estimated_rows >= threshold:
                logger.info("✓ Using Dataflow processing (large dataset)")
                return 'dataflow'
            else:
                logger.info("✓ Using standard processing (small dataset)")
                return 'standard'

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

            # Count extracted rows and track bytes (generator wrapper)
            def counting_generator(gen):
                for df in gen:
                    self.total_rows_extracted += len(df)
                    # Track bytes processed (memory usage of DataFrame)
                    self.total_bytes_processed += df.memory_usage(deep=True).sum()
                    yield df

            # Mark extraction complete, loading starting
            self._report_phase_timestamp('extraction_completed')
            self._current_phase = 'load'
            self._report_phase_timestamp('loading_started')

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
            last_sync_value = self.job_config.get('last_sync_value')
            historical_start_date = self.job_config.get('historical_start_date')
            since_datetime = last_sync_value or historical_start_date

            if not since_datetime:
                raise ConfigurationError(
                    "Either last_sync_value or historical_start_date must be provided "
                    "for transactional loads"
                )

            # Detect stale watermark: if destination table is empty but we have
            # a last_sync_value, the watermark is stale (e.g. table was recreated).
            # Fall back to historical_start_date or a safe default to re-extract.
            if last_sync_value and since_datetime == last_sync_value:
                try:
                    table_info = self.loader.get_table_info()
                    if table_info.get('num_rows', -1) == 0:
                        fallback = historical_start_date or "2000-01-01T00:00:00"
                        logger.warning(
                            f"Destination table is empty but last_sync_value is "
                            f"'{last_sync_value}' — stale watermark detected. "
                            f"Falling back to '{fallback}'"
                        )
                        since_datetime = fallback
                except Exception as e:
                    logger.warning(f"Could not check destination table row count: {e}")

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

            # Count extracted rows, track max timestamp and bytes (generator wrapper)
            timestamp_col = self.job_config.get('timestamp_column')

            def counting_generator(gen):
                for df in gen:
                    self.total_rows_extracted += len(df)
                    # Track bytes processed (memory usage of DataFrame)
                    self.total_bytes_processed += df.memory_usage(deep=True).sum()
                    # Track max timestamp for updating last_sync_value
                    if timestamp_col and timestamp_col in df.columns:
                        batch_max = df[timestamp_col].max()
                        if pd.notna(batch_max):
                            if self.max_extracted_timestamp is None or batch_max > self.max_extracted_timestamp:
                                self.max_extracted_timestamp = batch_max
                    yield df

            # Mark extraction complete, loading starting
            self._report_phase_timestamp('extraction_completed')
            self._current_phase = 'load'
            self._report_phase_timestamp('loading_started')

            # Load to BigQuery
            logger.info("Starting incremental data load to BigQuery...")
            result = self.loader.load_incremental(
                df_generator=counting_generator(df_generator),
                on_batch_loaded=self._on_batch_loaded
            )

            # Log max timestamp if captured
            if self.max_extracted_timestamp is not None:
                logger.info(f"Max extracted timestamp: {self.max_extracted_timestamp}")

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
        Now uses pre-detected files from detect_file_changes() if available.
        """
        logger.info("Starting CATALOG load for FILES")

        # Update status to running
        if self.etl_run_id:
            self.config.update_etl_run_status(self.etl_run_id, 'running')

        try:
            # Use pre-detected files if available (from detect_file_changes)
            # Otherwise fall back to extracting all files
            if hasattr(self, '_files_to_process') and self._files_to_process:
                files_to_load = self._files_to_process
                logger.info(f"Using {len(files_to_load)} pre-detected files for catalog load")
            else:
                # Fallback: load all files (backward compatibility)
                files_to_load = self.extractor.list_files()
                logger.info(f"Listing all {len(files_to_load)} files for catalog load")

            if not files_to_load:
                logger.warning("No files to process")
                return {'total_rows': 0, 'batches_loaded': 0, 'files_processed': 0}

            # Process files
            all_dataframes = []
            files_processed = []

            for file_metadata in files_to_load:
                file_path = file_metadata['file_path']
                logger.info(f"Extracting file: {file_path}")

                try:
                    df = self.extractor.extract_file(file_path)
                    self.total_rows_extracted += len(df)
                    # Track bytes processed (memory usage + file size)
                    self.total_bytes_processed += df.memory_usage(deep=True).sum()
                    self.total_bytes_processed += file_metadata.get('file_size_bytes', 0)
                    all_dataframes.append(df)
                    files_processed.append(file_metadata)

                    logger.info(
                        f"Extracted {len(df):,} rows from {file_path}"
                    )
                except Exception as e:
                    logger.error(f"Failed to extract file {file_path}: {str(e)}")
                    raise

            if not all_dataframes:
                logger.warning("No data extracted from files")
                return {'total_rows': 0, 'batches_loaded': 0, 'files_processed': 0}

            # Combine all dataframes
            combined_df = pd.concat(all_dataframes, ignore_index=True)
            logger.info(f"Combined {len(files_processed)} files → {len(combined_df):,} total rows")

            # Rename columns to match BigQuery schema (original -> sanitized names)
            combined_df = self._rename_dataframe_columns(combined_df)

            # Mark extraction complete, loading starting
            self._report_phase_timestamp('extraction_completed')
            self._current_phase = 'load'
            self._report_phase_timestamp('loading_started')

            # Load to BigQuery (full replacement)
            logger.info("Starting data load to BigQuery...")

            def df_generator():
                yield combined_df

            result = self.loader.load_full(
                df_generator=df_generator(),
                on_batch_loaded=self._on_batch_loaded
            )

            result['files_processed'] = len(files_processed)

            # Record processed files in ProcessedFile table
            # This enables change detection for future runs
            logger.info("Recording processed files for future change detection...")
            for file_metadata in files_processed:
                try:
                    self.config.record_processed_file(
                        data_source_id=self.data_source_id,
                        file_path=file_metadata['file_path'],
                        file_size_bytes=file_metadata['file_size_bytes'],
                        file_last_modified=file_metadata['file_last_modified'].isoformat() if hasattr(file_metadata['file_last_modified'], 'isoformat') else str(file_metadata['file_last_modified']),
                        rows_loaded=len(combined_df) // len(files_processed) if files_processed else 0  # Approximate per-file
                    )
                except Exception as e:
                    logger.warning(f"Failed to record processed file {file_metadata['file_path']}: {e}")

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
            # Parse ISO datetime strings to datetime objects for accurate comparison
            from dateutil import parser as date_parser

            processed_files = {}
            for f in processed_files_list:
                # Parse ISO string to datetime object (for comparison with GCS/S3/Azure blob timestamps)
                file_last_modified = f['file_last_modified']
                if file_last_modified and isinstance(file_last_modified, str):
                    try:
                        file_last_modified = date_parser.isoparse(file_last_modified)
                    except Exception as e:
                        logger.warning(f"Failed to parse datetime for {f['file_path']}: {e}")
                        file_last_modified = None

                processed_files[f['file_path']] = {
                    'file_size_bytes': f['file_size_bytes'],
                    'file_last_modified': file_last_modified
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
            first_file = True

            for df, file_metadata in file_generator:
                self.total_rows_extracted += len(df)
                # Track bytes processed
                self.total_bytes_processed += df.memory_usage(deep=True).sum()
                self.total_bytes_processed += file_metadata.get('file_size_bytes', 0)

                logger.info(
                    f"Extracted {len(df):,} rows from {file_metadata['file_path']}"
                )

                # Mark extraction complete after first file (since we're streaming)
                if first_file:
                    self._report_phase_timestamp('extraction_completed')
                    self._current_phase = 'load'
                    self._report_phase_timestamp('loading_started')
                    first_file = False

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
                # Mark all phases as completed even though no work was done
                self._report_phase_timestamp('extraction_completed')
                self._current_phase = 'load'
                self._report_phase_timestamp('loading_started')
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

    def run_with_dataflow(self):
        """
        Execute ETL using Dataflow + Apache Beam for large datasets.

        This method submits a Dataflow job to GCP and monitors its execution.
        Suitable for datasets with >= 1M rows.

        Now uses pre-detected files from detect_file_changes() if available,
        avoiding reprocessing unchanged files.

        Returns:
            Dict with execution results
        """
        logger.info("=" * 80)
        logger.info("STARTING DATAFLOW EXECUTION")
        logger.info("=" * 80)

        try:
            from dataflow_pipelines.etl_pipeline import (
                run_scalable_pipeline,
                run_bigquery_native_pipeline,
                run_file_pipeline
            )
            from dataflow_pipelines.partitioning import calculate_work_units

            # Update status to running
            if self.etl_run_id:
                self.config.update_etl_run_status(self.etl_run_id, 'running')

            # Prepare GCP configuration
            gcp_config = {
                'project_id': self.config.gcp_project_id,
                'region': self.config.dataflow_region,
                'bucket': self.config.dataflow_bucket,
                'dataset_id': self.config.bigquery_dataset
            }

            # Add runtime context to job config
            job_config_with_context = self.job_config.copy()
            job_config_with_context['data_source_id'] = self.data_source_id
            job_config_with_context['etl_run_id'] = self.etl_run_id

            # CRITICAL: Calculate work partitions for parallel processing
            logger.info("=" * 80)
            logger.info("CALCULATING WORK PARTITIONS")
            logger.info("=" * 80)

            # Get pre-detected files if available (from detect_file_changes in run())
            files_to_process = getattr(self, '_files_to_process', None)
            source_type = self.job_config['source_type']
            is_file_source = source_type in ['gcs', 's3', 'azure_blob']

            # Calculate estimated rows based on files that will actually be processed
            if files_to_process:
                total_size_bytes = sum(f['file_size_bytes'] for f in files_to_process)
                total_size_mb = total_size_bytes / (1024 * 1024)
                file_format = self.job_config.get('file_format', 'csv')
                rows_per_mb = {'csv': 20000, 'parquet': 100000, 'json': 10000}
                estimated_rows = int(total_size_mb * rows_per_mb.get(file_format, 20000))
                logger.info(f"Estimating {estimated_rows:,} rows from {len(files_to_process)} files ({total_size_mb:.2f} MB)")
            else:
                estimated_rows = self.estimate_row_count()

            # Pass files_to_process to partitioning for file sources
            work_units = calculate_work_units(
                job_config=job_config_with_context,
                extractor=self.extractor,
                estimated_rows=estimated_rows,
                files_to_process=files_to_process if is_file_source else None
            )

            # Handle empty work units (no changes detected)
            if not work_units:
                logger.info("=" * 80)
                logger.info("NO WORK UNITS: Nothing to process via Dataflow")
                logger.info("=" * 80)
                return {
                    'status': 'success',
                    'processing_mode': 'dataflow',
                    'message': 'No files to process - all files unchanged',
                    'rows_extracted': 0,
                    'rows_loaded': 0
                }

            logger.info(f"✓ Created {len(work_units)} work units for parallel processing")
            logger.info("=" * 80)

            # Determine which pipeline to use based on source type and work unit type
            source_type = self.job_config['source_type']

            if work_units and work_units[0].get('type') == 'bigquery_native':
                # Use BigQuery native I/O for BigQuery sources
                logger.info("Launching BIGQUERY NATIVE Dataflow pipeline")
                result = run_bigquery_native_pipeline(job_config_with_context, gcp_config, work_units)
            elif is_file_source and files_to_process:
                # Use native Beam I/O for file sources (NEW - no pandas, handles large files)
                logger.info("Launching FILE PIPELINE with native Beam I/O")

                # Build full GCS paths from bucket name and file paths
                bucket_name = job_config_with_context['connection_params'].get('bucket', '')
                file_paths = []
                for f in files_to_process:
                    file_path = f['file_path']
                    # Construct full GCS path if not already present
                    if not file_path.startswith('gs://'):
                        full_path = f"gs://{bucket_name}/{file_path}"
                    else:
                        full_path = file_path
                    file_paths.append(full_path)

                logger.info(f"File paths for Beam: {file_paths}")
                result = run_file_pipeline(job_config_with_context, gcp_config, file_paths)
            else:
                # Use scalable pipeline for database sources
                logger.info("Launching SCALABLE Dataflow pipeline")
                result = run_scalable_pipeline(job_config_with_context, gcp_config, work_units)

            logger.info("=" * 80)
            logger.info("DATAFLOW JOB SUBMITTED")
            logger.info(f"Job Name: {result['job_name']}")
            logger.info(f"Monitor at: https://console.cloud.google.com/dataflow/jobs/{gcp_config['region']}/{result['job_name']}")
            logger.info("=" * 80)

            # Poll for Dataflow job completion and track metrics
            final_rows_loaded = 0
            dataflow_job_id = None
            dataflow_api_failed = False

            try:
                job_name = result['job_name']
                final_rows_loaded, dataflow_job_id = self._wait_for_dataflow_completion(
                    job_name=job_name,
                    region=gcp_config['region'],
                    project_id=gcp_config['project_id']
                )
            except Exception as e:
                logger.warning(f"Failed to wait for Dataflow completion: {e}")
                dataflow_api_failed = True

            # Use estimated rows as fallback if Dataflow API failed or returned 0
            effective_rows = final_rows_loaded
            if final_rows_loaded == 0 and estimated_rows > 0:
                if dataflow_api_failed:
                    logger.warning(f"Dataflow API failed - using estimated row count: {estimated_rows:,}")
                else:
                    logger.warning(f"Dataflow returned 0 rows - using estimated row count: {estimated_rows:,}")
                effective_rows = estimated_rows

            # Record processed files for change detection on future runs
            if is_file_source and files_to_process:
                logger.info("Recording processed files for future change detection...")
                rows_per_file = effective_rows // len(files_to_process) if len(files_to_process) > 0 else 0

                for file_metadata in files_to_process:
                    try:
                        self.config.record_processed_file(
                            data_source_id=self.data_source_id,
                            file_path=file_metadata['file_path'],
                            file_size_bytes=file_metadata['file_size_bytes'],
                            file_last_modified=file_metadata['file_last_modified'].isoformat() if hasattr(file_metadata['file_last_modified'], 'isoformat') else str(file_metadata['file_last_modified']),
                            rows_loaded=rows_per_file
                        )
                        logger.info(f"Recorded: {file_metadata['file_path']}")
                    except Exception as e:
                        logger.warning(f"Failed to record processed file {file_metadata['file_path']}: {e}")

            # Update row counts using effective_rows (with fallback)
            self.total_rows_extracted = effective_rows
            self.total_rows_loaded = effective_rows

            return {
                'status': 'success',
                'processing_mode': 'dataflow',
                'dataflow_job_name': result['job_name'],
                'dataflow_job_id': dataflow_job_id,
                'message': result['message'],
                'rows_extracted': effective_rows,
                'rows_loaded': effective_rows
            }

        except Exception as e:
            logger.error(f"Dataflow execution failed: {str(e)}")
            raise

    def _wait_for_dataflow_completion(self, job_name: str, region: str, project_id: str, timeout_seconds: int = 3000) -> tuple:
        """
        Wait for Dataflow job to complete and return row count and job ID.

        Args:
            job_name: Dataflow job name
            region: GCP region
            project_id: GCP project ID
            timeout_seconds: Maximum time to wait (default 50 minutes)

        Returns:
            Tuple of (rows_loaded, job_id) where:
            - rows_loaded: Number of rows loaded (from BigQuery)
            - job_id: Dataflow job ID for status tracking
        """
        import time

        logger.info(f"Waiting for Dataflow job '{job_name}' to complete...")

        # Initialize Dataflow client with retry logic
        client = None
        job_id = None
        max_init_retries = 3

        for retry in range(max_init_retries):
            try:
                from google.cloud import dataflow_v1beta3
                client = dataflow_v1beta3.JobsV1Beta3Client()
                break
            except ImportError as e:
                logger.error(f"Failed to import dataflow_v1beta3: {e}")
                logger.error("Please ensure google-cloud-dataflow-client is installed")
                raise
            except Exception as e:
                if retry < max_init_retries - 1:
                    logger.warning(f"Failed to initialize Dataflow client (attempt {retry + 1}/{max_init_retries}): {e}")
                    time.sleep(5)
                else:
                    raise

        start_time = time.time()
        poll_interval = 30  # seconds
        max_poll_retries = 3

        # First, get the job ID from job name with retry
        for retry in range(max_poll_retries):
            try:
                from google.cloud import dataflow_v1beta3
                request = dataflow_v1beta3.ListJobsRequest(
                    project_id=project_id,
                    location=region,
                    filter=dataflow_v1beta3.ListJobsRequest.Filter.ALL
                )
                jobs = client.list_jobs(request=request)
                for job in jobs:
                    if job.name == job_name:
                        job_id = job.id
                        break
                if job_id:
                    break
            except Exception as e:
                if retry < max_poll_retries - 1:
                    logger.warning(f"Could not list Dataflow jobs (attempt {retry + 1}/{max_poll_retries}): {e}")
                    time.sleep(5)
                else:
                    logger.warning(f"All attempts to list Dataflow jobs failed: {e}")
                    # Try using job_name as job_id as fallback
                    job_id = job_name

        if not job_id:
            logger.warning(f"Could not find Dataflow job with name {job_name}")
            return (0, None)

        logger.info(f"Found Dataflow job ID: {job_id}")

        # Poll for job completion with retry logic
        consecutive_errors = 0
        max_consecutive_errors = 5

        while time.time() - start_time < timeout_seconds:
            try:
                from google.cloud import dataflow_v1beta3
                request = dataflow_v1beta3.GetJobRequest(
                    project_id=project_id,
                    location=region,
                    job_id=job_id
                )
                job = client.get_job(request=request)
                consecutive_errors = 0  # Reset on success

                current_state = job.current_state.name if hasattr(job.current_state, 'name') else str(job.current_state)
                elapsed = int(time.time() - start_time)
                logger.info(f"Job {job_id} status: {current_state} (elapsed: {elapsed}s)")

                if current_state in ['JOB_STATE_DONE', 'DONE']:
                    logger.info("Dataflow job completed successfully!")
                    # Try to get row count from BigQuery destination
                    rows_loaded = self._get_bigquery_row_count()
                    return (rows_loaded, job_id)

                elif current_state in ['JOB_STATE_FAILED', 'FAILED', 'JOB_STATE_CANCELLED', 'CANCELLED']:
                    logger.error(f"Dataflow job ended with state: {current_state}")
                    raise Exception(f"Dataflow job failed with state: {current_state}")

                # Still running, wait and poll again
                time.sleep(poll_interval)

            except Exception as e:
                if 'failed' in str(e).lower() or 'cancelled' in str(e).lower():
                    raise

                consecutive_errors += 1
                logger.warning(f"Error polling Dataflow job (error {consecutive_errors}/{max_consecutive_errors}): {e}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive polling errors ({consecutive_errors}), giving up")
                    # Return what we have - job_id is known, rows will use fallback
                    return (0, job_id)

                time.sleep(poll_interval)

        logger.warning(f"Timeout waiting for Dataflow job after {timeout_seconds} seconds")
        return (0, job_id)

    def _get_bigquery_row_count(self) -> int:
        """
        Get row count from BigQuery destination table.

        Returns:
            Number of rows in the destination table
        """
        from google.cloud import bigquery

        try:
            client = bigquery.Client(project=self.config.gcp_project_id)
            table_ref = f"{self.config.gcp_project_id}.{self.config.bigquery_dataset}.{self.job_config['dest_table_name']}"

            query = f"SELECT COUNT(*) as cnt FROM `{table_ref}`"
            result = client.query(query).result()

            for row in result:
                count = row.cnt
                logger.info(f"BigQuery destination table row count: {count:,}")
                return count

            return 0
        except Exception as e:
            logger.warning(f"Could not get BigQuery row count: {e}")
            return 0

    def _report_phase_timestamp(self, phase: str):
        """
        Report a phase timestamp to Django API.

        Args:
            phase: Phase name (init_completed, validation_completed, extraction_started,
                   extraction_completed, loading_started, loading_completed)
        """
        if self.etl_run_id:
            self.config.update_etl_run_status(
                etl_run_id=self.etl_run_id,
                status='running',
                **{f'{phase}_at': True}
            )

    def run(self):
        """
        Execute ETL job based on load type.

        4-stage pipeline: INIT → VALIDATE → EXTRACT → LOAD

        Returns:
            Dict with execution results
        """
        self.start_time = datetime.utcnow()
        self._current_phase = 'init'

        logger.info("=" * 80)
        logger.info("ETL RUN STARTED")
        logger.info(f"DataSource ID: {self.data_source_id}")
        logger.info(f"ETL Run ID: {self.etl_run_id}")
        logger.info(f"Load Type: {self.job_config['load_type']}")
        logger.info(f"Source: {self.job_config['schema_name']}.{self.job_config['source_table_name']}")
        logger.info(f"Destination: {self.config.gcp_project_id}.{self.config.bigquery_dataset}.{self.job_config['dest_table_name']}")
        logger.info("=" * 80)

        try:
            # =========================================================================
            # PHASE 1: INIT - Configuration loaded, connections established
            # =========================================================================
            # (Already completed in __init__, report timestamp now)
            logger.info("PHASE: INIT completed - configuration loaded")
            self._report_phase_timestamp('init_completed')
            self._current_phase = 'validation'

            # =========================================================================
            # PHASE 2: VALIDATE - Verify BigQuery table exists
            # =========================================================================
            logger.info("PHASE: VALIDATE - verifying BigQuery destination table")
            if not self.loader.verify_table_exists():
                raise ConfigurationError(
                    f"Destination table does not exist: {self.loader.table_ref}. "
                    f"Please create the table first using the ETL wizard."
                )
            logger.info("PHASE: VALIDATE completed - destination table verified")
            self._report_phase_timestamp('validation_completed')
            self._current_phase = 'extraction'

            source_type = self.job_config['source_type']
            load_type = self.job_config['load_type']
            is_file_source = source_type in ['gcs', 's3', 'azure_blob']

            # For file sources: detect changes FIRST before deciding processing mode
            files_to_process = None
            if is_file_source:
                change_detection = self.detect_file_changes()

                if not change_detection['has_changes']:
                    # No files have changed - skip processing entirely
                    logger.info("=" * 80)
                    logger.info("SKIPPING ETL: No file changes detected")
                    logger.info("=" * 80)

                    # Update status to completed with 0 rows (all phases completed)
                    self.end_time = datetime.utcnow()
                    duration_seconds = int((self.end_time - self.start_time).total_seconds())

                    if self.etl_run_id:
                        self.config.update_etl_run_status(
                            etl_run_id=self.etl_run_id,
                            status='completed',
                            data_source_id=self.data_source_id,
                            rows_extracted=0,
                            rows_loaded=0,
                            duration_seconds=duration_seconds,
                            extraction_started_at=True,
                            extraction_completed_at=True,
                            loading_started_at=True,
                            loading_completed_at=True,
                        )

                    return {
                        'status': 'success',
                        'message': 'No file changes detected - skipping ETL',
                        'rows_extracted': 0,
                        'rows_loaded': 0,
                        'duration_seconds': duration_seconds
                    }

                # For Catalog mode: process ALL files if ANY changed
                # For Transactional mode: process only changed files
                if load_type == 'catalog':
                    files_to_process = change_detection['all_files']
                    logger.info(f"Catalog mode: Will process ALL {len(files_to_process)} files")
                else:
                    files_to_process = change_detection['changed_files']
                    logger.info(f"Transactional mode: Will process {len(files_to_process)} changed files")

                # Store for use by processing methods
                self._files_to_process = files_to_process
                self._processed_files_metadata = change_detection['processed_files']

            # Determine processing mode (standard vs dataflow)
            processing_mode = self.determine_processing_mode(files_to_process=files_to_process)
            logger.info(f"Selected processing mode: {processing_mode}")

            # =========================================================================
            # PHASE 3 & 4: EXTRACT → LOAD (handled by processing methods)
            # =========================================================================
            logger.info("PHASE: EXTRACT starting")
            self._report_phase_timestamp('extraction_started')

            # Execute based on processing mode
            if processing_mode == 'dataflow':
                # Use Dataflow + Apache Beam for large datasets
                result = self.run_with_dataflow()
            else:
                # Use standard pandas processing for smaller datasets
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
                update_kwargs = {
                    'etl_run_id': self.etl_run_id,
                    'status': 'completed',
                    'data_source_id': self.data_source_id,
                    'rows_extracted': self.total_rows_extracted,
                    'rows_loaded': self.total_rows_loaded,
                    'bytes_processed': self.total_bytes_processed,
                    'duration_seconds': duration_seconds,
                    'loading_completed_at': True,  # Mark final phase complete
                }

                # Include dataflow_job_id if this was a Dataflow execution
                if result.get('dataflow_job_id'):
                    update_kwargs['dataflow_job_id'] = result['dataflow_job_id']
                    logger.info(f"Including dataflow_job_id: {update_kwargs['dataflow_job_id']}")

                # Include max_extracted_timestamp for transactional loads
                if self.job_config.get('load_type') == 'transactional' and self.max_extracted_timestamp is not None:
                    # Convert to ISO string format
                    if hasattr(self.max_extracted_timestamp, 'isoformat'):
                        update_kwargs['max_extracted_timestamp'] = self.max_extracted_timestamp.isoformat()
                    else:
                        update_kwargs['max_extracted_timestamp'] = str(self.max_extracted_timestamp)
                    logger.info(f"Sending max_extracted_timestamp: {update_kwargs['max_extracted_timestamp']}")

                self.config.update_etl_run_status(**update_kwargs)

            logger.info("=" * 80)
            logger.info("ETL RUN COMPLETED SUCCESSFULLY")
            logger.info(f"Rows Extracted: {self.total_rows_extracted:,}")
            logger.info(f"Rows Loaded: {self.total_rows_loaded:,}")
            logger.info(f"Bytes Processed: {self.total_bytes_processed:,}")
            logger.info(f"Duration: {duration_seconds} seconds")
            logger.info("=" * 80)

            return {
                'status': 'success',
                'rows_extracted': self.total_rows_extracted,
                'rows_loaded': self.total_rows_loaded,
                'bytes_processed': self.total_bytes_processed,
                'duration_seconds': duration_seconds
            }

        except Exception as e:
            # Calculate duration even on failure
            self.end_time = datetime.utcnow()
            duration_seconds = int((self.end_time - self.start_time).total_seconds())

            # Map current phase to error type
            phase_to_error_type = {
                'init': ERROR_TYPE_INIT,
                'validation': ERROR_TYPE_VALIDATION,
                'extraction': ERROR_TYPE_EXTRACTION,
                'load': ERROR_TYPE_LOAD,
            }
            error_type = phase_to_error_type.get(self._current_phase, None)

            # Handle error with proper classification
            handle_etl_error(e, self.config, self.etl_run_id, self.data_source_id, error_type=error_type)

            logger.error("=" * 80)
            logger.error(f"ETL RUN FAILED in phase: {self._current_phase.upper()}")
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
