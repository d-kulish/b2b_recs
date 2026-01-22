#!/usr/bin/env python3
"""
Test Option 3: TFX GenericExecutor with Vertex AI Custom Jobs

This script tests whether adding GenericExecutor with ai_platform_training_args
properly spawns a Vertex AI Custom Job with GPU resources.

TEST STRATEGY:
1. First, run with --direct-custom-job to verify GPUs work (baseline - proven to work)
2. Then, run without flags to test the full TFX pipeline with GenericExecutor

The full pipeline test creates a complete TFX pipeline via Cloud Build that:
- Uses GenericExecutor for the Trainer component
- Has ai_platform_training_args with worker_pool_specs
- Should spawn a separate Custom Job for training with GPU

Uses existing artifacts from training run 8's dataset (but re-runs full pipeline).

Usage:
    # Step 1: Verify GPU access works with direct Custom Job (baseline)
    python scripts/test_option3_gpu_executor.py --direct-custom-job --epochs 1

    # Step 2: Test full TFX pipeline with GenericExecutor
    python scripts/test_option3_gpu_executor.py --epochs 2

    # Dry run (generate code only)
    python scripts/test_option3_gpu_executor.py --dry-run
"""

import argparse
import json
import logging
import os
import sys
import base64
from datetime import datetime

