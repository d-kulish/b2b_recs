# Phase: Experiments Domain

## Document Purpose
This document provides specifications for the **Experiments** page (`model_experiments.html`). The Experiments page enables running Quick Tests to validate configurations and provides an analytics dashboard for comparing results.

**Last Updated**: 2026-02-26 (History feature type — purchase history taste vector)

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
| **Ranking** | Score/rank candidates | RMSE, MAE, AUC-ROC* | `tfrs.tasks.Ranking()` |
| **Multitask** | Combined objectives | All metrics | Weighted loss |

*AUC-ROC is auto-detected and displayed only when labels are binary (0/1).

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
- Metrics (Recall@K for retrieval, RMSE/MAE for ranking, AUC-ROC for binary ranking)
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
| **Hardware** | Small (e2-standard-4) / Medium (e2-standard-8) / Large (e2-standard-16) / GPU T4 (n1-standard-4 + T4) | Auto-recommended (CPU only) |

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
- Metrics charts (Recall@K or RMSE/MAE, AUC-ROC line chart for binary ranking)
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

    # Hardware
    machine_type = CharField(default='e2-standard-4')  # Dataflow workers
    gpu_config = JSONField(default=dict)  # GPU for Trainer (empty = CPU-only)

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
    auc_roc = FloatField(null=True)       # Binary labels only
    test_auc_roc = FloatField(null=True)  # Binary labels only

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
| Hardware Tiers (Wizard) | `e2-standard-4/8/16` (CPU) + `n1-standard-4 + T4` (GPU) | e2-series for CPU (better availability); n1 required for GPU (GCP constraint — GPUs cannot attach to e2 VMs) |
| GPU Training Region | `europe-west4` (Netherlands) | GPU capacity; `europe-central2` doesn't support GPU training. Pipeline orchestrates from `europe-central2`, Trainer Custom Job runs in `europe-west4` |
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

## Bug Fix: Ranking Model Loss Reduction Causing Training Instability (2026-02-23)

### Problem

Ranking model experiments with binary labels (e.g., "probability to buy" with values 0/1) showed catastrophic training instability:
- Validation loss exploded from ~500 to 2,000+ over 100 epochs while training loss decreased
- RMSE of 3.25 on binary (0/1) labels — should be ≤1.0; predictions diverged far outside [0,1]
- Train RMSE ≈ Test RMSE (3.25 ≈ 3.23) — model equally broken on all data, not classic overfitting

Retrieval models were unaffected because `tfrs.tasks.Retrieval()` uses its own internally-normalized softmax loss.

### Root Cause

The ranking loss functions in `TrainerModuleGenerator` used `Reduction.SUM`:

```python
# ml_platform/configs/services.py (ranking + multitask paths)
loss_mapping = {
    'mse': 'tf.keras.losses.MeanSquaredError(reduction=tf.keras.losses.Reduction.SUM)',
    'binary_crossentropy': 'tf.keras.losses.BinaryCrossentropy(reduction=tf.keras.losses.Reduction.SUM)',
    'huber': 'tf.keras.losses.Huber(reduction=tf.keras.losses.Reduction.SUM)',
}
```

`Reduction.SUM` sums loss over the batch instead of averaging. For batch_size=4096, gradients were ~4096x too large. Combined with `clipnorm=1.0`, this created a **fixed-step training dynamic**: the optimizer always took steps of magnitude `learning_rate × 1.0` regardless of proximity to the optimum. The model could never converge — it perpetually overshot, and the unbounded output layer (`Dense(1)` with no activation) allowed predictions to diverge to arbitrary values.

Additionally, `BinaryCrossentropy` was instantiated without `from_logits=True`, but the output layer produces raw logits (no sigmoid). This caused BCE to treat logits as probabilities, clipping them internally and destroying gradient signal.

### Fix Applied

**File:** `ml_platform/configs/services.py` — two locations (ranking path line ~4293, multitask path line ~5423)

Removed `Reduction.SUM` (use default `SUM_OVER_BATCH_SIZE`) and added `from_logits=True` to BCE:

