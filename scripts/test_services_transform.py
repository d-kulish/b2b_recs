#!/usr/bin/env python3
"""
Test Services Transform Generation

Tests PreprocessingFnGenerator from services.py by:
1. Loading FeatureConfig from the database
2. Getting generated transform code
3. Running Transform with DirectRunner in a CustomJob

Usage:
    python scripts/test_services_transform.py --feature-config-id 9 --source-exp qt-91-20260108-163710
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# Setup Django
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from ml_platform.models import FeatureConfig
from ml_platform.configs.services import validate_python_code

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ID = 'b2b-recs'
REGION = 'europe-central2'
STAGING_BUCKET = 'b2b-recs-pipeline-staging'
ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
TFX_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer:latest'


def find_artifacts(source_exp: str) -> dict:
    """Find raw examples and schema from a previous experiment."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(STAGING_BUCKET)

    prefix = f'pipeline_root/{source_exp}/'
    blobs = list(bucket.list_blobs(prefix=prefix))
    paths = [b.name for b in blobs]

    examples_base = None
    schema_path = None

    for p in paths:
        if 'BigQueryExampleGen_' in p and '/examples/Split-train/' in p and not examples_base:
            parts = p.split('/')
            for i, part in enumerate(parts):
                if part.startswith('BigQueryExampleGen_'):
                    examples_base = '/'.join(parts[:i+1])
                    break
        if 'SchemaGen_' in p and 'schema.pbtxt' in p:
            schema_path = p

    if not examples_base or not schema_path:
        raise ValueError(f"Could not find artifacts in {prefix}. Found paths: {paths[:10]}")

    return {
        'examples_train': f'gs://{STAGING_BUCKET}/{examples_base}/examples/Split-train',
        'examples_eval': f'gs://{STAGING_BUCKET}/{examples_base}/examples/Split-eval',
        'schema': f'gs://{STAGING_BUCKET}/{schema_path}',
    }


def create_transform_runner_script(artifacts: dict, transform_gcs_path: str, output_path: str) -> str:
    """Create the script that runs Transform in the CustomJob."""

    return f'''#!/usr/bin/env python3
"""Transform runner script for CustomJob - testing services.py generation."""
import os
import sys
import logging
import tempfile
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("SERVICES.PY TRANSFORM TEST")
    logger.info("="*60)

    work_dir = tempfile.mkdtemp(prefix='transform_test_')
    logger.info(f"Work dir: {{work_dir}}")

    # Download transform module
    transform_local = os.path.join(work_dir, 'transform_module.py')
    logger.info(f"Downloading transform from {transform_gcs_path}")
    subprocess.run(['gsutil', 'cp', '{transform_gcs_path}', transform_local], check=True)

    # Download schema
    schema_local = os.path.join(work_dir, 'schema.pbtxt')
    logger.info(f"Downloading schema from {artifacts['schema']}")
    subprocess.run(['gsutil', 'cp', '{artifacts['schema']}', schema_local], check=True)

    # Download examples
    examples_train_local = os.path.join(work_dir, 'examples_train')
    examples_eval_local = os.path.join(work_dir, 'examples_eval')
    os.makedirs(examples_train_local, exist_ok=True)
    os.makedirs(examples_eval_local, exist_ok=True)

    logger.info(f"Downloading train examples from {artifacts['examples_train']}")
    subprocess.run(['gsutil', '-m', 'cp', '-r', '{artifacts['examples_train']}/*', examples_train_local], check=True)

    logger.info(f"Downloading eval examples from {artifacts['examples_eval']}")
    subprocess.run(['gsutil', '-m', 'cp', '-r', '{artifacts['examples_eval']}/*', examples_eval_local], check=True)

    # Import transform module and run preprocessing_fn test
    logger.info("="*60)
    logger.info("TESTING PREPROCESSING_FN")
    logger.info("="*60)

    import tensorflow as tf
    import tensorflow_transform as tft
    import tensorflow_transform.beam as tft_beam
    from tensorflow_transform.tf_metadata import schema_utils
    from tfx_bsl.tfxio import tf_example_record
    import apache_beam as beam

    # Load schema
    from tensorflow_metadata.proto.v0 import schema_pb2
    from google.protobuf import text_format

    with open(schema_local, 'r') as f:
        schema = text_format.Parse(f.read(), schema_pb2.Schema())
    logger.info(f"Loaded schema with {{len(schema.feature)}} features")

    # Import preprocessing_fn
    sys.path.insert(0, work_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location("transform_module", transform_local)
    transform_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transform_module)
    preprocessing_fn = transform_module.preprocessing_fn
    logger.info("Loaded preprocessing_fn from transform_module")

    # Output directories
    transform_output_dir = os.path.join(work_dir, 'transform_output')
    os.makedirs(transform_output_dir, exist_ok=True)

    # Run Transform with DirectRunner
    logger.info("Running Transform with DirectRunner...")

    train_files = tf.io.gfile.glob(os.path.join(examples_train_local, '*'))
    eval_files = tf.io.gfile.glob(os.path.join(examples_eval_local, '*'))
    logger.info(f"Train files: {{len(train_files)}}, Eval files: {{len(eval_files)}}")

    # Create TFT context and run
    with beam.Pipeline() as pipeline:
        with tft_beam.Context(temp_dir=os.path.join(work_dir, 'tft_temp')):
            # Create TFXIO for reading examples
            tfxio = tf_example_record.TFExampleRecord(
                file_pattern=train_files + eval_files,
                schema=schema,
                telemetry_descriptors=['test_transform']
            )

            # Read raw data
            raw_data = (
                pipeline
                | 'ReadData' >> tfxio.BeamSource()
            )

            # Get raw dataset metadata
            raw_dataset_metadata = tfxio.TensorAdapterConfig()

            # Analyze and transform
            (transformed_dataset, transform_fn) = (
                (raw_data, raw_dataset_metadata)
                | 'AnalyzeAndTransform' >> tft_beam.AnalyzeAndTransformDataset(preprocessing_fn)
            )

            # Write transform function
            _ = (
                transform_fn
                | 'WriteTransformFn' >> tft_beam.WriteTransformFn(transform_output_dir)
            )

    logger.info("="*60)
    logger.info("TRANSFORM COMPLETED SUCCESSFULLY!")
    logger.info("="*60)

    # Upload results
    logger.info(f"Uploading transform output to {output_path}")
    subprocess.run(['gsutil', '-m', 'cp', '-r', transform_output_dir, '{output_path}'], check=True)

    logger.info("Transform test passed!")

if __name__ == '__main__':
    main()
'''


