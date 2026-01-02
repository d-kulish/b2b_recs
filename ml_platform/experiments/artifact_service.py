"""
Artifact Service for Pipeline Artifacts

Service for fetching and parsing TFX pipeline artifacts from GCS,
including statistics, schema, and error details from Vertex AI.

Statistics and schema parsing is delegated to the tfdv-parser Cloud Run
service, which runs Python 3.10 with full TFDV support.

Implements lazy loading - artifacts are fetched on-demand when requested,
not proactively during pipeline execution.
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any

import requests
from django.conf import settings
from google.auth import default
from google.auth.transport.requests import Request

from .error_patterns import format_error_for_display

logger = logging.getLogger(__name__)

# TFDV Parser service URL (Cloud Run)
TFDV_PARSER_URL = os.environ.get(
    'TFDV_PARSER_URL',
    'https://tfdv-parser-3dmqemfmxq-lm.a.run.app'
)


class ArtifactServiceError(Exception):
    """Custom exception for artifact service errors."""
    pass


class ArtifactService:
    """
    Service for fetching and parsing TFX pipeline artifacts.

    Provides methods to:
    - Get detailed error information from Vertex AI
    - Parse TFDV statistics from GCS
    - Parse TFMD schema from GCS
    - Get training history from GCS
    """

    # GCS bucket names (must match ExperimentService)
    ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
    STAGING_BUCKET = 'b2b-recs-pipeline-staging'

    # Vertex AI configuration
    REGION = 'europe-central2'

    def __init__(self, project_id: str = None):
        """
        Initialize the artifact service.

        Args:
            project_id: GCP project ID (defaults to settings or env)
        """
        self.project_id = project_id or getattr(
            settings, 'GCP_PROJECT_ID', 'b2b-recs'
        )
        self._storage_client = None
        self._aiplatform_initialized = False

    @property
    def storage_client(self):
        """Lazy-load GCS client."""
        if self._storage_client is None:
            try:
                from google.cloud import storage
                self._storage_client = storage.Client(project=self.project_id)
            except ImportError:
                raise ArtifactServiceError(
                    "google-cloud-storage package not installed"
                )
        return self._storage_client

    def _init_aiplatform(self):
        """Initialize Vertex AI SDK."""
        if not self._aiplatform_initialized:
            try:
                from google.cloud import aiplatform
                aiplatform.init(
                    project=self.project_id,
                    location=self.REGION,
                )
                self._aiplatform_initialized = True
            except ImportError:
                raise ArtifactServiceError(
                    "google-cloud-aiplatform package not installed"
                )

    def _get_pipeline_root(self, quick_test) -> Optional[str]:
        """
        Get the pipeline root GCS path for a QuickTest.

        Args:
            quick_test: QuickTest instance

        Returns:
            Pipeline root GCS path or None
        """
        run_id = quick_test.cloud_build_run_id
        if not run_id:
            return None
        return f"gs://{self.STAGING_BUCKET}/pipeline_root/{run_id}"

    # =========================================================================
    # Error Details
    # =========================================================================

    def get_detailed_error(self, quick_test) -> Dict:
        """
        Get detailed error information for a failed QuickTest.

        Combines:
        - Stored error_message from QuickTest
        - Pattern-based classification and suggestions
        - Task-level error details from Vertex AI (if available)

        Args:
            quick_test: QuickTest instance

        Returns:
            Dict with detailed error information:
            {
                "has_error": bool,
                "failed_component": str or None,
                "error_type": str,
                "title": str,
                "suggestion": str,
                "severity": str,
                "summary": str,
                "has_stack_trace": bool,
                "full_message": str,
                "task_errors": [...] (if available from Vertex AI)
            }
        """
        from ml_platform.models import QuickTest

        # Check if there's an error
        if quick_test.status != QuickTest.STATUS_FAILED:
            return {
                'has_error': False,
                'message': 'Experiment did not fail'
            }

        # Get base error info from stored error_message
        error_message = quick_test.error_message or ''
        error_info = format_error_for_display(error_message)
        error_info['has_error'] = True

        # Try to get task-level errors from Vertex AI
        task_errors = []
        if quick_test.vertex_pipeline_job_name:
            try:
                task_errors = self._get_task_errors(quick_test.vertex_pipeline_job_name)
                if task_errors:
                    error_info['task_errors'] = task_errors

                    # If we found a specific failed task, update the component info
                    for task_error in task_errors:
                        if task_error.get('status') == 'failed':
                            if not error_info.get('failed_component'):
                                error_info['failed_component'] = task_error.get('component')
                            break

            except Exception as e:
                logger.warning(f"Failed to get task errors from Vertex AI: {e}")

        # Also include stage info from QuickTest
        if quick_test.stage_details:
            for stage in quick_test.stage_details:
                if stage.get('status') == 'failed':
                    if not error_info.get('failed_component'):
                        error_info['failed_component'] = stage.get('name')
                    break

        return error_info

    def _get_task_errors(self, pipeline_job_name: str) -> List[Dict]:
        """
        Get task-level error details from Vertex AI pipeline.

        Args:
            pipeline_job_name: Full Vertex AI pipeline job resource name

        Returns:
            List of task error details
        """
        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            pipeline_job = aiplatform.PipelineJob.get(pipeline_job_name)
            gca_resource = pipeline_job._gca_resource

            if not hasattr(gca_resource, 'job_detail') or not gca_resource.job_detail:
                return []

            task_details = gca_resource.job_detail.task_details
            if not task_details:
                return []

            task_errors = []
            component_map = {
                'bigqueryexamplegen': 'Data Loading',
                'statisticsgen': 'Statistics',
                'schemagen': 'Schema',
                'transform': 'Transform',
                'trainer': 'Training',
            }

            for task in task_details:
                task_name = task.task_name.lower() if task.task_name else ''

                # Map to display name
                component = None
                for tfx_name, display_name in component_map.items():
                    if tfx_name in task_name:
                        component = display_name
                        break

                if not component:
                    continue

                # Get task state
                task_state = task.state.name if task.state else 'UNKNOWN'

                # Map state to status
                status_map = {
                    'SUCCEEDED': 'completed',
                    'FAILED': 'failed',
                    'CANCELLED': 'cancelled',
                    'RUNNING': 'running',
                    'PENDING': 'pending',
                }
                status = status_map.get(task_state, 'unknown')

                task_info = {
                    'component': component,
                    'status': status,
                    'error_message': None,
                }

                # Try to get error message for failed tasks
                if status == 'failed' and hasattr(task, 'error') and task.error:
                    task_info['error_message'] = str(task.error.message) if task.error.message else None

                task_errors.append(task_info)

            return task_errors

        except Exception as e:
            logger.exception(f"Error fetching task errors: {e}")
            return []

    # =========================================================================
    # TFDV Parser Service Client
    # =========================================================================

    def _get_auth_token(self) -> Optional[str]:
        """
        Get identity token for Cloud Run service-to-service calls.

        Cloud Run requires an identity token (not access token) with the
        target service URL as the audience.

        For production (Cloud Run): Uses service account metadata endpoint
        For local development: Falls back to gcloud CLI
        """
        # Method 1: Try google.oauth2.id_token (works with service accounts)
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token

            auth_req = google.auth.transport.requests.Request()
            token = google.oauth2.id_token.fetch_id_token(auth_req, TFDV_PARSER_URL)
            return token
        except Exception as e:
            logger.debug(f"fetch_id_token failed (expected for user credentials): {e}")

        # Method 2: Fallback for local dev - use gcloud CLI (without audiences for user accounts)
        try:
            import subprocess
            result = subprocess.run(
                ['gcloud', 'auth', 'print-identity-token'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            else:
                logger.warning(f"gcloud identity token failed: {result.stderr}")
        except Exception as e:
            logger.warning(f"Failed to get identity token via gcloud: {e}")

        return None

    def _call_tfdv_parser(self, endpoint: str, payload: Dict) -> Optional[Dict]:
        """
        Call the tfdv-parser Cloud Run service.

        Args:
            endpoint: API endpoint (e.g., '/parse/statistics')
            payload: JSON payload to send

        Returns:
            Response JSON or None on error
        """
        url = f"{TFDV_PARSER_URL}{endpoint}"

        try:
            # Get auth token for Cloud Run authentication
            token = self._get_auth_token()
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = f'Bearer {token}'

            logger.info(f"Calling tfdv-parser: {endpoint}")
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=60  # Allow up to 60 seconds for large datasets
            )

            if response.ok:
                return response.json()
            else:
                logger.warning(f"tfdv-parser returned {response.status_code}: {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"tfdv-parser request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"tfdv-parser request failed: {e}")
            return None

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics_summary(self, quick_test, include_html: bool = False) -> Dict:
        """
        Get dataset statistics summary from TFDV artifacts via tfdv-parser service.

        Returns comprehensive statistics matching the standard TFDV visualization:

        Numeric Features:
        - count, missing%, mean, std_dev, zeros%, min, median, max
        - histogram data for visualization

        Categorical Features:
        - count, missing%, unique
        - top values with frequencies
        - value distribution for bar charts

        Args:
            quick_test: QuickTest instance
            include_html: If True, also return TFDV HTML visualization

        Returns:
            Dict with statistics summary
        """
        pipeline_root = self._get_pipeline_root(quick_test)
        if not pipeline_root:
            return {
                'available': False,
                'message': 'Pipeline artifacts not available'
            }

        # Call tfdv-parser service
        response = self._call_tfdv_parser('/parse/statistics', {
            'pipeline_root': pipeline_root,
            'include_html': include_html
        })

        if not response:
            return {
                'available': False,
                'message': 'Failed to connect to statistics parser service'
            }

        if not response.get('success'):
            return {
                'available': False,
                'message': response.get('error', 'Unknown error from parser service')
            }

        statistics = response.get('statistics', {})

        # Add HTML if requested and available
        if include_html and 'html' in response:
            statistics['html_visualization'] = response['html']

        return statistics

    def get_statistics_html(self, quick_test) -> Optional[str]:
        """
        Get TFDV HTML visualization for statistics.

        Args:
            quick_test: QuickTest instance

        Returns:
            HTML string or None
        """
        pipeline_root = self._get_pipeline_root(quick_test)
        if not pipeline_root:
            return None

        response = self._call_tfdv_parser('/parse/statistics/html', {
            'pipeline_root': pipeline_root
        })

        if response and response.get('success'):
            return response.get('html')

        return None

    # =========================================================================
    # Schema
    # =========================================================================

    def get_schema_summary(self, quick_test) -> Dict:
        """
        Get schema summary from TensorFlow Metadata artifacts via tfdv-parser service.

        Returns comprehensive schema information:
        - Feature names and types
        - Presence constraints (required/optional)
        - Domain constraints (min/max, vocabulary)
        - Value constraints

        Args:
            quick_test: QuickTest instance

        Returns:
            Dict with schema summary
        """
        pipeline_root = self._get_pipeline_root(quick_test)
        if not pipeline_root:
            return {
                'available': False,
                'message': 'Pipeline artifacts not available'
            }

        # Call tfdv-parser service
        response = self._call_tfdv_parser('/parse/schema', {
            'pipeline_root': pipeline_root
        })

        if not response:
            return {
                'available': False,
                'message': 'Failed to connect to schema parser service'
            }

        if not response.get('success'):
            return {
                'available': False,
                'message': response.get('error', 'Unknown error from parser service')
            }

        return response.get('schema', {})

    # =========================================================================
    # Training History (GCS-based)
    # =========================================================================

    def get_training_history(self, quick_test) -> Dict:
        """
        Get training history (per-epoch metrics) from GCS cache.

        Training metrics are stored in training_metrics.json by the trainer
        and cached in Django DB for fast access.

        Args:
            quick_test: QuickTest instance

        Returns:
            Dict with training history:
            {
                "available": bool,
                "message": str (if not available),
                "epochs": [...],
                "loss": {"train": [...], "val": [...]},
                "metrics": {...},
                "final_metrics": {...}
            }
        """
        from ml_platform.models import QuickTest
        from .training_cache_service import TrainingCacheService

        # Check if experiment completed
        if quick_test.status != QuickTest.STATUS_COMPLETED:
            return {
                'available': False,
                'message': 'Training history only available for completed experiments'
            }

        # Use TrainingCacheService to get history
        try:
            cache_service = TrainingCacheService()
            history = cache_service.get_training_history(quick_test)

            if history.get('available'):
                logger.info(f"Retrieved training history for {quick_test.display_name} (id={quick_test.id})")
                return history
            else:
                logger.info(f"No training history available for {quick_test.display_name} (id={quick_test.id})")
                return {
                    'available': False,
                    'message': 'No training metrics available for this experiment',
                    'final_metrics': {
                        'loss': quick_test.loss,
                        'recall_at_10': quick_test.recall_at_10,
                        'recall_at_50': quick_test.recall_at_50,
                        'recall_at_100': quick_test.recall_at_100,
                    }
                }

        except Exception as e:
            logger.exception(f"Error fetching training history for {quick_test.display_name}: {e}")
            return {
                'available': False,
                'message': f'Error retrieving training history: {str(e)}',
                'final_metrics': {
                    'loss': quick_test.loss,
                    'recall_at_10': quick_test.recall_at_10,
                    'recall_at_50': quick_test.recall_at_50,
                    'recall_at_100': quick_test.recall_at_100,
                }
            }

    # =========================================================================
    # Component Logs
    # =========================================================================

    # Map short stage names to TFX component names for log filtering
    COMPONENT_NAME_MAP = {
        'Examples': 'BigQueryExampleGen',
        'Stats': 'StatisticsGen',
        'Schema': 'SchemaGen',
        'Transform': 'Transform',
        'Train': 'Trainer',
    }

    def get_component_logs(self, quick_test, component: str, limit: int = 15) -> Dict:
        """
        Fetch recent logs for a pipeline component from Cloud Logging.

        Vertex AI pipeline component logs are stored under resource.type="ml_job"
        with the task's job_id (a numeric ID from Vertex AI task details).

        Args:
            quick_test: QuickTest instance
            component: Component name (Examples, Stats, Schema, Transform, Train)
            limit: Number of log entries to return (default 15)

        Returns:
            Dict with logs
        """
        # Validate component name
        if component not in self.COMPONENT_NAME_MAP:
            return {
                'available': False,
                'component': component,
                'message': f'Unknown component: {component}. Valid: {list(self.COMPONENT_NAME_MAP.keys())}'
            }

        # Need Vertex AI job name to query logs
        if not quick_test.vertex_pipeline_job_name:
            return {
                'available': False,
                'component': component,
                'message': 'Pipeline not yet submitted to Vertex AI'
            }

        try:
            from google.cloud import logging as cloud_logging
            from google.cloud import aiplatform
            from datetime import datetime, timedelta, timezone

            # Get the TFX component name
            tfx_component = self.COMPONENT_NAME_MAP[component]

            # First, get the task job_id from Vertex AI pipeline job details
            task_job_id = self._get_task_job_id(quick_test.vertex_pipeline_job_name, tfx_component)

            if not task_job_id:
                # Fall back to pipeline-level logs
                return self._get_pipeline_level_logs(quick_test, component, tfx_component, limit)

            # Initialize Cloud Logging client
            client = cloud_logging.Client(project=self.project_id)

            # Build the log filter for ml_job resource type
            # Include timestamp filter to find older logs (last 7 days)
            start_time = datetime.now(timezone.utc) - timedelta(days=7)
            log_filter = f'''
                resource.type="ml_job"
                resource.labels.job_id="{task_job_id}"
                timestamp>="{start_time.isoformat()}"
            '''.strip()

            logger.info(f"Fetching logs for {component} with ml_job filter, job_id={task_job_id}")

            # Query logs
            logs = []
            entries = client.list_entries(
                filter_=log_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=limit
            )

            for entry in entries:
                # Extract message from either textPayload or jsonPayload
                if hasattr(entry, 'text_payload') and entry.text_payload:
                    message = entry.text_payload
                elif hasattr(entry, 'json_payload') and entry.json_payload:
                    message = entry.json_payload.get('message', str(entry.json_payload))
                else:
                    message = str(entry.payload)

                # Format timestamp
                timestamp = entry.timestamp.strftime('%H:%M:%S') if entry.timestamp else ''

                # Get severity
                severity = entry.severity if hasattr(entry, 'severity') else 'INFO'

                logs.append({
                    'timestamp': timestamp,
                    'severity': str(severity),
                    'message': message[:500]  # Truncate long messages
                })

            # Reverse to show oldest first (more natural reading order)
            logs.reverse()

            return {
                'available': True,
                'component': component,
                'task_job_id': task_job_id,
                'logs': logs,
                'count': len(logs)
            }

        except ImportError as e:
            logger.warning(f"Required package not installed: {e}")
            return {
                'available': False,
                'component': component,
                'message': 'Required packages not available.'
            }
        except Exception as e:
            error_str = str(e)
            logger.exception(f"Error fetching logs for {component}: {e}")

            # Provide friendly messages for common errors
            if 'Permission denied' in error_str or '403' in error_str:
                return {
                    'available': False,
                    'component': component,
                    'message': 'Logs access denied. Grant roles/logging.viewer to your service account.'
                }
            elif 'not found' in error_str.lower() or '404' in error_str:
                return {
                    'available': False,
                    'component': component,
                    'message': 'No logs found for this pipeline run.'
                }

            return {
                'available': False,
                'component': component,
                'message': f'Failed to fetch logs: {error_str[:100]}'
            }

    def _get_task_job_id(self, pipeline_job_name: str, component_name: str) -> str:
        """
        Get the task job_id for a specific component from Vertex AI pipeline job details.

        Args:
            pipeline_job_name: Full resource name of the pipeline job
            component_name: TFX component name (e.g., 'Transform', 'Trainer')

        Returns:
            The numeric job_id string, or None if not found
        """
        try:
            from google.cloud import aiplatform

            # Extract location from pipeline job name
            # Format: projects/{project}/locations/{location}/pipelineJobs/{job_id}
            parts = pipeline_job_name.split('/')
            location = parts[3] if len(parts) > 3 else 'us-central1'

            aiplatform.init(project=self.project_id, location=location)

            # Get the pipeline job
            pipeline_job = aiplatform.PipelineJob.get(pipeline_job_name)

            # Access task details
            if not hasattr(pipeline_job, '_gca_resource') or not pipeline_job._gca_resource.job_detail:
                return None

            task_details = pipeline_job._gca_resource.job_detail.task_details

            # Find the task matching the component name
            component_lower = component_name.lower()
            for task in task_details:
                task_name_lower = task.task_name.lower() if task.task_name else ''

                if component_lower in task_name_lower:
                    # Extract job_id from executor_detail
                    # TFX components use container_detail.main_job
                    if task.executor_detail:
                        job_resource = None

                        # Try container_detail.main_job first (TFX components)
                        if task.executor_detail.container_detail:
                            job_resource = task.executor_detail.container_detail.main_job

                        # Fallback to custom_job_detail.job
                        if not job_resource and task.executor_detail.custom_job_detail:
                            job_resource = task.executor_detail.custom_job_detail.job

                        if job_resource:
                            # Format: projects/{project}/locations/{location}/customJobs/{job_id}
                            job_id = job_resource.split('/')[-1]
                            logger.info(f"Found task job_id for {component_name}: {job_id}")
                            return job_id

            logger.warning(f"No task job_id found for component {component_name}")
            return None

        except Exception as e:
            logger.warning(f"Error getting task job_id for {component_name}: {e}")
            return None

    def _get_pipeline_level_logs(self, quick_test, component: str, tfx_component: str, limit: int) -> Dict:
        """
        Fallback: Get pipeline-level logs when task job_id is not available.
        """
        try:
            from google.cloud import logging as cloud_logging

            client = cloud_logging.Client(project=self.project_id)
            job_id = quick_test.vertex_pipeline_job_name.split('/')[-1]

            # Query pipeline-level logs
            log_filter = f'''
                resource.type="aiplatform.googleapis.com/PipelineJob"
                resource.labels.pipeline_job_id="{job_id}"
            '''.strip()

            logger.info(f"Fetching pipeline-level logs for {component}")

            logs = []
            entries = client.list_entries(
                filter_=log_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=limit
            )

            for entry in entries:
                if hasattr(entry, 'text_payload') and entry.text_payload:
                    message = entry.text_payload
                elif hasattr(entry, 'json_payload') and entry.json_payload:
                    message = entry.json_payload.get('message', str(entry.json_payload))
                else:
                    message = str(entry.payload)

                timestamp = entry.timestamp.strftime('%H:%M:%S') if entry.timestamp else ''
                severity = entry.severity if hasattr(entry, 'severity') else 'INFO'

                logs.append({
                    'timestamp': timestamp,
                    'severity': str(severity),
                    'message': message[:500]
                })

            logs.reverse()

            return {
                'available': True,
                'component': component,
                'logs': logs,
                'count': len(logs),
                'note': 'Showing pipeline-level logs (task logs not available)'
            }

        except Exception as e:
            logger.exception(f"Error fetching pipeline-level logs: {e}")
            return {
                'available': False,
                'component': component,
                'message': f'No logs available for {component}'
            }

    # =========================================================================
    # Combined Artifact Data
    # =========================================================================

    def get_all_artifacts(self, quick_test) -> Dict:
        """
        Get all available artifact data for a QuickTest.

        Combines errors, statistics, schema, and training history
        into a single response.

        Args:
            quick_test: QuickTest instance

        Returns:
            Dict with all artifact data
        """
        return {
            'error': self.get_detailed_error(quick_test),
            'statistics': self.get_statistics_summary(quick_test),
            'schema': self.get_schema_summary(quick_test),
            'training_history': self.get_training_history(quick_test),
        }
