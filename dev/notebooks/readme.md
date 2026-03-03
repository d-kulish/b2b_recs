# Migrating Inference Notebooks: Local Model → Endpoint

Instructions for converting a notebook that loads a TF SavedModel locally (e.g. `dev/models/qt-174/inference_demo.ipynb`) into one that calls a deployed Cloud Run endpoint (e.g. `dev/notebooks/retr_tern.ipynb`).

---

## Prerequisites

Before starting, you need:

1. **A deployed endpoint** — the model must be deployed to Cloud Run via the platform's Deploy wizard (Training page → Deploy to Cloud Run). You need the full service URL, e.g. `https://ternopil-tern-retr-v1-serving-3dmqemfmxq-ez.a.run.app`.

2. **GCS artifacts still available** — the training-artifacts bucket (`gs://b2b-recs-training-artifacts/`) must still contain the training run's artifacts (vocab files, training metrics). Unlike the pipeline-staging bucket (7-day auto-delete), training-artifacts has no lifecycle policy, so artifacts are preserved indefinitely unless manually cleaned up.

3. **BigQuery access** — same as the local notebook; you need access to the test/train views.

---

## Step 1: Gather Endpoint Information

### Find the endpoint URL

If you don't have it, list Cloud Run services:

```bash
gcloud run services list --project=b2b-recs --format="table(metadata.name,status.url)"
```

### Find the GCS model path

The deployed container has a `MODEL_PATH` env var pointing to the GCS artifacts. To retrieve it:

```bash
# First find the region (check the URL suffix: -lm = europe-central2, -ez = europe-west4, etc.)
gcloud run services describe SERVICE_NAME \
  --project=b2b-recs --region=REGION \
  --format="yaml(spec.template.spec.containers[0].env)"
```

This returns something like:

```
env:
- name: MODEL_PATH
  value: gs://b2b-recs-training-artifacts/tr-66-20260302-142408/pushed_model/1772469577
- name: MODEL_NAME
  value: recommender
```

**Important:** The GCS path pattern is `tr-{run_id}-{timestamp}/pushed_model/{version}/`, NOT `training-runs/{run_id}/`. Always get the actual path from the service env vars.

### Query the model metadata

The endpoint exposes a TF Serving metadata API that reveals the exact input/output feature names and types:

```bash
curl -s "https://YOUR-ENDPOINT/v1/models/recommender/metadata" | python3 -m json.tool
```

Look for the `serving_default` signature. Example output:

```
Inputs:
  customer_id:   DT_INT64  shape [-1]
  date:          DT_INT64  shape [-1]
  cust_value:    DT_FLOAT  shape [-1]
  cs_last_purch: DT_INT64  shape [-1]
  cs_orders:     DT_INT64  shape [-1]
  cs_unique_skus:DT_INT64  shape [-1]
  history:       DT_INT64  shape [-1, 50]

Outputs:
  product_ids:   DT_INT64  shape [-1, 150]
  scores:        DT_FLOAT  shape [-1, 150]
```

**The feature names in the serving signature are what the endpoint expects.** They may differ from BigQuery column names (e.g. BQ has `days_since_last_purchase`, but the model expects `cs_last_purch`). The original local notebook shows this mapping in its `serve_fn()` calls.

### Get training metrics

Download the training metrics JSON from GCS:

```bash
gcloud storage cat "gs://b2b-recs-training-artifacts/tr-XX-TIMESTAMP/training_metrics.json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['final_metrics'], indent=2))"
```

---

## Step 2: Download Vocabulary Files

The vocab files (`customer_id_vocab`, `product_id_vocab`) are inside the SavedModel's `assets/` directory in GCS:

```bash
cd dev/notebooks/
gcloud storage cp \
  "gs://b2b-recs-training-artifacts/tr-XX-TIMESTAMP/pushed_model/VERSION/assets/customer_id_vocab" \
  "gs://b2b-recs-training-artifacts/tr-XX-TIMESTAMP/pushed_model/VERSION/assets/product_id_vocab" \
  .
```

These are plain text files with one ID per line. They're used to filter BigQuery queries to "known" customers/products for accuracy comparisons.

The notebook should also include code to auto-download them on first run (see the `ensure_vocabs()` function in `retr_tern.ipynb`).

