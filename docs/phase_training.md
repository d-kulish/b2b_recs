# Phase: Training Domain

## Document Purpose
This document provides detailed specifications for implementing the **Training** domain in the ML Platform. The Training domain executes full TFX pipelines for production model training.

**Last Updated**: 2026-01-29 (Feature: Deployment Integration in Training Wizard)

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

## Prerequisites

### Training Scheduler IAM Setup

For scheduled training to work, you must create and configure the `training-scheduler` service account. This service account is used by Cloud Scheduler to authenticate webhook calls via OIDC tokens.

#### Why This Is Needed

When Cloud Scheduler triggers a scheduled training:
1. Cloud Scheduler generates an OIDC token using the `training-scheduler` service account
2. The token is sent in the `Authorization` header to the webhook endpoint
3. Django verifies the token and executes the training

Without proper IAM setup, the webhook returns `401 Unauthorized` and schedules never execute.

#### Setup Commands

```bash
# 1. Create the service account
gcloud iam service-accounts create training-scheduler \
  --display-name="Training Scheduler Service Account" \
  --description="Service account for Cloud Scheduler to trigger training webhooks" \
  --project=PROJECT_ID

# 2. Grant Cloud Scheduler agent permission to create OIDC tokens
# Replace PROJECT_NUMBER with your GCP project number (e.g., 555035914949)
gcloud iam service-accounts add-iam-policy-binding \
  training-scheduler@PROJECT_ID.iam.gserviceaccount.com \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --project=PROJECT_ID

# 3. Grant the service account permission to invoke Cloud Run
gcloud run services add-iam-policy-binding django-app \
  --member="serviceAccount:training-scheduler@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=europe-central2 \
  --project=PROJECT_ID
```

#### Finding Your Project Number

```bash
gcloud projects describe PROJECT_ID --format="value(projectNumber)"
```

#### Verification

After setup, verify the service account exists and has correct permissions:

```bash
# Check service account exists
gcloud iam service-accounts list --project=PROJECT_ID --filter="email:training-scheduler@"

# Check IAM policy on the service account
gcloud iam service-accounts get-iam-policy \
  training-scheduler@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
```

#### Configuration

The service account email can be customized via Django settings:

```python
# settings.py (optional - defaults to training-scheduler@{GCP_PROJECT_ID}.iam.gserviceaccount.com)
TRAINING_SCHEDULER_SERVICE_ACCOUNT = "custom-scheduler@project.iam.gserviceaccount.com"
```

---

## User Interface

### Best Experiments Container (2026-01-15)

The Training page now features a "Best Experiments" container that displays top-performing experiments across all model types (Retrieval, Ranking, Hybrid). This mirrors functionality from the Experiments page.

#### Layout Structure

**Upper section:** Three clickable KPI rows for Retrieval/Ranking/Hybrid, each showing experiment count and type-specific metrics (R@K for retrieval, RMSE/MAE for ranking).

**Lower section:** Top 10 configurations table for selected model type, showing experiment details, hyperparameters, and metrics. 5 rows visible with scroll.

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

### Reusable View Modal Module (2026-01-15)

The experiment view modal has been refactored into a reusable external JavaScript module that can be shared across multiple pages (Training, Experiments). This provides consistent UX and eliminates code duplication.

#### Files

| File | Size | Description |
|------|------|-------------|
| `templates/includes/_exp_view_modal.html` | 19KB | Reusable HTML template partial |
| `static/js/exp_view_modal.js` | 93KB | JavaScript module (IIFE pattern) |
| `static/css/exp_view_modal.css` | 26KB | Complete CSS styling |
| `static/js/pipeline_dag.js` | - | Pipeline DAG visualization (existing) |
| `templates/includes/_pipeline_dag.html` | - | Pipeline DAG template (existing) |

#### JavaScript API

The `ExpViewModal` module exposes the following public API:

```javascript
// Configuration (call once on page load)
ExpViewModal.configure({
    showTabs: ['overview', 'pipeline', 'data', 'training'],
    showDataInsights: true,
    showTrainingTab: true,
    fieldMapping: { ... },  // Custom field mapping for different data sources
    onClose: function() { },
    onUpdate: function(exp) { },  // Called when experiment status updates
    endpoints: {
        experimentDetails: '/api/experiments/{id}/',
        componentLogs: '/api/experiments/{id}/component-logs/',
        dataInsights: '/api/experiments/{id}/data-insights/',
        trainingData: '/api/experiments/{id}/training-data/'
    }
});

// Open modal for an experiment (fetches data from API)
ExpViewModal.open(experimentId);

// Open modal with pre-loaded data (no API call)
ExpViewModal.openWithData(experimentData);

// Close the modal
ExpViewModal.close();

// Handle overlay click (for closing on background click)
ExpViewModal.handleOverlayClick(event);

// Switch to a specific tab
ExpViewModal.switchTab(tabName);  // 'overview', 'pipeline', 'data', 'training'

// Toggle error details visibility
ExpViewModal.toggleErrorDetails();

// Refresh component logs (Pipeline tab)
ExpViewModal.refreshComponentLogs();

// Update weight analysis charts (Training tab)
ExpViewModal.updateWeightAnalysisCharts();

// Update weight histogram chart (Training tab)
ExpViewModal.updateWeightHistogramChart();

// Get current state
ExpViewModal.getState();

// Get current experiment data
ExpViewModal.getCurrentExp();
```

#### Integration Example

To integrate the reusable view modal into a page:

**1. Add CSS and JS includes in the template:**

```django
{% load static %}

<!-- In <head> section -->
<link rel="stylesheet" href="{% static 'css/exp_view_modal.css' %}?v=1">

<!-- Before closing </body> tag -->
<script src="{% static 'js/pipeline_dag.js' %}?v=1"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0"></script>
<script src="{% static 'js/exp_view_modal.js' %}?v=1"></script>
```

**2. Include the modal template:**

```django
<!-- At the end of the page, before scripts -->
{% include 'includes/_exp_view_modal.html' %}
```

**3. Configure the module on page load:**

```javascript
document.addEventListener('DOMContentLoaded', function() {
    ExpViewModal.configure({
        showTabs: ['overview', 'pipeline', 'data', 'training'],
        onUpdate: function(exp) {
            // Optional: refresh related UI when experiment updates
            refreshBestExperiments();
        }
    });
});
```

**4. Open modal from table row click:**

```javascript
function openExpDetails(expId) {
    ExpViewModal.open(expId);
}
```

#### Key Features

1. **Live Polling**: For running experiments, the modal polls the API every 3 seconds to update status and metrics.

2. **Lazy Loading**: Data Insights and Training tabs load content only when first accessed, reducing initial load time.

3. **Chart.js Integration**: Training tab displays interactive charts for:
   - Loss curves (train/eval)
   - Recall metrics (R@5, R@10, R@50, R@100)
   - Weight analysis (L1/L2 norms, distribution)
   - Weight histograms (TensorBoard-style ridgeline)

4. **Tensor Visualization**: Overview tab renders feature configurations as visual tensor bars showing proportional feature dimensions.

5. **Tower Architecture**: Model configurations display query/candidate tower layers with parameter counts.

6. **Pipeline DAG**: Pipeline tab shows TFX pipeline stages with status icons and durations.

7. **Error Handling**: Failed experiments display error details with expandable stack traces.

#### Style Alignment Fixes (2026-01-15)

The stand-alone view modal (`exp_view_modal.css/js`) was updated to match the styling of the standard view modal on the Experiments page (`model_experiments.html`). The following fixes were applied:

#### CSS Style Fixes

1. **Tab Navigation Styling**
   - Removed inline tab styles from `model_training.html` that created underline-style tabs
   - Now uses pill button style tabs with rounded borders from `exp_view_modal.css`
   - Active tab: light blue background (`#eff6ff`) with blue border (`#2563eb`)

2. **Status Icon Styling**
   - Removed conflicting status icon styles with light backgrounds
   - Now uses solid colored backgrounds with white icons (e.g., green circle with white checkmark)

3. **Results Summary / Metric Cards**
   - Removed green-tinted backgrounds (`#f0fdf4`) and green borders
   - Now uses white background with dark gray borders (`#1f2937`)
   - Metric values display in dark text instead of green

4. **Dataset Details Section**
   - Removed boxed card styling with gray backgrounds
   - Now uses flat layout with colored left-border indicators for filters:
     - Blue (`#3b82f6`) for Date filters
     - Green (`#22c55e`) for Customer filters
     - Purple (`#a855f7`) for Product filters

5. **Data Insights Tab**
   - Added missing `.exp-view-stats-summary` and `.exp-view-stat-box` styles for statistics cards
   - Added `.exp-view-features-table` styles for legacy feature tables
   - Added TFDV rich statistics table styles (`.tfdv-table-container`, `.tfdv-features-table`)
   - Added mini histogram and horizontal bar chart styles for distribution visualization
   - Updated `.exp-view-tfdv-btn` from light blue outline to purple solid button (`#4f46e5`)

6. **Training Tab Height Constraint**
   - Added `max-height: 600px` and `overflow: hidden` to `.exp-view-modal`
   - Added `min-height: 0` to `.exp-view-body` for proper flex shrinking
   - Added `max-height: 170px` to training chart canvases
   - Added fixed height constraints to `#trainingWeightHistogramChart` container (250px)
   - Added final metrics table and weight stats select dropdown styling

#### JavaScript Chart Implementations

The following chart functions in `exp_view_modal.js` were updated from placeholders to full implementations:

1. **`renderGradientChart(history, tower)`**
   - Full Chart.js line chart for Weight Norm (L1/L2)
   - Supports tower switching (Query/Candidate)
   - Blue color for Query Tower, green for Candidate Tower

2. **`renderWeightStatsChart(history, tower)`**
   - Full Chart.js line chart for Weight Distribution statistics
   - Shows Mean (blue), Std Dev (orange), Min (green dashed), Max (red dashed)
   - Displays placeholder message when weight data is unavailable

3. **`renderWeightHistogramChart(history, tower)`**
   - Full D3.js ridgeline chart for TensorBoard-style weight/gradient distributions
   - Color gradient from light orange (older epochs) to dark orange (newer epochs)
   - Supports both "Weights" and "Gradients" data types
   - Epoch labels on right side with grid lines

4. **`fetchHistogramData(history, tower, isGradients)`**
   - New async function for on-demand histogram data fetch from MLflow
   - Shows loading spinner while fetching
   - Merges histogram data into training history and re-renders chart

#### Dependency Addition

Added D3.js library to `model_training.html` for ridgeline histogram visualization:
```html
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
```

### Migration Notes

When migrating from page-specific modal code to the reusable module:

1. Remove all old modal-related functions (e.g., `populateExpViewModal`, `renderFeaturesConfigForExp`, etc.)
2. Replace inline modal HTML with `{% include 'includes/_exp_view_modal.html' %}`
3. Update `openExpDetails()` to call `ExpViewModal.open(expId)`
4. Add `ExpViewModal.configure()` call in `DOMContentLoaded`
5. Ensure all required CSS/JS files are included

---

### Unified View Modal for Training Runs (2026-01-20)

The `ExpViewModal` has been extended to support a "training_run" mode, eliminating the need for a separate `TrainingViewModal` component. This consolidation reduces code duplication and ensures consistent UX across Experiments and Training pages.

#### Mode-Based Architecture

**Experiment mode** (default): Fetches from `/api/quick-tests/{id}/`, shows experiment configs and TFDV stats.

**Training run mode**: Fetches from `/api/training-runs/{id}/`, shows 8-stage pipeline, GPU config, blessing status, and Model Registry & Deployment sections in Overview tab.

#### JavaScript API Updates

```javascript
// Open modal for an experiment (default behavior)
ExpViewModal.open(experimentId);
ExpViewModal.open(experimentId, { mode: 'experiment' });

// Open modal for a training run
ExpViewModal.open(trainingRunId, { mode: 'training_run' });

// Open with pre-loaded training run data
ExpViewModal.openWithTrainingRunData(trainingRunData);

// Get current mode and run data
ExpViewModal.getMode();           // Returns 'experiment' or 'training_run'
ExpViewModal.getCurrentRun();     // Returns training run data (training_run mode only)
ExpViewModal.getCurrentExp();     // Returns experiment data (experiment mode only)
```

#### Training Run Mode Features

1. **8-Stage Pipeline DAG**: Shows all TFX stages for production training
   - Compile → Examples → Stats → Schema → Transform → Train → Evaluate → Push
   - Status indicators: pending, running (with spinner), completed, failed

2. **Training-Specific Status Badges**: Extended status support
   - `pending`, `scheduled`, `submitting`, `running`, `completed`, `failed`, `cancelled`, `not_blessed`
   - Each status has unique header gradient and icon

3. **GPU Configuration Display**: Shows allocated GPU resources
   - GPU type (T4, L4, V100, etc.)
   - GPU count
   - Preemptible status

4. **Blessing Status Banner**: For completed/not_blessed runs
   - Green banner: "Model passed evaluation (blessed)"
   - Orange banner: "Model did not pass evaluation threshold"

5. **Model Registry Section** (in Overview tab): For completed training runs
   - Shows registration status (Not Registered, Registered, or Evaluation Failed)
   - "Push to Registry" button for blessed but unregistered models
   - Displays model name, version, and registration timestamp when registered