# Setup Django
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from ml_platform.models import FeatureConfig, ModelConfig
from ml_platform.training.models import TrainingRun
from ml_platform.configs.services import (
    TrainerModuleGenerator,
    PreprocessingFnGenerator,
    validate_python_code
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = 'b2b-recs'
REGION = 'europe-west4'  # GPU training region
STAGING_BUCKET = 'b2b-recs-pipeline-staging'
ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
GPU_STAGING_BUCKET = 'b2b-recs-gpu-staging'

# GPU-enabled trainer image
TRAINER_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer-gpu:latest'

# Artifacts from training run 8 (Transform completed successfully before Trainer failed)
RUN_8_BASE = 'gs://b2b-recs-pipeline-staging/pipeline_root/tr-8-20260122-153919/555035914949/training-tr-8-20260122-153919-20260122154145'
ARTIFACTS = {
    'transform_graph': f'{RUN_8_BASE}/Transform_-3461554249698115584/transform_graph',
    'transformed_examples_train': f'{RUN_8_BASE}/Transform_-3461554249698115584/transformed_examples/Split-train',
    'transformed_examples_eval': f'{RUN_8_BASE}/Transform_-3461554249698115584/transformed_examples/Split-eval',
    'schema': f'{RUN_8_BASE}/SchemaGen_1150131768729272320/schema/schema.pbtxt',
}


def create_direct_runner_script(
    trainer_gcs_path: str,
    output_path: str,
    epochs: int,
    learning_rate: float,
) -> str:
    """Create runner script for direct Custom Job test (baseline)."""
    return f'''#!/usr/bin/env python3
"""Direct Custom Job Runner - Tests GPU access without TFX pipeline."""
import os
import sys
import logging
import tempfile
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TRANSFORM_GRAPH = '{ARTIFACTS["transform_graph"]}'
TRAIN_EXAMPLES = '{ARTIFACTS["transformed_examples_train"]}'
EVAL_EXAMPLES = '{ARTIFACTS["transformed_examples_eval"]}'
SCHEMA_PATH = '{ARTIFACTS["schema"]}'
TRAINER_GCS_PATH = '{trainer_gcs_path}'
OUTPUT_PATH = '{output_path}'

def main():
    logger.info("=" * 60)
    logger.info("BASELINE TEST: Direct Custom Job with GPU")
    logger.info("=" * 60)

    import tensorflow as tf
    gpus = tf.config.list_physical_devices('GPU')
    logger.info(f"Physical GPUs detected: {{len(gpus)}}")
    for i, gpu in enumerate(gpus):
        logger.info(f"  GPU {{i}}: {{gpu.name}}")

    if len(gpus) == 0:
        raise RuntimeError("NO GPUs DETECTED - baseline test failed!")

    logger.info("SUCCESS: GPU detected in direct Custom Job")

    work_dir = tempfile.mkdtemp(prefix='baseline_test_')

    # Download artifacts
    trainer_local = os.path.join(work_dir, 'trainer_module.py')
    subprocess.run(['gsutil', 'cp', TRAINER_GCS_PATH, trainer_local], check=True)

    transform_local = os.path.join(work_dir, 'transform_graph')
    os.makedirs(transform_local, exist_ok=True)
    subprocess.run(['gsutil', '-m', 'rsync', '-r', TRANSFORM_GRAPH, transform_local], check=True)

    schema_local = os.path.join(work_dir, 'schema.pbtxt')
    subprocess.run(['gsutil', 'cp', SCHEMA_PATH, schema_local], check=True)

    # Import trainer
    sys.path.insert(0, work_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location("trainer_module", trainer_local)
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)

    # Create FnArgs
    class FnArgs:
        pass

    fn_args = FnArgs()
    fn_args.train_files = [TRAIN_EXAMPLES + '/*']
    fn_args.eval_files = [EVAL_EXAMPLES + '/*']
    fn_args.transform_output = transform_local
    fn_args.schema_file = schema_local
    fn_args.serving_model_dir = os.path.join(work_dir, 'serving_model')
    fn_args.model_run_dir = os.path.join(work_dir, 'model_run')
    fn_args.train_steps = None
    fn_args.eval_steps = None
    fn_args.custom_config = {{
        'epochs': {epochs},
        'batch_size': 4096,
        'learning_rate': {learning_rate},
        'gcs_output_path': OUTPUT_PATH,
        'gpu_enabled': True,
        'gpu_count': 1,
    }}

    class DataAccessor:
        def tf_dataset_factory(self, file_pattern, options, schema):
            import tensorflow as tf
            if isinstance(file_pattern, list):
                file_pattern = file_pattern[0]
            files = tf.io.gfile.glob(file_pattern)
            logger.info(f"Found {{len(files)}} files")
            dataset = tf.data.TFRecordDataset(files, compression_type='GZIP')
            import tensorflow_transform as tft
            tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)
            feature_spec = tf_transform_output.transformed_feature_spec()
            def parse_fn(example):
                parsed = tf.io.parse_single_example(example, feature_spec)
                return {{k: tf.expand_dims(v, 0) if len(v.shape) == 0 else v for k, v in parsed.items()}}
            dataset = dataset.map(parse_fn, num_parallel_calls=tf.data.AUTOTUNE)
            dataset = dataset.batch(options.batch_size).prefetch(tf.data.AUTOTUNE)
            return dataset

    fn_args.data_accessor = DataAccessor()
    os.makedirs(fn_args.serving_model_dir, exist_ok=True)
    os.makedirs(fn_args.model_run_dir, exist_ok=True)

    logger.info("Starting training...")
    trainer.run_fn(fn_args)
    logger.info("Training completed!")

    subprocess.run(['gsutil', '-m', 'cp', '-r', fn_args.serving_model_dir, OUTPUT_PATH + '/model'], check=True)
    logger.info("BASELINE TEST PASSED!")

if __name__ == '__main__':
    main()
'''


def get_option3_compile_script(
    run_id: str,
    bigquery_query_b64: str,
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
) -> str:
    """
    Generate the compile script that tests Option 3: GenericExecutor.

    This is the KEY difference from current production code:
    - Adds custom_executor_spec with GenericExecutor to Trainer
    - Uses ai_platform_training_args with direct worker_pool_specs
    """
    return f'''#!/usr/bin/env python3
"""
OPTION 3 TEST: TFX Pipeline with GenericExecutor for GPU Training

This script is identical to production EXCEPT:
- Trainer has custom_executor_spec with GenericExecutor
- ai_platform_training_args has direct worker_pool_specs (not wrapped in job_spec)

If this works, the Trainer should spawn a separate Custom Job with GPU.
"""
import argparse
import base64
import json
import logging
import os
import tempfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_pipeline():
    from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
    from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer
    from tfx.proto import example_gen_pb2, trainer_pb2
    from tfx.orchestration import pipeline as tfx_pipeline
    from tfx.dsl.components.base import executor_spec
    from tfx.extensions.google_cloud_ai_platform.trainer import executor as ai_platform_trainer_executor

    pipeline_name = "option3-test-{run_id}"
    pipeline_root = "gs://{STAGING_BUCKET}/pipeline_root/option3-test-{run_id}"

    logger.info(f"Creating pipeline: {{pipeline_name}}")

    # Decode query
    bigquery_query = base64.b64decode("{bigquery_query_b64}").decode("utf-8")
    logger.info(f"Query: {{bigquery_query[:100]}}...")

    # 1. ExampleGen with random split
    output_config = example_gen_pb2.Output(
        split_config=example_gen_pb2.SplitConfig(
            splits=[
                example_gen_pb2.SplitConfig.Split(name="train", hash_buckets=8),
                example_gen_pb2.SplitConfig.Split(name="eval", hash_buckets=2),
            ]
        )
    )
    example_gen = BigQueryExampleGen(
        query=bigquery_query,
        output_config=output_config,
        custom_config={{'project': '{PROJECT_ID}'}}
    )

    # 2. StatisticsGen
    statistics_gen = StatisticsGen(examples=example_gen.outputs["examples"])

    # 3. SchemaGen
    schema_gen = SchemaGen(statistics=statistics_gen.outputs["statistics"])

    # 4. Transform
    transform = Transform(
        examples=example_gen.outputs["examples"],
        schema=schema_gen.outputs["schema"],
        module_file="{transform_module_path}",
    )

    # 5. Trainer with GenericExecutor - THIS IS THE KEY CHANGE!
    custom_config = {{
        "epochs": {epochs},
        "batch_size": {batch_size},
        "learning_rate": {learning_rate},
        "gcs_output_path": "{output_path}",
        "gpu_enabled": True,
        "gpu_count": 1,

        # KEY: ai_platform_training_args with DIRECT worker_pool_specs
        # (not wrapped in job_spec like the broken code)
        "ai_platform_training_args": {{
            "project": "{PROJECT_ID}",
            "region": "{REGION}",
            "worker_pool_specs": [{{
                "machine_spec": {{
                    "machine_type": "n1-standard-8",
                    "accelerator_type": "NVIDIA_TESLA_T4",
                    "accelerator_count": 1,
                }},
                "replica_count": 1,
                "container_spec": {{
                    "image_uri": "{TRAINER_IMAGE}",
                }},
            }}],
        }},
    }}

    logger.info(f"Trainer custom_config: {{json.dumps(custom_config, indent=2)}}")

    # KEY CHANGE: Add custom_executor_spec with GenericExecutor
    trainer = Trainer(
        module_file="{trainer_module_path}",
        examples=transform.outputs["transformed_examples"],
        transform_graph=transform.outputs["transform_graph"],
        schema=schema_gen.outputs["schema"],
        train_args=trainer_pb2.TrainArgs(num_steps=None),
        eval_args=trainer_pb2.EvalArgs(num_steps=None),
        custom_executor_spec=executor_spec.ExecutorClassSpec(
            ai_platform_trainer_executor.GenericExecutor
        ),
        custom_config=custom_config,
    )

    logger.info("Added GenericExecutor to Trainer - this should spawn a Custom Job with GPU")

    # Beam args for StatisticsGen/Transform
    beam_pipeline_args = [
        '--runner=DataflowRunner',
        f'--project={PROJECT_ID}',
        f'--region={REGION}',
        f'--temp_location=gs://{STAGING_BUCKET}/dataflow_temp',
        f'--staging_location=gs://{STAGING_BUCKET}/dataflow_staging',
        '--machine_type=n1-standard-4',
        '--disk_size_gb=50',
        '--experiments=use_runner_v2',
        '--max_num_workers=10',
    ]

    pipeline = tfx_pipeline.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=[example_gen, statistics_gen, schema_gen, transform, trainer],
        enable_cache=False,
        beam_pipeline_args=beam_pipeline_args,
    )

    logger.info("Pipeline created with 5 components")
    return pipeline


def compile_pipeline(pipeline, output_file: str):
    from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner

    logger.info(f"Compiling to: {{output_file}}")

    runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
        config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(
            default_image="{TRAINER_IMAGE}"
        ),
        output_filename=output_file
    )
    runner.run(pipeline)

    # Log structure for debugging
    with open(output_file, 'r') as f:
        spec = json.load(f)
    logger.info("Compiled pipeline executors:")
    for name in spec.get('deploymentSpec', {{}}).get('executors', {{}}).keys():
        logger.info(f"  - {{name}}")

    # NOTE: No post-processing needed! GenericExecutor handles GPU config
    logger.info("Pipeline compiled (no post-processing - GenericExecutor handles GPU)")
    return output_file


def submit_to_vertex_ai(template_path: str, display_name: str):
    from google.cloud import aiplatform

    logger.info(f"Submitting to Vertex AI: {{display_name}}")
    aiplatform.init(project="{PROJECT_ID}", location="{REGION}")

    pipeline_job = aiplatform.PipelineJob(
        display_name=display_name[:128],
        template_path=template_path,
        enable_caching=False,
    )
    pipeline_job.submit()

    logger.info(f"Pipeline submitted: {{pipeline_job.resource_name}}")
    return pipeline_job.resource_name


def write_result(result: dict):
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket("{STAGING_BUCKET}")
    blob = bucket.blob("build_results/option3-test-{run_id}.json")
    blob.upload_from_string(json.dumps(result, indent=2))
    logger.info("Result written to GCS")


def main():
    logger.info("=" * 60)
    logger.info("OPTION 3 TEST: GenericExecutor with Vertex AI GPU")
    logger.info("=" * 60)

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_file = os.path.join(temp_dir, "pipeline.json")
            pipeline = create_pipeline()
            compile_pipeline(pipeline, pipeline_file)

            display_name = "option3-test-{run_id}"
            resource_name = submit_to_vertex_ai(pipeline_file, display_name)

            result = {{
                "success": True,
                "run_id": "option3-test-{run_id}",
                "vertex_pipeline_job_name": resource_name,
                "test_type": "option3_generic_executor",
            }}
            write_result(result)

            logger.info("=" * 60)
            logger.info("OPTION 3 TEST SUBMITTED")
            logger.info(f"Pipeline: {{resource_name}}")
            logger.info("=" * 60)
            print(f"PIPELINE_JOB_NAME={{resource_name}}")

    except Exception as e:
        logger.error(f"Failed: {{e}}")
        import traceback
        traceback.print_exc()
        result = {{"success": False, "error": str(e)}}
        try:
            write_result(result)
        except:
            pass
        raise


if __name__ == "__main__":
    main()
'''


def main():
    parser = argparse.ArgumentParser(description='Test Option 3: GenericExecutor with GPU')
    parser.add_argument('--epochs', type=int, default=2, help='Training epochs')
    parser.add_argument('--batch-size', type=int, default=4096, help='Batch size')
    parser.add_argument('--learning-rate', type=float, default=0.1, help='Learning rate')
    parser.add_argument('--dry-run', action='store_true', help='Generate code only')
    parser.add_argument('--direct-custom-job', action='store_true',
                        help='Run baseline test with direct Custom Job (proven to work)')
    args = parser.parse_args()

    from google.cloud import storage

    run_id = f'opt3-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
    output_path = f'gs://{ARTIFACTS_BUCKET}/{run_id}'

    logger.info("=" * 60)
    logger.info("OPTION 3 GPU TEST")
    logger.info("=" * 60)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Mode: {'Direct Custom Job (baseline)' if args.direct_custom_job else 'TFX Pipeline with GenericExecutor'}")

    # Load configs from training run 8
    feature_config = FeatureConfig.objects.get(id=8)
    model_config = ModelConfig.objects.get(id=14)
    logger.info(f"Using FeatureConfig: {feature_config.name}")
    logger.info(f"Using ModelConfig: {model_config.name}")

    # Generate trainer module
    logger.info("Generating trainer module...")
    trainer_gen = TrainerModuleGenerator(feature_config, model_config)
    trainer_code = trainer_gen.generate()

    is_valid, error_msg, _ = validate_python_code(trainer_code, 'trainer')
    if not is_valid:
        logger.error(f"Invalid trainer code: {error_msg}")
        sys.exit(1)

    # Override epochs
    import re
    trainer_code = re.sub(r'EPOCHS = \d+', f'EPOCHS = {args.epochs}', trainer_code)
    trainer_code = re.sub(r'LEARNING_RATE = [\d.]+', f'LEARNING_RATE = {args.learning_rate}', trainer_code)

    # Upload trainer
    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)

    trainer_blob = f'{run_id}/trainer_module.py'
    bucket.blob(trainer_blob).upload_from_string(trainer_code)
    trainer_gcs = f'gs://{ARTIFACTS_BUCKET}/{trainer_blob}'
    logger.info(f"Uploaded trainer: {trainer_gcs}")

    if args.direct_custom_job:
        # BASELINE TEST: Direct Custom Job with GPU
        logger.info("Running BASELINE test with direct Custom Job...")

        runner_script = create_direct_runner_script(
            trainer_gcs, output_path, args.epochs, args.learning_rate
        )

        runner_blob = f'{run_id}/runner.py'
        bucket.blob(runner_blob).upload_from_string(runner_script)
        runner_gcs = f'gs://{ARTIFACTS_BUCKET}/{runner_blob}'

        if args.dry_run:
            logger.info("DRY RUN - Code generated:")
            logger.info(f"  Trainer: {trainer_gcs}")
            logger.info(f"  Runner: {runner_gcs}")
            return

        from google.cloud import aiplatform
        aiplatform.init(project=PROJECT_ID, location=REGION)

        job = aiplatform.CustomJob(
            display_name=f'baseline-gpu-{run_id}',
            worker_pool_specs=[{
                'machine_spec': {
                    'machine_type': 'n1-standard-8',
                    'accelerator_type': 'NVIDIA_TESLA_T4',
                    'accelerator_count': 1,
                },
                'replica_count': 1,
                'container_spec': {
                    'image_uri': TRAINER_IMAGE,
                    'command': ['bash', '-c', f'gsutil cp {runner_gcs} /tmp/r.py && python /tmp/r.py'],
                },
            }],
            staging_bucket=f'gs://{GPU_STAGING_BUCKET}',
        )

        job.submit()
        job_id = job.resource_name.split('/')[-1]

        logger.info(f"""
================================================================================
BASELINE TEST SUBMITTED (Direct Custom Job)
================================================================================
Job: {job.resource_name}

This test verifies GPUs work with direct Custom Job API.
If this passes, we know GPU access is working.

Monitor:
  gcloud ai custom-jobs describe {job_id} --region={REGION} --format='value(state)'

Logs (look for "Physical GPUs detected: 1"):
  gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="{job_id}"' \\
    --project={PROJECT_ID} --limit=50 --format='value(textPayload)' | grep -i gpu

Expected: "Physical GPUs detected: 1" and "BASELINE TEST PASSED!"
================================================================================
""")

    else:
        # OPTION 3 TEST: Full TFX Pipeline with GenericExecutor
        logger.info("Running OPTION 3 test with TFX Pipeline + GenericExecutor...")

        # Generate transform module (preprocessing_fn)
        transform_gen = PreprocessingFnGenerator(feature_config)
        transform_code = transform_gen.generate()

        transform_blob = f'{run_id}/transform_module.py'
        bucket.blob(transform_blob).upload_from_string(transform_code)
        transform_gcs = f'gs://{ARTIFACTS_BUCKET}/{transform_blob}'
        logger.info(f"Uploaded transform: {transform_gcs}")

        # Get BigQuery query from training run 8
        tr8 = TrainingRun.objects.get(id=8)
        dataset = tr8.dataset

        # Build query using BigQueryService (same as services.py)
        from ml_platform.datasets.services import BigQueryService
        bq_service = BigQueryService(tr8.ml_model)
        bq_query = bq_service.generate_training_query(
            dataset=dataset,
            split_strategy='random',
            sample_percent=10,  # Use 10% sample for faster test
        )
        query_b64 = base64.b64encode(bq_query.encode()).decode()
        logger.info(f"Query (10% sample): {bq_query[:100]}...")

        # Generate compile script
        compile_script = get_option3_compile_script(
            run_id=run_id,
            bigquery_query_b64=query_b64,
            transform_module_path=transform_gcs,
            trainer_module_path=trainer_gcs,
            output_path=output_path,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
        )

        script_blob = f'{run_id}/compile_and_submit.py'
        bucket.blob(script_blob).upload_from_string(compile_script)
        script_gcs = f'gs://{ARTIFACTS_BUCKET}/{script_blob}'
        logger.info(f"Uploaded compile script: {script_gcs}")

        if args.dry_run:
            logger.info("DRY RUN - Code generated:")
            logger.info(f"  Trainer: {trainer_gcs}")
            logger.info(f"  Transform: {transform_gcs}")
            logger.info(f"  Compile script: {script_gcs}")
            logger.info(f"\nTo inspect: gsutil cat {script_gcs}")
            return

        # Submit via Cloud Build
        from google.cloud.devtools import cloudbuild_v1

        tfx_image = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest'

        # Parse GCS path for Python download
        script_bucket = ARTIFACTS_BUCKET
        script_blob_path = f'{run_id}/compile_and_submit.py'

        build = cloudbuild_v1.Build(
            steps=[
                cloudbuild_v1.BuildStep(
                    name=tfx_image,
                    entrypoint='bash',
                    args=['-c', f'''
set -e
echo "OPTION 3 TEST: TFX Pipeline with GenericExecutor"
python -c "import tfx; print(f'TFX: {{tfx.__version__}}')"
python -c "from google.cloud import storage; storage.Client().bucket('{script_bucket}').blob('{script_blob_path}').download_to_filename('/tmp/compile.py')"
python /tmp/compile.py
'''],
                )
            ],
            timeout={'seconds': 1800},
            options=cloudbuild_v1.BuildOptions(
                logging=cloudbuild_v1.BuildOptions.LoggingMode.CLOUD_LOGGING_ONLY,
                machine_type=cloudbuild_v1.BuildOptions.MachineType.E2_HIGHCPU_8,
            ),
        )

        build_client = cloudbuild_v1.CloudBuildClient()
        operation = build_client.create_build(project_id=PROJECT_ID, build=build)
        build_id = operation.metadata.build.id

        logger.info(f"""
================================================================================
OPTION 3 TEST SUBMITTED (TFX Pipeline with GenericExecutor)
================================================================================
Cloud Build: {build_id}
Run ID: {run_id}

This test verifies that GenericExecutor spawns a Custom Job with GPU.

Step 1 - Monitor Cloud Build (compiles and submits pipeline):
  gcloud builds describe {build_id} --region=global --format='value(status)'

Step 2 - After Cloud Build succeeds, check for pipeline:
  gcloud ai pipelines list --region={REGION} --filter="displayName:option3-test" --format='table(name,state)'

Step 3 - When pipeline reaches Trainer step, check for Custom Job:
  gcloud ai custom-jobs list --region={REGION} --filter="displayName~option3" --format='table(name,state)'

Step 4 - Check Custom Job logs for GPU detection:
  # Get the Custom Job ID from step 3, then:
  gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="<JOB_ID>"' \\
    --project={PROJECT_ID} --limit=50 --format='value(textPayload)' | grep -i gpu

SUCCESS CRITERIA:
  - Pipeline spawns a SEPARATE Custom Job for Trainer (not in-pipeline)
  - Custom Job logs show "Physical GPUs detected: 1"
  - Training completes successfully

If Custom Job shows "Physical GPUs detected: 0", Option 3 is NOT working.
================================================================================
""")


if __name__ == '__main__':
    main()
