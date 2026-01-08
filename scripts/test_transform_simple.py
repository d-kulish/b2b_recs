#!/usr/bin/env python3
"""
Simple Transform Test - validates preprocessing_fn can be traced.

Submits a CustomJob that:
1. Downloads the transform_module.py
2. Imports preprocessing_fn
3. Uses tft.get_analyze_input_columns() to trace the function (same as TFX Transform)
4. Reports success/failure

This tests the same code path that caused the original error.
"""

import argparse
import logging
import os
import sys
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from ml_platform.models import FeatureConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ID = 'b2b-recs'
REGION = 'europe-central2'
STAGING_BUCKET = 'b2b-recs-pipeline-staging'
ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
TFX_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer:latest'


def find_schema(source_exp: str) -> str:
    """Find schema path from experiment."""
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(STAGING_BUCKET)
    prefix = f'pipeline_root/{source_exp}/'
    blobs = list(bucket.list_blobs(prefix=prefix))
    for b in blobs:
        if 'SchemaGen_' in b.name and 'schema.pbtxt' in b.name:
            return f'gs://{STAGING_BUCKET}/{b.name}'
    raise ValueError(f"Schema not found in {prefix}")


def create_simple_runner(transform_gcs_path: str, schema_gcs_path: str) -> str:
    """Create a simple test runner that traces preprocessing_fn."""
    return f'''#!/usr/bin/env python3
"""Simple preprocessing_fn trace test."""
import os
import sys
import tempfile
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("SIMPLE TRANSFORM TRACE TEST")
    logger.info("="*60)

    work_dir = tempfile.mkdtemp(prefix='transform_trace_')

    # Download files
    transform_local = os.path.join(work_dir, 'transform_module.py')
    schema_local = os.path.join(work_dir, 'schema.pbtxt')

    logger.info("Downloading transform module...")
    subprocess.run(['gsutil', 'cp', '{transform_gcs_path}', transform_local], check=True)

    logger.info("Downloading schema...")
    subprocess.run(['gsutil', 'cp', '{schema_gcs_path}', schema_local], check=True)

    # Import TFT
    import tensorflow as tf
    import tensorflow_transform as tft
    from tensorflow_metadata.proto.v0 import schema_pb2
    from google.protobuf import text_format
    from tensorflow_transform.tf_metadata import schema_utils

    # Load schema
    with open(schema_local, 'r') as f:
        schema = text_format.Parse(f.read(), schema_pb2.Schema())
    logger.info(f"Schema has {{len(schema.feature)}} features")

    # Get feature spec from schema
    feature_spec = schema_utils.schema_as_feature_spec(schema).feature_spec
    logger.info(f"Feature spec keys: {{list(feature_spec.keys())}}")

    # Load transform module - IMPORTANT: exec in global namespace so tft is available
    logger.info("Loading transform module...")
    with open(transform_local, 'r') as f:
        transform_code = f.read()

    # Execute the module code in a namespace that has tft
    module_globals = {{
        'tf': tf,
        'tft': tft,
        'math': __import__('math'),
    }}
    exec(transform_code, module_globals)
    preprocessing_fn = module_globals['preprocessing_fn']
    logger.info("Loaded preprocessing_fn")

    # Test: trace the preprocessing_fn (this is what TFX Transform does)
    logger.info("="*60)
    logger.info("TRACING PREPROCESSING_FN (tft.get_analyze_input_columns)")
    logger.info("="*60)

    try:
        analyze_input_columns = tft.get_analyze_input_columns(
            preprocessing_fn,
            feature_spec
        )
        logger.info(f"SUCCESS! Analyze input columns: {{analyze_input_columns}}")
    except Exception as e:
        logger.error(f"FAILED: {{type(e).__name__}}: {{e}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Also test transform input columns
    logger.info("="*60)
    logger.info("TRACING (tft.get_transform_input_columns)")
    logger.info("="*60)

    try:
        transform_input_columns = tft.get_transform_input_columns(
            preprocessing_fn,
            feature_spec
        )
        logger.info(f"SUCCESS! Transform input columns: {{transform_input_columns}}")
    except Exception as e:
        logger.error(f"FAILED: {{type(e).__name__}}: {{e}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    logger.info("="*60)
    logger.info("ALL TESTS PASSED!")
    logger.info("="*60)

if __name__ == '__main__':
    main()
'''


def main():
    parser = argparse.ArgumentParser(description='Simple transform trace test')
    parser.add_argument('--feature-config-id', type=int, default=9)
    parser.add_argument('--source-exp', default='qt-91-20260108-163710')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    from google.cloud import storage, aiplatform

    run_id = f'transform-trace-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
    logger.info(f"Run ID: {run_id}")

    # Get feature config
    fc = FeatureConfig.objects.get(id=args.feature_config_id)
    logger.info(f"FeatureConfig: {fc.name}")

    transform_code = fc.generated_transform_code
    logger.info(f"Transform code: {len(transform_code)} chars")

    # Find schema
    schema_path = find_schema(args.source_exp)
    logger.info(f"Schema: {schema_path}")

    # Upload transform code
    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)
    transform_blob_path = f'{run_id}/transform_module.py'
    bucket.blob(transform_blob_path).upload_from_string(transform_code)
    transform_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{transform_blob_path}'
    logger.info(f"Uploaded transform to {transform_gcs_path}")

    # Create and upload runner
    runner_script = create_simple_runner(transform_gcs_path, schema_path)
    runner_blob_path = f'{run_id}/runner.py'
    bucket.blob(runner_blob_path).upload_from_string(runner_script)
    runner_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{runner_blob_path}'
    logger.info(f"Uploaded runner to {runner_gcs_path}")

    if args.dry_run:
        logger.info("DRY RUN - not submitting")
        return

    # Submit job
    aiplatform.init(project=PROJECT_ID, location=REGION)

    job = aiplatform.CustomJob(
        display_name=f'transform-trace-{run_id}',
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
JOB SUBMITTED: {job_id}
================================================================================
Monitor: gcloud ai custom-jobs describe {job_id} --region={REGION}
Logs: gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="{job_id}"' --project={PROJECT_ID} --limit=50 --format='value(textPayload)'
================================================================================
""")


if __name__ == '__main__':
    main()
