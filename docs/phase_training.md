# Phase: Training Domain

## Document Purpose
This document provides detailed specifications for implementing the **Training** domain in the ML Platform. The Training domain executes full TFX pipelines for production model training.

**Last Updated**: 2025-12-01

---

## Overview

### Purpose
The Training domain allows users to:
1. Select a Dataset + Feature Config combination
2. Configure training hyperparameters (epochs, batch size, etc.)
3. Execute a full TFX pipeline via Vertex AI Pipelines
4. Monitor pipeline progress in real-time
5. Track artifacts in ML Metadata

### Key Principle
**Training is the production execution of a validated configuration.** Users should run Quick Tests in Modeling first, then promote the best config to Full Training.

### Output
- Trained TFRS model (SavedModel with embedded Transform)
- TFX artifacts tracked in ML Metadata
- Metrics logged to MLflow
- Model ready for deployment

---

## User Interface

### Training Runs List View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Training Runs                                              [+ New Training] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ 🔄 Training Run #47                                           Running │  │
│ │ Dataset: Q4 2024 Training Data | Config: config-042 (Large embeddings) │  │
│ │ Started: 45 min ago | Stage: Trainer (epoch 8/20)                      │  │
│ │ [View Progress]                                                        │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ ✅ Training Run #46                                        Completed   │  │
│ │ Dataset: Q4 2024 Training Data | Config: config-038                    │  │
│ │ Duration: 3h 42m | Cost: $38.50 | Recall@100: 46.8%                   │  │
│ │ [View Results] [Deploy] [Compare]                                      │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ ✅ Training Run #45                                        Deployed ●  │  │
│ │ Dataset: Q3 2024 Training Data | Config: config-032                    │  │
│ │ Duration: 2h 58m | Cost: $32.10 | Recall@100: 45.2%                   │  │
│ │ [View Results] [Rollback]                                              │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ ❌ Training Run #44                                           Failed   │  │
│ │ Dataset: Q4 2024 Training Data | Config: config-040                    │  │
│ │ Failed at: Transform | Error: OOM during vocabulary generation         │  │
│ │ [View Logs]                                                            │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### New Training Dialog

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Start Training Run                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ SELECT CONFIGURATION                                                         │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Dataset *                                                                    │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Q4 2024 Training Data                                              [▼] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ ℹ️ 2.45M rows | 98K users | 36K products | Last 6 months                    │
│                                                                              │
│ Feature Config *                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ★ config-042: Large embeddings (Best: 47.3% R@100)                 [▼] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ ℹ️ user_id: 64d | product_id: 64d | crosses: cat×subcat, user×city          │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ TRAINING HYPERPARAMETERS                                                     │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Epochs:             [20 ▼]        (recommended: 15-30)                       │
│ Batch Size:         [8192 ▼]      (recommended: 4096-16384)                  │
│ Learning Rate:      [0.1 ▼]       (Adagrad default)                          │
│ Early Stopping:     ☑ Enable      Patience: [5 ▼] epochs                     │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ COMPUTE RESOURCES                                                            │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ GPU Configuration:  [4x T4 ▼]     (options: 1x T4, 4x T4, 4x V100, 4x L4)    │
│ Use Preemptible:    ☑ Yes         (70% cost reduction, may be interrupted)  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ ESTIMATES                                                                    │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Estimated duration:  2-4 hours                                               │
│ Estimated cost:      $25-45 (with preemptible GPUs)                          │
│                                                                              │
│                                                                              │
│                                            [Cancel]  [▶ Start Training]     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Training Progress View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Training Run #47                                                   Running  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Dataset: Q4 2024 Training Data                                               │
│ Feature Config: config-042 (Large embeddings)                                │
│ Started: Nov 28, 2024 14:30 | Elapsed: 1h 23m                               │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ PIPELINE PROGRESS                                                            │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────┐    │
│ │ ████████████████████████████████████████░░░░░░░░░░░░░░░░░░░░ 65%    │    │
│ └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│ ✅ ExampleGen         Completed     12 min     2,450,123 examples           │
│ ✅ StatisticsGen      Completed      8 min     Stats generated              │
│ ✅ SchemaGen          Completed     30 sec     Schema inferred              │
│ ✅ Transform          Completed     25 min     Vocabularies created         │
│ 🔄 Trainer            Running       38 min     Epoch 8/20 (Loss: 0.31)      │
│ ⏳ Evaluator          Pending       -          -                             │
│ ⏳ Pusher             Pending       -          -                             │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ TRAINING METRICS (Live)                                                      │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Epoch    Loss      Recall@10   Recall@50   Recall@100                       │
│ ─────────────────────────────────────────────────────────                   │
│ 1        0.85      5.2%        12.1%       18.4%                            │
│ 2        0.62      8.7%        20.3%       29.5%                            │
│ 3        0.48      12.1%       28.5%       38.2%                            │
│ 4        0.41      14.8%       33.2%       42.1%                            │
│ 5        0.37      16.2%       35.8%       44.3%                            │
│ 6        0.34      17.1%       37.2%       45.6%                            │
│ 7        0.32      17.6%       38.1%       46.4%                            │
│ 8        0.31      17.9%       38.6%       46.8%      ← Current             │
│                                                                              │
│ [Training Curve Chart - Loss and Recall over epochs]                         │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ RESOURCE UTILIZATION                                                         │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ GPU Memory: 14.2 / 16.0 GB (89%)                                            │
│ GPU Utilization: 94%                                                         │
│ Current Cost: $18.42                                                         │
│                                                                              │
│                                                              [Cancel Run]    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Training Results View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Training Run #46 - Results                                       Completed  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ SUMMARY                                                                      │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Status:       ✅ Completed Successfully                                      │
│ Duration:     3h 42m                                                         │
│ Total Cost:   $38.50                                                         │
│ Early Stop:   Yes, at epoch 18 (patience: 5)                                │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ FINAL METRICS                                                                │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────┬────────────┬────────────────────────────────────────┐    │
│ │ Metric         │ Value      │ vs Quick Test                          │    │
│ ├────────────────┼────────────┼────────────────────────────────────────┤    │
│ │ Loss           │ 0.28       │ ↓ 0.10 (was 0.38 in quick test)        │    │
│ │ Recall@10      │ 18.9%      │ ↑ 0.7%                                 │    │
│ │ Recall@50      │ 39.2%      │ ↑ 0.7%                                 │    │
│ │ Recall@100     │ 46.8%      │ ↓ 0.5% (quick test was optimistic)     │    │
│ └────────────────┴────────────┴────────────────────────────────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ ARTIFACTS                                                                    │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Model:         gs://b2b-recs-ml/models/run-46/saved_model/                  │
│ Query Model:   gs://b2b-recs-ml/models/run-46/query_model/                  │
│ Candidate Model: gs://b2b-recs-ml/models/run-46/candidate_model/            │
│ Transform:     gs://b2b-recs-ml/artifacts/run-46/transform/                 │
│ Vocabularies:  gs://b2b-recs-ml/artifacts/run-46/vocabularies/              │
│                                                                              │
│ ML Metadata:   [View in MLMD Console]                                       │
│ MLflow:        [View Experiment]                                            │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ CONFIGURATION SNAPSHOT                                                       │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Dataset:       Q4 2024 Training Data (version 3)                            │
│ Feature Config: config-042 (Large embeddings)                               │
│ Epochs:        18 (early stopped)                                           │
│ Batch Size:    8192                                                         │
│ Learning Rate: 0.1 (Adagrad)                                                │
│ GPU:           4x T4 (preemptible)                                          │
│                                                                              │
│ [View Full Config JSON]                                                      │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ [View in MLflow]  [Compare with Other Runs]  [▶ Deploy This Model]          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### Django Models

