"""
Training Domain Services

Service layer for managing full-scale training runs on Vertex AI.
Handles creation, status tracking, cancellation, and deletion of training runs.

Key differences from ExperimentService (Quick Tests):
- 8 pipeline stages (vs 6): Compile, Examples, Stats, Schema, Transform, Train, Evaluate, Push
- GPU support with multi-GPU strategy
- Model blessing via Evaluator component
- Model Registry integration via Pusher component
- Extended training callbacks (early stopping, LR scheduling, checkpointing)
"""
import base64
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import TrainingRun

logger = logging.getLogger(__name__)


class TrainingServiceError(Exception):
    """Exception raised by TrainingService operations."""
    pass


class TrainingService:
    """
    Service class for managing training runs.

    Provides full lifecycle management for training pipelines:
    - Create training run records
    - Submit TFX pipelines to Vertex AI via Cloud Build
    - Monitor status and extract results
    - Cancel and delete training runs
    """

    # GCS bucket names (same as ExperimentService for consistency)
    ARTIFACTS_BUCKET = 'b2b-recs-training-artifacts'
    STAGING_BUCKET = 'b2b-recs-pipeline-staging'

    # Vertex AI configuration
    # NOTE: Data infrastructure (BigQuery, GCS, Cloud SQL) is in europe-central2
    REGION = 'europe-central2'

    # GPU Training Region Configuration
    # ===============================
    # IMPORTANT: Vertex AI custom training does NOT support GPUs in all regions!
    # europe-central2 (Warsaw) does NOT support GPU training for custom jobs,
    # even though GPU quota can be approved and Compute Engine has GPUs available.
    #
    # The Vertex AI locations documentation marks T4/L4 GPUs in europe-central2
    # with † (dagger), meaning "not available for training" - only for prediction.
    #
    # Therefore, GPU training jobs must run in a different region:
    # - europe-west4 (Netherlands): Verified working, 2x T4 quota approved
    # - Data is read cross-region from europe-central2 BigQuery/GCS (works fine)
    #
    # See: https://docs.cloud.google.com/vertex-ai/docs/general/locations
    # See: docs/training_full.md Section 11 for validation details
    GPU_TRAINING_REGION = 'europe-west4'

    # Dataflow Region Configuration
    # =============================
    # Dataflow jobs (StatisticsGen, Transform) do NOT need GPUs and should run
    # in the same region as the data to minimize latency and avoid resource
    # exhaustion in GPU-heavy regions like europe-west4.
    DATAFLOW_REGION = 'europe-central2'

    PIPELINE_DISPLAY_NAME_PREFIX = 'training'

    # 8 stages for Training (vs 6 for Experiments)
    # Includes Evaluator and Pusher components
    # NOTE: Stage names must match TFX_PIPELINE.components 'id' in pipeline_dag.js
    STAGE_ORDER = ['Compile', 'Examples', 'Stats', 'Schema', 'Transform', 'Train', 'Evaluator', 'Pusher']

    # Mapping from TFX component names to display names
    # NOTE: Display names must match TFX_PIPELINE.components 'id' in pipeline_dag.js
    STAGE_NAME_MAP = {
        'bigqueryexamplegen': 'Examples',
        'statisticsgen': 'Stats',
        'schemagen': 'Schema',
        'transform': 'Transform',
        'trainer': 'Train',
        'evaluator': 'Evaluator',
        'pusher': 'Pusher',
    }

    def __init__(self, ml_model):
        """
        Initialize TrainingService for a specific model endpoint.

        Args:
            ml_model: ModelEndpoint instance
        """
        self.ml_model = ml_model
        self.project_id = ml_model.gcp_project_id or getattr(
            settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID', 'b2b-recs')
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
                raise TrainingServiceError(
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
                    staging_bucket=f'gs://{self.STAGING_BUCKET}'
                )
                self._aiplatform_initialized = True
            except ImportError:
                raise TrainingServiceError(
                    "google-cloud-aiplatform package not installed"
                )

    def create_training_run(
        self,
        name: str,
        dataset,
        feature_config,
        model_config,
        description: str = '',
        base_experiment=None,
        training_params: dict = None,
        gpu_config: dict = None,
        evaluator_config: dict = None,
        deployment_config: dict = None,
        created_by=None,
    ) -> TrainingRun:
        """
        Create a new training run record.

        This creates the database record but does not submit the training pipeline.
        Pipeline submission will be implemented in Phase 2.

        Args:
            name: Model name in Vertex AI Model Registry
            dataset: Dataset instance
            feature_config: FeatureConfig instance
            model_config: ModelConfig instance
            description: Optional description
            base_experiment: Optional QuickTest experiment this is based on
            training_params: Training hyperparameters
            gpu_config: GPU configuration
            evaluator_config: Evaluator configuration
            deployment_config: Deployment configuration
            created_by: User who created the training run

        Returns:
            Created TrainingRun instance
        """
        with transaction.atomic():
            # Get next run number for this model endpoint
            last_run = TrainingRun.objects.filter(
                ml_model=self.ml_model
            ).order_by('-run_number').first()

            run_number = (last_run.run_number + 1) if last_run else 1

            # Determine model type from model_config
            model_type = TrainingRun.MODEL_TYPE_RETRIEVAL
            if model_config:
                config_model_type = getattr(model_config, 'model_type', None)
                if config_model_type == 'multitask':
                    model_type = TrainingRun.MODEL_TYPE_MULTITASK
                elif config_model_type == 'ranking':
                    model_type = TrainingRun.MODEL_TYPE_RANKING

            # Create training run
            training_run = TrainingRun.objects.create(
                ml_model=self.ml_model,
                name=name,
                run_number=run_number,
                description=description,
                model_type=model_type,
                dataset=dataset,
                feature_config=feature_config,
                model_config=model_config,
                base_experiment=base_experiment,
                training_params=training_params or {},
                gpu_config=gpu_config or {},
                evaluator_config=evaluator_config or {},
                deployment_config=deployment_config or {},
                created_by=created_by,
                status=TrainingRun.STATUS_PENDING,
            )

            logger.info(
                f"Created training run {training_run.display_name} "
                f"(id={training_run.id}) for model {self.ml_model.name}"
            )

            return training_run

    def refresh_status(self, training_run: TrainingRun) -> TrainingRun:
        """
        Refresh training run status from Cloud Build and/or Vertex AI.

        This handles two phases:
        1. Cloud Build phase (compilation): Check if Cloud Build completed and
           read the Vertex AI job name from GCS
        2. Vertex AI phase (pipeline execution): Check pipeline status and
           update stage details (8 stages for training)

        Args:
            training_run: TrainingRun instance to refresh

        Returns:
            Updated TrainingRun instance
        """
        logger.info(
            f"{training_run.display_name} (id={training_run.id}): "
            f"Refreshing status (current: {training_run.status})"
        )

        # Phase 1: If no Vertex AI job yet, check Cloud Build status
        if not training_run.vertex_pipeline_job_name:
            logger.info(
                f"{training_run.display_name}: No Vertex AI job yet, checking Cloud Build"
            )
            if training_run.cloud_build_run_id:
                self._check_cloud_build_result(training_run)
            else:
                logger.warning(
                    f"{training_run.display_name}: No cloud_build_run_id, cannot check Cloud Build"
                )
            # If still no vertex_pipeline_job_name after checking, return
            if not training_run.vertex_pipeline_job_name:
                logger.info(
                    f"{training_run.display_name}: Still no Vertex AI job, Cloud Build may be running"
                )
                return training_run

        # Phase 2: Check Vertex AI pipeline status
        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            # Get pipeline job status
            pipeline_job = aiplatform.PipelineJob.get(
                training_run.vertex_pipeline_job_name
            )

            state = pipeline_job.state.name

            # Map Vertex AI states to TrainingRun states
            state_mapping = {
                'PIPELINE_STATE_PENDING': TrainingRun.STATUS_RUNNING,
                'PIPELINE_STATE_RUNNING': TrainingRun.STATUS_RUNNING,
                'PIPELINE_STATE_SUCCEEDED': TrainingRun.STATUS_COMPLETED,
                'PIPELINE_STATE_FAILED': TrainingRun.STATUS_FAILED,
                'PIPELINE_STATE_CANCELLED': TrainingRun.STATUS_CANCELLED,
                'PIPELINE_STATE_CANCELLING': TrainingRun.STATUS_RUNNING,
            }

            new_status = state_mapping.get(state, training_run.status)

            if new_status != training_run.status:
                logger.info(
                    f"{training_run.display_name}: Status changing from "
                    f"{training_run.status} to {new_status}"
                )
                training_run.status = new_status

                if new_status == TrainingRun.STATUS_COMPLETED:
                    training_run.completed_at = timezone.now()
                    logger.info(f"{training_run.display_name}: Pipeline completed, extracting results")
                    # Extract results from GCS
                    self._extract_results(training_run)
                    # Cache training history from GCS for fast loading
                    self._cache_training_history(training_run)

                elif new_status == TrainingRun.STATUS_FAILED:
                    training_run.completed_at = timezone.now()
                    # Try to extract error message
                    if hasattr(pipeline_job, 'error') and pipeline_job.error:
                        training_run.error_message = str(pipeline_job.error)
                    logger.warning(
                        f"{training_run.display_name}: Pipeline failed: {training_run.error_message}"
                    )

                training_run.save()

            # Update progress from pipeline tasks
            self._update_progress(training_run, pipeline_job)

        except Exception as e:
            logger.exception(f"Error refreshing status for {training_run.display_name}: {e}")

        return training_run

    def _check_cloud_build_result(self, training_run: TrainingRun):
        """
        Check if Cloud Build has completed and read the result from GCS.

        The compile script writes result to:
        gs://{STAGING_BUCKET}/build_results/{run_id}.json

        Args:
            training_run: TrainingRun instance
        """
        run_id = training_run.cloud_build_run_id
        if not run_id:
            return

        result_blob_path = f"build_results/{run_id}.json"
        bucket = self.storage_client.bucket(self.STAGING_BUCKET)
        blob = bucket.blob(result_blob_path)

        try:
            if not blob.exists():
                # Cloud Build still running - no result yet
                logger.debug(f"Cloud Build result not ready yet: {result_blob_path}")
                return

            # Read result
            content = blob.download_as_string().decode('utf-8')
            result = json.loads(content)
            logger.info(f"Cloud Build result for {run_id}: {result}")

            if result.get('success'):
                # Cloud Build succeeded - pipeline was submitted to Vertex AI
                training_run.vertex_pipeline_job_name = result['vertex_pipeline_job_name']
                # Extract job ID from full resource name
                training_run.vertex_pipeline_job_id = result['vertex_pipeline_job_name'].split('/')[-1]
                training_run.status = TrainingRun.STATUS_RUNNING
                training_run.started_at = timezone.now()

                # Update stage_details: Compile completed, Examples starting
                training_run.stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None},
                    {'name': 'Examples', 'status': 'running', 'duration_seconds': None},
                    {'name': 'Stats', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Schema', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Transform', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Train', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Evaluator', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Pusher', 'status': 'pending', 'duration_seconds': None},
                ]
                training_run.current_stage = 'examples'
                training_run.progress_percent = 12  # ~1/8 stages complete

                training_run.save(update_fields=[
                    'vertex_pipeline_job_name',
                    'vertex_pipeline_job_id',
                    'status',
                    'started_at',
                    'stage_details',
                    'current_stage',
                    'progress_percent'
                ])
                logger.info(
                    f"{training_run.display_name} pipeline submitted: "
                    f"{training_run.vertex_pipeline_job_id}"
                )
            else:
                # Cloud Build failed
                training_run.status = TrainingRun.STATUS_FAILED
                training_run.error_message = result.get('error', 'Cloud Build failed')
                training_run.error_stage = 'compile'
                training_run.completed_at = timezone.now()

                # Update stage_details: Compile failed
                training_run.stage_details = [
                    {'name': 'Compile', 'status': 'failed', 'duration_seconds': None},
                    {'name': 'Examples', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Stats', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Schema', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Transform', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Train', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Evaluator', 'status': 'pending', 'duration_seconds': None},
                    {'name': 'Pusher', 'status': 'pending', 'duration_seconds': None},
                ]
                training_run.current_stage = 'failed'

                training_run.save(update_fields=[
                    'status',
                    'error_message',
                    'error_stage',
                    'completed_at',
                    'stage_details',
                    'current_stage'
                ])
                logger.warning(
                    f"{training_run.display_name} Cloud Build failed: {training_run.error_message}"
                )

        except Exception as e:
            logger.warning(f"Error checking Cloud Build result for {training_run.display_name}: {e}")

    def _update_progress(self, training_run: TrainingRun, pipeline_job):
        """
        Update progress and stage details from Vertex AI pipeline tasks.

        Handles 8 stages for training pipeline (vs 6 for experiments).

        Args:
            training_run: TrainingRun instance
            pipeline_job: Vertex AI PipelineJob instance
        """
        try:
            pipeline_state = pipeline_job.state.name
            logger.info(f"{training_run.display_name}: Pipeline state is {pipeline_state}")

            # Handle terminal pipeline states first
            if pipeline_state == 'PIPELINE_STATE_SUCCEEDED':
                # Pipeline completed - check actual task statuses to handle skipped stages
                task_statuses = self._get_task_statuses(pipeline_job)

                stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None}
                ]

                for stage_name in self.STAGE_ORDER[1:]:  # Skip 'Compile'
                    task_info = task_statuses.get(stage_name, {})
                    # Default to 'skipped' if task not found (wasn't triggered)
                    status = task_info.get('status', 'skipped')
                    duration = task_info.get('duration_seconds')

                    stage_details.append({
                        'name': stage_name,
                        'status': status,
                        'duration_seconds': duration
                    })

                current_stage = 'completed'
                progress_percent = 100
                logger.info(f"{training_run.display_name}: Pipeline SUCCEEDED")

            elif pipeline_state in ('PIPELINE_STATE_FAILED', 'PIPELINE_STATE_CANCELLED'):
                # Pipeline failed or cancelled
                task_statuses = self._get_task_statuses(pipeline_job)

                stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None}
                ]

                failed_stage_found = False
                for stage_name in self.STAGE_ORDER[1:]:  # Skip 'Compile'
                    task_info = task_statuses.get(stage_name, {})
                    status = task_info.get('status', 'pending')
                    duration = task_info.get('duration_seconds')

                    if failed_stage_found:
                        status = 'pending'
                        duration = None
                    elif status == 'failed':
                        failed_stage_found = True
                        training_run.error_stage = stage_name.lower()

                    stage_details.append({
                        'name': stage_name,
                        'status': status,
                        'duration_seconds': duration
                    })

                # If no specific failed stage found, mark first pending/running as failed
                if not failed_stage_found:
                    for stage in stage_details:
                        if stage['name'] != 'Compile' and stage['status'] in ('pending', 'running'):
                            stage['status'] = 'failed'
                            training_run.error_stage = stage['name'].lower()
                            break

                current_stage = 'failed' if 'FAILED' in pipeline_state else 'cancelled'
                completed_count = sum(1 for s in stage_details if s['status'] == 'completed')
                progress_percent = int((completed_count / len(stage_details)) * 100)

            else:
                # Pipeline is still running
                task_statuses = self._get_task_statuses(pipeline_job)

                stage_details = [
                    {'name': 'Compile', 'status': 'completed', 'duration_seconds': None}
                ]

                for stage_name in self.STAGE_ORDER[1:]:  # Skip 'Compile'
                    task_info = task_statuses.get(stage_name, {})
                    stage_details.append({
                        'name': stage_name,
                        'status': task_info.get('status', 'pending'),
                        'duration_seconds': task_info.get('duration_seconds')
                    })

                # Determine current stage
                current_stage = 'completed'
                for stage in stage_details:
                    if stage['status'] == 'running':
                        current_stage = stage['name'].lower()
                        break
                    elif stage['status'] == 'pending':
                        current_stage = stage['name'].lower()
                        break
                    elif stage['status'] == 'failed':
                        current_stage = 'failed'
                        break

                completed_count = sum(1 for s in stage_details if s['status'] == 'completed')
                progress_percent = int((completed_count / len(stage_details)) * 100)

            # Update TrainingRun
            training_run.stage_details = stage_details
            training_run.current_stage = current_stage
            training_run.progress_percent = progress_percent
            training_run.save(update_fields=['stage_details', 'current_stage', 'progress_percent'])

            logger.info(
                f"{training_run.display_name}: Updated progress - "
                f"stage={current_stage}, progress={progress_percent}%"
            )

        except Exception as e:
            logger.exception(f"Error updating progress for {training_run.display_name}: {e}")

    def _get_task_statuses(self, pipeline_job) -> dict:
        """
        Extract task statuses from Vertex AI pipeline job.

        Args:
            pipeline_job: Vertex AI PipelineJob instance

        Returns:
            Dict mapping short stage names to status info:
            {
                'Examples': {'status': 'completed', 'duration_seconds': 120},
                'Stats': {'status': 'running', 'duration_seconds': None},
                ...
            }
        """
        try:
            gca_resource = pipeline_job._gca_resource

            if not hasattr(gca_resource, 'job_detail') or not gca_resource.job_detail:
                return {}

            task_details = gca_resource.job_detail.task_details
            if not task_details:
                return {}

            result = {}

            for task in task_details:
                task_name = task.task_name.lower() if task.task_name else ''

                # Map to short stage name
                short_name = self.STAGE_NAME_MAP.get(task_name)
                if not short_name:
                    for tfx_name, display_name in self.STAGE_NAME_MAP.items():
                        if tfx_name in task_name:
                            short_name = display_name
                            break

                if not short_name:
                    continue

                # Get task state
                task_state = task.state.name if task.state else 'PENDING'

                # Map Vertex AI task states to our status
                state_mapping = {
                    'PENDING': 'pending',
                    'RUNNING': 'running',
                    'SUCCEEDED': 'completed',
                    'SKIPPED': 'skipped',
                    'FAILED': 'failed',
                    'CANCELLED': 'failed',
                    'CANCELLING': 'running',
                    'NOT_TRIGGERED': 'skipped',
                }
                status = state_mapping.get(task_state, 'pending')

                # Calculate duration
                duration_seconds = None
                if task.start_time and task.end_time:
                    duration = task.end_time - task.start_time
                    duration_seconds = int(duration.total_seconds())
                elif task.start_time and status == 'running':
                    from datetime import datetime as dt, timezone as dt_timezone
                    now = dt.now(dt_timezone.utc)
                    if hasattr(task.start_time, 'timestamp'):
                        duration_seconds = int(now.timestamp() - task.start_time.timestamp())

                result[short_name] = {
                    'status': status,
                    'duration_seconds': duration_seconds,
                }

            return result

        except Exception as e:
            logger.exception(f"Error extracting task statuses: {e}")
            return {}

    def _extract_results(self, training_run: TrainingRun):
        """
        Extract results and metrics from GCS after pipeline completion.

        Reads:
        - training_metrics.json - Training loss and recall metrics
        - evaluation_results.json - Evaluator output (blessing status)

        Args:
            training_run: TrainingRun instance
        """
        if not training_run.gcs_artifacts_path:
            return

        try:
            bucket = self.storage_client.bucket(self.ARTIFACTS_BUCKET)

            # Read training_metrics.json
            metrics_blob_path = training_run.gcs_artifacts_path.replace(
                f"gs://{self.ARTIFACTS_BUCKET}/", ""
            ) + "/training_metrics.json"

            blob = bucket.blob(metrics_blob_path)

            if blob.exists():
                metrics_content = blob.download_as_string().decode('utf-8')
                training_metrics = json.loads(metrics_content)

                final_metrics = training_metrics.get('final_metrics', {})
                update_fields = []

                # Extract loss
                if 'test_loss' in final_metrics:
                    training_run.loss = final_metrics['test_loss']
                    update_fields.append('loss')

                # Extract recall metrics (retrieval models)
                for k in [5, 10, 50, 100]:
                    metric_key = f'test_recall_at_{k}'
                    if metric_key in final_metrics:
                        setattr(training_run, f'recall_at_{k}', final_metrics[metric_key])
                        update_fields.append(f'recall_at_{k}')

                # Extract RMSE/MAE (ranking models)
                for metric in ['rmse', 'mae', 'test_rmse', 'test_mae']:
                    if metric in final_metrics:
                        setattr(training_run, metric, final_metrics[metric])
                        update_fields.append(metric)

                if update_fields:
                    training_run.save(update_fields=update_fields)

                logger.info(
                    f"Extracted results for {training_run.display_name}: "
                    f"{list(final_metrics.keys())}"
                )

        except Exception as e:
            logger.warning(f"Error extracting results for {training_run.display_name}: {e}")

        # Check blessing status from evaluator output
        try:
            blessing_blob_path = training_run.gcs_artifacts_path.replace(
                f"gs://{self.ARTIFACTS_BUCKET}/", ""
            ) + "/evaluation_blessing.json"

            blessing_blob = bucket.blob(blessing_blob_path)

            if blessing_blob.exists():
                blessing_content = blessing_blob.download_as_string().decode('utf-8')
                blessing_data = json.loads(blessing_content)
                is_blessed = blessing_data.get('is_blessed', False)

                training_run.is_blessed = is_blessed
                training_run.evaluation_results = blessing_data

                if not is_blessed:
                    training_run.status = TrainingRun.STATUS_NOT_BLESSED
                    logger.info(
                        f"{training_run.display_name} model not blessed - "
                        f"threshold not met: {blessing_data.get('threshold_metric')}"
                    )
                else:
                    logger.info(
                        f"{training_run.display_name} model blessed - "
                        f"threshold met: {blessing_data.get('threshold_metric')}"
                    )

                training_run.save(update_fields=['is_blessed', 'evaluation_results', 'status'])
            else:
                # No blessing file - evaluator may not have been enabled
                # Default to blessed for backward compatibility
                evaluator_config = training_run.evaluator_config or {}
                if evaluator_config.get('enabled', True):
                    # Evaluator was enabled but no blessing file - check pipeline output
                    logger.warning(
                        f"{training_run.display_name}: No blessing file found, defaulting to blessed"
                    )
                training_run.is_blessed = True
                training_run.save(update_fields=['is_blessed'])

        except Exception as e:
            logger.warning(f"Error checking blessing status for {training_run.display_name}: {e}")
            # Default to blessed on error
            training_run.is_blessed = True
            training_run.save(update_fields=['is_blessed'])

        # Register to Model Registry (regardless of blessing status)
        try:
            self._register_to_model_registry(training_run)
        except Exception as e:
            logger.warning(f"Model registration failed (non-fatal): {e}")

    def _register_to_model_registry(self, training_run: TrainingRun) -> None:
        """
        Register trained model to Vertex AI Model Registry.
        Called automatically after pipeline completion.
        """
        self._init_aiplatform()

        # Check if already registered
        if training_run.vertex_model_resource_name:
            logger.info(f"{training_run.display_name}: Already registered in Model Registry")
            return

        # Build display name from training run name (with fallback)
        model_name = training_run.name or f"{self.ml_model.name}-v{training_run.run_number}"

        # Find the versioned model directory (TFX Pusher creates versioned subdirectories)
        # Structure: pushed_model/<version_number>/saved_model.pb
        base_pushed_model_path = f"{training_run.gcs_artifacts_path}/pushed_model"
        artifact_uri = base_pushed_model_path

        try:
            from google.cloud import storage

            # Parse GCS path
            gcs_path = base_pushed_model_path.replace('gs://', '')
            bucket_name = gcs_path.split('/')[0]
            prefix = '/'.join(gcs_path.split('/')[1:]) + '/'

            client = storage.Client(project=self.project_id)
            bucket = client.bucket(bucket_name)

            # List subdirectories to find versioned model directory
            # Need to consume the iterator to populate prefixes
            iterator = bucket.list_blobs(prefix=prefix, delimiter='/')
            _ = list(iterator)  # Consume iterator to populate prefixes
            prefixes = list(iterator.prefixes)

            if prefixes:
                # Use the first (or only) version directory
                version_dir = prefixes[0].rstrip('/')
                artifact_uri = f"gs://{bucket_name}/{version_dir}"
                logger.info(f"{training_run.display_name}: Found versioned model at {artifact_uri}")
        except Exception as e:
            logger.warning(f"{training_run.display_name}: Could not find versioned model directory, using base path: {e}")

        # Helper to sanitize label values for GCP (lowercase, alphanumeric, dashes, underscores only)
        def sanitize_label(value: str) -> str:
            # Convert to lowercase, replace invalid chars with underscores, truncate to 63 chars
            sanitized = re.sub(r'[^a-z0-9_-]', '_', str(value).lower())
            # Ensure it starts with a letter or number
            if sanitized and not sanitized[0].isalnum():
                sanitized = 'v' + sanitized
            return sanitized[:63]

        # Labels for tracking (values must be strings, max 63 chars, lowercase alphanumeric only)
        labels = {
            'training_run_id': sanitize_label(training_run.id),
            'model_endpoint_id': sanitize_label(self.ml_model.id),
            'model_type': sanitize_label(training_run.model_type) if training_run.model_type else 'unknown',
            'is_blessed': sanitize_label(training_run.is_blessed) if training_run.is_blessed is not None else 'unknown',
        }

        # Add metrics as labels (truncated to 63 chars)
        if training_run.recall_at_100:
            labels['recall_at_100'] = sanitize_label(f"{training_run.recall_at_100:.4f}")
        if training_run.loss:
            labels['loss'] = sanitize_label(f"{training_run.loss:.4f}")

        try:
            from google.cloud import aiplatform

            # Find parent model (first registered model with same name) for versioning
            parent_model_resource_name = None
            parent_model = TrainingRun.objects.filter(
                ml_model=self.ml_model,
                name=training_run.name,
                vertex_model_resource_name__isnull=False
            ).exclude(
                vertex_model_resource_name=''
            ).exclude(
                id=training_run.id
            ).order_by('registered_at').first()  # Get FIRST (oldest) as parent

            if parent_model:
                parent_model_resource_name = parent_model.vertex_model_resource_name
                logger.info(
                    f"{training_run.display_name}: Found parent model {parent_model_resource_name}, "
                    f"will create as version"
                )

            model = aiplatform.Model.upload(
                display_name=model_name,
                artifact_uri=artifact_uri,
                serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-12:latest",
                labels=labels,
                parent_model=parent_model_resource_name,
            )

            training_run.vertex_model_resource_name = model.resource_name
            training_run.vertex_model_name = model.display_name
            training_run.vertex_model_version = model.version_id or ''
            training_run.vertex_parent_model_resource_name = parent_model_resource_name or ''
            training_run.registered_at = timezone.now()
            training_run.save(update_fields=[
                'vertex_model_resource_name', 'vertex_model_name', 'vertex_model_version',
                'vertex_parent_model_resource_name', 'registered_at', 'updated_at'
            ])

            logger.info(
                f"{training_run.display_name}: Registered to Model Registry as {model.display_name} "
                f"(version: {model.version_id})"
            )

        except Exception as e:
            logger.exception(f"{training_run.display_name}: Failed to register to Model Registry: {e}")
            # Don't raise - registration failure shouldn't fail the training run

    def _cache_training_history(self, training_run: TrainingRun):
        """
        Cache training history from GCS into Django DB for fast loading.

        This is called after training completion. Caching happens asynchronously
        and errors are logged but don't fail the completion process.

        Args:
            training_run: TrainingRun instance with gcs_artifacts_path set
        """
        if not training_run.gcs_artifacts_path:
            logger.info(
                f"{training_run.display_name}: "
                f"Skipping training history cache - no GCS artifacts path"
            )
            return

        try:
            from ml_platform.experiments.training_cache_service import TrainingCacheService

            cache_service = TrainingCacheService()
            success = cache_service.cache_training_history_for_run(training_run)

            if success:
                logger.info(
                    f"{training_run.display_name}: "
                    f"Training history cached successfully"
                )
            else:
                logger.warning(
                    f"{training_run.display_name}: "
                    f"Training history caching failed (non-fatal)"
                )

        except Exception as e:
            # Log but don't fail - caching is a nice-to-have
            logger.warning(
                f"{training_run.display_name}: "
                f"Error caching training history (non-fatal): {e}"
            )

    def cancel_training_run(self, training_run: TrainingRun) -> TrainingRun:
        """
        Cancel a running training run.

        Handles two phases:
        1. SUBMITTING phase: Cancel Cloud Build (compilation)
        2. RUNNING phase: Cancel Vertex AI pipeline

        Args:
            training_run: TrainingRun instance to cancel

        Returns:
            Updated TrainingRun instance
        """
        cloud_build_cancelled = False
        vertex_pipeline_cancelled = False

        # Phase 1: Cancel Cloud Build if still in compilation
        if training_run.cloud_build_id and not training_run.vertex_pipeline_job_name:
            try:
                from google.cloud.devtools import cloudbuild_v1

                client = cloudbuild_v1.CloudBuildClient()
                client.cancel_build(
                    project_id=self.project_id,
                    id=training_run.cloud_build_id
                )
                cloud_build_cancelled = True
                logger.info(f"Cancelled Cloud Build {training_run.cloud_build_id}")
            except Exception as e:
                # Cloud Build may have already completed
                logger.warning(f"Could not cancel Cloud Build: {e}")
                # Check if Vertex pipeline was submitted in the meantime
                self._check_cloud_build_result(training_run)
                training_run.refresh_from_db()

        # Phase 2: Cancel Vertex AI pipeline if it exists
        if training_run.vertex_pipeline_job_name:
            self._init_aiplatform()
            try:
                from google.cloud import aiplatform

                pipeline_job = aiplatform.PipelineJob.get(
                    training_run.vertex_pipeline_job_name
                )
                pipeline_job.cancel()
                vertex_pipeline_cancelled = True
                logger.info(f"Cancelled Vertex AI pipeline {training_run.vertex_pipeline_job_name}")
            except Exception as e:
                logger.warning(f"Error cancelling pipeline: {e}")

        # Update status
        training_run.status = TrainingRun.STATUS_CANCELLED
        training_run.completed_at = timezone.now()
        training_run.save(update_fields=['status', 'completed_at', 'updated_at'])

        logger.info(
            f"Cancelled training run {training_run.display_name} (id={training_run.id}) - "
            f"Cloud Build: {cloud_build_cancelled}, Vertex AI: {vertex_pipeline_cancelled}"
        )

        return training_run

    def delete_training_run(self, training_run: TrainingRun) -> None:
        """
        Delete a training run and its associated GCS artifacts.

        Only training runs in terminal states (completed, failed, cancelled, not_blessed)
        can be deleted.

        Args:
            training_run: TrainingRun instance to delete

        Raises:
            TrainingServiceError: If training run is not in terminal state
        """
        # Verify training run is in terminal state
        if training_run.status in (TrainingRun.STATUS_RUNNING, TrainingRun.STATUS_SUBMITTING):
            raise TrainingServiceError(
                f"Cannot delete training run in '{training_run.status}' state. "
                "Please cancel first."
            )

        run_id = training_run.id
        display_name = training_run.display_name

        # Delete GCS artifacts if path exists
        if training_run.gcs_artifacts_path:
            self._delete_gcs_artifacts(training_run.gcs_artifacts_path, display_name)

        # Delete the database record
        try:
            training_run.delete()
            logger.info(f"Successfully deleted training run {display_name} (id={run_id})")
        except Exception as e:
            logger.error(f"Failed to delete training run: {e}")
            raise TrainingServiceError(f"Failed to delete training run: {e}")

    def _delete_gcs_artifacts(self, gcs_path: str, display_name: str):
        """
        Delete GCS artifacts for a training run.

        Args:
            gcs_path: GCS path (gs://bucket/prefix)
            display_name: Training run display name for logging
        """
        try:
            # Parse GCS path
            if not gcs_path.startswith('gs://'):
                logger.warning(f"Invalid GCS path: {gcs_path}")
                return

            path = gcs_path[5:]  # Remove 'gs://'
            bucket_name = path.split('/')[0]
            prefix = '/'.join(path.split('/')[1:])

            bucket = self.storage_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))

            if blobs:
                logger.info(f"Deleting {len(blobs)} artifacts for {display_name}")
                for blob in blobs:
                    blob.delete()
                logger.info(f"Deleted GCS artifacts: {gcs_path}")
            else:
                logger.info(f"No GCS artifacts found at {gcs_path}")

        except Exception as e:
            # Log but don't fail - artifacts may already be deleted
            logger.warning(f"Error deleting GCS artifacts for {display_name}: {e}")

    def rerun_training_run(self, training_run: TrainingRun) -> TrainingRun:
        """
        Re-run a training run by creating a new run with the same config.

        Works for any terminal state (completed, failed, not_blessed, cancelled).

        Args:
            training_run: TrainingRun instance to re-run

        Returns:
            New TrainingRun instance

        Raises:
            TrainingServiceError: If training run is not in terminal state
        """
        TERMINAL_STATUSES = [
            TrainingRun.STATUS_COMPLETED,
            TrainingRun.STATUS_FAILED,
            TrainingRun.STATUS_NOT_BLESSED,
            TrainingRun.STATUS_CANCELLED,
        ]

        if training_run.status not in TERMINAL_STATUSES:
            raise TrainingServiceError(
                f"Cannot re-run training in '{training_run.status}' state. "
                "Only terminal states can be re-run."
            )

        # Keep original name (no suffix for clean reruns)
        new_run = self.create_training_run(
            name=training_run.name,  # Same name, new run_number auto-assigned
            description=f"Re-run of {training_run.display_name}",
            dataset=training_run.dataset,
            feature_config=training_run.feature_config,
            model_config=training_run.model_config,
            base_experiment=training_run.base_experiment,
            training_params=training_run.training_params,
            gpu_config=training_run.gpu_config,
            evaluator_config=training_run.evaluator_config,
            deployment_config=training_run.deployment_config,
            created_by=training_run.created_by,
        )

        # Copy schedule_config (without cloud_scheduler_job_name to avoid conflicts)
        if training_run.schedule_config:
            new_run.schedule_config = {
                k: v for k, v in training_run.schedule_config.items()
                if k != 'cloud_scheduler_job_name'
            }
            new_run.save(update_fields=['schedule_config'])

        logger.info(
            f"Created re-run {new_run.display_name} for {training_run.display_name}"
        )

        # Auto-submit the new run
        try:
            self.submit_training_pipeline(new_run)
        except Exception as e:
            logger.error(f"Failed to submit re-run pipeline: {e}")
            new_run.refresh_from_db()

        return new_run

    def create_cloud_scheduler_job_for_training_run(
        self, training_run: TrainingRun, schedule_config: dict
    ) -> str:
        """
        Create a Cloud Scheduler job to trigger scheduled training runs.

        Args:
            training_run: TrainingRun instance to use as template
            schedule_config: Schedule configuration dict with keys:
                - schedule_type: 'once', 'daily', 'weekly'
                - schedule_time: 'HH:MM' for daily/weekly
                - schedule_day_of_week: 0-6 for weekly (0=Monday)
                - schedule_timezone: timezone string (e.g., 'UTC')
                - scheduled_datetime: ISO-8601 for one-time schedules

        Returns:
            Full Cloud Scheduler job resource name

        Raises:
            TrainingServiceError: If job creation fails
        """
        from google.cloud import scheduler_v1
        from google.protobuf import duration_pb2

        schedule_type = schedule_config.get('schedule_type', 'now')
        if schedule_type == 'now':
            raise TrainingServiceError("Cannot create scheduler job for 'now' schedule type")

        # Build cron expression
        schedule_time = schedule_config.get('schedule_time', '09:00')
        hour, minute = schedule_time.split(':')

        if schedule_type == 'once':
            # One-time schedule - use at-style scheduling with specific datetime
            scheduled_datetime = schedule_config.get('scheduled_datetime')
            if not scheduled_datetime:
                raise TrainingServiceError("scheduled_datetime required for 'once' schedule type")
            # Cloud Scheduler doesn't support one-time directly, we'll pause after first run
            # Use a cron that runs at the specified time
            from datetime import datetime
            dt = datetime.fromisoformat(scheduled_datetime.replace('Z', '+00:00'))
            cron_schedule = f"{dt.minute} {dt.hour} {dt.day} {dt.month} *"
        elif schedule_type == 'daily':
            cron_schedule = f"{minute} {hour} * * *"
        elif schedule_type == 'weekly':
            day_of_week = schedule_config.get('schedule_day_of_week', 0)
            # Cloud Scheduler uses 0=Sunday, but we use 0=Monday
            # Convert: 0(Mon)->1, 1(Tue)->2, ... 6(Sun)->0
            cron_day = (day_of_week + 1) % 7
            cron_schedule = f"{minute} {hour} * * {cron_day}"
        else:
            raise TrainingServiceError(f"Unknown schedule type: {schedule_type}")

        timezone = schedule_config.get('schedule_timezone', 'UTC')

        # Create Cloud Scheduler client
        client = scheduler_v1.CloudSchedulerClient()

        # Build job name
        job_id = f"training-run-{training_run.id}-schedule"
        parent = f"projects/{self.project_id}/locations/{self.REGION}"
        job_name = f"{parent}/jobs/{job_id}"

        # Build webhook URL
        webhook_url = (
            f"https://{self.project_id}.appspot.com"
            f"/api/training-runs/{training_run.id}/schedule-webhook/"
        )

        # Create HTTP target with OIDC token
        http_target = scheduler_v1.HttpTarget(
            uri=webhook_url,
            http_method=scheduler_v1.HttpMethod.POST,
            oidc_token=scheduler_v1.OidcToken(
                service_account_email=f"{self.project_id}@appspot.gserviceaccount.com"
            )
        )

        job = scheduler_v1.Job(
            name=job_name,
            http_target=http_target,
            schedule=cron_schedule,
            time_zone=timezone,
            attempt_deadline=duration_pb2.Duration(seconds=600),
        )

        try:
            # Try to create the job
            created_job = client.create_job(
                request={"parent": parent, "job": job}
            )
            logger.info(f"Created Cloud Scheduler job: {created_job.name}")
            return created_job.name
        except Exception as e:
            if 'already exists' in str(e).lower():
                # Job exists, update it instead
                try:
                    updated_job = client.update_job(request={"job": job})
                    logger.info(f"Updated existing Cloud Scheduler job: {updated_job.name}")
                    return updated_job.name
                except Exception as update_error:
                    raise TrainingServiceError(f"Failed to update scheduler job: {update_error}")
            raise TrainingServiceError(f"Failed to create scheduler job: {e}")

    def delete_cloud_scheduler_job(self, job_name: str) -> bool:
        """
        Delete a Cloud Scheduler job.

        Args:
            job_name: Full resource name of the job to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if not job_name:
            return False

        try:
            from google.cloud import scheduler_v1
            client = scheduler_v1.CloudSchedulerClient()
            client.delete_job(name=job_name)
            logger.info(f"Deleted Cloud Scheduler job: {job_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete Cloud Scheduler job {job_name}: {e}")
            return False

    def deploy_model(self, training_run: TrainingRun) -> TrainingRun:
        """
        Deploy a completed, blessed model to a Vertex AI Endpoint.

        Args:
            training_run: TrainingRun instance to deploy

        Returns:
            Updated TrainingRun instance with deployment info

        Raises:
            TrainingServiceError: If training run cannot be deployed
        """
        # Validate state
        if training_run.status != TrainingRun.STATUS_COMPLETED:
            raise TrainingServiceError(
                f"Cannot deploy training run in '{training_run.status}' state. "
                "Only completed training runs can be deployed."
            )

        if not training_run.is_blessed:
            raise TrainingServiceError(
                "Cannot deploy unblessed model. Use 'Push Anyway' to force-push "
                "to registry first, or override the blessing check."
            )

        if training_run.is_deployed:
            raise TrainingServiceError(
                f"Training run is already deployed to endpoint: "
                f"{training_run.endpoint_resource_name}"
            )

        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            # Get or create endpoint
            endpoint_display_name = f"{self.ml_model.name}-endpoint"
            endpoints = aiplatform.Endpoint.list(
                filter=f'display_name="{endpoint_display_name}"',
                order_by="create_time desc"
            )

            if endpoints:
                endpoint = endpoints[0]
                logger.info(f"Using existing endpoint: {endpoint.resource_name}")
            else:
                endpoint = aiplatform.Endpoint.create(
                    display_name=endpoint_display_name,
                    project=self.project_id,
                    location=self.REGION,
                )
                logger.info(f"Created new endpoint: {endpoint.resource_name}")

            # Get model from Vertex AI Model Registry
            model_display_name = training_run.name or f"training-{training_run.id}"
            models = aiplatform.Model.list(
                filter=f'display_name="{model_display_name}"',
                order_by="create_time desc"
            )

            if not models:
                # Try to find by pushed_model path
                pushed_model_path = f"{training_run.gcs_artifacts_path}/pushed_model"
                logger.info(f"Looking for model at: {pushed_model_path}")

                # Find parent model (first registered model with same name) for versioning
                parent_model_resource_name = None
                parent_model = TrainingRun.objects.filter(
                    ml_model=self.ml_model,
                    name=training_run.name,
                    vertex_model_resource_name__isnull=False
                ).exclude(
                    vertex_model_resource_name=''
                ).exclude(
                    id=training_run.id
                ).order_by('registered_at').first()

                if parent_model:
                    parent_model_resource_name = parent_model.vertex_model_resource_name
                    logger.info(
                        f"{training_run.display_name}: Found parent model {parent_model_resource_name}, "
                        f"will create as version"
                    )

                # Upload model to registry if not found
                model = aiplatform.Model.upload(
                    display_name=model_display_name,
                    artifact_uri=pushed_model_path,
                    serving_container_image_uri=(
                        "us-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-12:latest"
                    ),
                    labels={
                        'training_run_id': str(training_run.id),
                        'model_endpoint_id': str(self.ml_model.id),
                    },
                    parent_model=parent_model_resource_name,
                )
                logger.info(
                    f"Uploaded model to registry: {model.resource_name} "
                    f"(version: {model.version_id})"
                )

                # Store version info
                training_run.vertex_model_version = model.version_id or ''
                training_run.vertex_parent_model_resource_name = parent_model_resource_name or ''
                training_run.registered_at = timezone.now()
            else:
                model = models[0]
                logger.info(f"Using existing model: {model.resource_name}")

            # Deploy model to endpoint with auto-scaling
            deployment_config = training_run.deployment_config or {}
            min_replicas = deployment_config.get('min_replicas', 1)
            max_replicas = deployment_config.get('max_replicas', 3)
            machine_type = deployment_config.get('machine_type', 'n1-standard-4')

            model.deploy(
                endpoint=endpoint,
                deployed_model_display_name=model_display_name,
                machine_type=machine_type,
                min_replica_count=min_replicas,
                max_replica_count=max_replicas,
                traffic_percentage=100,
            )

            # Update training run
            training_run.is_deployed = True
            training_run.deployed_at = timezone.now()
            training_run.endpoint_resource_name = endpoint.resource_name
            training_run.vertex_model_resource_name = model.resource_name

            # Include version fields in save if they were set (fallback upload path)
            update_fields = [
                'is_deployed', 'deployed_at', 'endpoint_resource_name',
                'vertex_model_resource_name'
            ]
            if training_run.vertex_model_version:
                update_fields.extend([
                    'vertex_model_version', 'vertex_parent_model_resource_name', 'registered_at'
                ])
            training_run.save(update_fields=update_fields)

            logger.info(
                f"Deployed {training_run.display_name} to endpoint {endpoint.resource_name}"
            )

            return training_run

        except Exception as e:
            logger.exception(f"Error deploying model: {e}")
            raise TrainingServiceError(f"Failed to deploy model: {e}")

    def undeploy_model(self, training_run: TrainingRun) -> TrainingRun:
        """
        Undeploy a model from its Vertex AI Endpoint.

        Removes the model from the endpoint but keeps it in the Model Registry.

        Args:
            training_run: TrainingRun instance to undeploy

        Returns:
            Updated TrainingRun instance with cleared deployment info

        Raises:
            TrainingServiceError: If model cannot be undeployed
        """
        if not training_run.is_deployed:
            raise TrainingServiceError(
                "Training run is not currently deployed."
            )

        if not training_run.endpoint_resource_name:
            # Model marked as deployed but no endpoint - just clear the flag
            training_run.is_deployed = False
            training_run.deployed_at = None
            training_run.save(update_fields=['is_deployed', 'deployed_at'])
            return training_run

        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            # Get the endpoint
            endpoint = aiplatform.Endpoint(training_run.endpoint_resource_name)

            # Find the deployed model ID on this endpoint
            deployed_model_id = None
            model_resource_name = training_run.vertex_model_resource_name

            # List deployed models to find the one to undeploy
            endpoint_obj = endpoint._gca_resource
            for deployed_model in endpoint_obj.deployed_models:
                if deployed_model.model == model_resource_name:
                    deployed_model_id = deployed_model.id
                    break

            if deployed_model_id:
                # Undeploy the model
                endpoint.undeploy(
                    deployed_model_id=deployed_model_id,
                    traffic_split={}  # No traffic to redirect
                )
                logger.info(
                    f"Undeployed model {model_resource_name} from endpoint "
                    f"{training_run.endpoint_resource_name}"
                )
            else:
                logger.warning(
                    f"Model {model_resource_name} not found on endpoint "
                    f"{training_run.endpoint_resource_name}, clearing deployment flag"
                )

            # Update training run
            training_run.is_deployed = False
            training_run.deployed_at = None
            training_run.endpoint_resource_name = ''
            training_run.save(update_fields=[
                'is_deployed', 'deployed_at', 'endpoint_resource_name'
            ])

            logger.info(f"Cleared deployment info for {training_run.display_name}")

            return training_run

        except Exception as e:
            logger.exception(f"Error undeploying model: {e}")
            raise TrainingServiceError(f"Failed to undeploy model: {e}")

    def force_push_model(self, training_run: TrainingRun) -> TrainingRun:
        """
        Force-push a not-blessed model to Vertex AI Model Registry.

        This allows manual override when the evaluator threshold wasn't met
        but the user wants to use the model anyway.

        Args:
            training_run: TrainingRun instance with STATUS_NOT_BLESSED

        Returns:
            Updated TrainingRun instance

        Raises:
            TrainingServiceError: If training run is not in not_blessed state
        """
        if training_run.status != TrainingRun.STATUS_NOT_BLESSED:
            raise TrainingServiceError(
                f"Cannot force-push training run in '{training_run.status}' state. "
                "Only not-blessed training runs can be force-pushed."
            )

        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            # Get pushed model path
            pushed_model_path = f"{training_run.gcs_artifacts_path}/pushed_model"
            model_display_name = f"{training_run.name or f'training-{training_run.id}'}-manual"

            # Find parent model (first registered model with same name) for versioning
            parent_model_resource_name = None
            parent_model = TrainingRun.objects.filter(
                ml_model=self.ml_model,
                name=training_run.name,
                vertex_model_resource_name__isnull=False
            ).exclude(
                vertex_model_resource_name=''
            ).exclude(
                id=training_run.id
            ).order_by('registered_at').first()

            if parent_model:
                parent_model_resource_name = parent_model.vertex_model_resource_name
                logger.info(
                    f"{training_run.display_name}: Found parent model {parent_model_resource_name}, "
                    f"will create as version"
                )

            # Upload model to registry with manual_push label
            model = aiplatform.Model.upload(
                display_name=model_display_name,
                artifact_uri=pushed_model_path,
                serving_container_image_uri=(
                    "us-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-12:latest"
                ),
                labels={
                    'training_run_id': str(training_run.id),
                    'model_endpoint_id': str(self.ml_model.id),
                    'manual_push': 'true',
                    'original_status': 'not_blessed',
                },
                parent_model=parent_model_resource_name,
            )

            logger.info(
                f"Force-pushed model to registry: {model.resource_name} "
                f"(version: {model.version_id})"
            )

            # Update training run - promote to completed
            training_run.status = TrainingRun.STATUS_COMPLETED
            training_run.is_blessed = True  # Mark as blessed after manual override
            training_run.vertex_model_resource_name = model.resource_name
            training_run.vertex_model_name = model_display_name
            training_run.vertex_model_version = model.version_id or ''
            training_run.vertex_parent_model_resource_name = parent_model_resource_name or ''
            training_run.registered_at = timezone.now()

            # Add manual push note to evaluation_results
            eval_results = training_run.evaluation_results or {}
            eval_results['manual_push'] = True
            eval_results['manual_push_at'] = timezone.now().isoformat()
            training_run.evaluation_results = eval_results

            training_run.save(update_fields=[
                'status', 'is_blessed', 'vertex_model_resource_name',
                'vertex_model_name', 'vertex_model_version',
                'vertex_parent_model_resource_name', 'registered_at', 'evaluation_results'
            ])

            logger.info(
                f"Force-pushed {training_run.display_name} - status promoted to completed"
            )

            return training_run

        except Exception as e:
            logger.exception(f"Error force-pushing model: {e}")
            raise TrainingServiceError(f"Failed to force-push model: {e}")

    def register_model(self, training_run: TrainingRun) -> TrainingRun:
        """
        Register or re-register a completed training run's model to Vertex AI Model Registry.

        This is for completed runs that either failed initial automatic registration
        (e.g., due to invalid container image) or need re-registration.

        Args:
            training_run: TrainingRun instance with STATUS_COMPLETED

        Returns:
            Updated TrainingRun instance

        Raises:
            TrainingServiceError: If training run is not in completed state or registration fails
        """
        if training_run.status != TrainingRun.STATUS_COMPLETED:
            raise TrainingServiceError(
                f"Cannot register model for training run in '{training_run.status}' state. "
                "Only completed training runs can be registered."
            )

        # Check if already registered
        if training_run.vertex_model_resource_name:
            raise TrainingServiceError(
                f"Training run is already registered as {training_run.vertex_model_name}. "
                "Cannot re-register an already registered model."
            )

        try:
            # Call the internal registration method
            self._register_to_model_registry(training_run)

            # Reload to get updated fields
            training_run.refresh_from_db()

            if not training_run.vertex_model_resource_name:
                raise TrainingServiceError(
                    "Registration failed - model was not registered to Vertex AI Model Registry"
                )

            logger.info(
                f"Registered {training_run.display_name} to Model Registry as {training_run.vertex_model_name}"
            )

            return training_run

        except TrainingServiceError:
            raise
        except Exception as e:
            logger.exception(f"Error registering model: {e}")
            raise TrainingServiceError(f"Failed to register model: {e}")

    def _get_retrieval_algorithm(self, training_run: TrainingRun) -> str:
        """
        Get the retrieval algorithm for a training run.

        Determines which serving container to use:
        - 'scann': Requires Python/Flask server with ScaNN ops support
        - 'brute_force': Can use native TF Serving for better latency

        Args:
            training_run: TrainingRun instance

        Returns:
            str: 'scann' or 'brute_force'
        """
        # Check if model_config exists and has retrieval_algorithm
        if training_run.model_config:
            algorithm = getattr(training_run.model_config, 'retrieval_algorithm', None)
            if algorithm:
                return algorithm

        # Default to brute_force if not specified
        return 'brute_force'

    def deploy_to_cloud_run(self, training_run: TrainingRun) -> str:
        """
        Deploy trained model to Cloud Run with TF Serving.

        Creates a new Cloud Run service running the tf-serving container,
        configured to load the model from GCS at startup.

        Args:
            training_run: TrainingRun instance to deploy

        Returns:
            str: Cloud Run service URL

        Raises:
            TrainingServiceError: If deployment fails
        """
        import subprocess

        # Validate prerequisites
        if not training_run.vertex_model_resource_name:
            raise TrainingServiceError("Model not registered in Model Registry")

        if training_run.status not in [TrainingRun.STATUS_COMPLETED, TrainingRun.STATUS_NOT_BLESSED]:
            raise TrainingServiceError(f"Cannot deploy model with status: {training_run.status}")

        if not training_run.gcs_artifacts_path:
            raise TrainingServiceError("No GCS artifacts path found for this training run")

        # Build service name (must be lowercase, alphanumeric, and hyphens only)
        service_name = f"{self.ml_model.name}-serving".lower().replace('_', '-')
        # Ensure name is valid (max 63 chars, starts with letter)
        service_name = service_name[:63]
        if not service_name[0].isalpha():
            service_name = f"m-{service_name}"[:63]

        # Get deployment config
        deployment_config = training_run.deployment_config or {}
        memory = deployment_config.get('memory', '4Gi')
        cpu = deployment_config.get('cpu', '2')
        min_instances = deployment_config.get('min_instances', 0)
        max_instances = deployment_config.get('max_instances', 10)
        timeout = deployment_config.get('timeout', '300')  # 5 minutes default

        # Model path in GCS
        model_path = f"{training_run.gcs_artifacts_path}/pushed_model"

        # Select container image based on retrieval algorithm
        # ScaNN models require Python/Flask server with ScaNN ops support
        # Non-ScaNN (brute_force) models use native TF Serving for better latency
        retrieval_algorithm = self._get_retrieval_algorithm(training_run)

        if retrieval_algorithm == 'scann':
            tf_serving_image = f"europe-central2-docker.pkg.dev/{self.project_id}/ml-serving/tf-serving-scann:latest"
            container_type = "Python/ScaNN"
        else:
            tf_serving_image = f"europe-central2-docker.pkg.dev/{self.project_id}/ml-serving/tf-serving-native:latest"
            container_type = "Native TF Serving"

        logger.info(
            f"Deploying {training_run.display_name} to Cloud Run service: {service_name}"
        )
        logger.info(f"  Retrieval algorithm: {retrieval_algorithm}")
        logger.info(f"  Container type: {container_type}")
        logger.info(f"  Model path: {model_path}")
        logger.info(f"  Image: {tf_serving_image}")
        logger.info(f"  Config: {cpu} vCPU, {memory} memory, {min_instances}-{max_instances} instances")

        try:
            # Deploy using gcloud CLI
            # Note: For production, consider using the Cloud Run Admin API directly
            cmd = [
                'gcloud', 'run', 'deploy', service_name,
                f'--image={tf_serving_image}',
                f'--region={self.REGION}',
                f'--project={self.project_id}',
                f'--memory={memory}',
                f'--cpu={cpu}',
                f'--min-instances={min_instances}',
                f'--max-instances={max_instances}',
                f'--timeout={timeout}',
                f'--set-env-vars=MODEL_PATH={model_path},MODEL_NAME=recommender',
                '--port=8501',
                '--allow-unauthenticated',  # For testing; use IAM in production
                '--format=value(status.url)',
            ]

            logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for deployment
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise TrainingServiceError(f"Cloud Run deployment failed: {error_msg}")

            service_url = result.stdout.strip()

            if not service_url:
                # Try to get the URL from describe
                describe_cmd = [
                    'gcloud', 'run', 'services', 'describe', service_name,
                    f'--region={self.REGION}',
                    f'--project={self.project_id}',
                    '--format=value(status.url)',
                ]
                describe_result = subprocess.run(
                    describe_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                service_url = describe_result.stdout.strip()

            logger.info(f"Cloud Run service deployed: {service_url}")

            # Update TrainingRun
            training_run.is_deployed = True
            training_run.deployed_at = timezone.now()
            training_run.endpoint_resource_name = service_url
            training_run.save(update_fields=[
                'is_deployed', 'deployed_at', 'endpoint_resource_name', 'updated_at'
            ])

            logger.info(
                f"Deployed {training_run.display_name} to Cloud Run: {service_url}"
            )

            return service_url

        except subprocess.TimeoutExpired:
            raise TrainingServiceError("Cloud Run deployment timed out after 5 minutes")
        except Exception as e:
            logger.exception(f"Error deploying to Cloud Run: {e}")
            raise TrainingServiceError(f"Failed to deploy to Cloud Run: {e}")

    def submit_training_pipeline(self, training_run: TrainingRun) -> TrainingRun:
        """
        Submit a training run to Vertex AI Pipeline.

        This generates code, uploads to GCS, and triggers Cloud Build to compile
        and submit the TFX pipeline. The method returns immediately after
        triggering Cloud Build - status updates come via refresh_status().

        Args:
            training_run: TrainingRun instance to submit

        Returns:
            Updated TrainingRun instance

        Raises:
            TrainingServiceError: If submission fails
        """
        from ml_platform.configs.services import PreprocessingFnGenerator, TrainerModuleGenerator
        from ml_platform.datasets.services import BigQueryService

        feature_config = training_run.feature_config
        model_config = training_run.model_config
        dataset = training_run.dataset

        logger.info(f"Submitting training pipeline for {training_run.display_name} (id={training_run.id})")

        try:
            # 1. Generate transform code from FeatureConfig
            logger.info(f"Generating transform code for FeatureConfig {feature_config.id}")
            transform_generator = PreprocessingFnGenerator(feature_config)
            transform_code = transform_generator.generate()

            # 2. Generate trainer code from FeatureConfig + ModelConfig
            # Training uses full epochs, batch size, and learning rate from training_params
            logger.info(f"Generating trainer code for ModelConfig {model_config.id}")
            trainer_generator = TrainerModuleGenerator(feature_config, model_config)
            trainer_code, is_valid, error_msg, error_line = trainer_generator.generate_and_validate()

            if not is_valid:
                raise TrainingServiceError(
                    f"Generated trainer code has syntax error at line {error_line}: {error_msg}"
                )

            # 3. Generate SQL query - Training always uses 100% of data with time-based split
            logger.info("Generating BigQuery SQL for training data")
            bq_service = BigQueryService(self.ml_model, dataset)

            # Training uses strict_time split by default for proper temporal validation
            training_params = training_run.training_params or {}
            split_strategy = training_params.get('split_strategy', 'strict_time')
            train_days = training_params.get('train_days', 90)
            val_days = training_params.get('val_days', 7)
            test_days = training_params.get('test_days', 7)
            date_column = training_params.get('date_column', '')

            # For temporal strategies, generate separate queries for each split
            split_queries = None
            if split_strategy in ('time_holdout', 'strict_time'):
                logger.info(f"Generating split-specific queries for {split_strategy}")
                split_queries = bq_service.generate_split_queries(
                    dataset=dataset,
                    split_strategy=split_strategy,
                    holdout_days=test_days,
                    date_column=date_column,
                    sample_percent=100,  # Training always uses 100% data
                    train_days=train_days,
                    val_days=val_days,
                    test_days=test_days,
                )
                bigquery_query = split_queries['train']
            else:
                # Random strategy: single query, TFX does hash-based splitting
                bigquery_query = bq_service.generate_training_query(
                    dataset=dataset,
                    split_strategy=split_strategy,
                    holdout_days=test_days,
                    date_column=date_column,
                    sample_percent=100,
                    train_days=train_days,
                    val_days=val_days,
                    test_days=test_days,
                )

            # 4. Create unique paths for this run
            run_id = f"tr-{training_run.id}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
            gcs_base_path = f"gs://{self.ARTIFACTS_BUCKET}/{run_id}"

            # 5. Upload code to GCS
            logger.info(f"Uploading code to GCS: {gcs_base_path}")
            transform_module_path = self._upload_to_gcs(
                content=transform_code,
                blob_path=f"{run_id}/transform_module.py"
            )
            trainer_module_path = self._upload_to_gcs(
                content=trainer_code,
                blob_path=f"{run_id}/trainer_module.py"
            )

            # Save GCS paths to training_run
            training_run.gcs_artifacts_path = gcs_base_path
            training_run.save(update_fields=['gcs_artifacts_path'])

            # 6. Trigger Cloud Build to compile and submit pipeline
            logger.info("Triggering TFX pipeline compilation via Cloud Build")
            build_id = self._trigger_cloud_build(
                training_run=training_run,
                bigquery_query=bigquery_query,
                split_queries=split_queries,
                transform_module_path=transform_module_path,
                trainer_module_path=trainer_module_path,
                gcs_output_path=gcs_base_path,
                run_id=run_id,
            )

            # 7. Update training run with Cloud Build info
            training_run.cloud_build_id = build_id
            training_run.cloud_build_run_id = run_id
            training_run.status = TrainingRun.STATUS_SUBMITTING

            # Initialize stage_details with 8 stages
            training_run.stage_details = [
                {'name': 'Compile', 'status': 'running', 'duration_seconds': None},
                {'name': 'Examples', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Stats', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Schema', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Transform', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Train', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Evaluator', 'status': 'pending', 'duration_seconds': None},
                {'name': 'Pusher', 'status': 'pending', 'duration_seconds': None},
            ]
            training_run.current_stage = 'compile'
            training_run.save(update_fields=[
                'cloud_build_id', 'cloud_build_run_id', 'status',
                'stage_details', 'current_stage'
            ])

            logger.info(f"Cloud Build triggered: {build_id} (run_id: {run_id})")
            return training_run

        except Exception as e:
            logger.exception(f"Error submitting training pipeline: {e}")
            training_run.status = TrainingRun.STATUS_FAILED
            training_run.error_message = str(e)
            training_run.error_stage = 'submit'
            training_run.save(update_fields=['status', 'error_message', 'error_stage'])
            raise TrainingServiceError(str(e))

    def _upload_to_gcs(self, content: str, blob_path: str) -> str:
        """
        Upload content to GCS.

        Args:
            content: String content to upload
            blob_path: Path within the artifacts bucket

        Returns:
            Full GCS path (gs://bucket/path)
        """
        bucket = self.storage_client.bucket(self.ARTIFACTS_BUCKET)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(content, content_type='text/plain')

        return f"gs://{self.ARTIFACTS_BUCKET}/{blob_path}"

    def _trigger_cloud_build(
        self,
        training_run: TrainingRun,
        bigquery_query: str,
        split_queries: Optional[dict],
        transform_module_path: str,
        trainer_module_path: str,
        gcs_output_path: str,
        run_id: str,
    ) -> str:
        """
        Trigger Cloud Build to compile and submit TFX training pipeline.

        This extends the Experiments pattern with:
        - GPU configuration for Trainer component
        - Evaluator component for model blessing
        - Pusher component for Model Registry

        Args:
            training_run: TrainingRun instance
            bigquery_query: BigQuery SQL query
            split_queries: Dict with train/eval/test queries (for temporal splits), or None
            transform_module_path: GCS path to transform_module.py
            trainer_module_path: GCS path to trainer_module.py
            gcs_output_path: GCS path for output artifacts
            run_id: Unique identifier for this run

        Returns:
            Cloud Build build ID
        """
        from google.cloud.devtools import cloudbuild_v1

        client = cloudbuild_v1.CloudBuildClient()

        # Base64 encode queries to avoid shell escaping issues
        query_b64 = base64.b64encode(bigquery_query.encode()).decode()

        bucket = self.storage_client.bucket(self.STAGING_BUCKET)

        # Upload the compile script to GCS
        script_path = f"build_scripts/{run_id}/training_compile_and_submit.py"
        blob = bucket.blob(script_path)
        blob.upload_from_string(self._get_compile_script(), content_type='text/plain')
        logger.info(f"Uploaded compile script to gs://{self.STAGING_BUCKET}/{script_path}")

        # For temporal strategies, upload split queries to GCS as JSON
        split_queries_blob_path = ""
        if split_queries:
            split_queries_blob_path = f"build_scripts/{run_id}/split_queries.json"
            split_blob = bucket.blob(split_queries_blob_path)
            split_blob.upload_from_string(json.dumps(split_queries), content_type='application/json')
            logger.info(f"Uploaded split queries to gs://{self.STAGING_BUCKET}/{split_queries_blob_path}")

        # Extract training configuration
        training_params = training_run.training_params or {}
        gpu_config = training_run.gpu_config or {}
        evaluator_config = training_run.evaluator_config or {}

        epochs = training_params.get('epochs', 100)
        batch_size = training_params.get('batch_size', 8192)
        learning_rate = training_params.get('learning_rate', 0.01)
        split_strategy = training_params.get('split_strategy', 'strict_time')

        # GPU configuration
        # Default to T4 (validated working in europe-west4 with 2x quota approved)
        gpu_type = gpu_config.get('gpu_type', 'NVIDIA_TESLA_T4')
        gpu_count = gpu_config.get('gpu_count', 2)
        machine_type = gpu_config.get('machine_type', 'n1-standard-16')
        preemptible = gpu_config.get('preemptible', True)

        # Evaluator configuration
        evaluator_enabled = evaluator_config.get('enabled', True)
        blessing_threshold = evaluator_config.get('blessing_threshold', {})
        blessing_metric = blessing_threshold.get('metric', 'recall_at_100')
        blessing_min_value = blessing_threshold.get('min_value', 0.40)

        # Model name for registry
        model_name = training_run.name or f"{self.ml_model.name}-v{training_run.run_number}"

        # Use pre-built TFX compiler image (same as Experiments)
        tfx_compiler_image = getattr(
            settings, 'TFX_COMPILER_IMAGE',
            'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest'
        )
        logger.info(f"Using TFX compiler image: {tfx_compiler_image}")

        # Build command with optional split queries and training-specific parameters
        split_args = ""
        if split_queries_blob_path:
            split_args = f'    --split-queries-gcs-path="{split_queries_blob_path}" \\\n'

        build = cloudbuild_v1.Build(
            steps=[
                cloudbuild_v1.BuildStep(
                    name=tfx_compiler_image,
                    entrypoint='bash',
                    args=[
                        '-c',
                        f'''
set -e
echo "TFX Training Pipeline Compiler"
python -c "import tfx; print(f'TFX version: {{tfx.__version__}}')"
python -c "from google.cloud import storage; storage.Client().bucket('{self.STAGING_BUCKET}').blob('{script_path}').download_to_filename('/tmp/training_compile_and_submit.py')"
python /tmp/training_compile_and_submit.py \\
    --run-id="{run_id}" \\
    --staging-bucket="{self.STAGING_BUCKET}" \\
    --bigquery-query-b64="{query_b64}" \\
{split_args}    --transform-module-path="{transform_module_path}" \\
    --trainer-module-path="{trainer_module_path}" \\
    --output-path="{gcs_output_path}" \\
    --epochs="{epochs}" \\
    --batch-size="{batch_size}" \\
    --learning-rate="{learning_rate}" \\
    --split-strategy="{split_strategy}" \\
    --gpu-type="{gpu_type}" \\
    --gpu-count="{gpu_count}" \\
    --machine-type="{machine_type}" \\
    --preemptible="{str(preemptible).lower()}" \\
    --evaluator-enabled="{str(evaluator_enabled).lower()}" \\
    --blessing-metric="{blessing_metric}" \\
    --blessing-min-value="{blessing_min_value}" \\
    --model-name="{model_name}" \\
    --project-id="{self.project_id}" \\
    --dataflow-region="{self.DATAFLOW_REGION}" \\
    --gpu-training-region="{self.GPU_TRAINING_REGION}"
'''
# NOTE: Dataflow runs in DATAFLOW_REGION (europe-central2) where data lives
# Trainer runs in GPU_TRAINING_REGION (europe-west4) where GPUs are available
                    ],
                )
            ],
            timeout={'seconds': 1800},  # 30 minutes (longer than experiments due to GPU compilation)
            options=cloudbuild_v1.BuildOptions(
                logging=cloudbuild_v1.BuildOptions.LoggingMode.CLOUD_LOGGING_ONLY,
                machine_type=cloudbuild_v1.BuildOptions.MachineType.E2_HIGHCPU_8,
            ),
        )

        # Trigger build
        operation = client.create_build(project_id=self.project_id, build=build)

        # Get build ID from operation metadata
        build_id = operation.metadata.build.id
        logger.info(f"Cloud Build started: {build_id}")

        return build_id

    def _get_compile_script(self) -> str:
        """
        Return the TFX training compile and submit script content.

        This extends the Experiments script with:
        - Evaluator component for model blessing
        - Pusher component for Model Registry
        - GPU configuration for Trainer
        - 3-way data split (train/eval/test with 16:3:1 ratio)
        """
        return '''
import argparse
import json
import logging
import os
import tempfile
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_training_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    bigquery_query: str,
    split_queries: Optional[dict],
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    project_id: str,
    # GPU training must run in europe-west4 (not europe-central2) due to regional GPU limitations
    # See: https://docs.cloud.google.com/vertex-ai/docs/general/locations
    gpu_training_region: str = 'europe-west4',
    # Dataflow region for StatisticsGen/Transform - should be where data lives
    # to avoid resource exhaustion in GPU-heavy regions
    dataflow_region: str = 'europe-central2',
    epochs: int = 100,
    batch_size: int = 8192,
    learning_rate: float = 0.01,
    split_strategy: str = 'strict_time',
    # GPU configuration - T4 validated working in europe-west4 (2x T4 quota approved)
    gpu_type: str = 'NVIDIA_TESLA_T4',
    gpu_count: int = 2,
    machine_type: str = 'n1-standard-16',
    preemptible: bool = True,
    # Evaluator configuration
    evaluator_enabled: bool = True,
    blessing_metric: str = 'recall_at_100',
    blessing_min_value: float = 0.40,
    # Model registry
    model_name: str = 'recommender-model',
    train_steps: Optional[int] = None,
    eval_steps: Optional[int] = None,
):
    """
    Create 8-stage TFX training pipeline.

    Components:
    1. BigQueryExampleGen - Data extraction with 3-way split
    2. StatisticsGen - TFDV statistics
    3. SchemaGen - Schema inference
    4. Transform - Preprocessing with vocabulary
    5. Trainer - GPU-enabled TFRS training
    6. Evaluator - Model validation with blessing threshold
    7. Pusher - Model Registry upload
    """
    from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
    from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer, Evaluator, Pusher
    from tfx.proto import example_gen_pb2, trainer_pb2, transform_pb2, pusher_pb2
    from tfx.orchestration import pipeline as tfx_pipeline
    from tfx.dsl.components.base import executor_spec
    from tfx.extensions.google_cloud_ai_platform.trainer import executor as ai_platform_trainer_executor
    # Constants must be imported from tfx.v1 (not exported from tfx.extensions directly in TFX 1.15)
    from tfx.v1.extensions.google_cloud_ai_platform import (
        ENABLE_VERTEX_KEY,
        VERTEX_REGION_KEY,
        TRAINING_ARGS_KEY,
    )
    import tensorflow_model_analysis as tfma

    logger.info(f"Creating TFX training pipeline: {pipeline_name}")
    logger.info(f"  Dataflow region: {dataflow_region} (StatisticsGen, Transform)")
    logger.info(f"  GPU training region: {gpu_training_region} (Trainer with {gpu_count}x {gpu_type})")
    logger.info(f"  Machine type: {machine_type}")
    logger.info(f"  Evaluator: enabled={evaluator_enabled}, threshold={blessing_metric}>={blessing_min_value}")

    # Configure split based on strategy
    # Training uses 3-way split: train/eval/test (16:3:1 ratio = 80%/15%/5%)
    if split_strategy == 'random':
        logger.info("Using hash-based 80/15/5 split (train/eval/test)")
        output_config = example_gen_pb2.Output(
            split_config=example_gen_pb2.SplitConfig(
                splits=[
                    example_gen_pb2.SplitConfig.Split(name="train", hash_buckets=16),
                    example_gen_pb2.SplitConfig.Split(name="eval", hash_buckets=3),
                    example_gen_pb2.SplitConfig.Split(name="test", hash_buckets=1),
                ]
            )
        )
        example_gen = BigQueryExampleGen(
            query=bigquery_query,
            output_config=output_config,
            custom_config={'project': project_id}
        )
    else:
        # time_holdout and strict_time: Use multiple input splits
        if not split_queries:
            raise ValueError(f"split_queries required for split_strategy={split_strategy}")

        logger.info(f"Using multiple input splits for {split_strategy}")
        input_config = example_gen_pb2.Input(splits=[
            example_gen_pb2.Input.Split(name='train', pattern=split_queries['train']),
            example_gen_pb2.Input.Split(name='eval', pattern=split_queries['eval']),
            example_gen_pb2.Input.Split(name='test', pattern=split_queries['test']),
        ])
        example_gen = BigQueryExampleGen(
            input_config=input_config,
            output_config=example_gen_pb2.Output(),
            custom_config={'project': project_id}
        )

    # 2. StatisticsGen
    statistics_gen = StatisticsGen(examples=example_gen.outputs["examples"])

    # 3. SchemaGen
    schema_gen = SchemaGen(statistics=statistics_gen.outputs["statistics"])

    # 4. Transform - analyze only train/eval (no test to prevent leakage)
    transform = Transform(
        examples=example_gen.outputs["examples"],
        schema=schema_gen.outputs["schema"],
        module_file=transform_module_path,
        splits_config=transform_pb2.SplitsConfig(
            analyze=['train', 'eval'],  # NO test - avoid data leakage
            transform=['train', 'eval', 'test']  # But transform all for evaluation
        ),
    )

    # 5. Trainer with GPU configuration
    train_args = trainer_pb2.TrainArgs(num_steps=train_steps)
    eval_args = trainer_pb2.EvalArgs(num_steps=eval_steps)

    # GPU-enabled TFX trainer image
    gpu_trainer_image = f'europe-central2-docker.pkg.dev/{project_id}/tfx-builder/tfx-trainer-gpu:latest'
    logger.info(f"Using GPU trainer image: {gpu_trainer_image}")

    custom_config = {
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "gcs_output_path": output_path,
        "gpu_enabled": True,
        "gpu_count": gpu_count,
        # CRITICAL: Enable Vertex AI mode (without this, GenericExecutor uses deprecated
        # Cloud ML Engine API which doesn't support worker_pool_specs)
        ENABLE_VERTEX_KEY: True,
        VERTEX_REGION_KEY: gpu_training_region,
        # Training args for Vertex AI CustomJob - GenericExecutor spawns a separate
        # Custom Job with these GPU resources
        TRAINING_ARGS_KEY: {
            "project": project_id,
            "worker_pool_specs": [{
                "machine_spec": {
                    "machine_type": machine_type,
                    "accelerator_type": gpu_type,
                    "accelerator_count": gpu_count,
                },
                "replica_count": 1,
                "container_spec": {
                    "image_uri": gpu_trainer_image,
                },
            }],
        },
    }

    logger.info(f"Configured Vertex AI GPU training: {gpu_count}x {gpu_type} on {machine_type}")

    # Use GenericExecutor to spawn a separate Vertex AI Custom Job for training.
    # This ensures the Trainer runs on a machine with GPU resources allocated.
    # The Custom Job uses worker_pool_specs from ai_platform_training_args above.
    trainer = Trainer(
        module_file=trainer_module_path,
        examples=transform.outputs["transformed_examples"],
        transform_graph=transform.outputs["transform_graph"],
        schema=schema_gen.outputs["schema"],
        train_args=train_args,
        eval_args=eval_args,
        custom_executor_spec=executor_spec.ExecutorClassSpec(
            ai_platform_trainer_executor.GenericExecutor
        ),
        custom_config=custom_config,
    )

    components = [example_gen, statistics_gen, schema_gen, transform, trainer]

    # 6. Evaluator - Model validation with blessing threshold
    if evaluator_enabled:
        # Configure TFMA evaluation with blessing threshold
        # Map blessing_metric to actual TFMA metric name
        metric_name_map = {
            'recall_at_5': 'factorized_top_k/top_5_categorical_accuracy',
            'recall_at_10': 'factorized_top_k/top_10_categorical_accuracy',
            'recall_at_50': 'factorized_top_k/top_50_categorical_accuracy',
            'recall_at_100': 'factorized_top_k/top_100_categorical_accuracy',
            'loss': 'loss',
            'rmse': 'root_mean_squared_error',
            'mae': 'mean_absolute_error',
        }
        tfma_metric_name = metric_name_map.get(blessing_metric, blessing_metric)

        # For loss/rmse/mae, lower is better; for recall, higher is better
        lower_is_better_metrics = ['loss', 'rmse', 'mae', 'root_mean_squared_error', 'mean_absolute_error']
        if blessing_metric in lower_is_better_metrics or tfma_metric_name in lower_is_better_metrics:
            # For lower-is-better metrics, use upper_bound threshold
            threshold_config = tfma.MetricThreshold(
                value_threshold=tfma.GenericValueThreshold(
                    upper_bound={'value': blessing_min_value}
                )
            )
        else:
            # For higher-is-better metrics (recall), use lower_bound threshold
            threshold_config = tfma.MetricThreshold(
                value_threshold=tfma.GenericValueThreshold(
                    lower_bound={'value': blessing_min_value}
                )
            )

        eval_config = tfma.EvalConfig(
            model_specs=[
                tfma.ModelSpec(label_key='label')  # Will be ignored for retrieval models
            ],
            slicing_specs=[
                tfma.SlicingSpec(),  # Overall metrics (no slicing)
            ],
            metrics_specs=[
                tfma.MetricsSpec(
                    metrics=[
                        tfma.MetricConfig(class_name='ExampleCount'),
                    ],
                    thresholds={
                        tfma_metric_name: threshold_config
                    }
                )
            ]
        )

        evaluator = Evaluator(
            examples=transform.outputs['transformed_examples'],
            model=trainer.outputs['model'],
            eval_config=eval_config,
        )
        components.append(evaluator)
        logger.info(f"Added Evaluator with threshold: {tfma_metric_name} >= {blessing_min_value}")

    # 7. Pusher - Register model to Vertex AI Model Registry
    # Push regardless of blessing status to allow manual override for not-blessed models
    pusher = Pusher(
        model=trainer.outputs['model'],
        push_destination=pusher_pb2.PushDestination(
            filesystem=pusher_pb2.PushDestination.Filesystem(
                base_directory=os.path.join(output_path, 'pushed_model')
            )
        ),
    )
    components.append(pusher)

    # Configure Dataflow for StatisticsGen and Transform
    # Dataflow runs in europe-central2 (where data lives) to avoid resource exhaustion
    # in GPU-heavy regions like europe-west4
    staging_bucket = f'{project_id}-pipeline-staging'
    beam_pipeline_args = [
        '--runner=DataflowRunner',
        f'--project={project_id}',
        f'--region={dataflow_region}',
        f'--temp_location=gs://{staging_bucket}/dataflow_temp',
        f'--staging_location=gs://{staging_bucket}/dataflow_staging',
        '--machine_type=n1-standard-4',
        '--disk_size_gb=50',
        '--experiments=use_runner_v2',
        '--max_num_workers=10',
        '--autoscaling_algorithm=THROUGHPUT_BASED',
    ]

    pipeline = tfx_pipeline.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=components,
        enable_cache=False,
        beam_pipeline_args=beam_pipeline_args,
    )
    logger.info(f"TFX training pipeline created with {len(components)} components")
    return pipeline


def compile_pipeline(
    pipeline,
    output_file: str,
    project_id: str = 'b2b-recs',
) -> str:
    """
    Compile TFX pipeline to Vertex AI Pipelines format.

    GPU resources for the Trainer are configured via GenericExecutor and
    ai_platform_training_args in create_training_pipeline(), not here.
    GenericExecutor spawns a separate Vertex AI Custom Job with the GPU config.
    """
    from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner
    logger.info(f"Compiling pipeline to: {output_file}")

    # Use GPU-enabled TFX image as default for all components
    custom_image = f'europe-central2-docker.pkg.dev/{project_id}/tfx-builder/tfx-trainer-gpu:latest'
    logger.info(f"Using TFX image: {custom_image}")

    runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
        config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(
            default_image=custom_image
        ),
        output_filename=output_file
    )
    runner.run(pipeline)
    logger.info(f"Pipeline compiled successfully: {output_file}")

    # NOTE: No post-processing needed. GPU resources are handled by GenericExecutor
    # which spawns a Vertex AI Custom Job with worker_pool_specs from custom_config.

    return output_file


def submit_to_vertex_ai(template_path: str, display_name: str, project_id: str, region: str) -> str:
    from google.cloud import aiplatform
    logger.info(f"Initializing Vertex AI: project={project_id}, region={region}")
    aiplatform.init(project=project_id, location=region)
    logger.info(f"Creating pipeline job: {display_name}")
    pipeline_job = aiplatform.PipelineJob(
        display_name=display_name[:128],
        template_path=template_path,
        enable_caching=False,
    )
    logger.info("Submitting pipeline job to Vertex AI...")
    pipeline_job.submit()
    resource_name = pipeline_job.resource_name
    logger.info(f"Pipeline submitted: {resource_name}")
    return resource_name


def write_result_to_gcs(bucket_name: str, blob_path: str, result: dict):
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    content = json.dumps(result, indent=2)
    blob.upload_from_string(content, content_type="application/json")
    logger.info(f"Result written to gs://{bucket_name}/{blob_path}")


def main():
    import base64
    parser = argparse.ArgumentParser(description="Compile and submit TFX training pipeline")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--staging-bucket", required=True)
    parser.add_argument("--bigquery-query-b64", required=True)
    parser.add_argument("--split-queries-gcs-path", default="")
    parser.add_argument("--transform-module-path", required=True)
    parser.add_argument("--trainer-module-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--split-strategy", default="strict_time")
    # GPU configuration
    # T4 GPUs validated working in europe-west4 (2x T4 quota approved)
    parser.add_argument("--gpu-type", default="NVIDIA_TESLA_T4")
    parser.add_argument("--gpu-count", type=int, default=2)
    parser.add_argument("--machine-type", default="n1-standard-16")
    parser.add_argument("--preemptible", default="true")
    # Evaluator configuration
    parser.add_argument("--evaluator-enabled", default="true")
    parser.add_argument("--blessing-metric", default="recall_at_100")
    parser.add_argument("--blessing-min-value", type=float, default=0.40)
    # Model registry
    parser.add_argument("--model-name", default="recommender-model")
    parser.add_argument("--project-id", required=True)
    # Region configuration
    # - Dataflow region: where StatisticsGen/Transform run (same as data for efficiency)
    # - GPU training region: where Trainer runs (must have GPU quota)
    parser.add_argument("--dataflow-region", default="europe-central2",
                        help="Region for Dataflow jobs (StatisticsGen, Transform)")
    parser.add_argument("--gpu-training-region", default="europe-west4",
                        help="Region for GPU training (Trainer component)")
    args = parser.parse_args()

    # Decode the base64 query
    bigquery_query = base64.b64decode(args.bigquery_query_b64).decode("utf-8")
    logger.info(f"Decoded BigQuery query: {bigquery_query[:100]}...")

    # Download split queries from GCS for temporal strategies
    split_queries = None
    if args.split_queries_gcs_path:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(args.staging_bucket)
        blob = bucket.blob(args.split_queries_gcs_path)
        split_queries = json.loads(blob.download_as_text())
        logger.info(f"Downloaded split queries from GCS")

    # Parse boolean args
    preemptible = args.preemptible.lower() == 'true'
    evaluator_enabled = args.evaluator_enabled.lower() == 'true'

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_file = os.path.join(temp_dir, f"pipeline_{args.run_id}.json")
            pipeline = create_training_pipeline(
                pipeline_name=f"training-{args.run_id}",
                pipeline_root=f"gs://{args.staging_bucket}/pipeline_root/{args.run_id}",
                bigquery_query=bigquery_query,
                split_queries=split_queries,
                transform_module_path=args.transform_module_path,
                trainer_module_path=args.trainer_module_path,
                output_path=args.output_path,
                project_id=args.project_id,
                gpu_training_region=args.gpu_training_region,
                dataflow_region=args.dataflow_region,
                epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.learning_rate,
                split_strategy=args.split_strategy,
                gpu_type=args.gpu_type,
                gpu_count=args.gpu_count,
                machine_type=args.machine_type,
                preemptible=preemptible,
                evaluator_enabled=evaluator_enabled,
                blessing_metric=args.blessing_metric,
                blessing_min_value=args.blessing_min_value,
                model_name=args.model_name,
            )
            compile_pipeline(
                pipeline,
                pipeline_file,
                project_id=args.project_id,
            )
            display_name = f"training-{args.run_id}"
            # Pipeline orchestration runs in dataflow_region (europe-central2)
            # Trainer component spawns its own Custom Job in gpu_training_region (europe-west4)
            resource_name = submit_to_vertex_ai(pipeline_file, display_name, args.project_id, args.dataflow_region)
            result = {
                "success": True,
                "run_id": args.run_id,
                "vertex_pipeline_job_name": resource_name,
                "display_name": display_name,
                "evaluator_enabled": evaluator_enabled,
                "model_name": args.model_name,
            }
            write_result_to_gcs(args.staging_bucket, f"build_results/{args.run_id}.json", result)
            logger.info("Training pipeline compilation and submission completed successfully")
            print(f"PIPELINE_JOB_NAME={resource_name}")
    except Exception as e:
        logger.error(f"Pipeline compilation/submission failed: {e}")
        error_result = {"success": False, "run_id": args.run_id, "error": str(e)}
        try:
            write_result_to_gcs(args.staging_bucket, f"build_results/{args.run_id}.json", error_result)
        except Exception as gcs_error:
            logger.error(f"Failed to write error to GCS: {gcs_error}")
        raise


if __name__ == "__main__":
    main()
'''
