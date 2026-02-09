# Billing Chapter — Design Specification

## Overview

The Billing chapter is the third collapsible section on the Starting Page (`system_dashboard.html`). It provides clients with a transparent view of their platform costs: actual GCP infrastructure charges plus a platform margin, along with the license fee.

**Chapter Icon:** `fa-credit-card` | **Gradient:** Orange (#f59e0b → #fbbf24)

---

## Current Status (2026-02-09)

### Completed

| Step | Status | Details |
|------|--------|---------|
| GCP Billing Export enabled | Done | Standard + Detailed usage cost enabled on billing account `0155F9-5165FE-BBC88A` |
| `billing_export` BigQuery dataset | Done | Created in `b2b-recs`, location `europe-central2` |
| BigQuery Data Transfer Service API | Done | Enabled on `b2b-recs` project |
| Cloud Billing API | Done | Enabled on `b2b-recs` project |
| `BillingConfig` model (singleton) | Done | Migration `0059_billing_models`, seeded with defaults via `get_solo()` |
| `BillingSnapshot` model | Done | Daily per-service records, unique on `(date, service_name)` |
| Django Admin registration | Done | Singleton enforcement for BillingConfig, list/filter for BillingSnapshot |
| `collect_billing_snapshots` command | Done | Queries billing export, applies margins, upserts snapshots. Supports `--date`, `--dry-run`, `--backfill --days N` |
| `setup_billing_scheduler` command | Done | Creates Cloud Scheduler job `collect-billing-snapshots` at 05:00 UTC |
| Webhook endpoint | Done | `POST /api/system/collect-billing-webhook/` — collects yesterday's data |
| Option B chosen | Done | Separate command/scheduler, isolated from `collect_resource_metrics` |

### Awaiting

| Step | Status | Details |
|------|--------|---------|
| Billing export data in BigQuery | Waiting ~24h | Table `gcp_billing_export_v1_0155F9_5165FE_BBC88A` will auto-appear |
| First dry-run test | Blocked by above | `python manage.py collect_billing_snapshots --dry-run` |
| Historical backfill | Blocked by above | `python manage.py collect_billing_snapshots --backfill --days 30` |
| Deploy to Cloud Run | Not started | Required before creating the scheduler job |
| Create Cloud Scheduler job | Blocked by deploy | `python manage.py setup_billing_scheduler --url https://django-app-...` |
| ETL dataset isolation | Not started | Filter `billing_export` from ETL dataset browser |
| API endpoints (3) | Not started | `/api/system/billing/summary/`, `/charts/`, `/invoice/` |
| Frontend (summary bar, 5 charts, invoice table) | Not started | Replace hardcoded Chapter 3 placeholder |

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

| Service | GCP Cost | Platform Fee | Total |
|---------|----------|-------------|-------|
| BigQuery | $12.50 | $12.50 (100%) | $25.00 |
| Cloud Storage | $3.20 | $3.20 (100%) | $6.40 |
| Cloud SQL | $45.00 | $45.00 (100%) | $90.00 |
| Vertex AI (GPU) | $28.00 | $14.00 (50%) | $42.00 |
| Cloud Run | $5.10 | $5.10 (100%) | $10.20 |
| Dataflow | $2.30 | $2.30 (100%) | $4.60 |
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
|  | Cost per Training   |  | Cost by Service    |                 |
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
| **Segments** | GCP services: BigQuery, Cloud Storage, Cloud SQL, Vertex AI, Cloud Run, Dataflow |
| **Y-axis** | USD amount |
| **Data source** | `BillingSnapshot` aggregated monthly |
| **Purpose** | "Am I spending more or less over time?" |

### Chart 2: Current Month Cost Breakdown

| Property | Value |
|----------|-------|
| **Type** | Donut chart with center total |
| **Period** | Current billing month |
| **Segments** | Same GCP services (colors match Chart 1) |
| **Center text** | Total estimated cost (large) + "estimated" label (small) |
| **Data source** | `BillingSnapshot` summed for current month |
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

### Chart 5: Cost by Service Over Time

| Property | Value |
|----------|-------|
| **Type** | Stacked area chart |
| **Period** | 30 days |
| **Areas** | GCP services (BigQuery, Cloud Storage, Cloud SQL, Vertex AI, Cloud Run, Dataflow) |
| **Data source** | Daily `BillingSnapshot` by service |
| **Purpose** | "Is storage growing? Is compute spiking?" |

### Service Color Palette

| Service | Color | Hex |
|---------|-------|-----|
| BigQuery | Blue | #4285f4 |
| Cloud Storage | Teal | #00bcd4 |
| Cloud SQL | Indigo | #5c6bc0 |
| Vertex AI | Orange | #f59e0b |
| Cloud Run | Green | #34a853 |
| Dataflow | Purple | #9c27b0 |

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

- One row per GCP service with non-zero cost in the current period
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
GCP Billing Export (BigQuery)
b2b-recs.billing_export.gcp_billing_export_v1_XXXXXX
│
│  Query: SELECT service.description, SUM(cost)
│         WHERE project.id = '<client-project>'
│         AND DATE(usage_start_time) = '<date>'
│         GROUP BY service.description
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
BillingSnapshot (Django model, daily per service)
├── date
├── service_name        (e.g., "BigQuery", "Vertex AI")
├── gcp_cost            (actual GCP charge)
├── margin_pct          (100 or 50, frozen at snapshot time)
├── platform_fee        (gcp_cost x margin_pct / 100)
└── total_cost          (gcp_cost + platform_fee)
```

### GCP Billing Export Setup

GCP Billing Export is enabled at the billing account level and writes cost data for all projects to a BigQuery dataset.

**Billing account:** `0155F9-5165FE-BBC88A` ("My Billing Account"), currency USD.

**Location:** `b2b-recs.billing_export` — a dedicated dataset in the `b2b-recs` project, `europe-central2`.

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

**BillingSnapshot** — Daily materialized cost records per GCP service. File: `ml_platform/models.py`.

| Field | Type | Description |
|-------|------|-------------|
| `date` | DateField | Cost date (from billing export `usage_start_time`) |
| `service_name` | CharField | GCP service (e.g., `BigQuery`, `Vertex AI`, `Cloud Run`) |
| `gcp_cost` | DecimalField | Actual GCP charge for this service on this date (USD) |
| `margin_pct` | IntegerField | Margin percentage applied (frozen at snapshot time) |
| `platform_fee` | DecimalField | `gcp_cost * margin_pct / 100` |
| `total_cost` | DecimalField | `gcp_cost + platform_fee` |

**Unique constraint:** `(date, service_name)` — one record per service per day.

**Migration:** `ml_platform/migrations/0059_billing_models.py` (applied).

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/system/billing/summary/` | GET | Summary bar data (period, estimated total, license status, % elapsed) |
| `/api/system/billing/charts/` | GET | All 5 chart datasets |
| `/api/system/billing/invoice/` | GET | Current month invoice preview rows |

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

1. Query `b2b-recs.billing_export.gcp_billing_export_v1_*` for target date's costs, filtered by `project.id`
2. Include GCP credits in cost calculation (`SUM(cost) + SUM(credits.amount)` for net cost)
3. For each GCP service with non-zero net cost:
   - Look up margin: 50% for `Vertex AI`, 100% for everything else (from `BillingConfig`)
   - Calculate `platform_fee = gcp_cost * margin_pct / 100`
   - Upsert `BillingSnapshot` record
4. Uses parameterized queries (`@client_project_id`, `@target_date`) for safety

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
- [x] Enable BigQuery Data Transfer Service API — 2026-02-09
- [x] Enable Cloud Billing API — 2026-02-09
- [ ] Verify export data appears (~24h after enabling)
- [ ] Grant cross-project `bigquery.dataViewer` on `billing_export` to client service accounts

### Phase 2: Data Layer
- [x] Create `BillingConfig` model (singleton) — 2026-02-09
- [x] Create `BillingSnapshot` model — 2026-02-09
- [x] Run migration (`0059_billing_models`) — 2026-02-09
- [x] Create management command `collect_billing_snapshots` — 2026-02-09
- [x] Backfill support (`--backfill --days N`) — 2026-02-09
- [ ] Test with real billing export data (after ~24h)
- [ ] Run backfill for available historical data

### Phase 3: ETL Isolation
- [ ] Update ETL dataset browser to filter out `billing_export` dataset
- [ ] Verify `billing_export` is not visible in any client-facing UI

### Phase 4: API
- [ ] `/api/system/billing/summary/` endpoint
- [ ] `/api/system/billing/charts/` endpoint
- [ ] `/api/system/billing/invoice/` endpoint

### Phase 5: Frontend
- [ ] Summary bar (period, estimated total, license status, progress)
- [ ] Chart 1: Monthly Cost Trend (stacked bar, 6mo)
- [ ] Chart 2: Cost Breakdown (donut, current month)
- [ ] Chart 3: Daily Spend (line + forecast)
- [ ] Chart 4: Cost per Training Run (bar, last 10 runs)
- [ ] Chart 5: Cost by Service Over Time (stacked area, 30d)
- [ ] Invoice Preview Table (full width)

### Phase 6: Scheduler Integration
- [x] Create `setup_billing_scheduler` management command — 2026-02-09
- [x] Create webhook `POST /api/system/collect-billing-webhook/` — 2026-02-09
- [ ] Deploy to Cloud Run
- [ ] Create Cloud Scheduler job via `setup_billing_scheduler --url`

---

## Implementation Notes

- Charts use **Chart.js 4.4.0** (already loaded on the page)
- Layout follows the same grid pattern as System Details resource charts
- Currency: **USD** throughout ($ symbol) — billing account currency is immutable
- Service color palette consistent across all charts and the invoice table
- Summary bar sits between chapter header and chart grid
- Invoice table uses existing `.info-card` styling with a custom table inside
- `BillingSnapshot` populated daily; API responses can be cached aggressively (billing data for past days is immutable)
- GCP Billing Export has ~24h delay — the dashboard always shows "estimated" for the current period
- BigQuery query includes GCP credits (`UNNEST(credits)`) for accurate net cost calculation
