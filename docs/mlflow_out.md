# MLflow Removal Migration Plan

## Executive Summary

This document outlines the plan to **completely remove MLflow** from the B2B Recommendations system and replace it with direct GCS-based metrics storage. This includes:

1. **Migrating all historical data** from MLflow PostgreSQL to Django DB cache
2. **Replacing trainer callbacks** with in-memory collection + GCS upload
3. **Deleting all MLflow infrastructure** (Cloud Run, Cloud SQL, GCS bucket)
4. **Removing all associated costs** (~$50/month savings)

**Related Documentation:** See `docs/mlflow.md` for complete implementation reference if you need to restore this architecture.

---

## Table of Contents

1. [Background & Motivation](#background--motivation)
2. [Current Architecture](#current-architecture)
3. [Target Architecture](#target-architecture)
4. [Benefits](#benefits)
5. [Migration Steps](#migration-steps)
   - [Phase 0: Data Migration & Verification](#phase-0-data-migration--verification)
   - [Phase 1: Create MetricsCollector](#phase-1-create-metricscollector-trainer-side)
   - [Phase 2: Update Django](#phase-2-update-django-to-read-from-gcs)
   - [Phase 3: Remove MLflow Infrastructure](#phase-3-remove-mlflow-infrastructure)
   - [Phase 4: Update Documentation](#phase-4-update-documentation)
   - [Phase 5: Cost Verification & Closure](#phase-5-cost-verification--closure)
6. [File Reference](#file-reference)
7. [Rollback Plan](#rollback-plan)
8. [Checklist](#checklist)

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

### Phase 0: Data Migration & Verification

**Goal:** Migrate all historical training data from MLflow to Django DB before removing MLflow infrastructure.

**CRITICAL:** This phase must be completed before any infrastructure deletion. Once MLflow is deleted, historical data is unrecoverable.

#### Step 0.1: Database Backup (Safety)

Export MLflow PostgreSQL database before any migration:

```bash
# Connect to Cloud SQL and create a backup
gcloud sql backups create \
    --instance=mlflow-db \
    --description="Pre-migration backup $(date +%Y%m%d)"

# Or export to GCS
gcloud sql export sql mlflow-db \
    gs://b2b-recs-backups/mlflow-db-export-$(date +%Y%m%d).sql.gz \
    --database=mlflow
```

#### Step 0.2: Verify Current Cache State

Check how many experiments need caching:

```bash
# Dry run to see what needs caching
python manage.py backfill_training_cache --dry-run

# Expected output shows experiments without training_history_json
```

**Django Shell verification:**
```python
from ml_platform.models import QuickTest

# Total completed experiments
total = QuickTest.objects.filter(status='completed').count()

# Experiments with MLflow run ID
with_mlflow = QuickTest.objects.filter(
    status='completed',
    mlflow_run_id__isnull=False
).exclude(mlflow_run_id='').count()

# Already cached
cached = QuickTest.objects.filter(
    status='completed',
    training_history_json__isnull=False
).count()

print(f"Total completed: {total}")
print(f"With MLflow ID: {with_mlflow}")
print(f"Already cached: {cached}")
print(f"Need caching: {with_mlflow - cached}")
```

#### Step 0.3: Backfill All Historical Data

Run the backfill command to cache all MLflow data to Django:

```bash
# Cache all completed experiments (may take several minutes)
python manage.py backfill_training_cache

# If many experiments, run in batches
python manage.py backfill_training_cache --limit 50
# ... repeat until all done

# Force re-cache if needed (overwrites existing)
python manage.py backfill_training_cache --force
```

**Monitor progress:**
- Each experiment takes ~30-60 seconds (MLflow API calls)
- Total time depends on number of experiments
- Errors are logged but don't stop the process

#### Step 0.4: Cache Histogram Data (Optional)

Histogram data is currently fetched on-demand. If you want to preserve it permanently, extend the backfill to include histograms:

**Option A:** Accept histogram data loss (recommended)
- Histograms rarely used
- Reduces cache size significantly
- New experiments will store histograms in GCS

**Option B:** Extend backfill to include histograms
- Modify `training_cache_service.py` to include histogram data
- Significantly increases cache size per experiment
- Run extended backfill

#### Step 0.5: Verify Migration Completeness

```python
from ml_platform.models import QuickTest

# Verify all MLflow experiments are cached
uncached = QuickTest.objects.filter(
    status='completed',
    mlflow_run_id__isnull=False,
    training_history_json__isnull=True
).exclude(mlflow_run_id='')

if uncached.exists():
    print(f"WARNING: {uncached.count()} experiments still uncached!")
    for qt in uncached[:10]:
        print(f"  - QuickTest {qt.id}: {qt.display_name}")
else:
    print("SUCCESS: All MLflow experiments are cached!")
```

#### Step 0.6: Export Raw MLflow Data (Optional Backup)

For additional safety, export raw MLflow data to GCS:

```bash
# Export experiments and runs via MLflow CLI (if accessible)
# Or query directly from Cloud SQL:

gcloud sql connect mlflow-db --user=mlflow

# In psql:
\copy experiments TO '/tmp/experiments.csv' CSV HEADER;
\copy runs TO '/tmp/runs.csv' CSV HEADER;
\copy metrics TO '/tmp/metrics.csv' CSV HEADER;
\copy params TO '/tmp/params.csv' CSV HEADER;

# Upload to GCS
gsutil cp /tmp/*.csv gs://b2b-recs-backups/mlflow-export/
```

**Checkpoint:** Only proceed to Phase 1 when:
- [ ] All completed experiments with `mlflow_run_id` have `training_history_json`
- [ ] Database backup exists in Cloud SQL or GCS
- [ ] You've verified sample experiments display correctly in Training tab

---

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

**Goal:** Delete all MLflow-related code and cloud infrastructure to eliminate costs.

**CRITICAL:** Only proceed after:
- Phase 0 complete (all data migrated)
- Phase 1-2 complete (new data flow tested)
- At least 2-3 new experiments run successfully with GCS-based metrics

#### Step 3.1: Delete Cloud Run Service

```bash
# Delete MLflow Cloud Run service
gcloud run services delete mlflow-server \
    --region=europe-central2 \
    --quiet

# Verify deletion
gcloud run services list --region=europe-central2
# Should NOT show mlflow-server
```

#### Step 3.2: Delete Cloud SQL Instance

```bash
# List existing backups before deletion
gcloud sql backups list --instance=mlflow-db

# Delete the Cloud SQL instance
# WARNING: This permanently deletes all data!
gcloud sql instances delete mlflow-db --quiet

# Verify deletion
gcloud sql instances list
# Should NOT show mlflow-db
```

#### Step 3.3: Delete Cloud Build Trigger

```bash
# List Cloud Build triggers
gcloud builds triggers list

# Delete MLflow build trigger (find exact name first)
gcloud builds triggers delete mlflow-server --quiet

# Or delete by trigger ID if name differs
gcloud builds triggers delete TRIGGER_ID --quiet
```

#### Step 3.4: Delete GCS Artifacts Bucket (Optional)

If MLflow artifacts bucket exists and is no longer needed:

```bash
# List bucket contents first
gsutil ls -la gs://PROJECT-mlflow-artifacts/

# Delete bucket and all contents
gsutil rm -r gs://PROJECT-mlflow-artifacts/

# Verify deletion
gsutil ls gs://PROJECT-mlflow-artifacts/
# Should show "BucketNotFoundException"
```

#### Step 3.5: Remove IAM Service Account

```bash
# List service accounts
gcloud iam service-accounts list | grep mlflow

# Delete MLflow service account
gcloud iam service-accounts delete \
    mlflow-server@PROJECT_ID.iam.gserviceaccount.com \
    --quiet

# Remove any remaining IAM bindings
# (Usually cleaned up with service account deletion)
```

#### Step 3.6: Delete Secret Manager Secrets (if any)

```bash
# List secrets related to MLflow
gcloud secrets list | grep -i mlflow

# Delete each MLflow-related secret
gcloud secrets delete MLFLOW_DB_PASSWORD --quiet
# ... repeat for other secrets
```

#### Step 3.7: Delete Code Files

**Files to delete:**
```
mlflow_server/
├── Dockerfile          ✗ DELETE
├── README.md           ✗ DELETE
├── cloudbuild.yaml     ✗ DELETE
├── entrypoint.sh       ✗ DELETE
└── requirements.txt    ✗ DELETE
```

```bash
# Remove mlflow_server directory
rm -rf mlflow_server/

# Remove MLflow service file
rm ml_platform/experiments/mlflow_service.py

# Remove integration test
rm tests/test_mlflow_integration.py
```

#### Step 3.8: Clean Up Code References

**Files to modify:**

| File | Changes |
|------|---------|
| `ml_platform/experiments/api.py` | Remove MLflow imports and histogram endpoint |
| `ml_platform/experiments/urls.py` | Remove histogram-data URL pattern |
| `ml_platform/experiments/services.py` | Remove MLflow environment variable, mlflow_info reading |
| `ml_platform/experiments/artifact_service.py` | Remove MLflow references |
| `ml_platform/models.py` | Keep `mlflow_run_id` field (for backward compatibility) or remove |
| `config/settings.py` | Remove `MLFLOW_TRACKING_URI` setting |

#### Step 3.9: Update Model Fields

**File:** `ml_platform/models.py`

**Option A: Keep fields for backward compatibility (recommended):**
```python
# QuickTest model - keep for historical reference
mlflow_run_id = models.CharField(
    max_length=255,
    blank=True,
    help_text="Deprecated: MLflow run ID (kept for historical data)"
)
mlflow_experiment_name = models.CharField(
    max_length=255,
    blank=True,
    help_text="Deprecated: MLflow experiment name"
)
```

**Option B: Remove fields completely:**
```bash
# Create migration to remove fields
python manage.py makemigrations ml_platform --name remove_mlflow_fields
python manage.py migrate
```

---

### Phase 4: Update Documentation

**Files to update:**

| File | Changes |
|------|---------|
| `README.md` | Remove MLflow setup instructions |
| `docs/phase_experiments.md` | Update architecture diagrams, remove MLflow references |
| `docs/phase_training.md` | Update training flow documentation |
| `implementation.md` | Remove MLflow references |

**Important:** Keep `docs/mlflow.md` as historical reference in case architecture needs to be restored.

---

### Phase 5: Cost Verification & Closure

**Goal:** Verify all MLflow-related costs are eliminated and document completion.

#### Step 5.1: Verify Cloud Resources Deleted

```bash
# Verify Cloud Run service deleted
gcloud run services list --region=europe-central2 | grep mlflow
# Should return nothing

# Verify Cloud SQL instance deleted
gcloud sql instances list | grep mlflow
# Should return nothing

# Verify service account deleted
gcloud iam service-accounts list | grep mlflow
# Should return nothing

# Verify Cloud Build triggers deleted
gcloud builds triggers list | grep mlflow
# Should return nothing
```

#### Step 5.2: Check Billing Report

1. Go to GCP Console → Billing → Reports
2. Filter by:
   - Time range: Last 7 days
   - Services: Cloud Run, Cloud SQL, Cloud Storage
3. Verify no charges for:
   - `mlflow-server` Cloud Run service
   - `mlflow-db` Cloud SQL instance
   - MLflow artifacts bucket

#### Step 5.3: Remove Environment Variables

Check and remove MLflow-related environment variables from:

```bash
# Cloud Run Django service
gcloud run services describe django-app --region=europe-central2 --format='yaml' | grep -i mlflow

# If found, update to remove:
gcloud run services update django-app \
    --region=europe-central2 \
    --remove-env-vars=MLFLOW_TRACKING_URI
```

#### Step 5.4: Update CI/CD Configuration

Check and remove MLflow-related configuration from:
- `.github/workflows/` (if using GitHub Actions)
- `cloudbuild.yaml` files
- Any deployment scripts

#### Step 5.5: Final Verification

Run this checklist to confirm complete removal:

```python
# In Django shell
from django.conf import settings

# Should raise AttributeError or return None/empty
try:
    print(f"MLFLOW_TRACKING_URI: {settings.MLFLOW_TRACKING_URI}")
except AttributeError:
    print("MLFLOW_TRACKING_URI not found (good!)")

# Verify mlflow_service import fails
try:
    from ml_platform.experiments import mlflow_service
    print("WARNING: mlflow_service still importable!")
except ImportError:
    print("mlflow_service not found (good!)")
```

#### Step 5.6: Document Completion

Update this document with:
- Completion date
- Final cost savings achieved
- Any issues encountered

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

| Resource | Type | Location | Est. Monthly Cost |
|----------|------|----------|-------------------|
| `mlflow-server` | Cloud Run Service | europe-central2 | ~$20 |
| `mlflow-db` | Cloud SQL Instance | europe-central2 | ~$30 |
| `mlflow-server` | Cloud Build Trigger | Global | ~$0 |
| `PROJECT-mlflow-artifacts` | GCS Bucket | europe-central2 | ~$1 |
| `mlflow-server@PROJECT` | Service Account | Global | $0 |
| **Total Savings** | | | **~$50/month** |

---

## Rollback Plan

If issues arise during migration:

### Immediate Rollback (Phase 0-2)
- Revert code changes via git
- Existing experiments continue to work (cached data preserved)
- MLflow server still running (not deleted until Phase 3)

### Phase 3 Rollback (Before Infrastructure Deletion)
- Re-deploy MLflow server from git history
- Restore Cloud SQL from backup
- Update environment variables

### Post-Infrastructure Deletion Rollback
If MLflow infrastructure is already deleted:
1. Use `docs/mlflow.md` to recreate architecture
2. Redeploy MLflow server using saved `mlflow_server/` from git history
3. Create new Cloud SQL instance (data will be lost unless backup exists)
4. Historical data still available in `QuickTest.training_history_json`

### Data Preservation
- All historical training data preserved in `QuickTest.training_history_json`
- Phase 0 creates database backup before any deletion
- New experiments use GCS-based metrics (independent of MLflow)

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

---

## Checklist

### Phase 0: Data Migration & Verification
- [ ] Create Cloud SQL backup
- [ ] Run `python manage.py backfill_training_cache --dry-run` to assess scope
- [ ] Run `python manage.py backfill_training_cache` to migrate all data
- [ ] Verify all completed experiments have `training_history_json`
- [ ] Test Training tab displays correctly for migrated experiments
- [ ] (Optional) Export raw MLflow data to GCS backup

### Phase 1: Create MetricsCollector ✅ COMPLETED
- [x] Create `MetricsCollector` class in `configs/services.py`
- [x] Create `MetricsCallback` to replace `MLflowCallback`
- [x] Update `WeightStatsCallback` to use `MetricsCollector`
- [x] Update `GradientStatsCallback` to use `MetricsCollector`
- [x] Update `run_fn()` to initialize `MetricsCollector` instead of `MLflowRestClient`
- [x] Update training completion to call `metrics_collector.save_to_gcs()`
- [ ] Test locally with a sample training run

### Phase 2: Update Django ✅ COMPLETED
- [x] Modify `training_cache_service.py` to read from GCS instead of MLflow
- [x] MLflow fallback kept for historical experiments
- [ ] Deploy Django changes
- [ ] Run 2-3 new experiments with GCS-based metrics
- [ ] Verify Training tab works for new experiments

### Phase 3: Remove MLflow Infrastructure (Partial - backward compat kept)
- [ ] Delete Cloud Run service: `mlflow-server`
- [ ] Delete Cloud SQL instance: `mlflow-db`
- [ ] Delete Cloud Build trigger
- [ ] Delete GCS artifacts bucket (if exists)
- [ ] Delete service account: `mlflow-server@PROJECT`
- [ ] Delete Secret Manager secrets (if any)
- [ ] Delete `mlflow_server/` directory
- [x] `ml_platform/experiments/mlflow_service.py` - KEPT for backward compatibility (deprecated)
- [ ] Delete `tests/test_mlflow_integration.py`
- [x] Clean up code references in other files
- [x] `MLFLOW_TRACKING_URI` - marked as deprecated in settings

### Phase 4: Update Documentation
- [ ] Update `README.md` to remove MLflow instructions
- [ ] Update `docs/phase_experiments.md` to reflect new architecture
- [x] Keep `docs/mlflow.md` for historical reference

### Phase 5: Cost Verification & Closure
- [ ] Verify no MLflow resources in `gcloud` commands
- [ ] Check GCP Billing for zero MLflow-related charges
- [ ] Remove `MLFLOW_TRACKING_URI` from Cloud Run environment
- [ ] Update CI/CD configuration if needed
- [ ] Run final verification script
- [ ] Document completion date and savings

---

## Next Steps (Action Required)

The code changes are complete. The following actions require manual execution:

### Immediate (Before Next Deployment)

1. **Run data migration backfill**
   ```bash
   # Activate virtualenv, then:
   python manage.py backfill_training_cache --dry-run  # Check scope
   python manage.py backfill_training_cache            # Migrate all
   ```

2. **Deploy Django changes**
   - Deploy the updated code to Cloud Run
   - Verify Training tab works for existing experiments (cached data)

3. **Test with a new experiment**
   - Run a new QuickTest to verify the GCS-based metrics flow
   - Check that `training_metrics.json` is created in GCS
   - Verify Training tab shows data for the new experiment

### After Verification (To Stop Costs)

4. **Delete MLflow Cloud Run service**
   ```bash
   gcloud run services delete mlflow-server --region=europe-central2 --quiet
   ```

5. **Delete MLflow Cloud SQL instance**
   ```bash
   # CAUTION: This permanently deletes all MLflow data!
   # Only run after verifying all experiments have cached data
   gcloud sql instances delete mlflow-db --quiet
   ```

6. **Delete MLflow service account**
   ```bash
   gcloud iam service-accounts delete mlflow-server@PROJECT_ID.iam.gserviceaccount.com --quiet
   ```

7. **Remove `MLFLOW_TRACKING_URI` from Cloud Run environment**
   ```bash
   gcloud run services update django-app --region=europe-central2 --remove-env-vars=MLFLOW_TRACKING_URI
   ```

### Cleanup (Optional)

8. **Delete MLflow server code** (once infrastructure deleted)
   ```bash
   rm -rf mlflow_server/
   rm tests/test_mlflow_integration.py
   ```

9. **Remove MLflow service** (once all experiments cached)
   - Delete `ml_platform/experiments/mlflow_service.py`
   - Update `training_cache_service.py` to remove MLflow fallback

### Verification Commands

```bash
# Verify Cloud Run service deleted
gcloud run services list --region=europe-central2 | grep mlflow

# Verify Cloud SQL instance deleted
gcloud sql instances list | grep mlflow

# Check billing (in GCP Console)
# Billing → Reports → Filter by Cloud Run, Cloud SQL
```

---

## Completion Record

| Field | Value |
|-------|-------|
| Migration Started | 2026-01-02 |
| Phase 1-2 Completed | 2026-01-02 |
| Phase 0 Completed | _pending backfill_ |
| Infrastructure Deleted | _pending_ |
| Migration Completed | _pending_ |
| Experiments Migrated | _N_ |
| Monthly Savings | _~$50_ |
| Issues Encountered | _None_ |
