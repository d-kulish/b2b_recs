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
2. **Your Projects** - Manage ML models and endpoints
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
| Your Projects | `fa-cube` | Purple (#8b5cf6 → #a78bfa) |
| Billing | `fa-credit-card` | Orange (#f59e0b → #fbbf24) |

---

## Chapter 1: System Details

Displays user-centric metrics with 3 grouped KPI cards and 6 resource-oriented charts in a 3-column layout.

### KPI Groups (3 Cards)

The KPIs are organized into 3 themed cards with icons, stats, and progress bars:

**Inference Card (Green icon):**
| KPI | ID | Data Source |
|-----|----|-------------|
| Active Endpoints | `kpiActiveEndpoints` | `DeployedEndpoint.objects.filter(is_active=True).count()` |
| Requests (30d) | `kpiRequests` | Sum of `cloud_run_total_requests` over last 30 days |
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

### Resource Charts (3 columns x 2 rows)

Data is sourced from the `ResourceMetrics` model (daily snapshots collected by `collect_resource_metrics` management command).

**Column 1: Data** (Blue palette, `#4285f4`)

| Chart | Type | Data Source | Period |
|-------|------|-------------|--------|
| BigQuery / SQL / Buckets | Stacked Bar (3 segments) | `bq_total_bytes`, `db_size_bytes`, `gcs_total_bytes` | 30 days |
| Jobs & Bytes Billed | Bar + Line (dual-axis) | `bq_jobs_completed`, `bq_jobs_failed`, `bq_bytes_billed` | 30 days |

**Column 2: Cloud Run** (Green palette, `#34a853`)

| Chart | Type | Data Source | Period |
|-------|------|-------------|--------|
| ETL Jobs | Stacked Bar | `ETLRun` model (completed/failed by day) | 30 days |
| Request Volume | Line (filled) | `cloud_run_total_requests` via Cloud Monitoring API | 30 days |

**Column 3: Compute & GPU** (Red palette, `#ea4335`)

| Chart | Type | Data Source | Period |
|-------|------|-------------|--------|
| GPU Training Hours | Bar | `gpu_training_hours` | 30 days |
| Training Jobs | Bar | `gpu_jobs_completed`, `gpu_jobs_failed` | 30 days |

### ResourceMetrics Model

Daily snapshot model storing GCP resource usage. Populated by `python manage.py collect_resource_metrics` or automatically via a Cloud Scheduler job (daily at 02:00 UTC).

| Field | Type | Description |
|-------|------|-------------|
| `date` | DateField | Snapshot date (unique) |
| `bq_total_bytes` | BigIntegerField | Total BigQuery storage |
| `bq_table_details` | JSONField | Per-table breakdown `[{name, bytes, rows}]` |
| `bq_jobs_completed` | IntegerField | Completed BQ jobs |
| `bq_jobs_failed` | IntegerField | Failed BQ jobs |
| `bq_bytes_billed` | BigIntegerField | Total bytes billed |
| `cloud_run_services` | JSONField | Service list `[{name, status, is_ml_serving}]` |
| `cloud_run_active_services` | IntegerField | Count of active services |
| `cloud_run_total_requests` | IntegerField | Total ML serving requests on this day |
| `cloud_run_request_details` | JSONField | Per-service breakdown `[{name, requests, errors}]` |
| `db_size_bytes` | BigIntegerField | PostgreSQL database size |
| `db_table_details` | JSONField | Top tables `[{name, size_bytes, row_count}]` |
| `gcs_bucket_details` | JSONField | Bucket usage `[{name, total_bytes, object_count}]` |
| `gcs_total_bytes` | BigIntegerField | Total GCS storage |
| `etl_jobs_completed` | IntegerField | ETL jobs completed on this day |
| `etl_jobs_failed` | IntegerField | ETL jobs failed on this day |

---

## Chapter 2: Your Projects

Displays grouped KPI containers for assets and model accuracy, plus model cards linking to their dashboards.

### KPI Containers (2-column grid)

Two `system-kpi-card` containers reusing the same CSS classes as Chapter 1's KPI groups, displayed in a flex row with a "+ Create New Model" button to the right.

**Assets Card (Purple icon, `fa-folder-open`):**

| KPI | Context Variable | Data Source |
|-----|-----------------|-------------|
| Projects | `total_models` | `ModelEndpoint.objects.count()` |
| Models | `total_registered_models` | `RegisteredModel.objects.count()` |
| Trainings | `total_trainings` | `TrainingRun.objects.count()` |
| Experiments | `total_experiments` | `QuickTest.objects.count()` |

**Accuracy Card (Green icon, `fa-bullseye`):**

| KPI | Context Variable | Data Source | Format |
|-----|-----------------|-------------|--------|
| Retrieval | `best_retrieval_recall` | Best `recall_at_100` from retrieval TrainingRuns | `81.2%` or `--` |
| Ranking | `best_ranking_rmse` | Best (lowest) `rmse` from ranking TrainingRuns | `0.45` or `--` |
| Hybrid | `best_hybrid_recall` | Best `recall_at_100` from multitask TrainingRuns | `81.2%` or `--` |

The "+ Create New Model" button sits to the right of the KPI grid in the chapter header area (uses `event.stopPropagation()` to avoid triggering the chapter toggle).

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
        "requests_30d": 0,
        "avg_latency_ms": 0
    }
}
```

### `GET /api/system/resource-charts/`

Returns 6 resource chart datasets from `ResourceMetrics` daily snapshots.

**Response:**
```json
{
    "success": true,
    "data": {
        "combined_storage": {
            "labels": ["2026-01-07", ...],
            "bigquery_gb": [5.11, 5.12, ...],
            "sql_gb": [0.01, 0.01, ...],
            "buckets_gb": [146.91, 146.92, ...]
        },
        "bq_jobs": {
            "labels": ["2026-01-24", ...],
            "completed": [5, 8, ...],
            "failed": [0, 1, ...],
            "bytes_billed_gb": [0.5, 0.8, ...]
        },
        "etl_health": {
            "labels": ["2026-01-07", "2026-01-08", ...],
            "completed": [3, 5, ...],
            "failed": [0, 1, ...]
        },
        "cloud_run_requests": {
            "labels": ["2026-01-31", ...],
            "requests": [142, 305, ...]
        },
        "gpu_hours": {
            "labels": ["2026-01-07", ...],
            "hours": [0.5, 1.2, ...],
            "completed": [1, 2, ...],
            "failed": [0, 0, ...]
        },
        "gpu_types": {
            "types": [{"type": "quick_test", "hours": 2.5, "count": 3}, ...],
            "total_hours": 5.0
        }
    }
}
```

### `GET /api/system/charts/`

Returns 4 ML-workflow chart datasets (legacy, still available).

### `GET /api/system/recent-activity/`

Returns last 5 activities merged from multiple sources.

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
        loadCharts,      // Fetch and render 8 resource charts
    };
})();
```

