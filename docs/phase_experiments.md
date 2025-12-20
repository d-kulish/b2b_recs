# Phase: Experiments Domain

## Document Purpose
This document provides **high-level specifications** for the Experiments domain. For detailed implementation instructions, see:

👉 **[phase_experiments_implementation.md](phase_experiments_implementation.md)** - Complete implementation guide with code examples

**Last Updated**: 2025-12-20

---

## ⚠️ IMPORTANT: Implementation Guide

**Before implementing, read the detailed implementation guide:**

| Document | Purpose |
|----------|---------|
| **[phase_experiments_implementation.md](phase_experiments_implementation.md)** | Step-by-step implementation with code |
| This document | High-level concepts and UI mockups |

---

## Key Technical Decisions (2024-12-14)

| Decision | Choice |
|----------|--------|
| Pipeline Framework | **Native TFX SDK** (NOT KFP v2 placeholder) |
| Data Flow | BigQuery → TFRecords → TFX |
| Container Image | `gcr.io/tfx-oss-public/tfx:latest` |
| TensorBoard | **NOT USED** (too expensive) - custom visualizations |
| Pipeline Compilation | On-demand at submission time |
| Sampling | TFX-level (ExampleGen/Transform) |
| Train/Val Split | 3 options: random (hash-based), time_holdout (date-filtered + hash), strict_time (true temporal) |
| Model Type (Phase 1) | Retrieval only |

---

## Recent Updates (December 2025)

### Pipeline DAG Visualization with Component Logs (2025-12-20)

**Major Enhancement:**

1. **Vertical DAG Layout** - Visual pipeline representation matching Vertex AI Pipelines style
   - 4-row structure: Examples → Stats/Schema → Transform → Train
   - SVG bezier curve connections between components
   - Clickable components for log inspection

2. **Component Logs Panel** - View execution logs without GCP access
   - Last ~15 log entries per component
   - Refresh button to fetch latest logs
   - Logs fetched from Cloud Logging API via `resource.type="ml_job"`
   - 7-day lookback window for completed experiments

3. **Color-Coded Status** - Component status at a glance
   - Grey outline: Pending
   - Orange fill: Running (animated pulse)
   - Green fill: Completed successfully
   - Red fill: Failed

4. **Technical Implementation**
   - New endpoint: `GET /api/quick-tests/{id}/logs/{component}/`
   - Uses Google Cloud Logging Python client
   - Extracts task job IDs from Vertex AI pipeline task details
   - IAM requirement: `roles/logging.viewer` for service account

### View Modal Redesign with Tabs & Artifacts (2025-12-19)

**Major Redesign:**

1. **4-Tab Modal Layout** - Clean tabbed interface replacing cluttered boxes
   - **Overview Tab**: Status, configuration, training params, results
   - **Pipeline Tab**: 6-stage progress bar with stage-by-stage status
   - **Data Insights Tab**: Dataset statistics + inferred schema (lazy-loaded)
   - **Training Tab**: Training curves placeholder (for future MLflow integration)

2. **Error Pattern Matching** - Smart error classification with fix suggestions
   - 15+ patterns for common failures (memory, schema, BigQuery, timeout, etc.)
   - User-friendly error titles instead of raw stack traces
   - Actionable suggestions (e.g., "Try reducing batch_size or selecting larger hardware")

3. **Artifact Visibility** - View pipeline artifacts without GCP access
   - Statistics: Feature count, missing %, min/max/mean values
   - Schema: Feature names, types, required/optional
   - Lazy-loaded on tab switch (not on modal open)

