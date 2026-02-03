
# Phase: Dashboard Domain

## Document Purpose
This document provides detailed specifications for the **Dashboard** page in the ML Platform. The Dashboard page (`model_dashboard.html`) serves as the central observability hub for deployed models, displaying key performance indicators, charts, and tables for monitoring model endpoints and registered models.

**Last Updated**: 2026-02-03 (Fixed ExpViewModal experiment mode tabs, added pipeline_dag.js and d3.js dependencies)

---

## Page Overview

The Model Dashboard (`/model/{id}/dashboard/`) is accessible via the horizontal navigation bar on any model page. It provides a comprehensive view of endpoint performance metrics and operational data.

**URL Pattern**: `/model/<model_id>/dashboard/`
**Template**: `templates/ml_platform/model_dashboard.html`
**Base Template**: `base_model.html`

---

## Chapter 1: Endpoints

The Endpoints chapter displays observability data for all serving endpoints associated with the model. It includes KPIs, time-series charts, and performance tables.

### Visual Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ [Chart Icon] Endpoints                                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────┐  ┌─────────────────────────────────┐  │
│  │ SERVING ENDPOINTS                   │  │ ┌─────────┐ ┌─────────┐        │  │
│  │                                     │  │ │ 47.3K   │ │ 142ms   │        │  │
│  │ [Rocket] [4 TOTAL] [0 ACTV] [4 IN] │  │ │Requests │ │Latency  │        │  │
│  │                                     │  │ └─────────┘ └─────────┘        │  │
│  │          (40% width)                │  │ ┌─────────┐ ┌─────────┐        │  │
│  │                                     │  │ │ 0.04%   │ │ 8       │        │  │
│  └─────────────────────────────────────┘  │ │ Errors  │ │Peak/Avg │        │  │
│                                            │ └─────────┘ └─────────┘        │  │
│                                            │        (60% width)              │  │
│                                            └─────────────────────────────────┘  │
│                                                                                 │
│  ┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────┐│
│  │ Request Volume Over Time│ │ Latency P50/P95/P99     │ │ Container Instances ││
│  │ [stacked area chart]    │ │ [multi-line chart]      │ │ [stacked area]      ││
│  └─────────────────────────┘ └─────────────────────────┘ └─────────────────────┘│
│                                                                                 │
│  ┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────┐│
│  │ Error Rate Over Time    │ │ Cold Start Latency      │ │ Resource Utilization││
│  │ [line chart]            │ │ [horizontal bar]        │ │ [dual Y-axis]       ││
│  └─────────────────────────┘ └─────────────────────────┘ └─────────────────────┘│
│                                                                                 │
│  ┌─────────────────────────────────────┐ ┌─────────────────────────────────────┐│
│  │ Endpoint Performance Table          │ │ Peak Usage Periods                  ││
│  └─────────────────────────────────────┘ └─────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
```

### KPI Section (7 Metrics)

The KPI section uses a **grouped layout** with two main containers:

#### Grouped Summary Card (40% width)
Contains endpoint status metrics in a single card:

| Metric | Description | Visual |
|--------|-------------|--------|
| Total | Total number of endpoints | Neutral color |
| Active | Running endpoints | Green (#10b981) |
| Inactive | Stopped endpoints | Red (#ef4444) |

**Layout**: Title "SERVING ENDPOINTS" on top, rocket icon + 3 stat boxes in a horizontal row below.

#### Performance KPI Grid (60% width)
A 2x2 grid of performance metrics:

| Metric | Icon | Description | Change Indicator |
|--------|------|-------------|------------------|
| Requests (7D) | `fa-chart-bar` | Total requests in last 7 days | % change (positive = green) |
| Latency (P95) | `fa-clock` | 95th percentile latency | ms change (negative = green) |
| Error Rate | `fa-exclamation-circle` | Error percentage | Trend text (stable/up/down) |
| Peak / Avg | `fa-server` | Peak instances with avg | "avg X.X" subtitle |

### Charts Section (6 Charts)

Charts are displayed in a 3-column grid (2 rows x 3 columns):

| Chart | Type | Data Source | Features |
|-------|------|-------------|----------|
| Request Volume Over Time | Stacked Area | `request_volume` | Per-endpoint breakdown, 7-day period |
| Latency Distribution | Multi-line | `latency_distribution` | P50/P95/P99 lines with different styles |
| Container Instances | Stacked Area | `container_instances` | Per-endpoint scaling visualization |
| Error Rate Over Time | Line + Fill | `error_rate` | Threshold line, spike highlighting |
| Cold Start Latency | Horizontal Bar | `cold_start_latency` | P50/P95 bars per endpoint |
| Resource Utilization | Dual Y-axis | `resource_utilization` | CPU (filled) and Memory (line) |

**Chart Library**: Chart.js (loaded from CDN)

### Tables Section (2 Tables)

Tables displayed in a 2-column grid:

#### Endpoint Performance Table
| Column | Description |
|--------|-------------|
| Endpoint | Name with color indicator |
| Requests | Total request count |
| Avg | Average latency (ms) |
| P95 | 95th percentile latency (ms) |
| Errors | Error count with percentage |
| Trend | Directional arrow with % change |

#### Peak Usage Periods Table
| Column | Description |
|--------|-------------|
| Time Period | Day and time range |
| Endpoint | Endpoint name with color indicator |
| Requests | Request count during peak |
| Max Instances | Maximum container instances |

---

## Chapter 2: Models

The Models chapter displays registered models from Vertex AI Model Registry with KPIs, training activity calendar, filtering, and a paginated table. It mirrors the Models Registry from the Training page but excludes scheduling-related elements.

### Visual Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ [Cube Icon] Models                                                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                   │
│  │ 7       │ │ 0       │ │ 0       │ │ 7       │ │ 0       │                   │
│  │ TOTAL   │ │DEPLOYED │ │OUTDATED │ │ IDLE    │ │SCHEDULED│                   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘                   │
│                                                                                 │
│  [Calendar Icon] Training Activity                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ DEC   JAN   FEB   MAR   APR   MAY   JUN   JUL   AUG                         ││
│  │ Mon  ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢      ││
│  │ Wed  ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢      ││
│  │ Fri  ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ■ ■ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢      ││
│  │ Sun  ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ■ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢ ▢      ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                                                                 │
│  [Model Type ▼] [Deployment ▼] [Sort By ▼] [Search...                        ] │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ # │ Model Name       │ Type     │ Deployment │ Version │ Metrics │Age│Action││
│  │───┼──────────────────┼──────────┼────────────┼─────────┼─────────┼───┼──────││
│  │ 1 │ model_name       │ Retrieval│ DEPLOYED   │ v1      │ R@5 ... │2d │ View ││
│  │ 2 │ model_name       │ Ranking  │ IDLE       │ v1      │ RMSE... │5d │ View ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                                                                 │
│  Showing 1-5 of 7 models                    [Previous] [1] [2] [Next]          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### KPI Section (5 Cards)

A row of 5 KPI cards displaying model statistics from the `/api/models/` endpoint:

| KPI | Icon | Color | Description |
|-----|------|-------|-------------|
| Total Models | `fa-cube` | Purple (#8b5cf6) | Total registered models |
| Deployed | `fa-rocket` | Green (#10b981) | Models currently deployed |
| Outdated | `fa-exclamation-triangle` | Orange (#f59e0b) | Models with newer versions available |
| Idle | `fa-pause-circle` | Gray (#6b7280) | Models not deployed |
| Scheduled | `fa-clock` | Blue (#3b82f6) | Models with active training schedules |

### Training Activity Calendar

GitHub-style contribution calendar showing training activity over time. Uses the `ScheduleCalendar` component with data from `/api/training-schedules/calendar/`.

**Features**:
- Historical training runs (green squares)
- Projected scheduled runs (blue dashed squares)
- Today marker (blue outline)
- Tooltip on hover showing activity details
- Popover on click with run/schedule details

### Filter Bar

| Filter | Type | Options |
|--------|------|---------|
| Model Type | Dropdown | All Types, Retrieval, Ranking, Multitask |
| Deployment | Dropdown | All, Deployed, Outdated, Idle |
| Sort By | Dropdown | Latest, Oldest, Best Metrics, Name A-Z |
| Search | Text Input | Debounced search (300ms) |

### Models Table

| Column | Content | Notes |
|--------|---------|-------|
| # | Row number | Calculated from pagination |
| Model Name | Name + "Run #N" | Two-line cell |
| Type | Badge | Retrieval (blue), Ranking (yellow), Multitask (purple) |
| Deployment | Badge | Deployed (green pill), Outdated (orange pill), Idle (blue pill) |
| Version | v{N} | Version badge |
| Metrics | 4 values | Model-type specific with min-width alignment |
| Age | Days | Color-coded: green (≤7d), orange (8-14d), red (>14d) |
| Actions | Button | Green "View" button only |

**Metrics by Model Type**:
- **Retrieval**: R@5, R@10, R@50, R@100
- **Ranking**: RMSE, Test RMSE, MAE, Test MAE
- **Multitask**: R@50, R@100, RMSE, Test RMSE

### Pagination

Uses Tailwind CSS classes matching the Models Registry:
- Active page: `bg-blue-600 text-white`
- Inactive pages: `border-gray-300 hover:bg-blue-50`
- Previous/Next buttons with disabled states
- "Showing X-Y of Z models" text

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/models/` | Fetch models with filters, pagination, KPI data |
| `GET /api/training-schedules/calendar/` | Fetch calendar data for heatmap |