```python
# ml_platform/models.py

class TrainingRun(models.Model):
    """
    Tracks a full training pipeline execution.
    """
    # Basic info
    ml_model = models.ForeignKey('MLModel', on_delete=models.CASCADE, related_name='training_runs')
    run_number = models.IntegerField()  # Auto-incremented per model

    # Configuration links
    dataset = models.ForeignKey('Dataset', on_delete=models.PROTECT)
    dataset_version = models.ForeignKey('DatasetVersion', on_delete=models.PROTECT, null=True)
    feature_config = models.ForeignKey('FeatureConfig', on_delete=models.PROTECT)

    # Training hyperparameters (JSON)
    hyperparameters = models.JSONField(default=dict)
    # Example:
    # {
    #   "epochs": 20,
    #   "batch_size": 8192,
    #   "learning_rate": 0.1,
    #   "optimizer": "adagrad",
    #   "early_stopping": {"enabled": true, "patience": 5}
    # }

    # Compute configuration (JSON)
    compute_config = models.JSONField(default=dict)
    # Example:
    # {
    #   "gpu_type": "T4",
    #   "gpu_count": 4,
    #   "preemptible": true,
    #   "machine_type": "n1-standard-32"
    # }

    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    current_stage = models.CharField(max_length=100, blank=True)
    current_epoch = models.IntegerField(null=True, blank=True)
    total_epochs = models.IntegerField(null=True, blank=True)

    # Pipeline tracking
    vertex_pipeline_id = models.CharField(max_length=255, blank=True)
    vertex_pipeline_url = models.URLField(blank=True)

    # Results
    final_loss = models.FloatField(null=True, blank=True)
    recall_at_10 = models.FloatField(null=True, blank=True)
    recall_at_50 = models.FloatField(null=True, blank=True)
    recall_at_100 = models.FloatField(null=True, blank=True)
    early_stopped_at_epoch = models.IntegerField(null=True, blank=True)

    # Artifacts (JSON)
    artifacts = models.JSONField(default=dict)
    # Example:
    # {
    #   "saved_model": "gs://bucket/models/run-46/saved_model/",
    #   "query_model": "gs://bucket/models/run-46/query_model/",
    #   "candidate_model": "gs://bucket/models/run-46/candidate_model/",
    #   "transform": "gs://bucket/artifacts/run-46/transform/",
    #   "vocabularies": "gs://bucket/artifacts/run-46/vocabularies/"
    # }

    # Cost tracking
    cost_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True)
    error_stage = models.CharField(max_length=100, blank=True)

    # ML Metadata & MLflow
    mlmd_context_id = models.CharField(max_length=255, blank=True)
    mlflow_run_id = models.CharField(max_length=255, blank=True)

    # Deployment status
    is_deployed = models.BooleanField(default=False)
    deployed_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['ml_model', 'run_number']

    def save(self, *args, **kwargs):
        if not self.run_number:
            # Auto-increment run number for this model
            last_run = TrainingRun.objects.filter(ml_model=self.ml_model).order_by('-run_number').first()
            self.run_number = (last_run.run_number + 1) if last_run else 1
        super().save(*args, **kwargs)


class TrainingMetricsHistory(models.Model):
    """
    Stores per-epoch metrics for training visualization.
    """
    training_run = models.ForeignKey(TrainingRun, on_delete=models.CASCADE, related_name='metrics_history')
    epoch = models.IntegerField()
    loss = models.FloatField()
    recall_at_10 = models.FloatField(null=True, blank=True)
    recall_at_50 = models.FloatField(null=True, blank=True)
    recall_at_100 = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['epoch']
        unique_together = ['training_run', 'epoch']
```

