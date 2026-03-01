# Saved Experiment Models

This directory contains TF SavedModels rescued from experiment Quick Tests. These models are too large for git (60+ MiB each) and must be downloaded from GCS or re-created locally.

**Last updated**: 2026-02-20

---

## Available Models

| Model | Type | Recall@5 | Recall@100 | Size | Hardware | Feature Config |
|-------|------|----------|------------|------|----------|---------------|
| `qt-131` | Retrieval (brute-force) | 0.9992 | 0.9994 | 61 MiB | GPU T4 | Lviv_nbo_retriv (ID: 13) |
| `qt-132` | Retrieval (brute-force) | 0.5855 | 0.9938 | 46 MiB | CPU | Lviv_nbo_retriv_v2 (ID: 14) |

Both trained on 2026-02-13.

---

## Directory Structure

```
models/
├── qt-131/
│   ├── Format-Serving/           # TF SavedModel (load this path)
│   │   ├── saved_model.pb
│   │   ├── variables/
│   │   │   ├── variables.data-00000-of-00001
│   │   │   └── variables.index
│   │   └── assets/               # Vocabulary files (baked into model)
│   │       ├── customer_id_vocab   (50,556 customers)
│   │       ├── product_id_vocab    (1,963 products)
│   │       ├── category_vocab
│   │       └── sub_category_vocab
│   ├── trainer_module.py         # Generated trainer code (reference)
│   ├── transform_module.py       # Generated preprocessing code (reference)
│   └── training_metrics.json     # Full epoch-by-epoch training history
└── qt-132/
    └── (same structure)
```

---

## How to Find Models from Experiments

Experiment models live in **two** GCS buckets with auto-delete lifecycle policies:

| Bucket | Contents | Lifecycle |
|--------|----------|-----------|
| `gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/` | Code files, metrics JSON | **7-day auto-delete** |
| `gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/` | Full TFX pipeline output (data, transform, **model**) | **7-day auto-delete** |

### Step 1: Get the GCS path from the database

```bash
# From project root
export $(grep -v '^#' .env | xargs)
export DB_ENGINE=postgresql DB_NAME=b2b_recs_dev DB_USER=django_user DB_HOST=127.0.0.1 DB_PORT=5433 DJANGO_SETTINGS_MODULE=config.settings

./venv/bin/python -c "
import django, os; django.setup()
from ml_platform.models import QuickTest
qt = QuickTest.objects.get(id=YOUR_ID)
print(f'GCS: {qt.gcs_artifacts_path}')
print(f'Pipeline: {qt.vertex_pipeline_job_name}')
print(f'Status: {qt.status}')
print(f'Recall@100: {qt.recall_at_100}')
"
```

### Step 2: Find the SavedModel in the pipeline-staging bucket

The model is NOT in the quicktest-artifacts bucket. It's in the Trainer component output:

```bash
# List the pipeline root to find the Trainer component
gsutil ls -r gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/ | grep saved_model

# The path pattern is:
# gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/
#   {project_number}/{pipeline_job_name}/
#     Trainer_{hash}/model/Format-Serving/saved_model.pb
```

### Step 3: Copy to local

```bash
mkdir -p models/qt-{id}
gcloud storage cp -r \
  "gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/{project}/...Trainer_.../model/Format-Serving" \
  models/qt-{id}/

# Also grab the code and metrics from the quicktest bucket
gcloud storage cp \
  "gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/trainer_module.py" \
  "gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/training_metrics.json" \
  "gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/transform_module.py" \
  models/qt-{id}/
```

**Act fast** — both buckets have 7-day auto-delete.

---

## Inference

### Environment

The project venv (`./venv/bin/python`, Python 3.13) works out of the box. Only `tensorflow` is needed — TFRS and TFT are **not** required because the TFT transform layer (vocabulary lookups, normalization, cyclical encoding) is baked into the SavedModel.

### Loading a Model

```python
import tensorflow as tf

model = tf.saved_model.load('models/qt-131/Format-Serving')
serve_fn = model.signatures['serving_default']
```

### Input Payload

Both models accept **raw values** — the internal TFT layer handles all preprocessing.

**QT-131** — 4 inputs:

```python
result = serve_fn(
    customer_id = tf.constant([100090964709], dtype=tf.int64),   # Raw customer ID from BigQuery
    product_id  = tf.constant([378964001001], dtype=tf.int64),   # Raw product ID (buyer tower context)
    date        = tf.constant([1707955200],   dtype=tf.int64),   # Unix timestamp in seconds
    cust_value  = tf.constant([5000.0],       dtype=tf.float32), # Customer value
)
```

**QT-132** — 4 inputs (different set):

```python
result = serve_fn(
    customer_id  = tf.constant([100090964709], dtype=tf.int64),
    date         = tf.constant([1707955200],   dtype=tf.int64),
    sub_category = tf.constant(['КУРКА'],      dtype=tf.string), # String, not int!
    cust_value   = tf.constant([5000.0],       dtype=tf.float32),
)
```

### Output

Both models return top-100 product recommendations:

```python
result['product_ids']  # shape (batch, 100), dtype int64 — raw product IDs
result['scores']       # shape (batch, 100), dtype float32 — similarity scores (higher = better)
```

Supports batched input — pass arrays to get recommendations for multiple customers at once.

### How to Find the Payload for Any Model

```python
model = tf.saved_model.load('models/qt-XXX/Format-Serving')
sig = model.signatures['serving_default']

# Inputs
for name, spec in sig.structured_input_signature[1].items():
    print(f'{name}: dtype={spec.dtype.name}, shape={spec.shape}')

# Outputs
for name, spec in sig.structured_outputs.items():
    print(f'{name}: dtype={spec.dtype.name}, shape={spec.shape}')
```

---

## Notebook Quick Start

```python
import tensorflow as tf
import numpy as np
from datetime import datetime

# Load
model = tf.saved_model.load('models/qt-131/Format-Serving')
serve_fn = model.signatures['serving_default']

# Single customer
result = serve_fn(
    customer_id=tf.constant([100090964709], dtype=tf.int64),
    product_id=tf.constant([378964001001], dtype=tf.int64),
    date=tf.constant([int(datetime(2026, 2, 15).timestamp())], dtype=tf.int64),
    cust_value=tf.constant([5000.0], dtype=tf.float32),
)

top_products = result['product_ids'].numpy()[0]
top_scores = result['scores'].numpy()[0]

for i in range(10):
    print(f'{i+1}. Product {top_products[i]}  (score: {top_scores[i]:.2f})')
```

### Batch Inference

```python
# Multiple customers at once
result = serve_fn(
    customer_id=tf.constant([100090964709, 170053803401, 330067280801], dtype=tf.int64),
    product_id=tf.constant([378964001001, 378964001001, 378964001001], dtype=tf.int64),
    date=tf.constant([1707955200, 1707955200, 1707955200], dtype=tf.int64),
    cust_value=tf.constant([5000.0, 3000.0, 12000.0], dtype=tf.float32),
)
# result['product_ids'].shape => (3, 100)
```

### Vocabulary Inspection

```python
# Check what customer/product IDs the model knows
with open('models/qt-131/Format-Serving/assets/customer_id_vocab') as f:
    customers = [line.strip() for line in f]
print(f'{len(customers)} customers in vocab')

with open('models/qt-131/Format-Serving/assets/product_id_vocab') as f:
    products = [line.strip() for line in f]
print(f'{len(products)} products in vocab')
```
