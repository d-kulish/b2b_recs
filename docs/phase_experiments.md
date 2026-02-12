# Phase: Experiments Domain

## Document Purpose
This document provides specifications for the **Experiments** page (`model_experiments.html`). The Experiments page enables running Quick Tests to validate configurations and provides an analytics dashboard for comparing results.

**Last Updated**: 2026-02-12 (Fix: Wizard machine_type now controls Dataflow workers end-to-end)

---

## Overview

### Purpose
The Experiments domain allows users to:
1. **Run Quick Tests** to validate feature and model configurations on Vertex AI
2. **Compare experiments** side-by-side (2-4 at a time)
3. **Analyze results** via the Experiments Dashboard with KPIs, heatmaps, and insights
4. **Identify best configurations** through hyperparameter analysis

### Key Principle
**Iterate fast, train cheap.** Quick Tests use sampled data and minimal epochs to rapidly validate configurations before committing to expensive full training runs.

### Architecture

```
                     ┌─────────────────────────────────────────────────┐
                     │                EXPERIMENTS PAGE                  │
                     ├─────────────────────────────────────────────────┤
                     │  Chapter 1: Quick Test                          │
                     │  - Create/manage experiments                     │
                     │  - Compare results                               │
                     │                                                  │
                     │  Chapter 2: Dashboard                            │
                     │  - KPIs by model type                           │
                     │  - Analytics & insights                         │
                     └─────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              EXECUTION PIPELINE                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   Cloud Build (Compile)           Vertex AI Pipeline (Train)                 │
│   ┌─────────────────┐            ┌────────────────────────────────────────┐ │
│   │ Generate TFX    │            │ ExampleGen → StatisticsGen → SchemaGen │ │
│   │ pipeline code   │ ─────────► │     │                                  │ │
│   │ Submit to       │            │     └───► Transform → Trainer          │ │
│   │ Vertex AI       │            │                          │             │ │
│   └─────────────────┘            │                          ▼             │ │
│                                  │                 training_metrics.json   │ │
│                                  └────────────────────────────────────────┘ │
│                                                                               │
│   Results stored in GCS: gs://b2b-recs-quicktest-artifacts/{exp_id}/         │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Model Types Supported

| Model Type | Purpose | Metrics | TFRS Task |
|------------|---------|---------|-----------|
| **Retrieval** | Find candidate items | Recall@5/10/50/100 | `tfrs.tasks.Retrieval()` |
| **Ranking** | Score/rank candidates | RMSE, MAE | `tfrs.tasks.Ranking()` |
| **Multitask** | Combined objectives | All 8 metrics | Weighted loss |

---

## Page Structure

### Chapter 1: Quick Test

Experiment creation and management interface.

#### Filter Bar
- **Status Filter**: All / Running / Completed / Failed / Cancelled
- **Model Type Filter**: All / Retrieval / Ranking / Multitask
- **Dataset Filter**: Dropdown of available datasets
- **Feature Config Filter**: Dropdown of feature configs
- **Model Config Filter**: Dropdown of model configs
- **Search**: Full-text search on experiment name/description

#### Experiment Cards
Each card displays:
- Experiment name and description
- Status badge (Running/Completed/Failed/Cancelled)
- Model type badge (Retrieval/Ranking/Multitask)
- Configuration summary (Dataset, Features, Model)
- Metrics (Recall@K for retrieval, RMSE/MAE for ranking)
- Progress bar (for running experiments)
- Action buttons: View, Rerun, Cancel/Delete

#### Control Buttons
- **[+ New Exp]**: Opens 2-step wizard
- **[Compare]**: Opens comparison selection modal

### Chapter 2: Experiments Dashboard

Analytics and insights for completed experiments, filtered by selected model type.

#### Model Type KPIs (Clickable)
Three KPI containers (Retrieval/Ranking/Multitask) showing:
- Experiment count
- Best metric value
- Average metric value

Clicking a KPI filters all dashboard content by that model type.

#### Dashboard Components

| Component | Description |
|-----------|-------------|
| **Metrics Trend** | Line chart showing best metrics over time |
| **Top Configurations** | Table of best-performing experiment configs |
| **Hyperparameter Insights** | TPE-based analysis of what correlates with good results |
| **Training Heatmaps** | Epoch loss + final metrics visualization |
| **Dataset Performance** | Compare metrics across different datasets |
| **Suggested Experiments** | AI-powered recommendations for next experiments |

---

## New Experiment Wizard

### Step 1: Select Configs

1. **Model Type Selector** (required first)
   - Retrieval (default) / Ranking / Multitask
   - Filters available Feature and Model configs

2. **Feature Config** dropdown
   - Shows configs compatible with selected model type
   - Preview: Tensor dimensions, assigned features, target column (if ranking)

3. **Model Config** dropdown
   - Shows configs of selected model type
   - Preview: Tower architecture, layer summary, Rating Head (if ranking)

4. **Dataset & Split**
   - Dataset dropdown
   - Train/Test split options: Random (80/20), Time Holdout, Strict Time

### Step 2: Training Parameters

| Parameter | Options | Default |
|-----------|---------|---------|
| **Sample %** | 5%, 10%, 25%, 50%, 100% | 10% |
| **Epochs** | 1-50 | 3 |
| **Batch Size** | 256, 512, 1024, 2048, 4096, 8192 | 4096 |
| **Learning Rate** | 0.001 - 1.0 | From ModelConfig |
| **Hardware** | Small (e2-standard-4) / Medium (e2-standard-8) / Large (e2-standard-16) | Auto-recommended |

---

## Experiment View Modal

Tabbed modal for viewing experiment details. **Now uses the reusable `ExpViewModal` module** shared with the Training page.

### Architecture

The view modal is implemented as a stand-alone reusable module:

| File | Purpose |
|------|---------|
| `static/js/exp_view_modal.js` | JavaScript module (IIFE pattern) |
| `static/css/exp_view_modal.css` | Complete CSS styling |
| `templates/includes/_exp_view_modal.html` | Reusable HTML template |
| `static/js/pipeline_dag.js` | Pipeline DAG visualization |

### Integration

```javascript
// Configure module on page load
ExpViewModal.configure({
    showTabs: ['overview', 'pipeline', 'data', 'training'],
    onUpdate: function(exp) {
        loadTopConfigurations();
        loadRecentExperiments();
    }
});

