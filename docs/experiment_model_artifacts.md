# Experiment Model Artifacts & Inference Notebooks

## Document Purpose
This document describes the process of downloading experiment model artifacts from GCS and creating inference analysis notebooks for local evaluation.

**Last Updated**: 2026-02-27

---

## Why Save Artifacts Locally

GCS buckets `b2b-recs-quicktest-artifacts` and `b2b-recs-pipeline-staging` have a **7-day auto-delete** lifecycle policy. To preserve interesting experiment results for later analysis, we copy them into the `models/` directory and create inference notebooks.

---

## Step 1: Identify the Experiment

Find the GCS timestamp suffix for your experiment. Replace `{id}` with your Quick Test ID (e.g. `171`):

```bash
gsutil ls gs://b2b-recs-quicktest-artifacts/ | grep "qt-{id}"
# Example output: gs://b2b-recs-quicktest-artifacts/qt-171-20260227-112744/
```

Note the full prefix (e.g. `qt-171-20260227-112744`) — it is the same in both buckets.

---

## Step 2: Create Local Directory and Download Code Artifacts

```bash
mkdir -p models/qt-{id}

# Trainer code, transform code, and training metrics
gsutil cp \
  gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/trainer_module.py \
  gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/transform_module.py \
  gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/training_metrics.json \
  models/qt-{id}/
```

---

## Step 3: Download the SavedModel

The SavedModel is in the pipeline-staging bucket under the Trainer component output. Navigate the directory tree to find it:

```bash
# 1. List the pipeline root
gsutil ls gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/
# → 555035914949/

# 2. List the project number directory
gsutil ls gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/555035914949/
# → quicktest-qt-{id}-{timestamp}-YYYYMMDDHHMMSS/

# 3. List pipeline components
gsutil ls gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/555035914949/{job_name}/
# → BigQueryExampleGen_..., StatisticsGen_..., SchemaGen_..., Transform_..., Trainer_...

# 4. Copy the SavedModel
gsutil cp -r \
  gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/555035914949/{job_name}/Trainer_{hash}/model/Format-Serving \
  models/qt-{id}/
```

### Resulting Directory Structure

```
models/qt-{id}/
├── Format-Serving/           # TF SavedModel
│   ├── saved_model.pb
│   ├── variables/
│   │   ├── variables.data-00000-of-00001
│   │   └── variables.index
│   └── assets/               # Vocabulary files baked into model
│       ├── customer_id_vocab
│       ├── product_id_vocab
│       ├── category_vocab
│       ├── brand_vocab
│       ├── name_vocab
│       ├── sub_cat_v1_vocab
│       ├── sub_cat_v2_vocab
│       └── sub_cat_v3_vocab
├── trainer_module.py         # Generated trainer code (reference)
├── transform_module.py       # Generated preprocessing code (reference)
├── training_metrics.json     # Full epoch-by-epoch training history
└── inference_demo.ipynb      # Inference analysis notebook (step 4)
```

---

## Step 4: Create the Inference Notebook

Copy an existing notebook from a previous experiment and update it:

```bash
cp models/qt-{prev_id}/inference_demo.ipynb models/qt-{id}/inference_demo.ipynb
```

### What to Update

**1. Training-reported recall values** — extract from `training_metrics.json`:

```bash
python -c "
import json
with open('models/qt-{id}/training_metrics.json') as f:
    m = json.load(f)['final_metrics']
print(f'R@5={m[\"test_recall_at_5\"]:.3f}, R@10={m[\"test_recall_at_10\"]:.3f}, '
      f'R@50={m[\"test_recall_at_50\"]:.3f}, R@100={m[\"test_recall_at_100\"]:.3f}')
"
```

Update these values in three notebook cells:
- `c2-sample` — the `print(f'\nTraining reported: ...')` line at the end
- `c3-all-custs` — same print line
- `c4-comparison` — the `training_recall` dict at the top

**2. Serving signature inputs** — if the new experiment uses a different feature config, the model inputs may differ. Check them:

```python
import tensorflow as tf
model = tf.saved_model.load('models/qt-{id}/Format-Serving')
sig = model.signatures['serving_default']
for name, spec in sig.structured_input_signature[1].items():
    print(f'{name}: dtype={spec.dtype.name}, shape={spec.shape}')
```

If the inputs differ from the source notebook, update the `serve_fn()` calls in cells `c2-sample`, `c3-all-custs`, `c5-basket`, and `c6-visual` to match the new signature. Also update the BigQuery SELECT columns and the `.fillna()` / `.astype()` preparation lines accordingly.

**3. Clear old outputs** — remove stale results from the source experiment:

```python
import json
path = 'models/qt-{id}/inference_demo.ipynb'
with open(path) as f:
    nb = json.load(f)
for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        cell['outputs'] = []
        cell['execution_count'] = None
with open(path, 'w') as f:
    json.dump(nb, f, indent=1)
```

---

## Step 5: Run the Notebook

Open the notebook in VS Code or Jupyter and run all cells. The notebook expects:
- **Working directory**: `models/qt-{id}/` (relative paths to `Format-Serving/`)
- **BigQuery access**: authenticated `gcloud` session with access to `b2b-recs` project
- **Test dataset**: `b2b-recs.raw_data.ternopil_test_v4` (the BQ view used for evaluation)

---

## Notebook Sections Reference

The `inference_demo.ipynb` notebook contains these analysis sections:

| Cell ID | Section | What It Does |
|---------|---------|-------------|
| `c1-setup` | Setup | Loads model, vocabularies, BigQuery client |
| `c2-sample` | 100% match accuracy | 500 random interactions where both customer and product are in vocab |
| `c3-all-custs` | All customers accuracy | 500 random interactions where product is in vocab (customers may be OOV) |
| `c4-comparison` | Comparison chart | Scatter plot: training vs 100%-match vs all-customers recall |
| `c5-basket` | Daily basket coverage | Per-basket recall boxplots (known vs all customers) |
| `c6-visual` | Visual example | Random customer: actual purchases vs top-150 recommendations |
