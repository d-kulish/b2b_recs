# Phase: Training Domain

## Document Purpose
This document provides detailed specifications for implementing the **Training** domain in the ML Platform. The Training domain executes full TFX pipelines for production model training.

**Last Updated**: 2026-01-25 (Added RegisteredModel entity for Schedule functionality)

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

### Reusable View Modal Module (2026-01-15)

The experiment view modal has been refactored into a reusable external JavaScript module that can be shared across multiple pages (Training, Experiments). This provides consistent UX and eliminates code duplication.

#### Architecture Overview

The reusable modal system consists of three components:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REUSABLE VIEW MODAL ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  _exp_view_modal.html (Template Include)                            │   │
│   │  - Reusable HTML structure for modal                                │   │
│   │  - 4 tabs: Overview, Pipeline, Data Insights, Training              │   │
│   │  - Includes _pipeline_dag.html for DAG visualization                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  exp_view_modal.js (JavaScript Module)                              │   │
│   │  - IIFE pattern exposing global ExpViewModal object                 │   │
│   │  - Configuration, state management, API calls                       │   │
│   │  - Tab switching, lazy loading, live polling                        │   │
│   │  - Chart rendering with Chart.js                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  exp_view_modal.css (Stylesheet)                                    │   │
│   │  - Complete styling for modal and all tabs                          │   │
│   │  - Status gradients, tensor visualization, tower architecture       │   │
│   │  - Training charts, metrics cards                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    UNIFIED VIEW MODAL ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ExpViewModal.open(id, options)                                            │
│           │                                                                  │
│           ├─── mode: 'experiment' (default)                                  │
│           │         │                                                        │
│           │         ├── Tabs: Overview, Pipeline, Data Insights, Training   │
│           │         ├── Fetches from: /api/quick-tests/{id}/                │
│           │         └── Shows: Experiment configurations, TFDV stats        │
│           │                                                                  │
│           └─── mode: 'training_run'                                          │
│                     │                                                        │
│                     ├── Tabs: Overview, Pipeline, Data Insights, Training   │
│                     ├── Fetches from: /api/training-runs/{id}/              │
│                     ├── Shows: Training run status, 8-stage pipeline,       │
│                     │          GPU config, blessing status                   │
│                     └── Overview includes: Model Registry & Deployment       │
│                                sections with action buttons                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

```
Training Run Modal Opens
        │
        ▼
preloadDataInsights() called (background)
        │
        ├── mode === 'training_run'
        │         │
        │         ▼
        │   /api/training-runs/{id}/statistics/
        │   /api/training-runs/{id}/schema/
        │         │
        │         ▼
        │   ArtifactService._call_tfdv_parser()
        │         │
        │         ▼
        │   tfdv-parser Cloud Run service
        │         │
        │         ▼
        │   GCS: gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}
        │
        ▼
Data cached in state.dataCache
        │
        ▼
User clicks "Data Insights" tab
        │
        ▼
loadDataInsights() renders cached data instantly
```

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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Overview Tab                                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Results                                                                  │ │
│ │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                         │ │
│ │ │  R@5    │ │  R@10   │ │  R@50   │ │  R@100  │                         │ │
│ │ │  23%    │ │  41%    │ │  68%    │ │  82%    │                         │ │
│ │ └─────────┘ └─────────┘ └─────────┘ └─────────┘                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 📦 MODEL REGISTRY                                                        │ │
│ │ ┌──────┐                                                                 │ │
│ │ │  ⏳  │  Not Registered                    [Push to Registry]           │ │
│ │ └──────┘  Model passed evaluation, ready for registry                    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 🚀 DEPLOYMENT                                                            │ │
│ │ ┌──────┐                                                                 │ │
│ │ │  ⏸️  │  Ready to Deploy                                                │ │
│ │ └──────┘  Model is registered and ready                                  │ │
│ │                                                                           │ │
│ │ [Deploy to Vertex AI]  [Deploy to Cloud Run]                             │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ DATASET: OLD_EXAMPLES_CHERNIGIV                                             │
│ ...                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

### Training Runs List View

