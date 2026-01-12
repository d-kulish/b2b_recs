# Hybrid/Multitask Model Custom Job Testing

This document describes the process of testing the multitask trainer code generation using Vertex AI Custom Jobs, including the artifacts used, issues encountered, and fixes applied.

**Date:** 2026-01-12

## Overview

To validate the newly implemented multitask trainer code generation without running the full TFX pipeline (~1 hour), we used the Custom Job testing approach documented in `docs/custom_job_test.md`. This reduces iteration time to ~5-10 minutes by reusing Transform artifacts from a previous experiment.

## Test Configuration

### Configs Used

| Config | ID | Name | Details |
|--------|-----|------|---------|
| **Feature Config** | #9 | `cherng_v3_rank_#1` | Ranking config with `target_column=sales` |
| **Model Config** | #17 | `hybrid_v1` | Multitask model with retrieval_weight=1.0, ranking_weight=1.0 |

### Feature Config #9 Details

```
config_type: ranking
target_column: sales (with clip p1-p90 + log transform)

Buyer Features:
  - customer_id (embedding 64d)
  - date (cyclical weekly/monthly + bucket 100 + normalize)
  - cust_value (bucket 100 + normalize)

Product Features:
  - product_id (embedding 32d)
  - category (embedding 8d)
  - sub_category (embedding 16d)

Crosses:
  - Buyer: customer_id × cust_value
  - Product: category × sub_category
```

### Model Config #17 Details

```
model_type: multitask
buyer_tower_layers: 128 → 64 → 32 (with L2 reg)
product_tower_layers: 128 → 64 → 32 (with L2 reg)
rating_head_layers: 128 → 64 → 32 → 1
output_embedding_dim: 32
retrieval_weight: 1.0
ranking_weight: 1.0
retrieval_algorithm: brute_force
loss_function: mse
optimizer: adam
learning_rate: 0.001
batch_size: 1024
```

## Source Artifacts

We reused Transform artifacts from a completed ranking experiment:

**Source Experiment:** `qt-97-20260109-174616` (QuickTest ID 97, completed ranking experiment)

### Artifact Paths

| Artifact | GCS Path |
|----------|----------|
| Transform Graph | `gs://b2b-recs-pipeline-staging/pipeline_root/qt-97-20260109-174616/.../Transform_.../transform_graph/` |
| Train Examples | `gs://b2b-recs-pipeline-staging/pipeline_root/qt-97-20260109-174616/.../Transform_.../transformed_examples/Split-train/` |
| Eval Examples | `gs://b2b-recs-pipeline-staging/pipeline_root/qt-97-20260109-174616/.../Transform_.../transformed_examples/Split-eval/` |
| Test Examples | `gs://b2b-recs-pipeline-staging/pipeline_root/qt-97-20260109-174616/.../Transform_.../transformed_examples/Split-test/` |
| Schema | `gs://b2b-recs-pipeline-staging/pipeline_root/qt-97-20260109-174616/.../SchemaGen_.../schema/schema.pbtxt` |

### Why These Artifacts Are Compatible

The Transform artifacts from the ranking experiment can be reused for multitask because:

1. **Same Feature Config (#9)**: Produces identical transformed features
2. **Target column included**: The `sales_target` column is in the TFRecords (needed for ranking loss)
3. **Model-agnostic Transform**: Transform phase processes features independently of model type

## Test Process

### Step 1: Code Generation Verification (Dry Run)

```bash
./venv/bin/python scripts/test_services_trainer.py \
    --feature-config-id 9 \
    --model-config-id 17 \
    --source-exp qt-97-20260109-174616 \
    --epochs 2 \
    --dry-run
```

**Result:** Code generated successfully, syntax validated.

### Step 2: First Job Submission (QuickTest #64)

```bash
./venv/bin/python scripts/test_services_trainer.py \
    --feature-config-id 9 \
    --model-config-id 17 \
    --source-exp qt-97-20260109-174616 \
    --epochs 2 \
    --create-quicktest \
    --wait
```

**Result:** Job failed after ~4 minutes.

## Issues Encountered and Fixes

### Issue #1: Batch Shape Mismatch

**Error:**
```
tensorflow.python.framework.errors_impl.InvalidArgumentError:
Cannot batch tensors with different shapes in component 0.
First element had shape [1024,1] and element 12 had shape [964,1].
```

**Location:** `_precompute_candidate_embeddings()` at line 746

**Root Cause:**
The `_input_fn()` function returns a dataset that is already batched with `BATCH_SIZE=1024`. The `_precompute_candidate_embeddings()` function then tried to batch it again with `.batch(128)`, causing shape conflicts when the last batch had fewer elements.

**Original Code:**
```python
def _precompute_candidate_embeddings(model, candidates_dataset, batch_size=128):
    ...
    for batch in candidates_dataset.batch(batch_size):  # WRONG: double batching
```

**Fix Applied:** (`ml_platform/configs/services.py` line 5154)
```python
def _precompute_candidate_embeddings(model, candidates_dataset, batch_size=128):
    """
    ...
    NOTE: candidates_dataset is expected to be ALREADY batched from _input_fn.
    We iterate directly without calling .batch() again.
    """
    ...
    # Dataset is already batched from _input_fn, iterate directly
    for batch in candidates_dataset:  # FIXED: no re-batching
```

### Issue #2: GCS Path Check Using os.path.exists()

**Error:**
```
No test split found - skipping test evaluation
```

**Location:** `run_fn()` test set evaluation section

**Root Cause:**
The code used `os.path.exists()` and `glob.glob()` to check for the test split directory, but these functions only work for local filesystem paths, not GCS paths.

**Original Code:**
```python
test_split_dir = os.path.join(
    os.path.dirname(os.path.dirname(fn_args.train_files[0])),
    'Split-test'
)
if os.path.exists(test_split_dir):  # WRONG: doesn't work for GCS
    test_files = glob.glob(os.path.join(test_split_dir, '*.gz'))
```

**Fix Applied:** (`ml_platform/configs/services.py` lines 5666-5673)
```python
# Check for test split - use tf.io.gfile for GCS compatibility
train_files_dir = fn_args.train_files[0].rsplit('/', 1)[0]
parent_dir = train_files_dir.rsplit('/', 1)[0]
test_split_dir = f"{parent_dir}/Split-test"

if tf.io.gfile.exists(test_split_dir):  # FIXED: works for GCS
    test_files = tf.io.gfile.glob(f"{test_split_dir}/*.gz")
```

## Test Runs Summary

| QuickTest | Job ID | Status | Issue |
|-----------|--------|--------|-------|
| #64 (ID: 100) | 4062408492097470464 | Failed | Batch shape mismatch |
| #65 (ID: 101) | 8961198986769727488 | Completed | Test eval skipped (GCS path issue) |
| #66 (ID: 102) | (pending) | Pending | Waiting for resources in europe-central2 |

### QuickTest #65 Results (Partial Success)

Training completed successfully but test evaluation was skipped due to the GCS path issue:

```
Candidate deduplication: 1040 unique products from 13252 transactions
No test split found - skipping test evaluation
Saving model to: /tmp/trainer_test_1gtugnhx/serving_model
```

**Metrics captured:**
- Training loss: 3523.9 → 3346.2 (2 epochs)
- Validation RMSE: 1.033 → 0.954
- Validation MAE: 0.808 → 0.735
- Model saved with dual signatures (serve + serve_ranking)

**Metrics NOT captured (due to skipped test eval):**
- Recall@5/10/50/100
- Test RMSE/MAE

## Enhanced Test Script

The `scripts/test_services_trainer.py` was enhanced with new options:

| Argument | Description |
|----------|-------------|
| `--create-quicktest` | Create a QuickTest record in Django DB before submitting |
| `--wait` | Wait for job completion and fetch metrics automatically |
| `--timeout` | Timeout in minutes for `--wait` (default: 30) |

### New Helper Functions Added

1. **`create_quicktest_record()`**: Creates a QuickTest record with status='running'
2. **`wait_for_job_completion()`**: Polls Vertex AI until job finishes
3. **`fetch_metrics_from_gcs()`**: Downloads training_metrics.json from GCS
4. **`update_quicktest_with_metrics()`**: Updates QuickTest record with final metrics

## Files Modified

| File | Changes |
|------|---------|
| `ml_platform/configs/services.py` | Fixed batch issue (line 5154), fixed GCS path issue (lines 5666-5673) |
| `scripts/test_services_trainer.py` | Added `--create-quicktest`, `--wait`, `--timeout` options and helper functions |

## Verification Commands

### Check Job Status
```bash
gcloud ai custom-jobs describe JOB_ID --region=europe-central2 --format='value(state)'
```

### View Job Logs
```bash
gcloud logging read "resource.type=ml_job AND resource.labels.job_id=JOB_ID" \
    --project=b2b-recs --limit=100 --format="value(textPayload)"
```

### Check Generated Trainer Code
```bash
gsutil cat gs://b2b-recs-quicktest-artifacts/services-test-TIMESTAMP/trainer_module.py | head -50
```

### Check Training Metrics
```bash
gsutil cat gs://b2b-recs-quicktest-artifacts/services-test-TIMESTAMP/training_metrics.json | python -m json.tool
```

### Verify QuickTest in Django
```python
from ml_platform.models import QuickTest
qt = QuickTest.objects.get(experiment_number=66)
print(f"Status: {qt.status}")
print(f"Recall@100: {qt.recall_at_100}")
print(f"RMSE: {qt.rmse}")
```

## Next Steps

Once QuickTest #66 completes (pending resources), the full test will validate:

1. **Training**: MultitaskModel with weighted loss (retrieval + ranking)
2. **Candidate Embedding**: Deduplication of 1040 unique products
3. **Test Evaluation**: Both Recall@K and RMSE/MAE metrics
4. **Model Export**: Dual serving signatures
5. **DB Storage**: All 8 metrics stored in QuickTest record

## Conclusion

The custom job testing approach successfully identified two bugs in the multitask trainer code generation:

1. Double-batching in `_precompute_candidate_embeddings()`
2. Using local filesystem functions for GCS paths

Both issues have been fixed. The multitask training logic itself works correctly, as evidenced by QuickTest #65 completing training and saving the model with dual signatures.