**Chart Render Functions:**
- `renderCombinedStorageChart(data)` - Stacked bar (BigQuery / Cloud SQL / GCS Buckets, 30d)
- `renderBqJobsChart(data)` - Bar + line dual-axis (jobs + bytes billed, 30d)
- `renderEtlHealthChart(data)` - Stacked bar (completed/failed ETL jobs, 30d)
- `renderCloudRunRequestsChart(data)` - Line with fill (Cloud Monitoring data, 30d)
- `renderGpuHoursChart(data)` - Bar (GPU training hours, 30d)
- `renderGpuJobsChart(data)` - Bar (completed/failed training jobs, 30d)

**Key Features:**
- Destroys charts before recreating (prevents memory leaks)
- Graceful fallbacks for missing data ("No data available")
- Color palettes per resource column (blue/green/red)

---

## Context Variables

The view provides these context variables:

| Variable | Type | Description |
|----------|------|-------------|
| `models` | QuerySet | All ModelEndpoint objects |
| `total_models` | int | Count of all models |
| `active_models` | int | Count of models with status='active' |
| `total_registered_models` | int | Count of all RegisteredModel objects |
| `total_trainings` | int | Count of all TrainingRun objects |
| `total_experiments` | int | Count of all QuickTest objects |
| `best_retrieval_recall` | float/None | Best recall@100 from retrieval TrainingRuns |
| `best_ranking_rmse` | float/None | Best (lowest) RMSE from ranking TrainingRuns |
| `best_hybrid_recall` | float/None | Best recall@100 from multitask TrainingRuns |

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

## Metrics Collection

### Management Commands

| Command | Description |
|---------|-------------|
| `collect_resource_metrics` | Collects a single day's GCP resource metrics snapshot (BQ, Cloud Run, DB, GCS, GPU, request counts) |
| `backfill_resource_metrics --days 30` | Backfills historical data with growth curves + real GPU and Cloud Monitoring request data |
| `setup_metrics_scheduler --url https://<app>` | Creates a Cloud Scheduler job for automated daily collection |
| `setup_metrics_scheduler --delete` | Deletes the Cloud Scheduler job |

### Automated Daily Collection

A Cloud Scheduler job triggers `POST /api/system/collect-metrics-webhook/` daily at 02:00 UTC. The webhook runs the same logic as `collect_resource_metrics` and returns a JSON response.

- **Scheduler job name:** `collect-resource-metrics`
- **Schedule:** `0 2 * * *` (daily at 02:00 UTC)
- **Auth:** OIDC token (no Django login required)
- **Setup:** `python manage.py setup_metrics_scheduler --url https://<cloud-run-url>`

### Cloud Monitoring Integration

The `cloud_run_total_requests` and `cloud_run_request_details` fields are populated by querying the `run.googleapis.com/request_count` metric from the Cloud Monitoring API. Only services ending with `-serving` (ML endpoints) are included.

**Metric aggregation:** Uses `ALIGN_DELTA` aligner for the cumulative `request_count` metric to compute net requests per alignment period. The `ALIGN_DELTA` aligner is required because `request_count` is a CUMULATIVE metric kind — `ALIGN_SUM` is incompatible and returns empty results.

**IAM requirement:** The service account running the collection commands needs the `roles/monitoring.viewer` IAM role on the GCP project.

**Dependency:** `google-cloud-monitoring>=2.21.0`

---

## Future Enhancements

- [ ] Dynamic project ID from settings/database
- [ ] Real billing data from subscription service
- [ ] User profile dropdown menu
- [ ] Quick actions in header
- [x] ~~Recent activity feed~~ (Implemented, later replaced by resource charts)
- [x] ~~Resource charts~~ (Implemented - 6 charts in 3-column layout: Data, Cloud Run, Compute & GPU)
- [x] ~~Cloud Run request volume via Cloud Monitoring API~~ (Implemented - queries `run.googleapis.com/request_count` for `-serving` services)
- [x] ~~Scheduled `collect_resource_metrics` via Cloud Scheduler~~ (Implemented - daily at 02:00 UTC via webhook)