---

## API Endpoints

### Training Run CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{model_id}/training-runs/` | List training runs |
| POST | `/api/models/{model_id}/training-runs/` | Start new training run |
| GET | `/api/training-runs/{run_id}/` | Get training run details |
| POST | `/api/training-runs/{run_id}/cancel/` | Cancel running training |
| GET | `/api/training-runs/{run_id}/logs/` | Get training logs |
| GET | `/api/training-runs/{run_id}/metrics/` | Get metrics history |

### Webhooks (for pipeline callbacks)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/training-runs/{run_id}/webhook/stage-complete/` | Pipeline stage completed |
| POST | `/api/training-runs/{run_id}/webhook/epoch-complete/` | Training epoch completed |
| POST | `/api/training-runs/{run_id}/webhook/failed/` | Pipeline failed |
| POST | `/api/training-runs/{run_id}/webhook/completed/` | Pipeline completed |

---

## TFX Pipeline

### Full Training Pipeline Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FULL TRAINING TFX PIPELINE                                │
│                                                                              │
│   BigQuery        ExampleGen        StatisticsGen        SchemaGen          │
│   (100% data)     (TFRecords)       (full stats)         (schema)           │
│       │               │                  │                  │               │
│       └───────────────┴──────────────────┴──────────────────┘               │
│                                  │                                           │
│                                  ↓                                           │
│                             Transform                                        │
│                         (full vocabularies)                                  │
│                                  │                                           │
│                                  ↓                                           │
│                              Trainer                                         │
│                      (GPU, multi-epoch, early stopping)                      │
│                                  │                                           │
│                                  ↓                                           │
│                             Evaluator                                        │
│                        (compute final metrics)                               │
│                                  │                                           │
│                                  ↓                                           │
│                              Pusher                                          │
│                      (push to model registry)                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ↓
                         ┌─────────────────┐
                         │   ML Metadata   │
                         │   (artifact     │
                         │    tracking)    │
                         └─────────────────┘
