"""
Pipeline Service for submitting and monitoring Vertex AI pipelines.

This module handles:
- Uploading generated TFX code to GCS
- Submitting pipelines to Vertex AI
- Polling pipeline status
- Extracting and storing results
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class PipelineServiceError(Exception):
    """Custom exception for pipeline service errors."""
    pass


class PipelineService:
    """
    Service for managing Vertex AI Pipeline execution.

    Responsibilities:
    - Upload generated code to GCS
    - Submit pipelines to Vertex AI
    - Poll pipeline status
    - Extract and store results
    """

    def __init__(self):
        self.project = getattr(settings, 'VERTEX_AI_PROJECT', 'b2b-recs')
        self.location = getattr(settings, 'VERTEX_AI_LOCATION', 'europe-central2')
        self.quicktest_bucket = getattr(settings, 'GCS_QUICKTEST_BUCKET', 'b2b-recs-quicktest-artifacts')
        self.staging_bucket = getattr(settings, 'GCS_PIPELINE_STAGING_BUCKET', 'b2b-recs-pipeline-staging')

        self._aiplatform_initialized = False
        self._storage_client = None

    def _ensure_aiplatform_initialized(self):
        """Lazy-initialize Vertex AI SDK."""
        if not self._aiplatform_initialized:
            try:
                from google.cloud import aiplatform
                aiplatform.init(project=self.project, location=self.location)
                self._aiplatform_initialized = True
                logger.info(f"Vertex AI initialized for project={self.project}, location={self.location}")
            except ImportError:
                raise PipelineServiceError(
                    "google-cloud-aiplatform package not installed. "
                    "Run: pip install google-cloud-aiplatform"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI: {e}")
                raise PipelineServiceError(f"Failed to initialize Vertex AI: {e}")

    @property
    def storage_client(self):
        """Lazy-load GCS client."""
        if self._storage_client is None:
            try:
                from google.cloud import storage
                self._storage_client = storage.Client(project=self.project)
            except ImportError:
                raise PipelineServiceError(
                    "google-cloud-storage package not installed. "
                    "Run: pip install google-cloud-storage"
                )
            except Exception as e:
                logger.error(f"Failed to initialize GCS client: {e}")
                raise PipelineServiceError(f"Failed to connect to GCS: {e}")
        return self._storage_client

    # =========================================================================
    # Quick Test Submission
    # =========================================================================

    def submit_quick_test(
        self,
        feature_config,
        model_config,
        trainer_code: str,
        epochs: int = 10,
        batch_size: int = 4096,
        learning_rate: float = 0.001,
        user=None
    ):
        """
        Submit a Quick Test pipeline to Vertex AI.

        Args:
            feature_config: The FeatureConfig to test (defines feature transformations)
            model_config: The ModelConfig to test (defines neural network architecture)
            trainer_code: Generated trainer code (from TrainerModuleGenerator)
            epochs: Number of training epochs
            batch_size: Training batch size
            learning_rate: Learning rate
            user: User who initiated the test

        Returns:
            QuickTest instance with pipeline job info
        """
        from ml_platform.models import QuickTest

        # Create QuickTest record with both configs
        quick_test = QuickTest.objects.create(
            feature_config=feature_config,
            model_config=model_config,  # Link to ModelConfig
            created_by=user,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            status=QuickTest.STATUS_PENDING,
            stage_details=self._get_initial_stage_details()
        )

        # Store trainer code for upload (not in model anymore)
        quick_test._trainer_code = trainer_code

        try:
            # Update status to submitting
            quick_test.status = QuickTest.STATUS_SUBMITTING
            quick_test.save(update_fields=['status'])

            # 1. Upload generated code to GCS
            gcs_path = self._upload_code_to_gcs(feature_config, quick_test, trainer_code)
            quick_test.gcs_artifacts_path = gcs_path

            # 2. Build pipeline parameters
            pipeline_params = self._build_pipeline_params(
                feature_config=feature_config,
                quick_test=quick_test,
                gcs_path=gcs_path
            )

            # 3. Submit to Vertex AI
            job = self._submit_pipeline(pipeline_params, quick_test)

            # 4. Update QuickTest with job info
            quick_test.vertex_pipeline_job_name = job.resource_name
            quick_test.vertex_pipeline_job_id = job.name
            quick_test.status = QuickTest.STATUS_RUNNING
            quick_test.submitted_at = timezone.now()
            quick_test.started_at = timezone.now()
            quick_test.save()

            logger.info(f"QuickTest {quick_test.pk} submitted: {job.resource_name}")
            return quick_test

        except Exception as e:
            logger.exception(f"Failed to submit QuickTest {quick_test.pk}")
            quick_test.status = QuickTest.STATUS_FAILED
            quick_test.error_message = str(e)
            quick_test.completed_at = timezone.now()
            quick_test.save()
            raise

    def _get_initial_stage_details(self) -> list:
        """Create initial stage details structure."""
        return [
            {"name": "ExampleGen", "status": "pending", "duration_seconds": None},
            {"name": "StatisticsGen", "status": "pending", "duration_seconds": None},
            {"name": "SchemaGen", "status": "pending", "duration_seconds": None},
            {"name": "Transform", "status": "pending", "duration_seconds": None},
            {"name": "Trainer", "status": "pending", "duration_seconds": None},
        ]

    def _upload_code_to_gcs(self, feature_config, quick_test, trainer_code: str) -> str:
        """
        Upload Transform and Trainer code to GCS.

        Args:
            feature_config: FeatureConfig with generated_transform_code
            quick_test: QuickTest record
            trainer_code: Generated trainer code (passed explicitly, not from feature_config)

        Returns:
            GCS path prefix (e.g., gs://bucket/quicktest-42/)
        """
        bucket = self.storage_client.bucket(self.quicktest_bucket)
        prefix = f"quicktest-{quick_test.pk}"

        # Upload Transform code (from FeatureConfig)
        transform_blob = bucket.blob(f"{prefix}/transform_module.py")
        transform_blob.upload_from_string(
            feature_config.generated_transform_code,
            content_type='text/x-python'
        )
        logger.info(f"Uploaded transform_module.py to gs://{self.quicktest_bucket}/{prefix}/")

        # Upload Trainer code (generated at runtime from FeatureConfig + ModelConfig)
        trainer_blob = bucket.blob(f"{prefix}/trainer_module.py")
        trainer_blob.upload_from_string(
            trainer_code,
            content_type='text/x-python'
        )
        logger.info(f"Uploaded trainer_module.py to gs://{self.quicktest_bucket}/{prefix}/")

        gcs_path = f"gs://{self.quicktest_bucket}/{prefix}"
        return gcs_path

    def _build_pipeline_params(
        self,
        feature_config,
        quick_test,
        gcs_path: str
    ) -> Dict[str, Any]:
        """Build parameters for the pipeline."""
        dataset = feature_config.dataset

        # Generate the SQL query from dataset configuration
        # This uses the existing BigQueryService that handles joins, filters, etc.
        from ml_platform.datasets.services import BigQueryService
        bq_service = BigQueryService(dataset.model_endpoint, dataset=dataset)
        query_sql = bq_service.generate_query(dataset)

        return {
            # Data source - SQL query instead of direct table reference
            "bigquery_project": self.project,
            "bigquery_query": query_sql,

            # Module paths
            "transform_module_path": f"{gcs_path}/transform_module.py",
            "trainer_module_path": f"{gcs_path}/trainer_module.py",

            # Training params
            "epochs": quick_test.epochs,
            "batch_size": quick_test.batch_size,
            "learning_rate": quick_test.learning_rate,

            # Output paths
            "output_path": gcs_path,
            "pipeline_root": f"gs://{self.staging_bucket}/runs/quicktest-{quick_test.pk}",

            # Compute settings
            "machine_type": getattr(settings, 'QUICKTEST_MACHINE_TYPE', 'e2-standard-4'),
        }

    def _submit_pipeline(self, params: Dict[str, Any], quick_test):
        """
        Submit pipeline to Vertex AI.

        Compiles and submits the KFP v2 pipeline defined in pipeline_builder.py.
        """
        self._ensure_aiplatform_initialized()
        from google.cloud import aiplatform

        try:
            from ml_platform.pipelines.pipeline_builder import (
                get_pipeline_template_path,
                quicktest_pipeline
            )
        except ImportError as e:
            raise PipelineServiceError(f"Pipeline builder not available: {e}")

        # Get compiled pipeline template
        try:
            template_path = get_pipeline_template_path()
        except Exception as e:
            raise PipelineServiceError(f"Failed to get pipeline template: {e}")

        # Create pipeline job
        job = aiplatform.PipelineJob(
            display_name=f"quicktest-{quick_test.pk}-{quick_test.feature_config.name[:20]}",
            template_path=template_path,
            parameter_values={
                "bigquery_query": params["bigquery_query"],
                "transform_module_path": params["transform_module_path"],
                "trainer_module_path": params["trainer_module_path"],
                "output_path": params["output_path"],
                "pipeline_root": params["pipeline_root"],
                "epochs": params["epochs"],
                "batch_size": params["batch_size"],
                "learning_rate": params["learning_rate"],
                "machine_type": params["machine_type"],
                "project_id": self.project,
            },
            pipeline_root=params["pipeline_root"],
            project=self.project,
            location=self.location,
        )

        # Submit the job
        service_account = f"django-app@{self.project}.iam.gserviceaccount.com"
        job.submit(service_account=service_account)

        logger.info(f"Pipeline job submitted: {job.resource_name}")
        return job

    # =========================================================================
    # Status Polling
    # =========================================================================

    def get_pipeline_status(self, quick_test) -> Dict[str, Any]:
        """
        Get current status of a pipeline from Vertex AI.

        Returns:
            Dict with status, stages, and progress info
        """
        if not quick_test.vertex_pipeline_job_name:
            return {
                "status": quick_test.status,
                "current_stage": quick_test.current_stage,
                "progress_percent": quick_test.progress_percent,
                "stage_details": quick_test.stage_details,
            }

        try:
            self._ensure_aiplatform_initialized()
            from google.cloud import aiplatform

            job = aiplatform.PipelineJob.get(quick_test.vertex_pipeline_job_name)

            # Parse job state
            state = job.state.name if job.state else "UNKNOWN"

            # Map Vertex AI state to our status
            from ml_platform.models import QuickTest
            status_map = {
                "PIPELINE_STATE_PENDING": QuickTest.STATUS_PENDING,
                "PIPELINE_STATE_RUNNING": QuickTest.STATUS_RUNNING,
                "PIPELINE_STATE_SUCCEEDED": QuickTest.STATUS_COMPLETED,
                "PIPELINE_STATE_FAILED": QuickTest.STATUS_FAILED,
                "PIPELINE_STATE_CANCELLED": QuickTest.STATUS_CANCELLED,
                "PIPELINE_STATE_CANCELLING": QuickTest.STATUS_RUNNING,
            }

            new_status = status_map.get(state, quick_test.status)

            # Parse task details for stage progress
            stage_details = self._parse_task_details(job)
            current_stage = self._determine_current_stage(stage_details)

            return {
                "status": new_status,
                "current_stage": current_stage,
                "progress_percent": self._calculate_progress(stage_details),
                "stage_details": stage_details,
                "vertex_state": state,
            }

        except Exception as e:
            logger.exception(f"Failed to get status for QuickTest {quick_test.pk}")
            return {
                "status": quick_test.status,
                "current_stage": quick_test.current_stage,
                "progress_percent": quick_test.progress_percent,
                "stage_details": quick_test.stage_details,
                "error": str(e)
            }

    def _parse_task_details(self, job) -> list:
        """Parse Vertex AI job task details into our stage format."""
        # Map component names to our stage names
        component_map = {
            "examplegen": "ExampleGen",
            "bigqueryexamplegen": "ExampleGen",
            "statisticsgen": "StatisticsGen",
            "schemagen": "SchemaGen",
            "transform": "Transform",
            "trainer": "Trainer",
        }

        stages = []
        task_details = getattr(job, 'task_details', []) or []

        for task in task_details:
            task_name = getattr(task, 'task_name', '').lower()

            for key, stage_name in component_map.items():
                if key in task_name:
                    task_state = getattr(task, 'state', None)
                    state = task_state.name if task_state else "pending"

                    # Map task state to our status
                    if "SUCCEEDED" in state:
                        status = "completed"
                    elif "RUNNING" in state:
                        status = "running"
                    elif "FAILED" in state:
                        status = "failed"
                    else:
                        status = "pending"

                    # Calculate duration
                    duration = None
                    start_time = getattr(task, 'start_time', None)
                    end_time = getattr(task, 'end_time', None)
                    if start_time and end_time:
                        duration = int((end_time - start_time).total_seconds())

                    # Get error if any
                    error = None
                    task_error = getattr(task, 'error', None)
                    if task_error:
                        error = getattr(task_error, 'message', str(task_error))

                    stages.append({
                        "name": stage_name,
                        "status": status,
                        "duration_seconds": duration,
                        "error": error
                    })
                    break

        # Ensure all stages are present
        stage_names = [s["name"] for s in stages]
        for stage_name in ["ExampleGen", "StatisticsGen", "SchemaGen", "Transform", "Trainer"]:
            if stage_name not in stage_names:
                stages.append({
                    "name": stage_name,
                    "status": "pending",
                    "duration_seconds": None,
                    "error": None
                })

        # Sort by expected order
        order = ["ExampleGen", "StatisticsGen", "SchemaGen", "Transform", "Trainer"]
        stages.sort(key=lambda s: order.index(s["name"]) if s["name"] in order else 99)

        return stages

    def _determine_current_stage(self, stage_details: list) -> str:
        """Determine current stage from stage details."""
        for stage in stage_details:
            if stage["status"] == "running":
                return stage["name"].lower()
            if stage["status"] == "failed":
                return "failed"

        # Check if all completed
        if all(s["status"] == "completed" for s in stage_details):
            return "completed"

        return "pending"

    def _calculate_progress(self, stage_details: list) -> int:
        """Calculate progress percentage from stage details."""
        weights = {
            "ExampleGen": 20,
            "StatisticsGen": 10,
            "SchemaGen": 5,
            "Transform": 25,
            "Trainer": 40,
        }

        total = sum(weights.values())
        completed = 0

        for stage in stage_details:
            weight = weights.get(stage["name"], 0)
            if stage["status"] == "completed":
                completed += weight
            elif stage["status"] == "running":
                completed += weight * 0.5

        return int((completed / total) * 100)

    # =========================================================================
    # Results Extraction
    # =========================================================================

    def extract_results(self, quick_test) -> Dict[str, Any]:
        """
        Extract results from completed pipeline.

        Reads metrics from GCS output location.
        Handles both retrieval metrics (recall@K) and ranking metrics (RMSE/MAE).

        Tries metrics.json first, then falls back to training_metrics.json for
        detailed metrics (which stores training metrics as final_rmse, final_mae, etc.)
        """
        if not quick_test.gcs_artifacts_path:
            return {}

        try:
            # Parse GCS path
            gcs_path = quick_test.gcs_artifacts_path
            if gcs_path.startswith("gs://"):
                gcs_path = gcs_path[5:]

            bucket_name = gcs_path.split("/")[0]
            prefix = "/".join(gcs_path.split("/")[1:])

            bucket = self.storage_client.bucket(bucket_name)

            # Try metrics.json first
            metrics = {}
            metrics_blob = bucket.blob(f"{prefix}/metrics.json")
            if metrics_blob.exists():
                metrics_content = metrics_blob.download_as_string()
                metrics = json.loads(metrics_content)

            # Also try training_metrics.json for detailed metrics (final_rmse, test_rmse, etc.)
            training_metrics_blob = bucket.blob(f"{prefix}/training_metrics.json")
            final_metrics = {}
            if training_metrics_blob.exists():
                training_content = training_metrics_blob.download_as_string()
                training_data = json.loads(training_content)
                final_metrics = training_data.get('final_metrics', {})

            if not metrics and not final_metrics:
                logger.warning(f"No metrics files found at {quick_test.gcs_artifacts_path}")
                return {}

            # Determine model type from feature config
            feature_config = quick_test.feature_config
            config_type = getattr(feature_config, 'config_type', 'retrieval')

            result = {
                "loss": metrics.get("loss") or final_metrics.get("final_loss"),
                "vocabulary_stats": metrics.get("vocabulary_stats", {}),
            }

            if config_type == 'ranking':
                # Ranking model metrics
                # Training RMSE/MAE: check metrics.json first, then training_metrics.json (final_rmse/final_mae)
                # Note: final_val_rmse/final_val_mae are validation metrics from training
                result.update({
                    "rmse": (metrics.get("rmse") or metrics.get("root_mean_squared_error") or
                             final_metrics.get("final_val_rmse") or final_metrics.get("final_rmse")),
                    "mae": (metrics.get("mae") or metrics.get("mean_absolute_error") or
                            final_metrics.get("final_val_mae") or final_metrics.get("final_mae")),
                    "test_rmse": (metrics.get("test_rmse") or metrics.get("test_root_mean_squared_error") or
                                  final_metrics.get("test_rmse")),
                    "test_mae": (metrics.get("test_mae") or metrics.get("test_mean_absolute_error") or
                                 final_metrics.get("test_mae")),
                })
            else:
                # Retrieval model metrics
                result.update({
                    "recall_at_5": metrics.get("recall_at_5") or final_metrics.get("test_recall_at_5"),
                    "recall_at_10": metrics.get("recall_at_10") or final_metrics.get("test_recall_at_10"),
                    "recall_at_50": metrics.get("recall_at_50") or final_metrics.get("test_recall_at_50"),
                    "recall_at_100": metrics.get("recall_at_100") or final_metrics.get("test_recall_at_100"),
                })

            return result

        except Exception as e:
            logger.exception(f"Failed to extract results for QuickTest {quick_test.pk}")
            return {"error": str(e)}

    # =========================================================================
    # Pipeline Management
    # =========================================================================

    def cancel_pipeline(self, quick_test) -> bool:
        """Cancel a running pipeline."""
        if not quick_test.vertex_pipeline_job_name:
            return False

        try:
            self._ensure_aiplatform_initialized()
            from google.cloud import aiplatform

            job = aiplatform.PipelineJob.get(quick_test.vertex_pipeline_job_name)
            job.cancel()

            from ml_platform.models import QuickTest
            quick_test.status = QuickTest.STATUS_CANCELLED
            quick_test.completed_at = timezone.now()
            quick_test.save()

            logger.info(f"Cancelled QuickTest {quick_test.pk}")
            return True

        except Exception as e:
            logger.exception(f"Failed to cancel QuickTest {quick_test.pk}")
            return False

    def update_quick_test_status(self, quick_test):
        """
        Update QuickTest from Vertex AI status.
        Called by polling mechanism.
        """
        from ml_platform.models import QuickTest

        if quick_test.is_terminal:
            return quick_test

        status_info = self.get_pipeline_status(quick_test)

        # Update fields
        quick_test.status = status_info["status"]
        quick_test.current_stage = status_info["current_stage"]
        quick_test.progress_percent = status_info["progress_percent"]
        quick_test.stage_details = status_info["stage_details"]

        # If completed, extract results
        if quick_test.status == QuickTest.STATUS_COMPLETED:
            quick_test.completed_at = timezone.now()
            if quick_test.started_at:
                quick_test.duration_seconds = int(
                    (quick_test.completed_at - quick_test.started_at).total_seconds()
                )

            results = self.extract_results(quick_test)
            quick_test.loss = results.get("loss")
            quick_test.vocabulary_stats = results.get("vocabulary_stats", {})

            # Determine model type from feature config
            feature_config = quick_test.feature_config
            config_type = getattr(feature_config, 'config_type', 'retrieval')

            if config_type == 'ranking':
                # Ranking model metrics
                quick_test.rmse = results.get("rmse")
                quick_test.mae = results.get("mae")
                quick_test.test_rmse = results.get("test_rmse")
                quick_test.test_mae = results.get("test_mae")
            else:
                # Retrieval model metrics
                quick_test.recall_at_5 = results.get("recall_at_5")
                quick_test.recall_at_10 = results.get("recall_at_10")
                quick_test.recall_at_50 = results.get("recall_at_50")
                quick_test.recall_at_100 = results.get("recall_at_100")

            # Update FeatureConfig best metrics
            quick_test.feature_config.update_best_metrics(quick_test)

        elif quick_test.status == QuickTest.STATUS_FAILED:
            quick_test.completed_at = timezone.now()
            if quick_test.started_at:
                quick_test.duration_seconds = int(
                    (quick_test.completed_at - quick_test.started_at).total_seconds()
                )
            # Error message from stage details
            for stage in quick_test.stage_details:
                if stage.get("status") == "failed" and stage.get("error"):
                    quick_test.error_message = stage["error"]
                    quick_test.error_stage = stage["name"]
                    break

        quick_test.save()
        return quick_test
