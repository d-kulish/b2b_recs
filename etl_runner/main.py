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

from config import Config
from extractors.postgresql import PostgreSQLExtractor
from extractors.mysql import MySQLExtractor
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

        if source_type == 'postgresql':
            return PostgreSQLExtractor(connection_params)
        elif source_type == 'mysql':
            return MySQLExtractor(connection_params)
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

            # Execute load based on type
            if self.job_config['load_type'] == 'catalog':
                result = self.run_catalog_load()
            elif self.job_config['load_type'] == 'transactional':
                result = self.run_transactional_load()
            else:
                raise ConfigurationError(f"Invalid load type: {self.job_config['load_type']}")

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