```

### Vertex AI Pipelines Integration

```python
# ml_platform/training/services.py

from google.cloud import aiplatform
from tfx.orchestration import pipeline as tfx_pipeline
from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner

class TrainingPipelineService:
    """
    Manages TFX pipeline execution via Vertex AI Pipelines.
    """

    def __init__(self, project_id: str, region: str):
        self.project_id = project_id
        self.region = region
        aiplatform.init(project=project_id, location=region)

    def create_pipeline(
        self,
        training_run: 'TrainingRun',
        dataset: 'Dataset',
        feature_config: 'FeatureConfig'
    ) -> tfx_pipeline.Pipeline:
        """
        Create TFX Pipeline object from training configuration.
        """
        pass

    def compile_pipeline(self, pipeline: tfx_pipeline.Pipeline) -> str:
        """
        Compile pipeline to Kubeflow Pipelines IR.
        Returns path to compiled pipeline JSON.
        """
        pass

    def submit_pipeline(
        self,
        compiled_pipeline_path: str,
        training_run: 'TrainingRun'
    ) -> str:
        """
        Submit pipeline to Vertex AI Pipelines.
        Returns pipeline run ID.
        """
        pass

    def get_pipeline_status(self, pipeline_run_id: str) -> dict:
        """
        Get current status of a pipeline run.
        """
        pass

    def cancel_pipeline(self, pipeline_run_id: str) -> bool:
        """
        Cancel a running pipeline.
        """
        pass
```

### TFX Pipeline Definition

```python
# training/tfx_pipeline.py

from tfx import v1 as tfx
from tfx.components import (
    BigQueryExampleGen,
    StatisticsGen,
    SchemaGen,
    Transform,
    Trainer,
    Evaluator,
    Pusher,
)
from tfx.proto import trainer_pb2
from tfx.extensions.google_cloud_ai_platform.trainer import executor as ai_platform_trainer_executor