def main():
    parser = argparse.ArgumentParser(description='Test services.py transform generation')
    parser.add_argument('--feature-config-id', type=int, default=9, help='FeatureConfig ID')
    parser.add_argument('--source-exp', default='qt-91-20260108-163710', help='Source experiment for raw examples')
    parser.add_argument('--dry-run', action='store_true', help='Generate code but do not submit job')

    args = parser.parse_args()

    from google.cloud import storage, aiplatform

    run_id = f'transform-test-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
    logger.info(f"Run ID: {run_id}")

    # Get feature config from database
    logger.info(f"Loading FeatureConfig {args.feature_config_id}...")
    feature_config = FeatureConfig.objects.get(id=args.feature_config_id)
    logger.info(f"  FeatureConfig: {feature_config.name}")
    logger.info(f"  Config Type: {feature_config.config_type}")
    logger.info(f"  Target Column: {feature_config.target_column}")

    # Get generated transform code
    transform_code = feature_config.generated_transform_code
    if not transform_code:
        logger.error("No generated_transform_code found!")
        sys.exit(1)

    logger.info(f"Transform code: {len(transform_code)} chars")

    # Validate syntax
    is_valid, error_msg, error_line = validate_python_code(transform_code, 'transform')
    if not is_valid:
        logger.error(f"Generated code is INVALID: {error_msg} at line {error_line}")
        with open('/tmp/invalid_transform.py', 'w') as f:
            f.write(transform_code)
        logger.error("Saved invalid code to /tmp/invalid_transform.py")
        sys.exit(1)

    logger.info("Generated code is syntactically valid")

    # Show the target column section
    if 'TARGET COLUMN' in transform_code:
        start = transform_code.find('# TARGET COLUMN')
        end = transform_code.find('return outputs')
        logger.info("Target column code:")
        for line in transform_code[start:end].split('\n')[:20]:
            logger.info(f"  {line}")

    # Find artifacts
    logger.info(f"Finding artifacts from {args.source_exp}...")
    artifacts = find_artifacts(args.source_exp)
    for k, v in artifacts.items():
        logger.info(f"  {k}: {v}")

    # Upload transform code
    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)
    transform_blob_path = f'{run_id}/transform_module.py'
    bucket.blob(transform_blob_path).upload_from_string(transform_code)
    transform_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{transform_blob_path}'
    logger.info(f"Uploaded transform to {transform_gcs_path}")

    # Create runner script
    output_path = f'gs://{ARTIFACTS_BUCKET}/{run_id}/transform_output'
    runner_script = create_transform_runner_script(artifacts, transform_gcs_path, output_path)

    # Upload runner script
    runner_blob_path = f'{run_id}/runner.py'
    bucket.blob(runner_blob_path).upload_from_string(runner_script)
    runner_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{runner_blob_path}'
    logger.info(f"Uploaded runner to {runner_gcs_path}")

    if args.dry_run:
        logger.info("DRY RUN - not submitting")
        logger.info(f"Generated transform saved to: {transform_gcs_path}")
        logger.info(f"Runner script saved to: {runner_gcs_path}")
        logger.info(f"You can inspect with: gsutil cat {transform_gcs_path}")
        return

    # Submit CustomJob
    aiplatform.init(project=PROJECT_ID, location=REGION)

    job = aiplatform.CustomJob(
        display_name=f'transform-test-{run_id}',
        worker_pool_specs=[{
            'machine_spec': {'machine_type': 'n1-standard-4'},
            'replica_count': 1,
            'container_spec': {
                'image_uri': TFX_IMAGE,
                'command': ['bash', '-c', f'gsutil cp {runner_gcs_path} /tmp/runner.py && python /tmp/runner.py'],
            },
        }],
        staging_bucket=f'gs://{STAGING_BUCKET}',
    )

    logger.info("Submitting CustomJob...")
    job.submit()

    job_id = job.resource_name.split('/')[-1]
    logger.info(f"""
================================================================================
CUSTOM JOB SUBMITTED - Testing services.py Transform
================================================================================
Run ID: {run_id}
Job: {job.resource_name}
Job ID: {job_id}

Monitor:
  gcloud ai custom-jobs describe {job_id} --region={REGION}

Logs:
  gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="{job_id}"' \\
      --project={PROJECT_ID} --limit=100 --format='value(textPayload)'

Generated transform:
  gsutil cat {transform_gcs_path}

Output:
  {output_path}
================================================================================
""")


if __name__ == '__main__':
    main()
