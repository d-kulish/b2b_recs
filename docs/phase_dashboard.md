
# Phase: Dashboard Domain

## Document Purpose
This document provides detailed specifications for the **Dashboard** page in the ML Platform. The Dashboard page (`model_dashboard.html`) serves as the central observability hub for deployed models, displaying key performance indicators, charts, and tables for monitoring model endpoints.

**Last Updated**: 2025-02-03 (Initial documentation: Endpoints chapter implementation)

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

## File Structure

### Created Files

| File | Purpose |
|------|---------|
| `templates/ml_platform/model_dashboard.html` | Django template with chapter structure |
| `static/js/model_dashboard_endpoints.js` | IIFE module for Endpoints chapter |
| `static/css/model_dashboard.css` | Styles with `.model-dashboard-` prefix |
| `static/data/demo/model_dashboard_endpoints.json` | Demo data for sales demonstrations |

### Template Structure

```html
{% extends 'base_model.html' %}
{% load static %}

{% block title %}{{ model.name }} - Dashboard{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{% static 'css/model_dashboard.css' %}?v=3">
{% endblock %}

{% block model_content %}
<!-- CHAPTER: ENDPOINTS -->
<div id="endpointsChapter" class="bg-white rounded-xl border border-black shadow-lg p-6">
    <!-- Header -->
    <div class="flex items-center gap-4 mb-6">
        <div class="w-14 h-14 rounded-xl ...">
            <i class="fas fa-chart-line text-white text-2xl"></i>
        </div>
        <h2 class="text-2xl font-bold text-gray-900">Endpoints</h2>
    </div>

    <!-- KPI Row -->
    <div id="endpointsKpiRow" class="model-dashboard-kpi-row"></div>

    <!-- Charts Grid -->
    <div id="endpointsChartsGrid" class="model-dashboard-charts-grid"></div>

    <!-- Tables Section -->
    <div id="endpointsTablesSection" class="model-dashboard-tables-section"></div>
</div>
{% endblock %}

{% block extra_js %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="{% static 'js/model_dashboard_endpoints.js' %}?v=2"></script>
<script>
document.addEventListener('DOMContentLoaded', function() {
    ModelDashboardEndpoints.init();
    ModelDashboardEndpoints.load();
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

1. **Training Metrics** - Loss curves, evaluation metrics, training history
2. **Data Quality** - Feature drift, data distribution changes
3. **A/B Testing** - Experiment results, variant comparison
4. **Alerts** - Active alerts, alert history, notification settings

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2025-02-03 | 1.0 | Initial Endpoints chapter implementation |
