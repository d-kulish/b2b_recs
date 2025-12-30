# Phase: Experiments Domain

## Document Purpose
This document provides **high-level specifications** for the Experiments domain. For detailed implementation instructions, see:

👉 **[phase_experiments_implementation.md](phase_experiments_implementation.md)** - Complete implementation guide with code examples

**Last Updated**: 2025-12-25

---

## ⚠️ IMPORTANT: Implementation Guide

**Before implementing, read the detailed implementation guide:**

| Document | Purpose |
|----------|---------|
| **[phase_experiments_implementation.md](phase_experiments_implementation.md)** | Step-by-step implementation with code |
| This document | High-level concepts and UI mockups |

---

## Key Technical Decisions (2024-12-14)

| Decision | Choice |
|----------|--------|
| Pipeline Framework | **Native TFX SDK** (NOT KFP v2 placeholder) |
| Data Flow | BigQuery → TFRecords → TFX |
| Container Image | `gcr.io/tfx-oss-public/tfx:latest` |
| TensorBoard | **NOT USED** (too expensive) - custom visualizations |
| Pipeline Compilation | On-demand at submission time |
| Sampling | TFX-level (ExampleGen/Transform) |
| Train/Val Split | 3 options: random (hash-based), time_holdout (date-filtered + hash), strict_time (true temporal) |
| Model Type (Phase 1) | Retrieval only |

---

## Recent Updates (December 2025)

### Cancel Button Bug Fix for Compile Phase (2025-12-30)

**Bug Fix:** Cancel button now properly cancels experiments during the Compile (Cloud Build) phase.

#### The Problem

The Cancel button only worked when experiments were in the RUNNING phase (Vertex AI pipeline execution). When cancelling during the SUBMITTING phase (Compile), the following occurred:

1. **Database updated** - Status changed to "cancelled" ✓
2. **Cloud Build continued** - Compilation kept running ✗
3. **Pipeline submitted** - Vertex AI pipeline was submitted after Cloud Build completed ✗
4. **Resources wasted** - Orphaned pipeline consumed compute resources ✗

**Root Cause:** The `cancel_quick_test()` method in `services.py` only handled Vertex AI pipeline cancellation. When `vertex_pipeline_job_name` was empty (during Compile phase), it returned early without cancelling Cloud Build.

#### Two-Phase Execution Architecture

```
SUBMITTING ─── Cloud Build Phase (1-2 min)
    │           └─ Compiles TFX pipeline, submits to Vertex AI
    │           └─ cloud_build_id stored, vertex_pipeline_job_name NOT YET available
    ▼
RUNNING ────── Vertex AI Pipeline Phase (5-15 min)
    │           └─ Examples → Stats → Schema → Transform → Train
    │           └─ vertex_pipeline_job_name now available
    ▼
COMPLETED/FAILED/CANCELLED
```

#### The Fix

Updated `cancel_quick_test()` in `ml_platform/experiments/services.py` to handle both phases:

| Phase | Condition | Action |
|-------|-----------|--------|
| Compile | `cloud_build_id` exists, no `vertex_pipeline_job_name` | Cancel via `cloudbuild_v1.CloudBuildClient().cancel_build()` |
| Pipeline | `vertex_pipeline_job_name` exists | Cancel via `aiplatform.PipelineJob.cancel()` |
| Race condition | Cloud Build completes during cancel | Check for result, then cancel Vertex pipeline if submitted |

**Key Changes:**
- Added Cloud Build cancellation using `google.cloud.devtools.cloudbuild_v1`
- Handle race condition where Cloud Build completes between cancel request and API call
- Comprehensive logging for debugging which phase was cancelled

---

### MLflow Training Metrics Enhancement (2025-12-25)

**Major Enhancement:** Expanded training metrics collection and visualization in the Training tab.

#### The Problem

1. **Recall metrics not logged** - Bug in `_evaluate_recall_on_test_set` caused `TypeError: unhashable type: 'numpy.ndarray'` when building product ID lookup dictionary
2. **Limited loss visualization** - Only training and validation loss shown, not regularization or total loss
3. **No weight monitoring** - No visibility into weight norms or distributions during training
4. **Gradient norms missing** - Couldn't detect vanishing/exploding gradients

#### Changes Made

**1. Fixed Recall Evaluation Bug**

The `_precompute_candidate_embeddings` and `_evaluate_recall_on_test_set` functions now properly convert numpy arrays to Python scalars:

```python
# Fixed: Handle numpy arrays with extra dimensions and convert to Python scalars
if len(batch_ids.shape) > 1:
    batch_ids = batch_ids.flatten()
for b in batch_ids:
    if hasattr(b, 'decode'):
        converted_ids.append(b.decode())  # Bytes -> string
    elif hasattr(b, 'item'):
        converted_ids.append(b.item())    # Numpy scalar -> Python scalar
    else:
        converted_ids.append(b)           # Already Python type
```

**2. Added Training Callbacks**

Two new Keras callbacks log weight statistics to MLflow:

| Callback | Metrics Logged | Purpose |
|----------|---------------|---------|
| `WeightNormCallback` | `weight_norm`, `query_weight_norm`, `candidate_weight_norm` | Detect weight explosion/collapse |
| `WeightStatsCallback` | `{tower}_weights_mean/std/min/max` | Monitor weight distributions per tower |

**Tower Categorization Logic:**
- Query tower: variables with `'query'` OR `'buyer'` in name
- Candidate tower: variables with `'candidate'` OR `'product'` in name

**3. Enhanced MLflow Service**

`get_training_history()` now returns:

```python
{
    'loss': {
        'train': [...],           # Per-epoch
        'val': [...],
        'regularization': [...],
        'val_regularization': [...],
        'total': [...],
        'val_total': [...]
    },
    'gradient': {
        'total': [...],           # Per-epoch weight norms
        'query': [...],
        'candidate': [...]
    },
    'weight_stats': {
        'query': {'mean': [...], 'std': [...], 'min': [...], 'max': [...]},
        'candidate': {'mean': [...], 'std': [...], 'min': [...], 'max': [...]}
    },
    'final_metrics': {
        'test_loss': ...,
        'test_recall_at_10': ...,
        'test_recall_at_50': ...,
        'test_recall_at_100': ...,
        ...
    }
}
```

**4. Updated Training Tab UI**

New 4-chart layout with final metrics table:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TRAINING PROGRESS                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────┐  ┌─────────────────────────────────────┐│
│ │ Loss (Combined)                 │  │ Recall Metrics (Bar Chart)          ││
│ │ - Training Loss (blue)          │  │ - Recall@10, @50, @100              ││
│ │ - Validation Loss (orange)      │  │ - Shows final test values           ││
│ │ - Reg Loss (grey, dashed)       │  │                                     ││
│ │ - Total Loss (purple, dashed)   │  │                                     ││
│ └─────────────────────────────────┘  └─────────────────────────────────────┘│
│ ┌─────────────────────────────────┐  ┌─────────────────────────────────────┐│
│ │ Weight Norms (L2)               │  │ Weight Distribution                 ││
│ │ - Total (grey, dashed)          │  │ - Tower selector dropdown           ││
│ │ - Query Tower (blue)            │  │ - Mean, Std, Min, Max lines         ││
│ │ - Candidate Tower (green)       │  │                                     ││
│ └─────────────────────────────────┘  └─────────────────────────────────────┘│
│ FINAL METRICS                                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Test Metrics          │ Final Training Metrics                          │ │
│ │ - Test Loss           │ - Final Training Loss                           │ │
│ │ - Recall@10/50/100    │ - Final Val Loss                                │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Chart Features:**
- **Loss chart**: Toggle legend to show/hide individual loss components
- **Recall chart**: Bar chart (not line) since recall is only calculated at end
- **Weight norms**: Shows training stability over epochs
- **Weight distribution**: Dropdown to switch between Query and Candidate tower stats

#### Files Modified

| File | Change |
|------|--------|
| `ml_platform/configs/services.py` | Fixed recall bug, added `WeightNormCallback`, added `WeightStatsCallback`, registered callbacks in run_fn |
| `ml_platform/experiments/mlflow_service.py` | Updated `get_training_history()` to include all loss variants, weight norms, weight stats |
| `templates/ml_platform/model_experiments.html` | Added 4 new charts (Loss enhanced, Recall bar, Weight norms, Weight distribution), Final metrics table, CSS for new components |

#### Backward Compatibility

- **Existing experiments**: Will show placeholders ("data not available") for new metrics (weight norms, weight stats)
- **New experiments**: Will collect and display all new metrics

#### Bug Fixes (2025-12-25)

Two bugs were discovered and fixed during initial testing:

**1. Missing numpy import**
```
NameError: name 'np' is not defined
File "trainer_module.py", line 833, in on_epoch_end
    _mlflow_client.log_metric('weight_norm', float(np.sqrt(total_norm_sq)), step=epoch)
```
**Fix:** Added `import numpy as np` to `_generate_imports()` method.

**2. Dict literal syntax in generated code**
```
TypeError: unhashable type: 'dict'
File "trainer_module.py", line 852, in on_epoch_end
    tower_stats = {{'query': [], 'candidate': []}}
```
**Cause:** Double braces `{{}}` in Python string templates escape to single braces, but the generated code `{{'query': []}}` is interpreted as a **set literal** containing a dict (not a dict literal). Sets require hashable elements, but dicts are unhashable.

**Fix:** Changed to `dict()` constructor and string concatenation:
```python
# Before (broken)
tower_stats = {{'query': [], 'candidate': []}}
_mlflow_client.log_metric(f'{{tower}}_weights_mean', ...)

# After (fixed)
tower_stats = dict(query=[], candidate=[])
_mlflow_client.log_metric(tower + '_weights_mean', ...)
```

