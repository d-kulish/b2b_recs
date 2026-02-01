# Endpoints Dashboard Specification

## Document Purpose
This document provides detailed specifications for implementing the **Endpoints Dashboard** chapter on the Deployment page. The dashboard displays performance metrics, health status, and resource utilization for deployed ML serving endpoints.

**Created**: 2026-02-01
**Status**: Phase 0 Implemented (Skeleton UI)

---

## Overview

### Purpose
The Endpoints Dashboard enables users to:
1. Monitor performance of all deployed endpoints at a glance
2. Compare endpoints side-by-side (request volume, latency, errors)
3. Identify scaling patterns and resource utilization
4. Detect cold start issues and optimize configurations
5. Track model-specific inference metrics (future: Prometheus)

### Key Principles
- **Comparison-first**: Dashboard designed for multi-endpoint comparison
- **Actionable insights**: Every metric should help users make decisions
- **Production-ready**: Handle empty states, errors, and edge cases gracefully

### Scope

| Parameter | Value |
|-----------|-------|
| Time range | Last 7 days (fixed) |
| Update mode | On-demand refresh button |
| View mode | Multi-endpoint comparison |
| Data source | Cloud Monitoring API (primary), Prometheus (future) |
| Granularity | 4-hour buckets (42 data points) |

---

## Data Sources

### Primary: Google Cloud Monitoring (FREE)

Cloud Monitoring automatically collects metrics for Cloud Run services. No additional configuration required.

**API**: `google-cloud-monitoring` Python SDK
**Documentation**: https://cloud.google.com/monitoring/api/metrics_gcp

| Metric Type | Cloud Monitoring Metric | Unit | Aggregation |
|-------------|------------------------|------|-------------|
| Request Count | `run.googleapis.com/request_count` | count | SUM |
| Request Latency | `run.googleapis.com/request_latencies` | ms | DISTRIBUTION |
| Instance Count | `run.googleapis.com/container/instance_count` | count | MAX/MEAN |
| Startup Latency | `run.googleapis.com/container/startup_latencies` | ms | DISTRIBUTION |
| CPU Utilization | `run.googleapis.com/container/cpu/utilizations` | ratio (0-1) | MEAN |
| Memory Utilization | `run.googleapis.com/container/memory/utilizations` | ratio (0-1) | MEAN |
| Billable Time | `run.googleapis.com/container/billable_instance_time` | s | SUM |

**Metric Labels Available**:
- `service_name`: Cloud Run service name (e.g., "model-a-serving")
- `revision_name`: Specific revision
- `response_code`: HTTP status code
- `response_code_class`: 2xx, 4xx, 5xx

### Future: TensorFlow Serving Prometheus Metrics

Requires enabling Prometheus endpoint in TF Serving container configuration.

**Configuration** (add to TF Serving startup):
```
--monitoring_config_file=/models/monitoring.config
--rest_api_port=8501
```

**monitoring.config**:
```protobuf
prometheus_config {
  enable: true
  path: "/monitoring/prometheus/metrics"
}
```

| Metric Type | Prometheus Metric | Description |
|-------------|------------------|-------------|
| Inference Count | `:tensorflow:serving:request_count` | Requests per model |
| Runtime Latency | `:tensorflow:serving:runtime_latency` | Pure model inference time |
| Request Latency | `:tensorflow:serving:request_latency` | End-to-end serving time |
| Batch Size | `:tensorflow:serving:batching_session:batch_size` | Actual batch sizes used |
| Graph Runs | `:tensorflow:core:graph_runs` | TF graph executions |

**Access Method**: Google Cloud Managed Service for Prometheus (included in Cloud Monitoring) or custom Prometheus server.

---

## Page Layout

### Overall Structure

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Endpoints Dashboard                                            [🔄 Refresh]     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│ [KPI Summary Cards - 4 cards in a row]                                          │
│                                                                                  │
│ [Charts Row 1: Request Volume + Latency Distribution]                           │
│                                                                                  │
│ [Charts Row 2: Container Instances + Error Rate]                                │
│                                                                                  │
│ [Charts Row 3: Cold Start Latency + Resource Utilization]                       │
│                                                                                  │
│ [Table 1: Endpoint Performance Comparison]                                      │
│                                                                                  │
│ [Table 2: Peak Usage Periods]                                                   │
│                                                                                  │
│ [Future: Prometheus Metrics Section]                                            │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Responsive Breakpoints

| Breakpoint | Layout |
|------------|--------|
| Desktop (≥1200px) | 2 charts per row, 4 KPI cards |
| Tablet (768-1199px) | 1 chart per row, 2 KPI cards per row |
| Mobile (<768px) | 1 chart per row, 1 KPI card per row, stacked |

---

## Component Specifications

### 1. KPI Summary Cards

Four summary cards showing aggregated metrics across all endpoints for the last 7 days.