### Modal Integration: ExpViewModal

The View button and table row clicks open the `ExpViewModal` in model mode to display comprehensive model details.

**Integration Components**:
- **CSS**: `exp_view_modal.css` - Modal styling
- **HTML**: `_exp_view_modal.html` - Modal template (included inside `model_content` block)
- **JS**: `exp_view_modal.js` - Modal logic with `openForModel()` method

**Configuration** (in DOMContentLoaded):
```javascript
ExpViewModal.configure({
    showTabs: ['overview', 'versions', 'artifacts', 'deployment', 'lineage'],
    onClose: function() {
        ModelDashboardModels.refresh();
    },
    onUpdate: function(data) {
        ModelDashboardModels.refresh();
    }
});
```

**Tabs Displayed in Model Mode**:
| Tab | Content |
|-----|---------|
| Overview | Dataset, features config, model config, metrics |
| Versions | Version history with metrics comparison (read-only, no deploy buttons) |
| Artifacts | GCS paths, Vertex AI resource names |
| Deployment | Deploy/undeploy actions |
| Lineage | Model lineage visualization |

**API Called**: `GET /api/models/{modelId}/` - Fetches full model details for modal population

---

## Chapter 3: Experiments

The Experiments chapter displays experiment analytics from the Experiments page, including model type KPIs, metrics trend chart, and top configurations table.