---

### Compare Feature Redesign (2025-12-24)

**Major Enhancement:** Redesigned experiment comparison with two-step modal flow and comprehensive grouped comparison tables.

#### The Problem

The old compare feature had several UX issues:
1. Compare button was hidden until experiments were checkbox-selected from cards
2. Users couldn't see all available experiments at once
3. Comparison table lacked detail (no feature lists, no dataset info, no visual indicators)

#### The Solution

**1. Always-Visible Compare Button**
- Compare button in Quick Test chapter header is now always visible
- Clicking opens the Selection Modal (instead of requiring pre-selection)

**2. Selection Modal**
```
┌─────────────────────────────────────────────────────────┐
│ Select Experiments to Compare                      [X]  │
├─────────────────────────────────────────────────────────┤
│  Select 2-5 experiments                    3 selected   │
│  ┌─────────────────────────────────────────────────────┐│
│  │ ☑ Exp #12 • Testing Q4 feat...  completed   47.3%  ││
│  │ ☑ Exp #11 • Baseline with...    completed   45.1%  ││
│  │ ☑ Exp #9  • Failed debug        failed      —      ││
│  │ ☐ Exp #8  • Another test        completed   43.2%  ││
│  └─────────────────────────────────────────────────────┘│
│  [Clear All]                    [Cancel]  [Compare (3)] │
└─────────────────────────────────────────────────────────┘
```

- Scrollable list of all experiments (completed, failed, cancelled)
- Each row shows: experiment number, name, description (30 chars), status badge, Recall@100
- Checkbox selection with 5-experiment limit
- Selected rows get yellow highlight
- Rows disabled (greyed out) when 5 already selected

**3. Enhanced Comparison Modal**
```
│ DATASET                                                 │
│ Name              │ Q4 Data    ≡ │ Q4 Data      │ Q4 Data    │
│ Rows              │ 1.2M       ≡ │ 1.2M         │ 1.2M       │
│ FEATURE CONFIG                                          │
│ Name              │ Q4 v2      ≠ │ Q3 v1        │ Q3 v1      │
│ Buyer Features    │ user_id(64d) │ user_id(32d) │ user_id(32d)│
│ RESULTS                                                 │
│ Recall@100        │ 47.3% ★     │ 45.1%        │ —          │
```

- **Grouped sections**: Results, Training Parameters, Sampling, Dataset, Feature Config, Model Config
- **Row indicators**: ≡ (identical values across all), ≠ (values differ)
- **Best value highlighting**: ★ with green color for best metrics
- **Feature lists**: Shows actual features like "user_id(64d), city(16d)" instead of just counts
- **Cross features**: Formatted as "user_id×city(16d)"
- **Tower layers**: Formatted as "256→128→64"

#### New API Endpoint

