"""
Native TFX Pipeline for Quick Tests

This module defines a TFX pipeline that runs on Vertex AI Pipelines.
It uses proper TFX components:

1. BigQueryExampleGen - Read data from BigQuery using generated SQL
2. StatisticsGen - Compute dataset statistics using TFDV
3. SchemaGen - Infer schema from statistics
4. Transform - Apply preprocessing_fn from generated transform_module.py
5. Trainer - Train TFRS model using generated trainer_module.py

The pipeline is compiled to a JSON spec that can be submitted to Vertex AI.
"""
import os
import logging
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


def create_tfx_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    bigquery_query: str,
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    project_id: str = 'b2b-recs',
    region: str = 'europe-central2',
    epochs: int = 10,
    batch_size: int = 4096,
    learning_rate: float = 0.001,
    train_steps: Optional[int] = None,
    eval_steps: Optional[int] = None,
):
    """
    Create a TFX pipeline for Quick Tests.

    Args:
        pipeline_name: Name of the pipeline
        pipeline_root: GCS path for pipeline artifacts
        bigquery_query: SQL query to extract training data
        transform_module_path: GCS path to transform_module.py
        trainer_module_path: GCS path to trainer_module.py
        output_path: GCS path for output artifacts (model, metrics)
        project_id: GCP project ID
        region: GCP region
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate for optimizer
        train_steps: Max training steps (None = use full dataset)
        eval_steps: Max evaluation steps (None = use full eval dataset)

    Returns:
        TFX Pipeline instance
    """
    try:
        import tfx
        from tfx import v1 as tfx_v1
        from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
        from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer
        from tfx.proto import example_gen_pb2, trainer_pb2
        from tfx.dsl.components.common import resolver
        from tfx.dsl.experimental import latest_blessed_model_resolver
        from tfx.orchestration import pipeline as tfx_pipeline

        logger.info(f"Creating TFX pipeline: {pipeline_name}")

        # =================================================================
        # COMPONENT 1: BigQueryExampleGen
        # Reads data from BigQuery and outputs TFRecords
        # =================================================================
        # Configure train/eval split (80/20 random split)
        output_config = example_gen_pb2.Output(
            split_config=example_gen_pb2.SplitConfig(
                splits=[
                    example_gen_pb2.SplitConfig.Split(name='train', hash_buckets=8),
                    example_gen_pb2.SplitConfig.Split(name='eval', hash_buckets=2),
                ]
            )
        )

        example_gen = BigQueryExampleGen(
            query=bigquery_query,
            output_config=output_config,
        )

        # =================================================================
        # COMPONENT 2: StatisticsGen
        # Computes statistics on the dataset using TFDV
        # =================================================================
        statistics_gen = StatisticsGen(
            examples=example_gen.outputs['examples']
        )

        # =================================================================
        # COMPONENT 3: SchemaGen
        # Infers schema from statistics
        # =================================================================
        schema_gen = SchemaGen(
            statistics=statistics_gen.outputs['statistics']
        )

        # =================================================================
        # COMPONENT 4: Transform
        # Applies preprocessing_fn from the generated transform module
        # =================================================================
        transform = Transform(
            examples=example_gen.outputs['examples'],
            schema=schema_gen.outputs['schema'],
            module_file=transform_module_path,
        )

        # =================================================================
        # COMPONENT 5: Trainer
        # Trains the TFRS model using the generated trainer module
        # =================================================================
        # Training configuration
        train_args = trainer_pb2.TrainArgs(
            num_steps=train_steps,  # None = use full dataset
        )
        eval_args = trainer_pb2.EvalArgs(
            num_steps=eval_steps,  # None = use full eval dataset
        )

        # Custom config passed to run_fn
        custom_config = {
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': learning_rate,
        }

        trainer = Trainer(
            module_file=trainer_module_path,
            examples=transform.outputs['transformed_examples'],
            transform_graph=transform.outputs['transform_graph'],
            schema=schema_gen.outputs['schema'],
            train_args=train_args,
            eval_args=eval_args,
            custom_config=custom_config,
        )

        # =================================================================
        # BUILD PIPELINE
        # =================================================================
        components = [
            example_gen,
            statistics_gen,
            schema_gen,
            transform,
            trainer,
        ]

        pipeline = tfx_pipeline.Pipeline(
            pipeline_name=pipeline_name,
            pipeline_root=pipeline_root,
            components=components,
            enable_cache=False,  # Disable caching for experiments
        )

        logger.info(f"TFX pipeline created with {len(components)} components")
        return pipeline

    except ImportError as e:
        logger.error(f"TFX import error: {e}")
        raise ImportError(
            "TFX package not installed. Run: pip install tfx>=1.14.0"
        ) from e


def compile_tfx_pipeline(
    run_id: str,
    staging_bucket: str,
    bigquery_query: str,
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    epochs: int = 10,
    batch_size: int = 4096,
    learning_rate: float = 0.001,
    output_dir: Optional[str] = None,
) -> str:
    """
    Compile a TFX pipeline to a JSON spec for Vertex AI.

    Args:
        run_id: Unique identifier for this pipeline run
        staging_bucket: GCS bucket for staging
        bigquery_query: SQL query for data extraction
        transform_module_path: GCS path to transform_module.py
        trainer_module_path: GCS path to trainer_module.py
        output_path: GCS path for output artifacts
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate
        output_dir: Directory to write compiled pipeline (default: temp dir)

    Returns:
        Path to the compiled pipeline JSON spec
    """
    try:
        from tfx.orchestration import pipeline as tfx_pipeline
        from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner

        # Create output directory if not specified
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix='tfx_pipeline_')

        output_file = os.path.join(output_dir, f'quicktest_pipeline_{run_id}.json')

        # Create the pipeline with actual parameters
        pipeline = create_tfx_pipeline(
            pipeline_name=f'quicktest-{run_id}',
            pipeline_root=f'gs://{staging_bucket}/pipeline_root/{run_id}',
            bigquery_query=bigquery_query,
            transform_module_path=transform_module_path,
            trainer_module_path=trainer_module_path,
            output_path=output_path,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
        )

        # Compile to Kubeflow v2 pipeline spec (for Vertex AI)
        runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
            config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(),
            output_filename=output_file
        )
        runner.run(pipeline)

        logger.info(f"TFX pipeline compiled to: {output_file}")
        return output_file

    except ImportError as e:
        logger.error(f"TFX import error during compilation: {e}")
        raise ImportError(
            "TFX package not installed. Run: pip install tfx>=1.14.0"
        ) from e