def create_tfrs_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    bigquery_query: str,
    preprocessing_fn_path: str,
    trainer_module_path: str,
    hyperparameters: dict,
    compute_config: dict,
    serving_model_dir: str,
) -> tfx.dsl.Pipeline:
    """
    Create a TFX pipeline for TFRS model training.
    """

    # ExampleGen - Extract data from BigQuery
    example_gen = BigQueryExampleGen(
        query=bigquery_query,
        output_config=tfx.proto.Output(
            split_config=tfx.proto.SplitConfig(
                splits=[
                    tfx.proto.SplitConfig.Split(name='train', hash_buckets=10),
                    tfx.proto.SplitConfig.Split(name='eval', hash_buckets=2),
                ]
            )
        )
    )

    # StatisticsGen - Generate statistics
    statistics_gen = StatisticsGen(
        examples=example_gen.outputs['examples']
    )

    # SchemaGen - Infer schema
    schema_gen = SchemaGen(
        statistics=statistics_gen.outputs['statistics']
    )

    # Transform - Feature preprocessing
    transform = Transform(
        examples=example_gen.outputs['examples'],
        schema=schema_gen.outputs['schema'],
        preprocessing_fn=preprocessing_fn_path,
    )

    # Trainer - Train TFRS model
    trainer = Trainer(
        module_file=trainer_module_path,
        examples=transform.outputs['transformed_examples'],
        transform_graph=transform.outputs['transform_graph'],
        schema=schema_gen.outputs['schema'],
        train_args=trainer_pb2.TrainArgs(num_steps=hyperparameters['train_steps']),
        eval_args=trainer_pb2.EvalArgs(num_steps=hyperparameters['eval_steps']),
        custom_config={
            'epochs': hyperparameters['epochs'],
            'batch_size': hyperparameters['batch_size'],
            'learning_rate': hyperparameters['learning_rate'],
            'early_stopping_patience': hyperparameters.get('early_stopping_patience', 5),
        },
        custom_executor_spec=tfx.dsl.executor_spec.ExecutorClassSpec(
            ai_platform_trainer_executor.GenericExecutor
        ),
    )

    # Evaluator - Evaluate model
    evaluator = Evaluator(
        examples=example_gen.outputs['examples'],
        model=trainer.outputs['model'],
    )

    # Pusher - Push model to serving
    pusher = Pusher(
        model=trainer.outputs['model'],
        push_destination=tfx.proto.PushDestination(
            filesystem=tfx.proto.PushDestination.Filesystem(
                base_directory=serving_model_dir
            )
        )
    )

    return tfx.dsl.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=[
            example_gen,
            statistics_gen,
            schema_gen,
            transform,
            trainer,
            evaluator,
            pusher,
        ],
    )
```

### TFRS Trainer Module

```python
# training/tfrs_trainer.py

import tensorflow as tf
import tensorflow_recommenders as tfrs
from tfx.components.trainer.fn_args_utils import FnArgs

def run_fn(fn_args: FnArgs):
    """
    TFX Trainer module entry point for TFRS model.
    """
    # Load hyperparameters from custom_config
    hyperparams = fn_args.custom_config

    # Create tf.data datasets from TFRecords
    train_dataset = _create_dataset(
        fn_args.train_files,
        fn_args.data_accessor,
        fn_args.schema,
        batch_size=hyperparams['batch_size'],
    )

    eval_dataset = _create_dataset(
        fn_args.eval_files,
        fn_args.data_accessor,
        fn_args.schema,
        batch_size=hyperparams['batch_size'],
    )

    # Load vocabularies from Transform output
    tf_transform_output = tft.TFTransformOutput(fn_args.transform_graph_path)

    # Build TFRS model
    model = TFRSModel(
        tf_transform_output=tf_transform_output,
        hyperparams=hyperparams,
    )

    # Compile
    model.compile(optimizer=tf.keras.optimizers.Adagrad(hyperparams['learning_rate']))

    # Callbacks
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=hyperparams['early_stopping_patience'],
            restore_best_weights=True,
        ),
        # Custom callback to log metrics to Django
        TrainingMetricsCallback(fn_args.custom_config.get('webhook_url')),
    ]

    # Train
    model.fit(
        train_dataset,
        validation_data=eval_dataset,
        epochs=hyperparams['epochs'],
        callbacks=callbacks,
    )

    # Save model
    model.save(fn_args.serving_model_dir)