```python
loss_mapping = {
    'mse': 'tf.keras.losses.MeanSquaredError()',
    'binary_crossentropy': 'tf.keras.losses.BinaryCrossentropy(from_logits=True)',
    'huber': 'tf.keras.losses.Huber()',
}
```

### Impact on Existing Models

| Target Type | Loss | Effect |
|---|---|---|
| **Binary (0/1)** | BCE | Fixed — `from_logits=True` + proper gradient scaling |
| **Binary (0/1)** | MSE | Fixed — properly scaled gradients allow convergence |
| **Continuous (sales)** | MSE/Huber | Safe — default reduction averages correctly; `clipnorm=1.0` still protects against gradient spikes |

The `clipnorm=1.0` on the optimizer remains as a safety net but no longer dominates training dynamics.

### Verification

Rerun experiment #149 (or any ranking experiment) — validation loss should now track close to training loss, and RMSE on binary labels should be well below 1.0.

---

## GPU T4 Support (2026-02-13)

### Overview

The experiment wizard now supports GPU-accelerated training with a single NVIDIA T4 GPU. The T4 card in the hardware selection is unlocked; V100 remains locked for future use.

### Hardware Options

| Wizard Card | Dataflow Workers | Trainer Execution | Region |
|-------------|-----------------|-------------------|--------|
| Small | `e2-standard-4` (4 vCPU, 16 GB) | Standard Trainer (CPU) | `europe-central2` |
| Medium | `e2-standard-8` (8 vCPU, 32 GB) | Standard Trainer (CPU) | `europe-central2` |
| Large | `e2-standard-16` (16 vCPU, 64 GB) | Standard Trainer (CPU) | `europe-central2` |
| **GPU T4** | `e2-standard-4` (4 vCPU, 16 GB) | **GenericExecutor Custom Job** (1x T4) | **`europe-west4`** |

### Architecture

When GPU T4 is selected, the pipeline uses two separate compute configurations:

1. **Dataflow workers** (BigQueryExampleGen, StatisticsGen, Transform) — `e2-standard-4` in `europe-west1`, same as CPU path
2. **Trainer** — Vertex AI Custom Job via `GenericExecutor` with `n1-standard-4` + 1x T4 GPU in `europe-west4`

This mirrors the Training pipeline's GPU pattern (`ml_platform/training/services.py` lines 2966-3091).

**Why n1-standard-4 for GPU?** GCP requires N1 (or N2D) VMs for GPU attachment — e2-series VMs do not support accelerators. The `n1-standard-4` (4 vCPU, 15 GB RAM) is the smallest N1 VM, sufficient for a single T4.

**Why europe-west4?** `europe-central2` (Warsaw) does not support GPU training. `europe-west4` (Netherlands) has good GPU capacity. The pipeline still orchestrates from `europe-central2` — only the Trainer's Custom Job runs in `europe-west4`.

### Data Model

The `gpu_config` JSONField on `QuickTest` stores GPU configuration:

```python
# CPU experiment (default)
gpu_config = {}

# GPU T4 experiment
gpu_config = {
    "gpu_type": "NVIDIA_TESLA_T4",
    "gpu_count": 1,
    "machine_type": "n1-standard-4"
}
```

### Data Flow

```
Wizard (GPU T4 card)
  → machine_type = "e2-standard-4"  (for Dataflow)
  → gpu_config = {gpu_type: "NVIDIA_TESLA_T4", gpu_count: 1, machine_type: "n1-standard-4"}
    → POST /api/.../quick-test/
      → ExperimentService.submit_quick_test(gpu_config=...)
        → QuickTest.gpu_config = {...}
        → _submit_pipeline() → _submit_vertex_pipeline(gpu_config=...)
          → _trigger_cloud_build(gpu_config=...)
            → Cloud Build CLI: --gpu-type --gpu-count --gpu-machine-type --gpu-training-region
              → compile_and_submit.py create_tfx_pipeline(gpu_type=..., ...)
                → GenericExecutor + worker_pool_specs with T4 GPU
```

