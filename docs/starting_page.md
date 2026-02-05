# Starting Page (System Dashboard)

## Overview

The starting page (`system_dashboard.html`) is the landing page users see when accessing the Recs Studio platform. It provides an overview of the system and quick access to models.

**URL:** `/` (root)
**View:** `ml_platform.views.system_dashboard`
**Template:** `templates/ml_platform/system_dashboard.html`

---

## Design Principles

The starting page is intentionally **different** from model pages to provide clear visual distinction:

| Aspect | Starting Page | Model Pages |
|--------|---------------|-------------|
| Background | Pure white (`#ffffff`) | Dotted pattern |
| Header | No header bar | Full header with KPIs |
| Navigation | None | Horizontal pill tabs |
| Layout | Collapsible chapters | Content containers |

---

## Page Structure

### Header Section

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo]          b2b-recs                        [User Icon]    │
│  Recs Studio     (project ID)                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Components:**
- **Logo** - Positioned identically to model pages (70px height, "Recs Studio" text below)
- **Project ID** - Displayed next to logo, styled like model name (`text-5xl font-bold text-blue-900`)
- **User Profile Icon** - Far right, 44x44px circular icon

**Layout Classes:**
- Outer wrapper: `p-6 pb-0`
- Container: `max-w-[88rem] mx-auto`
- Header row: `px-6 py-3 flex items-center gap-6`

### Main Content

Three collapsible chapters displayed vertically:

1. **System Details** - Platform metrics, charts, and recent activity
2. **Your Models** - Manage ML models and endpoints
3. **Billing** - Usage tracking and subscription details

---

## Chapter Components

### Chapter Container Structure

```html
<div class="chapter-container open" data-chapter="[name]">
    <div class="chapter-header">
        <div class="chapter-title-wrapper">
            <div class="chapter-icon [type]">
                <i class="fas fa-[icon]"></i>
            </div>
            <div class="chapter-title-text">
                <span class="chapter-title">[Title]</span>
                <span class="chapter-subtitle">[Description]</span>
            </div>
        </div>
        <div class="chapter-toggle">
            <i class="fas fa-chevron-right"></i>
        </div>
    </div>
    <div class="chapter-content">
        <div class="chapter-content-inner">
            <!-- Chapter content here -->
        </div>
    </div>
</div>
```

### Chapter Styling

| Property | Value |
|----------|-------|
| Border | 2px solid #1f2937 |
| Border radius | 16px |
| Header padding | 24px 28px |
| Icon size | 48x48px |
| Icon border-radius | 12px |
| Title font-size | 24px |
| Title font-weight | 700 |
| Subtitle font-size | 14px |
| Subtitle color | #6b7280 |

### Chapter Icons

