#!/usr/bin/env python3
"""
Run Trainer Only - Vertex AI CustomJob

Submits a CustomJob that runs the TFX Trainer using existing pipeline artifacts.
No need to wait for the full pipeline - just tests the trainer code.

Usage:
    python scripts/run_trainer_only.py --source qt-58-20251230-123120 --epochs 5
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ID = 'b2b-recs'
REGION = 'europe-central2'
STAGING_BUCKET = 'b2b-recs-pipeline-staging'
ARTIFACTS_BUCKET = 'b2b-recs-quicktest-artifacts'
TRAINER_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer:latest'


def find_artifacts(source_exp: str) -> dict:
    """Find Transform artifacts from a completed experiment."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(STAGING_BUCKET)

    prefix = f'pipeline_root/{source_exp}/'
    blobs = list(bucket.list_blobs(prefix=prefix))
    paths = [b.name for b in blobs]

    # Find component outputs
    transform_base = None
    schema_path = None

    for p in paths:
        if 'Transform_' in p and '/transform_graph/' in p and not transform_base:
            # Get the Transform component base path
            parts = p.split('/')
            for i, part in enumerate(parts):
                if part.startswith('Transform_'):
                    transform_base = '/'.join(parts[:i+1])
                    break
        if 'SchemaGen_' in p and 'schema.pbtxt' in p:
            schema_path = p

    if not transform_base or not schema_path:
        raise ValueError(f"Could not find artifacts in {prefix}")

    return {
        'transform_graph': f'gs://{STAGING_BUCKET}/{transform_base}/transform_graph',
        'transformed_examples_train': f'gs://{STAGING_BUCKET}/{transform_base}/transformed_examples/Split-train',
        'transformed_examples_eval': f'gs://{STAGING_BUCKET}/{transform_base}/transformed_examples/Split-eval',
        'schema': f'gs://{STAGING_BUCKET}/{schema_path}',
    }