6. **Deployment Section** (in Overview tab): For registered models
   - Shows deployment status (Ready to Deploy or Deployed)
   - "Deploy to Vertex AI" and "Deploy to Cloud Run" buttons when not deployed
   - "Undeploy" button when currently deployed
   - Displays deployment timestamp when deployed

#### Tab Visibility by Mode

| Tab | Experiment Mode | Training Run Mode |
|-----|----------------|-------------------|
| Overview | ✅ | ✅ (includes Registry & Deployment sections) |
| Pipeline | ✅ | ✅ |
| Data Insights | ✅ | ✅ |
| Training | ✅ | ✅ |

#### CSS Additions

New status styles added to `exp_view_modal.css`:

```css
/* Scheduled status (yellow gradient) */
.exp-view-header.scheduled { ... }
.exp-view-status-icon.scheduled { background: #f59e0b; }

/* Not blessed status (orange gradient) */
.exp-view-header.not_blessed { ... }
.exp-view-status-icon.not_blessed { background: #f97316; }

/* Blessing status banner */
.exp-view-blessing-status { ... }
.exp-view-blessing-status.blessed { background: #dcfce7; color: #166534; }
.exp-view-blessing-status.not-blessed { background: #ffedd5; color: #c2410c; }
```

#### Integration Example (Training Page)

```javascript
// In model_training.html

// Configure TrainingCards to use ExpViewModal
TrainingCards.configure({
    modelId: {{ model.id }},
    onViewRun: function(runId) {
        ExpViewModal.open(runId, { mode: 'training_run' });
    }
});

// Configure ExpViewModal with callbacks
ExpViewModal.configure({
    showTabs: ['overview', 'pipeline', 'data', 'training'],
    onClose: function() {
        TrainingCards.refresh();
    },
    onUpdate: function(data) {
        TrainingCards.refresh();
    }
});
```

#### Deleted Files

The following redundant files were removed after consolidation:

| File | Lines | Reason |
|------|-------|--------|
| `static/js/training_view_modal.js` | 1,121 | Functionality merged into `exp_view_modal.js` |
| `static/css/training_view_modal.css` | 736 | Styles merged into `exp_view_modal.css` |

#### Configuration Constants

Training-specific constants added to `exp_view_modal.js`:

```javascript
// Training run status configuration
const TRAINING_STATUS_CONFIG = {
    pending: { icon: 'fa-hourglass-start', color: '#9ca3af', label: 'Pending' },
    scheduled: { icon: 'fa-clock', color: '#f59e0b', label: 'Scheduled' },
    submitting: { icon: 'fa-upload', color: '#3b82f6', label: 'Submitting' },
    running: { icon: 'fa-sync', color: '#3b82f6', label: 'Running' },
    completed: { icon: 'fa-check-circle', color: '#10b981', label: 'Completed' },
    failed: { icon: 'fa-times-circle', color: '#ef4444', label: 'Failed' },
    cancelled: { icon: 'fa-ban', color: '#6b7280', label: 'Cancelled' },
    not_blessed: { icon: 'fa-exclamation-triangle', color: '#f97316', label: 'Not Blessed' }
};

// 8-stage pipeline for training runs
const TRAINING_PIPELINE_STAGES = [
    { id: 'compile', name: 'Compile', icon: 'fa-cog' },
    { id: 'examples', name: 'Examples', icon: 'fa-database' },
    { id: 'stats', name: 'Stats', icon: 'fa-chart-bar' },
    { id: 'schema', name: 'Schema', icon: 'fa-sitemap' },
    { id: 'transform', name: 'Transform', icon: 'fa-exchange-alt' },
    { id: 'train', name: 'Train', icon: 'fa-graduation-cap' },
    { id: 'evaluate', name: 'Evaluate', icon: 'fa-check-double' },
    { id: 'push', name: 'Push', icon: 'fa-upload' }
];
```

### Data Insights Tab for Training Runs (2026-01-20)

The Training Run view modal now includes a **Data Insights** tab, providing the same dataset statistics and schema visualization available in the Experiments view modal.

#### Feature Overview

The Data Insights tab displays:
1. **Dataset Statistics Summary**
   - Total examples count
   - Total features count
   - Numeric/Categorical feature ratio
   - Average missing percentage

2. **Numeric Features Table**
   - Feature name, count, missing %, mean, std dev, zeros %, min, median, max
   - Mini histogram visualization for each feature's distribution

3. **Categorical Features Table**
   - Feature name, count, missing %, unique values
   - Top values with frequencies
   - Distribution bar charts

4. **Schema Information**
   - Feature types and constraints
   - Presence requirements

5. **Full TFDV Report Link**
   - "Open Full Report" button opens the complete TFDV visualization in a new tab

#### Implementation Details

**Backend API Endpoints** (`ml_platform/training/api.py`):

```python
# GET /api/training-runs/<id>/statistics/
def training_run_statistics(request, training_run_id):
    """Returns TFDV statistics summary for a training run."""

# GET /api/training-runs/<id>/schema/
def training_run_schema(request, training_run_id):
    """Returns schema summary for a training run."""

# GET /training/runs/<id>/tfdv/
def training_run_tfdv_page(request, training_run_id):
    """Serves full TFDV HTML visualization as standalone page."""
```

**URL Routes** (`ml_platform/training/urls.py`):

```python
path('api/training-runs/<int:training_run_id>/statistics/', ...),
path('api/training-runs/<int:training_run_id>/schema/', ...),
path('training/runs/<int:training_run_id>/tfdv/', ...),
```

**JavaScript Updates** (`static/js/exp_view_modal.js`):

1. **New Endpoint Configuration**:
   ```javascript
   endpoints: {
       // ... existing endpoints ...
       trainingRunStatistics: '/api/training-runs/{id}/statistics/',
       trainingRunSchema: '/api/training-runs/{id}/schema/',
       trainingRunTfdvReport: '/training/runs/{id}/tfdv/'
   }
   ```

2. **Tab Visibility**: Training run mode now shows same tabs as experiment mode:
   ```javascript
   if (state.mode === 'training_run') {
       visibleTabs = ['overview', 'pipeline', 'data', 'training'];
   }
   ```
   Note: Repository and Deployment tabs have been removed; their functionality is now integrated into the Overview tab as dedicated sections.

3. **Mode-Aware Data Loading**: `preloadDataInsights()` and `loadDataInsights()` now detect the mode and use appropriate endpoints.

4. **Preloading**: Data insights are preloaded in background when the training run modal opens.

#### Data Flow

**Preloading:** Modal opens → `preloadDataInsights()` calls `/api/training-runs/{id}/statistics/` and `/schema/` → ArtifactService calls tfdv-parser → Reads from GCS pipeline_root → Data cached. **On tab click:** `loadDataInsights()` renders cached data instantly.

#### Reuse of Existing Infrastructure

The implementation reuses:
- **ArtifactService**: Same service that handles experiment statistics
- **tfdv-parser microservice**: Cloud Run service for parsing TFDV artifacts
- **Pipeline root pattern**: Same GCS bucket structure (`gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}`)
- **UI components**: Same statistics cards, feature tables, and histogram visualizations

---

### Model Registry & Deployment Sections in Overview (2026-01-23)

The Training Run view modal now includes **Model Registry** and **Deployment** sections directly in the Overview tab, replacing the previous separate Repository and Deployment tabs. This consolidation provides a more streamlined view of the model lifecycle.

#### Visual Layout

Overview tab displays (in order): Results metrics (R@5/10/50/100), Model Registry section with status and push button, Deployment section with status and deploy buttons, then Dataset details.

#### Model Registry Section States

| Training Run State | Registry Section Display | Action Available |
|-------------------|--------------------------|------------------|
| Running/Pending | Hidden | - |
| Failed | Hidden | - |
| Completed, `is_blessed=false` | "Evaluation Failed" with ❌ icon | None |
| Completed, `is_blessed=true`, not registered | "Not Registered" with ⏳ icon | Push to Registry |
| Completed, registered | "Registered" with ✅ icon, shows model name/version | None |

#### Deployment Section States

| Training Run State | Deployment Section Display | Actions Available |
|-------------------|---------------------------|-------------------|
| Not registered | Hidden | - |
| Registered, not deployed | "Ready to Deploy" with ⏸️ icon | Deploy to Vertex AI, Deploy to Cloud Run |
| Registered, deployed | "Deployed" with 🚀 icon | Undeploy |

#### JavaScript API

New public API methods for training run actions:

```javascript
// Push a blessed model to the Model Registry
ExpViewModal.pushToRegistry(runId);
// POST /api/training-runs/{id}/push/

// Deploy model to Vertex AI Endpoint
ExpViewModal.deployTrainingRun(runId);
// POST /api/training-runs/{id}/deploy/

// Deploy model to Cloud Run (serverless TF Serving)
ExpViewModal.deployToCloudRun(runId);
// POST /api/training-runs/{id}/deploy-cloud-run/

// Undeploy a currently deployed model
ExpViewModal.undeployTrainingRun(runId);
// POST /api/models/{modelId}/undeploy/
```

#### CSS Classes

New styles added to `exp_view_modal.css`:

```css
/* Outcome section container */
.exp-view-outcome-section { ... }

/* Status row with icon */
.exp-view-outcome-status { ... }
.exp-view-outcome-status.registered { ... }
.exp-view-outcome-status.deployed { ... }
.exp-view-outcome-status.idle { ... }
.exp-view-outcome-status.pending { ... }
.exp-view-outcome-status.not-blessed { ... }

/* Status icon styling */
.exp-view-outcome-icon { ... }

/* Action buttons */
.btn-outcome-action { ... }
.btn-outcome-action.btn-secondary { ... }
.btn-outcome-action.btn-danger { ... }
```

#### Files Modified

| File | Changes |
|------|---------|
| `templates/includes/_exp_view_modal.html` | Removed Repository/Deployment tabs, added Registry/Deployment sections to Overview |
| `static/js/exp_view_modal.js` | Added `renderRegistrySection()`, `renderDeploymentSection()`, action handlers |
| `static/css/exp_view_modal.css` | Added outcome section styles (~80 lines) |

---

### Dynamic Deployment Status (2026-01-26)

Deployment status is now **dynamically queried from Vertex AI endpoint** rather than stored in the database. This ensures the endpoint is the single source of truth for deployment state.

#### Architecture Change

**Before (Database-driven):**
```
TrainingRun.is_deployed = True/False (database field)
TrainingRun.deployed_at = timestamp (database field)
TrainingRun.endpoint_resource_name = "projects/.../endpoints/..." (database field)
RegisteredModel.is_deployed = True/False (database field)
RegisteredModel.deployed_version_id = 123 (database field)
```

**After (Vertex AI-driven):**
```
# Deployment status queried dynamically from Vertex AI
service = TrainingService(model_endpoint)
endpoint_info = service.get_deployed_model_resource_names()
# Returns: {'deployed_models': set(), 'endpoint_resource_name': str, 'error': str}

is_deployed = training_run.vertex_model_resource_name in endpoint_info['deployed_models']
```

#### Key Changes

| Component | Change |
|-----------|--------|
| `TrainingRun` model | Removed: `is_deployed`, `deployed_at`, `endpoint_resource_name` fields |
| `RegisteredModel` model | Removed: `is_deployed`, `deployed_version_id` fields |
| `TrainingService` | Added: `get_deployed_model_resource_names()` method |
| `TrainingService.deploy_model()` | Removed database field updates, validation uses dynamic check |
| `TrainingService.undeploy_model()` | Queries endpoint by display name instead of stored resource name |
| API serializers | Accept `deployed_models` parameter, derive status dynamically |
| API endpoints | Query endpoint once per request, pass to serializers |
| KPI calculations | Computed in memory using dynamic deployment status |
| `RegisteredModelService` | Removed: `update_deployment_status()` method |
| Admin config | Removed `is_deployed` from list_filter and fieldsets |

#### New TrainingService Method

```python
def get_deployed_model_resource_names(self) -> dict:
    """
    Query Vertex AI endpoint to get currently deployed model resource names.

    Returns:
        Dict with:
            - deployed_models: Set of vertex_model_resource_name strings
            - endpoint_resource_name: The endpoint resource name (or None)
            - error: Error message if query failed (or None)
    """
```

#### Status Derivation Logic

```python
# In _serialize_registered_model()
if endpoint_error:
    model_status = 'unknown'
elif deployed_models is not None:
    is_deployed = training_run.vertex_model_resource_name in deployed_models
    if is_deployed:
        model_status = 'deployed'
    elif training_run.is_blessed:
        model_status = 'idle'
    else:
        model_status = 'not_blessed'
else:
    model_status = 'idle' if training_run.is_blessed else 'not_blessed'
```

#### Error Handling

| Scenario | Behavior |
|----------|----------|
| Vertex AI API fails | `model_status = 'unknown'`, `endpoint_error` included in response |
| No endpoint exists | All models treated as not deployed |
| Model not on endpoint | Treated as not deployed |

#### Migration