class TFRSModel(tfrs.Model):
    """
    Two-tower retrieval model for recommendations.
    """

    def __init__(self, tf_transform_output, hyperparams):
        super().__init__()
        self.query_model = self._build_query_tower(tf_transform_output, hyperparams)
        self.candidate_model = self._build_candidate_tower(tf_transform_output, hyperparams)
        self.task = tfrs.tasks.Retrieval()

    def _build_query_tower(self, tf_transform_output, hyperparams):
        """Build the query (user) tower."""
        # Implementation based on FeatureConfig
        pass

    def _build_candidate_tower(self, tf_transform_output, hyperparams):
        """Build the candidate (product) tower."""
        # Implementation based on FeatureConfig
        pass

    def compute_loss(self, features, training=False):
        query_embeddings = self.query_model(features)
        candidate_embeddings = self.candidate_model(features)
        return self.task(query_embeddings, candidate_embeddings)
```

---

## Webhook Integration

Django receives status updates from the running pipeline:

```python
# ml_platform/training/webhooks.py

@csrf_exempt
@require_POST
def stage_complete_webhook(request, run_id):
    """
    Called when a pipeline stage completes.
    """
    data = json.loads(request.body)
    training_run = get_object_or_404(TrainingRun, id=run_id)

    training_run.current_stage = data['stage']
    training_run.save()

    # Notify frontend via WebSocket or polling
    return JsonResponse({'status': 'ok'})


@csrf_exempt
@require_POST
def epoch_complete_webhook(request, run_id):
    """
    Called after each training epoch.
    """
    data = json.loads(request.body)
    training_run = get_object_or_404(TrainingRun, id=run_id)

    # Update current epoch
    training_run.current_epoch = data['epoch']
    training_run.save()

    # Save metrics history
    TrainingMetricsHistory.objects.create(
        training_run=training_run,
        epoch=data['epoch'],
        loss=data['loss'],
        recall_at_10=data.get('recall_at_10'),
        recall_at_50=data.get('recall_at_50'),
        recall_at_100=data.get('recall_at_100'),
    )

    return JsonResponse({'status': 'ok'})
```

---

## Implementation Checklist

### Phase 1: Basic Training Run
- [ ] Create Django models (TrainingRun, TrainingMetricsHistory)
- [ ] Create training sub-app structure
- [ ] Implement basic API endpoints
- [ ] Create training runs list page
- [ ] Create new training dialog

### Phase 2: TFX Pipeline Integration
- [ ] Create TFX pipeline definition
- [ ] Implement TFRS trainer module
- [ ] Compile pipeline to Kubeflow IR
- [ ] Submit to Vertex AI Pipelines

### Phase 3: Progress Tracking
- [ ] Implement webhook endpoints
- [ ] Create training progress view
- [ ] Real-time metrics display
- [ ] Training curve visualization

### Phase 4: Results & Artifacts
- [ ] Display final metrics
- [ ] Link to artifacts in GCS
- [ ] ML Metadata integration
- [ ] MLflow logging

---

## Dependencies on Other Domains

### Depends On
- **Datasets Domain**: Provides Dataset definition for ExampleGen
- **Modeling Domain**: Provides Feature Config for Transform

### Depended On By
- **Experiments Domain**: Training results feed into comparison
- **Deployment Domain**: Completed runs can be deployed

---

## Related Documentation

- [Implementation Overview](../implementation.md)
- [Datasets Phase](phase_datasets.md)
- [Modeling Phase](phase_modeling.md)
- [Experiments Phase](phase_experiments.md)
- [Deployment Phase](phase_deployment.md)