### Visual Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ [Flask Icon] Experiments                                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────────┐  ┌───────────────────────────────────────────────┐│
│  │ [🔍] RETRIEVAL  (selected)│  │ METRICS TREND                                ││
│  │ Experiments: 23           │  │ Best Recall metrics over time                ││
│  │ R@5: 0.055 | R@10: 0.088 │  │ ┌─────────────────────────────────────────┐  ││
│  │ R@50: 0.213 | R@100: 0.317│  │ │   📈 Multi-line area chart              │  ││
│  ├──────────────────────────┤  │ │   (R@100, R@50, R@10, R@5)              │  ││
│  │ [📊] RANKING              │  │ │                                         │  ││
│  │ Experiments: 3            │  │ └─────────────────────────────────────────┘  ││
│  │ RMSE: 0.498 | Test: 0.500 │  │                                              ││
│  │ MAE: 0.329 | Test: 0.329  │  └───────────────────────────────────────────────┘│
│  ├──────────────────────────┤                                                   │
│  │ [🔀] HYBRID               │                                                   │
│  │ Experiments: 4            │                                                   │
│  │ (40% width)               │                  (60% width)                      │
│  └──────────────────────────┘                                                   │
│                                                                                 │
│  TOP CONFIGURATIONS                                                             │
│  Best performing retrieval experiments (by R@100)                               │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ # │ Experiment │ Dataset │ Feature │ Model │ LR  │Batch│Epochs│R@100│ Loss ││
│  │───┼────────────┼─────────┼─────────┼───────┼─────┼─────┼──────┼─────┼──────││
│  │ 1 │ Exp #62    │ old_... │cherng_v2│scann_v│0.001│1024 │ 50   │0.317│2555.7││
│  │ 2 │ Exp #50    │ old_... │cherng_v2│chernig│0.001│1024 │ 50   │0.317│2730.8││
│  └─────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Model Type KPI Sections (40% width)