Migration `0009_remove_deployment_fields.py` removes:
- `trainingrun.is_deployed`
- `trainingrun.deployed_at`
- `trainingrun.endpoint_resource_name`
- `registeredmodel.is_deployed`
- `registeredmodel.deployed_version_id`

#### Benefits

1. **Single source of truth**: Vertex AI endpoint state is authoritative
2. **No stale data**: Status always reflects actual endpoint state
3. **Simpler model**: Fewer fields to maintain and synchronize
4. **Resilient**: Graceful degradation when API unavailable (shows "unknown")

---

### Training Runs List View

The Training cards use a unified 4-column horizontal layout shared with the Experiments page (via `cards.css`):

**Layout Structure:**
- Column 1 (30%): Info - Status icon, run name, timestamp, config details, GPU chip
- Column 2 (20%): Config - Dataset, Features, Model badges
- Column 3 (30%): Metrics - Duration, Cost, Recall@100 in bordered boxes
- Column 4 (20%): Actions - View/Deploy/Delete buttons, status badges
- Footer: 8-stage TFX pipeline progress bar (Compile→Examples→Stats→Schema→Transform→Train→Evaluator→Pusher)

Each card displays running/completed/failed states with status icons (🔄/✅/❌), 8-stage pipeline progress bar, and appropriate action buttons based on status.

**Shared CSS Architecture:**
- `cards.css` - Unified card layout classes used by both Training and Experiments pages
- `training_cards.css` - Training-specific styles (filters, error display, badges, pagination)

**Key CSS Classes (from cards.css):**
- `.ml-card` - Base card container
- `.ml-card-columns` - 4-column flex layout
- `.ml-card-col-info`, `.ml-card-col-config`, `.ml-card-col-metrics`, `.ml-card-col-actions`
- `.ml-card-stages` - Stage progress bar container
- `.ml-stage-segment` - Individual stage segment with status colors

### Models Registry Chapter

The Models Registry chapter displays production-ready models registered in Vertex AI Model Registry. See `docs/models_registry.md` for full specifications.

#### UI Components

| Component | Purpose |
|-----------|---------|
| **KPI Summary Row** | Total models, Blessed, Deployed, Idle counts, Latest registration date |
| **Training Schedule Grid** | GitHub-style activity grid showing past 10 weeks + next 30 weeks of scheduled training |
| **Filter Bar** | Type (All/Retrieval/Ranking/Multitask), Status (All/Blessed/Deployed/Idle), Sort, Search |
| **Registered Models Table** | Model name, type, version, metrics (R@100/RMSE), status badge, actions dropdown |

#### Model View Modal

Opens when clicking a model row. 5 tabs:
- **Overview**: Model metadata, latest version info, deployment status, metrics summary
- **Versions**: Version history table with metrics comparison
- **Artifacts**: Links to GCS paths, MLflow runs, TensorBoard logs
- **Deployment**: Current deployment status, Deploy/Undeploy actions
- **Lineage**: Source training run, dataset, feature config, model config

#### Key Features

- **Automatic Model Registration**: Models are auto-registered to Vertex AI when Pusher completes successfully
- **Native Versioning**: Uses Vertex AI's native model versioning (v1, v2, etc.) instead of separate model names
- **Dynamic Status**: Deployment status is queried from Vertex AI endpoint (single source of truth)
- **Schedule Grid Integration**: Shows when models will be retrained based on TrainingSchedule

### Rerun Feature (2026-01-23)

The Rerun feature allows users to create a new training run with the same configuration as an existing completed run.

#### How It Works

1. **Trigger**: Click the "Rerun" button on any training run card in a terminal state (completed, failed, cancelled, not_blessed)

2. **Process**:
   - Creates a new TrainingRun with identical configuration (dataset, feature config, model config, training params, GPU config, evaluator config)
   - Copies `schedule_config` from the source run (without the `cloud_scheduler_job_name` to avoid conflicts)
   - Auto-submits the new pipeline to Vertex AI
   - Assigns a new `run_number` while keeping the same `name`

3. **Confirmation**: Shows a confirmation modal before proceeding

#### Backend Implementation

```python
# services.py - rerun_training_run method
def rerun_training_run(self, training_run: TrainingRun) -> TrainingRun:
    # Only allow rerun for terminal states
    TERMINAL_STATUSES = [STATUS_COMPLETED, STATUS_FAILED, STATUS_NOT_BLESSED, STATUS_CANCELLED]

    # Create new run with same config
    new_run = self.create_training_run(
        name=training_run.name,
        description=f"Re-run of {training_run.display_name}",
        dataset=training_run.dataset,
        feature_config=training_run.feature_config,
        model_config=training_run.model_config,
        training_params=training_run.training_params,
        gpu_config=training_run.gpu_config,
        evaluator_config=training_run.evaluator_config,
        ...
    )

    # Copy schedule_config (without cloud_scheduler_job_name)
    if training_run.schedule_config:
        new_run.schedule_config = {
            k: v for k, v in training_run.schedule_config.items()
            if k != 'cloud_scheduler_job_name'
        }
        new_run.save(update_fields=['schedule_config'])

    # Auto-submit the new run
    self.submit_training_pipeline(new_run)
    return new_run
```

#### API Endpoint

```
POST /api/training-runs/<id>/rerun/

Response:
{
    "success": true,
    "training_run": { ... new run details ... },
    "message": "Re-run created as Training #48"
}
```

### Edit Feature (2026-01-23)

The Edit feature allows users to modify training run configuration (epochs, batch_size, GPU settings, schedule) directly on an existing TrainingRun. Any completed run can serve as a template for future scheduled runs.

#### Key Design Decisions

1. **Schedule config embedded in TrainingRun** - Uses a `schedule_config` JSONField, no separate entity
2. **Show saved (current) config** - When editing, displays the latest saved configuration
3. **Any completed run can be a template** - No special designation needed
4. **No versioning** - Just keeps the latest config

#### Schedule Config Schema

```json
{
  "schedule_type": "now|once|daily|weekly",
  "schedule_time": "HH:MM",
  "schedule_day_of_week": 0-6,
  "schedule_timezone": "UTC",
  "scheduled_datetime": "ISO-8601",
  "cloud_scheduler_job_name": "projects/.../jobs/..."
}
```

#### User Flow

1. **Trigger**: Click the "Edit" button (pencil icon) on any training run card in a terminal state

2. **Wizard Opens in Edit Mode**:
   - Skips Step 1 (experiment selection) - locked to existing config
   - Opens directly at Step 2 (Training Parameters)
   - Pre-fills all fields with current configuration
   - Step counter shows "Step 1 of 2" / "Step 2 of 2"

3. **Editable Fields**:
   - Training parameters (epochs, batch size, learning rate, early stopping)
   - GPU configuration (GPU type, count, preemptible)
   - Evaluator settings (enabled, blessing threshold)
   - Schedule configuration (now, once, daily, weekly)

4. **Save**: Click "Save" button to persist changes

#### Backend Implementation

**Model Field** (`models.py`):
```python
class TrainingRun(models.Model):
    # ... existing fields ...

    schedule_config = models.JSONField(
        default=dict,
        help_text="Embedded schedule configuration"
    )
```

**API Endpoints** (`api.py`):

```
GET /api/training-runs/<id>/config/

Response:
{
    "success": true,
    "config": {
        "id": 123,
        "name": "model-v1",
        "dataset_id": 1,
        "dataset_name": "...",
        "feature_config_id": 2,
        "model_config_id": 3,
        "training_params": { "epochs": 150, "batch_size": 8192, ... },
        "gpu_config": { "gpu_type": "NVIDIA_TESLA_T4", "gpu_count": 2, ... },
        "evaluator_config": { ... },
        "schedule_config": { "schedule_type": "weekly", "schedule_time": "09:00", ... }
    }
}
```

```
PATCH /api/training-runs/<id>/config/

Request:
{
    "training_params": { "epochs": 300, "batch_size": 16384, ... },
    "gpu_config": { "gpu_type": "NVIDIA_TESLA_T4", "gpu_count": 4 },
    "evaluator_config": { ... },
    "schedule_config": { "schedule_type": "daily", "schedule_time": "02:00", ... }
}

Response:
{
    "success": true,
    "config": { ... updated config ... },
    "updated_fields": ["training_params", "gpu_config", "schedule_config"]
}
```

**Schedule Webhook** (for Cloud Scheduler):
```
POST /api/training-runs/<id>/schedule-webhook/

- Called by Cloud Scheduler when a scheduled training should trigger
- Reads the template training run's CURRENT config
- Creates a new TrainingRun with copied config
- Submits the pipeline
```

#### Frontend Implementation

**State Changes** (`training_wizard.js`):
```javascript
let state = {
    editMode: false,      // Edit mode flag
    editRunId: null,      // Training run ID being edited
    // ... existing state
};
```

**Key Functions**:
- `openForEdit(runId)` - Opens wizard in edit mode, loads config from API
- `loadTrainingRunConfig(runId)` - Fetches config via GET `/api/training-runs/{id}/config/`
- `submitEditMode()` - Saves config via PATCH
- `buildEditPayload()` - Constructs the PATCH request body
- `updateSubmitButtonText()` - Shows "Save" in edit mode

**Training Cards Integration** (`training_cards.js`):
```javascript
function editRun(runId) {
    if (typeof TrainingWizard !== 'undefined' && TrainingWizard.openForEdit) {
        TrainingWizard.openForEdit(runId);
    } else {
        showToast('Edit feature not available', 'error');
    }
}
```

#### Cloud Scheduler Integration

When a schedule is configured (daily/weekly), the system:

1. **Creates Cloud Scheduler Job**:
   - Builds cron expression from schedule config
   - Creates HTTP target pointing to the webhook endpoint
   - Uses OIDC authentication

2. **Updates Schedule**:
   - Deletes old Cloud Scheduler job if schedule type changed
   - Creates new job with updated schedule

3. **Webhook Trigger**:
   - Cloud Scheduler calls the webhook at scheduled time
   - Webhook creates new TrainingRun with template's current config
   - Submits pipeline automatically

#### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/training/models.py` | Added `schedule_config` JSONField |
| `ml_platform/training/api.py` | Added GET/PATCH config endpoints, webhook |
| `ml_platform/training/urls.py` | Added URL routes for new endpoints |
| `ml_platform/training/services.py` | Added Cloud Scheduler methods, updated rerun |
| `static/js/training_wizard.js` | Added edit mode support |
| `static/js/training_cards.js` | Updated `editRun()` function |
| `static/css/modals.css` | Added `.progress-step-pill.hidden` style |

### Schedule Feature (2026-01-23)

The Schedule feature enables users to create recurring training schedules from existing training runs or registered models. Schedules are managed via Google Cloud Scheduler, which triggers webhook endpoints to execute training pipelines automatically.

#### Architecture Overview

The schedule system consists of:
1. **TrainingSchedule Model** - Django model storing schedule configuration and statistics
2. **TrainingScheduleService** - Service layer for Cloud Scheduler integration
3. **Schedule Modal Component** - Reusable frontend modal for creating schedules
4. **Webhook Endpoint** - Receives Cloud Scheduler triggers and executes training

**Flow:** User clicks Schedule → ScheduleModal opens → POST to `/api/training/schedules/from-run/` → TrainingSchedule saved → TrainingScheduleService creates Cloud Scheduler job → At scheduled time, Cloud Scheduler calls webhook → New TrainingRun created and submitted.

#### Schedule Types (Updated 2026-01-25)

| Type | Cron Pattern | Description |
|------|--------------|-------------|
| `once` | `MM HH DD MM *` | One-time execution at specific datetime |
| `hourly` | `MM * * * *` | Executes every hour at specified minute (:00, :15, :30, :45) |
| `daily` | `MM HH * * *` | Executes daily at specified time |
| `weekly` | `MM HH * * D` | Executes weekly on specified day at specified time |
| `monthly` | `MM HH DD * *` | Executes monthly on specified day (1-31) at specified time |

**Note:** For monthly schedules, days 29-31 may be skipped in shorter months (Feb, Apr, Jun, Sep, Nov).

#### TrainingSchedule Model