// Open modal (from card View button or table row click)
ExpViewModal.open(expId);
```

### Tabs

#### Overview Tab
- Results summary (metrics for completed experiments)
- Dataset details (tables, joins, filters)
- Feature Config (tensor visualization with dimension breakdown)
- Model Config (tower architecture with layer badges)
- Sampling parameters
- Training parameters

#### Pipeline Tab
- Pipeline DAG visualization with status icons
- Progress bar (for running experiments)
- Component logs (click node to view)
- Error details (for failed experiments)

#### Data Insights Tab (lazy-loaded)
- Dataset statistics summary
- Feature distributions (numeric and categorical)
- Schema information
- Link to full TFDV report

#### Training Tab (lazy-loaded)
- Loss curves (train/eval)
- Metrics charts (Recall@K or RMSE/MAE)
- Weight analysis (L1/L2 norms by tower)
- Weight histogram (TensorBoard-style ridgeline)
- Final metrics table
- Vocabulary statistics

### Live Polling

For running experiments, the modal automatically:
- Polls experiment status every 10 seconds
- Updates pipeline DAG node statuses
- Refreshes progress bar and metrics
- Stops polling when experiment completes/fails/cancels

---

## Compare Modal

Side-by-side comparison of 2-4 experiments:

### Selection
- Paginated list of completed experiments
- Checkbox selection (2-4 required)
- Filter by model type

### Comparison Table
Unified table showing for each experiment:
- Dataset configuration
- Feature configuration (tensor dims, feature count)
- Model architecture (tower structures, params)
- Training parameters (epochs, batch size, LR, sample %)
- Final metrics (Recall@K or RMSE/MAE)

---

## API Endpoints

### Experiment Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/quick-tests/` | List experiments (paginated) |
| POST | `/api/feature-configs/{id}/quick-test/` | Create experiment |
| GET | `/api/quick-tests/{id}/` | Get experiment details |
| POST | `/api/quick-tests/{id}/cancel/` | Cancel running experiment |
| POST | `/api/quick-tests/{id}/rerun/` | Re-run experiment with same config |
| DELETE | `/api/quick-tests/{id}/delete/` | Delete experiment + GCS artifacts |
| GET | `/api/quick-tests/{id}/errors/` | Get error details |
| GET | `/api/quick-tests/{id}/statistics/` | Get data insights |
| GET | `/api/quick-tests/{id}/training-history/` | Get training metrics |
| GET | `/api/quick-tests/{id}/histogram-data/` | Get weight histogram |