**Note:** Vocab files are git-ignored. Each user downloads them on first notebook run.

---

## Step 3: Code Changes

### 3.1 Replace imports

**Local model notebook:**
```python
import tensorflow as tf
import numpy as np
import pandas as pd
from google.cloud import bigquery
```

**Endpoint notebook:**
```python
import requests          # NEW — for HTTP calls
import time              # NEW — for latency tracking
import subprocess, os    # NEW — for vocab download
import numpy as np
import pandas as pd
from google.cloud import bigquery
# tensorflow is NOT needed
```

### 3.2 Replace model loading with endpoint config

**Local:**
```python
serve_fn = tf.saved_model.load('Format-Serving').signatures['serving_default']

with open('Format-Serving/assets/customer_id_vocab') as f:
    known_customers = set(int(l.strip()) for l in f)
```

**Endpoint:**
```python
ENDPOINT_URL = 'https://YOUR-ENDPOINT.a.run.app'
MODEL_NAME   = 'recommender'
PREDICT_URL  = f'{ENDPOINT_URL}/v1/models/{MODEL_NAME}:predict'
BATCH_SIZE   = 64  # native TF Serving max_batch_size limit

# Vocabs downloaded from GCS (see Step 2)
with open('customer_id_vocab') as f:
    known_customers = set(int(l.strip()) for l in f)
```

### 3.3 Fix `pad_history` for JSON serialization

BigQuery returns history arrays containing **numpy int64** values. These are fine for `tf.constant()` but **not JSON-serializable**. You must convert to Python int.

**Local (works but fragile):**
```python
def pad_history(hist, max_len=HISTORY_LEN):
    arr = list(hist) if hist is not None else []  # numpy int64 elements!
    arr = arr[:max_len]
    return arr + [0] * (max_len - len(arr))
```

**Endpoint (safe for JSON):**
```python
def pad_history(hist, max_len=HISTORY_LEN):
    arr = [int(x) for x in hist] if hist is not None else []  # Python int
    arr = arr[:max_len]
    return arr + [0] * (max_len - len(arr))
```

Without this fix you get: `TypeError: Object of type int64 is not JSON serializable`.

### 3.4 Replace `serve_fn()` calls with HTTP requests

**Local:**
```python
history_padded = np.array([pad_history(h) for h in df['purchase_history'].values], dtype=np.int64)

result = serve_fn(
    customer_id=tf.constant(df['customer_id'].values, dtype=tf.int64),
    date=tf.constant(df['date_unix'].values, dtype=tf.int64),
    cust_value=tf.constant(df['cust_value'].values, dtype=tf.float32),
    cs_last_purch=tf.constant(df['days_since_last_purchase'].values, dtype=tf.int64),
    cs_orders=tf.constant(df['cust_order_days_60d'].values, dtype=tf.int64),
    cs_unique_skus=tf.constant(df['cust_unique_products_60d'].values, dtype=tf.int64),
    history=tf.constant(history_padded, dtype=tf.int64),
)
all_rec_ids = result['product_ids'].numpy()
all_rec_scores = result['scores'].numpy()
```

**Endpoint:**
```python
def build_instances(df):
    """Convert DataFrame rows to endpoint-compatible JSON instances."""
    instances = []
    for _, row in df.iterrows():
        instances.append({
            'customer_id':  int(row['customer_id']),
            'date':         int(row['date_unix']),
            'cust_value':   float(row['cust_value']),
            'cs_last_purch': int(row['days_since_last_purchase']),
            'cs_orders':    int(row['cust_order_days_60d']),
            'cs_unique_skus': int(row['cust_unique_products_60d']),
            'history':      pad_history(row['purchase_history']),
        })
    return instances

def predict(instances):
    """Call endpoint with automatic batching."""
    all_pids, all_scores = [], []
    for i in range(0, len(instances), BATCH_SIZE):
        batch = instances[i:i + BATCH_SIZE]
        resp = requests.post(PREDICT_URL, json={'instances': batch}, timeout=120)
        resp.raise_for_status()
        for p in resp.json()['predictions']:
            all_pids.append(p['product_ids'])
            all_scores.append(p['scores'])
    return np.array(all_pids, dtype=np.int64), np.array(all_scores, dtype=np.float32)

instances = build_instances(df)
all_rec_ids, all_rec_scores = predict(instances)
```