```python
class TrainingSchedule(models.Model):
    # Schedule Types (Updated 2026-01-25)
    SCHEDULE_TYPE_ONCE = 'once'
    SCHEDULE_TYPE_HOURLY = 'hourly'
    SCHEDULE_TYPE_DAILY = 'daily'
    SCHEDULE_TYPE_WEEKLY = 'weekly'
    SCHEDULE_TYPE_MONTHLY = 'monthly'

    # Status
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    # Core Fields
    name = CharField(max_length=100)
    description = TextField(blank=True)
    ml_model = ForeignKey('ModelEndpoint', CASCADE)

    # Schedule Configuration
    schedule_type = CharField(choices=[...])
    scheduled_datetime = DateTimeField(null=True)  # For 'once'
    schedule_time = TimeField(null=True)           # For 'hourly' (minute only), 'daily', 'weekly', 'monthly'
    schedule_day_of_week = IntegerField(null=True) # 0=Monday, 6=Sunday (for 'weekly')
    schedule_day_of_month = IntegerField(null=True) # 1-31 (for 'monthly')
    schedule_timezone = CharField(default='UTC')

    # Training Configuration (frozen at creation)
    dataset = ForeignKey('Dataset', PROTECT)
    feature_config = ForeignKey('FeatureConfig', PROTECT)
    model_config = ForeignKey('ModelConfig', PROTECT)
    base_experiment = ForeignKey('QuickTest', SET_NULL, null=True)
    training_params = JSONField(default=dict)
    gpu_config = JSONField(default=dict)
    evaluator_config = JSONField(default=dict)
    deployment_config = JSONField(default=dict)

    # Cloud Scheduler
    cloud_scheduler_job_name = CharField(max_length=500, blank=True)

    # Statistics
    status = CharField(default=STATUS_ACTIVE)
    last_run_at = DateTimeField(null=True)
    next_run_at = DateTimeField(null=True)
    total_runs = IntegerField(default=0)
    successful_runs = IntegerField(default=0)
    failed_runs = IntegerField(default=0)

    @property
    def is_active(self):
        return self.status == self.STATUS_ACTIVE

    @property
    def is_recurring(self):
        return self.schedule_type in (
            self.SCHEDULE_TYPE_HOURLY,
            self.SCHEDULE_TYPE_DAILY,
            self.SCHEDULE_TYPE_WEEKLY,
            self.SCHEDULE_TYPE_MONTHLY
        )

    @property
    def success_rate(self):
        if self.total_runs == 0:
            return None
        return (self.successful_runs / self.total_runs) * 100
```

#### API Endpoints

##### Create Schedule from Training Run
```
POST /api/training/schedules/from-run/

Request (Weekly example):
{
    "source_training_run_id": 123,
    "name": "Weekly Product Model Retraining",
    "description": "Retrain product recommender every Monday",
    "schedule_type": "weekly",
    "schedule_time": "09:00",
    "schedule_day_of_week": 0,
    "schedule_timezone": "Europe/Warsaw"
}

Request (Hourly example):
{
    "source_training_run_id": 123,
    "name": "Hourly Model Update",
    "schedule_type": "hourly",
    "schedule_time": "00:30",   // Run at :30 each hour
    "schedule_timezone": "UTC"
}

Request (Monthly example):
{
    "source_training_run_id": 123,
    "name": "Monthly Full Retraining",
    "schedule_type": "monthly",
    "schedule_time": "02:00",
    "schedule_day_of_month": 15,   // 15th of each month
    "schedule_timezone": "Europe/Warsaw"
}

Response:
{
    "success": true,
    "schedule": {
        "id": 456,
        "name": "Weekly Product Model Retraining",
        "schedule_type": "weekly",
        "next_run_at": "2026-01-27T09:00:00+01:00",
        ...
    },
    "message": "Schedule 'Weekly Product Model Retraining' created successfully"
}
```

##### Preview Schedule Configuration
```
GET /api/training/schedules/preview/?source_run_id=123

Response:
{
    "success": true,
    "preview": {
        "source_run_id": 123,
        "source_run_name": "product_model_v3",
        "source_run_number": 5,
        "dataset_id": 1,
        "dataset_name": "Q4 Product Data",
        "feature_config_id": 2,
        "feature_config_name": "Standard Features",
        "model_config_id": 3,
        "model_config_name": "Retrieval Two-Tower",
        "model_type": "retrieval",
        "training_params": {...},
        "gpu_config": {...}
    }
}
```

##### Other Schedule Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/training/schedules/` | List all schedules |
| POST | `/api/training/schedules/` | Create schedule (full config) |
| GET | `/api/training/schedules/{id}/` | Get schedule details |
| PUT | `/api/training/schedules/{id}/` | Edit schedule (timing only) |
| DELETE | `/api/training/schedules/{id}/` | Delete schedule |
| POST | `/api/training/schedules/{id}/pause/` | Pause schedule |
| POST | `/api/training/schedules/{id}/resume/` | Resume schedule |
| POST | `/api/training/schedules/{id}/cancel/` | Cancel schedule |
| POST | `/api/training/schedules/{id}/trigger/` | Trigger immediately |
| POST | `/api/training/schedules/{id}/webhook/` | Webhook for Cloud Scheduler |

#### TrainingScheduleService

The service handles all Cloud Scheduler interactions:

```python
class TrainingScheduleService:
    def __init__(self, ml_model):
        self.ml_model = ml_model
        self.project_id = ml_model.gcp_project_id
        self.region = settings.CLOUD_SCHEDULER_REGION

    def create_schedule(self, schedule, webhook_base_url) -> Dict:
        """Creates Cloud Scheduler job with HTTP target"""
        # Generates cron expression from schedule config
        # Creates job with OIDC authentication
        # Updates schedule with job name and next_run_at

    def execute_scheduled_training(self, schedule) -> TrainingRun:
        """Called by webhook to create and submit training run"""
        # Creates TrainingRun with schedule's frozen config
        # Submits pipeline via TrainingService
        # Updates schedule statistics

    def pause_schedule(self, schedule) -> Dict:
        """Pauses Cloud Scheduler job"""

    def resume_schedule(self, schedule) -> Dict:
        """Resumes Cloud Scheduler job"""

    def delete_schedule(self, schedule) -> Dict:
        """Deletes Cloud Scheduler job"""

    def trigger_now(self, schedule) -> Dict:
        """Manually triggers schedule execution"""

    def update_schedule(self, schedule, webhook_base_url, update_data) -> Dict:
        """Updates schedule timing fields and Cloud Scheduler job"""
        # Only editable: name, description, schedule_type, schedule_time,
        # schedule_day_of_week, schedule_day_of_month, schedule_timezone,
        # scheduled_datetime
        # Training config (training_params, gpu_config, etc.) remains frozen
```

#### Frontend Components

##### Schedule Modal (schedule_modal.js)

IIFE module pattern with public API:

```javascript
const ScheduleModal = (function() {
    // Configuration
    let config = {
        endpoints: {
            preview: '/api/training/schedules/preview/',
            createFromRun: '/api/training/schedules/from-run/'
        },
        onSuccess: null
    };

    // State (Updated 2026-01-25)
    let state = {
        mode: null,              // 'training_run' or 'model'
        sourceId: null,
        sourceData: null,
        scheduleConfig: {
            name: '',
            scheduleType: 'daily',
            scheduleTime: '09:00',
            scheduleMinute: 0,       // For 'hourly' (0, 15, 30, 45)
            scheduleDayOfWeek: 0,    // For 'weekly' (0=Monday, 6=Sunday)
            scheduleDayOfMonth: 1,   // For 'monthly' (1-31)
            scheduleTimezone: 'UTC'
        }
    };

    // Public API
    return {
        configure: function(options) {...},
        openForTrainingRun: function(runId) {...},
        openForModel: function(modelId) {...},
        openForEdit: function(scheduleId) {...},   // Edit existing schedule
        close: function() {...},
        onScheduleTypeChange: function(type) {...},
        selectDay: function(day) {...},
        selectMinute: function(minute) {...},      // New for hourly
        selectDayOfMonth: function(day) {...},     // New for monthly
        create: function() {...}
    };
})();
```

##### Schedule Modal UI Layout (Updated 2026-01-25)

The modal displays: model name (read-only), schedule name input, schedule type buttons (Once/Hourly/Daily/Weekly/Monthly), and type-specific fields:
- **Once**: Date/time picker
- **Hourly**: Minute selector (:00/:15/:30/:45)
- **Daily**: Time picker
- **Weekly**: Time picker + day-of-week selector (Mon-Sun)
- **Monthly**: Day grid (1-31, with 29-31 highlighted as potentially skipped) + time picker

Footer shows next run preview and Create/Cancel buttons.

#### Integration Points

##### Training Cards ("Schedule" Button)

```javascript
// training_cards.js - scheduleRun()
function scheduleRun(runId) {
    ScheduleModal.configure({
        onSuccess: function(schedule) {
            showToast(`Schedule "${schedule.name}" created`, 'success');
            loadTrainingRuns();
        }
    });
    ScheduleModal.openForTrainingRun(runId);
}
```

##### View Modal ("Schedule Retraining" Button)

Added to Registry & Deployment section for registered models:

```javascript
// exp_view_modal.js - renderRegistryDeploymentSection()
<button class="btn-outcome-action btn-schedule"
        onclick="ExpViewModal.scheduleRetraining(${data.id})">
    <i class="fas fa-calendar-alt"></i> Schedule Retraining
</button>
```

#### Files Summary

##### New Files
| File | Purpose |
|------|---------|
| `templates/includes/_schedule_modal.html` | Reusable modal HTML template |
| `static/js/schedule_modal.js` | Modal JavaScript module (IIFE) |
| `static/css/schedule_modal.css` | Modal styling |

##### Modified Files
| File | Changes |
|------|---------|
| `ml_platform/training/api.py` | Added `training_schedule_from_run`, `training_schedule_preview` endpoints |
| `ml_platform/training/urls.py` | Added URL patterns for new endpoints |
| `static/js/training_cards.js` | Updated `scheduleRun()` to use ScheduleModal |
| `static/js/exp_view_modal.js` | Added `scheduleRetraining()` function, "Schedule Retraining" button |
| `static/css/exp_view_modal.css` | Added `.btn-schedule` button styling |
| `templates/ml_platform/model_training.html` | Added modal include and script/CSS imports |

#### Usage Flow

1. **From Training Cards**:
   - User clicks "Schedule" on a completed training run card
   - Schedule modal opens with source run's configuration displayed
   - User configures schedule name, type, time, timezone
   - On submit, Cloud Scheduler job is created
   - Success toast shown, training runs list refreshed

2. **From Model Registry**:
   - User opens completed training run in View Modal
   - Goes to Overview tab → Registry & Deployment section
   - Clicks "Schedule Retraining" button
   - View modal closes, Schedule modal opens
   - Same flow as above

3. **Scheduled Execution**:
   - Cloud Scheduler triggers webhook at scheduled time
   - Webhook creates new TrainingRun with frozen configuration
   - Training pipeline submitted to Vertex AI
   - Schedule statistics updated (total_runs, last_run_at, next_run_at)

### RegisteredModel Entity (2026-01-25)

The `RegisteredModel` entity restructures the Schedule functionality to properly relate to registered models instead of individual training runs. This creates a 1:1 relationship between a named model and its schedule, with all training run versions linked to the same RegisteredModel.

#### Motivation

**Problem with Previous Design:**
- Schedules were created from individual TrainingRuns
- No clear relationship between scheduled model versions
- Difficult to track all versions of a model
- Schedule could be created for any training run, leading to confusion

**New Design Goals:**
- One schedule per model name (1:1 relationship enforced)
- All versions of a model link to the same RegisteredModel
- Schedule attaches to RegisteredModel, not individual TrainingRuns
- RegisteredModel created when first training run is set up (before Vertex AI registration)

#### Architecture Overview

**Relationships:** RegisteredModel (1) → TrainingRun versions (N) and RegisteredModel (1) ↔ TrainingSchedule (1). Each TrainingRun links back to its RegisteredModel via `registered_model` FK. The schedule attaches to the RegisteredModel, not individual runs.

#### Workflow Supported

1. **Create:** User creates training run → RegisteredModel created (pre-Vertex) → TrainingSchedule linked → TrainingRun submitted
2. **First completion:** Pusher registers to Vertex AI as v1 → RegisteredModel updated with resource info
3. **Schedule trigger:** New TrainingRun from frozen config → Completes → Registers as v2 → Version cache updated

#### RegisteredModel Model

```python
class RegisteredModel(models.Model):
    """
    Represents a named model that can have multiple versions.
    Each version is a TrainingRun. A schedule attaches to this model.
    """

    MODEL_TYPE_CHOICES = [
        ('retrieval', 'Retrieval'),
        ('ranking', 'Ranking'),
        ('multitask', 'Multitask'),
    ]

    # Relationships
    ml_model = ForeignKey('ModelEndpoint', CASCADE, related_name='registered_models')

    # Model Identity
    model_name = CharField(max_length=255)  # becomes vertex_model_name
    model_type = CharField(max_length=20, choices=MODEL_TYPE_CHOICES)
    description = TextField(blank=True)

    # Vertex AI State (populated after first registration)
    vertex_model_resource_name = CharField(max_length=500, blank=True)
    first_registered_at = DateTimeField(null=True, blank=True)

    # Latest Version Cache (for fast lookups)
    latest_version_id = IntegerField(null=True, blank=True)
    latest_version_number = CharField(max_length=100, blank=True)
    total_versions = IntegerField(default=0)

    # Deployment Status
    is_deployed = BooleanField(default=False)
    deployed_version_id = IntegerField(null=True, blank=True)

    # Status & Metadata
    is_active = BooleanField(default=True)
    created_by = ForeignKey(User, SET_NULL, null=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['ml_model', 'model_name']  # Enforces uniqueness per endpoint

    @property
    def has_schedule(self):
        """Check if this model has an associated schedule."""
        return hasattr(self, 'schedule') and self.schedule is not None

    @property
    def is_registered(self):
        """Check if this model has been registered to Vertex AI."""
        return bool(self.vertex_model_resource_name)
```

#### Relationship Changes

**TrainingSchedule - Added Field:**
```python
class TrainingSchedule(models.Model):
    # ... existing fields ...

    registered_model = OneToOneField(
        'RegisteredModel',
        on_delete=CASCADE,
        null=True,  # Nullable for migration
        related_name='schedule'  # Access via registered_model.schedule
    )
```