### Files Modified

| File | Change |
|------|--------|
| `ml_platform/models.py` | Added `gpu_config` JSONField to QuickTest |
| `ml_platform/migrations/0063_quicktest_gpu_config.py` | Migration for new field |
| `ml_platform/experiments/api.py` | Accept/serialize `gpu_config` in API layer |
| `ml_platform/experiments/services.py` | Thread `gpu_config` through 5 methods + update inline compile script with conditional GPU/CPU Trainer |
| `templates/ml_platform/model_experiments.html` | Unlock T4 card, GPU JS logic, payload + display |
| `cloudbuild/compile_and_submit.py` | GPU args and conditional Trainer (consistency) |

### Expected Behaviour

**CPU path** (Small/Medium/Large): Unchanged. Standard Trainer runs on the pipeline worker VM.

**GPU path** (GPU T4):
- Cloud Build logs show `--gpu-type=NVIDIA_TESLA_T4 --gpu-count=1 --gpu-machine-type=n1-standard-4 --gpu-training-region=europe-west4`
- Vertex AI pipeline's Trainer spawns a Custom Job in `europe-west4` with 1x T4 GPU using `tfx-trainer-gpu:latest` image
- Rerun preserves `gpu_config` from the original experiment
- Compare view shows GPU info (e.g., "T4 x1") in the Training section

---

## Feature: AUC-ROC Metrics for Binary Label Ranking Models (2026-02-24)

### Background

Ranking models predict "probability to buy" with binary labels (0/1). Previously only RMSE/MAE were tracked — these measure prediction magnitude accuracy, not ranking quality. For binary classification, AUC-ROC is the standard metric that measures whether the model ranks positives above negatives (higher is better, 0.5 = random, 1.0 = perfect).

### How It Works

**Binary label auto-detection:** During training, the first batch of data is scanned to detect whether labels consist only of {0.0, 1.0}. The result is stored as `is_binary_labels` in `training_metrics.json → params`. No user configuration required.

**AUC-ROC metric:** `tf.keras.metrics.AUC(name='auc_roc', curve='ROC')` is always added to ranking and multitask model task metrics. For non-binary labels, the metric still computes but the UI hides it since its interpretation is less meaningful for continuous targets.

**Frontend display logic:** The `is_binary_labels` flag controls what the UI shows:
- **Binary labels → AUC-ROC primary:** Experiment cards, training cards, model registry, and view modal all show AUC-ROC alongside RMSE. The view modal adds a per-epoch AUC-ROC line chart and includes AUC-ROC in the final metrics table.
- **Non-binary labels → unchanged:** RMSE/MAE display only, fully backward compatible with existing experiments.

### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/configs/services.py` | Added AUC metric to ranking/multitask tasks; binary label detection in both run_fn paths; `is_binary_labels` param logging |
| `ml_platform/models.py` | Added `auc_roc`, `test_auc_roc` fields to QuickTest |
| `ml_platform/training/models.py` | Added `auc_roc`, `test_auc_roc` fields to TrainingRun |
| `ml_platform/experiments/services.py` | Extract `val_auc_roc[-1]` and `test_auc_roc` from training metrics |
| `ml_platform/training/services.py` | Same extraction for TrainingRun |
| `ml_platform/experiments/api.py` | Serialize `auc_roc`, `test_auc_roc`, `is_binary_labels` in 3 metrics helpers |
| `ml_platform/training/api.py` | Serialize same fields in 2 serialization locations |
| `static/js/exp_view_modal.js` | AUC-ROC bar chart bars, per-epoch line chart, results card, final metrics table |
| `templates/includes/_exp_view_modal.html` | New canvas for AUC-ROC line chart |
| `templates/ml_platform/model_experiments.html` | AUC-ROC in experiment cards (ranking + multitask) |
| `static/js/training_cards.js` | AUC-ROC in training run cards |
| `static/js/models_registry.js` | AUC-ROC in registered model cards |

