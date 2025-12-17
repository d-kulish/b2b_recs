# Phase: Experiments Implementation Guide

## Document Purpose
This document provides a **complete implementation guide** for building the Experiments domain with native TFX pipelines on Vertex AI. It is designed to be self-contained and actionable - you should be able to open this document and start implementing without additional context.

**Last Updated**: 2025-12-17

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Implementation Status](#implementation-status)
3. [Architecture Overview](#architecture-overview)
4. [Technical Decisions](#technical-decisions)
5. [Implementation Plan](#implementation-plan)
6. [Phase 1: TFX Pipeline Infrastructure](#phase-1-tfx-pipeline-infrastructure)
7. [Phase 2: Trainer Module Generator Rebuild](#phase-2-trainer-module-generator-rebuild)
8. [Phase 3: Experiment Parameters & Submission](#phase-3-experiment-parameters--submission)
9. [Phase 4: Pipeline Visualization UI](#phase-4-pipeline-visualization-ui)
10. [Phase 5: Metrics Collection & Display](#phase-5-metrics-collection--display)
11. [Phase 6: MLflow Integration](#phase-6-mlflow-integration)
12. [Phase 7: Pre-built Docker Image](#phase-7-pre-built-docker-image-for-fast-cloud-build)
13. [Phase 8: TFX Pipeline Bug Fixes](#phase-8-tfx-pipeline-bug-fixes-december-2025)
14. [Phase 9: Experiments UI Refactor](#phase-9-experiments-ui-refactor-december-2025)
15. [File Reference](#file-reference)
16. [API Reference](#api-reference)
17. [Testing Guide](#testing-guide)

---

## Executive Summary

### What We're Building

The **Experiments Domain** enables users to:
1. **Run Quick Tests** - Submit TFX pipelines to Vertex AI with specific (Dataset + FeatureConfig + ModelConfig) combinations
2. **Analyze Results** - View, compare, and identify the best parameter combinations on the Experiments page
3. **Find Optimal Configs** - Determine which configuration produces the highest accuracy for full-scale GPU training

### Key Concept

```
Quick Test = Submit pipeline with specific configuration
Experiments Page = Analyze Quick Test results to find optimal parameters
```

**Goal**: Find the best (Dataset + FeatureConfig + ModelConfig) combination, NOT to deploy models from Quick Tests.

### Technical Stack

| Component | Technology |
|-----------|------------|
| Pipeline Framework | **Native TFX SDK** compiled for Vertex AI |
| Data Flow | BigQuery → TFRecords → TFX Components |
| Container Image | `gcr.io/tfx-oss-public/tfx:latest` (standard) |
| Model Type | Retrieval only (Ranking/Multitask later) |
| Experiment Tracking | **MLflow** (self-hosted on Cloud Run) |
| Metrics Visualization | MLflow UI + Custom charts |
| Pipeline Compilation | On-demand at submission time |

---

## Implementation Status

**Current Status**: ✅ **TFX pipelines fully working on Vertex AI!** Complete end-to-end execution: BigQueryExampleGen → StatisticsGen → SchemaGen → Transform → Trainer → Model Saved. Pipeline trains TFRS two-tower retrieval model and exports SavedModel with serving signature.

### Completed Phases

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 0** | ✅ Complete | GCP Infrastructure verification (buckets, IAM, region) |
| **Phase 1** | ✅ Complete | TFX Pipeline Infrastructure (native TFX, Cloud Build compilation, Vertex AI submission) |
| **Phase 2** | ✅ Complete | Trainer Module Generator (existing code works, minor f-string bug fixes) |
| **Phase 3** | ✅ Complete | Experiment Parameters & Submission (API endpoints, split strategies, sampling) |
| **Phase 4** | ✅ Complete | Pipeline Visualization UI (Quick Test dialog, status polling, results display) |
| **Phase 5** | 🔲 Pending | Metrics Collection & Display (per-epoch charts, comparison table) |
| **Phase 6** | 🔲 Pending | MLflow Integration (experiment tracking, heatmaps, comparison) |
| **Phase 7** | ✅ Complete | Pre-built Docker Image for fast Cloud Build execution |
| **Phase 8** | ✅ Complete | TFX Pipeline Bug Fixes (embedding shapes, dataset serialization, model saving) |
| **Phase 9** | ✅ Complete | Experiments UI Refactor (new chapter layout, wizard modal, experiment cards, pagination) |

### Cloud Build Implementation (December 2025)

#### Why Cloud Build?

**Problem**: TFX requires Python 3.9-3.10, but the Django application runs on Python 3.13 (to maintain long-term support). TFX cannot be installed in the Django venv.

**Solution**: Use Google Cloud Build to compile TFX pipelines in a Python 3.10 container, then submit the compiled JSON spec to Vertex AI Pipelines.

#### Current Architecture

```
Django (Python 3.13)
    │
    ├── 1. Generate transform_module.py and trainer_module.py
    ├── 2. Upload modules to GCS
    ├── 3. Trigger Cloud Build with parameters
    │
    └── Cloud Build (pre-built TFX image)
            │
            ├── 4. Download compile script from GCS (dependencies pre-installed)
            ├── 5. Create TFX pipeline (BigQueryExampleGen → StatisticsGen → SchemaGen → Transform → Trainer)
            ├── 6. Compile to JSON using kubeflow_v2_dag_runner
            ├── 7. Submit to Vertex AI Pipelines
            └── 8. Write result to GCS for Django to read
```

#### Pre-built Docker Image

- **Image**: `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest`
- **Location**: Artifact Registry (europe-central2)
- **Contents**: Python 3.10 + TFX 1.15.0 + KFP 2.4.0 + google-cloud-aiplatform + google-cloud-storage
- **Build Time**: ~1-2 minutes (down from 12-15 minutes with vanilla python:3.10)

#### Files for Cloud Build

| File | Description |
|------|-------------|
| `ml_platform/experiments/services.py` | `_trigger_cloud_build()` - triggers build, `_get_compile_script()` - embedded Python script |
| `cloudbuild/compile_and_submit.py` | Standalone script (reference, embedded version used) |
| `cloudbuild/tfx-compile.yaml` | Cloud Build config (reference, programmatic API used) |

#### Key Implementation Details

1. **BigQuery Query Encoding**: Base64-encoded to avoid shell escaping issues with backticks and special characters
2. **Script Upload**: Compile script uploaded to GCS first (Cloud Build arg limit is 10,000 chars)
3. **Script Download**: Uses Python `google-cloud-storage` (not gsutil, which isn't in python:3.10 image)
4. **Result Communication**: Build writes JSON to `gs://b2b-recs-pipeline-staging/build_results/{run_id}.json`
5. **Service Account**: `django-app@b2b-recs.iam.gserviceaccount.com` with `cloudbuild.builds.editor` role

### Resolved: Cloud Build Performance (Phase 7)

**Previous Problem**: Cloud Build took **12+ minutes** with vanilla `python:3.10` image due to dependency installation.

**Solution Implemented**: Pre-built Docker image with all TFX dependencies:
- Image: `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest`
- Build time reduced to **~1-2 minutes**
- Dependencies pre-installed: TFX 1.15.0, KFP 2.4.0, google-cloud-aiplatform, google-cloud-storage

### Successfully Tested

- **Cloud Build Trigger**: Successfully triggers TFX pipeline compilation
- **GCS Artifacts**: `gs://b2b-recs-quicktest-artifacts/qt_{id}_{timestamp}`
- **Build Results**: Written to `gs://b2b-recs-pipeline-staging/build_results/{run_id}.json`
- **Region**: `europe-central2` (Warsaw)

### Files Created

| File | Description |
|------|-------------|
| `ml_platform/experiments/__init__.py` | Experiments sub-app initialization |
| `ml_platform/experiments/urls.py` | API route definitions |
| `ml_platform/experiments/api.py` | REST endpoints for Quick Tests |
| `ml_platform/experiments/services.py` | ExperimentService with Cloud Build integration |
| `ml_platform/experiments/tfx_pipeline.py` | TFX pipeline definition (reference) |
| `cloudbuild/compile_and_submit.py` | TFX compile script (reference) |
| `cloudbuild/tfx-compile.yaml` | Cloud Build config (reference) |

### Files Modified

| File | Changes |
|------|---------|
| `requirements.txt` | Added `google-cloud-aiplatform`, `google-cloud-build` (TFX runs in Cloud Build, not locally) |
| `ml_platform/models.py` | Added split strategy fields to QuickTest model |
| `ml_platform/datasets/services.py` | Added `generate_training_query()` with holdout/sampling |
| `ml_platform/configs/services.py` | Fixed f-string escaping, added `has_transform_code` to serializer |
| `ml_platform/urls.py` | Registered experiments sub-app |
| `ml_platform/pipelines/urls.py` | Cleared old KFP routes (moved to experiments) |
| `templates/ml_platform/model_experiments.html` | Added split strategy UI, fixed filter for `has_transform_code` |

### Key Technical Decisions Made

1. **Cloud Build for TFX Compilation**: Required because TFX needs Python 3.10, Django runs on 3.13

2. **Split Strategies**:
   - `random` (default): Hash-based split for fastest iteration
   - `time_holdout`: Days 0-29 train/val (random), day 30 test
   - `strict_time`: Full temporal ordering (train < val < test)

3. **Sampling**: Applied after holdout filter to preserve test set integrity

4. **Sub-App Structure**: Created `ml_platform/experiments/` instead of using existing pipelines directory

5. **Pure TFX Pipeline**: Native TFX components (BigQueryExampleGen, StatisticsGen, SchemaGen, Transform, Trainer) - NO KFP v2 custom components

### Bug Fixes Applied

1. **Feature configs not appearing in dropdown**: `generated_transform_code` not in serializer → Added `has_transform_code` boolean field

2. **"No model endpoint selected" error**: Session-based lookup failed → Get from FeatureConfig relationship chain

3. **f-string escaping** in TrainerModuleGenerator:
   - `{len(product_ids)}` → `{{len(product_ids)}}`
   - `signatures = {` → `signatures = {{`

4. **Cloud Build shell escaping**: BigQuery queries with backticks → Base64 encoding

5. **Cloud Build arg too long**: Embedded script exceeded 10,000 char limit → Upload script to GCS first

6. **gsutil not found**: `python:3.10` image doesn't have gsutil → Use Python `google-cloud-storage` to download

7. **Pre-built Docker image not being used**: `services.py` still referenced `python:3.10` → Updated to use `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest`

8. **Pipeline name validation error**: Vertex AI requires `[a-z0-9-]` pattern → Changed `run_id` format from `qt_14_20251215_184911` to `qt-14-20251215-184911` (hyphens instead of underscores)

9. **GCS bucket permissions**: Compute Engine service account lacked access → Granted `objectAdmin` to `555035914949-compute@developer.gserviceaccount.com` on `b2b-recs-pipeline-staging` and `b2b-recs-quicktest-artifacts` buckets

10. **BigQuery project mismatch**: BigQueryExampleGen running jobs in wrong project (`se4d1ef3f85b1926b-tp`) → Added `beam_pipeline_args` with `--project=b2b-recs` to TFX pipeline configuration

11. **Embedding flatten shape issue (December 16, 2025)**: Dense layer received `(None, None)` input shape in `BuyerModel.call()` and `ProductModel.call()`. Cause: `tf.reshape(f, [tf.shape(f)[0], -1])` loses static shape info during graph tracing. Fix: Changed to `tf.squeeze(f, axis=1) if len(f.shape) == 3 else f` which preserves static dimensions.

12. **Infinite dataset error (December 16, 2025)**: `model.fit()` failed with "infinite dataset" error. Cause: `TensorFlowDatasetOptions` defaults `num_epochs=None` (infinite). Fix: Added `num_epochs=1` to `_input_fn` so epochs are controlled by `model.fit()` parameter.

13. **StringLookup type mismatch (December 16, 2025)**: `StringLookup` layer expected strings but received integer indices. Cause: TFX Transform already converts text to vocab indices via `tft.compute_and_apply_vocabulary()`. Fix: Removed `StringLookup` wrapper, use `Embedding` layer directly on vocab indices. Added `NUM_OOV_BUCKETS = 1` constant to trainer module.

14. **FactorizedTopK serialization error (December 16, 2025)**: `ResourceGather is stateful` error during dataset serialization. Cause: `candidates_dataset.batch(128).map(self.candidate_tower)` tried to serialize `Embedding` layers into dataset pipeline. Fix: Removed `FactorizedTopK` metrics from training (not required for loss computation, only for evaluation).

15. **Untracked resource error during model save (December 16, 2025)**: `tf.saved_model.save()` failed with "untracked resource" for TFT vocabulary hash tables. Cause: Standalone `@tf.function` captured TFT resources not tracked by model. Fix: Created `ServingModel` class (inherits `tf.keras.Model`) that properly tracks all resources as attributes: `tft_layer`, `product_ids`, `product_embeddings`, `retrieval_model`.

### Next Steps

1. **Phase 5**: Implement per-epoch metrics charts and comparison table
2. **Phase 6**: Deploy MLflow server to Cloud Run, integrate tracking
3. **Metrics extraction**: Parse training metrics from Vertex AI logs or Trainer output
4. **Quick Test results display**: Show training metrics in UI after pipeline completion

---

## Architecture Overview

### End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERACTION                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Experiments Page (model_experiments.html)                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Select Dataset         → dropdown (existing datasets)               │ │
│  │ 2. Select FeatureConfig   → dropdown (filtered by dataset)             │ │
│  │ 3. Select ModelConfig     → dropdown (global model configs)            │ │
│  │ 4. Configure Parameters   → sample%, split strategy, epochs, etc.      │ │
│  │ 5. Click "Start Quick Test"                                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DJANGO BACKEND                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Generate SQL Query (from Dataset config)                                │
│     └── BigQueryService.generate_query(dataset) with sampling               │
│                                                                              │
│  2. Get Transform Code (from FeatureConfig - already stored)                │
│     └── feature_config.generated_transform_code                             │
│                                                                              │
│  3. Generate Trainer Code (FeatureConfig + ModelConfig → runtime)           │
│     └── TrainerModuleGenerator(feature_config, model_config).generate()     │
│                                                                              │
│  4. Upload Modules to GCS                                                   │
│     └── gs://bucket/quicktest-{id}/transform_module.py                      │
│     └── gs://bucket/quicktest-{id}/trainer_module.py                        │
│                                                                              │
│  5. Build TFX Pipeline Definition                                           │
│     └── TFXPipelineBuilder.create_pipeline(params)                          │
│                                                                              │
│  6. Compile Pipeline to JSON                                                │
│     └── tfx.dsl.compiler.Compiler().compile(pipeline)                       │
│                                                                              │
│  7. Submit to Vertex AI                                                     │
│     └── aiplatform.PipelineJob(...).submit()                                │
│                                                                              │
│  8. Create QuickTest Record                                                 │
│     └── QuickTest.objects.create(vertex_pipeline_job_name=...)              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    VERTEX AI PIPELINE EXECUTION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Native TFX Pipeline (compiled JSON running on Vertex AI Pipelines)         │
│                                                                              │
│  ┌──────────────────┐                                                       │
│  │ BigQueryExampleGen│  ← SQL query with sampling + split config            │
│  │ (get-data-step)  │  → TFRecords (train + eval splits)                   │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │  StatisticsGen   │  ← TFRecords                                          │
│  │(prepare-data-step)│  → DatasetFeatureStatisticsList                      │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │    SchemaGen     │  ← Statistics                                         │
│  │                  │  → Schema proto                                       │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │    Transform     │  ← Examples, Schema, transform_module.py (GCS)        │
│  │(features-eng-step)│  → Transformed TFRecords, TransformGraph, Vocabs     │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │     Trainer      │  ← Transformed examples, TransformGraph,              │
│  │(train-model-step)│    trainer_module.py (GCS)                            │
│  │                  │  → SavedModel (temp), metrics.json, epoch_metrics     │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ├─────────────────────┐                                            │
│           ▼                     ▼                                            │
│  ┌──────────────────┐  ┌──────────────────┐                                 │
│  │    Evaluator     │  │ MetricsExporter  │                                 │
│  │(evaluate-model)  │  │(explain-predict) │                                 │
│  └──────────────────┘  └──────────────────┘                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESULTS & ARTIFACTS                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  GCS Artifact Structure:                                                     │
│  gs://b2b-recs-quicktest-artifacts/quicktest-{id}/                          │
│  ├── modules/                                                               │
│  │   ├── transform_module.py                                                │
│  │   └── trainer_module.py                                                  │
│  ├── pipeline_root/                                                         │
│  │   ├── BigQueryExampleGen/                                                │
│  │   │   └── examples/                                                      │
│  │   ├── StatisticsGen/                                                     │
│  │   │   └── statistics/                                                    │
│  │   ├── SchemaGen/                                                         │
│  │   │   └── schema/                                                        │
│  │   ├── Transform/                                                         │
│  │   │   ├── transform_graph/                                               │
│  │   │   └── transformed_examples/                                          │
│  │   └── Trainer/                                                           │
│  │       ├── model/ (temporary - not for deployment)                        │
│  │       └── logs/                                                          │
│  └── results/                                                               │
│      ├── metrics.json           ← Final metrics for Django                  │
│      └── epoch_metrics.json     ← Per-epoch history for charts              │
│                                                                              │
│  Django Polling:                                                             │
│  - Poll Vertex AI every 10 seconds                                          │
│  - Update QuickTest.status, stage_details, progress_percent                 │
│  - On completion: fetch metrics.json, update QuickTest record               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXPERIMENTS PAGE (Analysis)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Running Experiments                                                     │ │
│  │ ├── Pipeline DAG visualization (like Vertex AI console screenshot)     │ │
│  │ ├── Real-time progress per component                                   │ │
│  │ ├── Stage status icons (✅ completed, 🔄 running, ⏳ pending)          │ │
│  │ └── Cancel button                                                      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Completed Experiments                                                   │ │
│  │ ├── Comparison table (Dataset, Features, Model, Metrics)               │ │
│  │ ├── Sort by recall@10, recall@50, recall@100, loss                     │ │
│  │ ├── Filter by Dataset, FeatureConfig, ModelConfig                      │ │
│  │ ├── Per-epoch metrics charts (custom, not TensorBoard)                 │ │
│  │ └── "Use for Full Training" action button (future)                     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technical Decisions

### Confirmed Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pipeline Framework | Native TFX SDK | Full TFX component support, proper artifact handling |
| Container Image | `gcr.io/tfx-oss-public/tfx:latest` | Standard image, no custom builds needed |
| TensorBoard | **NOT USED** | Expensive; build custom visualizations instead |
| Pipeline Compilation | On-demand | Show progress bar during compilation |
| Sampling | TFX-level (ExampleGen/Transform) | Cleaner than SQL-level |
| Train/Val Split | All 3 options | Random, time-based, user-configurable |
| Metrics | Collect all available | Per-epoch: loss, recall@k, learning rate, etc. |
| Model Type (Phase 1) | Retrieval only | Ranking/Multitask in future phases |

### Data Flow: BigQuery → TFRecords → TFX

```
BigQuery Table(s)
       │
       ▼ (BigQueryExampleGen with SQL query)
TFRecords (train + eval splits)
       │
       ▼ (StatisticsGen)
Statistics Proto
       │
       ▼ (SchemaGen)
Schema Proto
       │
       ▼ (Transform with preprocessing_fn)
Transformed TFRecords + Vocabularies + Transform Graph
       │
       ▼ (Trainer with run_fn)
Trained Model + Metrics
```

---

## Implementation Plan

### Phase Overview

| Phase | Description | Estimated Effort |
|-------|-------------|------------------|
| **Phase 1** | TFX Pipeline Infrastructure | Large |
| **Phase 2** | Trainer Module Generator Rebuild | Medium |
| **Phase 3** | Experiment Parameters & Submission | Medium |
| **Phase 4** | Pipeline Visualization UI | Medium |
| **Phase 5** | Metrics Collection & Display | Medium |

### Dependency Graph

```
Phase 1 (TFX Pipeline) ──┬──► Phase 3 (Submission)
                         │
Phase 2 (Trainer Gen) ───┘
                               │
                               ▼
                         Phase 4 (Visualization)
                               │
                               ▼
                         Phase 5 (Metrics)
```

---

## Phase 1: TFX Pipeline Infrastructure

### Objective
Replace the current KFP v2 placeholder pipeline (`pipeline_builder.py`) with a native TFX pipeline that properly executes all components.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `ml_platform/pipelines/tfx_pipeline.py` | **CREATE** | Native TFX pipeline definition |
| `ml_platform/pipelines/pipeline_builder.py` | **REPLACE** | Remove KFP v2 components, use TFX |
| `ml_platform/pipelines/services.py` | **MODIFY** | Update submission logic for TFX |
| `requirements.txt` | **MODIFY** | Add `tfx>=1.14.0` |

### Step 1.1: Install TFX Dependencies

```python
# requirements.txt additions
tfx>=1.14.0
tensorflow>=2.13.0
tensorflow-transform>=1.14.0
tensorflow-data-validation>=1.14.0
tensorflow-recommenders>=0.7.3
```

### Step 1.2: Create TFX Pipeline Definition

**File: `ml_platform/pipelines/tfx_pipeline.py`**

```python
"""
Native TFX Pipeline Definition for Quick Tests.

This module defines a proper TFX pipeline that runs on Vertex AI Pipelines.
It replaces the placeholder KFP v2 components with actual TFX components.

Pipeline Components:
1. BigQueryExampleGen - Extract data from BigQuery to TFRecords
2. StatisticsGen - Compute dataset statistics using TFDV
3. SchemaGen - Infer schema from statistics
4. Transform - Apply preprocessing_fn from generated transform_module.py
5. Trainer - Train TFRS model using generated trainer_module.py
"""

import os
from typing import Optional, Dict, Any, List
from absl import logging

from tfx import v1 as tfx
from tfx.dsl.components.common import resolver
from tfx.dsl.input_resolution.strategies import latest_artifact_strategy
from tfx.proto import example_gen_pb2
from tfx.proto import trainer_pb2


def create_quicktest_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    # Data source
    bigquery_query: str,
    bq_project: str,
    bq_location: str,
    # Sampling configuration
    sample_percent: int,  # 5, 10, 25, 100
    # Split configuration
    split_strategy: str,  # 'random', 'time_based', 'custom'
    train_ratio: float,   # e.g., 0.8 for 80% train
    time_split_column: Optional[str] = None,  # For time-based split
    # Module paths (GCS)
    transform_module_path: str = None,
    trainer_module_path: str = None,
    # Training parameters
    epochs: int = 5,
    batch_size: int = 4096,
    learning_rate: float = 0.1,
    train_steps: Optional[int] = None,
    eval_steps: int = 100,
    # Output
    metrics_output_path: str = None,
) -> tfx.dsl.Pipeline:
    """
    Creates a native TFX pipeline for Quick Tests.

    This pipeline validates feature configurations by running a complete
    TFX workflow on Vertex AI Pipelines.

    Args:
        pipeline_name: Unique name for the pipeline
        pipeline_root: GCS path for pipeline artifacts
        bigquery_query: SQL query to extract training data
        bq_project: BigQuery project ID
        bq_location: BigQuery dataset location (e.g., 'US', 'EU')
        sample_percent: Percentage of data to sample (5, 10, 25, 100)
        split_strategy: How to split train/eval ('random', 'time_based', 'custom')
        train_ratio: Fraction of data for training (e.g., 0.8)
        time_split_column: Column for time-based split (required if split_strategy='time_based')
        transform_module_path: GCS path to transform_module.py
        trainer_module_path: GCS path to trainer_module.py
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Optimizer learning rate
        train_steps: Number of training steps (None = auto-calculate)
        eval_steps: Number of evaluation steps
        metrics_output_path: GCS path to write final metrics.json

    Returns:
        tfx.dsl.Pipeline: Configured TFX pipeline
    """

    # =========================================================================
    # 1. BigQueryExampleGen - Extract data from BigQuery
    # =========================================================================

    # Apply sampling to query if needed
    sampled_query = _apply_sampling_to_query(bigquery_query, sample_percent)

    # Configure train/eval split
    output_config = _build_split_config(split_strategy, train_ratio, time_split_column)

    example_gen = tfx.extensions.google_cloud_big_query.BigQueryExampleGen(
        query=sampled_query,
        output_config=output_config,
    )

    # =========================================================================
    # 2. StatisticsGen - Compute dataset statistics
    # =========================================================================

    statistics_gen = tfx.components.StatisticsGen(
        examples=example_gen.outputs['examples']
    )

    # =========================================================================
    # 3. SchemaGen - Infer schema from statistics
    # =========================================================================

    schema_gen = tfx.components.SchemaGen(
        statistics=statistics_gen.outputs['statistics'],
        infer_feature_shape=True
    )

    # =========================================================================
    # 4. Transform - Apply feature engineering
    # =========================================================================

    transform = tfx.components.Transform(
        examples=example_gen.outputs['examples'],
        schema=schema_gen.outputs['schema'],
        module_file=transform_module_path,
    )

    # =========================================================================
    # 5. Trainer - Train TFRS model
    # =========================================================================

    # Build custom_config to pass to run_fn
    custom_config = {
        'epochs': epochs,
        'batch_size': batch_size,
        'learning_rate': learning_rate,
        'metrics_output_path': metrics_output_path,
    }

    trainer = tfx.components.Trainer(
        module_file=trainer_module_path,
        examples=transform.outputs['transformed_examples'],
        transform_graph=transform.outputs['transform_graph'],
        schema=schema_gen.outputs['schema'],
        train_args=tfx.proto.TrainArgs(num_steps=train_steps),
        eval_args=tfx.proto.EvalArgs(num_steps=eval_steps),
        custom_config=custom_config,
    )

    # =========================================================================
    # Build Pipeline
    # =========================================================================

    components = [
        example_gen,
        statistics_gen,
        schema_gen,
        transform,
        trainer,
    ]

    return tfx.dsl.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=components,
    )


def _apply_sampling_to_query(query: str, sample_percent: int) -> str:
    """
    Apply sampling to BigQuery query.

    For TFX-level sampling, we use TABLESAMPLE or WHERE with RAND().

    Args:
        query: Original SQL query
        sample_percent: Percentage to sample (5, 10, 25, 100)

    Returns:
        Modified query with sampling applied
    """
    if sample_percent >= 100:
        return query

    # Wrap original query and apply sampling
    # Using RAND() for reproducible sampling with a seed based on a column
    sampled_query = f"""
    SELECT * FROM (
        {query}
    ) AS base_data
    WHERE RAND() < {sample_percent / 100.0}
    """

    return sampled_query


def _build_split_config(
    split_strategy: str,
    train_ratio: float,
    time_split_column: Optional[str] = None
) -> example_gen_pb2.Output:
    """
    Build ExampleGen output configuration for train/eval split.

    Supports three strategies:
    - random: Hash-based random split (default TFX behavior)
    - time_based: Split by time column (requires time_split_column)
    - custom: User-defined ratio

    Args:
        split_strategy: 'random', 'time_based', or 'custom'
        train_ratio: Fraction for training (e.g., 0.8)
        time_split_column: Column name for time-based split

    Returns:
        example_gen_pb2.Output configuration
    """

    if split_strategy == 'random':
        # Hash-based split using TFX default
        # Calculate hash buckets based on ratio
        # e.g., 80/20 split = 8 train buckets, 2 eval buckets
        total_buckets = 10
        train_buckets = int(train_ratio * total_buckets)
        eval_buckets = total_buckets - train_buckets

        return example_gen_pb2.Output(
            split_config=example_gen_pb2.SplitConfig(
                splits=[
                    example_gen_pb2.SplitConfig.Split(
                        name='train',
                        hash_buckets=train_buckets
                    ),
                    example_gen_pb2.SplitConfig.Split(
                        name='eval',
                        hash_buckets=eval_buckets
                    ),
                ]
            )
        )

    elif split_strategy == 'time_based':
        # Time-based split requires custom handling
        # TFX doesn't have built-in time-based split, so we handle this
        # in the query itself or use a custom ExampleGen
        # For now, use partition_feature_name if available
        if time_split_column:
            return example_gen_pb2.Output(
                split_config=example_gen_pb2.SplitConfig(
                    splits=[
                        example_gen_pb2.SplitConfig.Split(name='train', hash_buckets=8),
                        example_gen_pb2.SplitConfig.Split(name='eval', hash_buckets=2),
                    ],
                    # Note: For true time-based split, modify the SQL query
                    # to add a partition column based on date
                )
            )
        else:
            # Fallback to random if no time column specified
            return _build_split_config('random', train_ratio, None)

    elif split_strategy == 'custom':
        # Custom ratio - use hash buckets to approximate
        # Calculate closest integer ratio
        total_buckets = 100  # Higher precision
        train_buckets = int(train_ratio * total_buckets)
        eval_buckets = total_buckets - train_buckets

        return example_gen_pb2.Output(
            split_config=example_gen_pb2.SplitConfig(
                splits=[
                    example_gen_pb2.SplitConfig.Split(
                        name='train',
                        hash_buckets=train_buckets
                    ),
                    example_gen_pb2.SplitConfig.Split(
                        name='eval',
                        hash_buckets=eval_buckets
                    ),
                ]
            )
        )

    else:
        raise ValueError(f"Unknown split_strategy: {split_strategy}")


def compile_pipeline_for_vertex(
    pipeline: tfx.dsl.Pipeline,
    output_path: str,
) -> str:
    """
    Compile TFX pipeline to JSON for Vertex AI Pipelines.

    Args:
        pipeline: TFX pipeline definition
        output_path: Local path to save compiled JSON

    Returns:
        Path to compiled pipeline JSON
    """
    from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner

    runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
        config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(),
        output_filename=output_path
    )

    runner.run(pipeline)

    logging.info(f"Pipeline compiled to {output_path}")
    return output_path
```

### Step 1.3: Update Pipeline Services

**File: `ml_platform/pipelines/services.py`** (key changes)

```python
# Add imports
from ml_platform.pipelines.tfx_pipeline import (
    create_quicktest_pipeline,
    compile_pipeline_for_vertex
)

class PipelineService:
    """Updated service using native TFX pipeline."""

    def submit_quick_test(
        self,
        feature_config,
        model_config,
        trainer_code: str,
        # New parameters
        sample_percent: int = 100,
        split_strategy: str = 'random',
        train_ratio: float = 0.8,
        time_split_column: str = None,
        # Training params
        epochs: int = 10,
        batch_size: int = 4096,
        learning_rate: float = 0.001,
        user=None
    ):
        """
        Submit a Quick Test pipeline to Vertex AI using native TFX.
        """
        from ml_platform.models import QuickTest

        # Create QuickTest record
        quick_test = QuickTest.objects.create(
            feature_config=feature_config,
            model_config=model_config,
            created_by=user,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            # New fields
            sample_percent=sample_percent,
            split_strategy=split_strategy,
            train_ratio=train_ratio,
            time_split_column=time_split_column,
            status=QuickTest.STATUS_PENDING,
            stage_details=self._get_initial_stage_details()
        )

        try:
            # Update status to submitting
            quick_test.status = QuickTest.STATUS_SUBMITTING
            quick_test.save(update_fields=['status'])

            # 1. Upload generated code to GCS
            gcs_path = self._upload_code_to_gcs(
                feature_config, quick_test, trainer_code
            )
            quick_test.gcs_artifacts_path = gcs_path

            # 2. Generate SQL query with sampling
            from ml_platform.datasets.services import BigQueryService
            dataset = feature_config.dataset
            bq_service = BigQueryService(dataset.model_endpoint, dataset=dataset)
            query_sql = bq_service.generate_query(dataset)

            # 3. Build TFX pipeline
            pipeline_name = f"quicktest-{quick_test.pk}"
            pipeline_root = f"gs://{self.staging_bucket}/runs/{pipeline_name}"
            metrics_output_path = f"{gcs_path}/results/metrics.json"

            pipeline = create_quicktest_pipeline(
                pipeline_name=pipeline_name,
                pipeline_root=pipeline_root,
                bigquery_query=query_sql,
                bq_project=self.project,
                bq_location=dataset.bq_location,
                sample_percent=sample_percent,
                split_strategy=split_strategy,
                train_ratio=train_ratio,
                time_split_column=time_split_column,
                transform_module_path=f"{gcs_path}/modules/transform_module.py",
                trainer_module_path=f"{gcs_path}/modules/trainer_module.py",
                epochs=epochs,
                batch_size=batch_size,
                learning_rate=learning_rate,
                metrics_output_path=metrics_output_path,
            )

            # 4. Compile pipeline (on-demand)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
                compiled_path = f.name

            compile_pipeline_for_vertex(pipeline, compiled_path)

            # 5. Submit to Vertex AI
            self._ensure_aiplatform_initialized()
            from google.cloud import aiplatform

            job = aiplatform.PipelineJob(
                display_name=pipeline_name,
                template_path=compiled_path,
                pipeline_root=pipeline_root,
                project=self.project,
                location=self.location,
            )

            service_account = f"django-app@{self.project}.iam.gserviceaccount.com"
            job.submit(service_account=service_account)

            # 6. Update QuickTest with job info
            quick_test.vertex_pipeline_job_name = job.resource_name
            quick_test.vertex_pipeline_job_id = job.name
            quick_test.status = QuickTest.STATUS_RUNNING
            quick_test.submitted_at = timezone.now()
            quick_test.started_at = timezone.now()
            quick_test.save()

            # Clean up temp file
            os.unlink(compiled_path)

            return quick_test

        except Exception as e:
            quick_test.status = QuickTest.STATUS_FAILED
            quick_test.error_message = str(e)
            quick_test.completed_at = timezone.now()
            quick_test.save()
            raise
```

### Step 1.4: Update Stage Details for TFX Components

The stage names need to match actual TFX component names:

```python
def _get_initial_stage_details(self) -> list:
    """Create initial stage details for TFX pipeline."""
    return [
        {"name": "BigQueryExampleGen", "status": "pending", "duration_seconds": None},
        {"name": "StatisticsGen", "status": "pending", "duration_seconds": None},
        {"name": "SchemaGen", "status": "pending", "duration_seconds": None},
        {"name": "Transform", "status": "pending", "duration_seconds": None},
        {"name": "Trainer", "status": "pending", "duration_seconds": None},
    ]
```

---

## Phase 2: Trainer Module Generator Rebuild

### Objective
Completely rebuild the `TrainerModuleGenerator` to produce a working `trainer_module.py` that:
1. Integrates properly with TFX `Trainer` component
2. Combines FeatureConfig (what features) + ModelConfig (architecture)
3. Exports metrics in JSON format for Django consumption

### Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `ml_platform/configs/services.py` | **MODIFY** | Rebuild `TrainerModuleGenerator` class |

### Step 2.1: Trainer Module Structure

The generated `trainer_module.py` must implement:

```python
# Required by TFX Trainer component
def run_fn(fn_args: tfx.components.FnArgs):
    """Entry point for TFX Trainer."""
    pass
```

### Step 2.2: TrainerModuleGenerator Rebuild

**Key sections to generate:**

```python
class TrainerModuleGenerator:
    """
    Generates TFX Trainer module code from FeatureConfig + ModelConfig.

    Generated code structure:
    1. Imports
    2. Constants (from configs)
    3. Input functions (_input_fn)
    4. BuyerModel class (Query Tower)
    5. ProductModel class (Candidate Tower)
    6. RetrievalModel class (combines towers)
    7. run_fn() - TFX entry point
    8. Metrics export
    """

    def __init__(self, feature_config: 'FeatureConfig', model_config: 'ModelConfig'):
        self.feature_config = feature_config
        self.model_config = model_config

    def generate(self) -> str:
        """Generate complete trainer_module.py code."""
        sections = [
            self._generate_imports(),
            self._generate_constants(),
            self._generate_input_fn(),
            self._generate_buyer_model(),
            self._generate_product_model(),
            self._generate_retrieval_model(),
            self._generate_run_fn(),
        ]
        return '\n\n'.join(sections)
```

### Step 2.3: Generated Code Template

The generator should produce code following this template:

```python
"""
Auto-generated TFX Trainer Module
Generated: {timestamp}
FeatureConfig: {feature_config_name} (ID: {feature_config_id})
ModelConfig: {model_config_name} (ID: {model_config_id})
"""

import json
import os
from typing import Dict, List, Text
import tensorflow as tf
import tensorflow_transform as tft
import tensorflow_recommenders as tfrs
from tfx import v1 as tfx
from tfx_bsl.public import tfxio

# =============================================================================
# CONSTANTS (from ModelConfig)
# =============================================================================

EMBEDDING_DIMENSION = {output_embedding_dim}
BATCH_SIZE = {batch_size}
LEARNING_RATE = {learning_rate}
EPOCHS = {epochs}

# Optimizer configuration
OPTIMIZER = '{optimizer}'  # adagrad, adam, sgd, etc.

# Tower layers configuration
BUYER_TOWER_LAYERS = {buyer_tower_layers_json}
PRODUCT_TOWER_LAYERS = {product_tower_layers_json}


# =============================================================================
# INPUT FUNCTION
# =============================================================================

def _input_fn(
    file_pattern: List[Text],
    data_accessor: tfx.components.DataAccessor,
    tf_transform_output: tft.TFTransformOutput,
    batch_size: int
) -> tf.data.Dataset:
    """Generate dataset from transformed examples."""
    return data_accessor.tf_dataset_factory(
        file_pattern,
        tfxio.TensorFlowDatasetOptions(batch_size=batch_size),
        tf_transform_output.transformed_metadata.schema
    )


# =============================================================================
# BUYER MODEL (Query Tower)
# =============================================================================

class BuyerModel(tf.keras.Model):
    """Query tower for user/buyer representation."""

    def __init__(self, tf_transform_output: tft.TFTransformOutput):
        super().__init__()

        # Feature embeddings
        {buyer_embedding_layers}

        # Tower layers
        self.tower = tf.keras.Sequential([
            {buyer_tower_sequential_layers}
        ])

    def call(self, inputs):
        # Concatenate all feature embeddings
        embeddings = []
        {buyer_call_body}

        x = tf.concat(embeddings, axis=-1)
        return self.tower(x)


# =============================================================================
# PRODUCT MODEL (Candidate Tower)
# =============================================================================

class ProductModel(tf.keras.Model):
    """Candidate tower for product representation."""

    def __init__(self, tf_transform_output: tft.TFTransformOutput):
        super().__init__()

        # Feature embeddings
        {product_embedding_layers}

        # Tower layers
        self.tower = tf.keras.Sequential([
            {product_tower_sequential_layers}
        ])

    def call(self, inputs):
        # Concatenate all feature embeddings
        embeddings = []
        {product_call_body}

        x = tf.concat(embeddings, axis=-1)
        return self.tower(x)


# =============================================================================
# RETRIEVAL MODEL
# =============================================================================

class RetrievalModel(tfrs.Model):
    """Two-tower retrieval model."""

    def __init__(
        self,
        buyer_model: tf.keras.Model,
        product_model: tf.keras.Model,
        candidate_dataset: tf.data.Dataset
    ):
        super().__init__()
        self.buyer_model = buyer_model
        self.product_model = product_model

        # Retrieval task with metrics
        self.task = tfrs.tasks.Retrieval(
            metrics=tfrs.metrics.FactorizedTopK(
                candidates=candidate_dataset.batch(128).map(self.product_model)
            )
        )

    def compute_loss(self, features: Dict[Text, tf.Tensor], training=False) -> tf.Tensor:
        buyer_embeddings = self.buyer_model(features)
        product_embeddings = self.product_model(features)
        return self.task(buyer_embeddings, product_embeddings)


# =============================================================================
# RUN FUNCTION (TFX Entry Point)
# =============================================================================

def run_fn(fn_args: tfx.components.FnArgs):
    """
    TFX Trainer entry point.

    Args:
        fn_args: FnArgs containing:
            - train_files: List of training TFRecord file paths
            - eval_files: List of evaluation TFRecord file paths
            - transform_output: Path to transform graph
            - serving_model_dir: Path to save model
            - custom_config: Dict with epochs, batch_size, etc.
    """
    # Load transform output
    tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)

    # Get custom config
    custom_config = fn_args.custom_config or {{}}
    epochs = custom_config.get('epochs', EPOCHS)
    batch_size = custom_config.get('batch_size', BATCH_SIZE)
    learning_rate = custom_config.get('learning_rate', LEARNING_RATE)
    metrics_output_path = custom_config.get('metrics_output_path')

    # Build datasets
    train_dataset = _input_fn(
        fn_args.train_files,
        fn_args.data_accessor,
        tf_transform_output,
        batch_size
    )

    eval_dataset = _input_fn(
        fn_args.eval_files,
        fn_args.data_accessor,
        tf_transform_output,
        batch_size
    )

    # Build models
    buyer_model = BuyerModel(tf_transform_output)
    product_model = ProductModel(tf_transform_output)

    # Build retrieval model
    model = RetrievalModel(
        buyer_model=buyer_model,
        product_model=product_model,
        candidate_dataset=eval_dataset  # Use eval for candidates
    )

    # Configure optimizer
    optimizer = _get_optimizer(OPTIMIZER, learning_rate)
    model.compile(optimizer=optimizer)

    # Metrics callback for per-epoch logging
    epoch_metrics = []

    class MetricsCallback(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            epoch_metrics.append({{
                'epoch': epoch + 1,
                **{{k: float(v) for k, v in (logs or {{}}).items()}}
            }})

    # Train model
    history = model.fit(
        train_dataset,
        epochs=epochs,
        validation_data=eval_dataset,
        callbacks=[MetricsCallback()]
    )

    # Export metrics
    if metrics_output_path:
        _export_metrics(
            history=history,
            epoch_metrics=epoch_metrics,
            output_path=metrics_output_path
        )

    # Save model (temporary - for validation only)
    model.save(fn_args.serving_model_dir)


def _get_optimizer(optimizer_name: str, learning_rate: float):
    """Get configured optimizer."""
    optimizers = {{
        'adagrad': tf.keras.optimizers.Adagrad,
        'adam': tf.keras.optimizers.Adam,
        'sgd': tf.keras.optimizers.SGD,
        'rmsprop': tf.keras.optimizers.RMSprop,
        'adamw': tf.keras.optimizers.AdamW,
        'ftrl': tf.keras.optimizers.Ftrl,
    }}
    optimizer_class = optimizers.get(optimizer_name.lower(), tf.keras.optimizers.Adagrad)
    return optimizer_class(learning_rate=learning_rate)


def _export_metrics(history, epoch_metrics: List[Dict], output_path: str):
    """Export metrics to JSON for Django consumption."""
    from google.cloud import storage
    import json

    # Parse GCS path
    if output_path.startswith('gs://'):
        path = output_path[5:]
        bucket_name = path.split('/')[0]
        blob_path = '/'.join(path.split('/')[1:])

        # Final metrics
        final_metrics = {{
            'loss': float(history.history.get('loss', [0])[-1]),
            'val_loss': float(history.history.get('val_loss', [0])[-1]),
            'factorized_top_k/top_10_categorical_accuracy': float(
                history.history.get('factorized_top_k/top_10_categorical_accuracy', [0])[-1]
            ),
            'factorized_top_k/top_50_categorical_accuracy': float(
                history.history.get('factorized_top_k/top_50_categorical_accuracy', [0])[-1]
            ),
            'factorized_top_k/top_100_categorical_accuracy': float(
                history.history.get('factorized_top_k/top_100_categorical_accuracy', [0])[-1]
            ),
            'epochs_completed': len(history.history.get('loss', [])),
        }}

        # Upload final metrics
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        metrics_blob = bucket.blob(blob_path)
        metrics_blob.upload_from_string(json.dumps(final_metrics, indent=2))

        # Upload epoch metrics
        epoch_blob_path = blob_path.replace('metrics.json', 'epoch_metrics.json')
        epoch_blob = bucket.blob(epoch_blob_path)
        epoch_blob.upload_from_string(json.dumps(epoch_metrics, indent=2))
```

---

## Phase 3: Experiment Parameters & Submission

### Objective
Add experiment parameter configuration to the UI and API.

### New Parameters to Support

| Parameter | Type | Options | Default |
|-----------|------|---------|---------|
| `sample_percent` | int | 5, 10, 25, 100 | 100 |
| `split_strategy` | str | 'random', 'time_based', 'custom' | 'random' |
| `train_ratio` | float | 0.5 - 0.95 | 0.8 |
| `time_split_column` | str | column name | None |

### Step 3.1: Update QuickTest Model

**File: `ml_platform/models.py`**

Add new fields to `QuickTest`:

```python
class QuickTest(models.Model):
    # ... existing fields ...

    # Sampling configuration
    sample_percent = models.IntegerField(
        default=100,
        help_text="Percentage of data to sample (5, 10, 25, 100)"
    )

    # Split configuration
    SPLIT_STRATEGY_CHOICES = [
        ('random', 'Random Split'),
        ('time_based', 'Time-Based Split'),
        ('custom', 'Custom Ratio'),
    ]

    split_strategy = models.CharField(
        max_length=20,
        choices=SPLIT_STRATEGY_CHOICES,
        default='random',
        help_text="Train/eval split strategy"
    )

    train_ratio = models.FloatField(
        default=0.8,
        help_text="Fraction of data for training (0.5 - 0.95)"
    )

    time_split_column = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Column for time-based split"
    )
```

### Step 3.2: Update API Endpoint

**File: `ml_platform/pipelines/api.py`**

Update `start_quick_test` to accept new parameters:

```python
@api_view(['POST'])
def start_quick_test(request, config_id):
    """Start a Quick Test pipeline."""

    # Get required configs
    feature_config = get_object_or_404(FeatureConfig, pk=config_id)
    model_config_id = request.data.get('model_config_id')
    model_config = get_object_or_404(ModelConfig, pk=model_config_id)

    # Experiment parameters
    sample_percent = int(request.data.get('sample_percent', 100))
    split_strategy = request.data.get('split_strategy', 'random')
    train_ratio = float(request.data.get('train_ratio', 0.8))
    time_split_column = request.data.get('time_split_column')

    # Training parameters
    epochs = int(request.data.get('epochs', model_config.epochs))
    batch_size = int(request.data.get('batch_size', model_config.batch_size))
    learning_rate = float(request.data.get('learning_rate', model_config.learning_rate))

    # Generate trainer code
    from ml_platform.configs.services import TrainerModuleGenerator
    generator = TrainerModuleGenerator(feature_config, model_config)
    trainer_code = generator.generate()

    # Submit pipeline
    service = PipelineService()
    quick_test = service.submit_quick_test(
        feature_config=feature_config,
        model_config=model_config,
        trainer_code=trainer_code,
        sample_percent=sample_percent,
        split_strategy=split_strategy,
        train_ratio=train_ratio,
        time_split_column=time_split_column,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        user=request.user
    )

    return Response({
        'success': True,
        'data': {
            'quick_test_id': quick_test.pk,
            'status': quick_test.status,
        }
    })
```

---

## Phase 4: Pipeline Visualization UI

### Objective
Create a pipeline DAG visualization similar to Vertex AI console.

### UI Components

1. **Pipeline DAG** - Visual graph of components
2. **Stage Status** - Color-coded status per component
3. **Connections** - Arrows showing data flow
4. **Artifact Boxes** - Small boxes between stages

### Step 4.1: DAG Visualization Component

**File: `templates/ml_platform/model_experiments.html`**

Create a reusable pipeline DAG component:

```html
<!-- Pipeline DAG Visualization -->
<div class="pipeline-dag" id="pipeline-dag-${quickTestId}">
    <div class="dag-container">
        <!-- Stage: BigQueryExampleGen -->
        <div class="dag-stage" data-stage="BigQueryExampleGen">
            <div class="stage-box ${getStageStatusClass('BigQueryExampleGen')}">
                <div class="stage-icon">📊</div>
                <div class="stage-name">get-data-step</div>
                <div class="stage-image">BigQueryExampleGen</div>
                <div class="stage-status-icon"></div>
            </div>
        </div>

        <!-- Connector + Artifact -->
        <div class="dag-connector">
            <div class="connector-line"></div>
            <div class="artifact-box">Examples</div>
        </div>

        <!-- Stage: StatisticsGen -->
        <div class="dag-stage" data-stage="StatisticsGen">
            <div class="stage-box ${getStageStatusClass('StatisticsGen')}">
                <div class="stage-icon">📈</div>
                <div class="stage-name">prepare-data-step</div>
                <div class="stage-image">StatisticsGen</div>
                <div class="stage-status-icon"></div>
            </div>
        </div>

        <!-- Continue for other stages... -->
    </div>
</div>
```

### Step 4.2: DAG CSS Styles

```css
/* Pipeline DAG Styles */
.pipeline-dag {
    background: #f8fafc;
    border-radius: 12px;
    padding: 24px;
    overflow-x: auto;
}

.dag-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
}

.dag-stage {
    position: relative;
}

.stage-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px 20px;
    background: white;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    min-width: 180px;
    position: relative;
}

.stage-box.completed {
    border-color: #10b981;
    background: #ecfdf5;
}

.stage-box.running {
    border-color: #3b82f6;
    background: #eff6ff;
    animation: pulse 2s infinite;
}

.stage-box.pending {
    border-color: #e5e7eb;
    background: #f9fafb;
    opacity: 0.7;
}

.stage-box.failed {
    border-color: #ef4444;
    background: #fef2f2;
}

.stage-status-icon {
    position: absolute;
    top: -8px;
    right: -8px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
}

.stage-box.completed .stage-status-icon {
    background: #10b981;
    color: white;
}

.stage-box.completed .stage-status-icon::after {
    content: '✓';
}

.stage-box.running .stage-status-icon {
    background: #3b82f6;
    color: white;
}

.stage-box.running .stage-status-icon::after {
    content: '↻';
    animation: spin 1s linear infinite;
}

.dag-connector {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
}

.connector-line {
    width: 2px;
    height: 20px;
    background: #d1d5db;
}

.artifact-box {
    padding: 4px 8px;
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    font-size: 11px;
    color: #6b7280;
}

@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
    50% { box-shadow: 0 0 0 8px rgba(59, 130, 246, 0); }
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
```

---

## Phase 5: Metrics Collection & Display

### Objective
Collect all available metrics and display them with custom visualizations (NO TensorBoard).

### Metrics to Collect

| Metric | Source | Description |
|--------|--------|-------------|
| `loss` | Trainer | Training loss |
| `val_loss` | Trainer | Validation loss |
| `factorized_top_k/top_10_categorical_accuracy` | TFRS | Recall@10 |
| `factorized_top_k/top_50_categorical_accuracy` | TFRS | Recall@50 |
| `factorized_top_k/top_100_categorical_accuracy` | TFRS | Recall@100 |
| `learning_rate` | Optimizer | Current learning rate |
| `epoch` | Trainer | Epoch number |

### Step 5.1: Epoch Metrics Chart Component

Using Chart.js for custom visualizations:

```javascript
// Epoch Metrics Chart
function renderEpochMetricsChart(containerId, epochMetrics) {
    const ctx = document.getElementById(containerId).getContext('2d');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: epochMetrics.map(m => `Epoch ${m.epoch}`),
            datasets: [
                {
                    label: 'Loss',
                    data: epochMetrics.map(m => m.loss),
                    borderColor: '#ef4444',
                    yAxisID: 'y-loss',
                },
                {
                    label: 'Recall@100',
                    data: epochMetrics.map(m => m['factorized_top_k/top_100_categorical_accuracy']),
                    borderColor: '#10b981',
                    yAxisID: 'y-recall',
                },
            ]
        },
        options: {
            responsive: true,
            scales: {
                'y-loss': {
                    type: 'linear',
                    position: 'left',
                    title: { display: true, text: 'Loss' }
                },
                'y-recall': {
                    type: 'linear',
                    position: 'right',
                    title: { display: true, text: 'Recall@100' },
                    min: 0,
                    max: 1,
                }
            }
        }
    });
}
```

### Step 5.2: Metrics Comparison Table

```html
<div class="metrics-comparison-table">
    <table>
        <thead>
            <tr>
                <th>Quick Test</th>
                <th>Dataset</th>
                <th>Features</th>
                <th>Model</th>
                <th>Loss</th>
                <th>R@10</th>
                <th>R@50</th>
                <th>R@100</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody id="experiments-table-body">
            <!-- Populated via JavaScript -->
        </tbody>
    </table>
</div>
```

---

## Phase 6: MLflow Integration

### Objective
Implement MLflow for experiment tracking and comparison, enabling users to find the best configuration across multiple Quick Test runs.

### Why MLflow (Not TensorBoard)

| Aspect | TensorBoard | MLflow |
|--------|-------------|--------|
| **Primary Use** | Real-time training visualization | Experiment tracking & comparison |
| **Cost** | Vertex AI TensorBoard = expensive | Self-hosted = ~$20-40/month |
| **Cross-run Comparison** | Limited | Built-in (parallel coords, scatter plots) |
| **Best For** | Single-run debugging | Finding best config across runs |

**MLflow is the right tool for our use case** - finding the best (Dataset + FeatureConfig + ModelConfig) combination.

### MLflow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MLFLOW ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────┐     ┌─────────────────────┐                        │
│  │  MLflow Server      │     │  Backend Store      │                        │
│  │  (Cloud Run)        │────▶│  (Cloud SQL)        │                        │
│  │                     │     │                     │                        │
│  │  - REST API         │     │  - Experiments      │                        │
│  │  - Web UI           │     │  - Runs             │                        │
│  │  - Tracking         │     │  - Params/Metrics   │                        │
│  └─────────────────────┘     │  - Tags             │                        │
│           │                  └─────────────────────┘                        │
│           │                                                                  │
│           │                  ┌─────────────────────┐                        │
│           └─────────────────▶│  Artifact Store     │                        │
│                              │  (GCS Bucket)       │                        │
│                              │                     │                        │
│                              │  - Model files      │                        │
│                              │  - Plots/images     │                        │
│                              └─────────────────────┘                        │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Django App                                                               ││
│  │ ┌───────────────────┐                                                   ││
│  │ │  MLflowService    │                                                   ││
│  │ │  - log_quick_test()                                                   ││
│  │ │  - get_experiment_runs()                                              ││
│  │ │  - compare_runs()                                                     ││
│  │ │  - get_best_run()                                                     ││
│  │ └───────────────────┘                                                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step 6.1: Deploy MLflow Server on Cloud Run

**File: `mlflow-server/Dockerfile`**

```dockerfile
FROM python:3.10-slim

# Install MLflow and dependencies
RUN pip install --no-cache-dir \
    mlflow==2.9.2 \
    psycopg2-binary \
    google-cloud-storage \
    gunicorn

# Create non-root user
RUN useradd -m mlflow
USER mlflow

EXPOSE 8080

# Start MLflow server
CMD ["mlflow", "server", \
     "--backend-store-uri", "${BACKEND_STORE_URI}", \
     "--default-artifact-root", "${ARTIFACT_ROOT}", \
     "--host", "0.0.0.0", \
     "--port", "8080"]
```

**File: `mlflow-server/cloudbuild.yaml`**

```yaml
steps:
  # Build the container image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/mlflow-server:latest', '.']

  # Push to Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/mlflow-server:latest']

  # Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'mlflow-server'
      - '--image'
      - 'gcr.io/$PROJECT_ID/mlflow-server:latest'
      - '--region'
      - 'us-central1'
      - '--platform'
      - 'managed'
      - '--allow-unauthenticated'  # Or use IAM for security
      - '--set-env-vars'
      - 'BACKEND_STORE_URI=postgresql://${_DB_USER}:${_DB_PASS}@${_DB_HOST}/${_DB_NAME}'
      - '--set-env-vars'
      - 'ARTIFACT_ROOT=gs://${_GCS_BUCKET}/mlflow-artifacts'
      - '--memory'
      - '1Gi'
      - '--cpu'
      - '1'
      - '--min-instances'
      - '0'
      - '--max-instances'
      - '2'

substitutions:
  _DB_USER: mlflow
  _DB_PASS: ''  # Set via Secret Manager
  _DB_HOST: ''  # Cloud SQL connection
  _DB_NAME: mlflow
  _GCS_BUCKET: b2b-recs-mlflow-artifacts

images:
  - 'gcr.io/$PROJECT_ID/mlflow-server:latest'
```

### Step 6.2: Cloud SQL Setup for MLflow

```sql
-- Create MLflow database
CREATE DATABASE mlflow;

-- Create MLflow user
CREATE USER mlflow WITH PASSWORD 'secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow;
```

**Infrastructure requirements:**
- Cloud SQL PostgreSQL instance (smallest tier: db-f1-micro ~$10/month)
- GCS bucket for artifacts: `gs://b2b-recs-mlflow-artifacts`
- Cloud Run service account with:
  - `roles/cloudsql.client`
  - `roles/storage.objectAdmin` on artifact bucket

### Step 6.3: Django Settings

**File: `settings.py`** (additions)

```python
# MLflow Configuration
MLFLOW_TRACKING_URI = os.environ.get(
    'MLFLOW_TRACKING_URI',
    'https://mlflow-server-xxxxx-uc.a.run.app'  # Cloud Run URL
)

# MLflow experiment naming
MLFLOW_EXPERIMENT_PREFIX = os.environ.get('MLFLOW_EXPERIMENT_PREFIX', 'b2b-recs')
```

### Step 6.4: MLflow Service Implementation

**File: `ml_platform/experiments/services.py`**

```python
"""
MLflow Integration Service

Handles all MLflow operations for experiment tracking:
- Logging Quick Test runs
- Querying experiments for comparison
- Finding best configurations
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

import mlflow
from mlflow.tracking import MlflowClient
from django.conf import settings

logger = logging.getLogger(__name__)


class MLflowService:
    """
    Service for MLflow experiment tracking integration.

    Usage:
        service = MLflowService()
        service.log_quick_test(quick_test, feature_config, model_config, dataset)
    """

    def __init__(self, tracking_uri: str = None):
        """
        Initialize MLflow service.

        Args:
            tracking_uri: MLflow tracking server URL (defaults to settings)
        """
        self.tracking_uri = tracking_uri or settings.MLFLOW_TRACKING_URI
        mlflow.set_tracking_uri(self.tracking_uri)
        self.client = MlflowClient(self.tracking_uri)

    # =========================================================================
    # Experiment Management
    # =========================================================================

    def get_or_create_experiment(
        self,
        model_endpoint_name: str,
        dataset_name: str
    ) -> str:
        """
        Get or create MLflow experiment for a model/dataset combination.

        Experiment naming: "{prefix}/{model_endpoint}/{dataset}"
        Example: "b2b-recs/ClientABC-Recs/Q4-2024-Training"

        Args:
            model_endpoint_name: Name of the model endpoint
            dataset_name: Name of the dataset

        Returns:
            experiment_id: MLflow experiment ID
        """
        experiment_name = f"{settings.MLFLOW_EXPERIMENT_PREFIX}/{model_endpoint_name}/{dataset_name}"

        experiment = self.client.get_experiment_by_name(experiment_name)
        if experiment:
            return experiment.experiment_id

        # Create new experiment
        experiment_id = self.client.create_experiment(
            name=experiment_name,
            tags={
                'model_endpoint': model_endpoint_name,
                'dataset': dataset_name,
                'created_by': 'b2b-recs-platform',
            }
        )
        logger.info(f"Created MLflow experiment: {experiment_name} (ID: {experiment_id})")
        return experiment_id

    # =========================================================================
    # Quick Test Logging
    # =========================================================================

    def log_quick_test(
        self,
        quick_test: 'QuickTest',
        feature_config: 'FeatureConfig',
        model_config: 'ModelConfig',
        dataset: 'Dataset'
    ) -> str:
        """
        Log a completed Quick Test to MLflow.

        Called by Django after pipeline completion when metrics are available.

        Args:
            quick_test: QuickTest model instance with results
            feature_config: FeatureConfig used in the test
            model_config: ModelConfig used in the test
            dataset: Dataset used in the test

        Returns:
            run_id: MLflow run ID
        """
        # Get or create experiment
        experiment_id = self.get_or_create_experiment(
            model_endpoint_name=dataset.model_endpoint.name,
            dataset_name=dataset.name
        )

        # Build run name
        run_name = f"{feature_config.name} + {model_config.name} #{quick_test.pk}"

        with mlflow.start_run(
            experiment_id=experiment_id,
            run_name=run_name
        ) as run:
            # -----------------------------------------------------------------
            # Log Parameters
            # -----------------------------------------------------------------

            # Identifiers
            mlflow.log_param("quick_test_id", quick_test.pk)
            mlflow.log_param("feature_config_id", feature_config.pk)
            mlflow.log_param("feature_config_name", feature_config.name)
            mlflow.log_param("model_config_id", model_config.pk)
            mlflow.log_param("model_config_name", model_config.name)
            mlflow.log_param("dataset_id", dataset.pk)
            mlflow.log_param("dataset_name", dataset.name)

            # Experiment settings
            mlflow.log_param("run_type", "quick_test")
            mlflow.log_param("sample_percent", quick_test.sample_percent)
            mlflow.log_param("split_strategy", quick_test.split_strategy)
            mlflow.log_param("train_ratio", quick_test.train_ratio)

            # Training hyperparameters
            mlflow.log_param("epochs", quick_test.epochs)
            mlflow.log_param("batch_size", quick_test.batch_size)
            mlflow.log_param("learning_rate", quick_test.learning_rate)
            mlflow.log_param("optimizer", model_config.optimizer)

            # Model architecture
            mlflow.log_param("model_type", model_config.model_type)
            mlflow.log_param("output_embedding_dim", model_config.output_embedding_dim)
            mlflow.log_param("buyer_tower_layers", len(model_config.buyer_tower_layers))
            mlflow.log_param("product_tower_layers", len(model_config.product_tower_layers))

            # Feature configuration summary
            mlflow.log_param("buyer_features_count", len(feature_config.buyer_model_features))
            mlflow.log_param("product_features_count", len(feature_config.product_model_features))
            mlflow.log_param("buyer_crosses_count", len(feature_config.buyer_model_crosses))
            mlflow.log_param("product_crosses_count", len(feature_config.product_model_crosses))
            mlflow.log_param("buyer_tensor_dim", feature_config.buyer_tensor_dim)
            mlflow.log_param("product_tensor_dim", feature_config.product_tensor_dim)

            # Log individual feature embedding dims for analysis
            for feature in feature_config.buyer_model_features:
                col_name = feature.get('column', 'unknown').replace('.', '_')
                emb_dim = feature.get('embedding_dim', 0)
                if emb_dim:
                    mlflow.log_param(f"buyer_{col_name}_emb_dim", emb_dim)

            for feature in feature_config.product_model_features:
                col_name = feature.get('column', 'unknown').replace('.', '_')
                emb_dim = feature.get('embedding_dim', 0)
                if emb_dim:
                    mlflow.log_param(f"product_{col_name}_emb_dim", emb_dim)

            # -----------------------------------------------------------------
            # Log Metrics
            # -----------------------------------------------------------------

            if quick_test.loss is not None:
                mlflow.log_metric("loss", quick_test.loss)

            if quick_test.recall_at_10 is not None:
                mlflow.log_metric("recall_at_10", quick_test.recall_at_10)

            if quick_test.recall_at_50 is not None:
                mlflow.log_metric("recall_at_50", quick_test.recall_at_50)

            if quick_test.recall_at_100 is not None:
                mlflow.log_metric("recall_at_100", quick_test.recall_at_100)

            if quick_test.duration_seconds:
                mlflow.log_metric("duration_seconds", quick_test.duration_seconds)

            # -----------------------------------------------------------------
            # Log Tags (for filtering in UI)
            # -----------------------------------------------------------------

            mlflow.set_tag("model_endpoint_id", str(dataset.model_endpoint.pk))
            mlflow.set_tag("status", quick_test.status)
            mlflow.set_tag("has_cross_features",
                          str(bool(feature_config.buyer_model_crosses or
                                   feature_config.product_model_crosses)))

            if quick_test.created_by:
                mlflow.set_tag("user", quick_test.created_by.email)

            mlflow.set_tag("submitted_at", quick_test.submitted_at.isoformat() if quick_test.submitted_at else "")

            # -----------------------------------------------------------------
            # Log Artifacts (optional - for detailed analysis)
            # -----------------------------------------------------------------

            # Log vocabulary stats if available
            if quick_test.vocabulary_stats:
                import json
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(quick_test.vocabulary_stats, f, indent=2)
                    mlflow.log_artifact(f.name, "vocabulary_stats.json")

            logger.info(f"Logged Quick Test #{quick_test.pk} to MLflow run {run.info.run_id}")
            return run.info.run_id

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_experiment_runs(
        self,
        model_endpoint_name: str,
        dataset_name: str,
        run_type: str = 'all',
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all runs for an experiment.

        Args:
            model_endpoint_name: Name of the model endpoint
            dataset_name: Name of the dataset
            run_type: 'all', 'quick_test', or 'full_training'
            max_results: Maximum runs to return

        Returns:
            List of run dictionaries with params and metrics
        """
        experiment_name = f"{settings.MLFLOW_EXPERIMENT_PREFIX}/{model_endpoint_name}/{dataset_name}"
        experiment = self.client.get_experiment_by_name(experiment_name)

        if not experiment:
            return []

        # Build filter string
        filter_string = ""
        if run_type != 'all':
            filter_string = f"params.run_type = '{run_type}'"

        runs = self.client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=filter_string,
            max_results=max_results,
            order_by=["metrics.recall_at_100 DESC"]
        )

        return [
            {
                'run_id': run.info.run_id,
                'run_name': run.data.tags.get('mlflow.runName', run.info.run_id),
                'status': run.info.status,
                'start_time': run.info.start_time,
                'params': dict(run.data.params),
                'metrics': dict(run.data.metrics),
                'tags': dict(run.data.tags),
            }
            for run in runs
        ]

    def get_best_run(
        self,
        model_endpoint_name: str,
        dataset_name: str,
        metric: str = 'recall_at_100',
        run_type: str = 'quick_test'
    ) -> Optional[Dict[str, Any]]:
        """
        Get the best run by a specific metric.

        Args:
            model_endpoint_name: Name of the model endpoint
            dataset_name: Name of the dataset
            metric: Metric to optimize ('recall_at_100', 'recall_at_50', 'loss')
            run_type: 'quick_test' or 'full_training'

        Returns:
            Best run dictionary or None
        """
        runs = self.get_experiment_runs(
            model_endpoint_name=model_endpoint_name,
            dataset_name=dataset_name,
            run_type=run_type,
            max_results=1
        )

        return runs[0] if runs else None

    def compare_runs(self, run_ids: List[str]) -> Dict[str, Any]:
        """
        Compare multiple runs.

        Args:
            run_ids: List of MLflow run IDs to compare

        Returns:
            Comparison dictionary with params diff and metrics comparison
        """
        runs = [self.client.get_run(run_id) for run_id in run_ids]

        comparison = {
            'runs': [],
            'params_diff': {},
            'metrics_comparison': {},
        }

        # Collect all params and metrics
        all_params = set()
        all_metrics = set()

        for run in runs:
            all_params.update(run.data.params.keys())
            all_metrics.update(run.data.metrics.keys())

            comparison['runs'].append({
                'run_id': run.info.run_id,
                'run_name': run.data.tags.get('mlflow.runName', run.info.run_id),
                'params': dict(run.data.params),
                'metrics': dict(run.data.metrics),
            })

        # Find params that differ
        for param in all_params:
            values = [run.data.params.get(param) for run in runs]
            if len(set(values)) > 1:
                comparison['params_diff'][param] = values

        # Compare metrics
        for metric in all_metrics:
            values = [run.data.metrics.get(metric) for run in runs]
            comparison['metrics_comparison'][metric] = {
                'values': values,
                'best_idx': values.index(max(v for v in values if v is not None)) if any(values) else None,
            }

        return comparison

    # =========================================================================
    # Heatmap Data Generation
    # =========================================================================

    def get_heatmap_data(
        self,
        model_endpoint_name: str,
        dataset_name: str,
        metric: str = 'recall_at_100',
        x_axis: str = 'buyer_tensor_dim',
        y_axis: str = 'product_tensor_dim',
    ) -> Dict[str, Any]:
        """
        Generate heatmap data for experiment visualization.

        Args:
            model_endpoint_name: Name of the model endpoint
            dataset_name: Name of the dataset
            metric: Metric to display in heatmap
            x_axis: Parameter for X axis
            y_axis: Parameter for Y axis

        Returns:
            Heatmap data structure for frontend
        """
        runs = self.get_experiment_runs(
            model_endpoint_name=model_endpoint_name,
            dataset_name=dataset_name,
            run_type='quick_test'
        )

        # Extract unique axis values
        x_values = sorted(set(r['params'].get(x_axis) for r in runs if r['params'].get(x_axis)))
        y_values = sorted(set(r['params'].get(y_axis) for r in runs if r['params'].get(y_axis)))

        # Build cells
        cells = []
        best_cell = None
        best_value = -1

        for run in runs:
            x_val = run['params'].get(x_axis)
            y_val = run['params'].get(y_axis)
            metric_val = run['metrics'].get(metric)

            if x_val and y_val and metric_val is not None:
                cell = {
                    'x': x_val,
                    'y': y_val,
                    'value': metric_val,
                    'run_id': run['run_id'],
                    'run_name': run['run_name'],
                }
                cells.append(cell)

                if metric_val > best_value:
                    best_value = metric_val
                    best_cell = cell

        return {
            'metric': metric,
            'x_axis': {'name': x_axis, 'values': x_values},
            'y_axis': {'name': y_axis, 'values': y_values},
            'cells': cells,
            'best': best_cell,
        }
```

### Step 6.5: Update Pipeline Completion Flow

**File: `ml_platform/pipelines/services.py`** (add to `_handle_pipeline_completion`)

```python
def _handle_pipeline_completion(self, quick_test: 'QuickTest'):
    """
    Handle pipeline completion - fetch metrics and log to MLflow.
    """
    # Fetch metrics from GCS (existing code)
    metrics = self._fetch_metrics_from_gcs(quick_test)

    # Update QuickTest record
    quick_test.loss = metrics.get('loss')
    quick_test.recall_at_10 = metrics.get('factorized_top_k/top_10_categorical_accuracy')
    quick_test.recall_at_50 = metrics.get('factorized_top_k/top_50_categorical_accuracy')
    quick_test.recall_at_100 = metrics.get('factorized_top_k/top_100_categorical_accuracy')
    quick_test.status = QuickTest.STATUS_COMPLETED
    quick_test.completed_at = timezone.now()
    quick_test.save()

    # Log to MLflow
    try:
        from ml_platform.experiments.services import MLflowService
        mlflow_service = MLflowService()
        mlflow_run_id = mlflow_service.log_quick_test(
            quick_test=quick_test,
            feature_config=quick_test.feature_config,
            model_config=quick_test.model_config,
            dataset=quick_test.feature_config.dataset
        )

        # Store MLflow run ID for reference
        quick_test.mlflow_run_id = mlflow_run_id
        quick_test.save(update_fields=['mlflow_run_id'])

    except Exception as e:
        logger.warning(f"Failed to log to MLflow: {e}")
        # Don't fail the pipeline completion if MLflow logging fails
```

### Step 6.6: Add MLflow Run ID to QuickTest Model

**File: `ml_platform/models.py`** (add field to QuickTest)

```python
class QuickTest(models.Model):
    # ... existing fields ...

    # MLflow tracking
    mlflow_run_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="MLflow run ID for this Quick Test"
    )
```

### Step 6.7: API Endpoints for MLflow Data

**File: `ml_platform/experiments/api.py`**

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings

from ml_platform.experiments.services import MLflowService


@api_view(['GET'])
def get_experiment_runs(request, model_endpoint_id, dataset_id):
    """
    Get all MLflow runs for a model/dataset combination.

    GET /api/experiments/{model_endpoint_id}/{dataset_id}/runs/
    """
    from ml_platform.models import ModelEndpoint, Dataset

    model_endpoint = ModelEndpoint.objects.get(pk=model_endpoint_id)
    dataset = Dataset.objects.get(pk=dataset_id)

    service = MLflowService()
    runs = service.get_experiment_runs(
        model_endpoint_name=model_endpoint.name,
        dataset_name=dataset.name,
        run_type=request.query_params.get('run_type', 'all'),
        max_results=int(request.query_params.get('max_results', 100))
    )

    return Response({
        'success': True,
        'data': {
            'runs': runs,
            'count': len(runs),
        }
    })


@api_view(['GET'])
def get_heatmap_data(request, model_endpoint_id, dataset_id):
    """
    Get heatmap data for experiment visualization.

    GET /api/experiments/{model_endpoint_id}/{dataset_id}/heatmap/
    Query params: metric, x_axis, y_axis
    """
    from ml_platform.models import ModelEndpoint, Dataset

    model_endpoint = ModelEndpoint.objects.get(pk=model_endpoint_id)
    dataset = Dataset.objects.get(pk=dataset_id)

    service = MLflowService()
    heatmap_data = service.get_heatmap_data(
        model_endpoint_name=model_endpoint.name,
        dataset_name=dataset.name,
        metric=request.query_params.get('metric', 'recall_at_100'),
        x_axis=request.query_params.get('x_axis', 'buyer_tensor_dim'),
        y_axis=request.query_params.get('y_axis', 'product_tensor_dim'),
    )

    return Response({
        'success': True,
        'data': heatmap_data
    })


@api_view(['POST'])
def compare_runs(request):
    """
    Compare multiple MLflow runs.

    POST /api/experiments/compare/
    Body: {"run_ids": ["abc123", "def456"]}
    """
    run_ids = request.data.get('run_ids', [])

    if len(run_ids) < 2:
        return Response({
            'success': False,
            'error': 'At least 2 run IDs required for comparison'
        }, status=400)

    service = MLflowService()
    comparison = service.compare_runs(run_ids)

    return Response({
        'success': True,
        'data': comparison
    })


@api_view(['GET'])
def get_mlflow_ui_url(request):
    """
    Get the MLflow UI URL for direct access.

    GET /api/experiments/mlflow-url/
    """
    return Response({
        'success': True,
        'data': {
            'url': settings.MLFLOW_TRACKING_URI
        }
    })
```

### Step 6.8: Experiments Page UI Integration

**File: `templates/ml_platform/model_experiments.html`** (add MLflow section)

```html
<!-- MLflow Experiment Analysis Section -->
<div class="card mt-4">
    <div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0">Experiment Analysis</h5>
        <a href="#" id="openMlflowBtn" class="btn btn-sm btn-outline-primary" target="_blank">
            Open MLflow UI ↗
        </a>
    </div>
    <div class="card-body">
        <!-- Tabs for different views -->
        <ul class="nav nav-tabs" id="analysisTab" role="tablist">
            <li class="nav-item">
                <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#runsTable">
                    Runs Table
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#heatmapView">
                    Heatmap
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#compareView">
                    Compare
                </button>
            </li>
        </ul>

        <div class="tab-content mt-3">
            <!-- Runs Table Tab -->
            <div class="tab-pane fade show active" id="runsTable">
                <div class="table-responsive">
                    <table class="table table-hover" id="mlflowRunsTable">
                        <thead>
                            <tr>
                                <th><input type="checkbox" id="selectAllRuns"></th>
                                <th>Run Name</th>
                                <th>R@100</th>
                                <th>R@50</th>
                                <th>R@10</th>
                                <th>Loss</th>
                                <th>Features</th>
                                <th>Model</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody id="mlflowRunsBody">
                            <!-- Populated via JavaScript -->
                        </tbody>
                    </table>
                </div>
                <button class="btn btn-primary" id="compareSelectedBtn" disabled>
                    Compare Selected
                </button>
            </div>

            <!-- Heatmap Tab -->
            <div class="tab-pane fade" id="heatmapView">
                <div class="row mb-3">
                    <div class="col-md-3">
                        <label>Metric</label>
                        <select class="form-select" id="heatmapMetric">
                            <option value="recall_at_100">Recall@100</option>
                            <option value="recall_at_50">Recall@50</option>
                            <option value="recall_at_10">Recall@10</option>
                            <option value="loss">Loss</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label>X Axis</label>
                        <select class="form-select" id="heatmapXAxis">
                            <option value="buyer_tensor_dim">Buyer Tensor Dim</option>
                            <option value="product_tensor_dim">Product Tensor Dim</option>
                            <option value="epochs">Epochs</option>
                            <option value="learning_rate">Learning Rate</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label>Y Axis</label>
                        <select class="form-select" id="heatmapYAxis">
                            <option value="product_tensor_dim">Product Tensor Dim</option>
                            <option value="buyer_tensor_dim">Buyer Tensor Dim</option>
                            <option value="buyer_crosses_count">Cross Features</option>
                        </select>
                    </div>
                    <div class="col-md-3 d-flex align-items-end">
                        <button class="btn btn-primary" id="refreshHeatmap">
                            Refresh
                        </button>
                    </div>
                </div>
                <div id="heatmapContainer" style="height: 400px;">
                    <!-- Heatmap rendered here -->
                </div>
            </div>

            <!-- Compare Tab -->
            <div class="tab-pane fade" id="compareView">
                <div id="comparisonResult">
                    <p class="text-muted">Select runs from the Runs Table to compare.</p>
                </div>
            </div>
        </div>
    </div>
</div>
```

### Step 6.9: MLflow Cost Estimate

| Component | Monthly Cost (Low Usage) | Monthly Cost (High Usage) |
|-----------|--------------------------|---------------------------|
| Cloud Run (MLflow server) | $5-15 (scales to zero) | $30-50 |
| Cloud SQL (PostgreSQL) | $10-20 (db-f1-micro) | $30-50 |
| GCS (artifacts) | $1-5 | $5-20 |
| **Total** | **~$20-40/month** | **~$70-120/month** |

### MLflow Built-in Features You Get

1. **Runs Table** - Sortable, filterable list of all experiment runs
2. **Parallel Coordinates** - Visualize param → metric relationships
3. **Scatter Plots** - Parameter vs metric analysis
4. **Run Comparison** - Side-by-side diff of params and metrics
5. **REST API** - Query experiments programmatically
6. **Web UI** - Full-featured experiment browser

---

## Phase 7: Pre-built Docker Image for Fast Cloud Build

> **Status: COMPLETED** (2025-12-15)
> - Artifact Registry: `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder`
> - Image: `tfx-compiler:latest` (TFX 1.15.0, KFP 2.15.2)
> - Django setting: `TFX_COMPILER_IMAGE` in `config/settings.py`
> - Services updated: `ml_platform/experiments/services.py` uses pre-built image

### Objective
Eliminate the 12+ minute Cloud Build setup time by creating a pre-built Docker image with all TFX dependencies pre-installed.

### Current Problem

```
Cloud Build Execution Timeline (Current):
├── Download python:3.10 image      ~30 seconds
├── pip install tfx>=1.15.0         ~3-4 minutes
├── pip install kfp>=2.0.0          ~2-3 minutes
├── pip install tensorflow          ~3-4 minutes (pulled as TFX dependency)
├── pip install other deps          ~1-2 minutes
├── Download compile script         ~1 second
├── Compile TFX pipeline            ~30 seconds
└── Submit to Vertex AI             ~5 seconds
                                    ─────────────
                          Total:    ~12-15 minutes
```

### Solution: Pre-built Image

```
Cloud Build Execution Timeline (With Pre-built Image):
├── Pull pre-built image (cached)   ~5 seconds
├── Download compile script         ~1 second
├── Compile TFX pipeline            ~30 seconds
└── Submit to Vertex AI             ~5 seconds
                                    ─────────────
                          Total:    ~1-2 minutes
```

### Step 7.1: Create Dockerfile for TFX Builder ✅

**File: `cloudbuild/tfx-builder/Dockerfile`** (IMPLEMENTED)

```dockerfile
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install TFX first - it pulls compatible versions of tensorflow, apache-beam, etc.
RUN pip install --no-cache-dir tfx==1.15.0

# Install KFP for Kubeflow pipeline compilation (kubeflow_v2_dag_runner)
RUN pip install --no-cache-dir kfp>=2.0.0

# Install dill (required by tfx_bsl/beam, must be compatible with apache-beam)
RUN pip install --no-cache-dir "dill>=0.3.1.1,<0.3.2"

# Install additional Google Cloud SDKs
RUN pip install --no-cache-dir \
    google-cloud-aiplatform>=1.38.0 \
    google-cloud-storage>=2.14.0 \
    google-cloud-bigquery>=3.14.0

# Verify installations
RUN python -c "import tfx; print(f'TFX version: {tfx.__version__}')"
RUN python -c "import kfp; print(f'KFP version: {kfp.__version__}')"
RUN python -c "from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner; print('Runner OK')"

WORKDIR /workspace
CMD ["python", "--version"]
```

**Key learnings from implementation:**
- TFX must be installed first to get compatible dependency versions
- KFP is not bundled with TFX 1.15.0, must install separately
- dill version must be `<0.3.2` to be compatible with apache-beam

### Step 7.2: Build and Push to Artifact Registry ✅

```bash
# Create Artifact Registry repository (one-time) - DONE
gcloud artifacts repositories create tfx-builder \
    --repository-format=docker \
    --location=europe-central2 \
    --description="TFX Pipeline Builder images" \
    --project=b2b-recs

# Build using Cloud Build (recommended) - DONE
cd cloudbuild/tfx-builder
gcloud builds submit --config=cloudbuild.yaml --project=b2b-recs

# Alternative: Build locally
gcloud auth configure-docker europe-central2-docker.pkg.dev
docker build -t europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest .
docker push europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest
```

**Current image location:**
```
europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest
europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:v1.0.0
```

> **Note:** Currently using `b2b-recs` project for development. For production multi-tenant deployment, migrate to dedicated `b2b-recs-platform` project.

### Step 7.3: Update services.py to Use Pre-built Image ✅

**Changes to `ml_platform/experiments/services.py`** (IMPLEMENTED):

```python
# Django setting added to config/settings.py:
TFX_COMPILER_IMAGE = os.environ.get(
    'TFX_COMPILER_IMAGE',
    'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest'
)

# In services.py - now uses setting:
tfx_compiler_image = getattr(
    settings, 'TFX_COMPILER_IMAGE',
    'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest'
)

cloudbuild_v1.BuildStep(
    name=tfx_compiler_image,  # Pre-built image with all dependencies
    entrypoint='bash',
    args=['-c', '''
        python -c "from google.cloud import storage; ..."
        python /tmp/compile_and_submit.py ...
    ''']
)
# Timeout reduced from 1800s to 600s since build is now much faster
```

### Step 7.4: Cloud Build Config for Image Updates

**File: `cloudbuild/tfx-builder/cloudbuild.yaml`**

```yaml
# Use this to rebuild the TFX compiler image when dependencies change
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'europe-central2-docker.pkg.dev/$PROJECT_ID/tfx-builder/tfx-compiler:latest'
      - '-t'
      - 'europe-central2-docker.pkg.dev/$PROJECT_ID/tfx-builder/tfx-compiler:$SHORT_SHA'
      - '.'

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'europe-central2-docker.pkg.dev/$PROJECT_ID/tfx-builder/tfx-compiler:latest'

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'europe-central2-docker.pkg.dev/$PROJECT_ID/tfx-builder/tfx-compiler:$SHORT_SHA'

images:
  - 'europe-central2-docker.pkg.dev/$PROJECT_ID/tfx-builder/tfx-compiler:latest'
  - 'europe-central2-docker.pkg.dev/$PROJECT_ID/tfx-builder/tfx-compiler:$SHORT_SHA'

options:
  logging: CLOUD_LOGGING_ONLY
```

### Expected Results After Implementation

| Metric | Before (python:3.10) | After (pre-built) |
|--------|---------------------|-------------------|
| Image pull time | ~30s | ~5s (cached) |
| Dependency install | ~10-12 min | 0 (pre-installed) |
| Total build time | ~12-15 min | ~1-2 min |
| "Quick Test" worthy | No | Yes |

### Maintenance Notes

1. **When to rebuild the image**:
   - TFX version upgrade
   - New dependencies needed
   - Security patches for base image

2. **Version strategy**:
   - Use `latest` for active development
   - Tag stable versions (v1.0.0, v1.1.0) for production
   - Keep last 3 versions for rollback

3. **Cost**:
   - Artifact Registry storage: ~$0.10/GB/month
   - Image size: ~2-3 GB
   - Monthly cost: ~$0.30

### Multi-Tenant SaaS Architecture

The TFX compiler image is a **shared resource** hosted in a central platform project and used by all client projects. This is critical for the SaaS architecture where each client has their own isolated GCP project.

#### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         b2b-recs-platform                                │
│                      (SaaS Management Project)                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Artifact Registry: europe-central2-docker.pkg.dev                 │  │
│  │                                                                    │  │
│  │  tfx-builder/                                                      │  │
│  │  └── tfx-compiler:latest    ← Built ONCE, used by ALL clients     │  │
│  │      └── tfx-compiler:v1.0.0                                       │  │
│  │                                                                    │  │
│  │  IAM Policy:                                                       │  │
│  │  ├── client-a-cb@cloudbuild.gsa → artifactregistry.reader         │  │
│  │  ├── client-b-cb@cloudbuild.gsa → artifactregistry.reader         │  │
│  │  └── client-c-cb@cloudbuild.gsa → artifactregistry.reader         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
     ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
     │  client-a   │         │  client-b   │         │  client-c   │
     │             │         │             │         │             │
     │ Django App  │         │ Django App  │         │ Django App  │
     │     │       │         │     │       │         │     │       │
     │     ▼       │         │     ▼       │         │     ▼       │
     │ Cloud Build │         │ Cloud Build │         │ Cloud Build │
     │  (pulls     │         │  (pulls     │         │  (pulls     │
     │   shared    │         │   shared    │         │   shared    │
     │   image)    │         │   image)    │         │   image)    │
     │     │       │         │     │       │         │     │       │
     │     ▼       │         │     ▼       │         │     ▼       │
     │ Vertex AI   │         │ Vertex AI   │         │ Vertex AI   │
     └─────────────┘         └─────────────┘         └─────────────┘
```

#### Image Location

The TFX compiler image is hosted at:
```
europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest
```

**Note**: The image is in the `b2b-recs-platform` project (SaaS management), NOT in individual client projects.

#### Why Centralized Image?

| Approach | Pros | Cons |
|----------|------|------|
| **Centralized (chosen)** | Single image to maintain, consistent versions, update once for all clients | Requires cross-project IAM |
| Per-client image | Full isolation | N copies, N updates needed, wasteful |
| Public image | No IAM needed | Anyone can pull (minor security concern) |

#### Step 7.5: Grant Client Projects Access

For each new client project, grant Cloud Build permission to pull the shared image:

```bash
#!/bin/bash
# provision_client_image_access.sh

CLIENT_PROJECT=$1
PLATFORM_PROJECT="b2b-recs-platform"
REGION="europe-central2"

# Get Cloud Build service account for client project
CB_SA_NUMBER=$(gcloud projects describe $CLIENT_PROJECT --format='value(projectNumber)')
CB_SA="${CB_SA_NUMBER}@cloudbuild.gserviceaccount.com"

# Grant access to shared TFX compiler image
gcloud artifacts repositories add-iam-policy-binding tfx-builder \
    --project=$PLATFORM_PROJECT \
    --location=$REGION \
    --member="serviceAccount:$CB_SA" \
    --role="roles/artifactregistry.reader"

echo "✅ Client $CLIENT_PROJECT can now use shared TFX compiler image"
```

#### Step 7.6: Configure Django to Use Centralized Image

Make the image path configurable in Django settings:

**File: `b2b_recs/settings.py`**

```python
# TFX Pipeline Compilation
# The TFX compiler image is hosted in the central platform project
# and shared across all client projects
TFX_COMPILER_IMAGE = os.environ.get(
    'TFX_COMPILER_IMAGE',
    'europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest'
)
```

**File: `ml_platform/experiments/services.py`**

```python
from django.conf import settings

def _trigger_cloud_build(self, ...):
    # Use the centralized TFX compiler image
    build = cloudbuild_v1.Build(
        steps=[
            cloudbuild_v1.BuildStep(
                name=settings.TFX_COMPILER_IMAGE,  # Centralized image
                entrypoint='bash',
                args=['-c', '''
                    python -c "from google.cloud import storage; ..."
                    python /tmp/compile_and_submit.py ...
                ''']
            )
        ],
        # ...
    )
```

#### Client Onboarding Checklist

When provisioning a new client project, add this step to the onboarding process:

- [ ] Create client GCP project
- [ ] Set up Cloud SQL, BigQuery, GCS buckets
- [ ] Deploy Django app to Cloud Run
- [ ] **Grant Cloud Build access to shared TFX compiler image** ← NEW
- [ ] Configure static IP and Cloud NAT
- [ ] Test Quick Test pipeline submission

#### Important Notes

1. **Two Different Images**:
   - **TFX Compiler Image** (shared): Used by Cloud Build to COMPILE pipelines (this image)
   - **TFX Runtime Image** (Google's): Used by Vertex AI to RUN pipelines (`gcr.io/tfx-oss-public/tfx`)

2. **No Client Data in Compiler Image**: The compiler image contains only TFX libraries. Client data flows through their own project's GCS and Vertex AI.

3. **Version Pinning**: For production stability, consider pinning to a specific version:
   ```python
   TFX_COMPILER_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:v1.0.0'
   ```

---

## Phase 8: TFX Pipeline Bug Fixes (December 2025)

This phase documents critical bug fixes discovered during pipeline execution testing.

### Issue 1: BigQuery Project Mismatch (403 Forbidden)

**Problem**: BigQueryExampleGen was trying to run jobs in Vertex AI's internal project (`se4d1ef3f85b1926b-tp`) instead of `b2b-recs`.

**Root Cause**: `BigQueryExampleGen` uses the BigQuery Python client directly, which defaults to Application Default Credentials (ADC). In Vertex AI workers, ADC points to an internal infrastructure project.

**Solution**: Added `custom_config={'project': project_id}` to `BigQueryExampleGen`:

```python
# File: ml_platform/experiments/services.py (line 456-460)
example_gen = BigQueryExampleGen(
    query=bigquery_query,
    output_config=output_config,
    custom_config={'project': project_id}  # Explicit project
)
```

### Issue 2: TIMESTAMP Column Type Not Supported

**Problem**: TFX BigQueryExampleGen failed with `RuntimeError: BigQuery column "first_purchase_date" has non-supported type TIMESTAMP`.

**Root Cause**: TFX only supports basic types (STRING, INT64, FLOAT64, BOOL). TIMESTAMP/DATE/DATETIME are not supported.

**Solution**: Added automatic TIMESTAMP → INT64 conversion in query generation:

```python
# File: ml_platform/datasets/services.py
def generate_query(self, dataset, for_analysis=False, for_tfx=False):
    # When for_tfx=True, TIMESTAMP columns are converted:
    # UNIX_SECONDS(CAST(col AS TIMESTAMP)) AS col
```

**Affected columns are now converted**:
- `first_purchase_date` → Unix epoch seconds (INT64)
- `last_purchase_date` → Unix epoch seconds (INT64)
- `transaction_date` → Unix epoch seconds (INT64)

### Issue 3: Missing tensorflow-recommenders in TFX Container

**Problem**: Trainer failed with `ModuleNotFoundError: No module named 'tensorflow_recommenders'`.

**Root Cause**: The standard TFX container (`gcr.io/tfx-oss-public/tfx:1.15.0`) doesn't include tensorflow-recommenders.

**Solution**: Created custom training image with TFRS pre-installed:

```dockerfile
# File: cloudbuild/tfx-trainer/Dockerfile
FROM gcr.io/tfx-oss-public/tfx:1.15.0
RUN pip install --no-cache-dir tensorflow-recommenders>=0.7.3
```

Updated pipeline compilation to use custom image:

```python
# File: ml_platform/experiments/services.py (line 508-513)
custom_image = f'europe-central2-docker.pkg.dev/{project_id}/tfx-builder/tfx-trainer:latest'
runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
    config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(
        default_image=custom_image
    ),
    output_filename=output_file
)
```

### Issue 4: Embedding Dimension Mismatch in Model Towers

**Problem**: Trainer failed with `ValueError: Dimension 0 in both shapes must be equal, but are 16 and 8`.

**Root Cause**: Different features have different embedding dimensions (e.g., 16 vs 8). The `tf.concat(features, axis=1)` failed because embeddings have shape `[batch, 1, dim]` with varying `dim`.

**Solution**: Flatten embeddings before concatenation:

```python
# File: ml_platform/configs/services.py (BuyerModel and ProductModel)
# Before:
return tf.concat(features, axis=1)

# After:
flattened = [tf.reshape(f, [tf.shape(f)[0], -1]) for f in features]
return tf.concat(flattened, axis=1)
```

### Files Modified in Phase 8

| File | Changes |
|------|---------|
| `ml_platform/experiments/services.py` | BigQuery project fix, custom training image |
| `ml_platform/datasets/services.py` | TIMESTAMP → INT64 conversion for TFX |
| `ml_platform/configs/services.py` | Embedding flattening before concat |
| `cloudbuild/tfx-trainer/Dockerfile` | New custom training image with TFRS |
| `cloudbuild/tfx-trainer/cloudbuild.yaml` | Build configuration for trainer image |

### Build the Custom Training Image

```bash
cd cloudbuild/tfx-trainer
gcloud builds submit --config=cloudbuild.yaml --project=b2b-recs
```

### Current Pipeline Status

After Phase 8 fixes, the pipeline successfully progresses through:

1. ✅ **BigQueryExampleGen** - Extracts data from BigQuery with correct project
2. ✅ **StatisticsGen** - Generates data statistics
3. ✅ **SchemaGen** - Infers data schema
4. ✅ **Transform** - Applies feature preprocessing
5. ✅ **Trainer** - Training with TFRS completed

---

## Phase 9: Experiments UI Refactor (December 2025)

This phase implements a complete redesign of the Quick Test chapter UI to match the design patterns used in the Model Configs page.

### Changes Overview

**Old Design:**
- Two dropdowns (Feature Config, Model Config) + "Run Quick Test" button in header
- Training parameters in collapsible section
- Simple dialog for split strategy/sampling
- Basic experiment history list

**New Design:**
- Chapter header with "Compare" and "New Exp" buttons
- Filter bar (Status, Feature Config, Model Config, Search)
- Experiment cards with status, configs, metrics, progress
- Pagination (3 visible, scroll for 10, footer navigation)
- 2-step wizard modal for creating experiments

### New Chapter Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ Quick Test                                     [Compare] [+ New Exp]     │
├─────────────────────────────────────────────────────────────────────────────┤
│ Status: [All ▼]  Feature: [All ▼]  Model: [All ▼]  [🔍 Search...]          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🔄 Exp #3 · feats_v3 + model_v3 · Running 45%                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ✅ Exp #2 · feats_v3 + model_v2 · Recall@100: 47.3%                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Showing 1-3 of 15                     [← Prev] [1] [2] [3] [4] [5] [Next →] │
└─────────────────────────────────────────────────────────────────────────────┘
```

### New Experiment Wizard (2 Steps)

**Step 1: Select Configs**
- Feature Config dropdown with preview panel (tensor dimensions, feature list)
- Model Config dropdown with preview panel (tower layers, parameters)
- Preview panels styled like View modals in model_configs.html

**Step 2: Training Parameters**
- Data Split & Sampling (strategy, sample %, holdout days, date column)
- Training Parameters (epochs, batch size, learning rate)
- Rating Column (for ranking models)
- Summary section

### Database Changes

Added `experiment_number` field to `QuickTest` model:

```python
# ml_platform/models.py
experiment_number = models.PositiveIntegerField(
    null=True,
    blank=True,
    help_text="Sequential experiment number within the Model Endpoint"
)

@property
def display_name(self):
    """Return display name like 'Exp #1', 'Exp #2', etc."""
    return f"Exp #{self.experiment_number or self.pk}"

def assign_experiment_number(self):
    """Assign next sequential number for this Model Endpoint."""
    # Auto-increments per Model Endpoint
```

### API Changes

Updated `GET /api/quick-tests/` endpoint:

**New Parameters:**
- `page` - Page number (default: 1)
- `page_size` - Items per page (default: 10, max: 50)
- `search` - Search by experiment number or config names

**New Response Fields:**
```json
{
  "success": true,
  "quick_tests": [...],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_count": 25,
    "total_pages": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

**Updated Serializer:**
- Added `experiment_number`, `display_name`
- Added `elapsed_seconds`, `duration_seconds`
- Added `recall_at_100` for card metric display

### View Changes

Updated `model_experiments` view to set session:

```python
# ml_platform/views.py
def model_experiments(request, model_id):
    model = get_object_or_404(ModelEndpoint, id=model_id)
    request.session['model_endpoint_id'] = model_id  # Required for API
    ...
```

### Files Modified in Phase 9

| File | Changes |
|------|---------|
| `ml_platform/models.py` | Added `experiment_number` field, `display_name` property, `assign_experiment_number()` method |
| `ml_platform/migrations/0034_*.py` | Migration for experiment_number field |
| `ml_platform/experiments/api.py` | Added pagination, search, updated serializer |
| `ml_platform/experiments/services.py` | Call `assign_experiment_number()` before save |
| `ml_platform/views.py` | Set `model_endpoint_id` in session |
| `templates/ml_platform/model_experiments.html` | Complete rewrite with new chapter layout, wizard, cards |

### UI Components

**Experiment Card States:**
- `submitting` - Yellow icon, progress bar
- `running` - Blue spinning icon, progress bar
- `completed` - Green checkmark, Recall@100 metric
- `failed` - Red X, error stage
- `cancelled` - Gray icon

**Wizard Progress Pills:**
- Uses green (`#16a34a`) for current step (matches model_configs.html)
- Uses white for future steps
- Uses green border for completed steps

**Footer Buttons:**
- Blue square navigation buttons (`btn-neu-nav`) in footer-left
- Green "Run" button (`btn-neu-save`) and red "Cancel" button (`btn-neu-cancel`) in footer-right

---

## File Reference

### Files to Create

| File | Description |
|------|-------------|
| `ml_platform/pipelines/tfx_pipeline.py` | Native TFX pipeline definition |
| `ml_platform/experiments/services.py` | MLflow integration service |
| `ml_platform/experiments/api.py` | MLflow API endpoints |
| `mlflow-server/Dockerfile` | MLflow server container |
| `mlflow-server/cloudbuild.yaml` | Cloud Build config for MLflow |

### Files to Modify

| File | Changes |
|------|---------|
| `ml_platform/pipelines/pipeline_builder.py` | Remove KFP v2 components, import from tfx_pipeline.py |
| `ml_platform/pipelines/services.py` | Update submission to use native TFX, add MLflow logging on completion |
| `ml_platform/configs/services.py` | Rebuild TrainerModuleGenerator |
| `ml_platform/models.py` | Add new QuickTest fields (`sample_percent`, `split_strategy`, `mlflow_run_id`) |
| `ml_platform/pipelines/api.py` | Accept new experiment parameters |
| `templates/ml_platform/model_experiments.html` | Add DAG visualization, metrics charts, MLflow integration |
| `requirements.txt` | Add TFX and MLflow dependencies |
| `b2b_recs/settings.py` | Add MLflow configuration settings |
| `ml_platform/urls.py` | Add MLflow API endpoints |

### Existing Related Files

| File | Purpose |
|------|---------|
| `docs/phase_datasets.md` | Dataset configuration reference |
| `docs/phase_configs.md` | Feature/Model config reference |
| `docs/tfx_code_generation.md` | Code generation details |
| `ml_platform/datasets/services.py` | BigQueryService for SQL generation |
| `past/recommenders.ipynb` | TFX example for reference |

---

## API Reference

### Updated Endpoints

| Method | Endpoint | Changes |
|--------|----------|---------|
| POST | `/api/feature-configs/{id}/quick-test/` | Add `sample_percent`, `split_strategy`, `train_ratio`, `time_split_column` |
| GET | `/api/quick-tests/{id}/` | Returns epoch_metrics in addition to final metrics |

### New Request Body (Start Quick Test)

```json
{
    "model_config_id": 3,
    "sample_percent": 10,
    "split_strategy": "random",
    "train_ratio": 0.8,
    "time_split_column": null,
    "epochs": 5,
    "batch_size": 4096,
    "learning_rate": 0.1
}
```

### New Response Fields (Quick Test Status)

```json
{
    "success": true,
    "data": {
        "quick_test_id": 42,
        "status": "completed",
        "mlflow_run_id": "abc123def456",
        "metrics": {
            "loss": 0.38,
            "recall_at_10": 0.182,
            "recall_at_50": 0.385,
            "recall_at_100": 0.473
        },
        "epoch_metrics": [
            {"epoch": 1, "loss": 0.85, "val_loss": 0.82, ...},
            {"epoch": 2, "loss": 0.52, "val_loss": 0.48, ...},
            ...
        ],
        "stage_details": [...]
    }
}
```

### MLflow API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/experiments/{model_endpoint_id}/{dataset_id}/runs/` | Get all MLflow runs for experiment |
| GET | `/api/experiments/{model_endpoint_id}/{dataset_id}/heatmap/` | Get heatmap visualization data |
| POST | `/api/experiments/compare/` | Compare multiple runs |
| GET | `/api/experiments/mlflow-url/` | Get MLflow UI URL |

### MLflow Runs Response

```json
{
    "success": true,
    "data": {
        "runs": [
            {
                "run_id": "abc123",
                "run_name": "Rich Features v2 + Deep Tower #42",
                "status": "FINISHED",
                "start_time": 1702500000000,
                "params": {
                    "feature_config_id": "12",
                    "model_config_id": "3",
                    "buyer_tensor_dim": "128",
                    "product_tensor_dim": "64",
                    "epochs": "5"
                },
                "metrics": {
                    "recall_at_100": 0.473,
                    "recall_at_50": 0.385,
                    "loss": 0.38
                }
            }
        ],
        "count": 47
    }
}
```

### MLflow Heatmap Response

```json
{
    "success": true,
    "data": {
        "metric": "recall_at_100",
        "x_axis": {
            "name": "buyer_tensor_dim",
            "values": ["64", "96", "128"]
        },
        "y_axis": {
            "name": "product_tensor_dim",
            "values": ["32", "64", "96"]
        },
        "cells": [
            {"x": "64", "y": "32", "value": 0.42, "run_id": "abc123"},
            {"x": "128", "y": "64", "value": 0.473, "run_id": "def456"}
        ],
        "best": {"x": "128", "y": "64", "value": 0.473, "run_id": "def456"}
    }
}
```

---

## Testing Guide

### Manual Testing Checklist

#### Phase 1: TFX Pipeline
- [ ] Pipeline compiles without errors
- [ ] Pipeline submits to Vertex AI
- [ ] All 5 stages execute successfully
- [ ] Artifacts created in GCS

#### Phase 2: Trainer Generator
- [ ] Generated code compiles (syntax check)
- [ ] Buyer tower embeddings match FeatureConfig
- [ ] Product tower embeddings match FeatureConfig
- [ ] Tower layers match ModelConfig
- [ ] Metrics exported to JSON

#### Phase 3: Experiment Parameters
- [ ] Sample 5% produces ~5% of rows
- [ ] Random split produces ~80/20 split
- [ ] Time-based split works with date column
- [ ] Custom ratio produces expected split

#### Phase 4: Pipeline Visualization
- [ ] DAG renders correctly
- [ ] Status updates in real-time
- [ ] Completed stages show green checkmark
- [ ] Running stage shows spinner

#### Phase 5: Metrics Display
- [ ] Final metrics displayed correctly
- [ ] Epoch chart renders
- [ ] Comparison table sortable
- [ ] Filters work correctly

#### Phase 6: MLflow Integration
- [ ] MLflow server deploys to Cloud Run
- [ ] Cloud SQL database created and accessible
- [ ] Django can connect to MLflow tracking URI
- [ ] Quick Test completion logs to MLflow
- [ ] MLflow run ID stored in QuickTest record
- [ ] `/api/experiments/.../runs/` returns run list
- [ ] `/api/experiments/.../heatmap/` returns visualization data
- [ ] Run comparison works correctly
- [ ] "Open MLflow UI" link works
- [ ] Heatmap renders in Experiments page

### Test Dataset

Use a small test dataset for development:
- ~10,000 rows
- 3-5 features per tower
- No cross features initially

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Pipeline compilation fails | Missing TFX dependencies | Install `tfx>=1.14.0` |
| BigQueryExampleGen fails | Wrong BQ location | Use `dataset.bq_location` |
| Transform fails | Invalid preprocessing_fn | Check generated code syntax |
| Trainer fails | Mismatched feature names | Verify FeatureConfig matches schema |
| Metrics not found | Wrong GCS path | Check `metrics_output_path` |
| 403 Forbidden on BigQuery | Wrong project in ADC | Add `custom_config={'project': project_id}` to BigQueryExampleGen |
| TIMESTAMP type not supported | TFX doesn't support TIMESTAMP | Use `for_tfx=True` in `generate_training_query()` to convert to INT64 |
| ModuleNotFoundError: tensorflow_recommenders | Standard TFX image missing TFRS | Use custom image `tfx-trainer:latest` with TFRS |
| ValueError: Dimension mismatch in concat | Embeddings have shape `[batch,1,dim]` with varying dim | Flatten embeddings before concat with `tf.reshape` |

### Debug Commands

```bash
# Check pipeline compilation
python -c "from ml_platform.pipelines.tfx_pipeline import create_quicktest_pipeline; print('OK')"

# Validate generated trainer code
python -c "exec(open('trainer_module.py').read()); print('Syntax OK')"

# Test GCS access
gsutil ls gs://b2b-recs-quicktest-artifacts/
```

---

## Next Steps After Implementation

1. **Add Evaluator Component** - For model quality validation
2. **Add Pusher Component** - For full training → deployment
3. **Implement Ranking Models** - Update TrainerModuleGenerator
4. **Implement Multitask Models** - Combined retrieval + ranking
5. **Add Hyperparameter Tuning** - Vertex AI Vizier integration

---

## Related Documentation

- [Phase: Datasets](phase_datasets.md) - Dataset configuration
- [Phase: Configs](phase_configs.md) - Feature and Model configs
- [TFX Code Generation](tfx_code_generation.md) - Code generation details
- [Implementation Overview](../implementation.md) - Overall system architecture
