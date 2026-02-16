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

### Header Row

The chapter header contains the title on the left and a "+ New Project" button next to the collapse arrow on the right. The button uses the shared `btn btn-primary` classes from `static/css/buttons.css` (white background, black border, outlined style) and `event.stopPropagation()` to avoid triggering the chapter toggle.

### KPI Containers (4:3 grid)

Two `system-kpi-card` containers in a `4fr 3fr` grid layout, spanning the full chapter width. The `chapter-kpi-equal` CSS class ensures each card's stat tablets fill the available space (4-column grid for Assets, 3-column grid for Accuracy).

**Assets Card (Blue icon, `fa-folder-open`):**

| KPI | Context Variable | Data Source |
|-----|-----------------|-------------|
| Projects | `total_models` | `ModelEndpoint.objects.count()` |
| Models | `total_registered_models` | `RegisteredModel.objects.count()` |
| Trainings | `total_trainings` | `TrainingRun.objects.count()` |
| Experiments | `total_experiments` | `QuickTest.objects.count()` |

**Accuracy Card (Green icon, `fa-bullseye`):**

| KPI | Context Variable | Data Source | Format |
|-----|-----------------|-------------|--------|
| Retrieval | `best_retrieval_recall` | Best `recall_at_100` from retrieval TrainingRuns (×100) | `31.9%` or `--` |
| Ranking | `best_ranking_rmse` | Best (lowest) `rmse` from ranking TrainingRuns | `0.48` or `--` |
| Hybrid | `best_hybrid_recall` | Best `recall_at_100` from multitask TrainingRuns (×100) | `23.5%` or `--` |

### Project Card Structure

Each project card mirrors the model page header layout from `base_model.html` (without the logo and navigation bar). The card is a `bg-white border border-black rounded-xl px-6 py-3 shadow-lg` container with a single flex row:

**Left section (30% width):**
- Project name (`text-5xl font-bold`, color-coded: green if endpoint active, red if failed, blue otherwise)
- Description (truncated to 15 words, or italic "No description" placeholder)

**Center section (4 KPI cards):**

Uses the shared `.header-kpi-card` classes from `model_dashboard.css` — identical styling to the model page header.

| KPI | Icon Class | Icon | Data Source | Subtitle |
|-----|-----------|------|-------------|----------|
| Endpoints Active | `header-kpi-icon endpoints` | `fa-rocket` | `DeployedEndpoint` per project (real) | "of X total" |
| Total Models | `header-kpi-icon models` | `fa-cube` | `RegisteredModel` per project (real) | "X deployed" |
| Requests (7D) | `header-kpi-icon requests` | `fa-chart-bar` | Placeholder (`--`) | -- |
| Latency (P95) | `header-kpi-icon latency` | `fa-clock` | Placeholder (`--`) | -- |

**Right section:**
- Arrow icon (`fa-arrow-right`, blue) — the only clickable element, links to `{% url 'model_dashboard' model.id %}`
- Styled as a 44x44 circle with `hover:bg-blue-50` transition

**Per-project KPI data** is computed server-side in the `system_dashboard` view by iterating the `ModelEndpoint` queryset and attaching:
- `kpi_endpoints_active` / `kpi_endpoints_total` — from `DeployedEndpoint` objects (via `RegisteredModel`)
- `kpi_models_total` / `kpi_models_deployed` — from `RegisteredModel` objects

### Empty State

When no models exist, displays:
- Large cube icon
- "No models created yet" text
- "Create Your First Model" button

---

## Chapter 3: Billing

The Billing chapter provides clients with a clear view of their platform costs, along with the license fee. All amounts are displayed in EUR (converted from USD at a configurable exchange rate).

