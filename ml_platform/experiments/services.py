"""
Experiments Domain Services

Core business logic for running ML experiments (Quick Tests):
- Code generation orchestration (Transform + Trainer modules)
- TFX pipeline compilation and submission to Vertex AI
- Status monitoring and results extraction
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ExperimentServiceError(Exception):
    """Custom exception for experiment service errors."""
    pass


class ExperimentService:
    """
    Service for orchestrating ML experiments (Quick Tests).

    Handles the complete lifecycle:
    1. Generate transform code from FeatureConfig
    2. Generate trainer code from FeatureConfig + ModelConfig
    3. Generate SQL query with split/sampling
    4. Upload code to GCS
    5. Compile and submit TFX pipeline to Vertex AI
    6. Monitor status and extract results
    """

    # GCS bucket names
    ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
    STAGING_BUCKET = 'b2b-recs-pipeline-staging'

    # Vertex AI configuration
    REGION = 'europe-central2'
    PIPELINE_DISPLAY_NAME_PREFIX = 'quicktest'

    def __init__(self, model_endpoint):
        """
        Initialize with a ModelEndpoint instance.

        Args:
            model_endpoint: ModelEndpoint instance for GCP configuration
        """
        self.model_endpoint = model_endpoint
        self.project_id = model_endpoint.gcp_project_id or getattr(
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
                raise ExperimentServiceError(
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
                raise ExperimentServiceError(
                    "google-cloud-aiplatform package not installed"
                )

    def submit_quick_test(
        self,
        feature_config,
        model_config,
        user=None,
        split_strategy: str = 'random',
        holdout_days: int = 1,
        date_column: str = '',
        data_sample_percent: int = 100,
        epochs: int = None,
        batch_size: int = None,
        learning_rate: float = None,
    ):
        """
        Submit a new Quick Test pipeline to Vertex AI.

        Args:
            feature_config: FeatureConfig instance
            model_config: ModelConfig instance
            user: User who initiated the test (optional)
            split_strategy: 'random', 'time_holdout', or 'strict_time'
            holdout_days: Days to exclude for time-based strategies
            date_column: Column name for temporal split
            data_sample_percent: Percentage of data to use
            epochs: Override ModelConfig epochs
            batch_size: Override ModelConfig batch_size
            learning_rate: Override ModelConfig learning_rate

        Returns:
            QuickTest instance
        """
        from ml_platform.models import QuickTest

        # Create QuickTest record
        quick_test = QuickTest.objects.create(
            feature_config=feature_config,
            model_config=model_config,
            created_by=user,
            split_strategy=split_strategy,
            holdout_days=holdout_days,
            date_column=date_column,
            data_sample_percent=data_sample_percent,
            epochs=epochs or model_config.epochs,
            batch_size=batch_size or model_config.batch_size,
            learning_rate=learning_rate or model_config.learning_rate,
            status=QuickTest.STATUS_SUBMITTING,
        )

        try:
            # Generate code and submit pipeline
            self._submit_pipeline(quick_test, feature_config, model_config)

            # Update status
            quick_test.status = QuickTest.STATUS_RUNNING
            quick_test.started_at = timezone.now()
            quick_test.save(update_fields=['status', 'started_at'])

        except Exception as e:
            logger.exception(f"Error submitting quick test: {e}")
            quick_test.status = QuickTest.STATUS_FAILED
            quick_test.error_message = str(e)
            quick_test.save(update_fields=['status', 'error_message'])

        return quick_test

    def _submit_pipeline(self, quick_test, feature_config, model_config):
        """
        Internal method to generate code and submit pipeline.

        Args:
            quick_test: QuickTest instance
            feature_config: FeatureConfig instance
            model_config: ModelConfig instance
        """
        from ml_platform.configs.services import PreprocessingFnGenerator, TrainerModuleGenerator
        from ml_platform.datasets.services import BigQueryService

        # 1. Generate transform code from FeatureConfig
        logger.info(f"Generating transform code for FeatureConfig {feature_config.id}")
        transform_generator = PreprocessingFnGenerator(feature_config)
        transform_code = transform_generator.generate()

        # 2. Generate trainer code from FeatureConfig + ModelConfig
        logger.info(f"Generating trainer code for ModelConfig {model_config.id}")
        trainer_generator = TrainerModuleGenerator(feature_config, model_config)
        trainer_code, is_valid, error_msg, error_line = trainer_generator.generate_and_validate()

        if not is_valid:
            raise ExperimentServiceError(
                f"Generated trainer code has syntax error at line {error_line}: {error_msg}"
            )

        # 3. Generate SQL query with split/sampling
        logger.info("Generating BigQuery SQL with split strategy")
        dataset = feature_config.dataset
        bq_service = BigQueryService(self.model_endpoint, dataset)

        bigquery_query = bq_service.generate_training_query(
            dataset=dataset,
            split_strategy=quick_test.split_strategy,
            holdout_days=quick_test.holdout_days,
            date_column=quick_test.date_column,
            sample_percent=quick_test.data_sample_percent
        )

        # 4. Create unique paths for this run
        run_id = f"qt_{quick_test.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
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

        # Save GCS paths to quick_test
        quick_test.gcs_artifacts_path = gcs_base_path
        quick_test.save(update_fields=['gcs_artifacts_path'])

        # 6. Submit TFX pipeline to Vertex AI
        logger.info("Submitting TFX pipeline to Vertex AI")
        pipeline_job = self._submit_vertex_pipeline(
            quick_test=quick_test,
            bigquery_query=bigquery_query,
            transform_module_path=transform_module_path,
            trainer_module_path=trainer_module_path,
            gcs_output_path=gcs_base_path,
            run_id=run_id
        )

        # Save Vertex AI job info
        quick_test.vertex_pipeline_job_name = pipeline_job.resource_name
        quick_test.vertex_pipeline_job_id = pipeline_job.name.split('/')[-1]
        quick_test.save(update_fields=['vertex_pipeline_job_name', 'vertex_pipeline_job_id'])

        logger.info(f"Pipeline submitted: {quick_test.vertex_pipeline_job_id}")

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

    def _submit_vertex_pipeline(
        self,
        quick_test,
        bigquery_query: str,
        transform_module_path: str,
        trainer_module_path: str,
        gcs_output_path: str,
        run_id: str,
    ):
        """
        Submit the TFX pipeline to Vertex AI via Cloud Build.

        Cloud Build is used to compile the TFX pipeline (requires Python 3.10)
        and submit it to Vertex AI. The result is written to GCS for retrieval.

        Args:
            quick_test: QuickTest instance
            bigquery_query: SQL query for data extraction
            transform_module_path: GCS path to transform_module.py
            trainer_module_path: GCS path to trainer_module.py
            gcs_output_path: GCS path for output artifacts
            run_id: Unique identifier for this run

        Returns:
            Object with resource_name and name attributes (pipeline job info)
        """
        import time

        logger.info(f"Triggering Cloud Build for TFX pipeline compilation: {run_id}")

        # Trigger Cloud Build
        build_id = self._trigger_cloud_build(
            run_id=run_id,
            bigquery_query=bigquery_query,
            transform_module_path=transform_module_path,
            trainer_module_path=trainer_module_path,
            output_path=gcs_output_path,
            epochs=quick_test.epochs,
            batch_size=quick_test.batch_size,
            learning_rate=quick_test.learning_rate,
        )

        logger.info(f"Cloud Build triggered: {build_id}")

        # Wait for Cloud Build to complete and read result from GCS
        result = self._wait_for_build_result(run_id, timeout_seconds=1800)

        if not result.get('success'):
            raise ExperimentServiceError(
                f"Cloud Build failed: {result.get('error', 'Unknown error')}"
            )

        # Return a simple object with the pipeline job info
        class PipelineJobInfo:
            def __init__(self, resource_name):
                self.resource_name = resource_name
                self.name = resource_name

        return PipelineJobInfo(result['vertex_pipeline_job_name'])

    def _trigger_cloud_build(
        self,
        run_id: str,
        bigquery_query: str,
        transform_module_path: str,
        trainer_module_path: str,
        output_path: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
    ) -> str:
        """
        Trigger Cloud Build to compile and submit TFX pipeline.

        Args:
            run_id: Unique run identifier
            bigquery_query: BigQuery SQL query
            transform_module_path: GCS path to transform module
            trainer_module_path: GCS path to trainer module
            output_path: GCS path for outputs
            epochs: Training epochs
            batch_size: Batch size
            learning_rate: Learning rate

        Returns:
            Cloud Build build ID
        """
        import base64
        from google.cloud.devtools import cloudbuild_v1

        client = cloudbuild_v1.CloudBuildClient()

        # Base64 encode the query to avoid shell escaping issues
        query_b64 = base64.b64encode(bigquery_query.encode()).decode()

        # Upload the compile script to GCS (avoid Cloud Build arg length limit)
        script_path = f"build_scripts/{run_id}/compile_and_submit.py"
        bucket = self.storage_client.bucket(self.STAGING_BUCKET)
        blob = bucket.blob(script_path)
        blob.upload_from_string(self._get_compile_script(), content_type='text/plain')
        script_gcs_path = f"gs://{self.STAGING_BUCKET}/{script_path}"
        logger.info(f"Uploaded compile script to {script_gcs_path}")

        # Build configuration - downloads script from GCS using Python (gsutil not available in python:3.10)
        # Parse bucket and blob path from script_gcs_path
        script_bucket = self.STAGING_BUCKET
        script_blob = script_path

        build = cloudbuild_v1.Build(
            steps=[
                cloudbuild_v1.BuildStep(
                    name='python:3.10',
                    entrypoint='bash',
                    args=[
                        '-c',
                        f'''
set -e
pip install --quiet tfx>=1.15.0 google-cloud-aiplatform>=1.38.0 google-cloud-storage dill kfp>=2.0.0
python -c "from google.cloud import storage; storage.Client().bucket('{script_bucket}').blob('{script_blob}').download_to_filename('/tmp/compile_and_submit.py')"
python /tmp/compile_and_submit.py \
    --run-id="{run_id}" \
    --staging-bucket="{self.STAGING_BUCKET}" \
    --bigquery-query-b64="{query_b64}" \
    --transform-module-path="{transform_module_path}" \
    --trainer-module-path="{trainer_module_path}" \
    --output-path="{output_path}" \
    --epochs="{epochs}" \
    --batch-size="{batch_size}" \
    --learning-rate="{learning_rate}" \
    --project-id="{self.project_id}" \
    --region="{self.REGION}"
'''
                    ],
                )
            ],
            timeout={'seconds': 1800},
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
        """Return the TFX compile and submit script content."""
        return '''
import argparse
import json
import logging
import os
import tempfile
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_tfx_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    bigquery_query: str,
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    epochs: int = 10,
    batch_size: int = 4096,
    learning_rate: float = 0.001,
    train_steps: Optional[int] = None,
    eval_steps: Optional[int] = None,
):
    from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
    from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer
    from tfx.proto import example_gen_pb2, trainer_pb2
    from tfx.orchestration import pipeline as tfx_pipeline

    logger.info(f"Creating TFX pipeline: {pipeline_name}")

    output_config = example_gen_pb2.Output(
        split_config=example_gen_pb2.SplitConfig(
            splits=[
                example_gen_pb2.SplitConfig.Split(name="train", hash_buckets=8),
                example_gen_pb2.SplitConfig.Split(name="eval", hash_buckets=2),
            ]
        )
    )

    example_gen = BigQueryExampleGen(query=bigquery_query, output_config=output_config)
    statistics_gen = StatisticsGen(examples=example_gen.outputs["examples"])
    schema_gen = SchemaGen(statistics=statistics_gen.outputs["statistics"])
    transform = Transform(
        examples=example_gen.outputs["examples"],
        schema=schema_gen.outputs["schema"],
        module_file=transform_module_path,
    )

    train_args = trainer_pb2.TrainArgs(num_steps=train_steps)
    eval_args = trainer_pb2.EvalArgs(num_steps=eval_steps)
    custom_config = {"epochs": epochs, "batch_size": batch_size, "learning_rate": learning_rate}

    trainer = Trainer(
        module_file=trainer_module_path,
        examples=transform.outputs["transformed_examples"],
        transform_graph=transform.outputs["transform_graph"],
        schema=schema_gen.outputs["schema"],
        train_args=train_args,
        eval_args=eval_args,
        custom_config=custom_config,
    )

    components = [example_gen, statistics_gen, schema_gen, transform, trainer]
    pipeline = tfx_pipeline.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=components,
        enable_cache=False,
    )
    logger.info(f"TFX pipeline created with {len(components)} components")
    return pipeline


def compile_pipeline(pipeline, output_file: str) -> str:
    from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner
    logger.info(f"Compiling pipeline to: {output_file}")
    runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
        config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(),
        output_filename=output_file
    )
    runner.run(pipeline)
    logger.info("Pipeline compiled successfully")
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
    parser = argparse.ArgumentParser(description="Compile and submit TFX pipeline")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--staging-bucket", required=True)
    parser.add_argument("--bigquery-query-b64", required=True, help="Base64 encoded BigQuery SQL")
    parser.add_argument("--transform-module-path", required=True)
    parser.add_argument("--trainer-module-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", default="europe-central2")
    args = parser.parse_args()

    # Decode the base64 query
    bigquery_query = base64.b64decode(args.bigquery_query_b64).decode("utf-8")
    logger.info(f"Decoded BigQuery query: {bigquery_query[:100]}...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_file = os.path.join(temp_dir, f"pipeline_{args.run_id}.json")
            pipeline = create_tfx_pipeline(
                pipeline_name=f"quicktest-{args.run_id}",
                pipeline_root=f"gs://{args.staging_bucket}/pipeline_root/{args.run_id}",
                bigquery_query=bigquery_query,
                transform_module_path=args.transform_module_path,
                trainer_module_path=args.trainer_module_path,
                output_path=args.output_path,
                epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.learning_rate,
            )
            compile_pipeline(pipeline, pipeline_file)
            display_name = f"quicktest-{args.run_id}"
            resource_name = submit_to_vertex_ai(pipeline_file, display_name, args.project_id, args.region)
            result = {"success": True, "run_id": args.run_id, "vertex_pipeline_job_name": resource_name, "display_name": display_name}
            write_result_to_gcs(args.staging_bucket, f"build_results/{args.run_id}.json", result)
            logger.info("Pipeline compilation and submission completed successfully")
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

    def _wait_for_build_result(self, run_id: str, timeout_seconds: int = 1800) -> dict:
        """
        Wait for Cloud Build to complete and read result from GCS.

        The compile_and_submit.py script writes result to:
        gs://{STAGING_BUCKET}/build_results/{run_id}.json

        Args:
            run_id: Unique run identifier
            timeout_seconds: Maximum time to wait

        Returns:
            Result dictionary with success, vertex_pipeline_job_name, or error
        """
        import time

        result_blob_path = f"build_results/{run_id}.json"
        bucket = self.storage_client.bucket(self.STAGING_BUCKET)
        blob = bucket.blob(result_blob_path)

        start_time = time.time()
        poll_interval = 10  # seconds

        logger.info(f"Waiting for build result: gs://{self.STAGING_BUCKET}/{result_blob_path}")

        while (time.time() - start_time) < timeout_seconds:
            if blob.exists():
                content = blob.download_as_string().decode('utf-8')
                result = json.loads(content)
                logger.info(f"Build result received: {result}")
                return result

            time.sleep(poll_interval)

        # Timeout
        return {
            'success': False,
            'error': f'Build timeout after {timeout_seconds} seconds'
        }

    def refresh_status(self, quick_test) -> 'QuickTest':
        """
        Refresh the status of a QuickTest from Vertex AI.

        Args:
            quick_test: QuickTest instance

        Returns:
            Updated QuickTest instance
        """
        if not quick_test.vertex_pipeline_job_name:
            return quick_test

        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            # Get pipeline job status
            pipeline_job = aiplatform.PipelineJob.get(
                quick_test.vertex_pipeline_job_name
            )

            state = pipeline_job.state.name

            # Map Vertex AI states to QuickTest states
            state_mapping = {
                'PIPELINE_STATE_PENDING': quick_test.STATUS_SUBMITTING,
                'PIPELINE_STATE_RUNNING': quick_test.STATUS_RUNNING,
                'PIPELINE_STATE_SUCCEEDED': quick_test.STATUS_COMPLETED,
                'PIPELINE_STATE_FAILED': quick_test.STATUS_FAILED,
                'PIPELINE_STATE_CANCELLED': quick_test.STATUS_CANCELLED,
                'PIPELINE_STATE_CANCELLING': quick_test.STATUS_RUNNING,
            }

            new_status = state_mapping.get(state, quick_test.status)

            if new_status != quick_test.status:
                quick_test.status = new_status

                if new_status == quick_test.STATUS_COMPLETED:
                    quick_test.completed_at = timezone.now()
                    # Extract results from GCS
                    self._extract_results(quick_test)

                elif new_status == quick_test.STATUS_FAILED:
                    quick_test.completed_at = timezone.now()
                    # Try to extract error message
                    if hasattr(pipeline_job, 'error') and pipeline_job.error:
                        quick_test.error_message = str(pipeline_job.error)

                quick_test.save()

            # Update progress from pipeline tasks
            self._update_progress(quick_test, pipeline_job)

        except Exception as e:
            logger.warning(f"Error refreshing status for QuickTest {quick_test.id}: {e}")

        return quick_test

    def _extract_results(self, quick_test):
        """
        Extract results and metrics from GCS after pipeline completion.

        Args:
            quick_test: QuickTest instance
        """
        if not quick_test.gcs_artifacts_path:
            return

        try:
            # Try to read metrics.json from output path
            metrics_path = f"{quick_test.gcs_artifacts_path}/metrics.json"
            blob_path = metrics_path.replace(f"gs://{self.ARTIFACTS_BUCKET}/", "")

            bucket = self.storage_client.bucket(self.ARTIFACTS_BUCKET)
            blob = bucket.blob(blob_path)

            if blob.exists():
                metrics_content = blob.download_as_string().decode('utf-8')
                metrics = json.loads(metrics_content)

                # Map metrics to QuickTest model fields
                update_fields = []

                if 'loss' in metrics:
                    quick_test.loss = metrics['loss']
                    update_fields.append('loss')

                if 'factorized_top_k/top_10_categorical_accuracy' in metrics:
                    quick_test.recall_at_10 = metrics['factorized_top_k/top_10_categorical_accuracy']
                    update_fields.append('recall_at_10')

                if 'factorized_top_k/top_50_categorical_accuracy' in metrics:
                    quick_test.recall_at_50 = metrics['factorized_top_k/top_50_categorical_accuracy']
                    update_fields.append('recall_at_50')

                if 'factorized_top_k/top_100_categorical_accuracy' in metrics:
                    quick_test.recall_at_100 = metrics['factorized_top_k/top_100_categorical_accuracy']
                    update_fields.append('recall_at_100')

                if update_fields:
                    quick_test.save(update_fields=update_fields)

                logger.info(f"Extracted results for QuickTest {quick_test.id}: {metrics}")

        except Exception as e:
            logger.warning(f"Error extracting results for QuickTest {quick_test.id}: {e}")

    def _update_progress(self, quick_test, pipeline_job):
        """
        Update progress percentage and current stage from pipeline tasks.

        Args:
            quick_test: QuickTest instance
            pipeline_job: Vertex AI PipelineJob instance
        """
        try:
            # This is simplified - full implementation would parse pipeline tasks
            # For now, estimate based on state
            state = pipeline_job.state.name

            if state == 'PIPELINE_STATE_PENDING':
                quick_test.progress_percent = 0
                quick_test.current_stage = 'pending'
            elif state == 'PIPELINE_STATE_RUNNING':
                # Estimate progress (would need task details for accuracy)
                quick_test.progress_percent = 50
                quick_test.current_stage = 'running'
            elif state == 'PIPELINE_STATE_SUCCEEDED':
                quick_test.progress_percent = 100
                quick_test.current_stage = 'completed'
            elif state in ('PIPELINE_STATE_FAILED', 'PIPELINE_STATE_CANCELLED'):
                quick_test.current_stage = 'failed' if 'FAILED' in state else 'cancelled'

            quick_test.save(update_fields=['progress_percent', 'current_stage'])

        except Exception as e:
            logger.warning(f"Error updating progress for QuickTest {quick_test.id}: {e}")

    def cancel_quick_test(self, quick_test) -> 'QuickTest':
        """
        Cancel a running Quick Test pipeline.

        Args:
            quick_test: QuickTest instance

        Returns:
            Updated QuickTest instance
        """
        if not quick_test.vertex_pipeline_job_name:
            quick_test.status = quick_test.STATUS_CANCELLED
            quick_test.save(update_fields=['status'])
            return quick_test

        self._init_aiplatform()

        try:
            from google.cloud import aiplatform

            pipeline_job = aiplatform.PipelineJob.get(
                quick_test.vertex_pipeline_job_name
            )
            pipeline_job.cancel()

            quick_test.status = quick_test.STATUS_CANCELLED
            quick_test.completed_at = timezone.now()
            quick_test.save(update_fields=['status', 'completed_at'])

            logger.info(f"Cancelled QuickTest {quick_test.id}")

        except Exception as e:
            logger.warning(f"Error cancelling QuickTest {quick_test.id}: {e}")
            quick_test.status = quick_test.STATUS_CANCELLED
            quick_test.error_message = f"Cancel error: {str(e)}"
            quick_test.save(update_fields=['status', 'error_message'])

        return quick_test