### Comparison & Selection

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/experiments/selectable/` | List experiments for comparison |
| POST | `/api/experiments/compare/` | Get comparison data |

### Dashboard Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/experiments/dashboard-stats/` | KPI stats by model type |
| GET | `/api/experiments/metrics-trend/?model_type=X` | Metrics over time |
| GET | `/api/experiments/top-configurations/?model_type=X` | Best configs table |
| GET | `/api/experiments/hyperparameter-analysis/?model_type=X` | TPE analysis |
| GET | `/api/experiments/training-heatmaps/?model_type=X` | Heatmap data |
| GET | `/api/experiments/dataset-comparison/?model_type=X` | Dataset performance |
| GET | `/api/experiments/suggestions/` | Suggested experiments |

### Configuration Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{id}/feature-configs/` | Available feature configs |
| GET | `/api/model-configs/` | Available model configs |
| GET | `/api/feature-configs/{id}/` | Feature config details |
| GET | `/api/model-configs/{id}/` | Model config details |
| GET | `/api/datasets/{id}/summary/` | Dataset summary |

---

## Data Model

### QuickTest Model

```python
class QuickTest(models.Model):
    """Tracks quick test experiment runs."""

    # Configuration references
    feature_config = ForeignKey('FeatureConfig')
    model_config = ForeignKey('ModelConfig')
    dataset = ForeignKey('Dataset')

    # Training parameters
    data_sample_percent = IntegerField(default=10)
    epochs = IntegerField(default=3)
    batch_size = IntegerField(default=4096)
    learning_rate = FloatField(default=0.1)

    # Status tracking
    status = CharField(choices=['submitting', 'running', 'completed', 'failed', 'cancelled'])
    current_stage = CharField()  # ExampleGen, Transform, Trainer, etc.

    # Pipeline references
    cloud_build_id = CharField()
    vertex_pipeline_job_name = CharField()
    gcs_artifacts_path = CharField()

    # Results - Retrieval metrics
    loss = FloatField(null=True)
    recall_at_5 = FloatField(null=True)
    recall_at_10 = FloatField(null=True)
    recall_at_50 = FloatField(null=True)
    recall_at_100 = FloatField(null=True)

    # Results - Ranking metrics
    rmse = FloatField(null=True)
    mae = FloatField(null=True)
    test_rmse = FloatField(null=True)
    test_mae = FloatField(null=True)

    # Cached training history (for fast UI loading)
    training_history_json = JSONField(default=dict)

    # Hyperparameter analysis fields
    buyer_tower_structure = CharField()
    product_tower_structure = CharField()
    buyer_tensor_dim = IntegerField()
    product_tensor_dim = IntegerField()
    buyer_feature_details = JSONField()
    product_feature_details = JSONField()
```

### Training History Cache Structure

```json
{
    "cached_at": "2026-01-15T10:30:00Z",
    "epochs": [0, 5, 10, 15, ...],
    "loss": {
        "train": [...],
        "val": [...],
        "total": [...]
    },
    "gradient_norms": {
        "total": [...],
        "query": [...],
        "candidate": [...]
    },
    "final_metrics": {
        "test_recall_at_5": 0.045,
        "test_recall_at_10": 0.082,
        "test_recall_at_50": 0.195,
        "test_recall_at_100": 0.285
    },
    "params": {
        "epochs": 50,
        "batch_size": 4096,
        "learning_rate": 0.1
    }
}
```

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pipeline Framework | Native TFX SDK | Full TFX component support |
| Data Flow | BigQuery → TFRecords → TFX | Standard TFX pattern |
| Dataflow Region | `europe-west1` (Belgium) | Hardcoded. Largest EU region with best worker capacity. `europe-central2` (Warsaw) is prone to `ZONE_RESOURCE_POOL_EXHAUSTED` |
| Dataflow Machine Type | User-selected via wizard | Flows from wizard → DB → Cloud Build CLI arg → compile script → `beam_pipeline_args`. Defaults to `e2-standard-4` |
| Pipeline Orchestration Region | `europe-central2` (Warsaw) | Co-located with BigQuery data and GCS buckets |
| Hardware Tiers (Wizard) | `e2-standard-4/8/16` | e2-series for better availability; auto-recommended based on dataset size and model complexity |
| Metrics Storage | GCS JSON files | Simple, no extra infrastructure |
| Training Cache | Django JSONField | Instant UI loading (<1s) |
| Histogram Data | On-demand fetch | Large data, rarely needed |
| Container Image | `gcr.io/tfx-oss-public/tfx:1.15.0` + TFRS + ScaNN | TF 2.15 compatibility |

---

## Services

### ExperimentService

