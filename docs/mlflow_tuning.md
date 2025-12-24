# MLflow Integration Tuning

## Date: 2024-12-24

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

**Attempted Fix**: Runtime installation of mlflow library.

**Status**: Led to Problem 3

---

### Problem 3: MLflow Dependency Conflicts

**Symptom**:
```
Could not install MLflow: cannot import name 'Sentinel' from 'typing_extensions'
```

**Root Cause**: The TFX container has pinned versions of packages (`typing_extensions`, `pydantic`, `protobuf`) that conflict with both full `mlflow` and `mlflow-skinny` requirements.

**Attempted Fixes**:
1. Use `mlflow-skinny` instead of full `mlflow` - FAILED (same typing_extensions conflict)
2. Upgrade `typing_extensions` before installing mlflow - FAILED (Python module caching issues)

**Status**: Led to Final Solution

---

## Final Solution: MLflowRestClient (Zero Dependencies)

After multiple failed attempts to install the mlflow library in the TFX container, we implemented a **custom REST API client** that requires zero external dependencies.

### Implementation

The `MLflowRestClient` class uses Python's built-in `urllib` module to communicate directly with the MLflow REST API:

```python
import urllib.request
import urllib.error
import urllib.parse

class MLflowRestClient:
    """Lightweight MLflow client using REST API directly. No dependencies."""

    def __init__(self, tracking_uri):
        self.tracking_uri = tracking_uri.rstrip('/')
        self.run_id = None
        self.experiment_id = None

    def _request(self, endpoint, data):
        """Make POST request to MLflow API."""
        url = f"{self.tracking_uri}/api/2.0/mlflow/{endpoint}"
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def set_experiment(self, name): ...
    def start_run(self, run_name=None): ...
    def log_param(self, key, value): ...
    def log_params(self, params): ...
    def log_metric(self, key, value, step=None): ...
    def set_tag(self, key, value): ...
    def set_tags(self, tags): ...
    def end_run(self, status="FINISHED"): ...
```

### Benefits

1. **Zero external dependencies** - Uses only Python standard library
2. **No installation required** - Works immediately in any Python environment
3. **No version conflicts** - Doesn't interfere with TFX's dependency tree
4. **Full functionality** - Supports all required tracking operations

### Metrics Logged

- **Per-epoch**: `loss`, `val_loss`, `regularization_loss` (with step numbers)
- **Final**: `final_loss`, `final_val_loss`
- **Test**: `test_loss`, `test_recall_at_5`, `test_recall_at_10`, `test_recall_at_50`, `test_recall_at_100`

---

## Split Strategy Implementation

| Strategy | Train | Eval | Test | Implementation |
|----------|-------|------|------|----------------|
| **Random** | 80% | 15% | 5% | TFX hash buckets (16/3/1) |
| **Time Holdout** | 80% of rest | 20% of rest | Last N days | SQL `split` column + `partition_feature_name` |
| **Strict Temporal** | train_days | val_days | test_days | SQL `split` column + `partition_feature_name` |

---

## Files Modified

1. `ml_platform/configs/services.py` - Generated trainer code with MLflowRestClient
2. `ml_platform/experiments/services.py` - TFX pipeline split configuration
3. `ml_platform/datasets/services.py` - SQL generation with `split` column
4. `templates/ml_platform/model_experiments.html` - UI descriptions for split strategies

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