def generate_patched_trainer(source_exp: str, epochs: int) -> str:
    """Generate patched trainer_module.py with the proper gradient fix using tf.Variable accumulators."""
    from google.cloud import storage
    import re

    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)
    blob = bucket.blob(f'{source_exp}/trainer_module.py')

    if not blob.exists():
        raise ValueError(f"No trainer_module.py found in {source_exp}")

    code = blob.download_as_string().decode('utf-8')

    # Update epochs
    code = re.sub(r'EPOCHS = \d+', f'EPOCHS = {epochs}', code)

    logger.info("Applying tf.Variable gradient accumulator fix...")

    # Use regex to replace the gradient stats initialization (handles any existing version)
    init_pattern = r'# Gradient.*?\n\s+self\._gradient_stats = dict\(query=\[\], candidate=\[\]\)'
    new_init = """# Gradient statistics accumulators (tf.Variables for graph-mode updates)
        self._grad_accum = {}
        for tower in ['query', 'candidate']:
            self._grad_accum[tower] = {
                'sum': tf.Variable(0.0, trainable=False, name=f'{tower}_grad_sum'),
                'sum_sq': tf.Variable(0.0, trainable=False, name=f'{tower}_grad_sum_sq'),
                'count': tf.Variable(0.0, trainable=False, name=f'{tower}_grad_count'),
                'min': tf.Variable(float('inf'), trainable=False, name=f'{tower}_grad_min'),
                'max': tf.Variable(float('-inf'), trainable=False, name=f'{tower}_grad_max'),
                'hist_counts': tf.Variable(tf.zeros(25, dtype=tf.int32), trainable=False, name=f'{tower}_grad_hist'),
            }"""
    code = re.sub(init_pattern, new_init, code, flags=re.DOTALL)

    # Replace entire train_step gradient collection block using regex
    # Match from "# Store gradient" or "# Accumulate gradient" to "# Update metrics"
    train_step_pattern = r'(        # (?:Store|Accumulate) gradient.*?)(\n        # Update metrics)'
    new_train_step = r"""        # Accumulate gradient statistics using tf ops (graph compatible)
        for grad, var in zip(gradients, self.trainable_variables):
            if grad is not None:
                var_name = var.name.lower()
                grad_flat = tf.reshape(tf.cast(grad, tf.float32), [-1])

                if 'query' in var_name or 'buyer' in var_name:
                    tower = 'query'
                elif 'candidate' in var_name or 'product' in var_name:
                    tower = 'candidate'
                else:
                    continue

                accum = self._grad_accum[tower]
                batch_sum = tf.reduce_sum(grad_flat)
                batch_sum_sq = tf.reduce_sum(tf.square(grad_flat))
                batch_count = tf.cast(tf.size(grad_flat), tf.float32)

                accum['sum'].assign_add(batch_sum)
                accum['sum_sq'].assign_add(batch_sum_sq)
                accum['count'].assign_add(batch_count)
                accum['min'].assign(tf.minimum(accum['min'], tf.reduce_min(grad_flat)))
                accum['max'].assign(tf.maximum(accum['max'], tf.reduce_max(grad_flat)))

                grad_clipped = tf.clip_by_value(grad_flat, -1.0, 1.0)
                hist = tf.histogram_fixed_width(grad_clipped, [-1.0, 1.0], nbins=25)
                accum['hist_counts'].assign_add(hist)
\2"""
    code = re.sub(train_step_pattern, new_train_step, code, flags=re.DOTALL)

    # Replace _gradient_stats check with _grad_accum
    code = code.replace("if not hasattr(self.model, '_gradient_stats'):", "if not hasattr(self.model, '_grad_accum'):")

    # Replace entire GradientStatsCallback on_epoch_end loop using regex
    callback_pattern = r'(        for tower in \[\'query\', \'candidate\'\]:\n            (?:grads_list|accum) = self\.model\._(?:gradient_stats|grad_accum).*?)(\n\nclass |\n\ndef _write_mlflow)'
    new_callback = r"""        for tower in ['query', 'candidate']:
            accum = self.model._grad_accum.get(tower)
            if accum is None:
                continue

            count = float(accum['count'].numpy())
            if count == 0:
                continue

            total_sum = float(accum['sum'].numpy())
            total_sum_sq = float(accum['sum_sq'].numpy())
            grad_min = float(accum['min'].numpy())
            grad_max = float(accum['max'].numpy())
            hist_counts = accum['hist_counts'].numpy()

            mean = total_sum / count
            variance = (total_sum_sq / count) - (mean ** 2)
            std = float(np.sqrt(max(0, variance)))
            norm = float(np.sqrt(total_sum_sq))

            _mlflow_client.log_metric(tower + '_grad_mean', mean, step=epoch)
            _mlflow_client.log_metric(tower + '_grad_std', std, step=epoch)
            _mlflow_client.log_metric(tower + '_grad_min', grad_min, step=epoch)
            _mlflow_client.log_metric(tower + '_grad_max', grad_max, step=epoch)
            _mlflow_client.log_metric(tower + '_grad_norm', norm, step=epoch)

            if epoch == 0:
                bin_edges = np.linspace(-1.0, 1.0, self.NUM_HISTOGRAM_BINS + 1)
                edges_str = ','.join([f'{e:.8f}' for e in bin_edges])
                _mlflow_client.log_param(f'{tower}_grad_hist_bin_edges', edges_str)

            for i, count_val in enumerate(hist_counts):
                _mlflow_client.log_metric(f'{tower}_grad_hist_bin_{i}', int(count_val), step=epoch)

            # Reset accumulators
            accum['sum'].assign(0.0)
            accum['sum_sq'].assign(0.0)
            accum['count'].assign(0.0)
            accum['min'].assign(float('inf'))
            accum['max'].assign(float('-inf'))
            accum['hist_counts'].assign(tf.zeros(25, dtype=tf.int32))
\2"""
    code = re.sub(callback_pattern, new_callback, code, flags=re.DOTALL)

    header = f"""# PATCHED TRAINER - tf.Variable gradient accumulators
# Source: {source_exp}
# Epochs: {epochs}
# Fix: Uses tf.Variable accumulators updated with tf ops (graph-compatible)
# Generated: {datetime.now().isoformat()}

"""
    return header + code


