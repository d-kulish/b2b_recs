# Billing Chapter — Design Specification

## Overview

The Billing chapter is the third collapsible section on the Starting Page (`system_dashboard.html`). It provides clients with a transparent view of their platform costs: actual GCP infrastructure charges plus a platform margin, along with the license fee.

**Chapter Icon:** `fa-credit-card` | **Gradient:** Orange (#f59e0b → #fbbf24)

---

## Current Status (2026-02-12)

### Completed

| Step | Status | Details |
|------|--------|---------|
| GCP Billing Export enabled | Done | Standard + Detailed usage cost enabled on billing account `0155F9-5165FE-BBC88A` |
| `billing_export` BigQuery dataset | Done | Created in `b2b-recs`, location `europe-central2` |
| BigQuery Data Transfer Service API | Done | Enabled on `b2b-recs` project |
| Cloud Billing API | Done | Enabled on `b2b-recs` project |
| `BillingConfig` model (singleton) | Done | Migration `0059_billing_models`, seeded with defaults via `get_solo()` |
| `BillingSnapshot` model | Done | Daily per-service records with category, unique on `(date, category, service_name)` |
| Django Admin registration | Done | Singleton enforcement for BillingConfig, list/filter for BillingSnapshot |
| `collect_billing_snapshots` command | Done | Queries resource-level billing export, classifies into categories (Data/Training/Inference/System), applies margins, stores snapshots. Supports `--date`, `--dry-run`, `--backfill --days N` |
| `setup_billing_scheduler` command | Done | Creates Cloud Scheduler job `collect-billing-snapshots` at 05:00 UTC |
| Webhook endpoint | Done | `POST /api/system/collect-billing-webhook/` — collects yesterday's data |
| Option B chosen | Done | Separate command/scheduler, isolated from `collect_resource_metrics` |

### Completed (2026-02-12)

| Step | Status | Details |
|------|--------|---------|
| Billing export data in BigQuery | Done | 10 days loaded (Feb 2–11), 16,288 rows, both `gcp_billing_export_v1_*` and `gcp_billing_export_resource_v1_*` tables |
| Fix query location bug | Done | Removed hardcoded `location='europe-central2'` (dataset is EU multi-region) |
| First dry-run test | Done | 7 services for Feb 11, margins applied correctly (100% default, 50% Vertex AI) |
| Historical backfill | Done | 55 service-day records (Feb 3–11), $15.14 GCP / $28.53 total with margin |
| ETL dataset isolation | Done | `billing_export` blocked in `list_bq_tables()` via `EXCLUDED_DATASETS` set — returns 403 |
| API: `/api/system/billing/summary/` | Done | Current month summary bar data with license info from `BillingConfig` |
| API: `/api/system/billing/charts/` | Done | 5 chart datasets: monthly_trend, cost_breakdown, daily_spend, cost_per_training, category_over_time (charts 1/2/5 use categories) |
| API: `/api/system/billing/invoice/` | Done | Invoice preview rows grouped by category with collapsible service drill-down |
| Frontend (Phase 5) | Done | Summary bar, 3 KPI cards, 5 Chart.js charts, invoice preview table — all powered by billing API |
| Deploy to Cloud Run | Done | Revision `django-app-00112-fbm`, URL `https://django-app-555035914949.europe-central2.run.app` |
| Cloud Scheduler job | Done | `collect-billing-snapshots` at 05:00 UTC, OIDC via `etl-runner@b2b-recs.iam.gserviceaccount.com`, verified with manual trigger |

### Awaiting

All phases complete. No pending items.

### Decisions Made

- **Currency:** USD (billing account currency is immutable). The UI will display USD amounts natively; EUR conversion may be added later as a display-layer concern.
- **Scheduler isolation (Option B):** Separate `collect_billing_snapshots` command with its own scheduler job at 05:00 UTC. Billing failures do not affect resource metrics collection.
- **Scheduler slot:** 05:00 UTC (after metrics 02:00, cleanup 03:00, orphans 04:00).

---

## Pricing Model

The platform uses a single, transparent pricing model — no tiers or plans.

| Component | Description |
|-----------|-------------|
| **License Fee** | $1,900/month (shown with % discount — currently 100%) |
| **GCP Costs** | Actual GCP charges per service, sourced from GCP Billing Export |
| **Platform Margin** | 100% on all GCP services, except GPU (Vertex AI) at 50% |

Clients see the GCP cost and platform fee separately per service line. No resource quantities (GB, hours, requests) are shown — only monetary amounts. This avoids disputes over metrics the client cannot influence.

### Invoice Line Example

Costs are grouped into 4 categories. Each category row is clickable to expand/collapse its service sub-rows.

| Service | GCP Cost | Platform Fee | Total |
|---------|----------|-------------|-------|
| **▼ Data** | **$63.00** | **$63.00** | **$126.00** |
| &nbsp;&nbsp;&nbsp;BigQuery | $12.50 | $12.50 (100%) | $25.00 |
| &nbsp;&nbsp;&nbsp;Cloud SQL | $45.00 | $45.00 (100%) | $90.00 |
| &nbsp;&nbsp;&nbsp;Cloud Dataflow | $2.30 | $2.30 (100%) | $4.60 |
| &nbsp;&nbsp;&nbsp;Cloud Storage | $3.20 | $3.20 (100%) | $6.40 |
| **▶ Training** | **$28.00** | **$14.00** | **$42.00** |
| **▶ Inference** | **$3.50** | **$3.50** | **$7.00** |
| **▶ System** | **$1.60** | **$1.60** | **$3.20** |
| | | | |
| **License** | | $1,900.00 | ~~$1,900.00~~ |
| **Discount** | | -100% | -$1,900.00 |
| **Total** | **$96.10** | **$82.10** | **$178.20** |

### Why This Approach

1. **Transparent** — client sees exactly what GCP charges and what the platform adds
2. **No rate maintenance** — costs come from GCP Billing Export, not hardcoded rates
3. **Fair** — margin is proportional to actual usage, not estimated
4. **Simple** — no plans, no tiers, no quotas, no overage rules
5. **Immutable history** — `BillingSnapshot` records freeze costs at time of capture

### Alternatives Considered

**Option A: Hidden Margin in Unit Rates** — Client sees "GPU Training: 12.5 hrs x $4.80/hr" with margin baked into the rate. Rejected because: showing resource quantities (GB, hours) invites disputes over metrics clients cannot control. Also requires maintaining a rate table.

**Option B: Plan-Based (Pure Subscription)** — Fixed tiers with hard limits. Overages billed separately. Rejected because: too rigid for ML workloads where usage varies wildly month-to-month.

---

## Layout

```
+-----------------------------------------------------------------+
|  BILLING                                                         |
|                                                                  |
|  +- Summary Bar -----------------------------------------------+|
|  |  Period: Feb 1-28  |  Estimated: $178    |  License: -100%   ||
|  |  ============-------  42% of period elapsed                  ||
|  +--------------------------------------------------------------+|
|                                                                  |
|  +- Chart 1 ----------+  +- Chart 2 ----------+  +- Chart 3 ---+|
|  | Monthly Cost Trend  |  | Cost Breakdown     |  | Daily Spend ||
|  | (stacked bar, 6mo)  |  | (donut, current)   |  | (line+fcast)||
|  +---------------------+  +--------------------+  +-------------+|
|                                                                  |
|  +- Chart 4 ----------+  +- Chart 5 ----------+                 |
|  | Cost per Training   |  | Cost by Category   |                 |
|  | (bar, last 10)      |  | (stacked area 30d) |                 |
|  +---------------------+  +--------------------+                 |
|                                                                  |
|  +- Table: Invoice Preview ------------------------------------+|
|  |  Service  |  GCP Cost  |  Platform Fee  |  Total             ||
|  +--------------------------------------------------------------+|
+-----------------------------------------------------------------+
```

**Grid:** Row 1: 3 columns. Row 2: 2 columns (centered or left-aligned). Invoice table spans full width below.

---

## Summary Bar

Slim horizontal bar at the top of the chapter content.

| Element | Content | Styling |
|---------|---------|---------|
| Billing Period | `Feb 1 - Feb 28, 2026` | 14px, #6b7280 |
| Estimated Total | `$178.20` | 24px, font-weight 700, #1f2937 |
| License Status | `License: -100%` or `License: $1,900` | Badge style -- green if discounted, neutral otherwise |
| Progress Bar | % of billing period elapsed | Thin bar, green fill |
| Days Remaining | `17 days left` | 12px, #9ca3af |

---

## Charts

### Chart 1: Monthly Cost Trend

| Property | Value |
|----------|-------|
| **Type** | Stacked bar chart |
| **Period** | Last 6 months |
| **Segments** | 4 cost categories: Data (blue), Training (orange), Inference (green), System (gray) |
| **Y-axis** | USD amount |
| **Data source** | `BillingSnapshot` aggregated monthly by `category` |
| **Purpose** | "Am I spending more or less over time?" |

### Chart 2: Current Month Cost Breakdown

| Property | Value |
|----------|-------|
| **Type** | Donut chart with center total |
| **Period** | Current billing month |
| **Segments** | 4 cost categories (colors match Chart 1) |
| **Center text** | Total estimated cost (large) + "estimated" label (small) |
| **Data source** | `BillingSnapshot` summed for current month by `category` |
| **Purpose** | "Where does my money go?" |

### Chart 3: Daily Spend

| Property | Value |
|----------|-------|
| **Type** | Line chart (solid) + dashed forecast line |
| **Period** | Day 1 of month -> today (solid), today -> end of month (dashed) |
| **Forecast** | Linear projection based on avg daily spend; shown only after day 5 of the month to avoid early-month volatility |
| **Reference line** | Previous month's total as horizontal dotted line |
| **Data source** | Daily `BillingSnapshot` totals |
| **Purpose** | "Am I on track or spiking?" |

### Chart 4: Cost per Training Run

| Property | Value |
|----------|-------|
| **Type** | Bar chart |
| **Period** | Last 10 training runs |
| **Bar color** | By model type: Retrieval (blue), Ranking (green), Multitask (pink) |
| **Label** | Run name or `TR-{id}` |
| **Data source** | `BillingSnapshot` filtered to Vertex AI costs, correlated with `TrainingRun` dates |
| **Purpose** | "Which runs are expensive? Can I optimize?" |

### Chart 5: Cost by Category Over Time

| Property | Value |
|----------|-------|
| **Type** | Stacked area chart |
| **Period** | 30 days |
| **Areas** | 4 cost categories: Data, Training, Inference, System |
| **Data source** | Daily `BillingSnapshot` by `category` |
| **Purpose** | "Is data spending growing? Is training spiking?" |

### Category Color Palette

| Category | Color | Hex |
|----------|-------|-----|
| Data | Blue | #4285f4 |
| Training | Orange | #f59e0b |
| Inference | Green | #34a853 |
| System | Gray | #6b7280 |

---

## Invoice Preview Table

Full-width table below the charts. Shows line items for the current billing period.

### Columns

| Column | Width | Alignment | Description |
|--------|-------|-----------|-------------|
| Service | 30% | Left | GCP service name with icon |
| GCP Cost | 20% | Right | Actual GCP charge for this service |
| Platform Fee | 25% | Right | Margin amount with percentage label (e.g., `$12.50 (100%)`) |
| Total | 25% | Right | GCP Cost + Platform Fee |

### Rows

- **Category rows** (bold, clickable): One row per category (Data, Training, Inference, System) with aggregated totals. Click to expand/collapse service sub-rows.
- **Service sub-rows** (indented, initially hidden): Individual GCP service costs within each category
- Separator row (thin line)
- License row: `License — $1,900.00` with discount shown (e.g., `Discount: -100%`)
- **Estimated Total** row: bold, summing all lines

### Table Footer

- "Billing data from GCP has ~24h delay. Final amounts may adjust." — small text, #9ca3af
- Optional: "Download PDF" link (future)

---

## Data Architecture

### Cost Flow

```
GCP Billing Export (BigQuery) — resource-level table
b2b-recs.billing_export.gcp_billing_export_resource_v1_XXXXXX
│
│  Query: SELECT service.description, resource.name, sku.description, SUM(cost)
│         WHERE project.id = '<client-project>'
│         AND DATE(usage_start_time) = '<date>'
│         GROUP BY service_name, cloud_run_service, is_gpu
│
▼
Category Classification (CATEGORY_MAP + Cloud Run inference detection)
├── Data:      BigQuery, Cloud SQL, Cloud Dataflow, Cloud Storage
├── Training:  Vertex AI (split into GPU / CPU via sku.description)
├── Inference: Cloud Run services matching Deployment.cloud_run_service
└── System:    Cloud Run (other), Cloud Scheduler, Secret Manager, Cloud Build, Artifact Registry, Cloud Logging
│
▼
BillingConfig (Django model, singleton)
├── license_fee = 1900.00
├── license_discount_pct = 100
├── default_margin_pct = 100
└── gpu_margin_pct = 50
│
▼  gcp_cost x (1 + margin_pct/100)
│
BillingSnapshot (Django model, daily per category + service)
├── date
├── category            ("Data", "Training", "Inference", "System")
├── service_name        (e.g., "BigQuery", "Vertex AI — GPU", "Cloud Run — my-endpoint")
├── gcp_cost            (actual GCP charge)
├── margin_pct          (100 or 50, frozen at snapshot time)
├── platform_fee        (gcp_cost x margin_pct / 100)
└── total_cost          (gcp_cost + platform_fee)
```

### GCP Billing Export Setup

GCP Billing Export is enabled at the billing account level and writes cost data for all projects to a BigQuery dataset.

**Billing account:** `0155F9-5165FE-BBC88A` ("My Billing Account"), currency USD.

**Location:** `b2b-recs.billing_export` — a dedicated dataset in the `b2b-recs` project, **EU multi-region** (switched from `europe-central2` on 2026-02-11 for retroactive backfill).

**Setup steps (completed 2026-02-09):**
1. Enabled BigQuery Data Transfer Service API (`bigquerydatatransfer.googleapis.com`)
2. Enabled Cloud Billing API (`cloudbilling.googleapis.com`)
3. Created `billing_export` dataset in project `b2b-recs` via `bq mk`
4. Enabled "Standard usage cost" and "Detailed usage cost" export in GCP Console > Billing > Billing Export
5. Export table `gcp_billing_export_v1_0155F9_5165FE_BBC88A` will auto-appear within ~24h

**Not enabled (not needed):**
- Committed use discounts export — no CUD reservations on this account
- Pricing export — we use actual charges, not list prices

**Data availability:** ~24 hours delay. The daily collection job (05:00 UTC) processes the previous day's costs.

**Data isolation:** The `billing_export` dataset must be invisible to clients:
- The ETL UI dataset browser must filter out `billing_export` (only show `raw_data`)
- Client Django service accounts get `bigquery.dataViewer` on `billing_export` dataset only (not full project-level BQ access)
- No client-facing UI should expose the dataset name or allow arbitrary BQ queries against it

### Models (implemented)

**BillingConfig** — Singleton configuration for the billing model. File: `ml_platform/models.py`.

| Field | Type | Description |
|-------|------|-------------|
| `license_fee` | DecimalField | Monthly license fee ($1,900) |
| `license_discount_pct` | IntegerField | Discount on license (0-100, currently 100) |
| `default_margin_pct` | IntegerField | Margin applied to most GCP services (100) |
| `gpu_margin_pct` | IntegerField | Margin applied to Vertex AI / GPU costs (50) |
| `billing_export_project` | CharField | GCP project hosting the billing export (`b2b-recs`) |
| `billing_export_dataset` | CharField | BigQuery dataset name (`billing_export`) |
| `client_project_id` | CharField | This client's GCP project ID (for filtering billing export) |

Helper methods: `get_solo()` (singleton access), `get_margin_pct(service_name)` (returns 50% for Vertex AI, 100% otherwise).

**BillingSnapshot** — Daily materialized cost records per GCP service, classified by category. File: `ml_platform/models.py`.

| Field | Type | Description |
|-------|------|-------------|
| `date` | DateField | Cost date (from billing export `usage_start_time`) |
| `category` | CharField | Cost category: `Data`, `Training`, `Inference`, `System` (indexed) |
| `service_name` | CharField | GCP service (e.g., `BigQuery`, `Vertex AI — GPU`, `Cloud Run — my-endpoint`) |
| `gcp_cost` | DecimalField | Actual GCP charge for this service on this date (USD) |
| `margin_pct` | IntegerField | Margin percentage applied (frozen at snapshot time) |
| `platform_fee` | DecimalField | `gcp_cost * margin_pct / 100` |
| `total_cost` | DecimalField | `gcp_cost + platform_fee` |

**Unique constraint:** `(date, category, service_name)` — one record per category+service per day.

**Migrations:** `0059_billing_models.py` (initial), `0060_billingsnapshot_category.py` (adds category + backfill).

### API Endpoints (implemented)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/system/billing/summary/` | GET | Summary bar data (period, estimated total, license status, % elapsed) |
| `/api/system/billing/charts/` | GET | All 5 chart datasets |
| `/api/system/billing/invoice/` | GET | Current month invoice preview rows |

**File:** `ml_platform/views.py` — follows the `api_system_resource_charts()` pattern (`@login_required`, `JsonResponse`, `try/except`).
**Routes:** `ml_platform/urls.py` — under the system-level API endpoints section.

---

## Daily Collection Job (implemented)

Billing snapshot collection uses a **separate** management command and scheduler job (Option B), isolated from `collect_resource_metrics`.

### Command: `collect_billing_snapshots`

**File:** `ml_platform/management/commands/collect_billing_snapshots.py`

```bash
# Collect yesterday's billing (default)
python manage.py collect_billing_snapshots

# Collect for a specific date
python manage.py collect_billing_snapshots --date 2026-02-01

# Backfill historical data
python manage.py collect_billing_snapshots --backfill --days 30

# Dry run
python manage.py collect_billing_snapshots --dry-run
```

### Flow

1. Query `b2b-recs.billing_export.gcp_billing_export_resource_v1_*` (resource-level table) for target date's costs, filtered by `project.id`
2. Include GCP credits in cost calculation (`SUM(cost) + SUM(credits.amount)` for net cost)
3. Group by `service.description`, Cloud Run service name (`resource.name`), and GPU flag (`sku.description`)
4. Classify each row into a category:
   - **Data:** BigQuery, Cloud SQL, Cloud Dataflow, Cloud Storage
   - **Training:** Vertex AI (split into "GPU" and "CPU" sub-rows via `sku.description`)
   - **Inference:** Cloud Run services matching `Deployment.cloud_run_service`
   - **System:** Everything else (Cloud Run system services, Cloud Scheduler, Secret Manager, etc.)
5. Apply margin: 50% for Vertex AI, 100% for everything else (from `BillingConfig`)
6. Delete existing snapshots for the target date, then bulk-create new categorized records
7. Uses parameterized queries (`@client_project_id`, `@target_date`) for safety

### Webhook

| Property | Value |
|----------|-------|
| **Endpoint** | `POST /api/system/collect-billing-webhook/` |
| **View** | `scheduler_collect_billing_webhook` in `ml_platform/views.py` |
| **Behavior** | Collects for yesterday (same pattern as metrics webhook, avoids Bug 3 from `start_page_2_schedulers.md`) |
| **Error logging** | Uses `exc_info=True` for full tracebacks (lesson from Bug 1/2) |

### Scheduler Setup

**File:** `ml_platform/management/commands/setup_billing_scheduler.py`

```bash
# Create
python manage.py setup_billing_scheduler --url https://django-app-555035914949.europe-central2.run.app

# Delete
python manage.py setup_billing_scheduler --delete
```

### Daily Scheduler Chain (UTC)

| Time | Job | Purpose |
|------|-----|---------|
| 02:00 | `collect-resource-metrics` | KPIs for System Details chapter |
| 03:00 | `cleanup-gcs-artifacts` | Clean old training artifacts |
| 04:00 | `cleanup-orphan-models` | Remove orphan Vertex AI models |
| **05:00** | **`collect-billing-snapshots`** | **Billing data for Billing chapter** |

---

## Implementation Steps

### Phase 1: GCP Setup
- [x] Enable GCP Billing Export to BigQuery (Standard + Detailed usage cost) — 2026-02-09
- [x] Create `billing_export` dataset in `b2b-recs` project — 2026-02-09
- [x] Recreate `billing_export` dataset in **EU multi-region** (was `europe-central2`) — 2026-02-11. EU multi-region gets retroactive backfill from Jan 1, 2026; regional does not.
- [x] Enable BigQuery Data Transfer Service API — 2026-02-09
- [x] Enable Cloud Billing API — 2026-02-09
- [x] Verify export data appears — 2026-02-12. 10 days loaded (Feb 2–11), 16,288 rows, 2 projects, 17 services
- [ ] Grant cross-project `bigquery.dataViewer` on `billing_export` to client service accounts

### Phase 2: Data Layer
- [x] Create `BillingConfig` model (singleton) — 2026-02-09
- [x] Create `BillingSnapshot` model — 2026-02-09
- [x] Run migration (`0059_billing_models`) — 2026-02-09
- [x] Create management command `collect_billing_snapshots` — 2026-02-09
- [x] Backfill support (`--backfill --days N`) — 2026-02-09
- [x] Fix query location bug (`europe-central2` → auto-detect for EU multi-region dataset) — 2026-02-12
- [x] Dry-run test with real billing data — 2026-02-12. 7 services for Feb 11 with correct margins (100% default, 50% Vertex AI)
- [x] Backfill historical data — 2026-02-12. 55 service-day records (Feb 3–11), $15.14 GCP / $28.53 total

### Phase 3: ETL Isolation
- [x] Block `billing_export` in ETL dataset browser — 2026-02-12. `EXCLUDED_DATASETS` blocklist in `list_bq_tables()` returns 403
- [x] Verify `billing_export` is not visible in any client-facing UI — 2026-02-12. Configs page hardcodes `raw_data`; ETL API now blocks `billing_export`

### Phase 4: API
- [x] `/api/system/billing/summary/` endpoint — 2026-02-12. Period info, cost totals, license info
- [x] `/api/system/billing/charts/` endpoint — 2026-02-12. 5 chart datasets (monthly_trend, cost_breakdown, daily_spend, cost_per_training, service_over_time)
- [x] `/api/system/billing/invoice/` endpoint — 2026-02-12. Per-service rows with margin, license, grand total

### Phase 5: Frontend
- [x] Summary bar (period, estimated total, license status, progress) — 2026-02-12
- [x] Chart 1: Monthly Cost Trend (stacked bar, 6mo) — 2026-02-12
- [x] Chart 2: Cost Breakdown (donut, current month) — 2026-02-12
- [x] Chart 3: Daily Spend (line + forecast) — 2026-02-12
- [x] Chart 4: Cost per Training Run (bar, last 10 runs) — 2026-02-12
- [x] Chart 5: Cost by Service Over Time (stacked area, 30d) — 2026-02-12
- [x] Invoice Preview Table (full width) — 2026-02-12

### Phase 6: Scheduler Integration
- [x] Create `setup_billing_scheduler` management command — 2026-02-09
- [x] Create webhook `POST /api/system/collect-billing-webhook/` — 2026-02-09
- [x] Deploy to Cloud Run — 2026-02-12. Revision `django-app-00112-fbm`
- [x] Create Cloud Scheduler job — 2026-02-12. Created via `gcloud scheduler jobs create http`, verified with manual trigger (status `{}`)

---

## Implementation Notes

- Charts use **Chart.js 4.4.0** (already loaded on the page)
- Layout follows the same grid pattern as System Details resource charts
- Currency: **USD** throughout ($ symbol) — billing account currency is immutable
- Category color palette (Data=blue, Training=orange, Inference=green, System=gray) consistent across all charts and the invoice table
- Summary bar sits between chapter header and chart grid
- Invoice table uses existing `.info-card` styling with a custom table inside
- `BillingSnapshot` populated daily; API responses can be cached aggressively (billing data for past days is immutable)
- GCP Billing Export has ~24h delay — the dashboard always shows "estimated" for the current period
- BigQuery query includes GCP credits (`UNNEST(credits)`) for accurate net cost calculation
