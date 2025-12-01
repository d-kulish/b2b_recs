# Phase: Experiments Domain

## Document Purpose
This document provides detailed specifications for implementing the **Experiments** domain in the ML Platform. The Experiments domain enables comparison of training results via MLflow heatmaps.

**Last Updated**: 2025-12-01

---

## Overview

### Purpose
The Experiments domain allows users to:
1. Compare Quick Test and Full Training results across configurations
2. Visualize metrics via heatmaps (Recall@k by configuration parameters)
3. Identify the best-performing configurations
4. Track experiment history and decisions

### Key Principle
**MLflow is for comparison and visualization, ML Metadata is for lineage.** Users use MLflow heatmaps to answer "which config is best?", while MLMD answers "what exact artifacts produced this model?".

### Tool Responsibilities

| Tool | Purpose |
|------|---------|
| **MLflow** | Experiment tracking, metrics comparison, heatmaps, parameter search visualization |
| **ML Metadata (MLMD)** | Artifact lineage, schema versions, vocabulary tracking, production model registry |

---

## User Interface

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

### Phase 1: MLflow Integration
- [ ] Deploy MLflow server to Cloud Run
- [ ] Create MLflowService class
- [ ] Implement log_quick_test method
- [ ] Implement log_training_run method

### Phase 2: Experiments Dashboard
- [ ] Create experiments sub-app structure
- [ ] Create experiments dashboard page
- [ ] Implement summary statistics cards
- [ ] Create recent experiments list

### Phase 3: Heatmap Visualization
- [ ] Implement HeatmapService
- [ ] Create heatmap API endpoint
- [ ] Build frontend heatmap component
- [ ] Add axis selection controls

### Phase 4: Comparison Tools
- [ ] Implement run comparison API
- [ ] Create comparison view UI
- [ ] Show configuration diffs
- [ ] Add recommendations based on comparison

---

## Dependencies on Other Domains

### Depends On
- **Engineering & Testing Domain**: Quick Test results
- **Training Domain**: Full Training results

### Depended On By
- **Deployment Domain**: Best model selection for deployment

---

## Related Documentation

- [Implementation Overview](../implementation.md)
- [Engineering & Testing Phase](phase_engineering_testing.md)
- [Training Phase](phase_training.md)
- [Deployment Phase](phase_deployment.md)
