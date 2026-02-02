"""
Pipeline Logs Service

Dedicated service for fetching pipeline component logs from Cloud Logging.
Provides logs for individual TFX components running in Vertex AI pipelines.

Design:
- Primary: Query pipeline-level logs (more reliable, always available)
- Fallback: Query task-specific logs (more specific, but requires job_id extraction)
- Manual refresh only (no polling)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class PipelineLogsServiceError(Exception):
    """Custom exception for pipeline logs service errors."""
    pass


class PipelineLogsService:
    """
    Service for fetching pipeline component logs from Cloud Logging.

    Retrieves logs for TFX components running in Vertex AI pipelines.
    Supports both pipeline-level and task-specific log queries.
    """

    # Mapping from UI component names to TFX component names
    COMPONENT_NAME_MAP = {
        'Examples': 'BigQueryExampleGen',
        'Stats': 'StatisticsGen',
        'Schema': 'SchemaGen',
        'Transform': 'Transform',
        'Train': 'Trainer',
    }

    # Default configuration
    DEFAULT_LOG_LIMIT = 100
    LOG_RETENTION_DAYS = 30  # Match Cloud Logging default retention
    MAX_MESSAGE_LENGTH = 1000

    def __init__(self, project_id: str = None):
        """
        Initialize the service.

        Args:
            project_id: GCP project ID (defaults to settings.GCP_PROJECT_ID)
        """
        self.project_id = project_id or getattr(settings, 'GCP_PROJECT_ID', 'b2b-recs')
        self._logging_client = None
        self._aiplatform_initialized = False

    @property
    def logging_client(self):
        """Lazy-load Cloud Logging client."""
        if self._logging_client is None:
            try:
                from google.cloud import logging as cloud_logging
                self._logging_client = cloud_logging.Client(project=self.project_id)
            except ImportError:
                raise PipelineLogsServiceError(
                    "google-cloud-logging package not installed. "
                    "Install with: pip install google-cloud-logging"
                )
        return self._logging_client

    # =========================================================================
    # Public API
    # =========================================================================

    def get_component_logs(self, quick_test, component: str, limit: int = None) -> Dict:
        """
        Fetch logs for a specific pipeline component.

        Args:
            quick_test: QuickTest instance with pipeline metadata
            component: Component name (Examples, Stats, Schema, Transform, Train)
            limit: Maximum number of log entries (default: 100)

        Returns:
            Dict with structure:
            {
                'available': bool,
                'component': str,
                'logs': [{'timestamp': str, 'severity': str, 'message': str}, ...],
                'count': int,
                'source': str,  # 'task' or 'pipeline'
                'message': str  # Only if available=False
            }
        """
        limit = limit or self.DEFAULT_LOG_LIMIT

        # Validate component name
        if component not in self.COMPONENT_NAME_MAP:
            return {
                'available': False,
                'component': component,
                'message': f"Unknown component: {component}. Valid components: {', '.join(self.COMPONENT_NAME_MAP.keys())}"
            }

        # Check if pipeline has been submitted
        if not quick_test.vertex_pipeline_job_name:
            status_msg = self._get_status_message(quick_test)
            return {
                'available': False,
                'component': component,
                'message': status_msg
            }

        # Try to get logs
        try:
            # First, try task-specific logs (more detailed)
            task_logs = self._get_task_logs(
                quick_test.vertex_pipeline_job_name,
                component,
                limit
            )

            if task_logs:
                return {
                    'available': True,
                    'component': component,
                    'logs': task_logs,
                    'count': len(task_logs),
                    'source': 'task'
                }

            # Fall back to pipeline-level logs
            pipeline_logs = self._get_pipeline_logs(
                quick_test.vertex_pipeline_job_name,
                component,
                limit
            )

            if pipeline_logs:
                return {
                    'available': True,
                    'component': component,
                    'logs': pipeline_logs,
                    'count': len(pipeline_logs),
                    'source': 'pipeline',
                    'note': 'Showing pipeline-level logs (task-specific logs not available)'
                }

            # No logs found
            return {
                'available': False,
                'component': component,
                'message': self._get_no_logs_message(quick_test, component)
            }

        except Exception as e:
            logger.exception(f"Error fetching logs for {component}: {e}")
            return self._handle_error(component, e)

    # =========================================================================
    # Private Methods - Log Fetching
    # =========================================================================

    def _get_task_logs(self, pipeline_job_name: str, component: str, limit: int) -> List[Dict]:
        """
        Fetch task-specific logs using the task's job_id.

        Args:
            pipeline_job_name: Full Vertex AI pipeline job resource name
            component: UI component name
            limit: Maximum log entries

        Returns:
            List of log entries, or empty list if not available
        """
        # Extract task job_id from Vertex AI
        task_job_id = self._extract_task_job_id(pipeline_job_name, component)

        if not task_job_id:
            logger.debug(f"No task job_id found for {component}, falling back to pipeline logs")
            return []

        # Query Cloud Logging for task-specific logs
        try:
            from google.cloud import logging as cloud_logging

            start_time = datetime.now(timezone.utc) - timedelta(days=self.LOG_RETENTION_DAYS)
            log_filter = f'''
                resource.type="ml_job"
                resource.labels.job_id="{task_job_id}"
                timestamp>="{start_time.isoformat()}"
            '''.strip()

            logger.info(f"Fetching task logs for {component} with job_id={task_job_id}")

            entries = self.logging_client.list_entries(
                filter_=log_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=limit
            )

            logs = self._parse_log_entries(entries)
            return logs  # Newest first

        except Exception as e:
            logger.warning(f"Failed to fetch task logs for {component}: {e}")
            return []

    def _get_pipeline_logs(self, pipeline_job_name: str, component: str, limit: int) -> List[Dict]:
        """
        Fetch pipeline-level logs as fallback.

        Args:
            pipeline_job_name: Full Vertex AI pipeline job resource name
            component: UI component name (used for filtering)
            limit: Maximum log entries

        Returns:
            List of log entries
        """
        try:
            from google.cloud import logging as cloud_logging

            # Extract job_id from resource name
            # Format: projects/{project}/locations/{location}/pipelineJobs/{job_id}
            job_id = pipeline_job_name.split('/')[-1]
            tfx_component = self.COMPONENT_NAME_MAP.get(component, component)

            start_time = datetime.now(timezone.utc) - timedelta(days=self.LOG_RETENTION_DAYS)

            # Query pipeline-level logs, filtered by component name in text
            log_filter = f'''
                resource.type="aiplatform.googleapis.com/PipelineJob"
                resource.labels.pipeline_job_id="{job_id}"
                timestamp>="{start_time.isoformat()}"
            '''.strip()

            logger.info(f"Fetching pipeline logs for {component} (job_id={job_id})")

            entries = self.logging_client.list_entries(
                filter_=log_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=limit * 2  # Fetch more, then filter
            )

            # Parse and filter by component name
            logs = []
            tfx_lower = tfx_component.lower()

            for entry in entries:
                log_entry = self._parse_single_entry(entry)
                if log_entry:
                    # Include if message mentions the component
                    if tfx_lower in log_entry['message'].lower():
                        logs.append(log_entry)
                        if len(logs) >= limit:
                            break

            return logs  # Newest first

        except Exception as e:
            logger.warning(f"Failed to fetch pipeline logs for {component}: {e}")
            return []

    def _extract_task_job_id(self, pipeline_job_name: str, component: str) -> Optional[str]:
        """
        Extract the task's job_id from Vertex AI pipeline job details.

        Args:
            pipeline_job_name: Full pipeline job resource name
            component: UI component name

        Returns:
            The numeric job_id string, or None if not found
        """
        try:
            from google.cloud import aiplatform

            # Extract location from pipeline job name
            # Format: projects/{project}/locations/{location}/pipelineJobs/{job_id}
            parts = pipeline_job_name.split('/')
            if len(parts) < 4:
                logger.warning(f"Invalid pipeline job name format: {pipeline_job_name}")
                return None

            location = parts[3]

            # Initialize Vertex AI SDK
            if not self._aiplatform_initialized:
                aiplatform.init(project=self.project_id, location=location)
                self._aiplatform_initialized = True

            # Get the pipeline job
            pipeline_job = aiplatform.PipelineJob.get(pipeline_job_name)

            # Access task details (using internal API - may break in future SDK versions)
            if not hasattr(pipeline_job, '_gca_resource'):
                logger.debug("Pipeline job doesn't have _gca_resource attribute")
                return None

            job_detail = pipeline_job._gca_resource.job_detail
            if not job_detail or not job_detail.task_details:
                logger.debug("No task details available yet")
                return None

            # Find the task matching the component
            tfx_component = self.COMPONENT_NAME_MAP.get(component, component)
            component_lower = tfx_component.lower()

            for task in job_detail.task_details:
                task_name = getattr(task, 'task_name', '') or ''
                if component_lower in task_name.lower():
                    # Extract job_id from executor_detail
                    executor = getattr(task, 'executor_detail', None)
                    if not executor:
                        continue

                    job_resource = None

                    # Try container_detail first (standard TFX components)
                    container = getattr(executor, 'container_detail', None)
                    if container:
                        job_resource = getattr(container, 'main_job', None)

                    # Fall back to custom_job_detail
                    if not job_resource:
                        custom_job = getattr(executor, 'custom_job_detail', None)
                        if custom_job:
                            job_resource = getattr(custom_job, 'job', None)

                    if job_resource:
                        # Extract job_id from resource name
                        # Format: projects/{project}/locations/{location}/customJobs/{job_id}
                        job_id = job_resource.split('/')[-1]
                        logger.info(f"Found task job_id for {component}: {job_id}")
                        return job_id

            logger.debug(f"No matching task found for component {component}")
            return None

        except Exception as e:
            logger.warning(f"Error extracting task job_id for {component}: {e}")
            return None

    # =========================================================================
    # Private Methods - Helpers
    # =========================================================================

    def _parse_log_entries(self, entries) -> List[Dict]:
        """Parse Cloud Logging entries into structured format."""
        logs = []
        for entry in entries:
            log_entry = self._parse_single_entry(entry)
            if log_entry:
                logs.append(log_entry)
        return logs

    def _parse_single_entry(self, entry) -> Optional[Dict]:
        """Parse a single Cloud Logging entry."""
        try:
            # Extract message from text_payload or json_payload
            message = None
            if hasattr(entry, 'text_payload') and entry.text_payload:
                message = entry.text_payload
            elif hasattr(entry, 'json_payload') and entry.json_payload:
                message = entry.json_payload.get('message', str(entry.json_payload))
            else:
                payload = getattr(entry, 'payload', None)
                if payload:
                    message = str(payload)

            if not message:
                return None

            # Format timestamp
            timestamp = ''
            if hasattr(entry, 'timestamp') and entry.timestamp:
                timestamp = entry.timestamp.strftime('%H:%M:%S')

            # Get severity
            severity = 'INFO'
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

    def _get_status_message(self, quick_test) -> str:
        """Get a user-friendly message based on experiment status."""
        status = getattr(quick_test, 'status', 'unknown')

        if status == 'submitting':
            return "Pipeline is being submitted. Logs will be available once execution starts."
        elif status == 'running':
            return "Pipeline is starting up. Logs should appear shortly."
        elif status == 'cancelled':
            return "Pipeline was cancelled before logs were generated."
        else:
            return "Pipeline has not been submitted to Vertex AI yet."

    def _get_no_logs_message(self, quick_test, component: str) -> str:
        """Get a message explaining why no logs were found."""
        status = getattr(quick_test, 'status', 'unknown')
        current_stage = getattr(quick_test, 'current_stage', '')

        # Check if this component has run yet
        stage_order = ['Compile', 'Examples', 'Stats', 'Schema', 'Transform', 'Train']
        component_index = stage_order.index(component) if component in stage_order else -1
        current_index = stage_order.index(current_stage) if current_stage in stage_order else -1

        if current_index >= 0 and component_index > current_index:
            return f"The {component} stage has not started yet. Currently running: {current_stage}"
        elif status == 'running':
            return f"No logs available for {component} yet. The component may still be initializing."
        else:
            return f"No logs found for {component}. Logs may have expired or the component didn't generate any output."

    def _handle_error(self, component: str, error: Exception) -> Dict:
        """Handle errors and return user-friendly messages."""
        error_str = str(error)

        if 'Permission denied' in error_str or '403' in error_str:
            return {
                'available': False,
                'component': component,
                'message': "Access denied. The service account may need 'roles/logging.viewer' permission."
            }
        elif 'not found' in error_str.lower() or '404' in error_str:
            return {
                'available': False,
                'component': component,
                'message': "Logs not found. They may have expired or been deleted."
            }
        else:
            return {
                'available': False,
                'component': component,
                'message': f"Failed to fetch logs: {error_str[:100]}"
            }
