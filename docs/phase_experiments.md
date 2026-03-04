# Phase: Experiments Domain

## Document Purpose
This document provides specifications for the **Experiments** page (`model_experiments.html`). The Experiments page enables running Quick Tests to validate configurations and provides an analytics dashboard for comparing results.

**Last Updated**: 2026-03-04 (Sync documentation with actual page structure and functionality)

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

### Chapter 1: Experiments Dashboard

Analytics and insights for completed experiments, filtered by selected model type. This chapter appears first on the page (collapsed by default).

#### Model Type KPIs (Clickable)

Three KPI sections (Retrieval / Ranking / Hybrid) with 5 metric cards each. Clicking a section filters all dashboard content by that model type.

**Retrieval KPIs:**

| Card | ID | Description |
|------|----|-------------|
| Experiments | `dashboardRetrievalCount` | Total retrieval experiments |
| R@5 | `dashboardRetrievalR5` | Best Recall@5 |
| R@10 | `dashboardRetrievalR10` | Best Recall@10 |
| R@50 | `dashboardRetrievalR50` | Best Recall@50 |
| R@100 | `dashboardRetrievalR100` | Best Recall@100 |

**Ranking KPIs:**

| Card | ID | Description |
|------|----|-------------|
| Experiments | `dashboardRankingCount` | Total ranking experiments |
| RMSE | `dashboardRankingRMSE` | Best RMSE |
| Test RMSE | `dashboardRankingTestRMSE` | Best Test RMSE |
| MAE | `dashboardRankingMAE` | Best MAE |
| Test MAE | `dashboardRankingTestMAE` | Best Test MAE |

**Hybrid (Multitask) KPIs:**

| Card | ID | Description |
|------|----|-------------|
| Experiments | `dashboardHybridCount` | Total hybrid experiments |
| RMSE | `dashboardHybridRMSE` | Best RMSE |
| Test RMSE | `dashboardHybridTestRMSE` | Best Test RMSE |
| R@50 | `dashboardHybridR50` | Best Recall@50 |
| R@100 | `dashboardHybridR100` | Best Recall@100 |

#### Metrics Trend (in KPI header area)

Line chart (Chart.js) showing best metrics over time, filtered by selected model type. Canvas ID: `trendChartCanvas`.

#### Dashboard Components

| Component | Description |
|-----------|-------------|
| **Top Configurations** | Table of top 5 best-performing experiment configs sorted by primary metric |
| **Hyperparameter Insights** | TPE-based analysis with 5 categories (Model Architecture, Features, Dataset, Training, Split Strategy) showing which values correlate with top 30% results |
| **Training Heatmaps** | Two D3.js heatmaps side-by-side: Epoch Loss (60% width) + Final Metrics (40% width). Color scale: green (low) to red (high) |
| **Dataset Performance** | Table comparing metrics across different datasets with model-type-specific columns |
| **Suggested Experiments** | AI-powered recommendations — Feature Exploration or Hyperparameter Variation cards with "Run Experiment" buttons |

### Chapter 2: Quick Test

Experiment creation and management interface.

#### Filter Bar

Six filter controls for the experiment list:

| Filter | ID | Options |
|--------|----|---------|
| **Exp Status** | `expStatusFilter` | All / Running / Completed / Failed / Cancelled |
| **Model Type** | `expModelTypeFilter` | All / Retrieval / Ranking / Hybrid |
| **Dataset Config** | `expDatasetFilter` | All Datasets (dynamically populated) |
| **Features Config** | `expFeatureFilter` | All Features (dynamically populated) |
| **Model Config** | `expModelFilter` | All Models (dynamically populated) |
| **Search** | `expSearchInput` | Full-text search on experiment name, config names, experiment number (e.g., "Exp #62", "#62") — debounced 300ms |

#### Experiment Cards

