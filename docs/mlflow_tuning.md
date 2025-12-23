# MLflow Integration Tuning

## Date: 2024-12-23

## Overview

This document tracks the fixes and tuning done to get MLflow working with the TFX Trainer on Vertex AI pipelines.

---

## Problems Encountered

### Problem 1: MLflow IAM Access Denied

**Symptom**: Trainer couldn't connect to MLflow Cloud Run server.

**Root Cause**: The Vertex AI compute service account (`555035914949-compute@developer.gserviceaccount.com`) was not in the MLflow Cloud Run invoker list.

**Fix**: Added IAM binding:
```bash
gcloud run services add-iam-policy-binding mlflow-server \
    --region=europe-central2 \
    --member="serviceAccount:555035914949-compute@developer.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --project=b2b-recs
```

**Status**: FIXED

---

### Problem 2: MLflow Module Not Found

**Symptom**: `ModuleNotFoundError: No module named 'mlflow'`

**Root Cause**: The TFX container image on Vertex AI doesn't have MLflow pre-installed.

**Fix**: Added runtime installation of MLflow in the generated trainer code:
```python
try:
    import mlflow
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mlflow>=2.0.0"])
    import mlflow
```

**Status**: FIXED (but led to Problem 3)

---

### Problem 3: MLflow Dependency Conflicts

**Symptom**:
```
Could not install MLflow: cannot import name 'Sentinel' from 'typing_extensions'
```

**Root Cause**: The TFX container has pinned versions of packages (`typing_extensions`, `pydantic`, `protobuf`) that conflict with full MLflow's requirements.

**Attempted Fix**: Use `mlflow-skinny` instead of full `mlflow`. This is a lightweight package with minimal dependencies, designed for tracking-only use cases.

```python
subprocess.check_call([sys.executable, "-m", "pip", "install", "mlflow-skinny>=2.0.0"])
```

**Status**: IN PROGRESS - Testing

---

## Current Implementation

### Generated Trainer Code (`configs/services.py`)

The trainer module now includes:

1. **Graceful MLflow import with auto-install**:
   ```python
   try:
       import mlflow
       MLFLOW_AVAILABLE = True
   except ImportError:
       # Install mlflow-skinny at runtime
       subprocess.check_call([...pip install mlflow-skinny...])
       import mlflow
       MLFLOW_AVAILABLE = True
   ```

2. **All MLflow calls protected by `MLFLOW_AVAILABLE` flag**:
   - `MLflowCallback.on_epoch_end()`
   - MLflow initialization in `run_fn()`
   - Logging params, tags, metrics
   - Test metrics logging

3. **Metrics logged to MLflow**:
   - Per-epoch: `loss`, `val_loss`, `regularization_loss`
   - Final: `final_loss`, `final_val_loss`
   - Test: `test_loss`, `test_recall_at_5`, `test_recall_at_10`, `test_recall_at_50`, `test_recall_at_100`

---

## Split Strategy Implementation

Also updated in this session:

| Strategy | Train | Eval | Test | Implementation |
|----------|-------|------|------|----------------|
| **Random** | 80% | 15% | 5% | TFX hash buckets (16/3/1) |
| **Time Holdout** | 80% of rest | 20% of rest | Last N days | SQL `split` column + `partition_feature_name` |
| **Strict Temporal** | train_days | val_days | test_days | SQL `split` column + `partition_feature_name` |

---

## Files Modified

1. `ml_platform/configs/services.py` - Generated trainer code with MLflow integration
2. `ml_platform/experiments/services.py` - TFX pipeline split configuration
3. `ml_platform/datasets/services.py` - SQL generation with `split` column
4. `templates/ml_platform/model_experiments.html` - UI descriptions for split strategies

---

## Next Steps

1. **Test mlflow-skinny installation** - Run experiment and verify MLflow connects successfully
2. **Verify Training tab** - Check that metrics appear in the View modal
3. **If mlflow-skinny fails**, alternatives:
   - Pin to older MLflow version (`mlflow==2.1.0`)
   - Upgrade `typing_extensions` before installing MLflow
   - Build custom Docker image with MLflow pre-installed

---

## Useful Commands

Check MLflow server logs:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=mlflow-server" --project=b2b-recs --limit=50
```

Check MLflow IAM:
```bash
gcloud run services get-iam-policy mlflow-server --region=europe-central2 --project=b2b-recs
```

Test MLflow server connectivity:
```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://mlflow-server-555035914949.europe-central2.run.app/api/2.0/mlflow/experiments/list
```