The Training cards use a unified 4-column horizontal layout shared with the Experiments page (via `cards.css`):

**Layout Structure:**
- Column 1 (30%): Info - Status icon, run name, timestamp, config details, GPU chip
- Column 2 (20%): Config - Dataset, Features, Model badges
- Column 3 (30%): Metrics - Duration, Cost, Recall@100 in bordered boxes
- Column 4 (20%): Actions - View/Deploy/Delete buttons, status badges
- Footer: 8-stage TFX pipeline progress bar (Compile→Examples→Stats→Schema→Transform→Train→Evaluator→Pusher)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Training Runs                                                        [+ New Training]    │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ INFO (30%)          │ CONFIG (20%)    │ METRICS (30%)         │ ACTIONS (20%)        │ │
│ ├─────────────────────┼─────────────────┼───────────────────────┼──────────────────────┤ │
│ │ 🔄 Training Run #47 │ Dataset:        │ ┌─────────┐ ┌───────┐ │ [View]               │ │
│ │ Jan 20 02:15 PM     │ Q4 2024 Data    │ │Duration │ │ Cost  │ │                      │ │
│ │                     │ Features:       │ │ 45m     │ │ $12   │ │ Running...           │ │
│ │ [2x T4]             │ config-042      │ └─────────┘ └───────┘ │                      │ │
│ ├─────────────────────┴─────────────────┴───────────────────────┴──────────────────────┤ │
│ │ [COMPILE ✓][EXAMPLES ✓][STATS ✓][SCHEMA ✓][TRANSFORM ✓][▶TRAIN ][EVALUATOR][PUSHER] │ │
│ └──────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ ✅ Training Run #46 │ Dataset:        │ ┌─────────┐ ┌───────┐ │ [View] [Deploy]      │ │
│ │ Jan 19 06:53 PM     │ Q4 2024 Data    │ │Duration │ │ Cost  │ │ [Delete]             │ │
│ │ [RANKING]           │ Features:       │ │ 3h 42m  │ │ $38   │ │                      │ │
│ │ [4x T4]             │ config-038      │ └─────────┘ └───────┘ │ ☑ Blessed            │ │
│ │                     │ Model:          │ ┌─────────┐           │ ○ Not Deployed       │ │
│ │                     │ ranking-v2      │ │R@100    │           │                      │ │
│ │                     │                 │ │ 46.8%   │           │                      │ │
│ │                     │                 │ └─────────┘           │                      │ │
│ ├─────────────────────┴─────────────────┴───────────────────────┴──────────────────────┤ │
│ │ [COMPILE ✓][EXAMPLES ✓][STATS ✓][SCHEMA ✓][TRANSFORM ✓][TRAIN ✓][EVALUATOR✓][PUSHER✓]│ │
│ └──────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ ✅ Training Run #45 │ Dataset:        │ ┌─────────┐ ┌───────┐ │ [View] [Deploy]      │ │
│ │ Jan 18 10:22 AM     │ Q3 2024 Data    │ │Duration │ │ Cost  │ │ [Delete]             │ │
│ │ [RETRIEVAL]         │ Features:       │ │ 2h 58m  │ │ $32   │ │                      │ │
│ │ [4x V100]           │ config-032      │ └─────────┘ └───────┘ │ ☑ Blessed            │ │
│ │                     │                 │ ┌─────────┐           │ ● Deployed           │ │
│ │                     │                 │ │R@100    │           │                      │ │
│ │                     │                 │ │ 45.2%   │           │                      │ │
│ │                     │                 │ └─────────┘           │                      │ │
│ ├─────────────────────┴─────────────────┴───────────────────────┴──────────────────────┤ │
│ │ [COMPILE ✓][EXAMPLES ✓][STATS ✓][SCHEMA ✓][TRANSFORM ✓][TRAIN ✓][EVALUATOR✓][PUSHER✓]│ │
│ └──────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ ❌ Training Run #44 │ Dataset:        │ Error: OOM during     │ [View] [Delete]      │ │
│ │ Jan 17 03:45 PM     │ Q4 2024 Data    │ vocabulary generation │                      │ │
│ │ [RANKING]           │ Features:       │                       │                      │ │
│ │ [2x T4]             │ config-040      │                       │ Failed               │ │
│ ├─────────────────────┴─────────────────┴───────────────────────┴──────────────────────┤ │
│ │ [COMPILE ✓][EXAMPLES ✓][STATS ✓][SCHEMA ✓][TRANSFORM ✗][TRAIN  ][EVALUATOR][PUSHER] │ │
│ └──────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Shared CSS Architecture:**
- `cards.css` - Unified card layout classes used by both Training and Experiments pages
- `training_cards.css` - Training-specific styles (filters, error display, badges, pagination)