4. **Hidden GCP Details** - Users only see Django app
   - Removed Vertex AI links (users can't access)
   - Removed GCS paths (users can't access)
   - All artifact data parsed and displayed in-app

### Experiment View Modal (2025-12-19)

**New Features:**

1. **Comprehensive View Modal** - Click experiment card or View button to see full details
   - Configuration: Feature Config, Model Config, Dataset
   - Training Parameters: Epochs, Batch Size, LR, Sample %, Split Strategy, Hardware
   - Pipeline Progress: 6-stage progress bar with real-time updates
   - Results: Loss, Recall@10/50/100, Vocabulary statistics
   - Error Section: Classified error with suggestions for failed experiments

2. **View Button** - Green button on experiment cards (above Cancel)
   - Opens the View modal with full experiment details
   - Alternative to clicking the card itself

3. **Real-time Updates** - View modal polls for updates on running experiments
   - Updates every 10 seconds
   - Auto-stops polling when experiment completes

4. **Styled Confirmation Dialog** - Cancel now uses styled modal instead of browser confirm()
   - Matches the design of confirmation dialogs elsewhere in the app

5. **Unified Backend Logging** - All experiment logs now show `Exp #N (id=X)` format
   - Makes it easier to correlate UI and server logs

### Experiment Cards Redesign & Cancel (2025-12-19)

**New Features:**

1. **Experiment Name & Description** - Optional fields to identify experiments
   - Name and Description fields in Step 1 of New Experiment wizard
   - Displayed on experiment cards (description truncated to 50 chars)

2. **Cancel Running Experiments** - Cancel button on every experiment card
   - Active (red) for running/submitting experiments
   - Disabled (light red) for completed/failed/cancelled
   - Calls `aiplatform.PipelineJob.cancel()` via Vertex AI SDK

3. **4-Column Card Layout** - Better information organization
   - Column 1 (30%): Exp #, Name, Description, Start/End times
   - Column 2 (20%): Dataset, Features, Model
   - Column 3 (30%): Training params (placeholder)
   - Column 4 (20%): View button, Cancel button

4. **Progress Bar Styling** - Tensor-breakdown-bar style
   - 24px height with labels inside
   - Gradient green colors for completed stages
   - Animated blue for running, red for failed

### Page Split from Configs Domain (2025-12-13)

**Major Change:** Quick Test functionality moved from Configs page to dedicated Experiments page.

**Why This Change:**
- `model_configs.html` exceeded 10,000 lines
- Running experiments and analyzing experiments deserve dedicated space
- Clear separation: Configs = Configure features/architecture, Experiments = Run and compare

**New UI Structure:**
- **Experiments Page** (`model_experiments.html`) now handles:
  - Feature Config + Model Config selection
  - Training parameters configuration
  - Quick Test execution and monitoring
  - Future: MLflow experiment comparison

**How Experiments Page Works:**
1. User selects Feature Config from dropdown
2. User selects Model Config from dropdown (determines architecture)
3. Training parameters (epochs, batch size, learning rate) auto-fill from ModelConfig
4. Click "Start Quick Test" to submit pipeline to Vertex AI
5. Monitor progress in real-time
6. View results when complete

---

## Overview

### Purpose
The Experiments domain allows users to:
1. **Run Quick Tests** to validate feature configurations on Vertex AI Pipelines
2. Compare Quick Test and Full Training results across configurations
3. Visualize metrics via heatmaps (Recall@k by configuration parameters)
4. Identify the best-performing configurations
5. Track experiment history and decisions

### Key Principle
**MLflow is for comparison and visualization, ML Metadata is for lineage.** Users use MLflow heatmaps to answer "which config is best?", while MLMD answers "what exact artifacts produced this model?".

### Terminology

| Term | Definition |
|------|------------|
| **Quick Test** | A lightweight training run (10% data, 2-3 epochs) for rapid validation |
| **Full Training** | Complete training run with all data and more epochs |
| **Feature Config** | Configuration of how columns are transformed (from Configs domain) |
| **Model Config** | Neural network architecture configuration (from Configs domain) |

### Tool Responsibilities

| Tool | Purpose |
|------|---------|
| **MLflow** | Experiment tracking, metrics comparison, heatmaps, parameter search visualization |
| **ML Metadata (MLMD)** | Artifact lineage, schema versions, vocabulary tracking, production model registry |

---

## Quick Test

### Overview

Quick Test runs a mini TFX pipeline on Vertex AI to validate feature configurations before committing to full training:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QUICK TEST PIPELINE                                  │
│                                                                              │
│   BigQuery     ExampleGen     Statistics    Schema      Transform           │
│   (10% sample) (TFRecords)    Gen          Gen         (vocabularies)       │
│       │            │             │            │             │               │
│       └────────────┴─────────────┴────────────┴─────────────┘               │
│                                        │                                     │
│                                        ↓                                     │
│                                    Trainer                                   │
│                               (2 epochs, no GPU)                             │
│                                        │                                     │
│                                        ↓                                     │
│                                   Metrics                                    │
│                              (Loss, Recall@k)                                │
│                                        │                                     │
│                                        ↓                                     │
│                                    MLflow                                    │
│                              (log experiment)                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test vs Full Training

| Aspect | Quick Test | Full Training |
|--------|------------|---------------|
| Data | 5-100% sample (configurable) | 100% data |
| ExampleGen | Sampled BigQuery | Full BigQuery |
| StatisticsGen/Transform | Dataflow (auto-scaling) | Dataflow (auto-scaling) |
| Trainer | CPU (configurable tiers) | GPU, 10-50 epochs |
| Hardware | Small/Medium/Large CPU tiers | GPU-enabled instances |
| Output | Temporary | Permanent artifacts |
| MLflow | Logged (tagged as quick test) | Logged (production) |

### Pipeline Integration

Full Vertex AI Pipeline integration for validating feature configurations:

**Backend:**
- `QuickTest` model in `ml_platform/models.py` - Tracks pipeline runs with status, progress, results
- `ml_platform/pipelines/` module - New sub-app for pipeline management:
  - `services.py` - PipelineService class for submission, polling, result extraction
  - `pipeline_builder.py` - KFP v2 pipeline with 6 components (ExampleGen, StatisticsGen, SchemaGen, Transform, Trainer, SaveMetrics)
  - `api.py` - 4 REST endpoints for start/status/cancel/list operations
- GCS buckets with lifecycle policies (7/30/3 days)
- IAM roles configured for `django-app` service account

**Pipeline Flow:**
```
FeatureConfig + ModelConfig → Dataset → BigQueryService.generate_query() → Vertex AI Pipeline → metrics.json → UI
```

### Quick Test API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/feature-configs/{id}/quick-test/` | Start quick test with configurable epochs, batch size, learning rate |
| GET | `/api/quick-tests/{id}/` | Get status and results (auto-polls Vertex AI) |
| POST | `/api/quick-tests/{id}/cancel/` | Cancel running pipeline |
| GET | `/api/feature-configs/{id}/quick-tests/` | List all tests for a config |

---

## User Interface

### Experiments Page Layout

The Experiments page has two main chapters:

1. **Quick Test Chapter** - Run and monitor validation tests
2. **Experiments Chapter** - Compare results via MLflow (future)

### Quick Test Chapter UI

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test                                                                   │
│ Validate your feature and model configurations before full training         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Configuration Selection                                                  │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │                                                                         │ │
│ │ Feature Config *                 Model Config *                         │ │
│ │ ┌─────────────────────────────┐  ┌─────────────────────────────┐      │ │
│ │ │ Q4 Features v2           ▼ │  │ Standard Two-Tower        ▼ │      │ │
│ │ └─────────────────────────────┘  └─────────────────────────────┘      │ │
│ │                                                                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Training Parameters                                                      │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │                                                                         │ │
│ │ Epochs           Batch Size        Learning Rate                        │ │
│ │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │ │
│ │ │ 3        ▼ │  │ 4096     ▼ │  │ 0.05        │                     │ │
│ │ └─────────────┘  └─────────────┘  └─────────────┘                     │ │
│ │                                                                         │ │
│ │ ⓘ Parameters auto-filled from selected Model Config                     │ │
│ │                                                                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                                              [▶ Start Quick Test]           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test Dialog

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test: Q4 Features v2 + Standard Two-Tower                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Quick Test Settings                                                          │
│                                                                              │
│ Data sample:    [10% ▼]    (options: 5%, 10%, 25%)                          │
│ Epochs:         [2 ▼]      (options: 1, 2, 3)                               │
│ Batch size:     [4096 ▼]   (options: 2048, 4096, 8192)                      │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│                                                                              │
│ Estimated:                                                                   │
│   Duration: ~8 minutes                                                       │
│   Cost: ~$1.50                                                               │
│                                                                              │
│ What Quick Test validates:                                                   │
│   ✓ Transform compiles successfully                                         │
│   ✓ Features have valid vocabularies                                        │
│   ✓ Model trains without errors                                             │
│   ✓ Basic metrics computed (loss, recall@10/50/100)                         │
│                                                                              │
│ ⚠️ Quick Test metrics are indicative only. Run Full Training for            │
│    production-ready results.                                                 │
│                                                                              │
│                                              [Cancel]  [▶ Start Quick Test] │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Hardware Configuration

The wizard includes hardware selection for configuring compute resources:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ Hardware Configuration                                                    │
│                                                                              │
│ CPU Options:                                                                 │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                        │
│ │ Small    ✓   │  │ Medium       │  │ Large        │                        │
│ │ 4 vCPU       │  │ 8 vCPU       │  │ 16 vCPU      │                        │
│ │ 15 GB RAM    │  │ 30 GB RAM    │  │ 60 GB RAM    │                        │
│ │ Recommended  │  │              │  │              │                        │
│ └──────────────┘  └──────────────┘  └──────────────┘                        │
│                                                                              │
│ GPU Options (coming soon):                                                   │
│ ┌──────────────┐  ┌──────────────┐                                          │
│ │ 🔒 T4        │  │ 🔒 A100      │                                          │
│ │ Coming Soon  │  │ Coming Soon  │                                          │
│ └──────────────┘  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Machine Type Tiers:**

| Tier | Machine Type | vCPU | Memory | Recommended For |
|------|--------------|------|--------|-----------------|
| Small | n1-standard-4 | 4 | 15 GB | Datasets < 100K rows |
| Medium | n1-standard-8 | 8 | 30 GB | Datasets 100K - 1M rows |
| Large | n1-standard-16 | 16 | 60 GB | Datasets > 1M rows |

**Auto-Recommendation:** The system automatically suggests hardware based on dataset size and model complexity.

**Dataflow Integration:** StatisticsGen and Transform components always use Dataflow with the selected machine type for worker nodes. This ensures scalable processing for large datasets.

### Quick Test Progress

**Stage Progress Bar (Updated December 2025):**

Each experiment card shows a 6-stage progress bar with color-coded status:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Experiment #7 - Running                                    [Cancel]          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ [Compile ✓] [Examples ✓] [Stats ✓] [Schema ●] [Transform ○] [Train ○]       │
│   green       green       green     orange      grey         grey            │
│                                                                              │
│ Current: Schema (analyzing statistics)                                       │
│                                                                              │
│ Feature: My Feature Config                                                   │
│ Model: Standard Two-Tower                                                    │
│ Split: Random (80/20)  Sample: 25%  Hardware: Medium                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Stage Statuses:**
| Color | Icon | Status | Description |
|-------|------|--------|-------------|
| Grey | ○ | Pending | Stage not yet started |
| Orange | ● | Running | Stage currently executing |
| Green | ✓ | Success | Stage completed successfully |
| Red | ✗ | Failed | Stage failed with error |

**Pipeline Stages:**
| Stage | TFX Component | Description |
|-------|---------------|-------------|
| Compile | Cloud Build | Compile TFX pipeline and submit to Vertex AI |
| Examples | BigQueryExampleGen | Extract data from BigQuery to TFRecords |
| Stats | StatisticsGen | Compute dataset statistics using TFDV |
| Schema | SchemaGen | Infer schema from statistics |
| Transform | Transform | Apply preprocessing_fn, generate vocabularies |
| Train | Trainer | Train TFRS two-tower model |

**Legacy Progress View (for reference):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test Running: Q4 Features v2                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────┐    │
│ │ ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 45%       │    │
│ └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│ Current Stage: Transform (generating vocabularies)                           │
│                                                                              │
│ ✅ ExampleGen        - Completed (2 min)                                     │
│ ✅ StatisticsGen     - Completed (1 min)                                     │
│ ✅ SchemaGen         - Completed (10 sec)                                    │
│ 🔄 Transform         - Running... (3 min elapsed)                            │
│ ⏳ Trainer           - Pending                                               │
│                                                                              │
│ Elapsed: 6 min 10 sec                                                        │
│ Estimated remaining: ~5 min                                                  │
│                                                                              │
│                                                              [Cancel Test]   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test Results

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test Results: Q4 Features v2                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Status: ✅ Success                                                           │
│ Duration: 8 min 23 sec                                                       │
│ Cost: $1.42                                                                  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ METRICS (indicative - 10% sample, 2 epochs)                                  │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────┬────────────┬────────────────────────────────────────┐    │
│ │ Metric         │ Value      │ vs Previous Best (config-038)          │    │
│ ├────────────────┼────────────┼────────────────────────────────────────┤    │
│ │ Loss           │ 0.38       │ ↓ 0.04 (was 0.42)                      │    │
│ │ Recall@10      │ 18.2%      │ ↑ 0.4% (was 17.8%)                     │    │
│ │ Recall@50      │ 38.5%      │ ↑ 1.2% (was 37.3%)                     │    │
│ │ Recall@100     │ 47.3%      │ ↑ 1.2% (was 46.1%)                     │    │
│ └────────────────┴────────────┴────────────────────────────────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ VOCABULARY STATS                                                             │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────┬────────────┬────────────┬───────────────────────────┐    │
│ │ Feature        │ Vocab Size │ OOV Rate   │ Status                    │    │
│ ├────────────────┼────────────┼────────────┼───────────────────────────┤    │
│ │ user_id        │ 9,823      │ 1.2%       │ ✅ Good                   │    │
│ │ product_id     │ 3,612      │ 0.8%       │ ✅ Good                   │    │
│ │ city           │ 28         │ 0%         │ ✅ Good                   │    │
│ │ product_name   │ 3,421      │ 2.1%       │ ✅ Good                   │    │
│ │ category       │ 12         │ 0%         │ ✅ Good                   │    │
│ │ subcategory    │ 142        │ 0.3%       │ ✅ Good                   │    │
│ └────────────────┴────────────┴────────────┴───────────────────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ WARNINGS                                                                     │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ (none)                                                                       │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ 🎉 This config shows improvement over previous best!                         │
│                                                                              │
│ [View in MLflow]  [Modify & Re-test]  [▶ Run Full Training]  [Close]        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## MLflow Experiment Comparison

### Experiments Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Experiments                                                                  │
│ Dataset: Q4 2024 Training Data                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ SUMMARY                                                                      │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│ │ Quick Tests  │  │ Full Trains  │  │ Best R@100   │  │ Currently    │     │
│ │     12       │  │      4       │  │    47.3%     │  │  Deployed    │     │
│ │              │  │              │  │  config-042  │  │   46.2%      │     │
│ └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ HEATMAP: Recall@100 by Configuration                                         │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Group X: [Embedding Dims ▼]  Group Y: [Cross Features ▼]  Show: [All ▼]     │
│                                                                              │
│                    │ user:32  │ user:64  │ user:64  │ user:128 │           │
│                    │ prod:32  │ prod:32  │ prod:64  │ prod:64  │           │
│ ───────────────────┼──────────┼──────────┼──────────┼──────────┤           │
│ No crosses         │  38.2%   │  41.5%   │  44.1%   │  44.8%   │           │
│                    │   ██     │   ███    │   ████   │   ████   │           │
│ ───────────────────┼──────────┼──────────┼──────────┼──────────┤           │
│ cat × subcat       │  39.1%   │  42.8%   │  45.9%   │  46.2%   │           │
│                    │   ██     │   ███    │  █████   │  █████   │           │
│ ───────────────────┼──────────┼──────────┼──────────┼──────────┤           │
│ + user × city      │  38.5%   │  43.1%   │ ★47.3%   │  46.9%   │           │
│                    │   ██     │   ███    │  █████   │  █████   │           │
│                                                                              │
│ ★ Best | ● Deployed | Legend: █████ >46% ████ 44-46% ███ 42-44% ██ <42%    │
│                                                                              │
│ [Export Heatmap]  [View as Table]  [Change Metric]                          │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ RECENT EXPERIMENTS                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-042 • Quick Test #3                              47.3% R@100   │  │
│ │ 2 hours ago | 8 min | $1.42 | user:64d prod:64d +crosses              │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-042 • Full Training #46                          46.8% R@100   │  │
│ │ 5 hours ago | 3h 42m | $38.50 | Promoted for deployment               │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-044 • Quick Test #1                                   Failed   │  │
│ │ 1 day ago | OOM during Transform | user:256d (too large)              │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ [View All in MLflow]                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Experiment Comparison View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Compare Experiments                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Selected: config-042 (Quick Test #3) vs config-038 (Full Training #45)      │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ METRICS COMPARISON                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────┬───────────────────┬───────────────────┬────────────┐    │
│ │ Metric          │ config-042        │ config-038        │ Diff       │    │
│ │                 │ (Quick Test)      │ (Full Train)      │            │    │
│ ├─────────────────┼───────────────────┼───────────────────┼────────────┤    │
│ │ Loss            │ 0.38              │ 0.32              │ -0.06      │    │
│ │ Recall@10       │ 18.2%             │ 17.5%             │ +0.7%      │    │
│ │ Recall@50       │ 38.5%             │ 37.8%             │ +0.7%      │    │
│ │ Recall@100      │ 47.3%             │ 46.1%             │ +1.2%      │    │
│ │ Duration        │ 8 min             │ 2h 58m            │ -          │    │
│ │ Cost            │ $1.42             │ $32.10            │ -          │    │
│ └─────────────────┴───────────────────┴───────────────────┴────────────┘    │
│                                                                              │
│ ⚠️ Note: Quick Test metrics are indicative (10% data, 2 epochs)             │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ CONFIGURATION DIFF                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Query Tower                                                             │ │
│ │   user_id:  64d  →  64d   (same)                                        │ │
│ │   city:     16d  →  16d   (same)                                        │ │
│ │                                                                         │ │
│ │ Candidate Tower                                                         │ │
│ │   product_id:    64d  →  64d   (same)                                   │ │
│ │   product_name:  32d  →  32d   (same)                                   │ │
│ │   category:      16d  →  16d   (same)                                   │ │
│ │   subcategory:   16d  →  16d   (same)                                   │ │
│ │                                                                         │ │
│ │ Cross Features                                                          │ │
│ │ + user_id × city (5000 buckets)     ← NEW in config-042                 │ │
│ │   category × subcategory (1000)     (same)                              │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ RECOMMENDATION                                                               │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ 💡 config-042 shows +1.2% improvement in Recall@100.                        │
│    Consider running Full Training with config-042 to confirm.               │
│                                                                              │
│ [▶ Run Full Training with config-042]  [Add More to Compare]  [Close]       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MLflow Integration View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MLflow Experiments                                          [Open MLflow ↗] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Experiment: Q4-2024-Training-Data                                           │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ RUNS TABLE                                                                   │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Filter: [All Types ▼]  Sort: [Recall@100 DESC ▼]  Search: [_________]       │
│                                                                              │
│ ┌───┬────────────┬─────────┬──────────┬──────────┬───────────┬───────────┐  │
│ │   │ Run Name   │ Type    │ R@100    │ R@50     │ Duration  │ Date      │  │
│ ├───┼────────────┼─────────┼──────────┼──────────┼───────────┼───────────┤  │
│ │ ☑ │ config-042 │ Quick   │ 47.3%    │ 38.5%    │ 8m        │ 2h ago    │  │
│ │ ☑ │ run-46     │ Full    │ 46.8%    │ 39.2%    │ 3h 42m    │ 5h ago    │  │
│ │ ☐ │ config-038 │ Quick   │ 46.1%    │ 37.3%    │ 7m        │ 1d ago    │  │
│ │ ☐ │ run-45     │ Full    │ 45.2%    │ 36.8%    │ 2h 58m    │ 3d ago    │  │
│ │ ☐ │ config-035 │ Quick   │ 42.0%    │ 33.1%    │ 5m        │ 5d ago    │  │
│ └───┴────────────┴─────────┴──────────┴──────────┴───────────┴───────────┘  │
│                                                                              │
│ [Compare Selected]  [Export CSV]                                            │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ PARALLEL COORDINATES                                                         │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│   user_emb    prod_emb   crosses    revenue_buckets   R@100                 │
│      │           │          │              │            │                    │
│     32          32         none           5         ────┼──── 42%            │
│      │           │          │              │            │                    │
│     64 ─────────32         one ──────────10 ───────────┼──── 45%            │
│      │           │          │              │            │                    │
│     64 ─────────64 ────────two ──────────10 ───────────┼──── 47%            │
│      │           │          │              │            │                    │
│    128          64         two           10         ────┼──── 47%            │
│                                                                              │
│ [Change Axes]  [Filter Runs]                                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### MLflow Experiment Structure

```
MLflow Experiment: "{model_name}-{dataset_name}"
│
├── Run: quick-test-{config_id}-{timestamp}
│   ├── Parameters:
│   │   ├── run_type: "quick_test"
│   │   ├── config_id: "config-042"
│   │   ├── data_sample_percent: 10
│   │   ├── epochs: 2
│   │   ├── user_id_embedding_dim: 64
│   │   ├── product_id_embedding_dim: 64
│   │   ├── cross_features: "category_x_subcategory,user_id_x_city"
│   │   └── ...
│   ├── Metrics:
│   │   ├── loss: 0.38
│   │   ├── recall_at_10: 0.182
│   │   ├── recall_at_50: 0.385
│   │   └── recall_at_100: 0.473
│   └── Tags:
│       ├── dataset_id: "dataset-001"
│       ├── feature_config_id: "config-042"
│       └── mlflow.runName: "config-042 Quick Test #3"
│
├── Run: full-training-{run_number}-{timestamp}
│   ├── Parameters:
│   │   ├── run_type: "full_training"
│   │   ├── training_run_id: 46
│   │   ├── epochs: 20
│   │   ├── batch_size: 8192
│   │   └── ...
│   ├── Metrics:
│   │   ├── final_loss: 0.28
│   │   ├── recall_at_100: 0.468
│   │   └── epoch_*: {...}  # per-epoch metrics
│   ├── Artifacts:
│   │   ├── model/  # link to GCS
│   │   └── training_curves.png
│   └── Tags:
│       ├── dataset_version: "3"
│       ├── is_deployed: "true"
│       └── ...
```

### Django Models (Lightweight)

Most experiment data lives in MLflow. Django stores minimal reference data:

```python
# ml_platform/models.py

class ExperimentComparison(models.Model):
    """
    Saved comparison for reference.
    """
    name = models.CharField(max_length=255)
    ml_model = models.ForeignKey('MLModel', on_delete=models.CASCADE)

    # MLflow run IDs being compared
    mlflow_run_ids = models.JSONField(default=list)

    # Notes
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
```

---

## API Endpoints

### Experiments API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{model_id}/experiments/` | Get experiments summary |
| GET | `/api/models/{model_id}/experiments/heatmap/` | Get heatmap data |
| GET | `/api/models/{model_id}/experiments/runs/` | List all MLflow runs |
| POST | `/api/experiments/compare/` | Compare multiple runs |
| GET | `/api/experiments/mlflow-url/` | Get MLflow UI URL |

### Heatmap Data Endpoint

**GET /api/models/{model_id}/experiments/heatmap/**

Query parameters:
- `metric`: `recall_at_100` (default), `recall_at_50`, `recall_at_10`, `loss`
- `x_axis`: `embedding_dims`, `cross_features`, `epochs`
- `y_axis`: `embedding_dims`, `cross_features`, `epochs`
- `run_type`: `all`, `quick_test`, `full_training`

Response:
```json
{
  "status": "success",
  "data": {
    "metric": "recall_at_100",
    "x_axis": {
      "name": "embedding_dims",
      "values": ["32/32", "64/32", "64/64", "128/64"]
    },
    "y_axis": {
      "name": "cross_features",
      "values": ["none", "cat×subcat", "+user×city"]
    },
    "cells": [
      {"x": "32/32", "y": "none", "value": 0.382, "run_id": "abc123"},
      {"x": "64/32", "y": "none", "value": 0.415, "run_id": "def456"},
      ...
    ],
    "best": {"x": "64/64", "y": "+user×city", "value": 0.473, "run_id": "ghi789"}
  }
}
```

---

## Services

### MLflow Integration Service

```python
# ml_platform/experiments/services.py

import mlflow
from mlflow.tracking import MlflowClient

class MLflowService:
    """
    Manages MLflow experiment tracking and visualization.
    """

    def __init__(self, tracking_uri: str):
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient()

    def get_or_create_experiment(self, name: str) -> str:
        """Get or create MLflow experiment, return experiment_id."""
        experiment = self.client.get_experiment_by_name(name)
        if experiment:
            return experiment.experiment_id
        return self.client.create_experiment(name)

    def log_quick_test(
        self,
        quick_test: 'QuickTest',
        feature_config: 'FeatureConfig',
        dataset: 'Dataset'
    ):
        """Log quick test results to MLflow."""
        experiment_id = self.get_or_create_experiment(
            f"{dataset.ml_model.name}-{dataset.name}"
        )

        with mlflow.start_run(experiment_id=experiment_id) as run:
            # Log parameters
            mlflow.log_param("run_type", "quick_test")
            mlflow.log_param("config_id", feature_config.id)
            mlflow.log_param("data_sample_percent", quick_test.data_sample_percent)
            mlflow.log_param("epochs", quick_test.epochs)

            # Log feature config parameters
            for feature in feature_config.query_tower:
                mlflow.log_param(f"{feature['name']}_embedding_dim", feature['embedding_dim'])
            for feature in feature_config.candidate_tower:
                mlflow.log_param(f"{feature['name']}_embedding_dim", feature['embedding_dim'])

            # Log cross features
            cross_names = [
                "_x_".join(cf['features'])
                for cf in feature_config.cross_features
            ]
            mlflow.log_param("cross_features", ",".join(cross_names) or "none")

            # Log metrics
            mlflow.log_metric("loss", quick_test.loss)
            mlflow.log_metric("recall_at_10", quick_test.recall_at_10)
            mlflow.log_metric("recall_at_50", quick_test.recall_at_50)
            mlflow.log_metric("recall_at_100", quick_test.recall_at_100)

            # Set tags
            mlflow.set_tag("dataset_id", dataset.id)
            mlflow.set_tag("feature_config_id", feature_config.id)
            mlflow.set_tag("mlflow.runName", f"{feature_config.name} Quick Test #{quick_test.id}")

            return run.info.run_id

    def log_training_run(
        self,
        training_run: 'TrainingRun',
        feature_config: 'FeatureConfig',
        dataset: 'Dataset'
    ):
        """Log full training results to MLflow."""
        # Similar to quick test, but with more parameters and artifacts
        pass

    def get_heatmap_data(
        self,
        experiment_name: str,
        metric: str,
        x_axis: str,
        y_axis: str,
        run_type: str = 'all'
    ) -> dict:
        """
        Generate heatmap data from MLflow runs.
        """
        experiment = self.client.get_experiment_by_name(experiment_name)
        if not experiment:
            return {"cells": [], "best": None}

        # Query runs
        filter_string = ""
        if run_type != 'all':
            filter_string = f"params.run_type = '{run_type}'"

        runs = self.client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=filter_string,
        )

        # Group runs by x/y axes
        # Implementation depends on axis types
        pass

    def compare_runs(self, run_ids: list) -> dict:
        """
        Compare multiple MLflow runs.
        Returns metrics and parameter diffs.
        """
        runs = [self.client.get_run(run_id) for run_id in run_ids]

        comparison = {
            "runs": [],
            "metrics": {},
            "params_diff": {},
        }

        for run in runs:
            comparison["runs"].append({
                "run_id": run.info.run_id,
                "name": run.data.tags.get("mlflow.runName", run.info.run_id),
                "metrics": run.data.metrics,
                "params": run.data.params,
            })

        # Calculate diffs
        # ...

        return comparison
```

### Heatmap Generation Service

```python
# ml_platform/experiments/services.py

class HeatmapService:
    """
    Generates heatmap visualizations from experiment data.
    """

    def __init__(self, mlflow_service: MLflowService):
        self.mlflow = mlflow_service

    def generate_heatmap_data(
        self,
        experiment_name: str,
        metric: str = 'recall_at_100',
        x_axis: str = 'embedding_dims',
        y_axis: str = 'cross_features',
    ) -> dict:
        """
        Generate heatmap data structure for frontend visualization.
        """
        runs = self.mlflow.get_runs(experiment_name)

        # Extract axis values
        x_values = self._extract_axis_values(runs, x_axis)
        y_values = self._extract_axis_values(runs, y_axis)

        # Build cell data
        cells = []
        best = None
        best_value = -1

        for run in runs:
            x_val = self._get_axis_value(run, x_axis)
            y_val = self._get_axis_value(run, y_axis)
            metric_val = run.data.metrics.get(metric)

            if metric_val is not None:
                cell = {
                    "x": x_val,
                    "y": y_val,
                    "value": metric_val,
                    "run_id": run.info.run_id,
                    "run_name": run.data.tags.get("mlflow.runName"),
                }
                cells.append(cell)

                if metric_val > best_value:
                    best_value = metric_val
                    best = cell

        return {
            "metric": metric,
            "x_axis": {"name": x_axis, "values": sorted(x_values)},
            "y_axis": {"name": y_axis, "values": sorted(y_values)},
            "cells": cells,
            "best": best,
        }

    def _extract_axis_values(self, runs, axis_type: str) -> set:
        """Extract unique values for an axis type."""
        values = set()
        for run in runs:
            val = self._get_axis_value(run, axis_type)
            if val:
                values.add(val)
        return values

    def _get_axis_value(self, run, axis_type: str):
        """Get the axis value for a specific run."""
        if axis_type == 'embedding_dims':
            user_dim = run.data.params.get('user_id_embedding_dim', '?')
            prod_dim = run.data.params.get('product_id_embedding_dim', '?')
            return f"{user_dim}/{prod_dim}"
        elif axis_type == 'cross_features':
            return run.data.params.get('cross_features', 'none')
        elif axis_type == 'epochs':
            return run.data.params.get('epochs', '?')
        else:
            return run.data.params.get(axis_type)
```

---

## MLflow Server Setup

### Cloud Run Deployment

MLflow server runs as a Cloud Run service per client project:

```yaml
# mlflow-server/cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/mlflow-server', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/mlflow-server']
```

```dockerfile
# mlflow-server/Dockerfile
FROM python:3.10-slim

RUN pip install mlflow psycopg2-binary google-cloud-storage

EXPOSE 5000

CMD ["mlflow", "server", \
     "--backend-store-uri", "postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}/${DB_NAME}", \
     "--default-artifact-root", "gs://${GCS_BUCKET}/mlflow-artifacts", \
     "--host", "0.0.0.0", \
     "--port", "5000"]
```

### Configuration

```python
# Django settings
MLFLOW_TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', 'http://mlflow-server:5000')
```

---

## Implementation Checklist

> **Note:** Detailed implementation steps are in [phase_experiments_implementation.md](phase_experiments_implementation.md)

### Phase 1: TFX Pipeline Infrastructure ✅ DONE
- [x] Install TFX dependencies (`tfx>=1.14.0`)
- [x] Create `ml_platform/pipelines/tfx_pipeline.py` - Native TFX pipeline
- [x] Implement `create_quicktest_pipeline()` function
- [x] Implement `compile_pipeline_for_vertex()` function
- [x] Update `pipeline_builder.py` to use TFX (remove KFP v2 placeholders)
- [x] Update `services.py` for TFX pipeline submission
- [x] Test pipeline compilation
- [x] Test pipeline execution on Vertex AI

### Phase 2: Trainer Module Generator Rebuild ✅ DONE
- [x] Rebuild `TrainerModuleGenerator` in `configs/services.py`
- [x] Generate proper `run_fn()` entry point
- [x] Generate BuyerModel class from FeatureConfig
- [x] Generate ProductModel class from FeatureConfig
- [x] Apply tower layers from ModelConfig
- [x] Implement metrics export to GCS
- [x] Validate generated code compiles

### Phase 3: Experiment Parameters & Submission ✅ DONE
- [x] Add new fields to `QuickTest` model:
  - `sample_percent` (5, 10, 25, 100)
  - `split_strategy` (random, time_holdout, strict_time)
  - `date_column` (for time-based strategies)
  - `holdout_days` (for time_holdout)
  - `train_days`, `val_days`, `test_days` (for strict_time)
- [x] Update API endpoint to accept new parameters
- [x] Update UI to show parameter configuration with dynamic defaults
- [x] Implement sampling in SQL query
- [x] Implement split configuration in ExampleGen:
  - `random`: Hash-based 80/20 split
  - `time_holdout`: Date-filtered + hash-based 80/20 split
  - `strict_time`: True temporal split using SQL `split` column + `partition_feature_name`

### Phase 4: Pipeline Visualization UI ✅ DONE
- [x] Create pipeline DAG component (like Vertex AI console)
- [x] Add real-time stage status updates
- [x] Show stage icons (✅ completed, 🔄 running, ⏳ pending)
- [x] Add artifact boxes between stages
- [x] Style to match screenshot reference

### Phase 5: Metrics Collection & Display 🔴 TODO
- [ ] Collect all available metrics per epoch
- [ ] Export `epoch_metrics.json` from Trainer
- [ ] Build epoch metrics chart (Chart.js)
- [ ] Build comparison table (sortable, filterable)

### Phase 6: MLflow Integration 🔴 TODO
- [ ] Deploy MLflow server to Cloud Run
  - [ ] Create `mlflow-server/Dockerfile`
  - [ ] Create `mlflow-server/cloudbuild.yaml`
  - [ ] Deploy and verify server accessible
- [ ] Set up Cloud SQL for MLflow backend store
  - [ ] Create PostgreSQL database
  - [ ] Configure connection from Cloud Run
- [ ] Create GCS bucket for MLflow artifacts
- [ ] Django MLflow integration:
  - [ ] Add `MLFLOW_TRACKING_URI` to settings
  - [ ] Create `ml_platform/experiments/services.py` (MLflowService)
  - [ ] Create `ml_platform/experiments/api.py` (endpoints)
  - [ ] Add `mlflow_run_id` field to QuickTest model
- [ ] Update pipeline completion to log to MLflow
- [ ] API endpoints:
  - [ ] GET `/api/experiments/{model_endpoint_id}/{dataset_id}/runs/`
  - [ ] GET `/api/experiments/{model_endpoint_id}/{dataset_id}/heatmap/`
  - [ ] POST `/api/experiments/compare/`
  - [ ] GET `/api/experiments/mlflow-url/`
- [ ] UI integration:
  - [ ] Add "Open MLflow UI" button
  - [ ] Runs table with sorting/filtering
  - [ ] Heatmap visualization
  - [ ] Run comparison view

### Phase 7: Pre-built TFX Compiler Image ✅ DONE (2025-12-15)
> **Critical for Quick Test performance** - Reduces compilation from 12-15 min to 1-2 min

- [x] Create Dockerfile for TFX compiler (`cloudbuild/tfx-builder/Dockerfile`)
- [x] Build and push to Artifact Registry:
  - `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest`
  - `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:v1.0.0`
- [x] Update `services.py` to use pre-built image instead of `python:3.10`
- [x] Add `TFX_COMPILER_IMAGE` to Django settings (configurable)
- [x] Create `cloudbuild/tfx-builder/cloudbuild.yaml` for rebuilding image
- [x] Create `cloudbuild/tfx-builder/README.md` with setup documentation
- [x] Verify image works (TFX 1.15.0, KFP 2.15.2)

**Current Setup (Development):**
- Image hosted in `b2b-recs` project (same as dev environment)
- For production multi-tenant: migrate to `b2b-recs-platform` project
- See [Phase 7 in implementation guide](phase_experiments_implementation.md#phase-7-pre-built-docker-image-for-fast-cloud-build)

### Phase 8: TFX Trainer Bug Fixes ✅ DONE (2025-12-16)
> **Critical bug fixes** - Fixed 5 issues preventing successful Trainer execution and model saving

- [x] **Embedding shape fix**: Changed `tf.reshape(f, [tf.shape(f)[0], -1])` to `tf.squeeze(f, axis=1)` to preserve static shapes
- [x] **Infinite dataset fix**: Added `num_epochs=1` to `TensorFlowDatasetOptions` in `_input_fn`
- [x] **StringLookup removal**: Removed redundant `StringLookup` layer (Transform already provides vocab indices)
- [x] **FactorizedTopK removal**: Removed stateful metrics that caused serialization issues during training
- [x] **ServingModel class**: Created proper wrapper class to track TFT resources for model saving
- [x] **NUM_OOV_BUCKETS constant**: Added to trainer module to match Transform preprocessing

**Result:** Pipeline now completes successfully: BigQueryExampleGen → StatisticsGen → SchemaGen → Transform → Trainer → Model Saved

### Phase 12: Pipeline Progress Bar & Error Improvements ✅ DONE (2025-12-18)
> **Visual progress tracking and better error handling**

- [x] **Stage progress bar**: 6-stage visual progress bar (Compile, Examples, Stats, Schema, Transform, Train)
- [x] **Color-coded status**: Grey (pending), orange (running), green (success), red (failed)
- [x] **Async Cloud Build**: Wizard closes immediately, status polled in background
- [x] **Cloud Build tracking**: Added `cloud_build_id` and `cloud_build_run_id` fields to QuickTest
- [x] **Column validation**: Validates FeatureConfig columns match BigQuery output before pipeline submission
- [x] **Duplicate column fix**: Fixed `generate_query()` to handle duplicate columns consistently
- [x] **Helpful error messages**: Column mismatch errors include suggestions for correct column names

**Result:** Users see real-time pipeline progress and get actionable error messages when column names don't match.

### Phase 13: Experiment Cards Redesign & Cancel ✅ DONE (2025-12-19)
> **Improved card layout and cancel functionality**

- [x] **4-column layout**: Exp info (30%), Config (20%), Params placeholder (30%), Actions (20%)
- [x] **Experiment name/description**: Optional fields in New Experiment wizard Step 1
- [x] **Cancel button**: Active for running experiments, disabled for others
- [x] **Progress bar styling**: Tensor-breakdown-bar with gradient green colors
- [x] **Styled confirmation**: Cancel uses styled modal instead of browser confirm()

**Result:** Experiment cards show more information in organized columns with cancel functionality.

### Phase 14: Experiment View Modal ✅ DONE (2025-12-19)
> **Comprehensive experiment details modal**

- [x] **View modal**: Full experiment details (config, params, progress, results, technical details)
- [x] **View button**: Green button on cards, opens View modal
- [x] **Real-time polling**: View modal updates every 10s for running experiments
- [x] **Code cleanup**: Removed old progress/results modals and unused functions
- [x] **Unified logging**: Backend logs use `{display_name} (id={id})` format
- [x] **Wizard scroll fix**: Step 2 now opens scrolled to top

**Result:** Users can view comprehensive experiment details without leaving the page.

### Phase 15: View Modal Redesign with Tabs & Artifacts ✅ DONE (2025-12-19)
> **Tabbed modal with artifact viewing and smart error handling**

- [x] **4-tab layout**: Overview, Pipeline, Data Insights, Training tabs
- [x] **Error pattern matching**: 15+ patterns with user-friendly titles and fix suggestions
- [x] **Artifact service**: Backend service to parse GCS statistics and schema
- [x] **Lazy loading**: Artifact data fetched on tab switch (not on modal open)
- [x] **Statistics display**: Feature count, missing %, min/max/mean values
- [x] **Schema display**: Feature names, types, required/optional
- [x] **Hidden GCP details**: Removed Vertex AI links and GCS paths from user view
- [x] **Training placeholder**: Ready for future MLflow integration

**Result:** Users see clean tabbed interface with actionable error messages and artifact visibility.

### Phase 17: Pipeline DAG Visualization ✅ DONE (2025-12-20)
> **Visual pipeline graph with component logs**

- [x] **Vertical DAG layout**: 4-row pipeline visualization (Examples → Stats/Schema → Transform → Train)
- [x] **SVG connections**: Bezier curve connections between components
- [x] **Clickable components**: Click to view component logs
- [x] **Cloud Logging integration**: Fetch logs via `google-cloud-logging` client
- [x] **Task job ID extraction**: Parse Vertex AI task details for `container_detail.main_job`
- [x] **Logs API endpoint**: `GET /api/quick-tests/{id}/logs/{component}/`
- [x] **Refresh functionality**: Refresh button to fetch latest logs
- [x] **7-day lookback**: Timestamp filter for accessing older experiment logs

**Result:** Users see visual pipeline DAG and can inspect component execution logs without GCP access.

### Previously Completed ✅
- [x] Create `model_experiments.html` page (placeholder)
- [x] Feature Config dropdown
- [x] Model Config dropdown
- [x] Training parameters panel
- [x] QuickTest Django model
- [x] `ml_platform/pipelines/` sub-app structure
- [x] PipelineService class (needs update for TFX)
- [x] API endpoints (need parameter updates)
- [x] GCS bucket lifecycle policies

### Future Phases (Not in Scope)
- [ ] Ranking Models
- [ ] Multitask Models
- [ ] Hyperparameter Tuning (Vertex AI Vizier)

---

## Dependencies on Other Domains

### Depends On
- **Configs Domain**: Feature Configs (feature engineering specifications) and Model Configs (neural network architecture)
- **Datasets Domain**: Dataset definitions for training data
- **Training Domain**: Full Training results (future)

### Depended On By
- **Deployment Domain**: Best model selection for deployment

---

## Related Documentation

- [Implementation Overview](../implementation.md)
- [Configs Phase](phase_configs.md)
- [Training Phase](phase_training.md)
- [Deployment Phase](phase_deployment.md)