**TrainingRun - Added Field:**
```python
class TrainingRun(models.Model):
    # ... existing fields ...

    registered_model = ForeignKey(
        'RegisteredModel',
        on_delete=SET_NULL,
        null=True,
        related_name='versions'  # Access all versions via registered_model.versions
    )
```

#### RegisteredModelService

New service class for managing RegisteredModel entities:

```python
class RegisteredModelService:
    def __init__(self, ml_model):
        self.ml_model = ml_model

    def get_or_create_for_training(self, model_name, model_type='retrieval',
                                    description='', created_by=None) -> RegisteredModel:
        """
        Get or create a RegisteredModel for a training run.
        Called when creating new training runs.
        """

    def update_after_registration(self, registered_model, training_run):
        """
        Update RegisteredModel after Vertex AI registration.
        Called when Pusher successfully registers a model version.
        Updates: first_registered_at, vertex_model_resource_name,
                 latest_version_id, latest_version_number, total_versions
        """

    def update_deployment_status(self, registered_model):
        """
        Update deployment status based on versions.
        Syncs is_deployed and deployed_version_id from TrainingRuns.
        """

    def check_name_available(self, model_name) -> dict:
        """
        Check if a model name is available or already exists.
        Returns: { exists, registered_model_id, has_schedule, schedule_id }
        """
```

#### API Endpoints

##### New RegisteredModel Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/registered-models/` | List RegisteredModels with schedule info |
| GET | `/api/registered-models/<id>/` | Get RegisteredModel details |
| GET | `/api/registered-models/<id>/versions/` | List all versions (TrainingRuns) |
| GET | `/api/registered-models/check-name/?name=X` | Check if name exists, has schedule |

##### List RegisteredModels
```
GET /api/registered-models/?model_type=retrieval&has_schedule=true

Response:
{
    "success": true,
    "registered_models": [
        {
            "id": 1,
            "model_name": "product-retrieval-v1",
            "model_type": "retrieval",
            "status": "deployed",
            "is_registered": true,
            "total_versions": 3,
            "has_schedule": true,
            "schedule_id": 5,
            "schedule_status": "active",
            ...
        }
    ],
    "kpi": {
        "total": 10,
        "registered": 8,
        "with_schedule": 4,
        "deployed": 2
    },
    "pagination": {...}
}
```

##### Check Name Availability
```
GET /api/registered-models/check-name/?name=product-model

Response:
{
    "success": true,
    "exists": true,
    "registered_model_id": 123,
    "has_schedule": true,
    "schedule_id": 456
}
```

##### Updated Schedule Creation Endpoint

The `/api/training/schedules/from-run/` endpoint now:
1. Gets or creates RegisteredModel using source run's model name
2. Validates that model doesn't already have a schedule (rejects with error)
3. Links new schedule to RegisteredModel
4. Links source TrainingRun to RegisteredModel if not already linked

```
POST /api/training/schedules/from-run/

Error Response (if model has schedule):
{
    "success": false,
    "error": "Model 'product-model' already has a schedule (ID: 456). Each model can only have one schedule."
}
```

#### Frontend Changes

##### Models Registry Table - Schedule Column

Added new "Schedule" column showing schedule status:
- **Scheduled** (green) - Model has active schedule
- **Paused** (yellow) - Model has paused schedule
- **None** (gray) - Model has no schedule

##### Models Registry Actions

New actions in dropdown menu:
- **Create Schedule** - Opens ScheduleModal for models without schedule
- **View Schedule** - Navigates to schedule for models with schedule

##### Training Wizard - Name Validation

Enhanced name validation to check RegisteredModel API:
1. Checks if model name already exists
2. If exists and has schedule, shows warning message
3. Disables schedule creation in wizard if model already has schedule

```javascript
// training_wizard.js - checkNameAvailability()
async function checkNameAvailability(name) {
    // Check RegisteredModel API
    const response = await fetch(`/api/registered-models/check-name/?name=${name}`);
    const data = await response.json();

    if (data.has_schedule) {
        // Show warning: "This model already has a schedule..."
        state.modelHasSchedule = true;
        state.formData.scheduleConfig.type = 'now';  // Force immediate run
    }
}
```

##### Schedule Modal - RegisteredModel Support

Added `openForRegisteredModel()` function:

```javascript
// schedule_modal.js
ScheduleModal.openForRegisteredModel(registeredModelId);
// - Loads RegisteredModel details
// - Checks if already has schedule (shows error if so)
// - Uses latest version's config as template
```

#### Migration

Migration `0007_add_registered_model.py` includes:

1. **Schema Changes:**
   - Creates `RegisteredModel` table
   - Adds `registered_model` FK to `TrainingRun` (nullable)
   - Adds `registered_model` OneToOne to `TrainingSchedule` (nullable)
   - Adds unique constraint on `(ml_model, model_name)`

2. **Data Migration:**
   - Creates RegisteredModels from existing TrainingRuns with `vertex_model_name`
   - Groups TrainingRuns by model name
   - Links all runs in group to same RegisteredModel
   - Links existing TrainingSchedules to RegisteredModels based on their runs

#### Files Summary

##### New Files
| File | Purpose |
|------|---------|
| `ml_platform/training/registered_model_service.py` | Service class for RegisteredModel operations |
| `ml_platform/training/migrations/0007_add_registered_model.py` | Migration with data migration |

##### Modified Files
| File | Changes |
|------|---------|
| `ml_platform/training/models.py` | Added RegisteredModel class, FKs to TrainingSchedule & TrainingRun |
| `ml_platform/training/services.py` | Updated create_training_run, _register_to_model_registry |
| `ml_platform/training/schedule_service.py` | Updated execute_scheduled_training |
| `ml_platform/training/api.py` | Added RegisteredModel endpoints, updated schedule validation |
| `ml_platform/training/urls.py` | Added RegisteredModel URL patterns |
| `static/js/models_registry.js` | Added Schedule column, Create/View Schedule actions |
| `static/js/training_wizard.js` | Enhanced name validation with RegisteredModel check |
| `static/js/schedule_modal.js` | Added openForRegisteredModel function |

#### Expected Results

1. **One Schedule Per Model**: Database and API enforce 1:1 relationship
2. **Version Tracking**: All versions of a model accessible via `registered_model.versions`
3. **Schedule Status in UI**: Models Registry shows schedule status for each model
4. **Validation**: Cannot create duplicate schedules for same model name
5. **Backward Compatibility**: Existing data migrated, existing schedules continue working

### Unified Scheduling in Training Wizard (2026-01-26)

The Training Wizard now provides a unified scheduling experience, allowing users to either run training immediately or create a schedule directly from the wizard. This replaces the previous inline schedule options with two dedicated action buttons that integrate with the full ScheduleModal.

#### UI Changes

**Previous Design (Replaced):**
```
┌─────────────────────────────────────────────────────────────────┐
│ 🕐 Schedule                                                     │
├─────────────────────────────────────────────────────────────────┤
│ [Run Now] [Schedule Once] [Daily] [Weekly]                      │
│ Time: [09:00]  Day: [Monday]  Timezone: [UTC]                   │
└─────────────────────────────────────────────────────────────────┘
```

**New Design:**
```
┌─────────────────────────────────────────────────────────────────┐
│ ┌─────────────────────┐    ┌─────────────────────┐              │
│ │   ▶ Run Now         │    │   📅 Schedule       │              │
│ │   (Green button)    │    │   (Purple button)   │              │
│ └─────────────────────┘    └─────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

#### Functionality

**Run Now Button:**
- Immediately submits the training run
- Uses `schedule_type: 'now'`
- Creates TrainingRun and submits to Vertex AI

**Schedule Button:**
- Opens the full ScheduleModal (same modal used by "Schedule" button on existing runs)
- Supports all 5 schedule types: Once, Hourly, Daily, Weekly, Monthly
- Pre-fills model name from Step 1 of wizard
- Auto-generates schedule name: `{model_name} - Retraining`
- Creates RegisteredModel + TrainingSchedule + Cloud Scheduler job

#### Data Flow

**Run Now:** Click "Run Now" → POST `/api/training/schedules/` with `schedule_type: 'now'` → Creates TrainingRun and submits to Vertex AI.

**Schedule:** Click "Schedule" → Opens ScheduleModal → Configure schedule → POST `/api/training/schedules/` → Creates RegisteredModel, TrainingSchedule, and Cloud Scheduler job.

#### API Changes

**POST /api/training/schedules/** - Enhanced for Wizard Mode:

New fields for wizard mode:
- `schedule_name`: Name for the TrainingSchedule (separate from model name)
- `schedule_description`: Description for the schedule

The endpoint now:
1. Distinguishes between `name` (model name) and `schedule_name` (schedule name)
2. Creates/gets RegisteredModel using the model name
3. Links the schedule to the RegisteredModel
4. Falls back to `name` for backward compatibility if `schedule_name` not provided

```python
# Example wizard mode request
{
    "name": "my-retrieval-model",           # Model name (for RegisteredModel)
    "schedule_name": "Weekly Retraining",   # Schedule name (for TrainingSchedule)
    "schedule_description": "...",
    "schedule_type": "weekly",
    "schedule_time": "09:00",
    "schedule_day_of_week": 0,
    "schedule_timezone": "UTC",
    "dataset_id": 1,
    "feature_config_id": 2,
    "model_config_id": 3,
    "base_experiment_id": 456,
    "training_params": {...},
    "gpu_config": {...},
    "evaluator_config": {...}
}
```

#### Frontend Implementation

**training_wizard.js:**
```javascript
// New function to open schedule modal with wizard config
function openScheduleModal() {
    const wizardConfig = buildWizardConfig();
    ScheduleModal.openForWizardConfig(wizardConfig);
}