**Key CSS Classes (from cards.css):**
- `.ml-card` - Base card container
- `.ml-card-columns` - 4-column flex layout
- `.ml-card-col-info`, `.ml-card-col-config`, `.ml-card-col-metrics`, `.ml-card-col-actions`
- `.ml-card-stages` - Stage progress bar container
- `.ml-stage-segment` - Individual stage segment with status colors

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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SCHEDULE ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User                    Frontend                    Backend                │
│   ────                    ────────                    ───────                │
│                                                                              │
│   Click "Schedule"                                                           │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────────────┐                                                        │
│   │ ScheduleModal   │────► POST /api/training/schedules/from-run/            │
│   │                 │              │                                         │
│   │ - Schedule Type │              ▼                                         │
│   │ - Time/Day      │      ┌───────────────────┐                             │
│   │ - Timezone      │      │ TrainingSchedule  │                             │
│   └─────────────────┘      │ (Django Model)    │                             │
│                            └─────────┬─────────┘                             │
│                                      │                                       │
│                                      ▼                                       │
│                            ┌───────────────────┐                             │
│                            │ TrainingSchedule  │                             │
│                            │ Service           │                             │
│                            └─────────┬─────────┘                             │
│                                      │                                       │
│                                      ▼                                       │
│                            ┌───────────────────┐                             │
│                            │ Google Cloud      │                             │
│                            │ Scheduler         │                             │
│                            └─────────┬─────────┘                             │
│                                      │                                       │
│                              (At scheduled time)                             │
│                                      │                                       │
│                                      ▼                                       │
│                            POST /api/training/schedules/{id}/webhook/        │
│                                      │                                       │
│                                      ▼                                       │
│                            ┌───────────────────┐                             │
│                            │ TrainingRun       │                             │
│                            │ Created & Started │                             │
│                            └───────────────────┘                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📅  Create Training Schedule                                           [X] │
│     Creating schedule from Training Run #5                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Model                                                                        │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ product_model_v3                                                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Schedule Name *                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Monthly Product Retraining                                              │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Schedule Type *                                                              │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                 │
│ │ 🕐 Once │ │⏳Hourly │ │ 🔄 Daily│ │📅Weekly │ │📆Monthly│                 │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘                 │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ [If ONCE selected]                                                           │
│ Date & Time *                                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 2026-01-30 14:00                                                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ [If HOURLY selected]                                                         │
│ Run at minute *                                                              │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                                 │
│ │  :00   │ │  :15   │ │  :30   │ │  :45   │                                 │
│ └────────┘ └────────┘ └────────┘ └────────┘                                 │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ [If DAILY selected]                                                          │
│ Time of Day *                                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 09:00                                                                    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ [If WEEKLY selected]                                                         │
│ Time of Day *           Day of Week *                                        │
│ ┌──────────────┐        ┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐                 │
│ │ 09:00        │        │Mon││Tue││Wed││Thu││Fri││Sat││Sun│                 │
│ └──────────────┘        └───┘└───┘└───┘└───┘└───┘└───┘└───┘                 │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ [If MONTHLY selected]                                                        │
│ Day of Month *                                                               │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │  1   2   3   4   5   6   7                                              │ │
│ │  8   9  10  11  12  13  14                                              │ │
│ │ 15  16  17  18  19  20  21                                              │ │
│ │ 22  23  24  25  26  27  28                                              │ │
│ │ [29] [30] [31]  ← Light-red background (may be skipped)                 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ ℹ️ Days 29-31 may be skipped in shorter months                               │
│                                                                              │
│ Time of Day *                                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 09:00                                                                    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Timezone                                                                     │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Europe/Warsaw                                                        [▼] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ▶️ Next run: Monthly on the 15th at 09:00 (Europe/Warsaw)                │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                    [Create]  [Cancel]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REGISTEREDMODEL ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       RegisteredModel                                │   │
│   │  model_name: "product-retrieval-v1"                                 │   │
│   │  model_type: "retrieval"                                            │   │
│   │  total_versions: 3                                                  │   │
│   │  is_deployed: true                                                  │   │
│   └───────────────────────┬─────────────────────────────────────────────┘   │
│                           │                                                  │
│           ┌───────────────┼───────────────┐                                 │
│           │               │               │                                  │
│           ▼               ▼               ▼                                  │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                     │
│   │ TrainingRun   │ │ TrainingRun   │ │ TrainingRun   │                     │
│   │ v1 (deployed) │ │ v2            │ │ v3 (latest)   │                     │
│   └───────────────┘ └───────────────┘ └───────────────┘                     │
│                                                                              │
│                           │                                                  │
│                           ▼                                                  │
│                   ┌───────────────┐                                         │
│                   │ TrainingSchedule│  ←── 1:1 relationship                 │
│                   │ Weekly @ 9AM    │                                       │
│                   └───────────────┘                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Workflow Supported

