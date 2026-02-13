#!/usr/bin/env python3
"""
TFX Pipeline Compile and Submit Script

This script runs in Cloud Build to:
1. Create a TFX pipeline with the specified parameters
2. Compile it to a Kubeflow v2 pipeline spec (JSON)
3. Submit the pipeline to Vertex AI
4. Write the pipeline job resource name to GCS for Django to read

Usage:
    python compile_and_submit.py \
        --run-id=qt_123 \
        --staging-bucket=b2b-recs-pipeline-staging \
        --bigquery-query="SELECT * FROM ..." \
        --transform-module-path=gs://bucket/transform.py \
        --trainer-module-path=gs://bucket/trainer.py \
        --output-path=gs://bucket/output \
        --epochs=10 \
        --batch-size=4096 \
        --learning-rate=0.001 \
        --project-id=b2b-recs \
        --region=europe-central2
"""

import argparse
import json
import logging
import os
import tempfile
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_tfx_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    bigquery_query: str,
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    project_id: str,
    region: str = 'europe-central2',
    epochs: int = 10,
    batch_size: int = 4096,
    learning_rate: float = 0.001,
    split_strategy: str = 'random',
    machine_type: str = 'e2-standard-4',
    gpu_type: str = '',
    gpu_count: int = 0,
    gpu_machine_type: str = '',
    gpu_training_region: str = 'europe-west4',
    train_steps: Optional[int] = None,
    eval_steps: Optional[int] = None,
):
    """Create a TFX pipeline for Quick Tests."""
    from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
    from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer
    from tfx.proto import example_gen_pb2, trainer_pb2, transform_pb2
    from tfx.orchestration import pipeline as tfx_pipeline

    logger.info(f"Creating TFX pipeline: {pipeline_name}, split_strategy={split_strategy}, machine_type={machine_type}")

    # Configure split based on strategy
    # All strategies use hash-based 80/20 split for train/eval
    # The temporal ordering is enforced by the SQL query's date filtering:
    # - 'random': No date filtering, pure random split
    # - 'time_holdout': SQL excludes last N days, then hash-based split
    # - 'strict_time': SQL filters to specific date window (excludes test period), then hash-based split
    logger.info(f"Using hash-based 80/20 split (strategy={split_strategy})")
    output_config = example_gen_pb2.Output(
        split_config=example_gen_pb2.SplitConfig(
            splits=[
                example_gen_pb2.SplitConfig.Split(name='train', hash_buckets=8),
                example_gen_pb2.SplitConfig.Split(name='eval', hash_buckets=2),
            ]
        )
    )

    # Component 1: BigQueryExampleGen
    example_gen = BigQueryExampleGen(
        query=bigquery_query,
        output_config=output_config,
    )

    # Component 2: StatisticsGen
    statistics_gen = StatisticsGen(
        examples=example_gen.outputs['examples']
    )

    # Component 3: SchemaGen
    schema_gen = SchemaGen(
        statistics=statistics_gen.outputs['statistics']
    )

    # Component 4: Transform
    # IMPORTANT: Analyze BOTH train and eval splits to build complete vocabulary.
    # This ensures all customer_ids and product_ids are in the vocabulary, not just
    # those that randomly landed in the train split due to hash-based splitting.
    # Without this, ~20% of IDs appearing only in eval would map to OOV embeddings.
    transform = Transform(
        examples=example_gen.outputs['examples'],
        schema=schema_gen.outputs['schema'],
        module_file=transform_module_path,
        splits_config=transform_pb2.SplitsConfig(
            analyze=['train', 'eval'],  # Build vocab from ALL data
            transform=['train', 'eval']  # Apply transforms to both splits
        ),
    )

    # Component 5: Trainer
    train_args = trainer_pb2.TrainArgs(num_steps=train_steps)
    eval_args = trainer_pb2.EvalArgs(num_steps=eval_steps)

    custom_config = {
        'epochs': epochs,
        'batch_size': batch_size,
        'learning_rate': learning_rate,
    }

    if gpu_type:
        # GPU path: Use GenericExecutor to spawn a Vertex AI Custom Job with GPU
        from tfx.dsl.components.base import executor_spec
        from tfx.extensions.google_cloud_ai_platform.trainer import executor as ai_platform_trainer_executor
        from tfx.v1.extensions.google_cloud_ai_platform import (
            ENABLE_VERTEX_KEY,
            VERTEX_REGION_KEY,
            TRAINING_ARGS_KEY,
        )

        gpu_trainer_image = f'europe-central2-docker.pkg.dev/{project_id}/tfx-builder/tfx-trainer-gpu:latest'
        logger.info(f"GPU training: {gpu_count}x {gpu_type} on {gpu_machine_type} in {gpu_training_region}")
        logger.info(f"Using GPU trainer image: {gpu_trainer_image}")

        custom_config['gpu_enabled'] = True
        custom_config['gpu_count'] = gpu_count
        custom_config[ENABLE_VERTEX_KEY] = True
        custom_config[VERTEX_REGION_KEY] = gpu_training_region
        custom_config[TRAINING_ARGS_KEY] = {
            'project': project_id,
            'worker_pool_specs': [{
                'machine_spec': {
                    'machine_type': gpu_machine_type,
                    'accelerator_type': gpu_type,
                    'accelerator_count': gpu_count,
                },
                'replica_count': 1,
                'container_spec': {
                    'image_uri': gpu_trainer_image,
                },
            }],
        }

        trainer = Trainer(
            module_file=trainer_module_path,
            examples=transform.outputs['transformed_examples'],
            transform_graph=transform.outputs['transform_graph'],
            schema=schema_gen.outputs['schema'],
            train_args=train_args,
            eval_args=eval_args,
            custom_executor_spec=executor_spec.ExecutorClassSpec(
                ai_platform_trainer_executor.GenericExecutor
            ),
            custom_config=custom_config,
        )
    else:
        # CPU path: Standard Trainer
        trainer = Trainer(
            module_file=trainer_module_path,
            examples=transform.outputs['transformed_examples'],
            transform_graph=transform.outputs['transform_graph'],
            schema=schema_gen.outputs['schema'],
            train_args=train_args,
            eval_args=eval_args,
            custom_config=custom_config,
        )

    # Build pipeline
    components = [
        example_gen,
        statistics_gen,
        schema_gen,
        transform,
        trainer,
    ]

    # Configure Dataflow for StatisticsGen and Transform components
    # This ensures scalable processing for large datasets
    # Dataflow runs in europe-west1 (Belgium) - largest EU region with best capacity.
    # europe-central2 (Warsaw) is a small region prone to ZONE_RESOURCE_POOL_EXHAUSTED.
    # e2-standard-4 uses dynamic resource pool with better availability than n1.
    dataflow_region = 'europe-west1'
    dataflow_machine_type = machine_type
    staging_bucket = f'{project_id}-pipeline-staging'
    beam_pipeline_args = [
        '--runner=DataflowRunner',
        f'--project={project_id}',
        f'--region={dataflow_region}',
        f'--temp_location=gs://{staging_bucket}/dataflow_temp',
        f'--staging_location=gs://{staging_bucket}/dataflow_staging',
        f'--machine_type={dataflow_machine_type}',
        '--disk_size_gb=50',
        '--experiments=use_runner_v2',
        '--max_num_workers=10',
        '--autoscaling_algorithm=THROUGHPUT_BASED',
    ]
    logger.info(f"Dataflow configured with machine_type={dataflow_machine_type}, region={dataflow_region}")

    pipeline = tfx_pipeline.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=components,
        enable_cache=False,
        beam_pipeline_args=beam_pipeline_args,
    )

    logger.info(f"TFX pipeline created with {len(components)} components using DataflowRunner")
    return pipeline


