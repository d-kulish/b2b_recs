# MLflow Trainer Integration Fix

**Date:** 2024-12-24
**Status:** Resolved

## Problem Summary

MLflow experiment tracking was not working from the TFX Trainer component running on Vertex AI Pipelines. Quick Tests completed successfully but no data appeared in MLflow, and `mlflow_info.json` was never created.

---

## Root Causes Identified

### Issue 1: Missing `import time` Statement

**Location:** `ml_platform/configs/services.py` (TrainerModuleGenerator)

The generated `MLflowRestClient` class used `time.time()` in multiple places:
- Token caching/expiry checks
- Metric timestamps
- Run end timestamps

But the `time` module was never imported in the generated trainer code.

**Symptom:** `NameError: name 'time' is not defined` was raised on the first MLflow API call, caught by the exception handler, and silently ignored. Training continued without MLflow logging.

**Fix:** Added `import time` to the generated trainer module imports.

```python
# Before (broken)
import urllib.request
import urllib.error
import urllib.parse

# After (fixed)
import time              # <-- Added
import urllib.request
import urllib.error
import urllib.parse
```

### Issue 2: Missing Authentication in MLflowRestClient

**Location:** `ml_platform/configs/services.py` (TrainerModuleGenerator)

The original `MLflowRestClient._request()` method made HTTP requests without authentication headers. The MLflow Cloud Run service requires identity token authentication.

**Fix:** Added `_get_identity_token()` method that:
1. Tries `google.oauth2.id_token.fetch_id_token()` (preferred)
2. Falls back to GCP metadata server (always available on Vertex AI)
3. Caches tokens for ~1 hour

Added `_get_auth_headers()` method that includes `Authorization: Bearer <token>` in all requests.

### Issue 3: Insufficient IAM Permissions

**Location:** Cloud Run IAM policy for `mlflow-server`

The original IAM policy only allowed:
- `555035914949-compute@developer.gserviceaccount.com`
- `django-app@b2b-recs.iam.gserviceaccount.com`

But Vertex AI Pipeline components (and Custom Jobs) run with different service accounts that weren't included.

**Fix:** Added `allAuthenticatedUsers` to allow any authenticated GCP identity to invoke the MLflow server:

```bash
gcloud run services add-iam-policy-binding mlflow-server \
  --region=europe-central2 \
  --member="allAuthenticatedUsers" \
  --role="roles/run.invoker" \
  --project=b2b-recs
```

---

## Files Modified

| File | Change |
|------|--------|
| `ml_platform/configs/services.py` | Added `import time`, added `_get_identity_token()`, added `_get_auth_headers()`, updated `_request()` and `set_experiment()` to use auth |

---

## How to Test MLflow Integration

### Option 1: Run a Quick Test

Submit a Quick Test from the UI and verify:
1. Pipeline completes successfully
2. `mlflow_info.json` exists in GCS artifacts
3. QuickTest record has `mlflow_run_id` populated
4. Data appears in MLflow UI

### Option 2: Run Standalone Vertex AI Test

This test runs the MLflowRestClient code on Vertex AI without running the full TFX pipeline.

**Step 1: Create test script**