| Chapter | Icon | Background Gradient |
|---------|------|---------------------|
| System Details | `fa-server` | Blue (#3b82f6 → #60a5fa) |
| Your Models | `fa-cube` | Purple (#8b5cf6 → #a78bfa) |
| Billing | `fa-credit-card` | Orange (#f59e0b → #fbbf24) |

---

## Chapter 1: System Details

Displays user-centric metrics with 3 grouped KPI cards, 4 charts, and a recent activity table.

### KPI Groups (3 Cards)

The KPIs are organized into 3 themed cards with icons, stats, and progress bars:

**Inference Card (Green icon):**
| KPI | ID | Data Source |
|-----|----|-------------|
| Active Endpoints | `kpiActiveEndpoints` | `DeployedEndpoint.objects.filter(is_active=True).count()` |
| Requests (7d) | `kpiRequests` | Placeholder (0) |
| Latency | `kpiLatency` | Placeholder (0ms) |
| Progress Bar | `kpiLatencyBar`, `kpiLatencyStatus` | Latency status indicator |

**Training Card (Blue icon):**
| KPI | ID | Data Source |
|-----|----|-------------|
| Runs (30d) | `kpiTrainingRuns` | `TrainingRun` count last 30 days |
| Success Rate | `kpiSuccessRate` | Completed / Total finished * 100 |
| Experiments (30d) | `kpiExperiments` | `QuickTest` count last 30 days |
| Progress Bar | `kpiSuccessBar`, `kpiSuccessStatus` | Success rate percentage |

**Data Card (Purple icon):**
| KPI | ID | Data Source |
|-----|----|-------------|
| ETL Runs (24h) | `kpiEtlRuns` | `ETLRun` count last 24 hours |
| Data Tables | `kpiDataTables` | BigQuery tables count |
| Data Volume | `kpiDataVolume` | Sum of table sizes in GB |
| Progress Bar | `kpiVolumeBar`, `kpiVolumeStatus` | Storage used indicator (100GB max)

### Charts Grid (2x2)

| Chart | Type | Data Source | Period |
|-------|------|-------------|--------|
| Training Activity | Line | TrainingRun (started/completed/failed) | 30 days |
| Model Performance | Line | TrainingRun (best/avg Recall@100) | 30 days |
| Endpoint Requests | Area | Placeholder (future: request logging) | 7 days |
| ETL Health | Stacked Bar | ETLRun (completed/failed) | 14 days |

### Recent Activity Table

Displays last 5 activities merged from:
- `TrainingRun` - Training started/completed/failed
- `QuickTest` - Experiment completed/failed
- `ETLRun` - ETL completed/failed
- `DeployedEndpoint` - Deployment events

**Columns:**
- Type (with icon)
- Status (badge)
- Model name
- Time ago

---

## Chapter 2: Your Models

Lists all models with cards linking to their dashboards.

### Model Card Structure

Each model displays:
- Model name
- Description (truncated to 15 words)
- Status badge (active/draft/inactive/failed)
- Created date
- Last trained date (if applicable)
- Arrow indicator on hover

### Status Badge Colors

| Status | Background | Text Color |
|--------|------------|------------|
| Active | #d1fae5 | #065f46 |
| Draft | #f3f4f6 | #4b5563 |
| Inactive | #fef3c7 | #92400e |
| Failed | #fee2e2 | #991b1b |

### Empty State

When no models exist, displays:
- Large cube icon
- "No models created yet" text
- "Create Your First Model" button

---

## Chapter 3: Billing

Displays subscription and usage information.

**Fields (all hardcoded/demo data):**
- Current Plan: Pro (with gradient badge)
- Billing Period: Feb 1 - Feb 28, 2026
- Training Hours Used: 12.5 / 100 hrs
- API Requests: 47,250 / Unlimited
- Current Charges: $0.00 (green)

---

## API Endpoints

### `GET /api/system/kpis/`

Returns system KPIs for the 3 grouped cards.

**Response:**
```json
{
    "success": true,
    "data": {
        "models": 5,
        "live_endpoints": 2,
        "training_runs_30d": 15,
        "training_success_rate": 87.5,
        "experiments_30d": 23,
        "etl_runs_24h": 3,
        "data_tables": 12,
        "data_volume_gb": 4.56,
        "requests_7d": 0,
        "avg_latency_ms": 0
    }
}
```

### `GET /api/system/charts/`

Returns 4 chart datasets.

**Response:**
```json
{
    "success": true,
    "data": {
        "training_activity": {
            "labels": ["2026-01-15", "2026-01-16", ...],
            "started": [2, 1, ...],
            "completed": [1, 2, ...],
            "failed": [0, 0, ...]
        },
        "model_performance": {
            "labels": ["2026-01-15", ...],
            "best": [85.5, 86.2, ...],
            "avg": [78.3, 79.1, ...]
        },
        "endpoint_requests": {
            "labels": ["2026-01-29", ...],
            "requests": [0, 0, ...]
        },
        "etl_health": {
            "labels": ["2026-01-22", ...],
            "completed": [3, 2, ...],
            "failed": [0, 1, ...]
        }
    }
}
```

### `GET /api/system/recent-activity/`

Returns last 5 activities merged from multiple sources.

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "type": "Training",
            "status": "completed",
            "model": "product-recs",
            "time": "2026-02-05T10:30:00Z",
            "time_ago": "2h ago"
        },
        ...
    ]
}
```

---

## JavaScript

### Toggle Function

```javascript
function toggleChapter(header) {
    const container = header.closest('.chapter-container');
    container.classList.toggle('open');
}
```

### SystemDashboard Module

IIFE module that manages dashboard data loading:

```javascript
const SystemDashboard = (function() {
    // Chart instances for cleanup
    let charts = {};

    // Public methods
    return {
        loadKPIs,        // Fetch and populate KPI values
        loadCharts,      // Fetch and render Chart.js charts
        loadRecentActivity  // Fetch and render activity table
    };
})();
```

**Key Features:**
- Destroys charts before recreating (prevents memory leaks)
- Graceful fallbacks for missing data ("No data available")
- Status badge color mapping
- Time ago formatting

---

## Context Variables

The view provides these context variables:

| Variable | Type | Description |
|----------|------|-------------|
| `models` | QuerySet | All ModelEndpoint objects |
| `total_models` | int | Count of all models |
| `active_models` | int | Count of models with status='active' |

---

## Dependencies

- **Tailwind CSS** 3.4.10 (CDN)
- **Font Awesome** 6.4.0 (CDN)
- **Chart.js** 4.4.0 (CDN)

---

## Graceful Fallbacks

| Scenario | Behavior |
|----------|----------|
| BigQuery unavailable | `data_tables: 0`, `data_volume_gb: 0` |
| No training data | Charts show "No data available" |
| Empty activity | Table shows "No recent activity" |
| API error | KPIs show "0", console error logged |

---

## Future Enhancements

- [ ] Dynamic project ID from settings/database
- [ ] Real billing data from subscription service
- [ ] User profile dropdown menu
- [ ] Quick actions in header
- [x] ~~Recent activity feed~~ (Implemented)
- [ ] Real endpoint request metrics (currently placeholder)