// Build config object for ScheduleModal
function buildWizardConfig() {
    return {
        model_name: state.formData.name,
        dataset_id: exp.dataset_id,
        feature_config_id: exp.feature_config_id,
        model_config_id: exp.model_config_id,
        base_experiment_id: exp.experiment_id,
        training_params: {...},
        gpu_config: {...},
        evaluator_config: {...}
    };
}
```

**schedule_modal.js:**
```javascript
// New method for wizard integration
function openForWizardConfig(wizardConfig) {
    state.mode = 'wizard';
    state.wizardConfig = wizardConfig;

    // Display model name from wizard
    document.getElementById('scheduleModelName').textContent = wizardConfig.model_name;

    // Pre-fill schedule name
    const suggestedName = `${wizardConfig.model_name} - Retraining`;
    document.getElementById('scheduleNameInput').value = suggestedName;

    // Show modal with all 5 schedule types
    // ...
}
```

#### Files Modified

| File | Change |
|------|--------|
| `templates/ml_platform/model_training.html` | Replaced inline schedule section with Run Now/Schedule buttons |
| `static/css/modals.css` | Added `.wizard-action-btn` styles |
| `static/css/schedule_modal.css` | Increased z-index to appear above wizard |
| `static/js/training_wizard.js` | Added `openScheduleModal()`, `buildWizardConfig()` |
| `static/js/schedule_modal.js` | Added `openForWizardConfig()`, updated `create()` for wizard mode |
| `ml_platform/training/api.py` | Enhanced `_training_schedule_create()` for wizard mode |

#### Benefits

1. **Full Feature Parity**: All 5 schedule types available from wizard (previously only 4)
2. **Consistent UX**: Same modal used everywhere for scheduling
3. **Single Source of Truth**: Schedule UI maintained in one place
4. **Proper Model Association**: Schedule always linked to RegisteredModel

### Bug Fixes (2026-01-26)

#### Fix: Schedule Deletion Now Properly Deletes Records

**Problem**: The "Delete" button in the Schedules UI only cancelled schedules (marked status as "cancelled") but did not delete them from the database. This caused issues when trying to create a new schedule with the same model name, as the `RegisteredModel` was still linked to the old cancelled schedule via a `OneToOneField`.

**Root Cause**: The UI's delete button called the `/cancel/` endpoint instead of using HTTP `DELETE` on the schedule detail endpoint.

**Solution**: Updated the frontend to call the correct DELETE endpoint.

**Changes**:

| File | Change |
|------|--------|
| `static/js/training_cards.js` | Added `detail` endpoint to config |
| `static/js/training_cards.js` | Renamed `cancelSchedule()` to `deleteSchedule()` |
| `static/js/training_cards.js` | Changed from `POST /cancel/` to `DELETE /schedules/{id}/` |
| `static/js/training_cards.js` | Updated public API export |

**Behavior After Fix**:
- Delete button now calls `DELETE /api/training/schedules/{id}/`
- Cloud Scheduler job is deleted (if exists)
- Schedule record is deleted from database
- `RegisteredModel` link is removed (allowing new schedules for same model)

#### Fix: Add Missing `vertex_pipeline_job_id` Field to TrainingRun

**Problem**: The `TrainingRun` model was missing the `vertex_pipeline_job_id` field, causing warnings in logs:
```
Error checking Cloud Build result for Training #N: The following fields do not exist
in this model... vertex_pipeline_job_id
```

**Root Cause**: The `TrainingRun` model only had `vertex_pipeline_job_name`, but the service code (`training/services.py`) attempted to update both `vertex_pipeline_job_name` and `vertex_pipeline_job_id`. The `QuickTest` model had both fields, but `TrainingRun` was missing the shorter ID field.

**Solution**: Added the missing field to the model.

**Changes**:

| File | Change |
|------|--------|
| `ml_platform/training/models.py` | Added `vertex_pipeline_job_id` CharField |
| `ml_platform/training/migrations/0008_...` | Migration to add the field |

**Field Definition**:
```python
vertex_pipeline_job_id = models.CharField(
    max_length=255,
    blank=True,
    help_text="Short pipeline job ID for display"
)
```

### Deployment Integration in Training Wizard (2026-01-29)

Added automatic Cloud Run deployment configuration to the Training Wizard. Users can now configure deployment options in Step 3 ("GPU & Deploy") and have models automatically deployed to Cloud Run after successful training and registration.

#### Feature Overview

The deployment integration adds:
1. **Auto-deployment toggle** - Enable/disable automatic deployment to Cloud Run
2. **Endpoint name configuration** - Auto-generated or custom service name
3. **Deployment presets** - Development, Production, High Traffic configurations
4. **Manual parameter tuning** - Fine-tune instances, memory, CPU, timeout
5. **9-stage pipeline visualization** - Register and Deploy stages in pipeline DAG

#### UI Layout (Step 3: GPU & Deploy)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🚀 Deploy                                                            [▼]    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ [○] Enable Auto-Deployment to Cloud Run                                     │
│                                                                              │
│ ─────────────────── (shown when enabled) ───────────────────                │
│                                                                              │
│ ENDPOINT NAME                                                                │
│ ┌──────────────────────────────────────────────────────────────────────┐    │
│ │ ◉ Create New Endpoint                                                 │    │
│ │ ┌─────────────────────────────────────────────────────────────────┐  │    │
│ │ │ 🏷️  my-model-serving                                             │  │    │
│ │ └─────────────────────────────────────────────────────────────────┘  │    │
│ │ ☐ Use custom name                                                    │    │
│ └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│ DEPLOYMENT PRESET                                                            │
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                 │
│ │   Development   │ │  Production ✓   │ │   High Traffic  │                 │
│ │   0-2 instances │ │ [RECOMMENDED]   │ │   2-50 instances│                 │
│ │   2Gi / 1 CPU   │ │  1-10 instances │ │   8Gi / 4 CPU   │                 │
│ │ Testing, low    │ │  4Gi / 2 CPU    │ │ High concurrency│                 │
│ │ traffic         │ │ Standard workload│ │                 │                 │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘                 │
│                                                                              │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│ │MIN INST  │ │MAX INST  │ │ MEMORY   │ │   CPU    │ │ TIMEOUT  │           │
│ │    1     │ │   10     │ │  4 Gi ▼  │ │ 2 vCPU ▼ │ │  300s ▼  │           │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Deployment Presets

| Preset | Min Instances | Max Instances | Memory | CPU | Use Case |
|--------|---------------|---------------|--------|-----|----------|
| Development | 0 | 2 | 2Gi | 1 | Testing, low traffic |
| Production | 1 | 10 | 4Gi | 2 | Standard workload (recommended) |
| High Traffic | 2 | 50 | 8Gi | 4 | High concurrency |

#### New TrainingRun Status Values

| Status | Description |
|--------|-------------|
| `deploying` | Model is being deployed to Cloud Run |
| `deployed` | Model successfully deployed to Cloud Run |
| `deploy_failed` | Deployment failed (training completed successfully) |

#### Pipeline Stages (9 stages)

The pipeline visualization now shows 9 stages with renamed and new components:

| Stage | Description | Status |
|-------|-------------|--------|
| Compile | Pipeline compilation | Always shown |
| Examples | ExampleGen - BigQuery data extraction | Always shown |
| Stats | StatisticsGen - Data statistics | Always shown |
| Schema | SchemaGen - Schema inference | Always shown |
| Transform | Transform - Feature engineering | Always shown |
| Train | Trainer - Model training | Always shown |
| Evaluator | Evaluator - Model evaluation | Always shown |
| Register | Model Registry registration (renamed from Pusher) | Always shown |
| Deploy | Cloud Run deployment | Shown as "pending" if enabled, "skipped" if disabled |

#### Database Changes

New fields added to `TrainingRun` model:

```python
# Deployment tracking fields
deploy_enabled = models.BooleanField(default=False)
deployment_status = models.CharField(
    max_length=20,
    choices=[('pending', 'Pending'), ('deploying', 'Deploying'),
             ('deployed', 'Deployed'), ('failed', 'Failed'), ('skipped', 'Skipped')],
    default='pending'
)
deployment_error = models.TextField(blank=True, default='')
deployment_started_at = models.DateTimeField(null=True, blank=True)
deployment_completed_at = models.DateTimeField(null=True, blank=True)
deployed_endpoint = models.ForeignKey(
    'DeployedEndpoint', null=True, blank=True,
    on_delete=models.SET_NULL, related_name='deployed_training_runs'
)
```

New status choices added:
```python
STATUS_DEPLOYING = 'deploying'
STATUS_DEPLOYED = 'deployed'
STATUS_DEPLOY_FAILED = 'deploy_failed'
```

#### API Changes

**Request Payload** - New `deployment_config` object:
```json
{
    "deployment_config": {
        "enabled": true,
        "service_name": "my-model-serving",
        "custom_name": false,
        "preset": "production",
        "min_instances": 1,
        "max_instances": 10,
        "memory": "4Gi",
        "cpu": "2",
        "timeout": "300"
    }
}
```

**Response** - New fields in training run serialization:
```json
{
    "deploy_enabled": true,
    "deployment_status": "deployed",
    "deployment_error": "",
    "deployed_endpoint_id": 123,
    "deployed_endpoint_url": "https://my-model-serving-xxx.run.app",
    "deployment_started_at": "2026-01-29T10:30:00Z",
    "deployment_completed_at": "2026-01-29T10:32:00Z"
}
```

#### Backend Flow

1. User enables deployment in wizard and configures options
2. Training pipeline executes normally (Compile → Examples → ... → Evaluator → Register)
3. After model registration completes in `_extract_results()`:
   - Check if `deployment_config.enabled` is True
   - Call `_auto_deploy_to_cloud_run()` method
4. Auto-deploy method:
   - Sets status to `deploying`
   - Updates stage_details to show Deploy stage as `running`
   - Calls existing `deploy_to_cloud_run()` method
   - On success: status → `deployed`, creates/updates `DeployedEndpoint` record
   - On failure: status → `deploy_failed`, stores error message

#### Files Changed

| File | Change |
|------|--------|
| `ml_platform/training/models.py` | Added deployment status choices, deployment tracking fields |
| `ml_platform/training/services.py` | Added `_auto_deploy_to_cloud_run()`, `_update_deploy_stage_status()`, updated stage handling |
| `ml_platform/training/api.py` | Updated serialization to include deployment fields |
| `templates/ml_platform/model_training.html` | Added deployment config UI to wizard |
| `static/js/training_wizard.js` | Added deployment config state and methods |
| `static/css/training_wizard.css` | Added deployment section styles |
| `static/js/pipeline_dag.js` | Renamed Pusher→Register, added Deploy node |
| `static/js/exp_view_modal.js` | Updated stage definitions |
| `static/css/pipeline_dag.css` | Increased height, added deploy_failed styling |
| `static/css/cards.css` | Added deploying/deployed/deploy_failed status badge styles |
| `static/js/training_cards.js` | Added STATUS_CONFIG entries for deployment states |
| `static/js/models_registry.js` | Updated help text to reference Register |

#### Service Name Validation

Cloud Run service names must follow these rules:
- Lowercase letters, numbers, and hyphens only
- 1-63 characters
- Must start with a letter
- Must end with a letter or number

The wizard auto-generates a valid service name from the model name and validates custom names in real-time.

### Edit Schedule Feature (2026-01-27)

Added ability to edit existing training schedules from the Schedules section. Users can modify schedule timing (type, time, day, timezone) but NOT training configuration (which remains frozen from the source run).

#### Editable Fields
- `name` - Schedule display name
- `description` - Optional description
- `schedule_type` - once, hourly, daily, weekly, monthly
- `schedule_time` - Time of day (HH:MM)
- `schedule_day_of_week` - Day for weekly schedules (0-6, Monday=0)
- `schedule_day_of_month` - Day for monthly schedules (1-31)
- `schedule_timezone` - Timezone for schedule
- `scheduled_datetime` - For one-time schedules

#### Non-Editable Fields (Frozen from Source)
- `training_params`
- `gpu_config`
- `evaluator_config`
- `deployment_config`

#### API Endpoint

```
PUT /api/training/schedules/{id}/

Request:
{
    "name": "Updated Schedule Name",
    "description": "New description",
    "schedule_type": "weekly",
    "schedule_time": "10:00",
    "schedule_day_of_week": 2,
    "schedule_timezone": "Europe/Warsaw"
}

Response:
{
    "success": true,
    "schedule": {...},
    "message": "Schedule updated successfully"
}
```

#### Validation Rules
- Schedule must be in `active` or `paused` status (not `cancelled` or `completed`)
- `name` cannot be empty
- `schedule_type` must be valid (once, hourly, daily, weekly, monthly)
- `schedule_day_of_week` must be 0-6
- `schedule_day_of_month` must be 1-31
- For `once` type, `scheduled_datetime` must be in the future

#### Implementation Changes

| File | Changes |
|------|---------|
| `ml_platform/training/api.py` | Added PUT support to `training_schedule_detail`, added `_training_schedule_update()` |
| `ml_platform/training/schedule_service.py` | Added `update_schedule()` and `_update_scheduler_job()` methods |
| `static/js/training_cards.js` | Added edit button to schedule cards, added `editSchedule()` function |
| `static/js/schedule_modal.js` | Added `openForEdit()`, edit mode state, PUT request handling |
| `templates/includes/_schedule_modal.html` | Made title/button text dynamic with IDs |
| `static/css/training_cards.css` | Added edit button styling |

#### UI Flow

```
User clicks Edit button on schedule card
         ↓
ScheduleModal.openForEdit(scheduleId)
         ↓
GET /api/training/schedules/{id}/ (fetch current values)
         ↓
Modal opens with:
- Title: "Edit Training Schedule"
- Subtitle: "Editing schedule: {name}"
- Button: "Save" (instead of "Create")
- Form pre-populated with current values
         ↓
User modifies schedule timing
         ↓
Click "Save" → PUT /api/training/schedules/{id}/
         ↓
Cloud Scheduler job updated (if active)
         ↓