**GET /api/experiments/selectable/**

Returns experiments available for comparison (excludes running/submitting/pending):

```json
{
  "success": true,
  "experiments": [
    {
      "id": 123,
      "experiment_number": 45,
      "display_name": "Exp #45",
      "experiment_name": "Testing Q4 features",
      "experiment_description_short": "First 50 chars of desc...",
      "status": "completed",
      "recall_at_100": 0.473,
      "feature_config_name": "Q4 v2",
      "model_config_name": "Standard",
      "created_at": "2024-12-23T10:30:00Z"
    }
  ],
  "count": 25
}
```

#### Enhanced Compare Response

**POST /api/experiments/compare/** now returns comprehensive data:

```json
{
  "success": true,
  "comparison": {
    "experiments": [
      {
        "id": 123,
        "display_name": "Exp #45",
        "status": "completed",
        "dataset": { "name": "Q4 Data", "row_count": 1200000, ... },
        "feature_config": {
          "name": "Q4 v2",
          "buyer_features": "user_id(64d), city(16d)",
          "buyer_tensor_dim": 128,
          "buyer_crosses": "user_id×city(16d)",
          ...
        },
        "model_config": { "name": "Standard", "tower_layers": "256→128→64", ... },
        "sampling": { "data_sample_percent": 25, "split_strategy": "random", ... },
        "training": { "epochs": 10, "batch_size": 4096, ... },
        "results": { "recall_at_100": 0.473, "loss": 0.034, ... }
      }
    ]
  }
}
```

#### Files Modified

| File | Change |
|------|--------|
| `ml_platform/experiments/api.py` | Added `selectable_experiments()`, enhanced `compare_experiments()`, added helper functions `_format_feature_list()`, `_format_crosses_list()`, `_format_tower_layers()` |
| `ml_platform/experiments/urls.py` | Added route for `/api/experiments/selectable/` |
| `templates/ml_platform/model_experiments.html` | New Selection Modal HTML, new CSS styles, new JavaScript functions, removed card checkboxes, Compare button always visible |

---

### Experiments Dashboard Chapter - MLflow Integration (2025-12-23)

**Major Feature:** Added complete Experiments Dashboard chapter to `model_experiments.html` for MLflow-based experiment analysis.

**New UI Components:**
1. **Experiments Dashboard Chapter** (blue icon, after Quick Test chapter)
   - Summary Dashboard: 4 stat cards (Total, Completed, Best R@100, Avg R@100)
   - Leaderboard Table: Sortable by metric, clickable rows open View modal
   - Configuration Heatmap: Chart.js grouped bar chart showing metrics by config combinations

2. **Compare Feature** (in Quick Test chapter) - **Redesigned 2025-12-24**
   - **Always-visible Compare button** (no longer hidden until selection)
   - **Two-step modal flow**: Selection Modal → Comparison Modal
   - **Selection Modal**: Scrollable list of all experiments (completed/failed/cancelled)
     - Shows: Exp #, name, description (30 chars), status badge, Recall@100
     - Select 2-5 experiments via checkboxes
     - "Clear All" and "Compare (N)" buttons
   - **Comparison Modal**: Grouped comparison table with visual indicators
     - Sections: Results, Training Parameters, Sampling, Dataset, Feature Config, Model Config
     - Row indicators: ≡ (identical across all), ≠ (values differ)
     - Best metrics highlighted with ★ (green)

3. **Training Tab** (in View modal)
   - Per-epoch loss charts (training + validation)
   - Per-epoch recall charts (R@10, R@50, R@100)
   - Chart.js visualizations with interactive tooltips

**New API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/experiments/dashboard-stats/` | GET | Summary statistics |
| `/api/experiments/heatmap/?metric=recall_at_100` | GET | Config combination matrix |
| `/api/experiments/leaderboard/?metric=recall_at_100` | GET | Ranked experiments |
| `/api/experiments/selectable/` | GET | List experiments for comparison selection (2025-12-24) |
| `/api/experiments/compare/` | POST | Multi-experiment comparison (enhanced 2025-12-24) |
| `/api/quick-tests/<id>/training-history/` | GET | Per-epoch MLflow metrics |

**Files Modified:**
- `templates/ml_platform/model_experiments.html` - Dashboard chapter HTML, CSS, JavaScript
- `ml_platform/experiments/api.py` - Added 4 new endpoints
- `ml_platform/experiments/urls.py` - Added URL routes

**See:** [`phase_mlflow_integration.md`](phase_mlflow_integration.md) for full MLflow integration details.

### MLflow Trainer Integration Fix (2025-12-24)

**Critical Fix:** Resolved 2-day issue where Vertex AI Trainer failed to communicate with MLflow server, resulting in experiments completing without any training metrics.

#### The Problem

The trainer component running on Vertex AI could not reliably send metrics to the MLflow server on Cloud Run. Experiments would complete successfully (model trained, metrics.json written), but the MLflow training history was empty. This made it impossible to visualize per-epoch training curves in the UI.

**Root Cause Analysis:**

| Issue | Description | Impact |
|-------|-------------|--------|
| **Cold Start Timeout** | MLflow server (Cloud Run, min-instances=0) takes 12-30s to cold start. Trainer used 10s timeout. | First request always failed |
| **Silent Failure** | Trainer caught MLflow exceptions, logged warning, set `_mlflow_client = None`, and continued training | Training succeeded but no metrics logged |
| **No Validation** | Trainer didn't verify MLflow was ready before starting training | Wasted hour-long experiments |
| **Cascading Failure** | When `set_experiment()` timed out, `experiment_id = None`, causing `runs/create` to return HTTP 400 | All subsequent MLflow calls failed |

**Evidence from Failed Experiment (qt-47):**
```
13:47:56 - MLflow: Got identity token via google-auth
13:48:26 - MLflow set_experiment error: The read operation timed out  ← 10s timeout expired
13:48:29 - MLflow API error (runs/create): HTTP 400 - Bad Request    ← No experiment_id!
13:48:29 - MLflow run started: None                                   ← run_id = None
```

Server-side (MLflow Cloud Run) responded 2 seconds AFTER client timeout:
```
15:48:16.786 - GET experiments/get-by-name returned 404 in 12.2s
15:48:26.222 - Gunicorn started (10 seconds after cold start)
```

#### The Fix

**1. Added `wait_for_ready()` method to MLflowRestClient**

The trainer now explicitly waits for MLflow server to be ready before attempting any operations:

```python
def wait_for_ready(self, max_wait_seconds=120):
    """Wait for MLflow server to be ready (handles cold starts)."""
    # Pings /health endpoint with exponential backoff
    # 60s timeout on first attempt, 30s after
    # Logs detailed progress for debugging
    # Raises RuntimeError if server not ready after 120s
```

**2. Made MLflow Mandatory**

Instead of silently continuing when MLflow fails, training now fails fast:

```python
# Before (broken):
try:
    _mlflow_client.set_experiment(...)
except Exception as e:
    logging.warning(f"MLflow failed: {e}")
    _mlflow_client = None  # Training continues without MLflow!

# After (fixed):
_mlflow_client.wait_for_ready(max_wait_seconds=120)
experiment_id = _mlflow_client.set_experiment(...)
if not experiment_id:
    raise RuntimeError("Failed to create experiment. Training cannot proceed.")
```

**3. Added Diagnostic Artifact (`mlflow_status.json`)**

Trainer writes status to GCS at each stage so Django can diagnose failures:

```json
{
  "status": "ready",
  "stage": "initialized",
  "experiment_id": "5",
  "run_id": "1193c2eba3aa4b86b21390ae67cde4de",
  "message": "MLflow fully initialized, training may proceed"
}
```

**4. Added Comprehensive Logging**

Trainer now logs exactly what's happening during MLflow connection:

```
--------------------------------------------------
MLFLOW CONNECTION: Starting server health check
  Server URL: https://mlflow-server-xxx.run.app
  Max wait time: 120s
--------------------------------------------------
MLFLOW CONNECTION: Attempt 1
  Elapsed: 0.0s | Remaining: 120.0s
  Getting authentication token...
  Auth token obtained: True
  Sending health check request (timeout=60s)...
  TIMEOUT - Server may be experiencing cold start
  Waiting 5s before next attempt...
MLFLOW CONNECTION: Attempt 2
  ...
  Response received: HTTP 200
  Request time: 15.32s
--------------------------------------------------
MLFLOW CONNECTION: SUCCESS after 20.3s (2 attempts)
--------------------------------------------------
```

**5. Added MLflow Server Request Logging**

Updated `mlflow_server/Dockerfile` to log all requests with timing:

```dockerfile
CMD mlflow server \
    --gunicorn-opts "--access-logfile - --access-logformat '%(t)s %(h)s %(m)s %(U)s %(s)s %(D)sms' --timeout 120"
```

**6. Created Integration Test Script**

`tests/test_mlflow_integration.py` - Run before experiments to verify MLflow works:

```bash
python tests/test_mlflow_integration.py
```

#### Files Modified

| File | Change |
|------|--------|
| `ml_platform/configs/services.py` | Added `wait_for_ready()`, mandatory MLflow, diagnostic artifact, comprehensive logging |
| `ml_platform/experiments/artifact_service.py` | Added `get_mlflow_status()` to read diagnostics |
| `mlflow_server/Dockerfile` | Added Gunicorn access logging and 120s timeout |
| `tests/test_mlflow_integration.py` | New standalone verification script |

#### Verification

First successful experiment with fix (qt-48, Exp #17):

**Trainer Logs:**
- Health check: SUCCESS after cold start wait
- Experiment created: id=5
- Run started: id=1193c2eba3aa4b86b21390ae67cde4de
- All 60+ metrics logged (HTTP 200)

**MLflow Server Logs:**
```
16:22:40 | GET /health                  → 200 (1.4s)
16:22:41 | POST /experiments/create     → 200 (27s)
16:22:41 | POST /runs/create            → 200 (34s)
16:22:42 | POST /runs/log-parameter ×8  → 200
16:22:43 | POST /runs/set-tag ×4        → 200
16:22:49 | POST /runs/log-metric ×60+   → 200
16:23:17 | POST /runs/update            → 200
```

**UI Result:** Training curves now visible in View modal → Training tab.

---

### Known Issue: Cloud SQL Performance (2025-12-24)

**Problem:** MLflow server response times are very slow (15-30 seconds per request).

**Root Cause:** Cloud SQL instance is `db-f1-micro` (smallest tier):
- 0.6 GB RAM (barely enough for PostgreSQL)
- Shared vCPU (competes with other tenants)
- Each metric INSERT takes 15-30s due to resource starvation

**Impact:**
- Training with 60+ metric calls takes extra ~20 minutes just for MLflow logging
- Django UI is slow when loading training history
- Worker timeouts during cold start (13 workers crashed in first 12 minutes)

**MLflow Server Logs Showing Worker Crashes:**
```
15:49:35 | CRITICAL WORKER TIMEOUT (pid:11)
15:49:37 | Worker was sent SIGKILL! Perhaps out of memory?
... (repeated 13 times over 12 minutes)
```

**Recommendations:**

| Option | Change | Cost Impact | Expected Improvement |
|--------|--------|-------------|---------------------|
| **Upgrade Cloud SQL** | `db-f1-micro` → `db-g1-small` | +$18/month | 3-5x faster |
| **Batch Metrics** | Use `/runs/log-batch` endpoint | None | Fewer API calls |
| **Increase Workers** | 2 → 4 workers with threads | None | Better concurrency |

**Upgrade Command:**
```bash
gcloud sql instances patch b2b-recs-db --tier=db-g1-small --project=b2b-recs
```

**Status:** Not addressed yet. System is functional but slow.

---

### Pipeline DAG Static File Extraction (2025-12-22)

**Major Enhancement:** Extracted pipeline DAG visualization into reusable static files for use on future Full Training page.

**Files Created:**
- `static/css/pipeline_dag.css` - 293 lines of DAG styles
- `static/js/pipeline_dag.js` - ~500 lines of DAG rendering logic
- `templates/includes/_pipeline_dag.html` - Reusable HTML template

**Key Benefits:**
1. **Reusability** - Same visualization component for Quick Test and Full Training pages
2. **Maintainability** - Single source of truth for DAG styling and logic
3. **Django Best Practices** - Proper separation into static files and includes

**Usage:**
```django
{% include 'includes/_pipeline_dag.html' %}
<script src="{% static 'js/pipeline_dag.js' %}?v=1"></script>
```

**Note:** Template documentation uses HTML comments instead of Django comments because Django parses template tags even inside `{# #}` comments.

### Enhanced Pipeline DAG Visualization (2025-12-22)

**Major Enhancement:** Complete TFX pipeline visualization with 8 nodes and 11 artifacts.

**Key Features:**
1. **8-Node Pipeline** - Pipeline Compile, Examples Gen, Stats Gen, Schema Gen, Transform, Trainer, Evaluator, Pusher
2. **11 Artifacts Displayed** - Config, Examples, Statistics, Schema, Transform Graph, Transformed Examples, Model, ModelRun, Model Blessing, Evaluation, Model Endpoint
3. **Bezier Curve Connections** - SVG curves with 4 types (left, right, down-left, down-right)
4. **Visual Improvements** - White background with subtle dots, 264px node width, consistent spacing

**Node Renaming:**
- BigQueryExampleGen → Examples Gen
- StatisticsGen → Stats Gen
- SchemaGen → Schema Gen

### Schema Fix & TFDV Hybrid Visualization (2025-12-21)

**Problems Solved:**
1. **Schema Tab Bug** - Schema showed "UNKNOWN" for all feature types and "No" for all required fields
2. **TFDV Modal Display Issues** - TFDV iframe modal rendered incorrectly (cramped, font errors, nested iframes)

**Root Causes:**
1. Field name mismatch: Backend returned `feature_type`/`presence`, frontend expected `type`/`required`
2. TFDV uses Google Facets which creates triple-nested iframes and loads external dependencies from GitHub - impossible to style from parent page

**Solutions:**
1. **Schema Fix** - Updated `renderSchema()` to use correct field names:
   ```javascript
   <td>${f.feature_type || 'UNKNOWN'}</td>
   <td>${f.presence === 'required' ? 'Yes' : 'No'}</td>
   ```

2. **Hybrid TFDV Approach**:
   - **Removed** broken iframe modal (`#tfdvModal`, `showTfdvVisualization()`, `closeTfdvModal()`)
   - **Kept** working custom statistics display (histograms, top values, distribution bars)
   - **Added** "Open Full Report" button that opens TFDV in a new browser tab

**New Endpoint:**
- `GET /experiments/quick-tests/{id}/tfdv/` - Serves TFDV HTML as standalone page

**Key Changes:**
- Button changed from `<button onclick>` to `<a target="_blank">` (avoids popup blockers)
- TFDV HTML wrapped in proper page with header and styling
- Users can inspect full interactive TFDV report in a new tab

### TFDV Parser Cloud Run Service (2025-12-20)

**Problem Solved:** Data Insights tab was showing "Statistics not yet available" because Django (Python 3.12) couldn't import `tensorflow-metadata` due to protobuf version conflicts with google-cloud packages.

**Solution:** Created a dedicated Cloud Run microservice (`tfdv-parser`) running Python 3.10 with full TFX/TFDV stack.

**Key Features:**
1. **Microservice Architecture** - Separates TensorFlow dependencies from Django
2. **Rich Statistics Display** - Matches standard TFDV visualization format
   - Numeric: count, missing%, mean, std_dev, zeros%, min, median, max, histograms
   - Categorical: count, missing%, unique, top values, distribution charts
3. **TFDV HTML Visualization** - "View Full TFDV Report" button for complete TFDV interactive display
4. **Cloud Run Service-to-Service Auth** - IAM-based authentication between Django and tfdv-parser

**Service Details:**
- URL: `https://tfdv-parser-3dmqemfmxq-lm.a.run.app`
- Endpoints: `/parse/statistics`, `/parse/schema`, `/parse/statistics/html`

### Pipeline DAG Visualization with Component Logs (2025-12-20)

**Major Enhancement:**

1. **Vertical DAG Layout** - Visual pipeline representation matching Vertex AI Pipelines style
   - 4-row structure: Examples → Stats/Schema → Transform → Train
   - SVG bezier curve connections between components
   - Clickable components for log inspection

2. **Component Logs Panel** - View execution logs without GCP access
   - Last ~15 log entries per component
   - Refresh button to fetch latest logs
   - Logs fetched from Cloud Logging API via `resource.type="ml_job"`
   - 7-day lookback window for completed experiments

3. **Color-Coded Status** - Component status at a glance
   - Grey outline: Pending
   - Orange fill: Running (animated pulse)
   - Green fill: Completed successfully
   - Red fill: Failed

4. **Technical Implementation**
   - New endpoint: `GET /api/quick-tests/{id}/logs/{component}/`
   - Uses Google Cloud Logging Python client
   - Extracts task job IDs from Vertex AI pipeline task details
   - IAM requirement: `roles/logging.viewer` for service account

### View Modal Redesign with Tabs & Artifacts (2025-12-19)

**Major Redesign:**

1. **4-Tab Modal Layout** - Clean tabbed interface replacing cluttered boxes
   - **Overview Tab**: Status, configuration, training params, results
   - **Pipeline Tab**: 6-stage progress bar with stage-by-stage status
   - **Data Insights Tab**: Dataset statistics + inferred schema (lazy-loaded)
   - **Training Tab**: Training curves placeholder (for future MLflow integration)

2. **Error Pattern Matching** - Smart error classification with fix suggestions
   - 15+ patterns for common failures (memory, schema, BigQuery, timeout, etc.)
   - User-friendly error titles instead of raw stack traces
   - Actionable suggestions (e.g., "Try reducing batch_size or selecting larger hardware")

3. **Artifact Visibility** - View pipeline artifacts without GCP access
   - Statistics: Feature count, missing %, min/max/mean values
   - Schema: Feature names, types, required/optional
   - Lazy-loaded on tab switch (not on modal open)

4. **Hidden GCP Details** - Users only see Django app
   - Removed Vertex AI links (users can't access)
   - Removed GCS paths (users can't access)
   - All artifact data parsed and displayed in-app

### Experiment View Modal (2025-12-19)

**New Features:**

1. **Comprehensive View Modal** - Click experiment card or View button to see full details
   - Configuration: Feature Config, Model Config, Dataset
   - Training Parameters: Epochs, Batch Size, LR, Sample %, Split Strategy, Hardware
   - Pipeline Progress: 6-stage progress bar with real-time updates
   - Results: Loss, Recall@10/50/100, Vocabulary statistics
   - Error Section: Classified error with suggestions for failed experiments

2. **View Button** - Green button on experiment cards (above Cancel)
   - Opens the View modal with full experiment details
   - Alternative to clicking the card itself

3. **Real-time Updates** - View modal polls for updates on running experiments
   - Updates every 10 seconds
   - Auto-stops polling when experiment completes

4. **Styled Confirmation Dialog** - Cancel now uses styled modal instead of browser confirm()
   - Matches the design of confirmation dialogs elsewhere in the app

5. **Unified Backend Logging** - All experiment logs now show `Exp #N (id=X)` format
   - Makes it easier to correlate UI and server logs

### Experiment Cards Redesign & Cancel (2025-12-19)

**New Features:**

1. **Experiment Name & Description** - Optional fields to identify experiments
   - Name and Description fields in Step 1 of New Experiment wizard
   - Displayed on experiment cards (description truncated to 50 chars)

2. **Cancel Running Experiments** - Cancel button on every experiment card
   - Active (red) for running/submitting experiments
   - Disabled (light red) for completed/failed/cancelled
   - Calls `aiplatform.PipelineJob.cancel()` via Vertex AI SDK

3. **4-Column Card Layout** - Better information organization
   - Column 1 (30%): Exp #, Name, Description, Start/End times
   - Column 2 (20%): Dataset, Features, Model
   - Column 3 (30%): Training params (placeholder)
   - Column 4 (20%): View button, Cancel button

4. **Progress Bar Styling** - Tensor-breakdown-bar style
   - 24px height with labels inside
   - Gradient green colors for completed stages
   - Animated blue for running, red for failed

### Page Split from Configs Domain (2025-12-13)

**Major Change:** Quick Test functionality moved from Configs page to dedicated Experiments page.

**Why This Change:**
- `model_configs.html` exceeded 10,000 lines
- Running experiments and analyzing experiments deserve dedicated space
- Clear separation: Configs = Configure features/architecture, Experiments = Run and compare

**New UI Structure:**
- **Experiments Page** (`model_experiments.html`) now handles:
  - Feature Config + Model Config selection
  - Training parameters configuration
  - Quick Test execution and monitoring
  - Future: MLflow experiment comparison

**How Experiments Page Works:**
1. User selects Feature Config from dropdown
2. User selects Model Config from dropdown (determines architecture)
3. Training parameters (epochs, batch size, learning rate) auto-fill from ModelConfig
4. Click "Start Quick Test" to submit pipeline to Vertex AI
5. Monitor progress in real-time
6. View results when complete

---

## Overview

### Purpose
The Experiments domain allows users to:
1. **Run Quick Tests** to validate feature configurations on Vertex AI Pipelines
2. Compare Quick Test and Full Training results across configurations
3. Visualize metrics via heatmaps (Recall@k by configuration parameters)
4. Identify the best-performing configurations
5. Track experiment history and decisions

### Key Principle
**MLflow is for comparison and visualization, ML Metadata is for lineage.** Users use MLflow heatmaps to answer "which config is best?", while MLMD answers "what exact artifacts produced this model?".

### Terminology

| Term | Definition |
|------|------------|
| **Quick Test** | A lightweight training run (10% data, 2-3 epochs) for rapid validation |
| **Full Training** | Complete training run with all data and more epochs |
| **Feature Config** | Configuration of how columns are transformed (from Configs domain) |
| **Model Config** | Neural network architecture configuration (from Configs domain) |

### Tool Responsibilities

| Tool | Purpose |
|------|---------|
| **MLflow** | Experiment tracking, metrics comparison, heatmaps, parameter search visualization |
| **ML Metadata (MLMD)** | Artifact lineage, schema versions, vocabulary tracking, production model registry |

---

## Quick Test

### Overview

Quick Test runs a mini TFX pipeline on Vertex AI to validate feature configurations before committing to full training:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QUICK TEST PIPELINE                                  │
│                                                                              │
│   BigQuery     ExampleGen     Statistics    Schema      Transform           │
│   (10% sample) (TFRecords)    Gen          Gen         (vocabularies)       │
│       │            │             │            │             │               │
│       └────────────┴─────────────┴────────────┴─────────────┘               │
│                                        │                                     │
│                                        ↓                                     │
│                                    Trainer                                   │
│                               (2 epochs, no GPU)                             │
│                                        │                                     │
│                                        ↓                                     │
│                                   Metrics                                    │
│                              (Loss, Recall@k)                                │
│                                        │                                     │
│                                        ↓                                     │
│                                    MLflow                                    │
│                              (log experiment)                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test vs Full Training

| Aspect | Quick Test | Full Training |
|--------|------------|---------------|
| Data | 5-100% sample (configurable) | 100% data |
| ExampleGen | Sampled BigQuery | Full BigQuery |
| StatisticsGen/Transform | Dataflow (auto-scaling) | Dataflow (auto-scaling) |
| Trainer | CPU (configurable tiers) | GPU, 10-50 epochs |
| Hardware | Small/Medium/Large CPU tiers | GPU-enabled instances |
| Output | Temporary | Permanent artifacts |
| MLflow | Logged (tagged as quick test) | Logged (production) |

### Pipeline Integration

Full Vertex AI Pipeline integration for validating feature configurations:

**Backend:**
- `QuickTest` model in `ml_platform/models.py` - Tracks pipeline runs with status, progress, results
- `ml_platform/pipelines/` module - New sub-app for pipeline management:
  - `services.py` - PipelineService class for submission, polling, result extraction
  - `pipeline_builder.py` - KFP v2 pipeline with 6 components (ExampleGen, StatisticsGen, SchemaGen, Transform, Trainer, SaveMetrics)
  - `api.py` - 4 REST endpoints for start/status/cancel/list operations
- GCS buckets with lifecycle policies (7/30/3 days)
- IAM roles configured for `django-app` service account

**Pipeline Flow:**
```
FeatureConfig + ModelConfig → Dataset → BigQueryService.generate_query() → Vertex AI Pipeline → metrics.json → UI
```

### Quick Test API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/feature-configs/{id}/quick-test/` | Start quick test with configurable epochs, batch size, learning rate |
| GET | `/api/quick-tests/{id}/` | Get status and results (auto-polls Vertex AI) |
| POST | `/api/quick-tests/{id}/cancel/` | Cancel running pipeline |
| GET | `/api/feature-configs/{id}/quick-tests/` | List all tests for a config |

---

## User Interface

### Experiments Page Layout

The Experiments page has two main chapters:

1. **Quick Test Chapter** - Run and monitor validation tests ✅ IMPLEMENTED
2. **Experiments Dashboard Chapter** - Compare results via MLflow ✅ IMPLEMENTED (2025-12-23)

### Quick Test Chapter UI

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test                                                                   │
│ Validate your feature and model configurations before full training         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Configuration Selection                                                  │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │                                                                         │ │
│ │ Feature Config *                 Model Config *                         │ │
│ │ ┌─────────────────────────────┐  ┌─────────────────────────────┐      │ │
│ │ │ Q4 Features v2           ▼ │  │ Standard Two-Tower        ▼ │      │ │
│ │ └─────────────────────────────┘  └─────────────────────────────┘      │ │
│ │                                                                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Training Parameters                                                      │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │                                                                         │ │
│ │ Epochs           Batch Size        Learning Rate                        │ │
│ │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │ │
│ │ │ 3        ▼ │  │ 4096     ▼ │  │ 0.05        │                     │ │
│ │ └─────────────┘  └─────────────┘  └─────────────┘                     │ │
│ │                                                                         │ │
│ │ ⓘ Parameters auto-filled from selected Model Config                     │ │
│ │                                                                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                                              [▶ Start Quick Test]           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test Dialog

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test: Q4 Features v2 + Standard Two-Tower                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Quick Test Settings                                                          │
│                                                                              │
│ Data sample:    [10% ▼]    (options: 5%, 10%, 25%)                          │
│ Epochs:         [2 ▼]      (options: 1, 2, 3)                               │
│ Batch size:     [4096 ▼]   (options: 2048, 4096, 8192)                      │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│                                                                              │
│ Estimated:                                                                   │
│   Duration: ~8 minutes                                                       │
│   Cost: ~$1.50                                                               │
│                                                                              │
│ What Quick Test validates:                                                   │
│   ✓ Transform compiles successfully                                         │
│   ✓ Features have valid vocabularies                                        │
│   ✓ Model trains without errors                                             │
│   ✓ Basic metrics computed (loss, recall@10/50/100)                         │
│                                                                              │
│ ⚠️ Quick Test metrics are indicative only. Run Full Training for            │
│    production-ready results.                                                 │
│                                                                              │
│                                              [Cancel]  [▶ Start Quick Test] │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Hardware Configuration

The wizard includes hardware selection for configuring compute resources:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ Hardware Configuration                                                    │
│                                                                              │
│ CPU Options:                                                                 │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                        │
│ │ Small    ✓   │  │ Medium       │  │ Large        │                        │
│ │ 4 vCPU       │  │ 8 vCPU       │  │ 16 vCPU      │                        │
│ │ 15 GB RAM    │  │ 30 GB RAM    │  │ 60 GB RAM    │                        │
│ │ Recommended  │  │              │  │              │                        │
│ └──────────────┘  └──────────────┘  └──────────────┘                        │
│                                                                              │
│ GPU Options (coming soon):                                                   │
│ ┌──────────────┐  ┌──────────────┐                                          │
│ │ 🔒 T4        │  │ 🔒 A100      │                                          │
│ │ Coming Soon  │  │ Coming Soon  │                                          │
│ └──────────────┘  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Machine Type Tiers:**

| Tier | Machine Type | vCPU | Memory | Recommended For |
|------|--------------|------|--------|-----------------|
| Small | n1-standard-4 | 4 | 15 GB | Datasets < 100K rows |
| Medium | n1-standard-8 | 8 | 30 GB | Datasets 100K - 1M rows |
| Large | n1-standard-16 | 16 | 60 GB | Datasets > 1M rows |

**Auto-Recommendation:** The system automatically suggests hardware based on dataset size and model complexity.

**Dataflow Integration:** StatisticsGen and Transform components always use Dataflow with the selected machine type for worker nodes. This ensures scalable processing for large datasets.

### Quick Test Progress

**Stage Progress Bar (Updated December 2025):**

Each experiment card shows a 6-stage progress bar with color-coded status:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Experiment #7 - Running                                    [Cancel]          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ [Compile ✓] [Examples ✓] [Stats ✓] [Schema ●] [Transform ○] [Train ○]       │
│   green       green       green     orange      grey         grey            │
│                                                                              │
│ Current: Schema (analyzing statistics)                                       │
│                                                                              │
│ Feature: My Feature Config                                                   │
│ Model: Standard Two-Tower                                                    │
│ Split: Random (80/20)  Sample: 25%  Hardware: Medium                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Stage Statuses:**
| Color | Icon | Status | Description |
|-------|------|--------|-------------|
| Grey | ○ | Pending | Stage not yet started |
| Orange | ● | Running | Stage currently executing |
| Green | ✓ | Success | Stage completed successfully |
| Red | ✗ | Failed | Stage failed with error |

**Pipeline Stages:**
| Stage | TFX Component | Description |
|-------|---------------|-------------|
| Compile | Cloud Build | Compile TFX pipeline and submit to Vertex AI |
| Examples | BigQueryExampleGen | Extract data from BigQuery to TFRecords |
| Stats | StatisticsGen | Compute dataset statistics using TFDV |
| Schema | SchemaGen | Infer schema from statistics |
| Transform | Transform | Apply preprocessing_fn, generate vocabularies |
| Train | Trainer | Train TFRS two-tower model |

**Legacy Progress View (for reference):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test Running: Q4 Features v2                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────┐    │
│ │ ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 45%       │    │
│ └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│ Current Stage: Transform (generating vocabularies)                           │
│                                                                              │
│ ✅ ExampleGen        - Completed (2 min)                                     │
│ ✅ StatisticsGen     - Completed (1 min)                                     │
│ ✅ SchemaGen         - Completed (10 sec)                                    │
│ 🔄 Transform         - Running... (3 min elapsed)                            │
│ ⏳ Trainer           - Pending                                               │
│                                                                              │
│ Elapsed: 6 min 10 sec                                                        │
│ Estimated remaining: ~5 min                                                  │
│                                                                              │
│                                                              [Cancel Test]   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test Results

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test Results: Q4 Features v2                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Status: ✅ Success                                                           │
│ Duration: 8 min 23 sec                                                       │
│ Cost: $1.42                                                                  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ METRICS (indicative - 10% sample, 2 epochs)                                  │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────┬────────────┬────────────────────────────────────────┐    │
│ │ Metric         │ Value      │ vs Previous Best (config-038)          │    │
│ ├────────────────┼────────────┼────────────────────────────────────────┤    │
│ │ Loss           │ 0.38       │ ↓ 0.04 (was 0.42)                      │    │
│ │ Recall@10      │ 18.2%      │ ↑ 0.4% (was 17.8%)                     │    │
│ │ Recall@50      │ 38.5%      │ ↑ 1.2% (was 37.3%)                     │    │
│ │ Recall@100     │ 47.3%      │ ↑ 1.2% (was 46.1%)                     │    │
│ └────────────────┴────────────┴────────────────────────────────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ VOCABULARY STATS                                                             │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────┬────────────┬────────────┬───────────────────────────┐    │
│ │ Feature        │ Vocab Size │ OOV Rate   │ Status                    │    │
│ ├────────────────┼────────────┼────────────┼───────────────────────────┤    │
│ │ user_id        │ 9,823      │ 1.2%       │ ✅ Good                   │    │
│ │ product_id     │ 3,612      │ 0.8%       │ ✅ Good                   │    │
│ │ city           │ 28         │ 0%         │ ✅ Good                   │    │
│ │ product_name   │ 3,421      │ 2.1%       │ ✅ Good                   │    │
│ │ category       │ 12         │ 0%         │ ✅ Good                   │    │
│ │ subcategory    │ 142        │ 0.3%       │ ✅ Good                   │    │
│ └────────────────┴────────────┴────────────┴───────────────────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ WARNINGS                                                                     │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ (none)                                                                       │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ 🎉 This config shows improvement over previous best!                         │
│                                                                              │
│ [View in MLflow]  [Modify & Re-test]  [▶ Run Full Training]  [Close]        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## MLflow Experiment Comparison

### Experiments Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Experiments                                                                  │
│ Dataset: Q4 2024 Training Data                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ SUMMARY                                                                      │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│ │ Quick Tests  │  │ Full Trains  │  │ Best R@100   │  │ Currently    │     │
│ │     12       │  │      4       │  │    47.3%     │  │  Deployed    │     │
│ │              │  │              │  │  config-042  │  │   46.2%      │     │
│ └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ HEATMAP: Recall@100 by Configuration                                         │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Group X: [Embedding Dims ▼]  Group Y: [Cross Features ▼]  Show: [All ▼]     │
│                                                                              │
│                    │ user:32  │ user:64  │ user:64  │ user:128 │           │
│                    │ prod:32  │ prod:32  │ prod:64  │ prod:64  │           │
│ ───────────────────┼──────────┼──────────┼──────────┼──────────┤           │
│ No crosses         │  38.2%   │  41.5%   │  44.1%   │  44.8%   │           │
│                    │   ██     │   ███    │   ████   │   ████   │           │
│ ───────────────────┼──────────┼──────────┼──────────┼──────────┤           │
│ cat × subcat       │  39.1%   │  42.8%   │  45.9%   │  46.2%   │           │
│                    │   ██     │   ███    │  █████   │  █████   │           │
│ ───────────────────┼──────────┼──────────┼──────────┼──────────┤           │
│ + user × city      │  38.5%   │  43.1%   │ ★47.3%   │  46.9%   │           │
│                    │   ██     │   ███    │  █████   │  █████   │           │
│                                                                              │
│ ★ Best | ● Deployed | Legend: █████ >46% ████ 44-46% ███ 42-44% ██ <42%    │
│                                                                              │
│ [Export Heatmap]  [View as Table]  [Change Metric]                          │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ RECENT EXPERIMENTS                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-042 • Quick Test #3                              47.3% R@100   │  │
│ │ 2 hours ago | 8 min | $1.42 | user:64d prod:64d +crosses              │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-042 • Full Training #46                          46.8% R@100   │  │
│ │ 5 hours ago | 3h 42m | $38.50 | Promoted for deployment               │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-044 • Quick Test #1                                   Failed   │  │
│ │ 1 day ago | OOM during Transform | user:256d (too large)              │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ [View All in MLflow]                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Experiment Comparison View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Compare Experiments                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Selected: config-042 (Quick Test #3) vs config-038 (Full Training #45)      │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ METRICS COMPARISON                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────┬───────────────────┬───────────────────┬────────────┐    │
│ │ Metric          │ config-042        │ config-038        │ Diff       │    │
│ │                 │ (Quick Test)      │ (Full Train)      │            │    │
│ ├─────────────────┼───────────────────┼───────────────────┼────────────┤    │
│ │ Loss            │ 0.38              │ 0.32              │ -0.06      │    │
│ │ Recall@10       │ 18.2%             │ 17.5%             │ +0.7%      │    │
│ │ Recall@50       │ 38.5%             │ 37.8%             │ +0.7%      │    │
│ │ Recall@100      │ 47.3%             │ 46.1%             │ +1.2%      │    │
│ │ Duration        │ 8 min             │ 2h 58m            │ -          │    │
│ │ Cost            │ $1.42             │ $32.10            │ -          │    │
│ └─────────────────┴───────────────────┴───────────────────┴────────────┘    │
│                                                                              │
│ ⚠️ Note: Quick Test metrics are indicative (10% data, 2 epochs)             │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ CONFIGURATION DIFF                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Query Tower                                                             │ │
│ │   user_id:  64d  →  64d   (same)                                        │ │
│ │   city:     16d  →  16d   (same)                                        │ │
│ │                                                                         │ │
│ │ Candidate Tower                                                         │ │
│ │   product_id:    64d  →  64d   (same)                                   │ │
│ │   product_name:  32d  →  32d   (same)                                   │ │
│ │   category:      16d  →  16d   (same)                                   │ │
│ │   subcategory:   16d  →  16d   (same)                                   │ │
│ │                                                                         │ │
│ │ Cross Features                                                          │ │
│ │ + user_id × city (5000 buckets)     ← NEW in config-042                 │ │
│ │   category × subcategory (1000)     (same)                              │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ RECOMMENDATION                                                               │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ 💡 config-042 shows +1.2% improvement in Recall@100.                        │
│    Consider running Full Training with config-042 to confirm.               │
│                                                                              │
│ [▶ Run Full Training with config-042]  [Add More to Compare]  [Close]       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MLflow Integration View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MLflow Experiments                                          [Open MLflow ↗] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Experiment: Q4-2024-Training-Data                                           │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ RUNS TABLE                                                                   │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Filter: [All Types ▼]  Sort: [Recall@100 DESC ▼]  Search: [_________]       │
│                                                                              │
│ ┌───┬────────────┬─────────┬──────────┬──────────┬───────────┬───────────┐  │
│ │   │ Run Name   │ Type    │ R@100    │ R@50     │ Duration  │ Date      │  │
│ ├───┼────────────┼─────────┼──────────┼──────────┼───────────┼───────────┤  │
│ │ ☑ │ config-042 │ Quick   │ 47.3%    │ 38.5%    │ 8m        │ 2h ago    │  │
│ │ ☑ │ run-46     │ Full    │ 46.8%    │ 39.2%    │ 3h 42m    │ 5h ago    │  │
│ │ ☐ │ config-038 │ Quick   │ 46.1%    │ 37.3%    │ 7m        │ 1d ago    │  │
│ │ ☐ │ run-45     │ Full    │ 45.2%    │ 36.8%    │ 2h 58m    │ 3d ago    │  │
│ │ ☐ │ config-035 │ Quick   │ 42.0%    │ 33.1%    │ 5m        │ 5d ago    │  │
│ └───┴────────────┴─────────┴──────────┴──────────┴───────────┴───────────┘  │
│                                                                              │
│ [Compare Selected]  [Export CSV]                                            │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ PARALLEL COORDINATES                                                         │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│   user_emb    prod_emb   crosses    revenue_buckets   R@100                 │
│      │           │          │              │            │                    │
│     32          32         none           5         ────┼──── 42%            │
│      │           │          │              │            │                    │
│     64 ─────────32         one ──────────10 ───────────┼──── 45%            │
│      │           │          │              │            │                    │
│     64 ─────────64 ────────two ──────────10 ───────────┼──── 47%            │
│      │           │          │              │            │                    │
│    128          64         two           10         ────┼──── 47%            │
│                                                                              │
│ [Change Axes]  [Filter Runs]                                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### MLflow Experiment Structure

```
MLflow Experiment: "{model_name}-{dataset_name}"
│
├── Run: quick-test-{config_id}-{timestamp}
│   ├── Parameters:
│   │   ├── run_type: "quick_test"
│   │   ├── config_id: "config-042"
│   │   ├── data_sample_percent: 10
│   │   ├── epochs: 2
│   │   ├── user_id_embedding_dim: 64
│   │   ├── product_id_embedding_dim: 64
│   │   ├── cross_features: "category_x_subcategory,user_id_x_city"
│   │   └── ...
│   ├── Metrics:
│   │   ├── loss: 0.38
│   │   ├── recall_at_10: 0.182
│   │   ├── recall_at_50: 0.385
│   │   └── recall_at_100: 0.473
│   └── Tags:
│       ├── dataset_id: "dataset-001"
│       ├── feature_config_id: "config-042"
│       └── mlflow.runName: "config-042 Quick Test #3"
│
├── Run: full-training-{run_number}-{timestamp}
│   ├── Parameters:
│   │   ├── run_type: "full_training"
│   │   ├── training_run_id: 46
│   │   ├── epochs: 20
│   │   ├── batch_size: 8192
│   │   └── ...
│   ├── Metrics:
│   │   ├── final_loss: 0.28
│   │   ├── recall_at_100: 0.468
│   │   └── epoch_*: {...}  # per-epoch metrics
│   ├── Artifacts:
│   │   ├── model/  # link to GCS
│   │   └── training_curves.png
│   └── Tags:
│       ├── dataset_version: "3"
│       ├── is_deployed: "true"
│       └── ...
```

### Django Models (Lightweight)

Most experiment data lives in MLflow. Django stores minimal reference data:

```python
# ml_platform/models.py

class ExperimentComparison(models.Model):
    """
    Saved comparison for reference.
    """
    name = models.CharField(max_length=255)
    ml_model = models.ForeignKey('MLModel', on_delete=models.CASCADE)

    # MLflow run IDs being compared
    mlflow_run_ids = models.JSONField(default=list)

    # Notes
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
```

---

## API Endpoints

### Experiments API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{model_id}/experiments/` | Get experiments summary |
| GET | `/api/models/{model_id}/experiments/heatmap/` | Get heatmap data |
| GET | `/api/models/{model_id}/experiments/runs/` | List all MLflow runs |
| POST | `/api/experiments/compare/` | Compare multiple runs |
| GET | `/api/experiments/mlflow-url/` | Get MLflow UI URL |

### Heatmap Data Endpoint

**GET /api/models/{model_id}/experiments/heatmap/**

Query parameters:
- `metric`: `recall_at_100` (default), `recall_at_50`, `recall_at_10`, `loss`
- `x_axis`: `embedding_dims`, `cross_features`, `epochs`
- `y_axis`: `embedding_dims`, `cross_features`, `epochs`
- `run_type`: `all`, `quick_test`, `full_training`

Response:
```json
{
  "status": "success",
  "data": {
    "metric": "recall_at_100",
    "x_axis": {
      "name": "embedding_dims",
      "values": ["32/32", "64/32", "64/64", "128/64"]
    },
    "y_axis": {
      "name": "cross_features",
      "values": ["none", "cat×subcat", "+user×city"]
    },
    "cells": [
      {"x": "32/32", "y": "none", "value": 0.382, "run_id": "abc123"},
      {"x": "64/32", "y": "none", "value": 0.415, "run_id": "def456"},
      ...
    ],
    "best": {"x": "64/64", "y": "+user×city", "value": 0.473, "run_id": "ghi789"}
  }
}
```

---

## Services

### MLflow Integration Service

```python
# ml_platform/experiments/services.py

import mlflow
from mlflow.tracking import MlflowClient

class MLflowService:
    """
    Manages MLflow experiment tracking and visualization.
    """

    def __init__(self, tracking_uri: str):
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient()

    def get_or_create_experiment(self, name: str) -> str:
        """Get or create MLflow experiment, return experiment_id."""
        experiment = self.client.get_experiment_by_name(name)
        if experiment:
            return experiment.experiment_id
        return self.client.create_experiment(name)

    def log_quick_test(
        self,
        quick_test: 'QuickTest',
        feature_config: 'FeatureConfig',
        dataset: 'Dataset'
    ):
        """Log quick test results to MLflow."""
        experiment_id = self.get_or_create_experiment(
            f"{dataset.ml_model.name}-{dataset.name}"
        )

        with mlflow.start_run(experiment_id=experiment_id) as run:
            # Log parameters
            mlflow.log_param("run_type", "quick_test")
            mlflow.log_param("config_id", feature_config.id)
            mlflow.log_param("data_sample_percent", quick_test.data_sample_percent)
            mlflow.log_param("epochs", quick_test.epochs)

            # Log feature config parameters
            for feature in feature_config.query_tower:
                mlflow.log_param(f"{feature['name']}_embedding_dim", feature['embedding_dim'])
            for feature in feature_config.candidate_tower:
                mlflow.log_param(f"{feature['name']}_embedding_dim", feature['embedding_dim'])

            # Log cross features
            cross_names = [
                "_x_".join(cf['features'])
                for cf in feature_config.cross_features
            ]
            mlflow.log_param("cross_features", ",".join(cross_names) or "none")

            # Log metrics
            mlflow.log_metric("loss", quick_test.loss)
            mlflow.log_metric("recall_at_10", quick_test.recall_at_10)
            mlflow.log_metric("recall_at_50", quick_test.recall_at_50)
            mlflow.log_metric("recall_at_100", quick_test.recall_at_100)

            # Set tags
            mlflow.set_tag("dataset_id", dataset.id)
            mlflow.set_tag("feature_config_id", feature_config.id)
            mlflow.set_tag("mlflow.runName", f"{feature_config.name} Quick Test #{quick_test.id}")

            return run.info.run_id

    def log_training_run(
        self,
        training_run: 'TrainingRun',
        feature_config: 'FeatureConfig',
        dataset: 'Dataset'
    ):
        """Log full training results to MLflow."""
        # Similar to quick test, but with more parameters and artifacts
        pass

    def get_heatmap_data(
        self,
        experiment_name: str,
        metric: str,
        x_axis: str,
        y_axis: str,
        run_type: str = 'all'
    ) -> dict:
        """
        Generate heatmap data from MLflow runs.
        """
        experiment = self.client.get_experiment_by_name(experiment_name)
        if not experiment:
            return {"cells": [], "best": None}

        # Query runs
        filter_string = ""
        if run_type != 'all':
            filter_string = f"params.run_type = '{run_type}'"

        runs = self.client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=filter_string,
        )

        # Group runs by x/y axes
        # Implementation depends on axis types
        pass

    def compare_runs(self, run_ids: list) -> dict:
        """
        Compare multiple MLflow runs.
        Returns metrics and parameter diffs.
        """
        runs = [self.client.get_run(run_id) for run_id in run_ids]

        comparison = {
            "runs": [],
            "metrics": {},
            "params_diff": {},
        }

        for run in runs:
            comparison["runs"].append({
                "run_id": run.info.run_id,
                "name": run.data.tags.get("mlflow.runName", run.info.run_id),
                "metrics": run.data.metrics,
                "params": run.data.params,
            })

        # Calculate diffs
        # ...

        return comparison
```

### Heatmap Generation Service

```python
# ml_platform/experiments/services.py

class HeatmapService:
    """
    Generates heatmap visualizations from experiment data.
    """

    def __init__(self, mlflow_service: MLflowService):
        self.mlflow = mlflow_service

    def generate_heatmap_data(
        self,
        experiment_name: str,
        metric: str = 'recall_at_100',
        x_axis: str = 'embedding_dims',
        y_axis: str = 'cross_features',
    ) -> dict:
        """
        Generate heatmap data structure for frontend visualization.
        """
        runs = self.mlflow.get_runs(experiment_name)

        # Extract axis values
        x_values = self._extract_axis_values(runs, x_axis)
        y_values = self._extract_axis_values(runs, y_axis)

        # Build cell data
        cells = []
        best = None
        best_value = -1

        for run in runs:
            x_val = self._get_axis_value(run, x_axis)
            y_val = self._get_axis_value(run, y_axis)
            metric_val = run.data.metrics.get(metric)

            if metric_val is not None:
                cell = {
                    "x": x_val,
                    "y": y_val,
                    "value": metric_val,
                    "run_id": run.info.run_id,
                    "run_name": run.data.tags.get("mlflow.runName"),
                }
                cells.append(cell)

                if metric_val > best_value:
                    best_value = metric_val
                    best = cell

        return {
            "metric": metric,
            "x_axis": {"name": x_axis, "values": sorted(x_values)},
            "y_axis": {"name": y_axis, "values": sorted(y_values)},
            "cells": cells,
            "best": best,
        }

    def _extract_axis_values(self, runs, axis_type: str) -> set:
        """Extract unique values for an axis type."""
        values = set()
        for run in runs:
            val = self._get_axis_value(run, axis_type)
            if val:
                values.add(val)
        return values

    def _get_axis_value(self, run, axis_type: str):
        """Get the axis value for a specific run."""
        if axis_type == 'embedding_dims':
            user_dim = run.data.params.get('user_id_embedding_dim', '?')
            prod_dim = run.data.params.get('product_id_embedding_dim', '?')
            return f"{user_dim}/{prod_dim}"
        elif axis_type == 'cross_features':
            return run.data.params.get('cross_features', 'none')
        elif axis_type == 'epochs':
            return run.data.params.get('epochs', '?')
        else:
            return run.data.params.get(axis_type)
```

---

## MLflow Server Setup

### Cloud Run Deployment

MLflow server runs as a Cloud Run service per client project:

```yaml
# mlflow-server/cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/mlflow-server', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/mlflow-server']
```

```dockerfile
# mlflow-server/Dockerfile
FROM python:3.10-slim

RUN pip install mlflow psycopg2-binary google-cloud-storage

EXPOSE 5000

CMD ["mlflow", "server", \
     "--backend-store-uri", "postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}/${DB_NAME}", \
     "--default-artifact-root", "gs://${GCS_BUCKET}/mlflow-artifacts", \
     "--host", "0.0.0.0", \
     "--port", "5000"]
```

### Configuration

```python
# Django settings
MLFLOW_TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', 'http://mlflow-server:5000')
```

---

## Implementation Checklist

> **Note:** Detailed implementation steps are in [phase_experiments_implementation.md](phase_experiments_implementation.md)

### Phase 1: TFX Pipeline Infrastructure ✅ DONE
- [x] Install TFX dependencies (`tfx>=1.14.0`)
- [x] Create `ml_platform/pipelines/tfx_pipeline.py` - Native TFX pipeline
- [x] Implement `create_quicktest_pipeline()` function
- [x] Implement `compile_pipeline_for_vertex()` function
- [x] Update `pipeline_builder.py` to use TFX (remove KFP v2 placeholders)
- [x] Update `services.py` for TFX pipeline submission
- [x] Test pipeline compilation
- [x] Test pipeline execution on Vertex AI

### Phase 2: Trainer Module Generator Rebuild ✅ DONE
- [x] Rebuild `TrainerModuleGenerator` in `configs/services.py`
- [x] Generate proper `run_fn()` entry point
- [x] Generate BuyerModel class from FeatureConfig
- [x] Generate ProductModel class from FeatureConfig
- [x] Apply tower layers from ModelConfig
- [x] Implement metrics export to GCS
- [x] Validate generated code compiles

### Phase 3: Experiment Parameters & Submission ✅ DONE
- [x] Add new fields to `QuickTest` model:
  - `sample_percent` (5, 10, 25, 100)
  - `split_strategy` (random, time_holdout, strict_time)
  - `date_column` (for time-based strategies)
  - `holdout_days` (for time_holdout)
  - `train_days`, `val_days`, `test_days` (for strict_time)
- [x] Update API endpoint to accept new parameters
- [x] Update UI to show parameter configuration with dynamic defaults
- [x] Implement sampling in SQL query
- [x] Implement split configuration in ExampleGen:
  - `random`: Hash-based 80/20 split
  - `time_holdout`: Date-filtered + hash-based 80/20 split
  - `strict_time`: True temporal split using SQL `split` column + `partition_feature_name`

### Phase 4: Pipeline Visualization UI ✅ DONE
- [x] Create pipeline DAG component (like Vertex AI console)
- [x] Add real-time stage status updates
- [x] Show stage icons (✅ completed, 🔄 running, ⏳ pending)
- [x] Add artifact boxes between stages
- [x] Style to match screenshot reference

### Phase 5: Metrics Collection & Display 🔴 TODO
- [ ] Collect all available metrics per epoch
- [ ] Export `epoch_metrics.json` from Trainer
- [ ] Build epoch metrics chart (Chart.js)
- [ ] Build comparison table (sortable, filterable)

### Phase 6: MLflow Integration 🔴 TODO
- [ ] Deploy MLflow server to Cloud Run
  - [ ] Create `mlflow-server/Dockerfile`
  - [ ] Create `mlflow-server/cloudbuild.yaml`
  - [ ] Deploy and verify server accessible
- [ ] Set up Cloud SQL for MLflow backend store
  - [ ] Create PostgreSQL database
  - [ ] Configure connection from Cloud Run
- [ ] Create GCS bucket for MLflow artifacts
- [ ] Django MLflow integration:
  - [ ] Add `MLFLOW_TRACKING_URI` to settings
  - [ ] Create `ml_platform/experiments/services.py` (MLflowService)
  - [ ] Create `ml_platform/experiments/api.py` (endpoints)
  - [ ] Add `mlflow_run_id` field to QuickTest model
- [ ] Update pipeline completion to log to MLflow
- [ ] API endpoints:
  - [ ] GET `/api/experiments/{model_endpoint_id}/{dataset_id}/runs/`
  - [ ] GET `/api/experiments/{model_endpoint_id}/{dataset_id}/heatmap/`
  - [ ] POST `/api/experiments/compare/`
  - [ ] GET `/api/experiments/mlflow-url/`
- [ ] UI integration:
  - [ ] Add "Open MLflow UI" button
  - [ ] Runs table with sorting/filtering
  - [ ] Heatmap visualization
  - [ ] Run comparison view

### Phase 7: Pre-built TFX Compiler Image ✅ DONE (2025-12-15)
> **Critical for Quick Test performance** - Reduces compilation from 12-15 min to 1-2 min

- [x] Create Dockerfile for TFX compiler (`cloudbuild/tfx-builder/Dockerfile`)
- [x] Build and push to Artifact Registry:
  - `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest`
  - `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:v1.0.0`
- [x] Update `services.py` to use pre-built image instead of `python:3.10`
- [x] Add `TFX_COMPILER_IMAGE` to Django settings (configurable)
- [x] Create `cloudbuild/tfx-builder/cloudbuild.yaml` for rebuilding image
- [x] Create `cloudbuild/tfx-builder/README.md` with setup documentation
- [x] Verify image works (TFX 1.15.0, KFP 2.15.2)

**Current Setup (Development):**
- Image hosted in `b2b-recs` project (same as dev environment)
- For production multi-tenant: migrate to `b2b-recs-platform` project
- See [Phase 7 in implementation guide](phase_experiments_implementation.md#phase-7-pre-built-docker-image-for-fast-cloud-build)

### Phase 8: TFX Trainer Bug Fixes ✅ DONE (2025-12-16)
> **Critical bug fixes** - Fixed 5 issues preventing successful Trainer execution and model saving

- [x] **Embedding shape fix**: Changed `tf.reshape(f, [tf.shape(f)[0], -1])` to `tf.squeeze(f, axis=1)` to preserve static shapes
- [x] **Infinite dataset fix**: Added `num_epochs=1` to `TensorFlowDatasetOptions` in `_input_fn`
- [x] **StringLookup removal**: Removed redundant `StringLookup` layer (Transform already provides vocab indices)
- [x] **FactorizedTopK removal**: Removed stateful metrics that caused serialization issues during training
- [x] **ServingModel class**: Created proper wrapper class to track TFT resources for model saving
- [x] **NUM_OOV_BUCKETS constant**: Added to trainer module to match Transform preprocessing

**Result:** Pipeline now completes successfully: BigQueryExampleGen → StatisticsGen → SchemaGen → Transform → Trainer → Model Saved

### Phase 12: Pipeline Progress Bar & Error Improvements ✅ DONE (2025-12-18)
> **Visual progress tracking and better error handling**

- [x] **Stage progress bar**: 6-stage visual progress bar (Compile, Examples, Stats, Schema, Transform, Train)
- [x] **Color-coded status**: Grey (pending), orange (running), green (success), red (failed)
- [x] **Async Cloud Build**: Wizard closes immediately, status polled in background
- [x] **Cloud Build tracking**: Added `cloud_build_id` and `cloud_build_run_id` fields to QuickTest
- [x] **Column validation**: Validates FeatureConfig columns match BigQuery output before pipeline submission
- [x] **Duplicate column fix**: Fixed `generate_query()` to handle duplicate columns consistently
- [x] **Helpful error messages**: Column mismatch errors include suggestions for correct column names

**Result:** Users see real-time pipeline progress and get actionable error messages when column names don't match.

### Phase 13: Experiment Cards Redesign & Cancel ✅ DONE (2025-12-19)
> **Improved card layout and cancel functionality**

- [x] **4-column layout**: Exp info (30%), Config (20%), Params placeholder (30%), Actions (20%)
- [x] **Experiment name/description**: Optional fields in New Experiment wizard Step 1
- [x] **Cancel button**: Active for running experiments, disabled for others
- [x] **Progress bar styling**: Tensor-breakdown-bar with gradient green colors
- [x] **Styled confirmation**: Cancel uses styled modal instead of browser confirm()

**Result:** Experiment cards show more information in organized columns with cancel functionality.

### Phase 14: Experiment View Modal ✅ DONE (2025-12-19)
> **Comprehensive experiment details modal**

- [x] **View modal**: Full experiment details (config, params, progress, results, technical details)
- [x] **View button**: Green button on cards, opens View modal
- [x] **Real-time polling**: View modal updates every 10s for running experiments
- [x] **Code cleanup**: Removed old progress/results modals and unused functions
- [x] **Unified logging**: Backend logs use `{display_name} (id={id})` format
- [x] **Wizard scroll fix**: Step 2 now opens scrolled to top

**Result:** Users can view comprehensive experiment details without leaving the page.

### Phase 15: View Modal Redesign with Tabs & Artifacts ✅ DONE (2025-12-19)
> **Tabbed modal with artifact viewing and smart error handling**

- [x] **4-tab layout**: Overview, Pipeline, Data Insights, Training tabs
- [x] **Error pattern matching**: 15+ patterns with user-friendly titles and fix suggestions
- [x] **Artifact service**: Backend service to parse GCS statistics and schema
- [x] **Lazy loading**: Artifact data fetched on tab switch (not on modal open)
- [x] **Statistics display**: Feature count, missing %, min/max/mean values
- [x] **Schema display**: Feature names, types, required/optional
- [x] **Hidden GCP details**: Removed Vertex AI links and GCS paths from user view
- [x] **Training placeholder**: Ready for future MLflow integration

**Result:** Users see clean tabbed interface with actionable error messages and artifact visibility.

### Phase 17: Pipeline DAG Visualization ✅ DONE (2025-12-20)
> **Visual pipeline graph with component logs**

- [x] **Vertical DAG layout**: 4-row pipeline visualization (Examples → Stats/Schema → Transform → Train)
- [x] **SVG connections**: Bezier curve connections between components
- [x] **Clickable components**: Click to view component logs
- [x] **Cloud Logging integration**: Fetch logs via `google-cloud-logging` client
- [x] **Task job ID extraction**: Parse Vertex AI task details for `container_detail.main_job`
- [x] **Logs API endpoint**: `GET /api/quick-tests/{id}/logs/{component}/`
- [x] **Refresh functionality**: Refresh button to fetch latest logs
- [x] **7-day lookback**: Timestamp filter for accessing older experiment logs

**Result:** Users see visual pipeline DAG and can inspect component execution logs without GCP access.

### Phase 18: TFDV Parser Cloud Run Service ✅ DONE (2025-12-20)
> **Microservice for parsing TFX artifacts with full TFDV support**

- [x] **Cloud Run service**: Python 3.10 with TFX/TFDV (`tfdv-parser`)
- [x] **Statistics parsing**: Parse FeatureStats.pb with rich statistics (histograms, top values)
- [x] **Schema parsing**: Parse schema.pbtxt with feature types and constraints
- [x] **TFDV HTML visualization**: Generate full TFDV interactive display
- [x] **Service-to-service auth**: IAM-based authentication between Django and tfdv-parser
- [x] **Enhanced Data Insights UI**: Rich tables for numeric and categorical features
- [x] **Mini visualizations**: Histogram bars for numeric, bar charts for categorical
- [x] **Identity token fallback**: gcloud CLI for local development

**Result:** Data Insights tab shows comprehensive TFDV statistics matching the standard visualization format.

### Phase 19: Schema Fix & TFDV Hybrid Visualization ✅ DONE (2025-12-21)
> **Bug fixes for Schema tab and improved TFDV display approach**

- [x] **Schema field name fix**: Updated `renderSchema()` to use `feature_type` and `presence` instead of `type` and `required`
- [x] **Removed broken TFDV modal**: Deleted iframe-based `#tfdvModal` HTML, CSS (~80 lines), and JavaScript functions
- [x] **New standalone TFDV endpoint**: `GET /experiments/quick-tests/{id}/tfdv/` serves TFDV HTML as full page
- [x] **Open in New Tab button**: Changed from `<button onclick>` to `<a target="_blank">` to avoid popup blockers
- [x] **Page wrapper**: TFDV HTML wrapped with header, experiment info, and consistent styling
- [x] **Documentation**: Updated phase_experiments_implementation.md with Phase 19

**Result:** Schema tab now displays correct feature types and required status. TFDV can be viewed in a new browser tab where it renders properly.

### Phase 20: Enhanced Pipeline DAG Visualization ✅ DONE (2025-12-22)
> **Complete TFX pipeline visualization with 8 nodes and artifacts**

- [x] **8-node TFX pipeline**: Pipeline Compile, Examples Gen, Stats Gen, Schema Gen, Transform, Trainer, Evaluator, Pusher
- [x] **11 artifacts displayed**: Config, Examples, Statistics, Schema, Transform Graph, Transformed Examples, Model, ModelRun, Model Blessing, Evaluation, Model Endpoint
- [x] **Bezier curve connections**: SVG curves with 4 types (left, right, down-left, down-right)
- [x] **White background styling**: Clean background with subtle dot grid (#d8d8d8 1px dots)
- [x] **Node width increase**: 264px (20% increase from 220px)
- [x] **Consistent spacing**: Equal vertical spacing (~174px) between all pipeline stages
- [x] **Node renaming**: BigQueryExampleGen → Examples Gen, StatisticsGen → Stats Gen, SchemaGen → Schema Gen
- [x] **New icons**: Trainer uses fa-microchip, Evaluator uses fa-check-double, Pusher uses fa-cloud-upload-alt
- [x] **Direct Model → Pusher path**: Alternative deployment path without Evaluator

**Result:** Pipeline visualization matches Vertex AI Pipelines console style with complete TFX component and artifact representation.

### Phase 21: Pipeline DAG Static File Extraction ✅ DONE (2025-12-22)
> **Reusable DAG visualization components for Full Training page**

- [x] **CSS extraction**: Created `static/css/pipeline_dag.css` with all DAG styles (293 lines)
- [x] **JS extraction**: Created `static/js/pipeline_dag.js` with DAG rendering logic (~500 lines)
- [x] **HTML template**: Created `templates/includes/_pipeline_dag.html` as reusable include
- [x] **model_experiments.html update**: Added imports, replaced inline code with includes
- [x] **HTML comments for docs**: Use `<!-- -->` instead of `{# #}` (Django parses tags in Django comments)
- [x] **Global functions preserved**: `renderPipelineStages()`, `selectDagComponent()`, `loadComponentLogs()`, etc.

**Result:** Pipeline DAG visualization is now a reusable component that can be included on both Quick Test and Full Training pages.

### Previously Completed ✅
- [x] Create `model_experiments.html` page (placeholder)
- [x] Feature Config dropdown
- [x] Model Config dropdown
- [x] Training parameters panel
- [x] QuickTest Django model
- [x] `ml_platform/pipelines/` sub-app structure
- [x] PipelineService class (needs update for TFX)
- [x] API endpoints (need parameter updates)
- [x] GCS bucket lifecycle policies

### Future Phases (Not in Scope)
- [ ] Ranking Models
- [ ] Multitask Models
- [ ] Hyperparameter Tuning (Vertex AI Vizier)

---

## Dependencies on Other Domains

### Depends On
- **Configs Domain**: Feature Configs (feature engineering specifications) and Model Configs (neural network architecture)
- **Datasets Domain**: Dataset definitions for training data
- **Training Domain**: Full Training results (future)

### Depended On By
- **Deployment Domain**: Best model selection for deployment

---

## Related Documentation

- [Implementation Overview](../implementation.md)
- [Configs Phase](phase_configs.md)
- [Training Phase](phase_training.md)
- [Deployment Phase](phase_deployment.md)