Three clickable KPI containers that filter the dashboard content:

| Section | Icon | Color | Metrics Displayed |
|---------|------|-------|-------------------|
| Retrieval | `fa-search` | Green (#10b981) | Experiments, R@5, R@10, R@50, R@100 |
| Ranking | `fa-sort-amount-down` | Orange (#f59e0b) | Experiments, RMSE, Test RMSE, MAE, Test MAE |
| Hybrid | `fa-layer-group` | Purple (#8b5cf6) | Experiments, RMSE, Test RMSE, R@50, R@100 |

**Behavior**: Clicking a section highlights it with a blue border and reloads the Metrics Trend chart and Top Configurations table for that model type.

### Metrics Trend Chart (60% width)

Chart.js line chart showing best metrics over time:

| Model Type | Lines | Colors | Fill Pattern |
|------------|-------|--------|--------------|
| Retrieval | R@100, R@50, R@10, R@5 | Green, Blue, Orange, Red | Cascading fill |
| Ranking | RMSE, Test RMSE, MAE, Test MAE | Orange variants, Green variants | Area fill |
| Hybrid | Recall (left Y-axis), RMSE (right Y-axis) | Mixed | Dual Y-axis |

**Features**:
- Legend in top-right corner
- Tooltip showing experiment count
- Responsive height (200px)
- Empty state when < 2 data points

### Top Configurations Table

Table showing top 5 experiments ranked by primary metric:

| Column | Retrieval | Ranking | Hybrid |
|--------|-----------|---------|--------|
| # | Rank (1-5) | Rank (1-5) | Rank (1-5) |
| Experiment | Display name | Display name | Display name |
| Dataset | Dataset name | Dataset name | Dataset name |
| Feature | Feature config | Feature config | Feature config |
| Model | Model config | Model config | Model config |
| LR | Learning rate | Learning rate | Learning rate |
| Metric 1 | Batch size | Batch size | R@100 |
| Metric 2 | Epochs | Epochs | R@50 |
| Metric 3 | R@100 (highlighted) | Test RMSE (highlighted) | Test RMSE |
| Metric 4 | Loss | Test MAE | Test MAE |

**Styling**:
- Rank 1: Gold (#f59e0b)
- Rank 2: Silver (#9ca3af)
- Rank 3: Bronze (#b45309)
- Best metric: Green highlight (#10b981)
- Clickable rows open ExpViewModal

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/experiments/dashboard-stats/` | KPI data for all three model types |
| `GET /api/experiments/metrics-trend/?model_type=X` | Trend data for chart |
| `GET /api/experiments/top-configurations/?limit=5&model_type=X` | Top 5 configs table |

### Modal Integration

Table row clicks open `ExpViewModal.open(expId)` to display experiment details. The modal automatically shows experiment-specific tabs based on `state.mode`:

**Tabs Displayed in Experiment Mode**:
| Tab | Content |
|-----|---------|
| Overview | Dataset, features config, model config, metrics |
| Pipeline | TFX pipeline DAG visualization (requires `pipeline_dag.js`) |
| Data Insights | TFDV statistics, schema validation |
| Training Runs | Loss curves, weight histograms (requires `d3.js`) |

**Note**: The `ExpViewModal` handles tab visibility per mode in `updateVisibleTabs()`. Experiment mode tabs are hardcoded to `['overview', 'pipeline', 'data', 'training']` regardless of page-level `config.showTabs` setting.

---

## File Structure

### Created Files

| File | Purpose |
|------|---------|
| `templates/ml_platform/model_dashboard.html` | Django template with chapter structure |
| `static/js/model_dashboard_endpoints.js` | IIFE module for Endpoints chapter |
| `static/js/model_dashboard_models.js` | IIFE module for Models chapter |
| `static/js/model_dashboard_experiments.js` | IIFE module for Experiments chapter |
| `static/css/model_dashboard.css` | Styles with `.model-dashboard-` prefix |
| `static/data/demo/model_dashboard_endpoints.json` | Demo data for Endpoints (sales demonstrations) |

### Dependencies

| File | Purpose |
|------|---------|
| `static/js/schedule_calendar.js` | GitHub-style calendar component |
| `static/css/schedule_calendar.css` | Calendar styles |
| `static/js/exp_view_modal.js` | Model/experiment view modal with tabs |
| `static/css/exp_view_modal.css` | Modal styling |
| `static/js/pipeline_dag.js` | TFX pipeline DAG visualization |
| `static/css/pipeline_dag.css` | Pipeline DAG styles |
| `templates/includes/_exp_view_modal.html` | Modal HTML template |

### External Libraries (CDN)

| Library | Version | Purpose |
|---------|---------|---------|
| Chart.js | latest | Line charts, area charts |
| D3.js | v7 | Weight distribution histograms in Training tab |

### Template Structure

```html
{% extends 'base_model.html' %}
{% load static %}

{% block title %}{{ model.name }} - Dashboard{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{% static 'css/model_dashboard.css' %}?v=5">
<link rel="stylesheet" href="{% static 'css/schedule_calendar.css' %}">
<link rel="stylesheet" href="{% static 'css/exp_view_modal.css' %}?v=3">
<link rel="stylesheet" href="{% static 'css/pipeline_dag.css' %}?v=1">
{% endblock %}

{% block model_content %}
<!-- CHAPTER: ENDPOINTS -->
<div id="endpointsChapter" class="bg-white rounded-xl border border-black shadow-lg p-6">
    ...
</div>

<!-- CHAPTER: MODELS -->
<div id="modelsChapter" class="bg-white rounded-xl border border-black shadow-lg p-6 mt-6">
    ...
</div>

<!-- CHAPTER: EXPERIMENTS -->
<div id="experimentsChapter" class="bg-white rounded-xl border border-black shadow-lg p-6 mt-6">
    <div class="flex items-center gap-4 mb-6">
        <div class="w-14 h-14 rounded-xl ..." style="background: linear-gradient(135deg, #10b981, #34d399);">
            <i class="fas fa-flask text-white text-2xl"></i>
        </div>
        <h2 class="text-2xl font-bold text-gray-900">Experiments</h2>
    </div>
    <div id="experimentsKpiTrendRow" class="model-dashboard-experiments-kpi-trend-row"></div>
    <div id="experimentsTopConfigsSection" class="model-dashboard-experiments-section"></div>
</div>

<!-- ExpViewModal (must be inside model_content block) -->
{% include 'includes/_exp_view_modal.html' %}
{% endblock %}

{% block extra_js %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="{% static 'js/pipeline_dag.js' %}?v=2"></script>
<script src="{% static 'js/exp_view_modal.js' %}?v=4"></script>
<script src="{% static 'js/schedule_calendar.js' %}"></script>
<script src="{% static 'js/model_dashboard_endpoints.js' %}?v=2"></script>
<script src="{% static 'js/model_dashboard_models.js' %}?v=1"></script>
<script src="{% static 'js/model_dashboard_experiments.js' %}?v=3"></script>
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Configure ExpViewModal for model viewing (used by Models chapter)
    // Note: Experiment mode tabs are hardcoded in updateVisibleTabs()
    ExpViewModal.configure({
        showTabs: ['overview', 'versions', 'artifacts', 'deployment', 'lineage'],
        onClose: function() {
            ModelDashboardModels.refresh();
            ModelDashboardExperiments.refresh();
        },
        onUpdate: function(data) {
            ModelDashboardModels.refresh();
            ModelDashboardExperiments.refresh();
        }
    });

    ModelDashboardEndpoints.init();
    ModelDashboardEndpoints.load();
    ModelDashboardModels.init();
    ModelDashboardModels.load();
    ModelDashboardExperiments.init();
    ModelDashboardExperiments.load();
});
</script>
{% endblock %}
```

---

## JavaScript Module: ModelDashboardEndpoints

### Public API

```javascript
ModelDashboardEndpoints.init(options)  // Initialize with optional config overrides
ModelDashboardEndpoints.load()         // Load and render data
ModelDashboardEndpoints.refresh()      // Clear cache and reload
```

### Configuration Options

```javascript
{
    containerId: '#endpointsChapter',
    kpiContainerId: '#endpointsKpiRow',
    chartsContainerId: '#endpointsChartsGrid',
    tablesContainerId: '#endpointsTablesSection',
    chartHeight: 220
}
```

### Demo Mode

The module operates in demo mode by default (`DEMO_MODE = true`), loading data from:
```
/static/data/demo/model_dashboard_endpoints.json
```

### Endpoint Colors

Consistent color palette for up to 3 endpoints:
```javascript
const ENDPOINT_COLORS = [
    { primary: '#3b82f6', light: 'rgba(59, 130, 246, 0.2)' },  // Blue
    { primary: '#10b981', light: 'rgba(16, 185, 129, 0.2)' },  // Green
    { primary: '#8b5cf6', light: 'rgba(139, 92, 246, 0.2)' }   // Purple
];
```

---

## JavaScript Module: ModelDashboardModels

### Public API

```javascript
ModelDashboardModels.init(options)      // Initialize with optional config overrides
ModelDashboardModels.load()             // Load and render data
ModelDashboardModels.refresh()          // Reload without resetting filters
ModelDashboardModels.setFilter(key, value)  // Set filter and refetch
ModelDashboardModels.handleSearch(value)    // Debounced search handler
ModelDashboardModels.viewDetails(modelId)   // Open ExpViewModal
ModelDashboardModels.nextPage()         // Navigate to next page
ModelDashboardModels.prevPage()         // Navigate to previous page
ModelDashboardModels.goToPage(page)     // Navigate to specific page
```

### Configuration Options

```javascript
{
    containerId: '#modelsChapter',
    kpiContainerId: '#modelsChapterKpiRow',
    calendarContainerId: '#modelsChapterCalendar',
    filterBarId: '#modelsChapterFilterBar',
    tableContainerId: '#modelsChapterTable',
    emptyStateId: '#modelsChapterEmptyState',
    endpoints: {
        list: '/api/models/'
    }
}
```

### State Structure

```javascript
state = {
    models: [],
    kpi: { total: 0, deployed: 0, outdated: 0, idle: 0, scheduled: 0 },
    pagination: { page: 1, pageSize: 5, totalCount: 0, totalPages: 1 },
    filters: { modelType: 'all', status: 'all', sort: 'latest', search: '' },
    loading: false,
    searchDebounceTimer: null,
    initialized: false
}
```

### Data Mode

Unlike the Endpoints chapter (which uses demo data), the Models chapter fetches **real data** from the `/api/models/` API endpoint with the same parameters as the Models Registry on the Training page.

---

## JavaScript Module: ModelDashboardExperiments

### Public API

```javascript
ModelDashboardExperiments.init(options)        // Initialize with optional config overrides
ModelDashboardExperiments.load()               // Load KPIs, trend chart, and top configs
ModelDashboardExperiments.refresh()            // Reload all data
ModelDashboardExperiments.selectModelType(type) // Switch model type filter ('retrieval', 'ranking', 'hybrid')
ModelDashboardExperiments.openExpDetails(expId) // Open ExpViewModal for experiment
```

### Configuration Options

```javascript
{
    kpiTrendContainerId: '#experimentsKpiTrendRow',
    topConfigsContainerId: '#experimentsTopConfigsSection',
    endpoints: {
        dashboardStats: '/api/experiments/dashboard-stats/',
        metricsTrend: '/api/experiments/metrics-trend/',
        topConfigurations: '/api/experiments/top-configurations/'
    },
    chartHeight: 200,
    topConfigsLimit: 5
}
```

### State Structure

```javascript
state = {
    kpis: null,           // KPI data for all model types
    loading: false,
    initialized: false
}
// selectedModelType = 'retrieval' (module-level variable)
```

### Data Mode

The Experiments chapter fetches **real data** from the `/api/experiments/` API endpoints, reusing the same endpoints as the Experiments Dashboard on the Experiments page.

---

## CSS Architecture

### Class Naming Convention

All classes use `.model-dashboard-` prefix to avoid conflicts:

```css
.model-dashboard-kpi-row          /* KPI section container */
.model-dashboard-summary-card     /* Grouped endpoint status card */
.model-dashboard-performance-grid /* 2x2 KPI card grid */
.model-dashboard-kpi-card         /* Individual KPI card */
.model-dashboard-charts-grid      /* 3-column chart grid */
.model-dashboard-chart-card       /* Chart container */
.model-dashboard-tables-section   /* 2-column table grid */
.model-dashboard-table-card       /* Table container */
.model-dashboard-table            /* Table element */
```

### Grid Layout

```css
/* KPI Row: Summary (40%) + Performance Grid (60%) */
.model-dashboard-kpi-row {
    display: grid;
    grid-template-columns: 2fr 3fr;
    gap: 16px;
}

/* Performance KPIs: 2x2 grid */
.model-dashboard-performance-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: repeat(2, 1fr);
    gap: 12px;
}

/* Charts: 3-column grid */
.model-dashboard-charts-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
}

/* Tables: 2-column grid */
.model-dashboard-tables-section {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
}
```

### Responsive Breakpoints

| Breakpoint | KPI Row | Charts | Tables |
|------------|---------|--------|--------|
| > 1200px | 2fr 3fr (40/60) | 3 columns | 2 columns |
| 900-1200px | 1 column, performance 4-col | 2 columns | 1 column |
| < 900px | 1 column, performance 2x2 | 2 columns | 1 column |
| < 768px | 1 column, stacked | 1 column | 1 column |

---

## Demo Data Structure

```json
{
  "endpoints_summary": {
    "total": 4,
    "active": 0,
    "inactive": 4
  },
  "endpoints": [
    { "id": "ep-001", "name": "chern-retrieval-v5", "status": "running", "color": "#3b82f6" }
  ],
  "kpi_summary": {
    "total_requests": 47250,
    "total_requests_change_pct": 12.3,
    "avg_latency_p95_ms": 142,
    "avg_latency_change_ms": -8,
    "error_rate_pct": 0.04,
    "error_rate_trend": "stable",
    "peak_instances": 8,
    "avg_instances": 2.4
  },
  "request_volume": { "labels": [...], "endpoints": [...] },
  "latency_distribution": { "labels": [...], "p50": [...], "p95": [...], "p99": [...] },
  "container_instances": { "labels": [...], "endpoints": [...] },
  "error_rate": { "labels": [...], "values": [...], "threshold": 1.0 },
  "cold_start_latency": { "endpoints": [...] },
  "resource_utilization": { "labels": [...], "cpu_percent": [...], "memory_percent": [...] },
  "endpoint_performance": [...],
  "peak_periods": [...]
}
```

---

## Future Chapters (Planned)

The Dashboard page may expand to include additional chapters:

1. **Data Quality** - Feature drift, data distribution changes
2. **A/B Testing** - Experiment results, variant comparison
3. **Alerts** - Active alerts, alert history, notification settings

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-03 | 1.4 | Fixed ExpViewModal experiment mode tabs, added pipeline_dag.js and d3.js dependencies |
| 2026-02-03 | 1.3 | Added Experiments chapter with KPIs, Metrics Trend chart, Top Configurations table |
| 2025-02-03 | 1.2 | Added ExpViewModal integration for View button functionality |
| 2025-02-03 | 1.1 | Added Models chapter with KPIs, calendar, filter bar, table |
| 2025-02-03 | 1.0 | Initial Endpoints chapter implementation |