Modal closes, schedule list refreshes
```

#### Schedule Card Actions (Updated)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Schedule Card Actions                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [▶ Run]  [⏸ Pause/▶ Resume]  [✏ Edit]  [🗑 Delete]                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### UI Views

The Training Wizard (`static/js/training_wizard.js`) provides a 3-step dialog for creating training runs. The View Modal (`static/js/exp_view_modal.js` in `training_run` mode) displays progress and results with Pipeline, Data Insights, and Training tabs. See [Unified View Modal for Training Runs](#unified-view-modal-for-training-runs-2026-01-20) for details.

---

## Data Model

### Django Models

**File:** `ml_platform/training/models.py`

#### TrainingRun

| Field Category | Key Fields |
|----------------|------------|
| **Identity** | `ml_model` (FK), `run_number`, `name` |
| **Configuration** | `dataset` (FK), `feature_config` (FK), `model_config` (FK), `training_params` (JSON), `gpu_config` (JSON) |
| **Status** | `status` (pending/scheduled/running/completed/failed/not_blessed/deploying/deployed), `current_stage` |
| **Results** | `recall_at_5/10/50/100`, `rmse`, `mae`, `final_loss`, `is_blessed` |
| **Vertex AI** | `vertex_pipeline_job_name`, `vertex_model_resource_name`, `vertex_model_version` |
| **Deployment** | `deploy_enabled`, `deployment_status`, `deployment_config` (JSON) |
| **Artifacts** | `artifacts` (JSON), `training_history_json` (JSON) |
| **Tracking** | `cost_usd`, `duration_seconds`, `error_message`, `mlflow_run_id` |
| **Timestamps** | `created_at`, `started_at`, `completed_at`, `registered_at` |

#### TrainingMetricsHistory

Stores per-epoch metrics for training visualization: `training_run` (FK), `epoch`, `loss`, `recall_at_*` metrics.

#### TrainingSchedule

Schedule configuration for recurring training runs. See [Schedule Feature](#schedule-feature-2026-01-23) section.

#### RegisteredModel

Groups model versions under a single name. See [RegisteredModel Entity](#registeredmodel-entity-2026-01-25) section.

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

**File:** `ml_platform/training/services.py`

The `TrainingService` class manages TFX pipeline execution:
- `create_training_pipeline()` - Builds TFX Pipeline from TrainingRun configuration
- `submit_training_pipeline()` - Compiles and submits to Vertex AI Pipelines
- `_poll_pipeline_status()` - Monitors pipeline execution
- `_extract_results()` - Extracts metrics and registers model after completion

### TFX Pipeline Components

| Stage | Component | Purpose |
|-------|-----------|---------|
| 1 | Compile | Pipeline compilation to Kubeflow IR |
| 2 | BigQueryExampleGen | Extract data from BigQuery to TFRecords |
| 3 | StatisticsGen | Generate TFDV statistics (via Dataflow) |
| 4 | SchemaGen | Infer schema from statistics |
| 5 | Transform | Feature preprocessing, vocabulary creation (via Dataflow) |
| 6 | Trainer | Train TFRS model (GPU via Vertex AI Custom Job) |
| 7 | Evaluator | Compute final metrics, determine blessing status |
| 8 | Register | Push model to Vertex AI Model Registry |
| 9 | Deploy | Auto-deploy to Cloud Run (if enabled) |

### TFRS Trainer Module

**File:** `training/tfrs_trainer.py`

The trainer module implements:
- `run_fn(fn_args)` - TFX Trainer entry point
- `TFRSModel(tfrs.Model)` - Two-tower retrieval model with query/candidate towers
- Custom callbacks for metrics logging to MLflow
- Early stopping with configurable patience

---

## Webhook Integration

**File:** `ml_platform/training/api.py`

| Webhook | Purpose |
|---------|---------|
| `POST /api/training-runs/{id}/webhook/stage-complete/` | Update stage status |
| `POST /api/training-runs/{id}/webhook/epoch-complete/` | Save per-epoch metrics |
| `POST /api/training/schedules/{id}/webhook/` | Trigger scheduled training |

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

### Solution: Custom TFX GPU Container

**File:** `cloudbuild/tfx-trainer-gpu/Dockerfile`

Base image: `tensorflow/tensorflow:2.15.0-gpu` with TFX 1.15.0, TFRS, and ScaNN installed.

Alternative base images:
- `gcr.io/deeplearning-platform-release/tf2-gpu.2-15.py310` (Google Deep Learning Containers)
- `nvidia/cuda:12.2.0-cudnn8-runtime-ubuntu22.04` (NVIDIA base)

### GPU Fallback Strategy

| Priority | Config | Use Case |
|----------|--------|----------|
| 1 | 2x T4 / n1-standard-16 | Default production |
| 2 | 4x T4 / n1-standard-32 | Large models |
| 3 | 2x L4 / g2-standard-24 | Alternative region |

**Note:** ScaNN is CPU-bound; GPUs accelerate only the model training phase.

Verify GPU access with: `tf.config.list_physical_devices('GPU')`

---

## GPU Quota and Regional Availability (2026-01-18)

### Critical Discovery: Regional GPU Limitations

**Vertex AI custom training does NOT support GPUs in all regions**, even if:
- GPU quota is approved for that region
- Compute Engine shows GPUs available in the region
- Documentation suggests GPU support

This is an undocumented limitation. Always verify GPU availability before requesting quota.

### Verified GPU Regions for Vertex AI Custom Training

| Region | T4 | L4 | V100 | A100 | Status |
|--------|----|----|------|------|--------|
| `europe-west4` (Netherlands) | ✅ | ✅ | ✅ | ✅ | **Recommended for EU** |
| `us-central1` (Iowa) | ✅ | ✅ | ✅ | ✅ | Largest capacity |
| `europe-west1` (Belgium) | ✅ | ✅ | ✅ | ✅ | Good EU alternative |
| `europe-central2` (Warsaw) | ❌ | ❌ | ❌ | ❌ | **No GPU support for training** |

> ⚠️ **europe-central2 (Warsaw)**: Despite quota approval, T4 GPUs are marked with † (dagger) in Vertex AI documentation, meaning "not available for training". GPUs in this region are only available for prediction/inference workloads.

### GPU Quota

Request via GCP Console: Quotas → `Vertex AI API` → `custom_model_training_nvidia_t4` in `europe-west4`.

### Split-Region Pipeline Architecture (2026-01-24)

| Region | Components |
|--------|------------|
| `europe-central2` | Pipeline orchestration, ExampleGen, StatisticsGen, Transform, Evaluator, Pusher |
| `europe-west4` | Trainer (GPU Custom Job) |

This prevents Dataflow from competing with GPU workloads.

### TrainingService Configuration

**File:** `ml_platform/training/services.py`

Region constants: `REGION = 'europe-central2'`, `GPU_TRAINING_REGION = 'europe-west4'`

---

## GPU Types Reference

| GPU | VRAM | Use Case | Recommended Config |
|-----|------|----------|-------------------|
| **T4** | 16 GB | Dev/test, production | 2x T4 / n1-standard-16 |
| **L4** | 24 GB | Large embeddings | 2x L4 / g2-standard-24 |
| **A100** | 40-80 GB | Large models | 2x A100 / a2-highgpu-2g |

**Regions:** `europe-west4` (recommended EU), `us-central1` (largest capacity). Note: `europe-central2` has no GPU training support.

### Upgrading from T4 to L4

To use L4 GPUs (recommended for larger models):

**1. Request L4 quota in europe-west4:**
```
Filter: custom_model_training_nvidia_l4_gpus
Region: europe-west4
Amount: 2-4
```

**2. Update TrainingService defaults:**
```python
# In ml_platform/training/services.py
gpu_type = gpu_config.get('gpu_type', 'NVIDIA_L4')  # Changed from NVIDIA_TESLA_T4
machine_type = gpu_config.get('machine_type', 'g2-standard-24')  # Changed from n1-standard-16
```

**3. Test with:**
```bash
gcloud ai custom-jobs create \
  --project=b2b-recs \
  --region=europe-west4 \
  --display-name="gpu-test-l4" \
  --worker-pool-spec="replica-count=1,machine-type=g2-standard-24,accelerator-type=NVIDIA_L4,accelerator-count=2,container-image-uri=europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer-gpu:latest" \
  --args="python","-c","import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

### References

