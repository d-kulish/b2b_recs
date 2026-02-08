# Billing Chapter — Design Specification

## Overview

The Billing chapter is the third collapsible section on the Starting Page (`system_dashboard.html`). It provides clients with a clear view of their platform usage, costs, and subscription status — without exposing raw GCP infrastructure costs.

**Chapter Icon:** `fa-credit-card` | **Gradient:** Orange (#f59e0b → #fbbf24)

---

## Design Approach: Usage Dashboard

Costs are abstracted into **4 billable categories** with unit pricing that includes the platform margin. The client sees usage quantities and rates — not the underlying GCP service costs. This is standard SaaS practice (AWS, Vercel, Datadog all follow this pattern).

### Why This Approach

1. **Margin is hidden in unit rates** — no awkward "service fee" line item
2. **Uses data already collected** — `ResourceMetrics` daily snapshots provide all usage metrics
3. **No GCP billing export required** — costs derived from usage metrics x pricing config
4. **Business-user friendly** — clients see "GPU Training: 12.5 hrs x $4.80/hr" not "Vertex AI n1-standard-16 with NVIDIA_TESLA_T4"
5. **Rate flexibility** — change pricing without recalculating history (snapshots store the rate at time of capture)

### 4 Billable Categories

| Category | Color | What It Covers | Key Metric |
|----------|-------|----------------|------------|
| **Compute** | Orange | GPU training hours, experiment runs | `gpu_training_hours`, QuickTest count |
| **Storage** | Blue | BigQuery + GCS + Cloud SQL combined | `bq_total_bytes` + `gcs_total_bytes` + `db_size_bytes` |
| **Data Processing** | Purple | ETL runs, BigQuery analysis queries | `etl_jobs_completed`, `bq_bytes_billed` |
| **Serving** | Green | API requests to deployed endpoints | `cloud_run_total_requests` |

---

## Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  BILLING                                                             │
│                                                                      │
│  ┌─ Summary Bar ──────────────────────────────────────────────────┐  │
│  │  Current Period: Feb 1-28  │  Estimated: $347  │  Plan: Pro    │  │
│  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░  42% of period elapsed             │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─ Chart 1 ─────────┐  ┌─ Chart 2 ─────────┐  ┌─ Chart 3 ──────┐ │
│  │ Monthly Cost Trend │  │ Cost Breakdown     │  │ Daily Spend    │ │
│  │ (stacked bar, 6mo) │  │ (donut, current)   │  │ (line+forecast)│ │
│  └────────────────────┘  └────────────────────┘  └────────────────┘ │
│                                                                      │
│  ┌─ Chart 4 ─────────┐  ┌─ Chart 5 ─────────┐  ┌─ Chart 6 ──────┐ │
│  │ Usage vs Limits    │  │ Cost per Training  │  │ Cost by        │ │
│  │ (horizontal bars)  │  │ (bar, last 10)     │  │ Category (30d) │ │
│  └────────────────────┘  └────────────────────┘  └────────────────┘ │
│                                                                      │
│  ┌─ Table: Invoice Preview ───────────────────────────────────────┐ │
│  │  Category  │  Usage  │  Rate  │  Subtotal                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

**Grid:** 3 columns x 2 rows for charts (matches System Details layout). Invoice table spans full width below.

---

## Summary Bar

Slim horizontal bar at the top of the chapter content. Quick-glance anchor before scrolling into detail.

| Element | Content | Styling |
|---------|---------|---------|
| Billing Period | `Feb 1 - Feb 28, 2026` | 14px, #6b7280 |
| Estimated Total | `$347.19` | 24px, font-weight 700, #1f2937 |
| Plan Badge | `Pro` with crown icon | Gradient badge (existing `.plan-badge` style) |
| Progress Bar | % of billing period elapsed | Thin bar, green fill |
| Days Remaining | `17 days left` | 12px, #9ca3af |

---

## Charts

### Chart 1: Monthly Cost Trend

| Property | Value |
|----------|-------|
| **Type** | Stacked bar chart (4 segments) |
| **Period** | Last 6 months |
| **Segments** | Compute (orange), Storage (blue), Processing (purple), Serving (green) |
| **Y-axis** | Dollar amount |
| **Data source** | `BillingSnapshot` aggregated monthly |
| **Purpose** | "Am I spending more or less over time?" |

### Chart 2: Current Month Cost Breakdown

| Property | Value |
|----------|-------|
| **Type** | Donut chart with center total |
| **Period** | Current billing month |
| **Segments** | Same 4 categories |
| **Center text** | Total estimated cost (large) + "estimated" label (small) |
| **Data source** | `BillingSnapshot` summed for current month |
| **Purpose** | "Where does my money go?" |

### Chart 3: Daily Spend

| Property | Value |
|----------|-------|
| **Type** | Line chart (solid) + dashed forecast line |
| **Period** | Day 1 of month → today (solid), today → end of month (dashed) |
| **Forecast** | Linear projection based on avg daily spend so far |
| **Reference line** | Previous month's total as horizontal dotted line |
| **Data source** | Daily `BillingSnapshot` totals |
| **Purpose** | "Am I on track or spiking?" |

### Chart 4: Usage vs Plan Limits

| Property | Value |
|----------|-------|
| **Type** | 4 horizontal progress bars |
| **Bars** | GPU Hours, Storage (GB), ETL Runs, API Requests |
| **Format** | `12.5 / 100 hrs` with percentage fill |
| **Colors** | Green (<70%), Amber (70-90%), Red (>90%) |
| **Data source** | `ResourceMetrics` aggregated for current period vs `PricingPlan` limits |
| **Purpose** | "Am I about to hit my limits?" |

### Chart 5: Cost per Training Run

| Property | Value |
|----------|-------|
| **Type** | Bar chart |
| **Period** | Last 10 training runs |
| **Bar color** | By model type: Retrieval (blue), Ranking (green), Multitask (pink) |
| **Label** | Run name or `TR-{id}` |
| **Data source** | `TrainingRun` model — `gpu_training_hours * rate` per run |
| **Purpose** | "Which runs are expensive? Can I optimize?" |

### Chart 6: Cost by Category Over Time

| Property | Value |
|----------|-------|
| **Type** | Stacked area chart |
| **Period** | 30 days |
| **Areas** | Same 4 categories (Compute, Storage, Processing, Serving) |
| **Data source** | Daily `BillingSnapshot` by category |
| **Purpose** | "Is storage growing? Is compute spiking?" |

---

## Invoice Preview Table

Full-width table below the charts. Shows line items for the current billing period.

### Columns

| Column | Width | Alignment | Description |
|--------|-------|-----------|-------------|
| Category | 35% | Left | Billable category with icon |
| Usage | 25% | Right | Quantity + unit (e.g., `12.5 hrs`) |
| Rate | 20% | Right | Per-unit rate (e.g., `$4.80/hr`) |
| Subtotal | 20% | Right | Usage x Rate |

### Example Rows

| Category | Usage | Rate | Subtotal |
|----------|-------|------|----------|
| GPU Training | 12.5 hrs | $4.80/hr | $60.00 |
| Experiments | 8 runs | $2.50/run | $20.00 |
| Storage | 152 GB | $0.12/GB | $18.24 |
| ETL Processing | 45 runs | $0.80/run | $36.00 |
| BQ Analysis | 2.3 TB | $6.50/TB | $14.95 |
| API Serving | 47,250 req | Included | $0.00 |
| | | | |
| **Platform Fee** | | | **$199.00** |
| **Estimated Total** | | | **$348.19** |

### Table Footer

- "Final invoice generated on Feb 28, 2026" — small text, #9ca3af
- Optional: "Download PDF" link (future)

---

## Data Architecture

### Cost Derivation Flow

```
ResourceMetrics (daily)              PricingPlan (per client)
├── gpu_training_hours  ──────────→  x compute_rate_per_hour  ──→  Compute $
├── QuickTest count     ──────────→  x experiment_rate        ──→  Compute $
├── bq_total_bytes      ──────────→  x storage_rate_per_gb    ──→  Storage $
├── gcs_total_bytes     ──────────→  x storage_rate_per_gb    ──→  Storage $
├── db_size_bytes       ──────────→  x storage_rate_per_gb    ──→  Storage $
├── bq_bytes_billed     ──────────→  x query_rate_per_tb      ──→  Processing $
├── etl_jobs_completed  ──────────→  x etl_rate_per_run       ──→  Processing $
└── cloud_run_total_requests ─────→  x serving_rate_per_1k    ──→  Serving $
                                                                        │
                                                                        ▼
                                                              BillingSnapshot (daily)
                                                              ├── date
                                                              ├── category (enum)
                                                              ├── usage_quantity
                                                              ├── unit_rate (frozen at snapshot time)
                                                              └── total_cost
```

### New Models Required

**PricingPlan** — Defines rates for a client's subscription tier.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField | Plan name (Starter, Pro, Enterprise) |
| `platform_fee` | DecimalField | Fixed monthly fee |
| `compute_rate_per_hour` | DecimalField | GPU training rate ($/hr) |
| `experiment_rate` | DecimalField | QuickTest rate ($/run) |
| `storage_rate_per_gb` | DecimalField | Combined storage rate ($/GB/mo) |
| `query_rate_per_tb` | DecimalField | BigQuery analysis rate ($/TB) |
| `etl_rate_per_run` | DecimalField | ETL job rate ($/run) |
| `serving_rate_per_1k` | DecimalField | API serving rate ($/1K requests) |
| `gpu_hours_limit` | FloatField | Monthly GPU hours included |
| `storage_limit_gb` | FloatField | Storage included (GB) |
| `etl_runs_limit` | IntegerField | ETL runs included |
| `api_requests_limit` | IntegerField | API requests included (0 = unlimited) |

**BillingSnapshot** — Daily materialized cost records.

| Field | Type | Description |
|-------|------|-------------|
| `date` | DateField | Snapshot date |
| `category` | CharField | `compute`, `storage`, `processing`, `serving` |
| `usage_quantity` | FloatField | Amount consumed (hours, GB, runs, requests) |
| `unit_rate` | DecimalField | Rate at time of snapshot (frozen) |
| `total_cost` | DecimalField | usage_quantity x unit_rate |
| `details` | JSONField | Breakdown `[{item, quantity, cost}]` |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/system/billing/summary/` | GET | Summary bar data (period, estimated total, plan, % elapsed) |
| `/api/system/billing/charts/` | GET | All 6 chart datasets |
| `/api/system/billing/invoice/` | GET | Current month invoice preview rows |

---

## Cross-Validation (Future)

Once GCP Billing Export is wired to BigQuery in the control-plane project, derived costs can be cross-validated against actual GCP costs:

```
Derived cost (ResourceMetrics x PricingPlan rates)
         vs
Actual GCP cost (billing export, filtered by project label)
         =
Margin verification per client
```

This ensures unit rates stay aligned with real costs and the target margin is maintained. This is an internal (control-plane) concern — the client never sees this comparison.

---

## Alternatives Considered

### Option 2: Cost Transparency

Show actual GCP costs with an explicit percentage markup. Table becomes:

| Service | GCP Cost | Platform Fee (30%) | Total |
|---------|----------|---------------------|-------|
| Vertex AI | $46.15 | $13.85 | $60.00 |
| BigQuery | $25.50 | $7.65 | $33.15 |

**Rejected because:** Exposes margin, invites price comparison, reveals GCP internals to business users.

### Option 3: Plan-Based (Pure Subscription)

Fixed tiers with hard limits. Overages billed separately.

**Rejected because:** Too rigid for ML workloads where usage varies wildly month-to-month. A client training 20 models one month and 2 the next would overpay or hit limits unpredictably.

---

## Implementation Notes

- Charts use **Chart.js 4.4.0** (already loaded on the page)
- Layout follows the same 3-column grid as System Details resource charts
- Color palette for categories matches throughout: Compute=orange, Storage=blue, Processing=purple, Serving=green
- `BillingSnapshot` populated by extending the existing `collect_resource_metrics` management command (runs daily at 02:00 UTC)
- Summary bar sits between chapter header and chart grid (no separate container — just a styled div)
- Invoice table uses existing `.info-card` styling with a custom table inside