Handles experiment lifecycle:
- `create_quick_test()` - Validate config, submit to Cloud Build
- `poll_experiment_status()` - Check Vertex AI pipeline status
- `extract_results()` - Parse training_metrics.json from GCS
- `rerun_quick_test()` - Re-run experiment with same configuration (terminal states only)
- `cancel_quick_test()` - Cancel Cloud Build or Vertex pipeline
- `delete_quick_test()` - Delete DB record and GCS artifacts

### TrainingCacheService

Caches training history for fast UI:
- `cache_training_history()` - Fetch from GCS, store in DB
- `get_cached_history()` - Return cached data
- Samples every 5th epoch to reduce cache size

#### Training History Data Flow (Experiments vs Training Runs)

**For Experiments (QuickTest):**
```
Trainer Component → training_metrics.json (GCS) → TrainingCacheService → training_history_json (DB) → API → UI
```

The TrainingCacheService reads `training_metrics.json` from GCS and caches it in the `training_history_json` JSONField for instant UI loading.

**For Training Runs (TrainingRun):**
```
Trainer Component → training_metrics.json (GCS) → ??? (NOT IMPLEMENTED) → training_history_json (DB, EMPTY) → No API endpoint → UI shows "Loading..."
```

**Current Gap (as of 2026-01-20):**

| Component | Experiments | Training Runs |
|-----------|-------------|---------------|
| GCS `training_metrics.json` | ✅ Written by Trainer | ✅ Written by Trainer |
| DB `training_history_json` | ✅ Cached via TrainingCacheService | ❌ Empty (no cache service) |
| API endpoint | ✅ `/api/quick-tests/{id}/training-history/` | ❌ Missing |
| Frontend preload | ✅ `preloadTrainingHistory()` | ❌ Not called in training_run mode |
| UI Training tab | ✅ Charts displayed | ❌ Shows "Loading training data..." forever |

**GCS File Structure (training_metrics.json):**
```json
{
    "epochs": [0, 1, 2, ...],           // Epoch indices
    "loss": {"train": [...], "val": [...]},
    "gradient": {...},
    "weight_stats": {...},
    "gradient_stats": {...},
    "final_metrics": {
        "test_recall_at_5": 0.047,
        "test_recall_at_10": 0.076,
        ...
    },
    "params": {"epochs": 150, "batch_size": 4096, ...},
    "available": true,
    "saved_at": "2026-01-19T19:17:00Z"
}
```

**To Fix Training Runs:**
1. Add API endpoint: `/api/training-runs/{id}/training-history/`
2. Either cache from GCS (like experiments) or fetch directly
3. Update `exp_view_modal.js` to call training history endpoint in `training_run` mode

### HyperparameterAnalyzer

TPE-based analysis of what configurations work best:
- Analyzes: tower structure, tensor dims, features, dataset filters
- Threshold: Top 30% by primary metric
- Output: Cards showing which values correlate with good results

### PipelineLogsService

Fetches pipeline component logs from Cloud Logging for the Pipeline tab:
- `get_component_logs()` - Fetch logs for a specific TFX component
- Primary strategy: Task-specific logs via `ml_job` resource type
- Fallback strategy: Pipeline-level logs via `aiplatform.googleapis.com/PipelineJob`
- Returns 50 most recent log entries (newest first)
- Supports all pipeline components: Examples, Stats, Schema, Transform, Train

**Log Display Features:**
- Clean table layout: Severity icon | Timestamp | Message
- Color-coded severity (ERROR=red, WARNING=amber, INFO=blue, DEBUG=gray)
- Manual refresh only (no auto-load on node click)
- Matches Google Logs Explorer styling

---

## Bug Fix: Wizard machine_type Was Dead Code (2026-02-12)

### Problem

The experiment wizard lets users select a hardware tier (Small / Medium / Large) which maps to `e2-standard-4/8/16`. This value was saved to the `QuickTest.machine_type` field and passed through 8 layers of code — API → ExperimentService → Cloud Build substitution → CLI argument → compile script — but the compile scripts **silently ignored it**. Both `ml_platform/experiments/services.py` (inline compile script) and `cloudbuild/compile_and_submit.py` (standalone compile script) hardcoded:

```python
dataflow_machine_type = 'e2-standard-4'  # ignores machine_type parameter
```

This meant every experiment ran on `e2-standard-4` regardless of what the user selected in the wizard. The `machine_type` parameter was accepted by both `create_tfx_pipeline()` functions but never used for Dataflow worker configuration.

