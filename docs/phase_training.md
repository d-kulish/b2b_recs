# Phase: Training Domain

## Document Purpose
This document provides detailed specifications for implementing the **Training** domain in the ML Platform. The Training domain executes full TFX pipelines for production model training.

**Last Updated**: 2026-01-15

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

### Best Experiments Container (2026-01-15)

The Training page now features a "Best Experiments" container that displays top-performing experiments across all model types (Retrieval, Ranking, Hybrid). This mirrors functionality from the Experiments page.

#### Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🏆 Best Experiments                                                          │
│    Top performing experiment configurations                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 🔍 RETRIEVAL │ Exps: 15 │ R@5: 0.234 │ R@10: 0.412 │ R@50: 0.687 │ R@100: 0.823 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 📊 RANKING   │ Exps: 8  │ RMSE: 0.4521 │ Test RMSE: 0.4789 │ MAE: 0.3124 │ Test MAE: 0.3456 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 📚 HYBRID    │ Exps: 5  │ R@50: 0.654 │ R@100: 0.801 │ RMSE: 0.4234 │ Test RMSE: 0.4567 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ TOP CONFIGURATIONS (Scrollable - 5 visible, 5 more with scroll)             │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ │ #  │ Experiment │ Dataset │ Feature │ Model │ LR  │ Batch │ Epochs │ R@100 │ Loss │ │
│ │ 1  │ Exp #47    │ Q4 Data │ cfg-042 │ mdl-1 │ 0.1 │ 8192  │ 20     │ 0.823 │ 0.31 │ │
│ │ 2  │ Exp #45    │ Q4 Data │ cfg-038 │ mdl-2 │ 0.05│ 4096  │ 15     │ 0.801 │ 0.35 │ │
│ │ ... │           │         │         │       │     │       │        │       │      │ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Features

1. **Model Type KPI Rows**: Three horizontal rows stacked vertically
   - Each row shows icon + model type name + 5 KPI boxes
   - Clicking a row selects it and updates the table below
   - Default selection: Retrieval

2. **Top Configurations Table**
   - Shows best 10 experiments for the selected model type
   - 5 rows visible, remaining 5 accessible via scroll
   - Sticky header for easy reference while scrolling
   - Click any row to open the View Modal

3. **View Modal with Full Feature Parity**
   - Identical to the Experiments page view modal
   - Three tabs: Overview, Pipeline, Training

#### View Modal - Overview Tab

The Overview tab displays comprehensive experiment details:

1. **Results Summary**: Final metrics (R@K for retrieval, RMSE/MAE for ranking)

2. **Dataset Section**: Tables and statistics from the dataset

3. **Features Config Section**: Full tensor visualization
   - Target Column card (for ranking models) with transforms
   - Buyer Tensor panel with color-coded dimension breakdown
   - Product Tensor panel with feature list and dimensions
   - Visual tensor bars showing proportional feature sizes

4. **Model Config Section**: Tower architecture visualization
   - Model type badge (Retrieval/Ranking/Hybrid)
   - Buyer Tower layers with badges (DENSE, DROPOUT, BATCHNORM)
   - Product Tower layers
   - Rating Head (for ranking/multitask models)
   - Parameter counts for each tower

5. **Sampling Section**: Data sampling configuration
   - Sample percentage
   - Split strategy (Random/Time Holdout/Strict Temporal)
   - Date column (for temporal strategies)
   - Holdout days (for time_holdout)

6. **Training Parameters Section**
   - Optimizer (populated from model config)
   - Epochs, Batch Size, Learning Rate
   - Hardware specifications (vCPUs, memory)

#### JavaScript Functions

The following functions power the view modal (copied from Experiments page):

```javascript
// Feature Config Visualization
loadFeaturesConfigForExp(featureConfigId)    // API call to fetch config
renderFeaturesConfigForExp(config)           // Render tensor breakdown
calculateExpTensorBreakdown(features, crosses)
getExpFeatureDimension(feature)
getExpDataTypeFromBqType(bqType)
getExpCrossFeatureNames(cross)
renderExpTensorBar(model, total, breakdown, maxTotal)

// Model Config Visualization
loadModelConfigForExp(modelConfigId)         // API call to fetch config
renderModelConfigForExp(mc)                  // Render tower architecture
renderExpTowerLayers(layers)                 // Render layer items
calculateExpTowerParams(layers, inputDim)   // Calculate parameters

// Parameters
renderSamplingChips(exp)                     // Full sampling display
renderTrainingParamsChips(exp)               // Full training params
```

#### CSS Classes

Key CSS classes for the view modal visualization:

- `.exp-view-tensor-panel`, `.exp-view-tensor-bar` - Tensor visualization
- `.exp-view-tower-stack`, `.exp-view-layer-item` - Tower architecture
- `.exp-view-layer-badge.dense`, `.dropout`, `.batch_norm` - Layer badges
- `.target-column-view-card` - Target column for ranking models
- `.exp-view-param-chip` - Parameter display chips

---

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

## GPU Support for TFX Training Containers (2026-01-11)

### Problem Statement

When scaling from experiments (small samples, CPU) to production training (full datasets, GPU), there is a critical compatibility issue:

| Component | Current Setup | Issue |
|-----------|---------------|-------|
| Base Image | `gcr.io/tfx-oss-public/tfx:1.15.0` | **No CUDA/GPU drivers included** |
| TensorFlow | 2.15.x (locked by TFX) | Requires CUDA 12.2 + cuDNN 8.9 |
| ScaNN | 1.3.0 | Compiled against TF 2.15 specifically |

**The standard TFX public Docker image does NOT include NVIDIA/CUDA support.** This is a known limitation confirmed by the TensorFlow community.

### Background: Previous Airflow-Based Solution

Before adopting TFX pipelines, production training used Airflow with custom GPU containers:

```dockerfile
# past/recs/trainer/Dockerfile
FROM tensorflow/tensorflow:2.16.2-gpu

RUN apt-get update && apt-get install -y libnccl2 libnccl-dev
ENV NCCL_DEBUG=INFO
```