- [Vertex AI Locations & Accelerators](https://docs.cloud.google.com/vertex-ai/docs/general/locations)
- [Compute Engine GPU Regions](https://docs.cloud.google.com/compute/docs/gpus/gpu-regions-zones)
- [Configure Compute for Training](https://cloud.google.com/vertex-ai/docs/training/configure-compute)
- [GPU Pricing](https://cloud.google.com/compute/gpus-pricing)

---

## Critical Bug Fix: GPUs Allocated But Not Used (2026-01-19)

### Problem Description

The first full training run (`tr-1-20260119-144450`) took ~2 hours despite having 2x T4 GPUs allocated, which is comparable to CPU-only training time. Investigation revealed that **GPUs were being provisioned but never actually utilized** by the training code.

### Root Cause Analysis

The issue had **two layers**:

#### Layer 1: Vertex AI GPU Allocation Missing

The TFX `Trainer` component was configured without Vertex AI GPU resource allocation:

```python
# BEFORE (broken) - ml_platform/training/services.py
trainer = Trainer(
    module_file=trainer_module_path,
    examples=transform.outputs["transformed_examples"],
    ...
    custom_config=custom_config,
    # ❌ No custom_executor_spec = No GPU allocation in Vertex AI
)
```

Even though the pipeline used a GPU-enabled Docker image (`tfx-trainer-gpu:latest`), Vertex AI was not instructed to attach GPUs to the Trainer component. The job ran on CPU-only VMs.

#### Layer 2: Training Code Ignored GPU Settings

Even if GPUs were allocated, the generated training code in `ml_platform/configs/services.py` did not:

1. **Extract GPU parameters** from `custom_config`
2. **Detect available GPUs** using TensorFlow
3. **Use `tf.distribute.MirroredStrategy`** for multi-GPU training
4. **Log GPU utilization** for debugging

```python
# BEFORE (broken) - Generated run_fn() in configs/services.py
custom_config = fn_args.custom_config or {}
epochs = custom_config.get('epochs', EPOCHS)
learning_rate = custom_config.get('learning_rate', LEARNING_RATE)
batch_size = custom_config.get('batch_size', BATCH_SIZE)
# ❌ gpu_enabled and gpu_count were NEVER extracted

# Model built without strategy scope
model = RetrievalModel(tf_transform_output=tf_transform_output)
model.compile(optimizer=optimizer)  # ❌ Single-device training only
```

### The Fix

#### Fix 1: Vertex AI GPU Resource Allocation

Added proper GPU configuration to the Trainer component using AI Platform executor:

```python
# AFTER (fixed) - ml_platform/training/services.py

# Import Vertex AI types
from tfx.dsl.components.base import executor_spec
from tfx.extensions.google_cloud_ai_platform.trainer import executor as ai_platform_trainer_executor
from google.cloud.aiplatform_v1.types import custom_job as custom_job_spec_pb2
from google.cloud.aiplatform_v1.types import machine_resources as machine_resources_pb2
from google.cloud.aiplatform_v1.types import accelerator_type as accelerator_type_pb2

# Configure GPU worker pool
worker_pool_spec = custom_job_spec_pb2.WorkerPoolSpec(
    machine_spec=machine_resources_pb2.MachineSpec(
        machine_type=machine_type,           # n1-standard-16
        accelerator_type=accelerator_type,   # NVIDIA_TESLA_T4
        accelerator_count=gpu_count,         # 2
    ),
    replica_count=1,
    container_spec=custom_job_spec_pb2.ContainerSpec(
        image_uri=gpu_trainer_image,
    ),
)

# Create custom job spec
vertex_job_spec = custom_job_spec_pb2.CustomJobSpec(
    worker_pool_specs=[worker_pool_spec],
)

# Add to custom_config
custom_config["ai_platform_training_args"] = {
    "project": project_id,
    "region": region,
    "job_spec": vertex_job_spec,
}

# Trainer with AI Platform executor
trainer = Trainer(
    module_file=trainer_module_path,
    ...
    custom_config=custom_config,
    custom_executor_spec=executor_spec.ExecutorClassSpec(
        ai_platform_trainer_executor.GenericExecutor  # ✅ GPU-aware executor
    ),
)
```

#### Fix 2: Training Code GPU Support

Updated all three model types (retrieval, ranking, multitask) in `ml_platform/configs/services.py`:

**2a. GPU Parameter Extraction:**

```python
# AFTER (fixed)
custom_config = fn_args.custom_config or {}
epochs = custom_config.get('epochs', EPOCHS)
learning_rate = custom_config.get('learning_rate', LEARNING_RATE)
batch_size = custom_config.get('batch_size', BATCH_SIZE)
gcs_output_path = custom_config.get('gcs_output_path', '')

# ✅ GPU configuration now extracted
gpu_enabled = custom_config.get('gpu_enabled', False)
gpu_count = custom_config.get('gpu_count', 0)
```

**2b. GPU Detection and Logging:**

```python
# ✅ Comprehensive GPU logging
physical_gpus = tf.config.list_physical_devices('GPU')
logging.info(f"GPU config from custom_config: gpu_enabled={gpu_enabled}, gpu_count={gpu_count}")
logging.info(f"Physical GPUs detected: {len(physical_gpus)}")
for i, gpu in enumerate(physical_gpus):
    logging.info(f"  GPU {i}: {gpu.name}")
```

**2c. Distribution Strategy Setup:**

```python
# ✅ MirroredStrategy for multi-GPU training
strategy = None
if gpu_enabled and len(physical_gpus) > 0:
    if len(physical_gpus) > 1:
        strategy = tf.distribute.MirroredStrategy()
        logging.info(f"Using MirroredStrategy with {strategy.num_replicas_in_sync} replicas")
    else:
        strategy = tf.distribute.get_strategy()
        logging.info("Using single GPU (default strategy)")
else:
    strategy = tf.distribute.get_strategy()
    logging.info("No GPU enabled or detected - using CPU (default strategy)")
```

**2d. Model Built Within Strategy Scope:**

```python
# ✅ Model and optimizer created within strategy scope
with strategy.scope():
    model = RetrievalModel(tf_transform_output=tf_transform_output)
    optimizer = Adagrad(learning_rate=learning_rate, clipnorm=1.0)
    model.compile(optimizer=optimizer)

logging.info(f"Model built with strategy: {type(strategy).__name__}")
```

### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/training/services.py` | Added Vertex AI GPU allocation to Trainer component |
| `ml_platform/configs/services.py` | Added GPU extraction, detection, logging, and MirroredStrategy to all 3 model types |

### Expected Behavior After Fix

When running a training job with GPUs enabled, logs should show:

```
GPU config from custom_config: gpu_enabled=True, gpu_count=2
Physical GPUs detected: 2
  GPU 0: /physical_device:GPU:0
  GPU 1: /physical_device:GPU:1
Using MirroredStrategy with 2 replicas
Building RetrievalModel...
Model built with strategy: MirroredStrategy
Using optimizer: Adagrad with lr=0.01, clipnorm=1.0
```

### Why This Bug Wasn't Caught Earlier

1. **GPU image worked** - The Docker image built successfully with GPU support
2. **Pipeline compiled** - TFX compilation succeeded without errors
3. **Jobs ran** - Training completed (just slower than expected)
4. **No explicit errors** - TensorFlow silently falls back to CPU when no GPUs detected
5. **String-embedded code** - The `run_fn()` is generated as a string, so Python doesn't validate imports at dev time
6. **Different test environments** - Quick tests use CPU by design, so GPU path was never exercised

### Verification Steps

1. **Check logs** for GPU detection messages
2. **Verify strategy** shows "MirroredStrategy with 2 replicas"
3. **Compare training time** - Should be 30-50% faster with 2x T4 vs CPU
4. **Monitor GPU utilization** in Cloud Console during training

### Related Documentation

- [TensorFlow Distributed Training](https://www.tensorflow.org/guide/distributed_training)
- [MirroredStrategy](https://www.tensorflow.org/api_docs/python/tf/distribute/MirroredStrategy)
- [Vertex AI Custom Training](https://cloud.google.com/vertex-ai/docs/training/create-custom-job)
- [TFX AI Platform Trainer](https://www.tensorflow.org/tfx/guide/trainer#training_on_google_cloud_ai_platform)

## Critical Bug Fix: Multi-GPU Training Loss Reduction Incompatibility (2026-01-28)

### Problem Description

Scheduled training pipeline `training-tr-27-20260128-030005-20260128030249` for a **multitask (hybrid) model** failed at the Trainer stage when running with 2 GPUs in `europe-west4`. A retrieval model pipeline succeeded an hour later with the same infrastructure.

**Error from Vertex AI Custom Job logs:**
```
ValueError: Please use `tf.keras.losses.Reduction.SUM` or `tf.keras.losses.Reduction.NONE`
for loss reduction when losses are used with `tf.distribute.Strategy`, except for
specifying losses in `Model.compile()` for use by the built-in training loop `Model.fit()`.
```

### Root Cause Analysis

The `tfrs.tasks.Ranking` loss function was created with the **default reduction mode** (`AUTO` → `SUM_OVER_BATCH_SIZE`), which is incompatible with `tf.distribute.MirroredStrategy` for multi-GPU training.

#### Why Retrieval Models Worked

- **Retrieval models** use `tfrs.tasks.Retrieval()` which computes loss internally using in-batch negatives
- The retrieval task handles its own loss computation and doesn't expose a Keras loss function directly
- No explicit loss reduction parameter is needed

#### Why Ranking/Multitask Models Failed

- **Ranking and Multitask models** use `tfrs.tasks.Ranking(loss=tf.keras.losses.MeanSquaredError())`
- The `MeanSquaredError()` (and other Keras loss functions) default to `Reduction.AUTO`
- When using `MirroredStrategy`, Keras requires explicit `Reduction.SUM` or `Reduction.NONE`
- The error occurs during `model.fit()` when the distributed strategy validates loss reduction modes

### The Fix

**File:** `ml_platform/configs/services.py`

**Locations:**
- `_generate_ranking_model()` (~line 4171)
- `_generate_multitask_model()` (~line 5289)

```python
# BEFORE (broken)
loss_mapping = {
    'mse': 'tf.keras.losses.MeanSquaredError()',
    'binary_crossentropy': 'tf.keras.losses.BinaryCrossentropy()',
    'huber': 'tf.keras.losses.Huber()',
}

# AFTER (fixed)
# CRITICAL: Must use Reduction.SUM for distributed training (multi-GPU)
# Default AUTO/SUM_OVER_BATCH_SIZE is incompatible with MirroredStrategy
loss_mapping = {
    'mse': 'tf.keras.losses.MeanSquaredError(reduction=tf.keras.losses.Reduction.SUM)',
    'binary_crossentropy': 'tf.keras.losses.BinaryCrossentropy(reduction=tf.keras.losses.Reduction.SUM)',
    'huber': 'tf.keras.losses.Huber(reduction=tf.keras.losses.Reduction.SUM)',
}
```

### Why This Bug Wasn't Caught Earlier

1. **Single-GPU Quick Tests**: Quick Tests use 1 GPU, where `MirroredStrategy` isn't used
2. **Retrieval-only production runs**: Previous production training used retrieval models which don't have this issue
3. **Multitask is new**: The multitask model type was recently implemented and this was the first scheduled 2-GPU production run

### Verification

Custom job test with 2 GPUs using artifacts from the failed pipeline:

```bash
./venv/bin/python scripts/test_services_trainer.py \
    --feature-config-id 9 \
    --model-config-id 17 \
    --source-exp "tr-27-20260128-030005/555035914949/training-tr-27-20260128-030005-20260128030249" \
    --epochs 2 \
    --gpu-count 2 \
    --learning-rate 0.001 \
    --wait
```

**Result:** `JOB_STATE_SUCCEEDED` with NCCL confirming 2 GPUs:
```
NCCL INFO comm ... rank 0 nranks 2 cudaDev 0 ... - Init COMPLETE
NCCL INFO comm ... rank 1 nranks 2 cudaDev 1 ... - Init COMPLETE
```

### Files Modified

| File | Change |
|------|--------|
| `ml_platform/configs/services.py` | Added `reduction=tf.keras.losses.Reduction.SUM` to loss functions in both `_generate_ranking_model()` and `_generate_multitask_model()` |
| `scripts/test_services_trainer.py` | Added `--gpu-count` argument for testing multi-GPU configurations |

### Related Documentation

- [Keras Distributed Training Guide](https://www.tensorflow.org/tutorials/distribute/custom_training)
- [Loss Reduction with Distribution Strategies](https://www.tensorflow.org/api_docs/python/tf/keras/losses/Reduction)

## Bug Fix: RMSE/MAE Validation Metrics Not Extracted for Ranking/Multitask Training Runs (2026-01-28)

### Problem Description

After completing a **multitask (hybrid) model** training pipeline (`training-tr-17-20260124-094938-20260124095148`, Training #20), the RMSE and MAE KPI boxes in the Training UI showed "-" while TEST RMSE (0.6071) and TEST MAE (0.4124) displayed correctly.

### Root Cause Analysis

The `TrainingService._extract_results()` method in `ml_platform/training/services.py` used incorrect keys to extract validation RMSE/MAE from the training metrics JSON.

#### How Metrics Are Stored in `training_metrics.json`

The `MetricsCollector.log_metric()` method categorizes metrics into two locations:

1. **Per-epoch metrics** (logged by `MetricsCallback.on_epoch_end`): `val_rmse`, `val_mae` etc. are stored in the **`loss` dict as arrays** (one value per epoch)
2. **Final/test metrics** (logged after training): `test_rmse`, `test_mae` are stored in the **`final_metrics` dict as scalars**

Actual JSON structure for Training #20:
```json
{
  "loss": {
    "val_rmse": [0.83, 0.77, ..., 0.6270],
    "val_mae": [0.58, 0.52, ..., 0.4199],
    ...
  },
  "final_metrics": {
    "test_rmse": 0.6071,
    "test_mae": 0.4124,
    "final_val_rmse": 0.6270,
    "final_val_mae": 0.4199,
    ...
  }
}
```

#### The Bug (TrainingService extraction)

```python
# BROKEN - looked for bare 'rmse'/'mae' in final_metrics (don't exist)
for metric in ['rmse', 'mae', 'test_rmse', 'test_mae']:
    if metric in final_metrics:
        setattr(training_run, metric, final_metrics[metric])
```

- `'rmse' in final_metrics` -> **False** (stored as `final_rmse` or in `loss['val_rmse']`)
- `'mae' in final_metrics` -> **False** (stored as `final_mae` or in `loss['val_mae']`)
- `'test_rmse' in final_metrics` -> **True** (works correctly)
- `'test_mae' in final_metrics` -> **True** (works correctly)

#### Why QuickTest (Experiments) Worked

The `ExperimentService` in `ml_platform/experiments/services.py` used the correct extraction logic:

```python
loss_data = training_metrics.get('loss', {})
if 'val_rmse' in loss_data and loss_data['val_rmse']:
    quick_test.rmse = loss_data['val_rmse'][-1]  # Last epoch value
```

The `TrainingService` extraction was written separately and didn't match this logic.

### The Fix

**File:** `ml_platform/training/services.py` (lines 715-736)

```python
# BEFORE (broken)
for metric in ['rmse', 'mae', 'test_rmse', 'test_mae']:
    if metric in final_metrics:
        setattr(training_run, metric, final_metrics[metric])
        update_fields.append(metric)

# AFTER (fixed - matches ExperimentService logic)
loss_data = training_metrics.get('loss', {})

# Validation RMSE/MAE from loss arrays (last epoch value)
if 'val_rmse' in loss_data and loss_data['val_rmse']:
    training_run.rmse = loss_data['val_rmse'][-1]
    update_fields.append('rmse')

if 'val_mae' in loss_data and loss_data['val_mae']:
    training_run.mae = loss_data['val_mae'][-1]
    update_fields.append('mae')

# Test RMSE/MAE from final_metrics (unchanged - already correct)
if 'test_rmse' in final_metrics:
    training_run.test_rmse = final_metrics['test_rmse']
    update_fields.append('test_rmse')

if 'test_mae' in final_metrics:
    training_run.test_mae = final_metrics['test_mae']
    update_fields.append('test_mae')
```

### Backfill for Existing Runs

Created management command to re-extract RMSE/MAE from cached `training_history_json` for completed ranking/multitask training runs:

**File:** `ml_platform/management/commands/backfill_ranking_metrics.py`

```bash
# Preview what would be updated
python manage.py backfill_ranking_metrics --dry-run

# Run the backfill
python manage.py backfill_ranking_metrics

# Force re-populate even if values exist
python manage.py backfill_ranking_metrics --force
```

**Backfill result for Training #20:**
```
Found 1 training run(s) to process.
[1/1] Processing TrainingRun 29 (Training #20, type=multitask)...
  Updated: RMSE=0.6270, MAE=0.4199
Completed: 1 updated, 0 skipped, 0 errors
```

### Files Modified

| File | Change |
|------|--------|
| `ml_platform/training/services.py` | Fixed `_extract_results()` to read validation RMSE/MAE from `loss` dict instead of `final_metrics` |
| `ml_platform/management/commands/backfill_ranking_metrics.py` | New management command to backfill RMSE/MAE for existing completed training runs |

### Models Registry View Modal - Versions Tab Enhancement (2026-01-27)

Replaced the table-based Versions tab in the Models Registry View modal with a visual KPI-focused design featuring a grouped bar chart and version cards with KPI boxes.

#### Visual Design

**Chart Section:**
- Grouped bar chart showing KPI trends across up to 5 versions
- Bars grouped by KPI metric (R@5, R@10, R@50, R@100 for retrieval models)
- Blue gradient colors from light (oldest) to dark (newest)
- Legend showing version labels (v1, v2, etc.)

**Version Cards:**
- Each card shows version number, run ID, and registration date
- 4 KPI boxes displaying metrics relevant to the model type
- Clickable to switch to that version's details

```
┌─────────────────────────────────────────────────────────────────┐
│  KPI Trends Across Versions                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │    █                              █                          ││
│  │  █ █ █                          █ █ █                        ││
│  │  █ █ █ █              █ █ █     █ █ █ █          █ █ █       ││
│  │  █ █ █ █ █      █ █ █ █ █ █ █   █ █ █ █ █    █ █ █ █ █ █     ││
│  │  ─────────      ─────────────   ─────────    ───────────     ││
│  │     R@5             R@10            R@50         R@100        ││
│  │  ■ v1  ■ v2  ■ v3  ■ v4  ■ v5                               ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  Version Details                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ● v5 - Run #17                                 Jan 26, 2026││
│  ├─────────────────────────────────────────────────────────────┤│
│  │  ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐                ││
│  │  │  R@5  │  │ R@10  │  │ R@50  │  │ R@100 │                ││
│  │  │ 0.045 │  │ 0.077 │  │ 0.189 │  │ 0.289 │                ││
│  │  └───────┘  └───────┘  └───────┘  └───────┘                ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

#### KPI Configuration by Model Type

| Model Type | KPI 1 | KPI 2 | KPI 3 | KPI 4 |
|------------|-------|-------|-------|-------|
| **Retrieval** | R@5 | R@10 | R@50 | R@100 |
| **Ranking** | RMSE | MAE | Test RMSE | Test MAE |
| **Multitask** | R@50 | R@100 | RMSE | Test RMSE |

#### Files Modified

| File | Changes |
|------|---------|
| `static/js/exp_view_modal.js` | Added `getKpiConfigForModelType()`, rewrote `renderVersionsTab()`, added `renderVersionsChart()`, added chart cleanup |
| `static/css/exp_view_modal.css` | Added styles for `.versions-tab-content`, `.versions-chart-section`, `.version-card`, `.version-kpis`, `.version-kpi-box` |

#### Technical Implementation

- Uses Chart.js grouped bar chart
- Limits display to 10 most recent versions in the list
- Limits chart to 5 most recent versions (reversed to show oldest→newest)
- Chart instance tracked in `charts.versionsChart` for proper cleanup
- Responsive design with scrollable version list

### Models Registry View Modal - Lineage Tab Removal (2026-01-27)

Removed the "Lineage" tab from the Models Registry View modal as it was not needed.

**Change:** Updated `visibleTabs` for model mode from:
```javascript
['overview', 'versions', 'artifacts', 'deployment', 'lineage']
```
to:
```javascript
['overview', 'versions', 'artifacts', 'deployment']
```

**File Modified:** `static/js/exp_view_modal.js` (line 1976)

The modal now shows only 4 tabs: **Overview**, **Versions**, **Artifacts**, **Deployment**.

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