```
1. User creates training run with name "my-model" + schedule config
   → RegisteredModel("my-model") created (not yet in Vertex AI)
   → TrainingSchedule created, linked to RegisteredModel
   → TrainingRun created and submitted

2. First training run completes
   → Pusher registers to Vertex AI as "my-model" v1
   → RegisteredModel updated with Vertex resource info

3. Schedule triggers (e.g., weekly)
   → New TrainingRun created from schedule's frozen config
   → Completes → Registers as "my-model" v2
   → RegisteredModel version cache updated
```

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

### How to Request GPU Quota

1. **Go to Quotas Page**:
   - URL: https://console.cloud.google.com/iam-admin/quotas?project=YOUR_PROJECT

2. **Filter for GPU Quota**:
   - Service: `Vertex AI API`
   - Search: `custom_model_training_nvidia_t4` (or `nvidia_l4`, etc.)

3. **Select Region** (Important!):
   - Choose `europe-west4` for EU workloads
   - NOT `europe-central2` (no GPU training support)

4. **Request Quota**:
   - Start with 2 GPUs for development/testing
   - Request 4 for production workloads

5. **Description Example**:
   > "Training TensorFlow recommendation models on Vertex AI Pipelines. Development and testing workloads."

6. **Approval Time**: Usually 15 minutes to 48 hours

### Split-Region Pipeline Architecture (2026-01-24)

The training pipeline uses a **split-region architecture** to avoid resource exhaustion in GPU-heavy regions:

- **Pipeline orchestration** runs in `europe-central2` (where data lives)
- **Dataflow jobs** (StatisticsGen, Transform) run in `europe-central2`
- **Trainer component** spawns a Custom Job in `europe-west4` (where GPUs are available)

This approach prevents Dataflow jobs from competing with GPU workloads in `europe-west4`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SPLIT-REGION PIPELINE ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   europe-central2 (Warsaw)                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ ✅ Pipeline Orchestration (Vertex AI Pipelines)                      │   │
│   │ ✅ BigQueryExampleGen (reads from BigQuery)                          │   │
│   │ ✅ StatisticsGen (Dataflow)                                          │   │
│   │ ✅ SchemaGen                                                          │   │
│   │ ✅ Transform (Dataflow)                                               │   │
│   │ ✅ Evaluator                                                          │   │
│   │ ✅ Pusher                                                             │   │
│   └──────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│                                      │ Custom Job spawn                      │
│                                      ▼                                       │
│   europe-west4 (Netherlands)                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ ✅ Trainer (Vertex AI Custom Job with 2x T4 GPUs)                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   Data stays in EU. Only GPU training runs cross-region.                    │
│   Cross-region transfer: ~$0.01/GB (negligible for model artifacts)         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why this architecture?**
- `europe-west4` is a GPU-heavy region that frequently experiences resource exhaustion
- Dataflow jobs don't need GPUs and were failing with "couldn't allocate workers"
- Running Dataflow in `europe-central2` (where data lives) is more efficient
- The Trainer's `GenericExecutor` spawns a separate Custom Job, allowing it to run in a different region