**Chapter Icon:** `fa-credit-card` | **Gradient:** Orange (#f59e0b → #fbbf24)

### Decisions

- **Currency:** GCP billing account uses USD (immutable). All UI amounts are converted to EUR at display time using a configurable rate stored in `BillingConfig.usd_to_display_rate` (default 0.92). The `display_currency` field (default "EUR") and rate can be adjusted in Django Admin.
- **Scheduler isolation (Option B):** Separate `collect_billing_snapshots` command with its own scheduler job at 05:00 UTC. Billing failures do not affect resource metrics collection.

### Pricing Model

The platform uses a single, simple pricing model — no tiers or plans.

| Component | Description |
|-----------|-------------|
| **License Fee** | €1,900/month (shown with % discount — currently 100%) |
| **Usage Costs** | Per-service costs grouped by category, displayed as a single total per service |

Clients see one total amount per service line. No resource quantities (GB, hours, requests) are shown — only monetary amounts. Internal cost structure (GCP charges, margins) is not exposed in the client-facing UI. The `BillingSnapshot` model retains full cost breakdown (gcp_cost, margin_pct, platform_fee) for internal use and Django Admin.

### Layout

```
+- Summary Bar -----------------------------------------------+
|  Period: Feb 1-28  |  Estimated: €164    |  License: -100%   |
|  ============-------  42% of period elapsed                  |
+--------------------------------------------------------------+

+- Chart 1 ----------+  +- Chart 2 ----------+  +- Chart 3 ---+
| Daily Spend         |  | Cost Breakdown     |  | Invoice     |
| (stacked bar, daily)|  | (donut, current)   |  | Preview     |
+---------------------+  +--------------------+  | (table,     |
+- Chart 4 ----------+  +- Chart 5 ----------+  | spanning)   |
| Monthly Cost Trend  |  | Cost per Training  |  |             |
| (stacked bar, 6mo)  |  | (bar, last 10)     |  +-------------+
+---------------------+  +--------------------+
```

**Grid:** 3 columns x 2 rows. Invoice table spans col 3, rows 1-2.

### Summary Bar

| Element | Content | Styling |
|---------|---------|---------|
| Billing Period | `Feb 1 - Feb 28, 2026` | 14px, #6b7280 |
| Estimated Total | `€163.94` | 24px, font-weight 700, #1f2937 |
| License Status | `License: -100%` or `License: €1,900` | Badge style — green if discounted |
| Progress Bar | % of billing period elapsed | Thin bar, green fill |
| Budget Bar | Spent / Budget (€920) | Green/orange/red based on pace |

### Charts

**Chart 1: Daily Spend** — Stacked bar, current month by category (Data/Training/Inference/System). Y-axis: EUR.

**Chart 2: Cost Breakdown** — Donut with center total (EUR). Current month per-category totals.

**Chart 3: Monthly Cost Trend** — Stacked bar, last 6 months by category. Y-axis: EUR.

**Chart 4: Cost per Training** — Bar, last 10 runs. Color by model type (retrieval=blue, ranking=green, multitask=pink). Y-axis: EUR.

**Category Colors:** Data=#4285f4 (blue), Training=#f59e0b (orange), Inference=#34a853 (green), System=#6b7280 (gray).

### Invoice Preview Table

4-column table spanning col 3 of the chart grid.

| Column | Width | Description |
|--------|-------|-------------|
| Service | 30% | Service name or category |
| Costs | 25% | Cost in EUR (before discounts) |
| Discount | 20% | Discount % (only License and VAT rows) |
| Total | 25% | Final amount in EUR |

**Row structure:**
- **License row** (bold): Costs=€1,900.00, Discount=-100%, Total=€0.00
- **Category rows** (bold, clickable): Expand/collapse service sub-rows
- **Service sub-rows** (indented, hidden by default): Individual GCP service costs
- Separator, **Subtotal**, **Grand Total**, **VAT** (20%), **Total Due**

### Invoice Line Example

| Service | Costs | Discount | Total |
|---------|-------|----------|-------|
| **License** | **€1,900.00** | **-100%** | **€0.00** |
| **▼ Data** | **€115.92** | | **€115.92** |
| &nbsp;&nbsp;&nbsp;Cloud SQL | €82.80 | | €82.80 |
| &nbsp;&nbsp;&nbsp;BigQuery | €23.00 | | €23.00 |
| **▶ Training** | **€38.64** | | **€38.64** |
| **▶ System** | **€2.94** | | **€2.94** |
| | | | |
| **Subtotal** | | | **€157.50** |
| **Grand Total** | | | **€157.50** |
| VAT | | 20% | €31.50 |
| **Total Due** | | | **€189.00** |

### Data Architecture

```
GCP Billing Export (BigQuery) — resource-level table
│  Query by project.id + date, GROUP BY service, Cloud Run name, GPU flag
▼
Category Classification (CATEGORY_MAP + Cloud Run inference detection)
├── Data:      BigQuery, Cloud SQL, Cloud Dataflow, Cloud Storage
├── Training:  Vertex AI (GPU / CPU via sku.description)
├── Inference: Cloud Run services matching Deployment.cloud_run_service
└── System:    Cloud Run (other), Cloud Scheduler, Secret Manager, etc.
▼
BillingConfig (singleton) → margin_pct per service
▼  gcp_cost × (1 + margin_pct/100)
BillingSnapshot (daily per category + service)
▼  API layer: total_cost × usd_to_display_rate → EUR
Client UI: Service | Costs | Discount | Total
```

### Models

**BillingConfig** — Singleton. File: `ml_platform/models.py`.

| Field | Type | Description |
|-------|------|-------------|
| `license_fee` | DecimalField | Monthly license fee (1900.00 EUR — already in display currency) |
| `license_discount_pct` | IntegerField | Discount on license (0-100, currently 100) |
| `default_margin_pct` | IntegerField | Margin applied to most GCP services (100) |
| `gpu_margin_pct` | IntegerField | Margin applied to Vertex AI / GPU costs (100) |
| `billing_export_project` | CharField | GCP project hosting billing export (`b2b-recs`) |
| `billing_export_dataset` | CharField | BigQuery dataset name (`billing_export`) |
| `client_project_id` | CharField | Client's GCP project ID for filtering |
| `display_currency` | CharField | Currency code for UI display (default "EUR") |
| `usd_to_display_rate` | DecimalField | Exchange rate: 1 USD = X display currency (default 0.92) |

**BillingSnapshot** — Daily per category+service. File: `ml_platform/models.py`.

| Field | Type | Description |
|-------|------|-------------|
| `date` | DateField | Cost date |
| `category` | CharField | `Data`, `Training`, `Inference`, `System` |
| `service_name` | CharField | GCP service name |
| `gcp_cost` | DecimalField | Actual GCP charge (USD, internal only) |
| `margin_pct` | IntegerField | Margin % (frozen at snapshot time, internal only) |
| `platform_fee` | DecimalField | `gcp_cost * margin_pct / 100` (internal only) |
| `total_cost` | DecimalField | `gcp_cost + platform_fee` (converted to EUR at display) |

**Unique constraint:** `(date, category, service_name)`. **Migrations:** `0059`, `0060`, `0064`.

### GCP Billing Export Setup

- **Billing account:** `0155F9-5165FE-BBC88A`, currency USD
- **Dataset:** `b2b-recs.billing_export`, EU multi-region
- **Tables:** `gcp_billing_export_resource_v1_*` (resource-level)
- **Data availability:** ~24h delay. Collection at 05:00 UTC processes previous day
- **Isolation:** `billing_export` blocked in ETL dataset browser via `EXCLUDED_DATASETS`

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
        "requests_30d": 42,
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

### `POST /api/system/setup-metrics-scheduler/`

Creates or updates the Cloud Scheduler job for daily metrics collection. Must be called from within the deployed Cloud Run app (the service account has the required IAM roles). Protected by Cloud Run IAM (requires valid identity token). Follows the same pattern as ETL scheduler creation.

**Response:**
```json
{
    "status": "success",
    "action": "created",
    "job_name": "projects/b2b-recs/locations/europe-central2/jobs/collect-resource-metrics",
    "schedule": "0 2 * * *",
    "webhook_url": "https://django-app-555035914949.europe-central2.run.app/api/system/collect-metrics-webhook/"
}
```

### `GET /api/system/charts/`

Returns 4 ML-workflow chart datasets (legacy, still available).

### `GET /api/system/recent-activity/`

Returns last 5 activities merged from multiple sources.

### `GET /api/system/billing/summary/`

Summary bar data: period, estimated total in EUR, license status, % elapsed, currency.

### `GET /api/system/billing/charts/`

All chart datasets (values converted to EUR). Includes `currency` field.

### `GET /api/system/billing/invoice/`

Current month invoice preview — Service + Costs + Discount + Total (EUR). No internal GCP cost/platform fee breakdown.

### `POST /api/system/collect-billing-webhook/`

Cloud Scheduler trigger for daily billing collection. Collects for yesterday.

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

### BillingDashboard Module

IIFE module that manages billing data loading:

- `loadSummary()` — Fetches `/api/system/billing/summary/`, populates KPI cards and progress bars
- `loadCharts()` — Fetches `/api/system/billing/charts/`, renders 4 Chart.js charts
- `loadInvoice()` — Fetches `/api/system/billing/invoice/`, renders invoice table with collapsible categories
- `formatEUR(val)` — Formats number as `€X.XXX,XX` (de-DE locale)

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
| `best_retrieval_recall` | float/None | Best recall@100 from retrieval TrainingRuns (×100 for percentage) |
| `best_ranking_rmse` | float/None | Best (lowest) RMSE from ranking TrainingRuns |
| `best_hybrid_recall` | float/None | Best recall@100 from multitask TrainingRuns (×100 for percentage) |

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
| `cleanup_gcs_artifacts` | Selectively deletes old training artifacts from GCS, preserving registered models |
| `cleanup_gcs_artifacts --dry-run` | Preview what would be deleted without making changes |
| `cleanup_gcs_artifacts --days 14` | Delete artifacts older than 14 days (default: 7) |
| `cleanup_gcs_artifacts --include-registered` | Also delete artifacts for registered models (opt-in) |
| `setup_cleanup_scheduler --url https://<app>` | Creates a Cloud Scheduler job for automated daily cleanup |
| `setup_cleanup_scheduler --delete` | Deletes the cleanup scheduler job |
| `collect_billing_snapshots` | Collects yesterday's billing data from GCP Billing Export, classifies by category, applies margins |
| `collect_billing_snapshots --date 2026-02-01` | Collect for a specific date |
| `collect_billing_snapshots --backfill --days 30` | Backfill historical billing data |
| `collect_billing_snapshots --dry-run` | Preview billing collection without saving |
| `setup_billing_scheduler --url https://<app>` | Creates Cloud Scheduler job for daily billing collection at 05:00 UTC |
| `setup_billing_scheduler --delete` | Deletes the billing scheduler job |

### Automated Daily Collection (UTC)

| Time | Job | Webhook | Purpose |
|------|-----|---------|---------|
| 02:00 | `collect-resource-metrics` | `POST /api/system/collect-metrics-webhook/` | KPIs for System Details chapter |
| 03:00 | `cleanup-gcs-artifacts` | `POST /api/system/cleanup-artifacts-webhook/` | Clean old training artifacts |
| 04:00 | `cleanup-orphan-models` | — | Remove orphan Vertex AI models |
| 05:00 | `collect-billing-snapshots` | `POST /api/system/collect-billing-webhook/` | Billing data for Billing chapter |

All jobs use OIDC auth via `etl-runner@b2b-recs.iam.gserviceaccount.com`, located in `europe-central2`.

### GCS Bucket Lifecycle Policies

| Bucket | Lifecycle | Purpose |
|--------|-----------|---------|
| `b2b-recs-quicktest-artifacts` | 7-day auto-delete | Experiment artifacts (short-lived) |
| `b2b-recs-training-artifacts` | No lifecycle (managed by `cleanup_gcs_artifacts`) | Training artifacts — registered models preserved indefinitely |
| `b2b-recs-pipeline-staging` | 7-day auto-delete | TFX intermediate artifacts (TFRecords, Transform, Statistics) |
| `b2b-recs-dataflow` | 3-day auto-delete | ETL temp files |

### Error Tracking

Each sub-collector (BigQuery, Cloud Run, Database, GCS, ETL, Cloud Run Requests, GPU) runs independently. If any collector fails, the error is recorded in the `collection_errors` JSONField on the `ResourceMetrics` record. The webhook response includes:

- `"status": "success"` — all 7 collectors succeeded
- `"status": "partial"` — some collectors failed (errors in `collection_errors` array)
- `"status": "error"` — entire collection failed

**Date handling:** All date calculations use `timezone.now().date()` (Django UTC-aware) instead of `date.today()` (timezone-naive) to prevent date mismatches when Cloud Run containers run at UTC boundaries.

### Cloud Monitoring Integration

The `cloud_run_total_requests` and `cloud_run_request_details` fields are populated by querying the `run.googleapis.com/request_count` metric from the Cloud Monitoring API. Only services ending with `-serving` (ML endpoints) are included.

**Metric aggregation:** Uses `ALIGN_DELTA` aligner for the cumulative `request_count` metric to compute net requests per alignment period. The `ALIGN_DELTA` aligner is required because `request_count` is a CUMULATIVE metric kind — `ALIGN_SUM` is incompatible and returns empty results.

**IAM requirement:** The service account running the collection commands needs the `roles/monitoring.viewer` IAM role on the GCP project.

**Dependency:** `google-cloud-monitoring>=2.21.0`

---

## Future Enhancements

- [ ] Dynamic project ID from settings/database
- [ ] User profile dropdown menu
- [ ] Quick actions in header
- [x] ~~Billing chapter with real GCP data~~ (Implemented — BillingSnapshot from GCP Billing Export, EUR display, 4 charts, invoice table)
- [x] ~~Recent activity feed~~ (Implemented, later replaced by resource charts)
- [x] ~~Resource charts~~ (Implemented - 6 charts in 3-column layout: Data, Cloud Run, Compute & GPU)
- [x] ~~Cloud Run request volume via Cloud Monitoring API~~ (Implemented - queries `run.googleapis.com/request_count` for `-serving` services)
- [x] ~~Scheduled `collect_resource_metrics` via Cloud Scheduler~~ (Implemented - daily at 02:00 UTC via webhook)
- [x] ~~Requests KPI wired to real data~~ (Implemented - `requests_30d` now sums `ResourceMetrics.cloud_run_total_requests` over 30 days via `api_system_kpis`)