def compile_pipeline(pipeline, output_file: str) -> str:
    """Compile TFX pipeline to Kubeflow v2 spec."""
    from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner

    logger.info(f"Compiling pipeline to: {output_file}")

    runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
        config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(),
        output_filename=output_file
    )
    runner.run(pipeline)

    logger.info(f"Pipeline compiled successfully")
    return output_file


def submit_to_vertex_ai(
    template_path: str,
    display_name: str,
    project_id: str,
    region: str,
) -> str:
    """Submit compiled pipeline to Vertex AI."""
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
    """Write result JSON to GCS for Django to read."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    content = json.dumps(result, indent=2)
    blob.upload_from_string(content, content_type='application/json')

    logger.info(f"Result written to gs://{bucket_name}/{blob_path}")


def main():
    parser = argparse.ArgumentParser(description='Compile and submit TFX pipeline')
    parser.add_argument('--run-id', required=True, help='Unique run identifier')
    parser.add_argument('--staging-bucket', required=True, help='GCS bucket for staging')
    parser.add_argument('--bigquery-query', required=True, help='BigQuery SQL query')
    parser.add_argument('--transform-module-path', required=True, help='GCS path to transform module')
    parser.add_argument('--trainer-module-path', required=True, help='GCS path to trainer module')
    parser.add_argument('--output-path', required=True, help='GCS path for output artifacts')
    parser.add_argument('--epochs', type=int, default=10, help='Training epochs')
    parser.add_argument('--batch-size', type=int, default=4096, help='Batch size')
    parser.add_argument('--learning-rate', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--split-strategy', default='random', help='Split strategy: random, time_holdout, strict_time')
    parser.add_argument('--machine-type', default='e2-standard-4', help='Machine type for Dataflow workers (BigQueryExampleGen, StatisticsGen, Transform)')
    parser.add_argument('--gpu-type', default='', help='GPU accelerator type (e.g. NVIDIA_TESLA_T4)')
    parser.add_argument('--gpu-count', type=int, default=0, help='Number of GPUs')
    parser.add_argument('--gpu-machine-type', default='', help='Machine type for GPU Trainer')
    parser.add_argument('--gpu-training-region', default='europe-west4', help='Region for GPU training')
    parser.add_argument('--project-id', required=True, help='GCP project ID')
    parser.add_argument('--region', default='europe-central2', help='GCP region')

    args = parser.parse_args()

    try:
        # Create temp directory for compiled pipeline
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_file = os.path.join(temp_dir, f'pipeline_{args.run_id}.json')

            # Create TFX pipeline
            pipeline = create_tfx_pipeline(
                pipeline_name=f'quicktest-{args.run_id}',
                pipeline_root=f'gs://{args.staging_bucket}/pipeline_root/{args.run_id}',
                bigquery_query=args.bigquery_query,
                transform_module_path=args.transform_module_path,
                trainer_module_path=args.trainer_module_path,
                output_path=args.output_path,
                project_id=args.project_id,
                region=args.region,
                epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.learning_rate,
                split_strategy=args.split_strategy,
                machine_type=args.machine_type,
                gpu_type=args.gpu_type,
                gpu_count=args.gpu_count,
                gpu_machine_type=args.gpu_machine_type,
                gpu_training_region=args.gpu_training_region,
            )

            # Compile to JSON
            compile_pipeline(pipeline, pipeline_file)

            # Submit to Vertex AI
            display_name = f'quicktest-{args.run_id}'
            resource_name = submit_to_vertex_ai(
                template_path=pipeline_file,
                display_name=display_name,
                project_id=args.project_id,
                region=args.region,
            )

            # Write result to GCS for Django to read
            result = {
                'success': True,
                'run_id': args.run_id,
                'vertex_pipeline_job_name': resource_name,
                'display_name': display_name,
            }
            write_result_to_gcs(
                bucket_name=args.staging_bucket,
                blob_path=f'build_results/{args.run_id}.json',
                result=result,
            )

            logger.info("Pipeline compilation and submission completed successfully")
            print(f"PIPELINE_JOB_NAME={resource_name}")

    except Exception as e:
        logger.error(f"Pipeline compilation/submission failed: {e}")

        # Write error to GCS
        error_result = {
            'success': False,
            'run_id': args.run_id,
            'error': str(e),
        }
        try:
            write_result_to_gcs(
                bucket_name=args.staging_bucket,
                blob_path=f'build_results/{args.run_id}.json',
                result=error_result,
            )
        except Exception as gcs_error:
            logger.error(f"Failed to write error to GCS: {gcs_error}")

        raise


if __name__ == '__main__':
    main()