### Running GPU Training Jobs

**1. Submit a test job to verify GPU access:**

```bash
gcloud ai custom-jobs create \
  --project=YOUR_PROJECT \
  --region=europe-west4 \
  --display-name="gpu-test-$(date +%Y%m%d-%H%M%S)" \
  --worker-pool-spec="replica-count=1,machine-type=n1-standard-16,accelerator-type=NVIDIA_TESLA_T4,accelerator-count=2,container-image-uri=europe-central2-docker.pkg.dev/YOUR_PROJECT/tfx-builder/tfx-trainer-gpu:latest" \
  --args="python","-c","import tensorflow as tf; gpus=tf.config.list_physical_devices('GPU'); print('FOUND '+str(len(gpus))+' GPUs'); print(gpus)"
```

**2. Expected output:**
```
FOUND 2 GPUs
[PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU'),
 PhysicalDevice(name='/physical_device:GPU:1', device_type='GPU')]
```

**3. Machine type + GPU combinations (T4):**

| GPUs | Machine Type | vCPUs | Memory |
|------|--------------|-------|--------|
| 1 | n1-standard-8 | 8 | 30 GB |
| 2 | n1-standard-16 | 16 | 60 GB |
| 4 | n1-standard-32 | 32 | 120 GB |

### TrainingService Configuration

The `TrainingService` uses two region constants for split-region execution:

```python
# In ml_platform/training/services.py
class TrainingService:
    REGION = 'europe-central2'           # Data infrastructure region
    GPU_TRAINING_REGION = 'europe-west4' # GPU training region (Trainer only)
    DATAFLOW_REGION = 'europe-central2'  # Dataflow region (StatisticsGen, Transform)
```

The `create_training_pipeline()` function accepts both regions:

```python
def create_training_pipeline(
    ...
    gpu_training_region: str = 'europe-west4',   # For Trainer Custom Job
    dataflow_region: str = 'europe-central2',    # For Dataflow jobs
    ...
):
```

- **Dataflow jobs** use `beam_pipeline_args` with `--region={dataflow_region}`
- **Trainer** uses `VERTEX_REGION_KEY: gpu_training_region` in its custom config
- **Pipeline orchestration** submits to `dataflow_region` (europe-central2)

---

## GPU Types Reference

### Available GPU Types for Vertex AI Training

| GPU | Architecture | VRAM | FP32 TFLOPS | Price/hr* | Best For |
|-----|--------------|------|-------------|-----------|----------|
| **T4** | Turing (2018) | 16 GB | 8.1 | ~$0.35 | Dev/test, small models |
| **L4** | Ada Lovelace (2023) | 24 GB | 30.3 | ~$0.70 | Production, large embeddings |
| **V100** | Volta (2017) | 16 GB | 15.7 | ~$2.50 | Legacy workloads |
| **A100** | Ampere (2020) | 40/80 GB | 19.5/156** | ~$3.50 | Large models, multi-GPU |
| **H100** | Hopper (2022) | 80 GB | 267** | ~$4.50 | Largest models, fastest training |

*Prices are approximate and vary by region. **Tensor Core performance.

### GPU Regional Availability Matrix

