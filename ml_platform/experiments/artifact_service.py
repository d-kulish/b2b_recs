"""
Artifact Service for Pipeline Artifacts

Service for fetching and parsing TFX pipeline artifacts from GCS,
including statistics, schema, and error details from Vertex AI.

Implements lazy loading - artifacts are fetched on-demand when requested,
not proactively during pipeline execution.
"""
import json
import logging
from typing import Dict, List, Optional, Any

from django.conf import settings

from .error_patterns import format_error_for_display

logger = logging.getLogger(__name__)


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
    - Get training history (placeholder for MLflow integration)
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
    # Statistics
    # =========================================================================

    def get_statistics_summary(self, quick_test) -> Dict:
        """
        Get dataset statistics summary from TFDV artifacts.

        Parses the StatisticsGen output to extract:
        - Total example count
        - Feature count
        - Per-feature statistics (type, unique values, missing %, etc.)

        Args:
            quick_test: QuickTest instance

        Returns:
            Dict with statistics summary:
            {
                "available": bool,
                "num_examples": int,
                "num_features": int,
                "avg_missing_ratio": float,
                "features": [
                    {
                        "name": str,
                        "type": str,
                        "num_unique": int or None,
                        "missing_pct": float,
                        "min": float or None,
                        "max": float or None,
                        "mean": float or None,
                    },
                    ...
                ]
            }
        """
        pipeline_root = self._get_pipeline_root(quick_test)
        if not pipeline_root:
            return {
                'available': False,
                'message': 'Pipeline artifacts not available'
            }

        try:
            # TFDV statistics are stored in the StatisticsGen component output
            # Path pattern: {pipeline_root}/StatisticsGen/statistics/{execution_id}/Split-train/FeatureStats.pb
            # We need to find the actual path by listing the directory

            stats = self._load_tfdv_statistics(pipeline_root)
            if not stats:
                return {
                    'available': False,
                    'message': 'Statistics not yet available. Pipeline may still be running.'
                }

            return self._parse_statistics(stats)

        except Exception as e:
            logger.exception(f"Error getting statistics: {e}")
            return {
                'available': False,
                'message': f'Failed to load statistics: {str(e)}'
            }

    def _load_tfdv_statistics(self, pipeline_root: str) -> Optional[Any]:
        """
        Load TFDV statistics from GCS.

        Uses tensorflow_metadata to parse statistics proto directly
        (without requiring full tensorflow_data_validation which needs TensorFlow).

        Args:
            pipeline_root: Pipeline root GCS path

        Returns:
            DatasetFeatureStatisticsList proto or None
        """
        try:
            from tensorflow_metadata.proto.v0 import statistics_pb2
        except ImportError:
            logger.warning("tensorflow_metadata not installed")
            return None

        # Parse bucket and prefix from pipeline_root
        # Format: gs://bucket/path/to/root
        path_parts = pipeline_root.replace('gs://', '').split('/', 1)
        bucket_name = path_parts[0]
        prefix = path_parts[1] if len(path_parts) > 1 else ''

        bucket = self.storage_client.bucket(bucket_name)

        # Vertex AI creates an execution_id folder layer, so actual path is:
        # {prefix}/{execution_id}/StatisticsGen/statistics/Split-train/FeatureStats.pb
        # We search from the pipeline_root and look for StatisticsGen in the path

        # List all blobs under pipeline_root (limited to avoid huge lists)
        blobs = list(bucket.list_blobs(prefix=prefix, max_results=500))

        # Find FeatureStats.pb file in StatisticsGen output
        stats_blob = None
        for blob in blobs:
            # Look for the statistics file pattern
            if ('StatisticsGen' in blob.name and
                'statistics' in blob.name and
                'Split-train' in blob.name and
                blob.name.endswith('FeatureStats.pb')):
                stats_blob = blob
                logger.info(f"Found statistics blob: {blob.name}")
                break

        if not stats_blob:
            # Fallback: look for any FeatureStats.pb in the prefix
            for blob in blobs:
                if blob.name.endswith('FeatureStats.pb'):
                    stats_blob = blob
                    logger.info(f"Found statistics blob (fallback): {blob.name}")
                    break

        if not stats_blob:
            logger.info(f"No statistics file found under {prefix}. Found {len(blobs)} blobs total.")
            # Log some of the blob names for debugging
            if blobs:
                sample_names = [b.name for b in blobs[:10]]
                logger.info(f"Sample blob names: {sample_names}")
            return None

        # Download and parse the protobuf directly
        logger.info(f"Loading statistics from gs://{bucket_name}/{stats_blob.name}")

        try:
            # Download raw bytes
            stats_bytes = stats_blob.download_as_bytes()

            # Parse as DatasetFeatureStatisticsList proto
            stats = statistics_pb2.DatasetFeatureStatisticsList()
            stats.ParseFromString(stats_bytes)

            logger.info(f"Successfully parsed statistics with {len(stats.datasets)} datasets")
            return stats

        except Exception as e:
            logger.warning(f"Failed to parse statistics proto: {e}")
            return None

    def _parse_statistics(self, stats) -> Dict:
        """
        Parse TFDV statistics into summary format.

        Args:
            stats: TFDV DatasetFeatureStatisticsList

        Returns:
            Summary dict
        """
        if not stats or not stats.datasets:
            return {
                'available': False,
                'message': 'No statistics data found'
            }

        dataset = stats.datasets[0]
        num_examples = dataset.num_examples

        features = []
        total_missing_ratio = 0

        for feature in dataset.features:
            # Safely extract feature name
            try:
                feature_path = getattr(feature, 'path', None)
                if feature_path and feature_path.step:
                    feature_name = feature_path.step[0]
                else:
                    feature_name = getattr(feature, 'name', 'unknown')
            except (AttributeError, IndexError):
                feature_name = 'unknown'

            # Determine feature type and extract stats
            feature_info = {
                'name': feature_name,
                'type': 'UNKNOWN',
                'num_unique': None,
                'missing_pct': 0,
                'min': None,
                'max': None,
                'mean': None,
            }

            # Calculate missing percentage
            if num_examples > 0:
                missing_count = getattr(feature, 'num_missing', 0) or 0
                feature_info['missing_pct'] = round((missing_count / num_examples) * 100, 2)
                total_missing_ratio += feature_info['missing_pct']

            # Check for numeric stats - wrap in try-except for proto compatibility
            try:
                if feature.HasField('num_stats'):
                    feature_info['type'] = 'NUMERIC'
                    num_stats = feature.num_stats
                    feature_info['min'] = round(num_stats.min, 4) if num_stats.min != float('inf') else None
                    feature_info['max'] = round(num_stats.max, 4) if num_stats.max != float('-inf') else None
                    feature_info['mean'] = round(num_stats.mean, 4) if num_stats.mean else None

                # Check for string stats
                elif feature.HasField('string_stats'):
                    feature_info['type'] = 'CATEGORICAL'
                    string_stats = feature.string_stats
                    feature_info['num_unique'] = string_stats.unique

                # Check for bytes stats
                elif feature.HasField('bytes_stats'):
                    feature_info['type'] = 'BYTES'
            except (ValueError, AttributeError):
                # HasField may fail for certain proto structures
                pass

            features.append(feature_info)

        # Calculate average missing ratio
        avg_missing = total_missing_ratio / len(features) if features else 0

        return {
            'available': True,
            'num_examples': num_examples,
            'num_features': len(features),
            'avg_missing_ratio': round(avg_missing, 2),
            'features': features[:50],  # Limit to 50 features for UI
            'total_features': len(features),
            'truncated': len(features) > 50
        }

    # =========================================================================
    # Schema
    # =========================================================================

    def get_schema_summary(self, quick_test) -> Dict:
        """
        Get schema summary from TensorFlow Metadata artifacts.

        Parses the SchemaGen output to extract:
        - Feature names
        - Feature types
        - Presence constraints (required/optional)

        Args:
            quick_test: QuickTest instance

        Returns:
            Dict with schema summary:
            {
                "available": bool,
                "features": [
                    {
                        "name": str,
                        "type": str,
                        "required": bool,
                        "description": str or None,
                    },
                    ...
                ]
            }
        """
        pipeline_root = self._get_pipeline_root(quick_test)
        if not pipeline_root:
            return {
                'available': False,
                'message': 'Pipeline artifacts not available'
            }

        try:
            schema = self._load_schema(pipeline_root)
            if not schema:
                return {
                    'available': False,
                    'message': 'Schema not yet available. Pipeline may still be running.'
                }

            return self._parse_schema(schema)

        except Exception as e:
            logger.exception(f"Error getting schema: {e}")
            return {
                'available': False,
                'message': f'Failed to load schema: {str(e)}'
            }

    def _load_schema(self, pipeline_root: str) -> Optional[Any]:
        """
        Load TensorFlow Metadata schema from GCS.

        Args:
            pipeline_root: Pipeline root GCS path

        Returns:
            Schema proto or None
        """
        try:
            from tensorflow_metadata.proto.v0 import schema_pb2
            from google.protobuf import text_format
        except ImportError:
            logger.warning("tensorflow_metadata not installed")
            return None

        # Parse bucket and prefix
        path_parts = pipeline_root.replace('gs://', '').split('/', 1)
        bucket_name = path_parts[0]
        prefix = path_parts[1] if len(path_parts) > 1 else ''

        bucket = self.storage_client.bucket(bucket_name)

        # Vertex AI creates an execution_id folder layer, so actual path is:
        # {prefix}/{execution_id}/SchemaGen/schema/schema.pbtxt
        # We search from the pipeline_root and look for SchemaGen in the path

        # List all blobs under pipeline_root
        blobs = list(bucket.list_blobs(prefix=prefix, max_results=500))

        # Find schema.pbtxt file in SchemaGen output
        schema_blob = None
        for blob in blobs:
            if ('SchemaGen' in blob.name and
                'schema' in blob.name and
                blob.name.endswith('schema.pbtxt')):
                schema_blob = blob
                logger.info(f"Found schema blob: {blob.name}")
                break

        if not schema_blob:
            # Fallback: look for any schema.pbtxt in the prefix
            for blob in blobs:
                if blob.name.endswith('schema.pbtxt'):
                    schema_blob = blob
                    logger.info(f"Found schema blob (fallback): {blob.name}")
                    break

        if not schema_blob:
            logger.info(f"No schema file found under {prefix}. Found {len(blobs)} blobs total.")
            return None

        # Download and parse
        logger.info(f"Loading schema from gs://{bucket_name}/{schema_blob.name}")
        content = schema_blob.download_as_text()

        schema = schema_pb2.Schema()
        text_format.Parse(content, schema)

        return schema

    def _parse_schema(self, schema) -> Dict:
        """
        Parse TensorFlow Metadata schema into summary format.

        Args:
            schema: Schema proto

        Returns:
            Summary dict
        """
        from tensorflow_metadata.proto.v0 import schema_pb2

        features = []

        for feature in schema.feature:
            # Safely get description - may not exist on all proto versions
            description = getattr(feature, 'description', None)
            if description == '':
                description = None

            feature_info = {
                'name': feature.name,
                'type': 'UNKNOWN',
                'required': False,
                'description': description,
            }

            # Get type - safely access in case proto version differs
            type_map = {
                schema_pb2.INT: 'INT64',
                schema_pb2.FLOAT: 'FLOAT',
                schema_pb2.BYTES: 'STRING',
            }
            feature_type = getattr(feature, 'type', None)
            if feature_type is not None:
                feature_info['type'] = type_map.get(feature_type, 'UNKNOWN')
            else:
                feature_info['type'] = 'UNKNOWN'

            # Check if required - safely handle potential proto differences
            try:
                if feature.HasField('presence'):
                    feature_info['required'] = feature.presence.min_fraction >= 1.0
            except (ValueError, AttributeError):
                # HasField may fail for certain field types or proto versions
                pass

            features.append(feature_info)

        return {
            'available': True,
            'num_features': len(features),
            'features': features[:50],  # Limit for UI
            'total_features': len(features),
            'truncated': len(features) > 50
        }

    # =========================================================================
    # Training History (Placeholder for MLflow)
    # =========================================================================

    def get_training_history(self, quick_test) -> Dict:
        """
        Get training history (per-epoch metrics).

        This is a placeholder for future MLflow integration.
        Currently returns a placeholder response.

        Args:
            quick_test: QuickTest instance

        Returns:
            Dict with training history or placeholder:
            {
                "available": bool,
                "message": str (if not available),
                "epochs": [...],
                "loss": [...],
                "metrics": {...}
            }
        """
        from ml_platform.models import QuickTest

        # Check if experiment completed
        if quick_test.status != QuickTest.STATUS_COMPLETED:
            return {
                'available': False,
                'message': 'Training history only available for completed experiments'
            }

        # Return placeholder for MLflow integration
        # TODO: Implement MLflow integration to fetch actual per-epoch metrics
        return {
            'available': False,
            'placeholder': True,
            'message': 'Training curves will be available when MLflow integration is complete',
            'final_metrics': {
                'loss': quick_test.loss,
                'recall_at_10': quick_test.recall_at_10,
                'recall_at_50': quick_test.recall_at_50,
                'recall_at_100': quick_test.recall_at_100,
            }
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
