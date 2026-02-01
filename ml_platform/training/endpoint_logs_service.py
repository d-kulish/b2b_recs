"""
Endpoint Logs Service

Service for fetching Cloud Run endpoint logs from Cloud Logging.
Follows the PipelineLogsService pattern for consistency.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class EndpointLogsServiceError(Exception):
    """Custom exception for endpoint logs service errors."""
    pass


class EndpointLogsService:
    """
    Service for fetching Cloud Run endpoint logs from Cloud Logging.

    Retrieves logs for Cloud Run services serving model predictions.
    """

    DEFAULT_LOG_LIMIT = 100
    LOG_RETENTION_DAYS = 7
    MAX_MESSAGE_LENGTH = 1000

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
                raise EndpointLogsServiceError(
                    "google-cloud-logging package not installed. "
                    "Install with: pip install google-cloud-logging"
                )
        return self._logging_client

    def get_logs(self, service_name: str, limit: int = None) -> Dict:
        """
        Fetch logs for a Cloud Run service.

        Args:
            service_name: Cloud Run service name
            limit: Maximum number of log entries (default: 100)

        Returns:
            Dict with structure:
            {
                'available': bool,
                'logs': [{'timestamp': str, 'severity': str, 'message': str}, ...],
                'count': int,
                'message': str  # Only if available=False
            }
        """
        limit = limit or self.DEFAULT_LOG_LIMIT

        if not service_name:
            return {
                'available': False,
                'message': 'No service name provided'
            }

        try:
            logs = self._fetch_cloud_run_logs(service_name, limit)

            if logs:
                return {
                    'available': True,
                    'logs': logs,
                    'count': len(logs)
                }

            return {
                'available': False,
                'message': 'No logs found. The endpoint may not have received any requests yet.'
            }

        except Exception as e:
            logger.exception(f"Error fetching logs for service {service_name}: {e}")
            return self._handle_error(e)

    def _fetch_cloud_run_logs(self, service_name: str, limit: int) -> List[Dict]:
        """
        Fetch logs from Cloud Logging for a Cloud Run service.

        Args:
            service_name: Cloud Run service name
            limit: Maximum log entries

        Returns:
            List of log entries
        """
        try:
            from google.cloud import logging as cloud_logging

            # Query Cloud Logging for Cloud Run revision logs
            # Match the Log Explorer query exactly:
            # resource.type = "cloud_run_revision"
            # resource.labels.service_name = "{service_name}"
            # resource.labels.location = "{region}"
            # severity>=DEFAULT
            log_filter = f'''
resource.type = "cloud_run_revision"
resource.labels.service_name = "{service_name}"
resource.labels.location = "{self.region}"
severity>=DEFAULT
'''.strip()

            logger.info(f"Fetching Cloud Run logs for service={service_name}, region={self.region}")
            logger.debug(f"Log filter: {log_filter}")

            entries = self.logging_client.list_entries(
                filter_=log_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=limit
            )

            logs = self._parse_log_entries(entries)
            return logs

        except Exception as e:
            logger.warning(f"Failed to fetch Cloud Run logs for {service_name}: {e}")
            raise

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
                # ProtobufEntry - structured logs (often audit logs)
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
                timestamp = entry.timestamp.strftime('%H:%M:%S')

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
