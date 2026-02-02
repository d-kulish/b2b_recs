"""
ETL Logs Service

Service for fetching Cloud Run Job logs from Cloud Logging for ETL runs.
Follows the EndpointLogsService pattern for consistency.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class EtlLogsServiceError(Exception):
    """Custom exception for ETL logs service errors."""
    pass


class EtlLogsService:
    """
    Service for fetching Cloud Run Job logs from Cloud Logging.

    Retrieves logs for ETL jobs running as Cloud Run Jobs.
    Can query by execution_name (preferred) or by job_name + timestamp range (fallback).
    """

    DEFAULT_LOG_LIMIT = 100
    LOG_RETENTION_DAYS = 7
    MAX_MESSAGE_LENGTH = 1000
    JOB_NAME = 'etl-runner'

    def __init__(self, project_id: str = None, region: str = 'europe-central2'):
        """
        Initialize the service.

        Args:
            project_id: GCP project ID (defaults to settings.GCP_PROJECT_ID)
            region: Cloud Run region (defaults to europe-central2)
        """
        self.project_id = project_id or getattr(settings, 'GCP_PROJECT_ID', 'b2b-recs')
        self.region = region
        self._logging_client = None

    @property
    def logging_client(self):
        """Lazy-load Cloud Logging client."""
        if self._logging_client is None:
            try:
                from google.cloud import logging as cloud_logging
                self._logging_client = cloud_logging.Client(project=self.project_id)
            except ImportError:
                raise EtlLogsServiceError(
                    "google-cloud-logging package not installed. "
                    "Install with: pip install google-cloud-logging"
                )
        return self._logging_client

    def get_logs(self, etl_run, limit: int = None) -> Dict:
        """
        Fetch logs for an ETL run.

        Args:
            etl_run: ETLRun instance
            limit: Maximum number of log entries (default: 100)

        Returns:
            Dict with structure:
            {
                'available': bool,
                'logs': [{'timestamp': str, 'severity': str, 'message': str}, ...],
                'count': int,
                'source': str,  # 'execution' or 'timestamp_range'
                'message': str  # Only if available=False
            }
        """
        limit = limit or self.DEFAULT_LOG_LIMIT

        # Check if the run has started
        if not etl_run.started_at:
            return {
                'available': False,
                'message': 'ETL run has not started yet.'
            }

        try:
            # Try to get logs by execution name (most precise)
            if etl_run.cloud_run_execution_name:
                logs = self._fetch_logs_by_execution(etl_run.cloud_run_execution_name, limit)
                if logs:
                    return {
                        'available': True,
                        'logs': logs,
                        'count': len(logs),
                        'source': 'execution'
                    }

            # Fallback: query by timestamp range
            logs = self._fetch_logs_by_timestamp(
                etl_run.started_at,
                etl_run.completed_at,
                limit
            )

            if logs:
                return {
                    'available': True,
                    'logs': logs,
                    'count': len(logs),
                    'source': 'timestamp_range',
                    'note': 'Logs queried by timestamp range (execution name not available)'
                }

            # No logs found
            return {
                'available': False,
                'message': self._get_no_logs_message(etl_run)
            }

        except Exception as e:
            logger.exception(f"Error fetching logs for ETL run {etl_run.id}: {e}")
            return self._handle_error(e)

    def _fetch_logs_by_execution(self, execution_name: str, limit: int) -> List[Dict]:
        """
        Fetch logs using the Cloud Run execution name.

        Args:
            execution_name: Cloud Run execution name (e.g., 'etl-runner-abc123')
            limit: Maximum log entries

        Returns:
            List of log entries
        """
        try:
            from google.cloud import logging as cloud_logging

            # Query Cloud Run Job logs by execution name
            # This is the most precise query
            log_filter = f'''
resource.type = "cloud_run_job"
resource.labels.job_name = "{self.JOB_NAME}"
resource.labels.location = "{self.region}"
labels."run.googleapis.com/execution_name" = "{execution_name}"
severity >= DEFAULT
'''.strip()

            logger.info(f"Fetching ETL logs by execution_name={execution_name}")
            logger.debug(f"Log filter: {log_filter}")

            entries = self.logging_client.list_entries(
                filter_=log_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=limit
            )

            logs = self._parse_log_entries(entries)
            return logs

        except Exception as e:
            logger.warning(f"Failed to fetch logs by execution name: {e}")
            return []

    def _fetch_logs_by_timestamp(
        self,
        started_at: datetime,
        completed_at: Optional[datetime],
        limit: int
    ) -> List[Dict]:
        """
        Fetch logs using timestamp range as fallback.

        Args:
            started_at: Run start timestamp
            completed_at: Run completion timestamp (optional)
            limit: Maximum log entries

        Returns:
            List of log entries
        """
        try:
            from google.cloud import logging as cloud_logging

            # Build timestamp range
            # Subtract 1 minute from start time to capture initialization logs
            start_time = started_at - timedelta(minutes=1)

            # End time: either completion time + buffer, or now
            if completed_at:
                end_time = completed_at + timedelta(minutes=5)
            else:
                end_time = datetime.now(timezone.utc)

            # Query Cloud Run Job logs by timestamp range
            log_filter = f'''
resource.type = "cloud_run_job"
resource.labels.job_name = "{self.JOB_NAME}"
resource.labels.location = "{self.region}"
timestamp >= "{start_time.isoformat()}"
timestamp <= "{end_time.isoformat()}"
severity >= DEFAULT
'''.strip()

            logger.info(f"Fetching ETL logs by timestamp range: {start_time} to {end_time}")
            logger.debug(f"Log filter: {log_filter}")

            entries = self.logging_client.list_entries(
                filter_=log_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=limit
            )

            logs = self._parse_log_entries(entries)
            return logs

        except Exception as e:
            logger.warning(f"Failed to fetch logs by timestamp: {e}")
            return []

    def _parse_log_entries(self, entries) -> List[Dict]:
        """Parse Cloud Logging entries into structured format."""
        logs = []
        for entry in entries:
            log_entry = self._parse_entry(entry)
            if log_entry:
                logs.append(log_entry)
        return logs

    def _parse_entry(self, entry) -> Optional[Dict]:
        """Parse a single Cloud Logging entry."""
        try:
            # Get payload (works for both TextEntry and ProtobufEntry)
            payload = getattr(entry, 'payload', None)
            if not payload:
                return None

            # Extract message based on payload type
            message = None
            if isinstance(payload, str):
                # TextEntry - container stdout/stderr logs
                message = payload
            elif isinstance(payload, dict):
                # ProtobufEntry - structured logs
                # Skip audit logs as they're not useful for debugging
                if payload.get('@type', '').endswith('AuditLog'):
                    return None
                # Try common message fields
                message = payload.get('message') or payload.get('textPayload')
                if not message:
                    # For other structured logs, show a summary
                    message = str(payload)
            else:
                message = str(payload)

            if not message:
                return None

            # Format timestamp
            timestamp = ''
            if hasattr(entry, 'timestamp') and entry.timestamp:
                timestamp = entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')

            # Get severity (handle None severity)
            severity = 'DEFAULT'
            if hasattr(entry, 'severity') and entry.severity:
                severity = str(entry.severity)

            return {
                'timestamp': timestamp,
                'severity': severity,
                'message': message[:self.MAX_MESSAGE_LENGTH]
            }
        except Exception as e:
            logger.debug(f"Failed to parse log entry: {e}")
            return None

    def _get_no_logs_message(self, etl_run) -> str:
        """Get a message explaining why no logs were found."""
        status = etl_run.status

        if status == 'pending':
            return "ETL run is pending. Logs will be available once execution starts."
        elif status == 'running':
            return "ETL run is starting up. Logs should appear shortly."
        elif status == 'cancelled':
            return "ETL run was cancelled before logs were generated."
        elif status == 'completed':
            return "No logs found. Logs may have expired (retained for 7 days)."
        elif status == 'failed':
            return "No logs found. The job may have failed before generating any logs."
        else:
            return "No logs available for this ETL run."

    def _handle_error(self, error: Exception) -> Dict:
        """Handle errors and return user-friendly messages."""
        error_str = str(error)

        if 'Permission denied' in error_str or '403' in error_str:
            return {
                'available': False,
                'message': "Access denied. The service account may need 'roles/logging.viewer' permission."
            }
        elif 'not found' in error_str.lower() or '404' in error_str:
            return {
                'available': False,
                'message': "Logs not found. They may have expired or been deleted."
            }
        else:
            return {
                'available': False,
                'message': f"Failed to fetch logs: {error_str[:100]}"
            }