```
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ 📊 Total         │ │ ⚡ Avg Latency   │ │ ❌ Error Rate    │ │ 🖥️ Peak          │
│ Requests         │ │ (P95)            │ │                  │ │ Instances        │
│                  │ │                  │ │                  │ │                  │
│ 45,230           │ │ 142 ms           │ │ 0.02%            │ │ 8                │
│ ↑ 12% vs prev    │ │ ↓ 8ms vs prev    │ │ ─ stable         │ │ avg: 2.3         │
└──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘
```

#### Card 1: Total Requests

| Property | Value |
|----------|-------|
| Title | "Total Requests" |
| Icon | 📊 or chart-bar icon |
| Primary Value | Sum of all requests across all endpoints |
| Format | Abbreviated (45.2K, 1.2M) |
| Secondary | % change vs previous 7 days |
| Color | Blue (#3b82f6) |

**Calculation**:
```python
total_requests = sum(request_count for all endpoints over 7 days)
prev_requests = sum(request_count for all endpoints, days -14 to -7)
change_pct = ((total_requests - prev_requests) / prev_requests) * 100
```

#### Card 2: Average Latency (P95)

| Property | Value |
|----------|-------|
| Title | "Avg Latency (P95)" |
| Icon | ⚡ or clock icon |
| Primary Value | Weighted average P95 latency |
| Format | `XXX ms` |
| Secondary | Change in ms vs previous 7 days |
| Color | Yellow/Amber (#f59e0b) |

**Calculation**:
```python
# Weighted by request count per endpoint
p95_latency = weighted_average(
    values=[endpoint.p95_latency for endpoint in endpoints],
    weights=[endpoint.request_count for endpoint in endpoints]
)
```

#### Card 3: Error Rate

| Property | Value |
|----------|-------|
| Title | "Error Rate" |
| Icon | ❌ or exclamation-triangle icon |
| Primary Value | Percentage of 4xx + 5xx responses |
| Format | `X.XX%` |
| Secondary | "stable" / "↑ increasing" / "↓ decreasing" |
| Color | Red (#ef4444) if >1%, Green (#10b981) if <0.1%, Gray otherwise |

**Calculation**:
```python
error_count = sum(request_count where response_code_class in ['4xx', '5xx'])
total_count = sum(request_count)
error_rate = (error_count / total_count) * 100
```

#### Card 4: Peak Instances

| Property | Value |
|----------|-------|
| Title | "Peak Instances" |
| Icon | 🖥️ or server icon |
| Primary Value | Maximum concurrent instances (any endpoint) |
| Format | Integer |
| Secondary | Average instances over period |
| Color | Purple (#8b5cf6) |

**Calculation**:
```python
peak_instances = max(instance_count across all endpoints and time buckets)
avg_instances = mean(instance_count across all endpoints and time buckets)
```

---

### 2. Chart 1: Request Volume Over Time

**Purpose**: Visualize traffic patterns across all endpoints, identify peak periods.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Request Volume                                                    [Legend]      │
│                                                                                  │
│  Requests                                                                        │
│  12K ┤                                                                          │
│      │                    ████                                                  │
│  10K ┤                   █████                                                  │
│      │        ████      ██████                                                  │
│   8K ┤       █████     ███████  ████                                           │
│      │      ██████    ████████ █████                                           │
│   6K ┤     ███████   █████████ ██████                                          │
│      │    ████████  ██████████ ███████     ████                                │
│   4K ┤   █████████ ███████████ ████████   █████                                │
│      │  ██████████ ███████████ █████████ ██████                                │
│   2K ┤ ███████████ ███████████ ██████████████████                              │
│      │████████████████████████████████████████████████████████████████████████ │
│   0K ┼──────────────────────────────────────────────────────────────────────── │
│      Mon      Tue      Wed      Thu      Fri      Sat      Sun                  │
│                                                                                  │
│      ● model-a-serving (23,450)  ● model-b-serving (21,780)                     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Specifications

| Property | Value |
|----------|-------|
| Chart Type | Stacked Area Chart |
| Library | Chart.js with chartjs-plugin-annotation |
| X-Axis | Time (4-hour buckets, 42 points) |
| Y-Axis | Request count |
| Series | One per endpoint (stacked) |
| Colors | Endpoint color palette (see Color Scheme) |
| Interaction | Hover shows tooltip with exact values |
| Legend | Bottom, clickable to toggle endpoints |

#### Data Structure

```javascript
{
  labels: ["Mon 00:00", "Mon 04:00", "Mon 08:00", ...], // 42 labels
  datasets: [
    {
      label: "model-a-serving",
      data: [1200, 1450, 2300, ...], // 42 values
      backgroundColor: "rgba(59, 130, 246, 0.6)", // blue with opacity
      borderColor: "rgb(59, 130, 246)",
      fill: true
    },
    {
      label: "model-b-serving",
      data: [980, 1100, 1800, ...],
      backgroundColor: "rgba(16, 185, 129, 0.6)", // green with opacity
      borderColor: "rgb(16, 185, 129)",
      fill: true
    }
  ]
}
```

#### Chart.js Configuration

```javascript
{
  type: 'line',
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          usePointStyle: true,
          padding: 20
        }
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label: (context) => `${context.dataset.label}: ${context.parsed.y.toLocaleString()} requests`
        }
      }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          maxRotation: 0,
          callback: (val, idx) => idx % 6 === 0 ? labels[idx] : '' // Show every 6th label (daily)
        }
      },
      y: {
        stacked: true,
        beginAtZero: true,
        ticks: {
          callback: (val) => val >= 1000 ? `${val/1000}K` : val
        }
      }
    },
    elements: {
      line: { tension: 0.3 }, // Smooth curves
      point: { radius: 0, hoverRadius: 5 }
    }
  }
}
```

---

### 3. Chart 2: Latency Distribution (P50/P95/P99)

**Purpose**: Monitor response time SLOs, detect latency degradation.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Latency Distribution                                   [All Endpoints ▼]        │
│                                                                                  │
│  Latency (ms)                                                                    │
│  500 ┤                                                                          │
│      │                                                                          │
│  400 ┤              ●                                                           │
│      │             ╱ ╲           P99 ────                                       │
│  300 ┤            ╱   ╲         ╱                                               │
│      │           ╱     ╲       ╱                                                │
│  200 ┤──────────╱───────╲─────╱────────────────────────────────────────────────│
│      │         ╱         ╲   ╱                   P95 ─ ─ ─                      │
│  150 ┤────────╱───────────╲─╱──────────────────────────────────────────────────│
│      │       ╱             ╳                                                    │
│  100 ┤──────╱─────────────╱─╲──────────────────────────────────────────────────│
│      │═════╱═════════════╱═══╲══════════════════════════════════ P50 ═══       │
│   50 ┤    ╱             ╱     ╲                                                 │
│      │   ╱             ╱       ╲                                                │
│    0 ┼──────────────────────────────────────────────────────────────────────── │
│      Mon      Tue      Wed      Thu      Fri      Sat      Sun                  │
│                                                                                  │
│      ═══ P50 (89ms avg)   ─ ─ P95 (142ms avg)   ─── P99 (287ms avg)            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Specifications

| Property | Value |
|----------|-------|
| Chart Type | Multi-line Chart |
| Library | Chart.js |
| X-Axis | Time (4-hour buckets) |
| Y-Axis | Latency in milliseconds |
| Series | P50 (solid), P95 (dashed), P99 (dotted) |
| Filter | Dropdown to select endpoint or "All Endpoints" |
| Colors | P50: Green (#10b981), P95: Yellow (#f59e0b), P99: Red (#ef4444) |

#### Line Styles

```javascript
// P50 - Solid, thick
{
  label: 'P50',
  borderColor: '#10b981',
  borderWidth: 3,
  borderDash: [],
  fill: false
}

// P95 - Dashed
{
  label: 'P95',
  borderColor: '#f59e0b',
  borderWidth: 2,
  borderDash: [8, 4],
  fill: false
}

// P99 - Dotted
{
  label: 'P99',
  borderColor: '#ef4444',
  borderWidth: 2,
  borderDash: [2, 4],
  fill: false
}
```

#### Filter Behavior

When "All Endpoints" selected:
- Show weighted average of all endpoints

When specific endpoint selected:
- Show that endpoint's percentiles only
- Update chart title to include endpoint name

---

### 4. Chart 3: Container Instances Over Time

**Purpose**: Understand auto-scaling behavior, identify scaling events.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Container Instances                                                              │
│                                                                                  │
│  Instances                                                                       │
│  10 ┤                                                                           │
│     │                    ▄▄▄▄                                                   │
│   8 ┤                   ██████                                                  │
│     │        ▄▄▄       ████████                                                 │
│   6 ┤       ████      ██████████  ▄▄▄▄                                         │
│     │      ██████    ████████████ ██████                                        │
│   4 ┤     ████████  ██████████████████████     ▄▄▄▄                            │
│     │    ██████████ ████████████████████████  ██████                           │
│   2 ┤   ████████████████████████████████████████████████████████████████████   │
│     │  █████████████████████████████████████████████████████████████████████   │
│   0 ┼──────────────────────────────────────────────────────────────────────── │
│      Mon      Tue      Wed      Thu      Fri      Sat      Sun                  │
│                                                                                  │
│      ■ model-a-serving    ■ model-b-serving    ─── min_instances threshold      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Specifications

| Property | Value |
|----------|-------|
| Chart Type | Stacked Area Chart |
| Library | Chart.js |
| X-Axis | Time (4-hour buckets) |
| Y-Axis | Instance count (integer) |
| Series | One per endpoint |
| Annotation | Horizontal line showing `min_instances` config |
| Colors | Match endpoint color palette |

#### Configuration Notes

- Show `min_instances` threshold line if any endpoint has `min_instances > 0`
- Tooltip should show: "X instances handling Y requests"
- Y-axis should always start at 0

---

### 5. Chart 4: Error Rate Over Time

**Purpose**: Track reliability, identify error spikes quickly.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Error Rate                                                       [By Endpoint]  │
│                                                                                  │
│  Error %                                                                         │
│  2.0% ┤                                                                         │
│       │                                                                         │
│  1.5% ┤                              ●                                          │
│       │                             ╱ ╲                                         │
│  1.0% ┤                            ╱   ╲                                        │
│       │                           ╱     ╲                                       │
│  0.5% ┤──────────────────────────╱───────╲──────────────────────────────────── │
│       │                         ╱         ╲                                     │
│  0.0% ┤═══════════════════════════════════════════════════════════════════════ │
│       │                                                                         │
│       Mon      Tue      Wed      Thu      Fri      Sat      Sun                 │
│                                                                                  │
│       ─── model-a-serving (0.05% avg)   ─── model-b-serving (0.02% avg)        │
│                                                                                  │
│  ⚠️ Spike detected: Thu 14:00 - model-a-serving reached 1.8% error rate         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Specifications

| Property | Value |
|----------|-------|
| Chart Type | Line Chart |
| Library | Chart.js |
| X-Axis | Time (4-hour buckets) |
| Y-Axis | Error percentage (0-5% typical scale) |
| Series | One per endpoint |
| Threshold | Horizontal line at 1% (warning) |
| Alert Banner | Show if any spike >1% in period |

#### Error Detection

```javascript
// Detect spikes for alert banner
const spikes = data.filter(point => point.errorRate > 1.0);
if (spikes.length > 0) {
  const worstSpike = spikes.reduce((max, s) => s.errorRate > max.errorRate ? s : max);
  showAlert(`Spike detected: ${worstSpike.time} - ${worstSpike.endpoint} reached ${worstSpike.errorRate}% error rate`);
}
```

---

### 6. Chart 5: Cold Start Latency Distribution

**Purpose**: Monitor startup performance, critical for endpoints with `min_instances=0`.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Cold Start Latency                                                               │
│                                                                                  │
│  Latency (ms)                                                                    │
│                                                                                  │
│  3000 ┤     ┬                                                                   │
│       │     │        ┬                                                          │
│  2500 ┤     │        │                                                          │
│       │     │        │                                                          │
│  2000 ┤   ┌─┴─┐    ┌─┴─┐                                                        │
│       │   │   │    │   │     ┬                                                  │
│  1500 ┤   │   │    │   │     │        ┬                                         │
│       │   │   │    │   │   ┌─┴─┐    ┌─┴─┐                                       │
│  1000 ┤───┤   ├────┤   ├───┤   ├────┤   ├───────────────────────────────────── │
│       │   │   │    │   │   │   │    │   │                                       │
│   500 ┤   └─┬─┘    └─┬─┘   └─┬─┘    └─┬─┘                                       │
│       │     │        │       │        │                                         │
│     0 ┼─────┴────────┴───────┴────────┴─────────────────────────────────────── │
│       endpoint-a  endpoint-b  endpoint-c  endpoint-d                            │
│                                                                                  │
│       Box: IQR (25th-75th)  Whiskers: 5th-95th  ● Median                        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Specifications

| Property | Value |
|----------|-------|
| Chart Type | Box Plot (via chartjs-chart-box-and-violin-plot plugin) |
| Library | Chart.js + plugin |
| X-Axis | Endpoint names |
| Y-Axis | Latency in milliseconds |
| Box | 25th to 75th percentile (IQR) |
| Whiskers | 5th to 95th percentile |
| Median | Line inside box |
| Outliers | Optional: show points beyond whiskers |

#### Alternative: Horizontal Bar Chart

If box plot is too complex, use grouped horizontal bars:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Cold Start Latency by Endpoint                                                   │
│                                                                                  │
│  endpoint-a  ████████████████████████████████████░░░░░░░░░░░░░░░  P50: 1.2s     │
│              ──────────────────────────────────────────────────▶  P95: 2.1s     │
│                                                                                  │
│  endpoint-b  ██████████████████████████████░░░░░░░░░░░░░░░░░░░░░  P50: 0.9s     │
│              ────────────────────────────────────────────▶        P95: 1.8s     │
│                                                                                  │
│  endpoint-c  ████████████████████████████████████████░░░░░░░░░░░  P50: 1.4s     │
│              ──────────────────────────────────────────────────────▶  P95: 2.4s │
│                                                                                  │
│              0s        0.5s       1.0s       1.5s       2.0s       2.5s         │
│                                                                                  │
│              ████ P50 (Median)    ─── P95                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 7. Chart 6: Resource Utilization

**Purpose**: Right-size container resources, identify over/under-provisioning.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Resource Utilization                                   [model-a-serving ▼]      │
│                                                                                  │
│  Utilization %                                                                   │
│  100% ┤                                                                         │
│       │                                                                         │
│   80% ┤                    ████                                                 │
│       │                   █████                                                 │
│   60% ┤        ████      ██████       ════════════════════════════════════════ │
│       │       █████     ███████  ════                                           │
│   40% ┤══════██████════████████═══════════════════════════════════════════════ │
│       │     ███████   █████████                                                 │
│   20% ┤    ████████  ██████████                                                │
│       │   █████████ ███████████                                                 │
│    0% ┼──────────────────────────────────────────────────────────────────────── │
│       Mon      Tue      Wed      Thu      Fri      Sat      Sun                 │
│                                                                                  │
│       ████ CPU (avg 42%)    ═══ Memory (avg 58%)                                │
│                                                                                  │
│  💡 Insight: Memory consistently higher than CPU. Consider adjusting ratio.     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Specifications

| Property | Value |
|----------|-------|
| Chart Type | Dual-series Area/Line Chart |
| Library | Chart.js |
| X-Axis | Time (4-hour buckets) |
| Y-Axis | Percentage (0-100%) |
| Series 1 | CPU Utilization (area, blue) |
| Series 2 | Memory Utilization (line, purple) |
| Filter | Dropdown to select endpoint |
| Insight Banner | Show optimization suggestions |

#### Insight Logic

```javascript
function generateInsight(cpuData, memData) {
  const avgCpu = average(cpuData);
  const avgMem = average(memData);

  if (avgCpu < 20 && avgMem < 30) {
    return "Resources underutilized. Consider reducing CPU/Memory allocation.";
  }
  if (avgCpu > 80) {
    return "CPU consistently high. Consider increasing CPU or adding instances.";
  }
  if (avgMem > 80) {
    return "Memory consistently high. Consider increasing memory allocation.";
  }
  if (avgMem > avgCpu * 1.5) {
    return "Memory consistently higher than CPU. Consider adjusting ratio.";
  }
  return "Resource utilization looks healthy.";
}
```

---

### 8. Table 1: Endpoint Performance Comparison

**Purpose**: Compare all endpoints at a glance, with drill-down capability.

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Endpoint Performance (Last 7 Days)                                        [Export CSV]   │
├──────────────────────┬──────────┬──────────┬──────────┬────────────┬──────────┬─────────┤
│ Endpoint             │ Requests │ Avg (ms) │ P95 (ms) │ Errors     │ Trend    │ Actions │
├──────────────────────┼──────────┼──────────┼──────────┼────────────┼──────────┼─────────┤
│ ▶ model-a-serving    │ 23,450   │ 89       │ 142      │ 12 (0.05%) │ ↑ +15%   │ [View]  │
│   └─ Expanded details...                                                                  │
├──────────────────────┼──────────┼──────────┼──────────┼────────────┼──────────┼─────────┤
│ ▶ model-b-serving    │ 21,780   │ 112      │ 198      │ 5 (0.02%)  │ ↓ -3%    │ [View]  │
├──────────────────────┼──────────┼──────────┼──────────┼────────────┼──────────┼─────────┤
│ ▶ model-c-serving    │ 8,920    │ 156      │ 312      │ 89 (1.0%)  │ ─ 0%     │ [View]  │
└──────────────────────┴──────────┴──────────┴──────────┴────────────┴──────────┴─────────┘
```

#### Column Specifications

| Column | Width | Content | Sorting |
|--------|-------|---------|---------|
| Endpoint | 200px | Service name with expand arrow | Alphabetical |
| Requests | 100px | Total count, abbreviated | Numeric desc (default) |
| Avg (ms) | 80px | Mean latency | Numeric |
| P95 (ms) | 80px | 95th percentile latency | Numeric |
| Errors | 120px | Count + percentage | Numeric |
| Trend | 80px | Arrow + % change vs prev 7d | Numeric |
| Actions | 80px | View button | - |

#### Expanded Details (Inline Drill-Down)

When row is expanded:

```
├──────────────────────┼──────────┼──────────┼──────────┼────────────┼──────────┼─────────┤
│ ▼ model-a-serving    │ 23,450   │ 89       │ 142      │ 12 (0.05%) │ ↑ +15%   │ [View]  │
│   ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│   │ Configuration                        │ Performance                               │  │
│   │ ─────────────────────────────────   │ ───────────────────────────────────────  │  │
│   │ CPU: 2 vCPU                         │ Cold Starts: 47 (avg 1.2s)                │  │
│   │ Memory: 4 Gi                        │ Peak Instances: 8                         │  │
│   │ Min Instances: 0                    │ Avg Instances: 2.3                        │  │
│   │ Max Instances: 10                   │ CPU Util: 42%                             │  │
│   │ Timeout: 300s                       │ Memory Util: 58%                          │  │
│   │                                     │                                           │  │
│   │ Model: chern-retrieval-v5           │ Deployed: 2026-01-28 14:30               │  │
│   │ Version: v1                         │ Training Run: #47                         │  │
│   └──────────────────────────────────────────────────────────────────────────────────┘  │
├──────────────────────┼──────────┼──────────┼──────────┼────────────┼──────────┼─────────┤
```

#### Conditional Formatting

| Condition | Style |
|-----------|-------|
| Error rate > 1% | Red background on Errors cell |
| Latency P95 > 500ms | Yellow background on P95 cell |
| Trend > +20% | Bold green text |
| Trend < -20% | Bold red text |

---

### 9. Table 2: Peak Usage Periods

**Purpose**: Identify high-traffic windows for capacity planning.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Peak Usage Periods (Top 10)                                                              │
├──────────────────────────┬──────────────────────┬──────────┬──────────────┬────────────┤
│ Time Period              │ Endpoint             │ Requests │ Max Instances│ Avg Latency│
├──────────────────────────┼──────────────────────┼──────────┼──────────────┼────────────┤
│ Wed, Jan 29 14:00-18:00  │ model-a-serving      │ 4,230    │ 8            │ 156ms      │
├──────────────────────────┼──────────────────────┼──────────┼──────────────┼────────────┤
│ Thu, Jan 30 09:00-13:00  │ model-b-serving      │ 3,890    │ 6            │ 189ms      │
├──────────────────────────┼──────────────────────┼──────────┼──────────────┼────────────┤
│ Tue, Jan 28 11:00-15:00  │ model-a-serving      │ 3,540    │ 5            │ 142ms      │
├──────────────────────────┼──────────────────────┼──────────┼──────────────┼────────────┤
│ Mon, Jan 27 16:00-20:00  │ model-c-serving      │ 2,890    │ 4            │ 201ms      │
├──────────────────────────┼──────────────────────┼──────────┼──────────────┼────────────┤
│ Fri, Jan 31 10:00-14:00  │ model-a-serving      │ 2,650    │ 5            │ 138ms      │
└──────────────────────────┴──────────────────────┴──────────┴──────────────┴────────────┘
```

#### Column Specifications

| Column | Width | Content |
|--------|-------|---------|
| Time Period | 200px | Day + date + 4-hour window |
| Endpoint | 180px | Service name |
| Requests | 100px | Count in that period |
| Max Instances | 120px | Peak concurrent instances |
| Avg Latency | 100px | Mean latency during peak |

#### Sorting
Default: By Requests descending (busiest periods first)

---

### 10. Future: Prometheus Metrics Section

**Purpose**: Display TF Serving-specific metrics when Prometheus is enabled.

**Visibility**: Only shown when at least one endpoint has Prometheus metrics available.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Model Inference Metrics (Prometheus)                            [Configure]     │
│                                                                                  │
│ ⚠️ Prometheus metrics require TF Serving configuration. [Learn More]            │
│                                                                                  │
│ ══════════════════════════════════════════════════════════════════════════════  │
│                                                                                  │
│ ┌────────────────────────────────────┐ ┌────────────────────────────────────┐   │
│ │ Chart 7: Inference vs Request      │ │ Chart 8: Batch Size Distribution   │   │
│ │ Latency Breakdown                  │ │                                    │   │
│ │                                    │ │                                    │   │
│ │  Request Latency ████████████████  │ │  ████                              │   │
│ │  Inference Time  ██████████        │ │  ████████                          │   │
│ │  Overhead        ██████            │ │  ████████████                      │   │
│ │                                    │ │  ████                              │   │
│ │  Shows where time is spent:        │ │   1    2    4    8   16            │   │
│ │  model inference vs overhead       │ │      Batch Size                    │   │
│ └────────────────────────────────────┘ └────────────────────────────────────┘   │
│                                                                                  │
│ ┌───────────────────────────────────────────────────────────────────────────┐   │
│ │ Table 3: Model-Level Metrics                                               │   │
│ ├──────────────────┬────────────┬──────────────┬──────────────┬────────────┤   │
│ │ Model            │ Inferences │ Runtime (ms) │ Request (ms) │ Overhead % │   │
│ ├──────────────────┼────────────┼──────────────┼──────────────┼────────────┤   │
│ │ recommender      │ 45,230     │ 45           │ 89           │ 49%        │   │
│ └──────────────────┴────────────┴──────────────┴──────────────┴────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Chart 7: Latency Breakdown

| Property | Value |
|----------|-------|
| Chart Type | Stacked Horizontal Bar |
| Purpose | Show inference time vs overhead |
| Metrics | `:tensorflow:serving:runtime_latency` vs `:tensorflow:serving:request_latency` |
| Insight | If overhead > 50%, investigate network/preprocessing |

#### Chart 8: Batch Size Distribution

| Property | Value |
|----------|-------|
| Chart Type | Histogram |
| Purpose | Understand batching effectiveness |
| Metric | `:tensorflow:serving:batching_session:batch_size` |
| Insight | If mostly batch_size=1, batching not effective |

#### Table 3: Model-Level Metrics

| Column | Metric |
|--------|--------|
| Model | Model name from TF Serving |
| Inferences | `:tensorflow:serving:request_count` |
| Runtime (ms) | `:tensorflow:serving:runtime_latency` P50 |
| Request (ms) | `:tensorflow:serving:request_latency` P50 |
| Overhead % | (Request - Runtime) / Request * 100 |

---

## Empty States

### No Endpoints Deployed

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│     📊 No Endpoint Metrics Available                            │
│                                                                  │
│     Deploy an endpoint to start collecting metrics.             │
│                                                                  │
│     Metrics will appear here once your endpoints                │
│     receive traffic.                                            │
│                                                                  │
│     [Go to Serving Endpoints]  [Documentation]                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### No Data in Time Range

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│     📈 No Data for Selected Period                              │
│                                                                  │
│     Your endpoints exist but have no traffic data               │
│     for the last 7 days.                                        │
│                                                                  │
│     Possible reasons:                                           │
│     • Endpoints are deployed but not receiving requests         │
│     • Endpoints were recently deployed (< 1 hour ago)           │
│     • All endpoints are currently inactive                      │
│                                                                  │
│     [Refresh]  [Run Health Check]                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Loading State

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│     ⏳ Loading metrics from Cloud Monitoring...                 │
│                                                                  │
│     [████████████░░░░░░░░░░░░░░░░░░░░]                          │
│                                                                  │
│     This may take a few seconds for large time ranges.          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Error State

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│     ❌ Failed to Load Metrics                                   │
│                                                                  │
│     Error: Cloud Monitoring API returned 403 (Permission Denied)│
│                                                                  │
│     The service account may be missing the                      │
│     `roles/monitoring.viewer` role.                             │
│                                                                  │
│     [Retry]  [View Troubleshooting Guide]                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Color Scheme

### Endpoint Color Palette

Assign colors to endpoints consistently:

```javascript
const ENDPOINT_COLORS = [
  { name: 'Blue',    primary: '#3b82f6', light: 'rgba(59, 130, 246, 0.2)' },
  { name: 'Green',   primary: '#10b981', light: 'rgba(16, 185, 129, 0.2)' },
  { name: 'Purple',  primary: '#8b5cf6', light: 'rgba(139, 92, 246, 0.2)' },
  { name: 'Orange',  primary: '#f97316', light: 'rgba(249, 115, 22, 0.2)' },
  { name: 'Pink',    primary: '#ec4899', light: 'rgba(236, 72, 153, 0.2)' },
  { name: 'Cyan',    primary: '#06b6d4', light: 'rgba(6, 182, 212, 0.2)' },
  { name: 'Yellow',  primary: '#eab308', light: 'rgba(234, 179, 8, 0.2)' },
  { name: 'Red',     primary: '#ef4444', light: 'rgba(239, 68, 68, 0.2)' },
];

function getEndpointColor(index) {
  return ENDPOINT_COLORS[index % ENDPOINT_COLORS.length];
}
```

### Status Colors

| Status | Color | Hex |
|--------|-------|-----|
| Healthy | Green | #10b981 |
| Warning | Yellow | #f59e0b |
| Error | Red | #ef4444 |
| Inactive | Gray | #6b7280 |

### Percentile Colors

| Percentile | Color | Use |
|------------|-------|-----|
| P50 | Green | #10b981 | Good/typical performance |
| P95 | Yellow | #f59e0b | Warning threshold |
| P99 | Red | #ef4444 | Worst case |

---

## API Endpoints

### New API Endpoints Required

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/endpoints-dashboard/summary/` | KPI summary for all endpoints |
| GET | `/api/endpoints-dashboard/request-volume/` | Time series for Chart 1 |
| GET | `/api/endpoints-dashboard/latency/` | Time series for Chart 2 |
| GET | `/api/endpoints-dashboard/instances/` | Time series for Chart 3 |
| GET | `/api/endpoints-dashboard/errors/` | Time series for Chart 4 |
| GET | `/api/endpoints-dashboard/cold-starts/` | Distribution for Chart 5 |
| GET | `/api/endpoints-dashboard/utilization/` | Time series for Chart 6 |
| GET | `/api/endpoints-dashboard/performance-table/` | Data for Table 1 |
| GET | `/api/endpoints-dashboard/peak-periods/` | Data for Table 2 |

### Query Parameters (Common)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int | 7 | Time range (future expansion) |
| `endpoint_id` | int | null | Filter to specific endpoint |
| `granularity` | string | "4h" | Time bucket size |

### Response Format (Example: Summary)

```json
{
  "success": true,
  "data": {
    "total_requests": 45230,
    "total_requests_prev": 40384,
    "total_requests_change_pct": 12.0,
    "avg_latency_p95_ms": 142,
    "avg_latency_p95_ms_prev": 150,
    "avg_latency_change_ms": -8,
    "error_rate_pct": 0.02,
    "error_rate_trend": "stable",
    "peak_instances": 8,
    "avg_instances": 2.3,
    "endpoints_count": 3,
    "period": {
      "start": "2026-01-25T00:00:00Z",
      "end": "2026-02-01T00:00:00Z"
    }
  },
  "generated_at": "2026-02-01T10:30:00Z"
}
```

---

## Implementation Phases

### Phase 0: Skeleton UI ✅ COMPLETE

| Component | Status | Files |
|-----------|--------|-------|
| CSS styles | ✅ Done | `static/css/endpoints_dashboard.css` |
| JS module (IIFE) | ✅ Done | `static/js/endpoints_dashboard.js` |
| HTML chapter | ✅ Done | `templates/ml_platform/model_deployment.html` |
| KPI cards (4) | ✅ Done | Skeleton values ("--") |
| Charts grid (6) | ✅ Done | Empty Chart.js instances |
| Tables (2) | ✅ Done | 5 skeleton rows with shimmer |
| Prometheus section | ✅ Done | "Coming Soon" badge |
| Refresh button | ✅ Done | Disabled state |
| Responsive layout | ✅ Done | Breakpoints at 1200px, 768px |

**Deliverable**: Visual scaffolding ready for API integration

**Files Created/Modified**:
- `static/css/endpoints_dashboard.css` - Dashboard-specific styles with `.dashboard-` prefix
- `static/js/endpoints_dashboard.js` - IIFE module with init/load/refresh API
- `templates/ml_platform/model_deployment.html` - Added chapter HTML, CSS/JS links, initialization

### Phase 1: Core Dashboard (MVP)

| Component | Priority |
|-----------|----------|
| KPI Summary Cards (4) | P0 |
| Chart 1: Request Volume | P0 |
| Chart 2: Latency Distribution | P0 |
| Table 1: Performance Comparison | P0 |
| Empty States | P0 |
| Refresh Button | P0 |

**Deliverable**: Basic dashboard showing traffic and latency

### Phase 2: Scaling & Resources

| Component | Priority |
|-----------|----------|
| Chart 3: Container Instances | P1 |
| Chart 4: Error Rate | P1 |
| Chart 5: Cold Start Latency | P1 |
| Chart 6: Resource Utilization | P1 |
| Table 2: Peak Usage Periods | P1 |
| Inline Drill-Down (Table 1) | P1 |

**Deliverable**: Full operational visibility

### Phase 3: Prometheus Integration (Future)

| Component | Priority |
|-----------|----------|
| TF Serving Prometheus config | P2 |
| Chart 7: Latency Breakdown | P2 |
| Chart 8: Batch Size Distribution | P2 |
| Table 3: Model-Level Metrics | P2 |

**Deliverable**: Deep model inference insights

### Phase 4: Enhancements (Future)

| Component | Priority |
|-----------|----------|
| Time range selector | P3 |
| Auto-refresh option | P3 |
| Alert integration | P3 |
| Cost tracking | P3 |
| Export/download reports | P3 |

---

## Technical Dependencies

### Python Packages

```
google-cloud-monitoring>=2.16.0  # Already in requirements.txt
```

### JavaScript Libraries

```
chart.js@4.x                     # Already installed
chartjs-plugin-annotation        # For threshold lines
chartjs-chart-box-and-violin-plot  # For cold start box plots (optional)
```

### GCP IAM Roles Required

The Django app service account needs:
- `roles/monitoring.viewer` - Read metrics from Cloud Monitoring

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:django-app@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.viewer"
```

---

## Related Documentation

- [Phase: Endpoints](phase_endpoints.md) - Serving Endpoints chapter specification
- [Cloud Run Monitoring](https://cloud.google.com/run/docs/monitoring) - GCP documentation
- [TensorFlow Serving Configuration](https://www.tensorflow.org/tfx/serving/serving_config) - Prometheus setup
- [Chart.js Documentation](https://www.chartjs.org/docs/) - Charting library

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-01 | Phase 0 implemented: Skeleton UI with CSS, JS module, HTML integration |
| 2026-02-01 | Initial specification created |