def create_runner_script(artifacts: dict, trainer_gcs_path: str, output_path: str, epochs: int) -> str:
    """Create the script that will run inside the CustomJob."""

    return f'''#!/usr/bin/env python3
"""Trainer runner script for CustomJob."""
import os
import sys
import logging
import tempfile
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("STANDALONE TRAINER TEST")
    logger.info("="*60)

    work_dir = tempfile.mkdtemp(prefix='trainer_test_')
    logger.info(f"Work dir: {{work_dir}}")

    # Download trainer module
    trainer_local = os.path.join(work_dir, 'trainer_module.py')
    logger.info(f"Downloading trainer from {trainer_gcs_path}")
    subprocess.run(['gsutil', 'cp', '{trainer_gcs_path}', trainer_local], check=True)

    # Download transform graph using rsync
    transform_local = os.path.join(work_dir, 'transform_graph')
    os.makedirs(transform_local, exist_ok=True)
    logger.info(f"Downloading transform graph from {artifacts['transform_graph']}")
    subprocess.run(['gsutil', '-m', 'rsync', '-r', '{artifacts['transform_graph']}', transform_local], check=True)

    # Download schema
    schema_local = os.path.join(work_dir, 'schema.pbtxt')
    logger.info(f"Downloading schema from {artifacts['schema']}")
    subprocess.run(['gsutil', 'cp', '{artifacts['schema']}', schema_local], check=True)

    # Set environment
    os.environ['MLFLOW_TRACKING_URI'] = 'https://mlflow-server-3dmqemfmxq-lm.a.run.app'
    os.environ['MLFLOW_RUN_NAME'] = 'trainer-standalone-test'

    # Import trainer module
    logger.info("Importing trainer module...")
    sys.path.insert(0, work_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location("trainer_module", trainer_local)
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)

    # Create FnArgs
    class FnArgs:
        pass

    fn_args = FnArgs()
    fn_args.train_files = ['{artifacts['transformed_examples_train']}/*']
    fn_args.eval_files = ['{artifacts['transformed_examples_eval']}/*']
    fn_args.transform_output = transform_local  # trainer uses transform_output, not transform_graph_path
    fn_args.schema_file = schema_local
    fn_args.serving_model_dir = os.path.join(work_dir, 'serving_model')
    fn_args.model_run_dir = os.path.join(work_dir, 'model_run')
    fn_args.train_steps = None
    fn_args.eval_steps = None
    fn_args.custom_config = {{
        'epochs': {epochs},
        'batch_size': 4096,
        'learning_rate': 0.1,
    }}

    # Create data accessor
    from tfx_bsl.public import tfxio

    class DataAccessor:
        def tf_dataset_factory(self, file_pattern, options, schema):
            import tensorflow as tf

            # Handle list of patterns
            if isinstance(file_pattern, list):
                file_pattern = file_pattern[0]

            files = tf.io.gfile.glob(file_pattern)
            logger.info(f"Found {{len(files)}} files matching {{file_pattern}}")

            dataset = tf.data.TFRecordDataset(files, compression_type='GZIP')

            # Load transform output for feature spec
            import tensorflow_transform as tft
            tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)
            feature_spec = tf_transform_output.transformed_feature_spec()

            def parse_fn(example):
                return tf.io.parse_single_example(example, feature_spec)

            dataset = dataset.map(parse_fn, num_parallel_calls=tf.data.AUTOTUNE)
            dataset = dataset.batch(options.batch_size)
            dataset = dataset.prefetch(tf.data.AUTOTUNE)
            return dataset

    fn_args.data_accessor = DataAccessor()

    # Create output directories
    os.makedirs(fn_args.serving_model_dir, exist_ok=True)
    os.makedirs(fn_args.model_run_dir, exist_ok=True)

    # Run training
    logger.info("="*60)
    logger.info("STARTING TRAINING")
    logger.info("="*60)

    trainer.run_fn(fn_args)

    logger.info("="*60)
    logger.info("TRAINING COMPLETED SUCCESSFULLY")
    logger.info("="*60)

    # Upload model
    logger.info(f"Uploading model to {output_path}")
    subprocess.run(['gsutil', '-m', 'cp', '-r', fn_args.serving_model_dir, '{output_path}'], check=True)

if __name__ == '__main__':
    main()
'''