This worked because:
1. `tensorflow/tensorflow:*-gpu` images include CUDA and cuDNN pre-installed
2. No TFX dependency constraints
3. No ScaNN version compatibility requirements (wasn't used)

The Airflow DAG (`past/dags/metro_recommender_production_v2.py`) handled GPU availability gracefully:
```
T4 (first choice) → V100 → L4 → 2x T4 (fallback)
```

### Research Findings

#### TensorFlow 2.15 CUDA Requirements

| Requirement | Version |
|-------------|---------|
| CUDA | 12.2 |
| cuDNN | 8.9.x |
| Python | 3.9-3.11 |
| NCCL | 2.16.5 (for multi-GPU) |

Source: [TensorFlow 2.15 Release Notes](https://blog.tensorflow.org/2023/11/whats-new-in-tensorflow-2-15.html)

#### TFX GPU Support

From [TensorFlow community discussion](https://groups.google.com/a/tensorflow.org/g/tfx/c/5oRt1EzCa4E):
> "TFX docker image does not come with NVIDIA/CUDA support which you have to set up by yourself to create a custom docker image."

#### Vertex AI GPU Configuration

When using GPUs with Vertex AI Training, you must:
1. Use a container with CUDA pre-installed
2. Specify `accelerator_type` and `accelerator_count` in the job spec
3. Set `NCCL_DEBUG=INFO` for troubleshooting multi-GPU issues

Source: [Vertex AI Training GPU Configuration](https://cloud.google.com/vertex-ai/docs/training/configure-compute)

### Solutions

#### Option 1: Custom TFX GPU Container (Recommended)

Build a custom Dockerfile that adds TFX to a GPU-enabled TensorFlow base:

```dockerfile
# cloudbuild/tfx-trainer-gpu/Dockerfile
FROM tensorflow/tensorflow:2.15.0-gpu

# Install system dependencies for multi-GPU
RUN apt-get update && apt-get install -y \
    libnccl2 \
    libnccl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set NCCL environment for GPU communication
ENV NCCL_DEBUG=INFO

# Install TFX and dependencies
RUN pip install --no-cache-dir \
    tfx==1.15.0 \
    tensorflow-recommenders>=0.7.3

# Add ScaNN (compiled for TF 2.15)
RUN pip install --no-cache-dir --no-deps scann==1.3.0

# Verify GPU support
RUN python -c "import tensorflow as tf; print(f'TF: {tf.__version__}'); print(f'GPUs: {tf.config.list_physical_devices(\"GPU\")}')"
RUN python -c "import tensorflow_recommenders as tfrs; print(f'TFRS: {tfrs.__version__}')"
RUN python -c "from tensorflow_recommenders.layers.factorized_top_k import ScaNN; print('ScaNN: available')"
```

**Pros:**
- Uses official TensorFlow GPU image with tested CUDA configuration
- Maintains TFX 1.15.0 / TF 2.15.x compatibility
- ScaNN 1.3.0 works (compiled for TF 2.15)

**Cons:**
- May need to resolve minor dependency conflicts
- Larger image size (~8-10 GB)

#### Option 2: Google Deep Learning Containers

Use Google's pre-configured containers with GPU support:

```dockerfile
FROM gcr.io/deeplearning-platform-release/tf2-gpu.2-15.py310

# Add TFX and TFRS
RUN pip install --no-cache-dir \
    tfx==1.15.0 \
    tensorflow-recommenders>=0.7.3

# Add ScaNN
RUN pip install --no-cache-dir --no-deps scann==1.3.0
```

**Pros:**
- Google-maintained, optimized for GCP
- Includes CUDA, cuDNN, NCCL pre-configured
- Regular security updates

**Cons:**
- Larger base image
- Less control over exact versions

Source: [Google Deep Learning Containers](https://cloud.google.com/deep-learning-containers/docs/choosing-container)

#### Option 3: NVIDIA CUDA Base Image

Start from NVIDIA's official CUDA image:

```dockerfile
FROM nvidia/cuda:12.2.0-cudnn8-runtime-ubuntu22.04

# Install Python
RUN apt-get update && apt-get install -y python3.10 python3-pip

# Install TensorFlow with CUDA support
RUN pip install tensorflow[and-cuda]==2.15.0

# Install TFX and TFRS
RUN pip install tfx==1.15.0 tensorflow-recommenders>=0.7.3

# Add ScaNN
RUN pip install --no-deps scann==1.3.0
```

**Pros:**
- Minimal base, smaller image size
- Full control over dependencies

**Cons:**
- More manual configuration required
- Need to ensure all CUDA libraries are compatible

### Pipeline Configuration for GPU

When submitting training jobs to Vertex AI, configure GPU resources:

```python
vertex_job_spec = {
    'worker_pool_specs': [{
        'machine_spec': {
            'machine_type': 'n1-standard-8',
            'accelerator_type': 'NVIDIA_TESLA_T4',
            'accelerator_count': 4,
        },
        'replica_count': 1,
        'container_spec': {
            'image_uri': 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer-gpu:latest',
        },
    }],
}
```

### GPU Availability Strategy

Follow the fallback pattern from the previous Airflow implementation:

| Priority | GPU Type | Machine Type | Use Case |
|----------|----------|--------------|----------|
| 1 | 4x T4 | n1-standard-32 | Best availability, good performance |
| 2 | 4x V100 | n1-standard-16 | Higher performance, less available |
| 3 | 4x L4 | g2-standard-48 | Newer GPUs, limited regions |
| 4 | 2x T4 | n1-standard-16 | Fallback if 4x unavailable |

### ScaNN and GPU Considerations

**Important:** ScaNN is CPU-bound (uses SIMD instructions, not GPU). The GPU accelerates:
- Model training (embedding lookups, dense layer computations)
- Forward/backward passes through query and candidate towers
- Batch processing during training

But ScaNN index building and approximate nearest neighbor search remain CPU operations. This is acceptable because:
- Index building happens once after training (not during)
- Inference speed from ScaNN (10-20x) compensates for CPU-based indexing

### Verification Steps

Before running large-scale training, verify GPU access:

```python
import tensorflow as tf

print(f"TensorFlow version: {tf.__version__}")
print(f"CUDA built: {tf.test.is_built_with_cuda()}")
print(f"GPUs available: {tf.config.list_physical_devices('GPU')}")

# Test GPU computation
with tf.device('/GPU:0'):
    a = tf.constant([[1.0, 2.0], [3.0, 4.0]])
    b = tf.constant([[1.0, 1.0], [0.0, 1.0]])
    c = tf.matmul(a, b)
    print(f"GPU computation test: {c}")
```

### Conclusion

**This is a solvable container configuration issue, not an architectural problem.**

The application architecture is sound:
- Experiments domain works correctly with TFX 1.15.0 + TF 2.15 + ScaNN 1.3.0
- Training domain requires a GPU-enabled custom container
- The same trainer code generation (`services.py`) works for both CPU and GPU

**Next Steps:**
1. Build `tfx-trainer-gpu` container using Option 1 (TF GPU base)
2. Test GPU detection in a simple Custom Job
3. Configure TFX pipeline to use GPU container for Trainer component
4. Implement GPU fallback strategy in pipeline submission

### References

- [Vertex AI Supported Frameworks](https://cloud.google.com/vertex-ai/docs/supported-frameworks-list)
- [TFX GPU Discussion](https://groups.google.com/a/tensorflow.org/g/tfx/c/5oRt1EzCa4E)
- [Google Deep Learning Containers](https://cloud.google.com/deep-learning-containers/docs/choosing-container)
- [TensorFlow 2.15 Release Notes](https://blog.tensorflow.org/2023/11/whats-new-in-tensorflow-2-15.html)
- [Vertex AI GPU Configuration](https://cloud.google.com/vertex-ai/docs/training/configure-compute)
- [NVIDIA cuDNN Support Matrix](https://docs.nvidia.com/deeplearning/cudnn/backend/latest/reference/support-matrix.html)
- [TFX on Vertex AI Tutorial](https://www.tensorflow.org/tfx/tutorials/tfx/gcp/vertex_pipelines_vertex_training)

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