### Backward Compatibility

- Old experiments without `is_binary_labels` in params default to `false` — UI shows RMSE/MAE only
- AUC-ROC model fields are nullable — no impact on existing data
- `tf.keras.metrics.AUC` is always compiled into the model but only surfaced in UI when binary

---

## Bug Fix: AUC-ROC Metrics Not Displayed Despite Being Computed (2026-02-24)

### Problem

After deploying AUC-ROC metrics (commit `e9d6420`), experiment QT-159 (and all other binary-label experiments) showed no AUC-ROC metrics — neither on experiment cards nor in the Training History tab of the view modal. RMSE/MAE displayed correctly; only AUC-ROC was missing.

### Root Cause

The `TrainingCacheService._extract_cacheable_data()` in `ml_platform/experiments/training_cache_service.py` constructs the cached `params` dict from hardcoded QuickTest DB fields:

```python
# BEFORE (bug): params built only from DB fields — trainer-reported params dropped
'params': {
    'epochs': quick_test.epochs,
    'batch_size': quick_test.batch_size,
    'learning_rate': ...,
    'optimizer': ...,
    'embedding_dim': ...,
},
```

The trainer writes `is_binary_labels` into `training_metrics.json → params` in GCS, but this flag was **dropped during caching** because the cache service rebuilt `params` from scratch using only DB fields. Since `is_binary_labels` never made it into the cached training history, the entire UI display chain evaluated it as `false`:

- Experiment cards (`model_experiments.html`): `if (exp.is_binary_labels)` → `false` → AUC-ROC hidden
- View modal metrics chart (`exp_view_modal.js`): `params.is_binary_labels === true` → `false` → AUC-ROC bars skipped
- View modal AUC-ROC line chart: same check → chart wrapper hidden
- View modal final metrics table: same check → AUC-ROC row omitted

The per-epoch AUC-ROC values (`loss.auc_roc`, `loss.val_auc_roc`) and final AUC-ROC values (`final_metrics.test_auc_roc`) were all correctly cached — only the `is_binary_labels` gate was missing.

### Fix Applied

**File:** `ml_platform/experiments/training_cache_service.py` — two methods:
- `_extract_cacheable_data()` (QuickTest path)
- `_extract_cacheable_data_for_run()` (TrainingRun path)

Merge trainer-reported params from GCS into the cached params dict. GCS params go first so DB fields override duplicates:

```python
# AFTER (fix): merge GCS params (is_binary_labels, label_key, etc.) with DB fields
'params': {
    **full_history.get('params', {}),  # ← trainer-reported params preserved
    'epochs': quick_test.epochs,
    'batch_size': quick_test.batch_size,
    'learning_rate': ...,
    'optimizer': ...,
    'embedding_dim': ...,
},
```

**File:** `ml_platform/management/commands/backfill_training_cache.py`

Updated queryset filter to include experiments with `gcs_artifacts_path` (not just `mlflow_run_id`), so newer MetricsCollector-based experiments are picked up by the backfill command.

### Re-cache

After the fix, all completed experiments were re-cached:

```bash
python manage.py backfill_training_cache --force
# Result: 24 experiments re-cached from GCS with corrected params
```

---

## Feature: History Feature Type — Purchase History Taste Vector (2026-02-26)

### Background

The standalone experiment (`scripts/test_taste_vector.py`) validated that an averaged purchase history embedding ("taste vector") improves retrieval Recall@5 by **+37%**. This feature integrates the taste vector into the platform as a 4th feature data type ("history") alongside text/numeric/temporal, so it works through the normal Experiments UI and Training pipeline workflow.

A history feature is a variable-length `ARRAY<STRING>` column (e.g. product IDs a buyer has purchased) that gets embedded using a **shared embedding table** with the product tower's product_id, then averaged into a fixed-width dense vector.

### How It Works

**Feature Config setup:**
1. User drags an ARRAY column (e.g. `purchase_history`) to the buyer tower
2. UI auto-detects the `ARRAY<STRING>` BigQuery type and sets `data_type: "history"`
3. User configures: `shared_with` (links to product_id feature), `embedding_dim` (16/32/64), `max_length` (padding cap, default 50)