### Analysis

The `machine_type` parameter flows through this call chain:

```
Wizard UI → POST /api/.../quick-test/ → ExperimentService.create_quick_test()
  → _submit_pipeline_via_cloud_build() → Cloud Build --machine-type=$_MACHINE_TYPE
    → compile_and_submit.py create_tfx_pipeline(machine_type=...)
      → beam_pipeline_args['--machine_type=???']  ← HERE: hardcoded, not from param
```

The inline script in `ExperimentService` had the same issue at line 1181.

Additionally, all intermediate function defaults still referenced the old `n1-standard-4` machine series, even though:
- The model choices were updated to `e2-standard` (better availability, dynamic resource pool)
- The `n1-standard` series is legacy and prone to capacity issues
- The help_text incorrectly stated the machine_type controlled "Trainer and Dataflow workers" — the Trainer actually runs on the Vertex AI pipeline worker VM, not a user-selected VM

### Fix Applied

**Core fix** — use the `machine_type` parameter instead of hardcoding:
```python
# Both compile scripts: experiments/services.py:1181 and compile_and_submit.py:144
dataflow_machine_type = machine_type  # was: 'e2-standard-4'
```

**Default updates** — aligned 7 stale `n1-standard-4` defaults to `e2-standard-4` across:
- `ml_platform/experiments/services.py` (3 function signatures)
- `cloudbuild/compile_and_submit.py` (function param + argparse default)
- `ml_platform/pipelines/pipeline_builder.py` (2 function signatures)
- `ml_platform/pipelines/services.py` (settings fallback)

**Model + migration** — updated `QuickTest.machine_type` field choices, default, and help_text. Migration `0060_update_machine_type_choices.py` updates the field metadata (no data migration needed — CharField doesn't enforce choices at DB level, so existing `n1-standard` values are preserved).

### Expected Behaviour

After the fix, the wizard selection controls Dataflow workers end-to-end:

| Wizard Selection | DB Value | Cloud Build Arg | Dataflow Workers |
|-----------------|----------|-----------------|------------------|
| Small | `e2-standard-4` | `--machine-type=e2-standard-4` | 4 vCPU, 16 GB |
| Medium | `e2-standard-8` | `--machine-type=e2-standard-8` | 8 vCPU, 32 GB |
| Large | `e2-standard-16` | `--machine-type=e2-standard-16` | 16 vCPU, 64 GB |

The Dataflow **region** stays hardcoded to `europe-west1` (Belgium) — this is intentional to avoid `ZONE_RESOURCE_POOL_EXHAUSTED` errors in `europe-central2` (Warsaw).

### Out of Scope

- `ml_platform/training/services.py:3176` — Training pipeline Dataflow also hardcodes `n1-standard-4`. Separate domain, separate fix.
- `cloudbuild/tfx-trainer-gpu/` — GPU Custom Jobs require `n1-standard` (GPUs don't attach to e2 VMs).

---

## Implementation Status

### Completed Features

- [x] Quick Test chapter with experiment cards
- [x] 2-step wizard (Select Configs → Training Params)
- [x] Model type selection (Retrieval/Ranking/Multitask)
- [x] Experiment comparison (2-4 experiments)
- [x] View modal with Config/Data Insights/Training/Error tabs
- [x] **View modal migrated to reusable ExpViewModal module** (2026-01-15)
- [x] **Pipeline logs service with Cloud Logging integration** (2026-01-15)
- [x] Cancel, Delete, and Rerun functionality
- [x] Experiments Dashboard with 8 analytical components
- [x] Model type conditional filtering for dashboard
- [x] Training heatmaps (epoch loss + final metrics)
- [x] Hyperparameter insights (TPE analysis)
- [x] Suggested experiments
- [x] ScaNN support for retrieval models
- [x] Multitask model support

### Future Enhancements

- [ ] Full Training Pipeline (extended epochs, checkpointing)
- [ ] Model Deployment (candidate index, serving endpoints)
- [ ] A/B Testing support

---

## Related Documentation

- [phase_experiments_implementation.md](phase_experiments_implementation.md) - Detailed implementation guide
- [phase_experiments_changelog.md](phase_experiments_changelog.md) - Detailed changelog history
- [phase_training.md](phase_training.md) - Training page (contains full ExpViewModal module documentation)
- [multi_task.md](multi_task.md) - Multitask model implementation
- [ranking_implementation.md](ranking_implementation.md) - Ranking model implementation
- [phase_configs.md](phase_configs.md) - Datasets & Configs page specification
