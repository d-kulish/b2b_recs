#!/usr/bin/env python3
"""
Direct preprocessing_fn test - calls the function with mock tensor inputs.
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


def create_direct_runner(transform_gcs_path: str) -> str:
    """Create runner that calls preprocessing_fn directly with tensors."""
    return f'''#!/usr/bin/env python3
"""Direct preprocessing_fn test with mock tensors."""
import os
import sys
import tempfile
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("DIRECT PREPROCESSING_FN TEST")
    logger.info("="*60)

    work_dir = tempfile.mkdtemp(prefix='transform_direct_')
    transform_local = os.path.join(work_dir, 'transform_module.py')

    logger.info("Downloading transform module...")
    subprocess.run(['gsutil', 'cp', '{transform_gcs_path}', transform_local], check=True)

    import tensorflow as tf
    import tensorflow_transform as tft

    # Load transform module with tft in namespace
    logger.info("Loading transform module...")
    with open(transform_local, 'r') as f:
        transform_code = f.read()

    module_globals = {{
        'tf': tf,
        'tft': tft,
        'math': __import__('math'),
    }}
    exec(transform_code, module_globals)
    preprocessing_fn = module_globals['preprocessing_fn']
    logger.info("Loaded preprocessing_fn")

    # Create mock input tensors matching the schema
    logger.info("="*60)
    logger.info("CREATING MOCK INPUT TENSORS")
    logger.info("="*60)

    batch_size = 100
    inputs = {{
        'customer_id': tf.constant([1001, 1002, 1003] * (batch_size // 3 + 1), dtype=tf.int64)[:batch_size],
        'product_id': tf.constant([2001, 2002, 2003] * (batch_size // 3 + 1), dtype=tf.int64)[:batch_size],
        'date': tf.constant([20260101, 20260102, 20260103] * (batch_size // 3 + 1), dtype=tf.int64)[:batch_size],
        'cust_value': tf.random.uniform([batch_size], 0, 1000, dtype=tf.float32),
        'sales': tf.random.uniform([batch_size], 0, 500, dtype=tf.float32),
        'category': tf.constant(['Electronics', 'Clothing', 'Food'] * (batch_size // 3 + 1), dtype=tf.string)[:batch_size],
        'sub_category': tf.constant(['Phones', 'Shirts', 'Snacks'] * (batch_size // 3 + 1), dtype=tf.string)[:batch_size],
        'city': tf.constant(['Kyiv', 'Lviv', 'Odesa'] * (batch_size // 3 + 1), dtype=tf.string)[:batch_size],
    }}

    for k, v in inputs.items():
        logger.info(f"  {{k}}: shape={{v.shape}}, dtype={{v.dtype}}")

    # Call preprocessing_fn in graph mode (like TFT does)
    logger.info("="*60)
    logger.info("CALLING PREPROCESSING_FN (graph tracing)")
    logger.info("="*60)

    @tf.function
    def trace_preprocessing():
        return preprocessing_fn(inputs)

    try:
        # This traces the function - same as TFT analyze phase
        outputs = trace_preprocessing()
        logger.info("SUCCESS! preprocessing_fn traced without errors")
        logger.info("Output keys:")
        for k, v in outputs.items():
            logger.info(f"  {{k}}: shape={{v.shape}}, dtype={{v.dtype}}")

        # Check specific outputs for ranking
        if 'sales_target' in outputs:
            logger.info(f"\\nsales_target shape: {{outputs['sales_target'].shape}}")
        if 'sales_clip_lower' in outputs:
            logger.info(f"sales_clip_lower shape: {{outputs['sales_clip_lower'].shape}}")
        if 'sales_clip_upper' in outputs:
            logger.info(f"sales_clip_upper shape: {{outputs['sales_clip_upper'].shape}}")

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
    parser = argparse.ArgumentParser(description='Direct transform test')
    parser.add_argument('--feature-config-id', type=int, default=9)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    from google.cloud import storage, aiplatform

    run_id = f'transform-direct-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
    logger.info(f"Run ID: {run_id}")

    fc = FeatureConfig.objects.get(id=args.feature_config_id)
    logger.info(f"FeatureConfig: {fc.name}")

    transform_code = fc.generated_transform_code
    logger.info(f"Transform code: {len(transform_code)} chars")

    # Upload
    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)
    transform_blob_path = f'{run_id}/transform_module.py'
    bucket.blob(transform_blob_path).upload_from_string(transform_code)
    transform_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{transform_blob_path}'

    runner_script = create_direct_runner(transform_gcs_path)
    runner_blob_path = f'{run_id}/runner.py'
    bucket.blob(runner_blob_path).upload_from_string(runner_script)
    runner_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{runner_blob_path}'

    logger.info(f"Uploaded to {transform_gcs_path}")

    if args.dry_run:
        logger.info("DRY RUN")
        return

    aiplatform.init(project=PROJECT_ID, location=REGION)

    job = aiplatform.CustomJob(
        display_name=f'transform-direct-{run_id}',
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

    job.submit()
    job_id = job.resource_name.split('/')[-1]
    logger.info(f"JOB SUBMITTED: {job_id}")
    logger.info(f"Monitor: gcloud ai custom-jobs describe {job_id} --region={REGION}")
    logger.info(f"Logs: gcloud logging read 'resource.type=\"ml_job\" AND resource.labels.job_id=\"{job_id}\"' --project={PROJECT_ID} --limit=50 --format='value(textPayload)'")


if __name__ == '__main__':
    main()
