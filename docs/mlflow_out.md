# MLflow Removal Migration Plan

## Executive Summary

This document outlines the plan to remove MLflow from the B2B Recommendations system and replace it with direct GCS-based metrics storage. This simplification will reduce infrastructure costs, eliminate cold-start latency, and streamline the architecture without losing any functionality.

---

## Table of Contents

1. [Background & Motivation](#background--motivation)
2. [Current Architecture](#current-architecture)
3. [Target Architecture](#target-architecture)
4. [Benefits](#benefits)
5. [Migration Steps](#migration-steps)
6. [File Reference](#file-reference)
7. [Rollback Plan](#rollback-plan)
8. [Timeline](#timeline)

---

## Background & Motivation

### Why MLflow Was Added

MLflow was originally integrated to provide:
- Experiment tracking during model training
- Metrics storage (loss curves, recall metrics, weight statistics)
- Experiment comparison capabilities

### Why MLflow Should Be Removed

After implementing the training history caching system (see `docs/phase_experiments.md`), MLflow's role has been significantly reduced:

| Feature | MLflow Usage | Reality |
|---------|--------------|---------|
| Training tab visualization | Bypassed (uses Django cache) | Not needed |
| Experiment comparison | Custom Django UI | Not needed |
| Model registry | Not used | Models stored in GCS |
| MLflow UI | Not used | Custom UI in Django |
| Real-time metrics | Not used | Batch processing only |

**MLflow is now just a pass-through metrics database** that adds:
- Infrastructure cost (~$30-50/month for Cloud Run + Cloud SQL)
- Cold-start latency (5-15 seconds on first request)
- Architectural complexity (extra service to maintain)
- Network latency during training (REST API calls every epoch)

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRAINING (Vertex AI)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   trainer.py                                                                 │
│       │                                                                      │
│       ├── MLflowCallback.on_epoch_end()                                      │
│       │       └── _mlflow_client.log_metric() ──────┐                        │
│       │                                             │                        │
│       ├── WeightNormCallback.on_epoch_end()         │                        │
│       │       └── _mlflow_client.log_metric() ──────┤                        │
│       │                                             │   REST API calls       │
│       ├── WeightStatsCallback.on_epoch_end()        │   (per epoch)          │
│       │       └── _mlflow_client.log_metric() ──────┤                        │
│       │       └── _mlflow_client.log_param()  ──────┤                        │
│       │                                             │                        │
│       └── GradientStatsCallback.on_epoch_end()      │                        │
│               └── _mlflow_client.log_metric() ──────┤                        │
│               └── _mlflow_client.log_param()  ──────┘                        │
│                                                     │                        │
│   At training completion:                           │                        │
│       └── _write_mlflow_info() ─────────────────────┼──► GCS: mlflow_info.json
│                                                     │                        │
└─────────────────────────────────────────────────────┼────────────────────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MLFLOW SERVER (Cloud Run)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│   mlflow_server/                                                             │
│       ├── Dockerfile                                                         │
│       ├── entrypoint.sh                                                      │
│       └── requirements.txt                                                   │
│                                                                              │
│   REST API endpoints:                                                        │
│       /api/2.0/mlflow/runs/log-metric                                        │
│       /api/2.0/mlflow/runs/log-parameter                                     │
│       /api/2.0/mlflow/metrics/get-history                                    │
│       /api/2.0/mlflow/runs/get                                               │
│                                 │                                            │
└─────────────────────────────────┼────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MLFLOW DATABASE (Cloud SQL)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│   PostgreSQL instance storing:                                               │
│       - experiments table                                                    │
│       - runs table                                                           │
│       - metrics table (millions of rows)                                     │
│       - params table                                                         │
│       - tags table                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ (50+ REST API calls to fetch history)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DJANGO APP (Cloud Run)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│   ml_platform/experiments/                                                   │
│       ├── mlflow_service.py ◄─── Fetches from MLflow REST API                │
│       ├── training_cache_service.py ◄─── Caches to Django DB                 │
│       └── services.py ◄─── Reads mlflow_info.json from GCS                   │
│                                                                              │
│   QuickTest.training_history_json ◄─── Cached training data                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Current Data Flow

1. **During training:** Callbacks make REST API calls to MLflow server every epoch
2. **At completion:** Trainer writes `mlflow_info.json` to GCS with run_id
3. **Django reads:** `services.py` reads `mlflow_info.json` to get run_id
4. **Cache population:** `training_cache_service.py` fetches from MLflow → stores in Django DB
5. **UI display:** Reads from `QuickTest.training_history_json` (cached)

### Problems with Current Architecture

1. **Network overhead:** 140+ metrics × 50 epochs = 7,000+ REST API calls per training run
2. **Cold start:** MLflow server takes 5-15 seconds to start after idle
3. **Cost:** Cloud Run + Cloud SQL instances just for metrics storage
4. **Complexity:** Extra service to deploy, monitor, and maintain
5. **Single point of failure:** MLflow server issues affect all experiments

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRAINING (Vertex AI)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   trainer.py                                                                 │
│       │                                                                      │
│       ├── MetricsCollector (in-memory dict)                                  │
│       │       metrics = {                                                    │
│       │           'epochs': [0, 1, 2, ...],                                  │
│       │           'loss': {'train': [...], 'val': [...]},                    │
│       │           'gradient': {...},                                         │
│       │           'weight_stats': {...},                                     │
│       │           'gradient_stats': {...},                                   │
│       │           ...                                                        │
│       │       }                                                              │
│       │                                                                      │
│       ├── MetricsCallback.on_epoch_end()                                     │
│       │       └── metrics_collector.log_metric()  (in-memory)                │
│       │                                                                      │
│       ├── WeightStatsCallback.on_epoch_end()                                 │
│       │       └── metrics_collector.log_weight_stats()  (in-memory)          │
│       │                                                                      │
│       └── GradientStatsCallback.on_epoch_end()                               │
│               └── metrics_collector.log_gradient_stats()  (in-memory)        │
│                                                                              │
│   At training completion:                                                    │
│       └── metrics_collector.save_to_gcs() ──────────► GCS: training_metrics.json
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                                              │
                                                              │ (single JSON file)
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               GCS BUCKET                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│   gs://bucket/quick_tests/{id}/                                              │
│       ├── training_metrics.json  ◄── Complete training history               │
│       ├── model/                     (loss, metrics, weights, gradients)     │
│       └── embeddings/                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                                              │
                                                              │ (single file read)
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DJANGO APP (Cloud Run)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│   ml_platform/experiments/                                                   │
│       ├── training_cache_service.py                                          │
│       │       └── Reads training_metrics.json from GCS                       │
│       │       └── Stores in QuickTest.training_history_json                  │
│       │                                                                      │
│       └── services.py                                                        │
│               └── Triggers cache on experiment completion                    │
│                                                                              │
│   DELETED:                                                                   │
│       ├── mlflow_service.py  ✗                                               │
│                                                                              │
│   QuickTest.training_history_json ◄─── Cached training data                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### New Data Flow

1. **During training:** Callbacks write to in-memory `MetricsCollector` (zero network calls)
2. **At completion:** `MetricsCollector.save_to_gcs()` uploads single JSON file
3. **Django reads:** `training_cache_service.py` reads JSON from GCS → stores in Django DB
4. **UI display:** Reads from `QuickTest.training_history_json` (cached)

---

## Benefits

### Cost Savings

| Resource | Current (MLflow) | After Removal | Savings |
|----------|------------------|---------------|---------|
| MLflow Cloud Run | ~$20/month | $0 | $20/month |
| MLflow Cloud SQL | ~$30/month | $0 | $30/month |
| **Total** | **~$50/month** | **$0** | **~$600/year** |

### Performance Improvements

| Metric | Current (MLflow) | After Removal | Improvement |
|--------|------------------|---------------|-------------|
| Training overhead | 7,000+ API calls | 1 file upload | 99.99% reduction |
| Cold start delay | 5-15 seconds | 0 seconds | Eliminated |
| Cache population | 50+ API calls | 1 file read | 98% reduction |

### Architectural Simplification

| Aspect | Current | After |
|--------|---------|-------|
| Services to maintain | 3 (Django, MLflow Server, MLflow DB) | 1 (Django) |
| Deployment complexity | High | Low |
| Failure points | Multiple | Fewer |
| Code to maintain | ~1500 lines MLflow-related | ~200 lines |

---

## Migration Steps

### Phase 1: Create MetricsCollector (Trainer Side)

**Goal:** Replace MLflow callbacks with in-memory collection + GCS upload.

#### Step 1.1: Create MetricsCollector Class

**File:** `ml_platform/configs/services.py`

Replace the `MLflowRestClient` class and related functions with a new `MetricsCollector`:

```python
class MetricsCollector:
    """
    In-memory metrics collector that saves to GCS at training completion.

    Replaces MLflow with direct JSON storage for simplicity and performance.
    """

    def __init__(self, gcs_output_path: str):
        self.gcs_output_path = gcs_output_path
        self.metrics = {
            'epochs': [],
            'loss': {},
            'gradient': {},
            'weight_stats': {'query': {}, 'candidate': {}},
            'gradient_stats': {'query': {}, 'candidate': {}},
            'final_metrics': {},
            'params': {},
        }
        self._current_epoch = -1

    def log_metric(self, name: str, value: float, step: int = None):
        """Log a metric value (equivalent to mlflow.log_metric)."""
        # Handle epoch tracking
        if step is not None and step > self._current_epoch:
            self._current_epoch = step
            self.metrics['epochs'].append(step)

        # Categorize metric by prefix
        if name.startswith('final_') or name.startswith('test_'):
            self.metrics['final_metrics'][name] = value
        elif 'loss' in name:
            if name not in self.metrics['loss']:
                self.metrics['loss'][name] = []
            self.metrics['loss'][name].append(value)
        elif 'weight_norm' in name:
            key = name.replace('_weight_norm', '')
            if key not in self.metrics['gradient']:
                self.metrics['gradient'][key] = []
            self.metrics['gradient'][key].append(value)
        # ... additional categorization

    def log_param(self, name: str, value):
        """Log a parameter (equivalent to mlflow.log_param)."""
        self.metrics['params'][name] = value

    def log_weight_stats(self, tower: str, stats: dict, histogram: dict = None):
        """Log weight statistics for a tower."""
        for stat_name, value in stats.items():
            if stat_name not in self.metrics['weight_stats'][tower]:
                self.metrics['weight_stats'][tower][stat_name] = []
            self.metrics['weight_stats'][tower][stat_name].append(value)

        if histogram:
            self.metrics['weight_stats'][tower]['histogram'] = histogram

    def log_gradient_stats(self, tower: str, stats: dict, histogram: dict = None):
        """Log gradient statistics for a tower."""
        for stat_name, value in stats.items():
            if stat_name not in self.metrics['gradient_stats'][tower]:
                self.metrics['gradient_stats'][tower][stat_name] = []
            self.metrics['gradient_stats'][tower][stat_name].append(value)

        if histogram:
            self.metrics['gradient_stats'][tower]['histogram'] = histogram

    def save_to_gcs(self):
        """Save all collected metrics to GCS as JSON."""
        if not self.gcs_output_path:
            logging.warning("No GCS output path - metrics not saved")
            return

        from google.cloud import storage

        # Add metadata
        self.metrics['saved_at'] = datetime.utcnow().isoformat()
        self.metrics['available'] = True

        # Upload to GCS
        path = self.gcs_output_path[5:]  # Remove 'gs://'
        bucket_name = path.split('/')[0]
        blob_path = '/'.join(path.split('/')[1:]) + '/training_metrics.json'

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(self.metrics, indent=2),
            content_type='application/json'
        )

        logging.info(f"Saved training metrics to gs://{bucket_name}/{blob_path}")
```

#### Step 1.2: Update Callbacks

**File:** `ml_platform/configs/services.py`

Modify the callbacks to use `MetricsCollector` instead of `_mlflow_client`:

**Before (MLflowCallback):**
```python
class MLflowCallback(tf.keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs=None):
        if _mlflow_client and logs:
            for metric_name, value in logs.items():
                _mlflow_client.log_metric(metric_name, float(value), step=epoch)
```

**After (MetricsCallback):**
```python
class MetricsCallback(tf.keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs=None):
        if _metrics_collector and logs:
            for metric_name, value in logs.items():
                _metrics_collector.log_metric(metric_name, float(value), step=epoch)
```

Similar changes for:
- `WeightNormCallback` → use `_metrics_collector.log_metric()`
- `WeightStatsCallback` → use `_metrics_collector.log_weight_stats()`
- `GradientStatsCallback` → use `_metrics_collector.log_gradient_stats()`

#### Step 1.3: Update Training Completion

**File:** `ml_platform/configs/services.py` (in `_generate_run_fn()`)

**Before:**
```python
# At end of training
if _mlflow_client:
    _mlflow_client.end_run()
if mlflow_run_id and gcs_output_path:
    _write_mlflow_info(gcs_output_path, mlflow_run_id)
```

**After:**
```python
# At end of training
if _metrics_collector:
    _metrics_collector.save_to_gcs()
    logging.info("Training metrics saved to GCS")
```

### Phase 2: Update Django to Read from GCS

**Goal:** Replace MLflow fetching with direct GCS JSON reading.

#### Step 2.1: Modify TrainingCacheService

**File:** `ml_platform/experiments/training_cache_service.py`

**Before:**
```python
def cache_training_history(self, quick_test) -> bool:
    if not quick_test.mlflow_run_id:
        return False

    mlflow_service = MLflowService()
    full_history = mlflow_service.get_training_history(quick_test.mlflow_run_id)
    # ... process and cache
```

**After:**
```python
def cache_training_history(self, quick_test) -> bool:
    if not quick_test.gcs_artifacts_path:
        return False

    # Read training_metrics.json from GCS
    full_history = self._read_training_metrics_from_gcs(quick_test.gcs_artifacts_path)
    if not full_history:
        return False

    # ... process and cache (same as before)

def _read_training_metrics_from_gcs(self, gcs_path: str) -> Optional[Dict]:
    """Read training_metrics.json from GCS."""
    from google.cloud import storage

    try:
        path = gcs_path[5:]  # Remove 'gs://'
        bucket_name = path.split('/')[0]
        blob_path = '/'.join(path.split('/')[1:]) + '/training_metrics.json'

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)

        if not blob.exists():
            logger.info(f"training_metrics.json not found at {gcs_path}")
            return None

        content = blob.download_as_string().decode('utf-8')
        return json.loads(content)

    except Exception as e:
        logger.exception(f"Error reading training metrics from GCS: {e}")
        return None
```

#### Step 2.2: Update ExperimentService

**File:** `ml_platform/experiments/services.py`

Remove MLflow-specific code from `_extract_results()`:

**Before:**
```python
def _extract_results(self, quick_test):
    # ... existing code ...

    # Extract MLflow run ID from mlflow_info.json
    try:
        mlflow_info_path = f"{quick_test.gcs_artifacts_path}/mlflow_info.json"
        # ... read and store mlflow_run_id
```

**After:**
```python
def _extract_results(self, quick_test):
    # ... existing code ...

    # No MLflow extraction needed - metrics come from training_metrics.json
    # The training_cache_service will read directly from GCS
```

### Phase 3: Remove MLflow Infrastructure

**Goal:** Delete all MLflow-related code and infrastructure.

#### Step 3.1: Delete MLflow Server

**Files to delete:**
```
mlflow_server/
├── Dockerfile          ✗ DELETE
├── README.md           ✗ DELETE
├── cloudbuild.yaml     ✗ DELETE
├── entrypoint.sh       ✗ DELETE
└── requirements.txt    ✗ DELETE
```

**Cloud resources to delete:**
- Cloud Run service: `mlflow-server`
- Cloud SQL instance: (MLflow PostgreSQL database)
- IAM service account permissions for MLflow

#### Step 3.2: Delete MLflow Service

**File to delete:**
```
ml_platform/experiments/mlflow_service.py  ✗ DELETE (entire file)
```

#### Step 3.3: Clean Up Code References

**Files to modify:**

| File | Changes |
|------|---------|
| `ml_platform/experiments/api.py` | Remove MLflow imports and histogram endpoint |
| `ml_platform/experiments/urls.py` | Remove histogram-data URL pattern |
| `ml_platform/experiments/services.py` | Remove MLflow environment variable, mlflow_info reading |
| `ml_platform/experiments/artifact_service.py` | Remove MLflow references |
| `ml_platform/models.py` | Keep `mlflow_run_id` field (for backward compatibility) or remove |
| `config/settings.py` | Remove `MLFLOW_TRACKING_URI` setting |
| `tests/test_mlflow_integration.py` | Delete entire file |

#### Step 3.4: Update Model Fields

**File:** `ml_platform/models.py`

Option A: Keep field for backward compatibility:
```python
# QuickTest model
mlflow_run_id = models.CharField(
    max_length=255,
    blank=True,
    help_text="Deprecated: MLflow run ID (kept for historical data)"
)
```

Option B: Create migration to remove field (if no historical data needed):
```bash
python manage.py makemigrations ml_platform --name remove_mlflow_fields
```

### Phase 4: Update Documentation

**Files to update:**

| File | Changes |
|------|---------|
| `README.md` | Remove MLflow setup instructions |
| `docs/phase_experiments.md` | Update architecture diagrams |
| `docs/phase_training.md` | Update training flow documentation |
| `implementation.md` | Remove MLflow references |

---

## File Reference

### Files to Modify

| File | Purpose | Changes |
|------|---------|---------|
| `ml_platform/configs/services.py` | Trainer code generation | Replace MLflow callbacks with MetricsCollector |
| `ml_platform/experiments/training_cache_service.py` | Cache service | Read from GCS instead of MLflow |
| `ml_platform/experiments/services.py` | Experiment service | Remove MLflow info extraction |
| `ml_platform/experiments/api.py` | API endpoints | Remove histogram-data endpoint |
| `ml_platform/experiments/urls.py` | URL routing | Remove histogram-data URL |
| `config/settings.py` | Django settings | Remove MLFLOW_TRACKING_URI |
| `templates/ml_platform/model_experiments.html` | Frontend | Remove on-demand histogram fetch |

### Files to Delete

| File | Purpose |
|------|---------|
| `mlflow_server/` (entire directory) | MLflow server Docker setup |
| `ml_platform/experiments/mlflow_service.py` | MLflow REST API client |
| `tests/test_mlflow_integration.py` | MLflow integration tests |

### Cloud Resources to Delete

| Resource | Type | Location |
|----------|------|----------|
| `mlflow-server` | Cloud Run Service | europe-central2 |
| MLflow PostgreSQL | Cloud SQL Instance | europe-central2 |
| `mlflow-server` | Cloud Build Trigger | Global |

---

## Rollback Plan

If issues arise during migration:

### Immediate Rollback (Phase 1-2)
- Revert code changes via git
- Existing experiments continue to work (cached data preserved)
- MLflow server still running (not deleted until Phase 3)

### Phase 3 Rollback
- Re-deploy MLflow server from git history
- Restore Cloud SQL from backup
- Update environment variables

### Data Preservation
- All historical training data remains in `QuickTest.training_history_json`
- New experiments use GCS-based metrics
- No data loss during migration

---

## Timeline

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| Phase 1 | Create MetricsCollector, update callbacks | None |
| Phase 2 | Update Django to read from GCS | Phase 1 complete |
| Phase 3 | Delete MLflow infrastructure | Phase 2 tested |
| Phase 4 | Update documentation | Phase 3 complete |

**Recommended approach:** Complete Phase 1-2, run several test experiments, verify data flow works correctly, then proceed with Phase 3.

---

## Appendix: JSON Schema for training_metrics.json

```json
{
  "saved_at": "2024-01-15T10:30:00Z",
  "available": true,

  "epochs": [0, 1, 2, 3, ...],

  "loss": {
    "loss": [0.5, 0.4, 0.3, ...],
    "val_loss": [0.6, 0.5, 0.4, ...],
    "total_loss": [...],
    "val_total_loss": [...],
    "regularization_loss": [...],
    "val_regularization_loss": [...]
  },

  "gradient": {
    "total": [1.2, 1.1, 1.0, ...],
    "query": [...],
    "candidate": [...]
  },

  "weight_stats": {
    "query": {
      "mean": [...],
      "std": [...],
      "min": [...],
      "max": [...],
      "histogram": {
        "bin_edges": [-1.0, -0.8, ..., 1.0],
        "counts": [[...], [...], ...]
      }
    },
    "candidate": { ... }
  },

  "gradient_stats": {
    "query": {
      "mean": [...],
      "std": [...],
      "min": [...],
      "max": [...],
      "norm": [...],
      "histogram": {
        "bin_edges": [-1.0, -0.8, ..., 1.0],
        "counts": [[...], [...], ...]
      }
    },
    "candidate": { ... }
  },

  "final_metrics": {
    "final_loss": 0.25,
    "final_val_loss": 0.35,
    "test_loss": 0.30,
    "test_recall_at_5": 0.002,
    "test_recall_at_10": 0.005,
    "test_recall_at_50": 0.035,
    "test_recall_at_100": 0.075
  },

  "params": {
    "epochs": 50,
    "batch_size": 2048,
    "learning_rate": 0.01,
    "optimizer": "adagrad",
    "embedding_dim": 32
  }
}
```

This schema is compatible with the existing `training_history_json` field structure, ensuring seamless integration with the current caching system.
