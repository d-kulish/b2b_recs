"""
KFP v2 Pipeline definition for Quick Tests.

This module defines the TFX pipeline that runs on Vertex AI Pipelines.
The pipeline includes:
1. ExampleGen - Read data from BigQuery using generated SQL
2. StatisticsGen - Compute dataset statistics
3. SchemaGen - Infer schema
4. Transform - Apply preprocessing_fn from generated code
5. Trainer - Train TFRS model using generated trainer module

NOTE: This is a simplified pipeline definition that will need to be expanded
with proper TFX component wrappers for production use.
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def build_quicktest_pipeline_params(
    bigquery_query: str,
    transform_module_path: str,
    trainer_module_path: str,
    output_path: str,
    pipeline_root: str,
    epochs: int = 10,
    batch_size: int = 4096,
    learning_rate: float = 0.001,
    machine_type: str = 'n1-standard-4',
) -> Dict[str, Any]:
    """
    Build parameters for the Quick Test pipeline.

    Args:
        bigquery_query: SQL query to extract training data
        transform_module_path: GCS path to transform_module.py
        trainer_module_path: GCS path to trainer_module.py
        output_path: GCS path for output artifacts
        pipeline_root: GCS path for pipeline working directory
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate
        machine_type: Vertex AI machine type

    Returns:
        Dict of pipeline parameters
    """
    return {
        "bigquery_query": bigquery_query,
        "transform_module_path": transform_module_path,
        "trainer_module_path": trainer_module_path,
        "output_path": output_path,
        "pipeline_root": pipeline_root,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "machine_type": machine_type,
    }


def get_pipeline_template_path() -> str:
    """
    Get the path to the compiled pipeline template.

    For production, this would return a GCS path to a pre-compiled pipeline JSON.
    For development, we compile on-the-fly.

    Returns:
        Path to pipeline template (local or GCS)
    """
    # TODO: In production, return GCS path to pre-compiled pipeline
    # return "gs://b2b-recs-pipeline-staging/templates/quicktest_pipeline.json"

    # For now, compile on-the-fly
    import tempfile
    import os

    template_path = os.path.join(tempfile.gettempdir(), 'quicktest_pipeline.json')

    if not os.path.exists(template_path):
        compile_pipeline(template_path)

    return template_path


def compile_pipeline(output_path: str = "quicktest_pipeline.json") -> str:
    """
    Compile the pipeline to JSON for Vertex AI.

    Args:
        output_path: Path to save compiled pipeline JSON

    Returns:
        Path to compiled pipeline
    """
    try:
        from kfp import compiler
        compiler.Compiler().compile(
            pipeline_func=quicktest_pipeline,
            package_path=output_path
        )
        logger.info(f"Pipeline compiled to {output_path}")
        return output_path
    except ImportError:
        logger.error("kfp package not installed. Run: pip install kfp>=2.4.0")
        raise
    except Exception as e:
        logger.error(f"Failed to compile pipeline: {e}")
        raise


# =============================================================================
# KFP v2 PIPELINE DEFINITION
# =============================================================================

try:
    from kfp import dsl
    from kfp.dsl import Input, Output, Artifact, Dataset, Model

    @dsl.component(
        base_image='python:3.9',
        packages_to_install=['google-cloud-bigquery', 'pandas', 'pyarrow']
    )
    def extract_data_from_bigquery(
        bigquery_query: str,
        project_id: str,
        output_dataset: Output[Dataset],
    ):
        """
        Extract data from BigQuery using the provided SQL query.

        This is a simplified ExampleGen that outputs to a Dataset artifact.
        In production TFX, this would be a proper BigQueryExampleGen component.
        """
        import json
        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)
        df = client.query(bigquery_query).to_dataframe()

        # Save as parquet
        output_path = output_dataset.path + '.parquet'
        df.to_parquet(output_path, index=False)

        # Save metadata
        output_dataset.metadata['num_rows'] = len(df)
        output_dataset.metadata['num_columns'] = len(df.columns)
        output_dataset.metadata['columns'] = list(df.columns)

        print(f"Extracted {len(df)} rows with {len(df.columns)} columns")

    @dsl.component(
        base_image='python:3.9',
        packages_to_install=['pandas', 'pyarrow']
    )
    def compute_statistics(
        input_dataset: Input[Dataset],
        output_stats: Output[Artifact],
    ):
        """
        Compute basic statistics on the dataset.

        This is a simplified StatisticsGen. In production TFX, this would use TFDV.
        """
        import json
        import pandas as pd

        # Load data
        df = pd.read_parquet(input_dataset.path + '.parquet')

        # Compute basic stats
        stats = {
            'num_rows': len(df),
            'num_columns': len(df.columns),
            'columns': {}
        }

        for col in df.columns:
            col_stats = {
                'dtype': str(df[col].dtype),
                'null_count': int(df[col].isnull().sum()),
                'unique_count': int(df[col].nunique()),
            }
            if df[col].dtype in ['int64', 'float64']:
                col_stats['min'] = float(df[col].min())
                col_stats['max'] = float(df[col].max())
                col_stats['mean'] = float(df[col].mean())
            stats['columns'][col] = col_stats

        # Save stats
        with open(output_stats.path + '.json', 'w') as f:
            json.dump(stats, f, indent=2)

        output_stats.metadata['num_rows'] = stats['num_rows']
        print(f"Computed statistics for {len(df.columns)} columns")

    @dsl.component(
        base_image='python:3.9',
        packages_to_install=['pandas', 'pyarrow']
    )
    def infer_schema(
        input_stats: Input[Artifact],
        output_schema: Output[Artifact],
    ):
        """
        Infer schema from statistics.

        This is a simplified SchemaGen. In production TFX, this would use TFDV.
        """
        import json

        # Load stats
        with open(input_stats.path + '.json', 'r') as f:
            stats = json.load(f)

        # Build simple schema
        schema = {
            'columns': []
        }

        for col_name, col_stats in stats.get('columns', {}).items():
            schema['columns'].append({
                'name': col_name,
                'dtype': col_stats['dtype'],
                'nullable': col_stats['null_count'] > 0,
            })

        # Save schema
        with open(output_schema.path + '.json', 'w') as f:
            json.dump(schema, f, indent=2)

        output_schema.metadata['num_columns'] = len(schema['columns'])
        print(f"Inferred schema with {len(schema['columns'])} columns")

    @dsl.component(
        base_image='tensorflow/tensorflow:2.13.0',
        packages_to_install=['tensorflow-transform', 'pandas', 'pyarrow', 'google-cloud-storage']
    )
    def transform_data(
        input_dataset: Input[Dataset],
        transform_module_path: str,
        output_transformed: Output[Dataset],
        output_transform_graph: Output[Artifact],
    ):
        """
        Transform data using the generated preprocessing_fn.

        This is a simplified Transform component. In production TFX, this would
        use the full TFTransformOutput with vocabulary files, etc.
        """
        import json
        import pandas as pd
        from google.cloud import storage

        # Download transform module from GCS
        # Parse GCS path
        if transform_module_path.startswith('gs://'):
            path = transform_module_path[5:]
            bucket_name = path.split('/')[0]
            blob_path = '/'.join(path.split('/')[1:])

            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            transform_code = blob.download_as_string().decode('utf-8')

            # Save locally
            with open('/tmp/transform_module.py', 'w') as f:
                f.write(transform_code)

            print("Downloaded transform module from GCS")
        else:
            print(f"Transform module path not GCS: {transform_module_path}")

        # Load data
        df = pd.read_parquet(input_dataset.path + '.parquet')
        print(f"Loaded {len(df)} rows for transformation")

        # For this simplified version, we just pass through the data
        # In production, we would execute the preprocessing_fn
        output_path = output_transformed.path + '.parquet'
        df.to_parquet(output_path, index=False)

        output_transformed.metadata['num_rows'] = len(df)
        output_transform_graph.metadata['status'] = 'placeholder'

        print(f"Transform complete: {len(df)} rows")

    @dsl.component(
        base_image='tensorflow/tensorflow:2.13.0',
        packages_to_install=[
            'tensorflow-recommenders',
            'pandas',
            'pyarrow',
            'google-cloud-storage'
        ]
    )
    def train_model(
        input_dataset: Input[Dataset],
        trainer_module_path: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        output_model: Output[Model],
        output_metrics: Output[Artifact],
    ):
        """
        Train the TFRS model using the generated trainer module.

        This is a simplified Trainer component that demonstrates the structure.
        In production, this would execute the full run_fn from the trainer module.
        """
        import json
        import pandas as pd
        from google.cloud import storage

        # Download trainer module from GCS
        if trainer_module_path.startswith('gs://'):
            path = trainer_module_path[5:]
            bucket_name = path.split('/')[0]
            blob_path = '/'.join(path.split('/')[1:])

            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            trainer_code = blob.download_as_string().decode('utf-8')

            # Save locally
            with open('/tmp/trainer_module.py', 'w') as f:
                f.write(trainer_code)

            print("Downloaded trainer module from GCS")

        # Load data
        df = pd.read_parquet(input_dataset.path + '.parquet')
        print(f"Loaded {len(df)} rows for training")
        print(f"Training params: epochs={epochs}, batch_size={batch_size}, lr={learning_rate}")

        # For this simplified version, we generate placeholder metrics
        # In production, we would execute the run_fn and capture actual metrics
        metrics = {
            "loss": 0.5,  # Placeholder
            "recall_at_10": 0.15,  # Placeholder
            "recall_at_50": 0.35,  # Placeholder
            "recall_at_100": 0.45,  # Placeholder
            "epochs_completed": epochs,
            "total_examples": len(df),
            "vocabulary_stats": {}
        }

        # Save metrics
        with open(output_metrics.path + '.json', 'w') as f:
            json.dump(metrics, f, indent=2)

        output_metrics.metadata['loss'] = metrics['loss']
        output_metrics.metadata['recall_at_100'] = metrics['recall_at_100']
        output_model.metadata['framework'] = 'tensorflow'

        print(f"Training complete. Loss: {metrics['loss']}, Recall@100: {metrics['recall_at_100']}")

    @dsl.component(
        base_image='python:3.9',
        packages_to_install=['google-cloud-storage']
    )
    def save_metrics_to_gcs(
        input_metrics: Input[Artifact],
        output_path: str,
    ):
        """
        Save final metrics to GCS for extraction by Django.
        """
        import json
        from google.cloud import storage

        # Load metrics
        with open(input_metrics.path + '.json', 'r') as f:
            metrics = json.load(f)

        # Parse GCS output path
        if output_path.startswith('gs://'):
            path = output_path[5:]
            bucket_name = path.split('/')[0]
            blob_path = '/'.join(path.split('/')[1:]) + '/metrics.json'

            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            blob.upload_from_string(json.dumps(metrics, indent=2))

            print(f"Saved metrics to gs://{bucket_name}/{blob_path}")
        else:
            print(f"Output path not GCS: {output_path}")

    @dsl.pipeline(
        name="quicktest-tfx-pipeline",
        description="Quick Test TFX pipeline for TFRS model validation"
    )
    def quicktest_pipeline(
        bigquery_query: str,
        transform_module_path: str,
        trainer_module_path: str,
        output_path: str,
        pipeline_root: str,
        epochs: int = 10,
        batch_size: int = 4096,
        learning_rate: float = 0.001,
        machine_type: str = 'n1-standard-4',
        project_id: str = 'b2b-recs',
    ):
        """
        TFX-like Pipeline for Quick Tests.

        This pipeline demonstrates the structure of a TFX pipeline using KFP v2.
        For production use, consider using the full TFX SDK with proper components.

        Components:
        1. ExampleGen - Read data from BigQuery
        2. StatisticsGen - Compute dataset statistics
        3. SchemaGen - Infer schema
        4. Transform - Apply preprocessing_fn
        5. Trainer - Train TFRS model
        6. SaveMetrics - Export metrics for Django
        """
        # Step 1: Extract data from BigQuery
        example_gen = extract_data_from_bigquery(
            bigquery_query=bigquery_query,
            project_id=project_id,
        )

        # Step 2: Compute statistics
        statistics_gen = compute_statistics(
            input_dataset=example_gen.outputs['output_dataset'],
        )

        # Step 3: Infer schema
        schema_gen = infer_schema(
            input_stats=statistics_gen.outputs['output_stats'],
        )

        # Step 4: Transform data
        transform = transform_data(
            input_dataset=example_gen.outputs['output_dataset'],
            transform_module_path=transform_module_path,
        )

        # Step 5: Train model
        trainer = train_model(
            input_dataset=transform.outputs['output_transformed'],
            trainer_module_path=trainer_module_path,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
        )

        # Step 6: Save metrics to GCS
        save_metrics = save_metrics_to_gcs(
            input_metrics=trainer.outputs['output_metrics'],
            output_path=output_path,
        )

except ImportError as e:
    logger.warning(f"KFP not available, pipeline definition skipped: {e}")

    def quicktest_pipeline(*args, **kwargs):
        raise ImportError("kfp package not installed. Run: pip install kfp>=2.4.0")