```python
# Save as /tmp/vertex_mlflow_test.py
import os
import sys
import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = "https://mlflow-server-555035914949.europe-central2.run.app"
MLFLOW_EXPERIMENT_NAME = "vertex-trainer-test"

class MLflowRestClient:
    """Copy of the generated MLflowRestClient with auth."""

    def __init__(self, tracking_uri):
        self.tracking_uri = tracking_uri.rstrip('/')
        self.run_id = None
        self.experiment_id = None
        self._token = None
        self._token_expiry = 0

    def _get_identity_token(self):
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token
            auth_req = google.auth.transport.requests.Request()
            self._token = google.oauth2.id_token.fetch_id_token(auth_req, self.tracking_uri)
            self._token_expiry = time.time() + 3600
            logger.info("Got token via google-auth")
            return self._token
        except Exception as e:
            logger.warning(f"google-auth failed: {e}")
        try:
            url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={urllib.parse.quote(self.tracking_uri)}"
            req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._token = resp.read().decode()
                self._token_expiry = time.time() + 3600
                logger.info("Got token via metadata server")
                return self._token
        except Exception as e:
            logger.error(f"Could not get token: {e}")
            return None

    def _get_auth_headers(self):
        headers = {"Content-Type": "application/json"}
        token = self._get_identity_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, endpoint, data):
        url = f"{self.tracking_uri}/api/2.0/mlflow/{endpoint}"
        headers = self._get_auth_headers()
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP {e.code}: {e.reason}")
            return None

    def set_experiment(self, name):
        try:
            url = f"{self.tracking_uri}/api/2.0/mlflow/experiments/get-by-name?experiment_name={urllib.parse.quote(name)}"
            req = urllib.request.Request(url, headers=self._get_auth_headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                self.experiment_id = result.get("experiment", {}).get("experiment_id")
                return self.experiment_id
        except urllib.error.HTTPError as e:
            if e.code == 404:
                result = self._request("experiments/create", {"name": name})
                if result:
                    self.experiment_id = result.get("experiment_id")
                return self.experiment_id
            return None

    def start_run(self, run_name=None):
        data = {"experiment_id": self.experiment_id}
        if run_name:
            data["run_name"] = run_name
        result = self._request("runs/create", data)
        if result:
            self.run_id = result.get("run", {}).get("info", {}).get("run_id")
        return self.run_id

    def log_metric(self, key, value, step=None):
        if self.run_id:
            data = {"run_id": self.run_id, "key": key, "value": float(value), "timestamp": int(time.time() * 1000)}
            if step is not None:
                data["step"] = step
            self._request("runs/log-metric", data)

    def end_run(self):
        if self.run_id:
            self._request("runs/update", {"run_id": self.run_id, "status": "FINISHED", "end_time": int(time.time() * 1000)})

def main():
    logger.info("Testing MLflow from Vertex AI...")
    client = MLflowRestClient(MLFLOW_TRACKING_URI)

    exp_id = client.set_experiment(MLFLOW_EXPERIMENT_NAME)
    if not exp_id:
        logger.error("FAILED: set_experiment")
        return 1

    run_id = client.start_run(run_name=f"test-{int(time.time())}")
    if not run_id:
        logger.error("FAILED: start_run")
        return 1

    client.log_metric("test_metric", 0.95, step=0)
    client.end_run()

    logger.info(f"SUCCESS! Run ID: {run_id}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Build and push container**

```bash
cd /tmp
mkdir mlflow-test && cd mlflow-test
cp /tmp/vertex_mlflow_test.py .

cat > Dockerfile << 'EOF'
FROM europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer:latest
WORKDIR /app
COPY vertex_mlflow_test.py /app/test.py
ENTRYPOINT ["python", "/app/test.py"]
EOF

gcloud builds submit --tag europe-central2-docker.pkg.dev/b2b-recs/cloud-run-source-deploy/mlflow-vertex-test:latest .
```

**Step 3: Submit Vertex AI Custom Job**

```bash
gcloud ai custom-jobs create \
  --region=europe-central2 \
  --display-name="mlflow-test" \
  --worker-pool-spec="machine-type=n1-standard-4,replica-count=1,container-image-uri=europe-central2-docker.pkg.dev/b2b-recs/cloud-run-source-deploy/mlflow-vertex-test:latest" \
  --project=b2b-recs
```

**Step 4: Check logs**

```bash
# Get job ID from create output, then:
gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="<JOB_ID>"' \
  --project=b2b-recs --limit=50 --format="value(textPayload)"
```

**Expected output:**
```
Testing MLflow from Vertex AI...
Got token via google-auth
SUCCESS! Run ID: <uuid>
```

---

## Verification Commands

**Check MLflow server connectivity:**
```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://mlflow-server-555035914949.europe-central2.run.app/api/2.0/mlflow/experiments/search" \
  -X POST -H "Content-Type: application/json" -d '{"max_results": 10}'
```

**Check MLflow IAM policy:**
```bash
gcloud run services get-iam-policy mlflow-server \
  --region=europe-central2 --project=b2b-recs
```

**Check if mlflow_info.json exists after Quick Test:**
```bash
gsutil cat gs://b2b-recs-quicktest-artifacts/qt-XX-XXXXXXXX-XXXXXX/mlflow_info.json
```

---

## Security Note

The current IAM policy includes `allAuthenticatedUsers` which allows any authenticated GCP identity to invoke the MLflow server. For production, consider:

1. Identifying the exact service account used by Vertex AI Pipeline Trainer components
2. Adding only that specific service account
3. Removing `allAuthenticatedUsers`

```bash
# To restrict access later:
gcloud run services remove-iam-policy-binding mlflow-server \
  --region=europe-central2 \
  --member="allAuthenticatedUsers" \
  --role="roles/run.invoker" \
  --project=b2b-recs

# Add specific SA instead:
gcloud run services add-iam-policy-binding mlflow-server \
  --region=europe-central2 \
  --member="serviceAccount:<PIPELINE_SA>@<PROJECT>.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --project=b2b-recs
```