def main():
    parser = argparse.ArgumentParser(description='Run Trainer only using existing artifacts')
    parser.add_argument('--source', default='qt-58-20251230-123120', help='Source experiment for artifacts')
    parser.add_argument('--epochs', type=int, default=5, help='Training epochs')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')

    args = parser.parse_args()

    from google.cloud import storage, aiplatform

    run_id = f'trainer-test-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
    logger.info(f"Run ID: {run_id}")

    # Find artifacts
    logger.info(f"Finding artifacts from {args.source}...")
    artifacts = find_artifacts(args.source)
    for k, v in artifacts.items():
        logger.info(f"  {k}: {v}")

    # Generate patched trainer
    logger.info("Generating patched trainer...")
    trainer_code = generate_patched_trainer(args.source, args.epochs)

    # Upload trainer
    client = storage.Client()
    bucket = client.bucket(ARTIFACTS_BUCKET)
    trainer_blob_path = f'{run_id}/trainer_module.py'
    bucket.blob(trainer_blob_path).upload_from_string(trainer_code)
    trainer_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{trainer_blob_path}'
    logger.info(f"Uploaded trainer to {trainer_gcs_path}")

    # Create runner script
    output_path = f'gs://{ARTIFACTS_BUCKET}/{run_id}/model'
    runner_script = create_runner_script(artifacts, trainer_gcs_path, output_path, args.epochs)

    # Upload runner script
    runner_blob_path = f'{run_id}/runner.py'
    bucket.blob(runner_blob_path).upload_from_string(runner_script)
    runner_gcs_path = f'gs://{ARTIFACTS_BUCKET}/{runner_blob_path}'
    logger.info(f"Uploaded runner to {runner_gcs_path}")

    if args.dry_run:
        logger.info("DRY RUN - not submitting")
        logger.info(f"Would run: {runner_gcs_path}")
        return

    # Submit CustomJob
    aiplatform.init(project=PROJECT_ID, location=REGION)

    job = aiplatform.CustomJob(
        display_name=f'trainer-test-{run_id}',
        worker_pool_specs=[{
            'machine_spec': {'machine_type': 'n1-standard-4'},
            'replica_count': 1,
            'container_spec': {
                'image_uri': TRAINER_IMAGE,
                'command': ['bash', '-c', f'gsutil cp {runner_gcs_path} /tmp/runner.py && python /tmp/runner.py'],
            },
        }],
        staging_bucket=f'gs://{STAGING_BUCKET}',
    )

    logger.info("Submitting CustomJob...")
    job.submit()

    logger.info(f"""
================================================================================
CUSTOM JOB SUBMITTED
================================================================================
Run ID: {run_id}
Job: {job.resource_name}
Epochs: {args.epochs}

Monitor:
  gcloud ai custom-jobs describe {job.resource_name.split('/')[-1]} --region={REGION}

Logs:
  https://console.cloud.google.com/logs/query?project={PROJECT_ID}

Output:
  {output_path}
================================================================================
""")


if __name__ == '__main__':
    main()