4-column card layout (`exp-card-new`) — clicking the card opens the full View Modal:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Col 1: Experiment Info (30%)  │ Col 2: Configs (20%)  │ Col 3: Metrics (30%) │ Col 4: Actions (20%) │
│ ● Status badge + icon         │ Dataset name           │ R@5  R@10  R@50 R@100│ [Rerun]    [View]    │
│ Display name (Exp #N)         │ Feature config name    │ Loss: 0.034          │ [Cancel]   [🗑]      │
│ Experiment name (optional)    │ Model config name      │                      │                      │
│ Description (50 chars)        │ Model type badge       │                      │                      │
│ Start: Jan 15 14:30           │                        │                      │                      │
│ End: Jan 15 15:45             │                        │                      │                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│ [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░] 6-Stage Progress Bar                            │
│  Data Prep │ Feature Eng │ Model Build │ Training │ Evaluation │ Export/Deploy │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Model Type Badges:**
- Retrieval: Blue search icon
- Ranking: Yellow star icon
- Hybrid/Multitask: Purple squares icon

**Metrics by Model Type:**
- Retrieval: R@5, R@10, R@50, R@100, Loss
- Ranking: RMSE, Test RMSE, MAE, Test MAE (+ AUC-ROC for binary labels)
- Hybrid: Retrieval section (R@5, R@10, R@50, R@100) + Ranking section (RMSE, Test RMSE, MAE, Test MAE)

**Action Button States:**

| Button | Running/Submitting | Completed/Failed/Cancelled |
|--------|--------------------|---------------------------|
| View | Enabled | Enabled |
| Cancel | Enabled | Disabled |
| Rerun | Disabled | Enabled |
| Delete | Disabled | Enabled |

#### Control Buttons
- **[Compare]** (`compareBtn`): Opens comparison modal
- **[+ New Exp]**: Opens 2-step wizard

#### Pagination
- Default: 5 experiments per page
- Shows "Showing X-Y of Z" with Previous/Next navigation

---

## New Experiment Wizard

2-step modal wizard (`newExpWizardModal`, max-width 1000px) with pill-based step navigation.

### Step 1: Select Configurations

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚡ New Experiment — Step 1 of 2                    [×]         │
│  ○ Select Configs    ○ Training Params                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  MODEL TYPE                                                     │
│  [● Retrieval]  [○ Ranking]  [○ Multitask/Hybrid]              │
│                                                                 │
│  EXPERIMENT METADATA (optional)                                 │
│  Name: [____________________]                                   │
│  Description: [____________________]                            │
│                                                                 │
│  FEATURE CONFIG        FEATURE CONFIG PREVIEW                   │
│  [▼ Select config ]    ┌────────────────────────────┐           │
│                        │ Dataset: Q4 Data            │           │
│                        │ Source: schema.table         │           │
│                        │ Target: rating (FLOAT64)    │← ranking  │
│                        │ Buyer Tensor: 80D  ████░░   │           │
│                        │ Product Tensor: 64D ███░░   │           │
│                        └────────────────────────────┘           │
│                                                                 │
│  MODEL CONFIG          MODEL CONFIG PREVIEW                     │
│  [▼ Select config ]    ┌────────────────────────────┐           │
│                        │ Buyer Tower: 256→128→64→32  │           │
│                        │ Product Tower: 128→64→32    │           │
│                        │ Rating Head: 128→64→1      │← ranking  │
│                        │ Retrieval: ScaNN            │← retrieval│
│                        │ Optimizer: adam, LR: 0.01   │           │
│                        └────────────────────────────┘           │
│                                                                 │
│                                        [Cancel]  [Next →]       │
└─────────────────────────────────────────────────────────────────┘
```

1. **Model Type Selector** (required first)
   - Retrieval (default) / Ranking / Multitask (shown as "Hybrid" in UI)
   - Filters available Feature and Model configs by compatibility

2. **Experiment Metadata** (optional)
   - Experiment Name (`wizardExpName`) — optional text input
   - Description (`wizardExpDescription`) — optional textarea

3. **Feature Config** dropdown (`wizardFeatureSelect`)
   - Shows configs compatible with selected model type
   - **Preview Panel** (`wizardFeaturePreview`):
     - Dataset name and source info
     - Target Column section (ranking configs only): column name, type, transforms
     - Tensor Breakdown Grid (2 columns): Buyer Tensor (dim + feature list) / Product Tensor (dim + feature list)

4. **Model Config** dropdown (`wizardModelSelect`)
   - Shows configs of selected model type
   - **Preview Panel** (`wizardModelPreview`):
     - Tower Architecture: Buyer Tower layers + Product Tower layers with params summary
     - Rating Head section (ranking/multitask only): layers + parameter count
     - Training Parameters preview (optimizer, LR, batch size)
     - Retrieval Algorithm section (retrieval/multitask only): Brute Force or ScaNN

### Step 2: Training Parameters

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚡ New Experiment — Step 2 of 2                    [×]         │
│  ● Select Configs    ○ Training Params                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ⚠ DATA SAMPLING                                               │
│  [5%] [10%] [25%] [100%]  Custom: [__]%                        │
│  Estimated examples: 74,346                                     │
│                                                                 │
│  🔀 SPLIT STRATEGY                                              │
│  [▼ Random (fastest) ]                                          │
│  Train 80% / Eval 15% / Test 5%                                │
│                                                                 │
│  📊 TRAINING PARAMETERS                                         │
│  Epochs:  [5] [10] [25] [50] [100]  Custom: [__]               │
│  Batch:   [1024] [2048] [4096] [8192]  Custom: [__]            │
│  LR:      [0.001] [0.01] [0.05] [0.1]  Custom: [__]           │
│                                                                 │
│  🎯 RATING COLUMN (ranking only)                                │
│  Target: rating (FLOAT64) — from feature config                 │
│                                                                 │
│  🖥 HARDWARE CONFIGURATION                                      │
│  Recommended: Small (based on dataset size)                     │
│  [Small] [Medium] [Large] [GPU T4] [🔒 V100]                   │
│                                                                 │
│  📋 SUMMARY (collapsible)                                       │
│  Feature Config: Q4 v2 │ Model: Deep Tower                     │
│  Sample: 10% │ Epochs: 25 │ Batch: 4096 │ LR: 0.01            │
│                                                                 │
│                              [← Back]  [Cancel]  [▶ Run]       │
└─────────────────────────────────────────────────────────────────┘
```

**Data Sampling:**

| Preset | Custom Range |
|--------|-------------|
| 5%, 10%, 25%, 100% | 1-100% via input |

Note: No 50% preset. Example count (`wizardExampleCountValue`) updates dynamically based on dataset size.

**Split Strategy** (`wizardSplitStrategy`):

| Strategy | Options | Default Behavior |
|----------|---------|-----------------|
| **Random (fastest)** | No extra options | Train 80% / Eval 15% / Test 5% |
| **Time Holdout** | Date column selector + Holdout days | Last N days = test; rest split 80/20 (train/eval) |
| **Strict Temporal** | Train days (7-365, default 60), Val days (1-30, default 7), Test days (1-30, default 7) | Rolling window with fixed periods |

**Training Parameters:**

| Parameter | Preset Buttons | Custom Input | Default |
|-----------|---------------|--------------|---------|
| **Epochs** | 5, 10, 25, 50, 100 | 1-500 | 25 |
| **Batch Size** | 1024, 2048, 4096, 8192 | 128-65536 (step 128) | 1024 |
| **Learning Rate** | 0.001, 0.01, 0.05, 0.1 | 0.0001-1.0 (step 0.001) | 0.01 |

**Hardware Configuration:**

| Card | Machine Type | Specs | GPU |
|------|-------------|-------|-----|
| Small (default) | `e2-standard-4` | 4 vCPU, 16 GB RAM | — |
| Medium | `e2-standard-8` | 8 vCPU, 32 GB RAM | — |
| Large | `e2-standard-16` | 16 vCPU, 64 GB RAM | — |
| GPU T4 | `n1-standard-4` | 4 vCPU, 15 GB RAM | 1× NVIDIA T4 |
| GPU V100 | — | — | Locked ("coming soon") |

Auto-recommendation based on dataset size and model complexity (`hardwareRecommendation`).

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

Side-by-side comparison of 2 experiments (`expCompareModal`, max-width 1000px, height 85vh).

### Selection

Two dropdown selectors (left + right) populated with experiments in terminal states (completed, failed, cancelled) via `/api/experiments/selectable/`. Selecting both experiments triggers a comparison data fetch via `POST /api/experiments/compare/`.

### Accordion Sections

Six expandable sections, each showing left vs right comparison:

```
┌───────────────────────────────────────────────────────────┐
│ Compare Experiments — Side-by-side comparison             │
├───────────────────────────────────────────────────────────┤
│ Left:  [▼ Exp #45 ]          Right: [▼ Exp #62 ]         │
├───────────────────────────────────────────────────────────┤
│ ✅ Results & Metrics                               [▼]    │
│ ┌─────────────────────┬─────────────────────┐             │
│ │ Completed ✓         │ Completed ✓         │             │
│ │ R@100: 0.317        │ R@100: 0.473        │             │
│ │ Loss: 0.034         │ Loss: 0.028         │             │
│ └─────────────────────┴─────────────────────┘             │
│ 🗄 Dataset Configuration                          [▼]     │
│ ⚙ Feature Configuration                           [▼]     │
│ 🧠 Model Configuration                            [▼]     │
│ 🏃 Training Parameters                            [▼]     │
│ 🔽 Sampling Configuration                         [▼]     │
└───────────────────────────────────────────────────────────┘
```

| Section | Icon | Content |
|---------|------|---------|
| **Results & Metrics** | Chart bar (green) | Status badge + model-specific metrics |
| **Dataset Configuration** | Database (purple) | Dataset name, tables, row counts |
| **Feature Configuration** | Cogs (blue) | Tensor dims, feature counts, buyer/product features |
| **Model Configuration** | Brain (pink) | Tower structures, optimizer, embedding dim |
| **Training Parameters** | Running (orange) | Epochs, batch size, LR, hardware, GPU info |
| **Sampling Configuration** | Filter (teal) | Sample %, split strategy, holdout days |

---

## API Endpoints

### Experiment Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/quick-tests/` | List experiments (paginated, filterable) |
| POST | `/api/feature-configs/{id}/quick-test/` | Create experiment |
| GET | `/api/quick-tests/{id}/` | Get experiment details |
| POST | `/api/quick-tests/{id}/cancel/` | Cancel running experiment |
| POST | `/api/quick-tests/{id}/rerun/` | Re-run experiment with same config |
| DELETE | `/api/quick-tests/{id}/delete/` | Delete experiment + GCS artifacts |
| GET | `/api/quick-tests/{id}/errors/` | Get error details |
| GET | `/api/quick-tests/{id}/statistics/` | Get TFDV data statistics |
| GET | `/api/quick-tests/{id}/schema/` | Get TensorFlow Metadata schema |
| GET | `/api/quick-tests/{id}/tfdv-visualization/` | Get TFDV visualization data |
| GET | `/experiments/quick-tests/{id}/tfdv/` | Standalone TFDV page (HTML, opens in new tab) |
| GET | `/api/quick-tests/{id}/training-history/` | Get training metrics |
| GET | `/api/quick-tests/{id}/histogram-data/` | Get weight histogram |
| GET | `/api/quick-tests/{id}/logs/{component}/` | Get pipeline component logs (ExampleGen, StatisticsGen, SchemaGen, Transform, Trainer) |

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

### Dataset Support

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/datasets/{id}/date-columns/` | Available date/timestamp columns for temporal split |

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
    model_config = ForeignKey('ModelConfig', null=True)
    dataset = ForeignKey('Dataset')
    created_by = ForeignKey(User)

    # Experiment metadata
    experiment_name = CharField(max_length=255)        # Optional user-defined name
    experiment_description = TextField()                # Optional user-defined description
    experiment_number = PositiveIntegerField()          # Sequential per Model Endpoint (display: "Exp #N")

    # Training parameters
    data_sample_percent = IntegerField(default=10)
    epochs = IntegerField(default=10)
    batch_size = IntegerField(default=4096)
    learning_rate = FloatField(default=0.001)
    rating_column = CharField(max_length=255)           # For ranking models

    # Split strategy
    split_strategy = CharField()  # random | time_holdout | strict_time
    holdout_days = IntegerField(default=1)
    date_column = CharField(max_length=255)
    train_days = IntegerField()   # strict_time only
    val_days = IntegerField()     # strict_time only
    test_days = IntegerField()    # strict_time only

    # Hardware
    machine_type = CharField(default='e2-standard-4')  # Dataflow workers
    gpu_config = JSONField(default=dict)  # GPU for Trainer (empty = CPU-only)

    # Status tracking
    status = CharField(choices=['pending', 'submitting', 'running', 'completed', 'failed', 'cancelled'])
    current_stage = CharField()  # ExampleGen, Transform, Trainer, etc.
    progress_percent = IntegerField()
    stage_details = JSONField()  # List of {name, status, duration_seconds, error}

    # Pipeline references
    cloud_build_id = CharField()
    cloud_build_run_id = CharField()
    vertex_pipeline_job_name = CharField()
    vertex_pipeline_job_id = CharField()
    gcs_artifacts_path = CharField(max_length=500)

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
    vocabulary_stats = JSONField()

    # Error handling
    error_message = TextField()
    error_stage = CharField(max_length=50)

    # MLflow tracking
    mlflow_run_id = CharField()
    mlflow_experiment_name = CharField()

    # Timestamps
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    submitted_at = DateTimeField(null=True)
    started_at = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
    duration_seconds = IntegerField(null=True)

    # Denormalized hyperparameter analysis fields
    optimizer = CharField()
    output_embedding_dim = IntegerField()
    retrieval_algorithm = CharField()
    top_k = IntegerField()
    buyer_tower_structure = CharField()
    product_tower_structure = CharField()
    buyer_activation = CharField()
    product_activation = CharField()
    buyer_l2_category = CharField()
    product_l2_category = CharField()
    buyer_total_params = IntegerField()
    product_total_params = IntegerField()
    buyer_tensor_dim = IntegerField()
    product_tensor_dim = IntegerField()
    buyer_feature_count = IntegerField()
    product_feature_count = IntegerField()
    buyer_cross_count = IntegerField()
    product_cross_count = IntegerField()
    buyer_feature_details = JSONField()
    product_feature_details = JSONField()
    buyer_cross_details = JSONField()
    product_cross_details = JSONField()

    # Denormalized dataset analysis fields
    dataset_row_count = IntegerField()
    dataset_date_range_days = IntegerField()
    dataset_unique_users = IntegerField()
    dataset_unique_products = IntegerField()
    dataset_date_filters = JSONField()
    dataset_customer_filters = JSONField()
    dataset_product_filters = JSONField()

    @property
    def is_terminal(self):
        """Check if completed/failed/cancelled."""

    @property
    def display_name(self):
        """Returns 'Exp #N' or 'Exp #id'."""
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
| Dataflow Region | `europe-west4` (Netherlands) | Co-located with pipeline orchestration. Cross-region reads from `europe-central2` BigQuery/GCS proven working |
| Dataflow Machine Type | User-selected via wizard | Flows from wizard → DB → Cloud Build CLI arg → compile script → `beam_pipeline_args`. Defaults to `e2-standard-4` |
| Pipeline Orchestration Region | `europe-west4` (Netherlands) | Moved from `europe-central2` (2026-03-02) due to recurring `ZONE_RESOURCE_POOL_EXHAUSTED` in Warsaw |
| Hardware Tiers (Wizard) | `e2-standard-4/8/16` (CPU) + `n1-standard-4 + T4` (GPU) | e2-series for CPU (better availability); n1 required for GPU (GCP constraint — GPUs cannot attach to e2 VMs) |
| GPU Training Region | `europe-west4` (Netherlands) | GPU capacity; `europe-central2` doesn't support GPU training. All pipeline components now run in `europe-west4` |
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

The Dataflow **region** is `europe-west4` (Netherlands) — co-located with pipeline orchestration. Previously `europe-west1` (Belgium), consolidated to `europe-west4` with all Vertex AI workloads (2026-03-02).

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
| Small | `e2-standard-4` (4 vCPU, 16 GB) | Standard Trainer (CPU) | `europe-west4` |
| Medium | `e2-standard-8` (8 vCPU, 32 GB) | Standard Trainer (CPU) | `europe-west4` |
| Large | `e2-standard-16` (16 vCPU, 64 GB) | Standard Trainer (CPU) | `europe-west4` |
| **GPU T4** | `e2-standard-4` (4 vCPU, 16 GB) | **GenericExecutor Custom Job** (1x T4) | **`europe-west4`** |

### Architecture

When GPU T4 is selected, the pipeline uses two separate compute configurations:

1. **Dataflow workers** (BigQueryExampleGen, StatisticsGen, Transform) — `e2-standard-4` in `europe-west4`
2. **Trainer** — Vertex AI Custom Job via `GenericExecutor` with `n1-standard-4` + 1x T4 GPU in `europe-west4`

This mirrors the Training pipeline's GPU pattern (`ml_platform/training/services.py` lines 2966-3091).

**Why n1-standard-4 for GPU?** GCP requires N1 (or N2D) VMs for GPU attachment — e2-series VMs do not support accelerators. The `n1-standard-4` (4 vCPU, 15 GB RAM) is the smallest N1 VM, sufficient for a single T4.

**Why europe-west4?** `europe-central2` (Warsaw) does not support GPU training and suffers from recurring `ZONE_RESOURCE_POOL_EXHAUSTED`. All pipeline components (orchestration, Dataflow, Trainer) now run in `europe-west4` (Netherlands). Data is read cross-region from `europe-central2` BigQuery/GCS.

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

The averaged purchase history embedding ("taste vector") encodes a buyer's entire purchase behavior into a single fixed-width dense vector by embedding each purchased product ID through a shared embedding table and averaging. This pattern is proven at scale across major recommendation systems:

- **YouTube (Google, 2016)** — [Deep Neural Networks for YouTube Recommendations](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/): watch history IDs averaged into a fixed-width vector; averaging outperformed sum and component-wise max
- **Uber Eats (2022)** — [Two-Tower Embeddings](https://www.uber.com/blog/innovative-recommendation-applications-using-two-tower-embeddings/): ordered store IDs embedded and averaged ("BOW features"), reducing model size 20x vs raw eater_uuid embeddings
- **Snapchat (2023)** — [Embedding-Based Retrieval](https://eng.snap.com/embedding-based-retrieval): past engagement sequences processed with average pooling into fixed-width vectors

#### Standalone Validation Experiment

Before platform integration, the taste vector was validated via a standalone Vertex AI Custom Job (`scripts/test_taste_vector.py`) that bypassed the TFX pipeline — reading v4 BigQuery views directly, preprocessing in Python, and training a TFRS retrieval model with shared product embedding + masked averaging. The script has a local orchestrator (submits to Vertex AI) and an inner GPU runner (T4 in europe-west4). Results after 100 epochs:

| Metric | Baseline #162 (100 ep) | Taste Vector (100 ep) | Change |
|--------|------------------------|-----------------------|--------|
| Recall@5 | 0.0523 | **0.0718** | **+37.2%** |
| Recall@10 | 0.0809 | **0.1010** | **+24.9%** |

Top-K precision improved dramatically. Overfitting started around epoch 13 (best val loss), causing Recall@50/100 to degrade — early stopping would resolve this. **Verdict: taste vector validated, proceed with platform integration.**

#### Why Platform Integration Was Needed

Before the history feature type was added, the platform's code generators had a hard-coded three-type system (text, numeric, temporal) that silently ignored ARRAY columns. When experiment #168 attempted to include `purchase_history`, it was dropped at three points: `SmartDefaultsService` skipped ARRAY types, `PreprocessingFnGenerator._collect_all_features()` had no history bucket, and `TrainerModuleGenerator._collect_features_by_type()` had no history handling. The taste vector never reached the model — the pipeline analysis (see "Bug Fix: Taste Vector Near-Zero Impact Investigation" below) confirmed that exp 168's metrics were indistinguishable from the scalar-only baseline.

#### Integration

This feature integrates the taste vector into the platform as a 4th feature data type ("history") alongside text/numeric/temporal, so it works through the normal Experiments UI and Training pipeline workflow.

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

---

## Bug Fix: ARRAY Column Type Detection Broken in Dataset Wizard & Feature Config (2026-02-26)

### Problem

BigQuery ARRAY columns (e.g., `purchase_history` which is `ARRAY<INT64>`) were displayed with just their element type (`int`) in the schema builder and passed as bare `INT64` to the feature config step. This broke the "history" feature type auto-detection (which expects `bq_type` starting with `ARRAY`), making it impossible to create a taste vector feature through the UI.

### Root Cause

BigQuery's Python client returns `field.field_type = "INT64"` and `field.mode = "REPEATED"` as **separate attributes**, but multiple code paths only read `field_type` and ignored `mode`. This affected:

1. **`get_table_schema()`** — the root backend source for schema data, propagating bare types to the dataset wizard schema builder, preview service, and training pipeline fallback
2. **`get_schema_with_sample()`** — the feature config endpoint, which reads from `result.schema` independently and also missed REPEATED mode
3. **`SemanticTypeService`** — had no `'history'` semantic type, so ARRAY columns couldn't be classified even if the type was correct
4. **Snapshot stats query** — ran `COUNTIF`, `AVG(ARRAY_LENGTH(...))` on ARRAY columns, which could fail or produce misleading stats
5. **`formatBqType()` (model_configs.html)** — no ARRAY handling, fell through to default
6. **`getDataTypeFromBqType()` (model_experiments.html)** — missing the ARRAY → history mapping that `model_configs.html` already had

### Fix Applied

| File | Change |
|------|--------|
| `ml_platform/datasets/services.py:308` | `get_table_schema()` now emits `ARRAY<{field_type}>` for REPEATED fields |
| `ml_platform/datasets/services.py:4918-4984` | Snapshot stats: skip ARRAY columns from BQ query entirely, emit type-only entry in results |
| `ml_platform/configs/api.py:821` | Exclude ARRAY columns from integer cardinality computation (`COUNT(DISTINCT ...)` fails on arrays) |
| `ml_platform/configs/api.py:859` | `get_schema_with_sample()` emits `ARRAY<{field_type}>` for REPEATED fields |
| `ml_platform/configs/services.py` | Added `'history'` to `SEMANTIC_TYPES` dict; `get_type_options()` and `infer_semantic_type()` return history for ARRAY types |
| `templates/ml_platform/model_configs.html` | `formatBqType()` returns `'ARRAY'` for types starting with `ARRAY` |
| `templates/ml_platform/model_experiments.html` | `getDataTypeFromBqType()` returns `'history'` for ARRAY types |

The fix pattern (`f'ARRAY<{field_type}>' if mode == 'REPEATED' else field_type`) already existed at `services.py:489` in the snapshot stats results loop — it just wasn't applied at the source.

### Impact

Without this fix, the history feature type added in the previous commit was effectively unusable through the UI — the ARRAY type information was lost before reaching the feature config step, so auto-detection never triggered. Non-ARRAY columns are completely unaffected.

---

## Bug Fix: `tft.vocabulary()` Misuse in History Transform Code Generation (2026-02-26)

### Problem

Experiment `quick-tests/166` fails at the Transform step with:
```
AttributeError: 'str' object has no attribute 'dtype'
```
The generated `transform_module.py` passes a **string** to `tft.vocabulary()`:
```python
deferred_vocab_filename_tensor=tft.vocabulary('product_id_vocab'),  # BUG
```
`tft.vocabulary(x, ...)` expects a **tensor** as its first argument. There is no "lookup vocab by name" API — the string `'product_id_vocab'` is not a valid input.

### Root Cause

The text feature used `tft.compute_and_apply_vocabulary()` which creates the vocabulary internally and never exposes the deferred vocab filename tensor. The history feature had no way to reference it with the original code pattern. The `_generate_history_transforms()` method incorrectly assumed `tft.vocabulary(name_string)` would return a handle to an existing vocab.

### Fix Applied

| File | Change |
|------|--------|
| `ml_platform/configs/services.py` `generate()` | Compute `shared_cols` — the set of text column names referenced by enabled history features via `shared_with` |
| `ml_platform/configs/services.py` `_generate_text_transforms()` | For columns in `shared_cols`, split `compute_and_apply_vocabulary` into `tft.vocabulary()` (captures deferred vocab tensor into a variable) + `tft.apply_vocabulary()`. Non-shared text features keep the one-liner |
| `ml_platform/configs/services.py` `_generate_history_transforms()` | Replace `tft.vocabulary('{shared_with}_vocab')` with a direct variable reference `{shared_with}_vocab` |

**Generated code before (buggy):**
```python
outputs['product_id'] = tft.compute_and_apply_vocabulary(
    _densify(inputs['product_id'], b''),
    num_oov_buckets=NUM_OOV_BUCKETS,
    vocab_filename='product_id_vocab'
)
outputs['purchase_history'] = tft.apply_vocabulary(
    inputs['purchase_history'],
    deferred_vocab_filename_tensor=tft.vocabulary('product_id_vocab'),  # BUG: string arg
    num_oov_buckets=NUM_OOV_BUCKETS
)
```

**Generated code after (fixed):**
```python
product_id_vocab = tft.vocabulary(
    _densify(inputs['product_id'], b''),
    vocab_filename='product_id_vocab'
)
outputs['product_id'] = tft.apply_vocabulary(
    _densify(inputs['product_id'], b''),
    deferred_vocab_filename_tensor=product_id_vocab,
    num_oov_buckets=NUM_OOV_BUCKETS
)
outputs['purchase_history'] = tft.apply_vocabulary(
    inputs['purchase_history'],
    deferred_vocab_filename_tensor=product_id_vocab,  # FIXED: variable reference
    num_oov_buckets=NUM_OOV_BUCKETS
)
```

### Impact

All experiments using history features (purchase history taste vectors) failed at the Transform step. Non-history experiments were unaffected. After the fix, the preprocessing code for experiment `quick-tests/166` must be regenerated and the experiment rerun.

---

## Bug Fix: Dense-to-Sparse Conversion for History Features in Serve Functions (2026-02-26)

### Problem

Experiment `quick-tests/167` (with the previous `tft.vocabulary()` bug fixed) passes Transform but fails at the **Trainer** step during `tf.saved_model.save()` with:
```
ValueError: Tensor("history:0", shape=(None, 50), dtype=int64): Shapes (None, 2) and (None, 50) are incompatible
```

Training completes successfully (all epochs run). The failure happens when TensorFlow traces the `serve()` function for export.

### Root Cause

The TFT saved transform model is traced during the Transform step with **SparseTensor** inputs (BigQueryExampleGen encodes ARRAY/REPEATED columns as VarLenFeature → SparseTensor). The serve function passes `history` as a dense `[None, 50]` tensor into `self.tft_layer(raw_features)`, causing a shape mismatch. The shape `(None, 2)` in the error is the SparseTensor's internal `indices` shape, not `(None, 50)`.

The data flow during **training** is:
```
BigQueryExampleGen → SparseTensor → Transform(SparseTensor) → SparseTensor → _input_fn pads to dense [batch, max_len] → model
```

The data flow during **serving** must match:
```
JSON dense [batch, max_len] → convert to SparseTensor → tft_layer(SparseTensor) → SparseTensor → pad to dense [batch, max_len] → model
```

Additionally, after `tft_layer` returns, the history column is still a SparseTensor but the model's tower expects a dense `[batch, max_len]` tensor (same as during training, where `_input_fn` pads SparseTensors to dense).

### Fix Applied

| File | Change |
|------|--------|
| `ml_platform/configs/services.py` `_generate_serve_history_padding()` | New static method: generates post-`tft_layer` padding code (SparseTensor → dense via `tf.sparse.to_dense()` + slice + `tf.pad()`) for a list of history features |
| `ml_platform/configs/services.py` `_generate_raw_tensor_signature()` | Returns 4th tuple element `history_features` (list of `(col_name, max_length)` pairs); history columns emit `tf.sparse.from_dense(col)` instead of bare `col` |
| `ml_platform/configs/services.py` `_generate_raw_tensor_signature_ranking()` | Same 4th return value change |
| `ml_platform/configs/services.py` `_generate_brute_force_serve_fn()` | Injects history padding block after `tft_layer` |
| `ml_platform/configs/services.py` `_generate_scann_serve_fn()` | Injects history padding block after `tft_layer` (both ScaNN and brute-force fallback) |
| `ml_platform/configs/services.py` `_generate_serve_fn_ranking()` | Injects history padding block after `tft_layer` |
| `ml_platform/configs/services.py` `_generate_serve_fn_multitask()` | Injects history padding block after `tft_layer` in both `serve()` and `serve_ranking()` |

**Generated code before (buggy):**
```python
    raw_features = {
        'customer_id': tf.expand_dims(customer_id, -1),
        'history': history,                          # dense [batch, 50] — SHAPE MISMATCH
    }
    transformed_features = self.tft_layer(raw_features)
    query_embeddings = self.retrieval_model.query_tower(transformed_features)
```

**Generated code after (fixed):**
```python
    raw_features = {
        'customer_id': tf.expand_dims(customer_id, -1),
        'history': tf.sparse.from_dense(history),    # convert to SparseTensor for TFT
    }
    transformed_features = self.tft_layer(raw_features)
    # Pad history feature back to dense [batch, 50]
    if isinstance(transformed_features['history'], tf.SparseTensor):
        _dense = tf.sparse.to_dense(transformed_features['history'], default_value=0)
        _dense = _dense[:, :50]
        _pad = tf.maximum(50 - tf.shape(_dense)[1], 0)
        transformed_features['history'] = tf.pad(_dense, [[0, 0], [0, _pad]])
    query_embeddings = self.retrieval_model.query_tower(transformed_features)
```

### Impact

All experiments using history features failed at the Trainer step during model export (`tf.saved_model.save()`). Training itself completed successfully — only the serve function tracing failed. Non-history experiments were unaffected. After the fix, experiment `quick-tests/167` must be rerun.

---

## Bug Fix: Taste Vector Near-Zero Impact Investigation (2026-02-27)

### Problem

Experiment 168 (`feat_retr_v6` + `mod_retr_v6`) added the 32D taste vector to the retrieval model. Compared to the scalar-only baseline (exp 162), the improvement was negligible:

| Experiment | ID | Config | R@5 | R@10 | R@50 | R@100 |
|---|---|---|---|---|---|---|
| `retr_v3` | 147 | Baseline (no scalars, no history) | 3.8% | 6.7% | 21.9% | 32.8% |
| `retv_v5` | 162 | + scalar context features | 5.2% | 8.1% | 22.0% | 33.1% |
| `exp_retv_v6` | 168 | + scalar context + history vector | 5.4% | 9.3% | 23.3% | 34.2% |

The standalone taste vector experiment showed +37% R@5. The pipeline version showed +0.2pp — something was wrong.

### Investigation

End-to-end audit of exp 168's data pipeline: Django DB configs → GCS artifacts (transform/trainer modules, TFRecords, schema, vocabulary) → raw and transformed TFRecord scans (74,346 train + 4,511 test examples) → code comparison (DB vs GCS).

### Bugs Found

**Bug 1: Label Leakage in SQL View (Primary Cause)**

The `customer_purchase_history` CTE in `create_ternopil_train_v4_view.sql` aggregated history at the customer level, then joined back to the same `train_data`. For 98.7% of training rows, the `purchase_history` array already contained the target product_id. With ~24 products in the average, the target contributed only ~4.2% of the taste vector — a signal too diluted for the model to learn from when the 64D customer_id embedding already encodes per-customer preferences directly. Gradient descent allocated capacity to the stronger signal.

- **Fix (retrieval views)**: Per-(customer, target_product) history via self-join excluding target
- **Fix (ranking views)**: Inline `ARRAY(SELECT p FROM UNNEST(ch.purchase_history) AS p WHERE p != deduped.product_id)` for positives; negatives unchanged (no leakage by definition)
- **Test views**: No fix needed — history from training period appearing for test-day targets is legitimate signal

**Bug 2: Padding/Masking Collision at Vocab Index 0**

Generated trainer code used `default_value=0` for padding and `history_ids != 0` for masking. But vocab index 0 is the most popular product (`378243001001`). In 42% of training examples (31,371/74,346), this product's embedding was silently zeroed out in the taste vector.

**Bug 3: Stale Transform Code in Database**

Pipeline submission called `generate()` instead of `generate_and_save()`, so the DB `generated_transform_code` field retained stale code with `tft.vocabulary('product_id_vocab')` (string arg — incorrect). The GCS-deployed code was correct. No impact on exp 168 results but would fail if DB code reused.

**Bug 4: buyer_feature_details Skips History Features**

`_extract_feature_details()` had no code path for `transforms.history`. Feature count was correct (7) but details showed only 6 entries — history (32D) was missing. Display-only.

### Files Changed

| File | Bug | Change |
|---|---|---|
| `sql/create_ternopil_train_v4_view.sql` | 1 | Per-target history CTE excluding target product |
| `sql/create_ternopil_prob_train_v4_view.sql` | 1 | Inline array filter for positives |
| `ml_platform/configs/services.py` | 2 | Padding default_value, mask condition (5 edits) — see padding fix chain below |
| `ml_platform/experiments/services.py` | 3, 4 | `generate_and_save()` + history feature details |
| `ml_platform/training/services.py` | 3 | `generate_and_save()` |
| `ml_platform/management/commands/backfill_hyperparameter_fields.py` | 4 | History feature details |

### Cross-References

- Bug 2 padding fix chain: see "Bug Fix: History Padding Index Out of Range" below
- Existing individual bug fix sections above cover the code generation bugs (ARRAY detection, `tft.vocabulary()` misuse, dense-to-sparse conversion)
- Label leakage fix verified by commit `9be194f` (Exclude target product from purchase_history in test v4 views)

---

## Bug Fix: History Padding Index Out of Range (2026-02-27)

### Problem

The Bug 2 fix (above) changed history padding from `0` to `-1` to avoid masking out vocab index 0. However, `tf.keras.layers.Embedding` does not accept negative indices:

```
InvalidArgumentError: indices[...] = -1 is not in [0, vocab_size)
```

This crashed the Trainer step in QT #169 (`feat_retr_v6` + `mod_retr_v6`).

### Fix

Use a **dedicated padding index** = `vocab_size + NUM_OOV_BUCKETS` (one beyond the last valid OOV index). Increase the embedding `input_dim` by 1 to accommodate it. The padding row's embedding exists in the weight matrix but gets zeroed out by the mask.

**6 change locations in `ml_platform/configs/services.py`:**

| # | Location | Change |
|---|----------|--------|
| 1 | `_generate_shared_embedding_code()` | `input_dim` +1; store `self.history_pad_index` on model |
| 2 | `_generate_buyer_model()` | `self.history_pad_index = shared_product_embedding.input_dim - 1`; mask: `!= self.history_pad_index` |
| 3 | `_generate_product_model()` | Same as BuyerModel |
| 4 | `_generate_history_padding_code()` | Compute `_history_pad_index` from `tf_transform_output`; use instead of `-1` |
| 5 | `_generate_serve_history_padding()` | `-1` → `self.history_pad_index` |
| 6 | All 4 serving model `__init__` methods | Add `self.history_pad_index` conditional on history features |

### Padding Fix Chain (Full History)

| Step | Padding Value | Mask Condition | Embedding input_dim | Status |
|---|---|---|---|---|
| Original | `0` | `!= 0` | `vocab_size + NUM_OOV_BUCKETS` | Masks out vocab index 0 (most popular product) |
| First fix | `-1` | `>= 0` | `vocab_size + NUM_OOV_BUCKETS` | Crashes: `-1` not in `[0, input_dim)` |
| **Final fix** | `vocab_size + NUM_OOV_BUCKETS` | `!= self.history_pad_index` | `vocab_size + NUM_OOV_BUCKETS + 1` | **Correct**: valid index, dedicated padding row, masked out |

### Verification

QT #169 (before fix): `JOB_STATE_FAILED` — `InvalidArgumentError: indices[...] = -1`
QT #170 (after fix): `JOB_STATE_SUCCEEDED` — R@5=0.0208, R@10=0.0330, R@50=0.1270, R@100=0.2218

---

## Bug Fix: Missing 'yearly' Cyclical Dimension in Dimension Calculators (2026-02-27)

### Problem

When a user enables the "Yearly" cyclical encoding checkbox in the Feature Engineering UI, the dimension calculation in 4 locations **undercounts by 2** (the sin/cos pair for yearly). The UI displays an incorrect tensor dimension preview, and downstream architecture sizing may be wrong.

The actual TFX code generation is correct — yearly sin/cos encoding IS generated properly. Only the dimension calculators are affected.

### Root Cause

The system has two config formats for cyclical encoding that evolved over time:

| Format | Key | Origin |
|--------|-----|--------|
| Old | `cyclical.annual` | Default config templates, early features |
| New | `cyclical.enabled` + `cyclical.yearly` | UI (model_configs.html) saves this format |

The code generation in `PreprocessingFnGenerator._generate_timestamp_transforms()` handles both keys correctly (checks `yearly` then falls back to `annual`). However, four dimension calculation paths were inconsistent:

| File | Line | Checked keys | Bug |
|------|------|-------------|-----|
| `configs/services.py` `_get_feature_dims()` (new format branch) | 439 | `['quarterly', 'monthly', 'weekly', 'daily']` | Missing `'yearly'` |
| `models.py` `FeatureConfig.get_feature_dim()` | 1565 | `['annual', ...]` | Missing `'yearly'` |
| `experiments/services.py` `ExperimentService` dimension calc | 454 | `['annual', ...]` | Missing `'yearly'` |
| `management/commands/backfill_hyperparameter_fields.py` | 380 | `['annual', ...]` | Missing `'yearly'` |

Since the UI saves configs with key `'yearly'` (not `'annual'`), any UI-created config with yearly enabled would have its cyclical dimensions undercounted by 2 in all four calculators.

### Fix Applied

| File | Change |
|------|--------|
| `ml_platform/configs/services.py:439` | Added `'yearly'` to new-format list: `['yearly', 'quarterly', 'monthly', 'weekly', 'daily']` |
| `ml_platform/models.py:1565` | Added `'yearly'` alongside `'annual'`: `['annual', 'yearly', 'quarterly', ...]` |
| `ml_platform/experiments/services.py:454` | Added `'yearly'` alongside `'annual'`: `['annual', 'yearly', 'quarterly', ...]` |
| `ml_platform/management/commands/backfill_hyperparameter_fields.py:380` | Added `'yearly'` alongside `'annual'`: `['annual', 'yearly', 'quarterly', ...]` |

Both `'annual'` and `'yearly'` are now recognized in all paths, ensuring backward compatibility with old configs while correctly handling new UI configs.

### Impact

Any feature config with yearly cyclical encoding enabled (created via the UI) would show 2 fewer dimensions in the tensor preview and hyperparameter extraction. The actual generated TFX code was unaffected — training produced correct results. After the fix, dimension displays are accurate for all cyclical combinations.

---

## Implementation Status

### Completed Features

- [x] Quick Test chapter with experiment cards
- [x] 2-step wizard (Select Configs → Training Params)
- [x] Model type selection (Retrieval/Ranking/Multitask)
- [x] Experiment comparison (2 experiments, 6 accordion sections)
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
- [x] **AUC-ROC metrics** for binary-label ranking models (auto-detected) (2026-02-24)
- [x] **History feature type** (purchase history taste vector, shared embedding + masked averaging) (2026-02-26)
- [x] **Split strategies** — Random, Time Holdout, Strict Temporal with rolling window
- [x] **6-filter bar** — Status, Model Type, Dataset, Features, Model + debounced search

### Future Enhancements

- [ ] Early stopping support (critical for taste vector models that overfit after ~13 epochs)
- [ ] Co-purchase vector — product-side analog of the buyer taste vector. For each product, collect the top-N most frequently co-purchased products, embed through the same shared product embedding table, and average into a fixed-width vector encoding the product's "purchase context" (e.g. daily staples vs premium basket). Same ARRAY column pattern, same shared embedding, same averaging — zero new code patterns needed. Adds +32D to the product tower
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
- [improve_model.md](improve_model.md) - Retrieval model quality improvement guide