| Region | T4 | L4 | V100 | A100 | H100 | Notes |
|--------|----|----|------|------|------|-------|
| `us-central1` (Iowa) | ✅ | ✅ | ✅ | ✅ | ✅ | **Largest capacity, all GPUs** |
| `us-west1` (Oregon) | ✅ | ✅ | ✅ | ✅ | ✅ | Good US West option |
| `us-east4` (Virginia) | ✅ | ✅ | ✅ | ✅ | ❌ | US East |
| `europe-west4` (Netherlands) | ✅ | ✅ | ✅ | ✅ | ❌ | **Best for EU, recommended** |
| `europe-west1` (Belgium) | ✅ | ✅ | ✅ | ✅ | ❌ | Good EU alternative |
| `europe-central2` (Warsaw) | ❌ | ❌ | ❌ | ❌ | ❌ | **No GPU training support** |
| `asia-east1` (Taiwan) | ✅ | ✅ | ✅ | ✅ | ❌ | Best for APAC |

> **Note**: Compute Engine may show GPUs available in a region where Vertex AI training doesn't support them. Always verify with actual job submission.

### Machine Type + GPU Combinations

#### T4 GPU (NVIDIA_TESLA_T4)

| GPUs | Machine Type | vCPUs | Memory | Use Case |
|------|--------------|-------|--------|----------|
| 1 | n1-standard-8 | 8 | 30 GB | Development, small models |
| 2 | n1-standard-16 | 16 | 60 GB | **Recommended for production** |
| 4 | n1-standard-32 | 32 | 120 GB | Large models, faster training |

#### L4 GPU (NVIDIA_L4)

| GPUs | Machine Type | vCPUs | Memory | Use Case |
|------|--------------|-------|--------|----------|
| 1 | g2-standard-8 | 8 | 32 GB | Development |
| 2 | g2-standard-24 | 24 | 96 GB | **Recommended for production** |
| 4 | g2-standard-48 | 48 | 192 GB | Large embeddings |
| 8 | g2-standard-96 | 96 | 384 GB | Very large models |

#### A100 GPU (NVIDIA_TESLA_A100)

| GPUs | Machine Type | vCPUs | Memory | Use Case |
|------|--------------|-------|--------|----------|
| 1 | a2-highgpu-1g | 12 | 85 GB | Single large model |
| 2 | a2-highgpu-2g | 24 | 170 GB | Multi-GPU training |
| 4 | a2-highgpu-4g | 48 | 340 GB | Distributed training |
| 8 | a2-highgpu-8g | 96 | 680 GB | Maximum performance |

### Recommendations by Use Case

| Use Case | Recommended GPU | Config | Reasoning |
|----------|-----------------|--------|-----------|
| **Development/Testing** | T4 x 1-2 | n1-standard-8/16 | Low cost, sufficient for iteration |
| **Production TFRS** | T4 x 2 or L4 x 2 | n1-standard-16 / g2-standard-24 | Good price/performance |
| **Large Embedding Tables** | L4 x 2-4 | g2-standard-24/48 | 24GB VRAM handles large vocabs |
| **Fastest Training** | A100 x 2-4 | a2-highgpu-2g/4g | When time matters more than cost |
| **Budget Conscious** | T4 x 2 preemptible | n1-standard-16 | 70% cheaper, use checkpointing |

### Why Regional GPU Disparity Exists

#### 1. Infrastructure Investment Priorities

Google prioritizes GPU infrastructure in:
- **High-demand regions** (us-central1, europe-west4) - largest ML customer base
- **Established regions** (europe-west1, us-east4) - built out over years
- **Strategic AI hubs** (us-west1 for TPUs, europe-west4 for NVIDIA partnerships)

#### 2. Compute Engine vs Vertex AI

| Aspect | Compute Engine | Vertex AI Training |
|--------|----------------|-------------------|
| GPU presence | Physical hardware | Managed infrastructure |
| What you get | Raw VM with GPU | Orchestrated training jobs |
| Requirements | Just hardware | + Job scheduling, networking, scaling |
| Availability | Broader | More restricted |

A region may have GPUs in Compute Engine (for self-managed VMs) but lack the Vertex AI managed training infrastructure.

#### 3. Regional Specialization

| Region | Focus |
|--------|-------|
| europe-west4 (Netherlands) | Heavy ML/AI, full GPU range, Vertex AI optimized |
| europe-central2 (Warsaw) | General enterprise, data sovereignty for Poland/CEE |
| us-central1 (Iowa) | Largest capacity, all GPU types, TPU access |

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