**Code generation pipeline:**

```
FeatureConfig (history feature)
  → PreprocessingFnGenerator
    → tft.apply_vocabulary(inputs['purchase_history'], vocab='product_id_vocab')
  → TrainerModuleGenerator
    → Shared Embedding: tf.keras.layers.Embedding(vocab_size, 32, name='shared_product_embedding')
    → BuyerModel: masked average of history IDs through shared embedding → 32D vector
    → ProductModel: product_id lookup through same shared embedding
    → Input fn: SparseTensor → padded dense [batch, max_length]
    → Serving: 2D input [None, max_length] in raw tensor signature
```

**Training flow:**
- BigQuery ARRAY column flows through ExampleGen as VarLenFeature
- Transform applies the product_id vocabulary to array elements (shared vocab)
- Trainer input_fn pads SparseTensor to fixed-width dense tensor
- BuyerModel embeds each history ID through shared embedding, masks padding, averages → taste vector
- ProductModel uses same shared embedding for product_id lookup

### Feature Config JSON

```json
{
    "column": "purchase_history",
    "display_name": "purchase_history",
    "bq_type": "ARRAY<STRING>",
    "data_type": "history",
    "transforms": {
        "history": {
            "enabled": true,
            "shared_with": "product_id",
            "embedding_dim": 32,
            "max_length": 50
        }
    }
}
```

### Model Type Support

All 3 model types (Retrieval, Ranking, Multitask) support history features. Parity is ensured by shared helper methods in `TrainerModuleGenerator`:

| Component | Method |
|-----------|--------|
| Shared embedding creation | `_generate_shared_embedding_code()` |
| Tower instantiation | `_generate_tower_instantiation_code()` |
| Input padding | `_generate_history_padding_code()` |
| Serving signature | `_generate_raw_tensor_signature()` |

### UI Changes

- **Data type selector**: Added "History" option with clock icon
- **Config modal**: Shared_with dropdown (product tower primary ID features), embedding dimension presets (16/32/64), max_length input
- **Feature display**: Shows `Shared(product_id): 32D`
- **Experiments page**: DATA_TYPES constant includes history

### Validation Results (Standalone Experiment)

| Metric | Baseline #162 | With Taste Vector | Change |
|--------|---------------|-------------------|--------|
| Recall@5 | 0.0523 | **0.0718** | **+37.2%** |
| Recall@10 | 0.0809 | **0.1010** | **+24.9%** |
| Recall@50 | 0.2196 | 0.2040 | -7.1% |
| Recall@100 | 0.3308 | 0.2965 | -10.4% |

Top-K precision improved significantly. Recall@50/100 drop is due to overfitting after epoch ~13 — early stopping (separate feature) would resolve this.

### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/models.py` | `_calc_feature_dim()`: history → `+embedding_dim` |
| `ml_platform/configs/services.py` | Dimension calc, preprocessing gen, trainer module gen, validation |
| `ml_platform/datasets/services.py` | ARRAY columns bypass COALESCE/TIMESTAMP in query gen |
| `templates/ml_platform/model_configs.html` | History data type UI, config modal, display |
| `templates/ml_platform/model_experiments.html` | DATA_TYPES constant |

### Backward Compatibility

- No history features → all generated code identical to previous behavior
- Existing numeric/text/temporal configs unchanged
- History dimension calculators skip when `transforms.history` absent

### Related Documentation

- [purchase_history.md](purchase_history.md) — Full research, standalone experiment results, and platform integration details

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
- [x] **GPU T4 support** (1x T4 via GenericExecutor in europe-west4) (2026-02-13)
- [x] **History feature type** (purchase history taste vector, shared embedding + masked averaging) (2026-02-26)

### Future Enhancements

- [ ] Early stopping support (critical for taste vector models that overfit after ~13 epochs)
- [ ] GPU V100 support (locked in wizard)
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
