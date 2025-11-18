"""
Configuration Management

Handles configuration loading from environment variables and Django API.
"""

import os
import logging
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for ETL runner"""

    def __init__(self):
        """Initialize configuration from environment variables"""

        # Django API configuration
        self.django_api_url = os.getenv('DJANGO_API_URL', '')
        self.api_token = os.getenv('ETL_API_TOKEN', '')

        # GCP configuration
        self.gcp_project_id = os.getenv('GCP_PROJECT_ID', '')
        self.bigquery_dataset = os.getenv('BIGQUERY_DATASET', 'raw_data')

        # ETL configuration
        self.batch_size = int(os.getenv('ETL_BATCH_SIZE', '10000'))
        self.max_retries = int(os.getenv('ETL_MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('ETL_RETRY_DELAY', '5'))  # seconds

        # Logging configuration
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')

        # Validate required config
        self._validate()

    def _validate(self):
        """Validate required configuration"""
        if not self.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID environment variable is required")

        if not self.django_api_url:
            raise ValueError(
                "DJANGO_API_URL environment variable is required. "
                "Set it to your Django Cloud Run URL (e.g., https://django-app-xxx.run.app)"
            )

        logger.info(f"Configuration loaded:")
        logger.info(f"  - Django API: {self.django_api_url}")
        logger.info(f"  - GCP Project: {self.gcp_project_id}")
        logger.info(f"  - BigQuery Dataset: {self.bigquery_dataset}")
        logger.info(f"  - Batch Size: {self.batch_size}")

    def get_job_config(self, data_source_id: int) -> Dict[str, Any]:
        """
        Fetch job configuration from Django API.

        Args:
            data_source_id: DataSource ID

        Returns:
            Dict with job configuration:
                - source_type: 'postgresql', 'mysql', etc.
                - connection_params: Connection details
                - source_table_name: Source table name
                - schema_name: Schema name
                - dest_table_name: Destination table name
                - load_type: 'transactional' or 'catalog'
                - timestamp_column: Column for incremental loads
                - selected_columns: List of columns to extract
                - last_sync_value: Last synced timestamp (for incremental)
                - historical_start_date: Start date for initial load
        """
        url = f"{self.django_api_url}/api/etl/job-config/{data_source_id}/"

        headers = {}
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'

        logger.info(f"Fetching job config from: {url}")

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            config = response.json()
            logger.info(f"Job config loaded for DataSource {data_source_id}")
            logger.debug(f"Config: {config}")

            return config

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch job config: {str(e)}")
            raise

    def update_etl_run_status(
        self,
        etl_run_id: int,
        status: str,
        **kwargs
    ) -> bool:
        """
        Update ETL run status in Django.

        Args:
            etl_run_id: ETLRun ID
            status: Status ('pending', 'running', 'completed', 'failed')
            **kwargs: Additional fields to update:
                - rows_extracted: Number of rows extracted
                - rows_loaded: Number of rows loaded
                - error_message: Error message if failed
                - duration_seconds: Duration in seconds

        Returns:
            True if update successful, False otherwise
        """
        if not etl_run_id:
            logger.warning("No ETL run ID provided, skipping status update")
            return False

        url = f"{self.django_api_url}/api/etl/runs/{etl_run_id}/update/"

        headers = {'Content-Type': 'application/json'}
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'

        payload = {'status': status, **kwargs}

        logger.info(f"Updating ETL run {etl_run_id}: {status}")
        logger.debug(f"Payload: {payload}")

        try:
            response = requests.patch(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()

            logger.info(f"ETL run status updated successfully")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update ETL run status: {str(e)}")
            return False

    def update_etl_run_progress(
        self,
        etl_run_id: int,
        rows_extracted: Optional[int] = None,
        rows_loaded: Optional[int] = None
    ) -> bool:
        """
        Update ETL run progress (rows extracted/loaded).

        Args:
            etl_run_id: ETLRun ID
            rows_extracted: Number of rows extracted so far
            rows_loaded: Number of rows loaded so far

        Returns:
            True if update successful, False otherwise
        """
        if not etl_run_id:
            return False

        url = f"{self.django_api_url}/api/etl/runs/{etl_run_id}/update/"

        headers = {'Content-Type': 'application/json'}
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'

        payload = {}
        if rows_extracted is not None:
            payload['rows_extracted'] = rows_extracted
        if rows_loaded is not None:
            payload['rows_loaded'] = rows_loaded

        if not payload:
            return False

        logger.debug(f"Updating ETL run {etl_run_id} progress: {payload}")

        try:
            response = requests.patch(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to update ETL run progress: {str(e)}")
            return False