Key points:
- Every value must be a **Python native type** (int, float, list), not numpy — `json.dumps` rejects numpy types.
- The `build_instances()` function handles the BQ column → model feature name mapping.
- The `predict()` function returns numpy arrays with the same shape as the local `result['product_ids'].numpy()`, so downstream code (Recall@K, basket coverage, visual) stays identical.

### 3.5 Handle batch size limits

**Native TF Serving** (non-ScaNN models) enforces `max_batch_size: 64` from `batching_config.txt`. Sending more than 64 instances in one request causes:

```
400 Bad Request: "Task size 65 is larger than maximum input batch size 64"
```

The `predict()` function above handles this automatically by splitting into batches of 64.

**ScaNN-based models** (Python/Flask server) do not have this limit, but batching is still recommended for large payloads.

---

## Step 4: Endpoint API Reference

The deployed endpoints use the **TF Serving REST API** format.

### Health check
```
GET /v1/models/recommender
→ {"model_version_status": [{"version": "1", "state": "AVAILABLE", ...}]}
```

### Metadata
```
GET /v1/models/recommender/metadata
→ Input/output signature definitions
```

### Predict
```
POST /v1/models/recommender:predict
Content-Type: application/json

{"instances": [
  {"customer_id": 100090964709, "date": 1707955200, "cust_value": 5000.0,
   "cs_last_purch": 14, "cs_orders": 3, "cs_unique_skus": 7,
   "history": [0,0,...,0]},
  ...
]}

→ {"predictions": [
  {"product_ids": [49892001001, 364807001001, ...], "scores": [610.53, 272.54, ...]},
  ...
]}
```

---

## Step 5: What Stays the Same

These parts of the notebook do **not** change:

- **BigQuery queries** — same test/train views, same SQL
- **Recall@K computation** — same loop over predictions
- **Comparison chart** — same matplotlib code
- **Basket coverage logic** — same groupby + overlap calculation
- **Visual customer section** — same HTML table rendering
- **Product name enrichment** — same BQ lookups for `art_name`, `category`, etc.

The only change is the inference call: `serve_fn(**tensors)` → `predict(instances)`.

---

## Checklist

- [ ] Get endpoint URL from Cloud Run
- [ ] Get GCS model path from service env vars (`MODEL_PATH`)
- [ ] Query `/v1/models/recommender/metadata` to confirm feature names
- [ ] Download training metrics from GCS
- [ ] Download vocab files from GCS `assets/` directory
- [ ] Replace `tensorflow` imports with `requests`
- [ ] Fix `pad_history` to convert numpy int64 → Python int
- [ ] Create `build_instances()` with correct BQ column → model feature mapping
- [ ] Create `predict()` with `BATCH_SIZE = 64` batching
- [ ] Replace all `serve_fn()` calls with `predict(build_instances(df))`
- [ ] Fill in `TRAINING_RECALL` dict with actual metrics from training run
- [ ] Verify endpoint health before running analysis cells
- [ ] Test with a small sample (20 rows) before running full 500

---

## File Structure

```
dev/notebooks/
├── readme.md                # This file
├── retrival/                # Retrieval model notebooks
│   ├── retr_tern.ipynb      # Endpoint-based notebook (tern_retr_v1, run 66)
│   ├── customer_id_vocab    # Auto-downloaded from GCS on first run
│   └── product_id_vocab     # Auto-downloaded from GCS on first run
├── nbo/                     # Next-best-offer model notebooks
└── promo/                   # Promo model notebooks
```

---

## Reference: Serving Container Types

| Container | Used for | Max batch size | Latency |
|-----------|----------|---------------|---------|
| `tf-serving-native` | Non-ScaNN models (brute_force) | 64 (configurable in `batching_config.txt`) | ~10-15ms lower |
| `tf-serving-scann` | ScaNN models | No hard limit (Flask/Gunicorn) | Slightly higher |

Both expose the same TF Serving REST API (`/v1/models/{name}:predict`), so the notebook code works with either container type. The only difference is the batch size limit.
