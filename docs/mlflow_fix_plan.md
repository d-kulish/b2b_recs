# MLflow Integration Fix Plan

**Date:** 2025-12-24
**Status:** Ready for Implementation
**Priority:** CRITICAL

---

## Executive Summary

The MLflow integration has a fundamental design flaw: it treats MLflow as optional and silently continues training when MLflow fails. Combined with Cloud Run cold-start timeouts, this results in experiments completing without any tracking data.

**Root Cause**: Lines 2595-2597 in `ml_platform/configs/services.py` catch MLflow exceptions and set `_mlflow_client = None`, then training proceeds normally without any error.

---

## Current State (BROKEN)

```
┌──────────────────────────────────────────────────────────────────┐
│                      Current Flow (WRONG)                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Trainer starts                                               │
│  2. Try MLflow init (10s timeout in old code)                   │
│       ├─ SUCCESS → logging works                                │
│       └─ FAILURE → warning logged, _mlflow_client = None        │
│                    ↓                                             │
│  3. Training proceeds anyway! (NO VALIDATION)                   │
│  4. Callbacks check if _mlflow_client: (silently skip)          │
│  5. Training completes                                           │
│  6. mlflow_info.json NOT written (because run_id is None)       │
│  7. Django shows "completed" but no MLflow data                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Proposed State (CORRECT)

```
┌──────────────────────────────────────────────────────────────────┐
│                     Proposed Flow (CORRECT)                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Trainer starts                                               │
│  2. MLflow validation (MANDATORY):                              │
│       a. Ping MLflow server health endpoint                     │
│       b. Create/get experiment                                   │
│       c. Start run                                               │
│       d. Confirm run_id is valid                                │
│       ├─ SUCCESS → proceed to training                          │
│       └─ FAILURE → RAISE EXCEPTION, ABORT TRAINING              │
│                                                                  │
│  3. Training proceeds (only if step 2 succeeded)                │
│  4. Per-epoch metrics logged to MLflow                          │
│  5. Training completes                                           │
│  6. Final metrics logged                                         │
│  7. mlflow_info.json written with valid run_id                  │
│  8. Django retrieves training history successfully               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Infrastructure - Eliminate Cold Starts (5 minutes)

**Goal**: Prevent cold start timeouts by keeping MLflow server warm.

**Action**: Set min-instances=1 on MLflow Cloud Run service.

```bash
gcloud run services update mlflow-server \
  --region=europe-central2 \
  --min-instances=1 \
  --project=b2b-recs
```

**Cost Impact**: ~$20-30/month additional
**Benefit**: Eliminates 12-30s cold start delays

**Verification**:
```bash
gcloud run services describe mlflow-server \
  --region=europe-central2 \
  --format="value(spec.template.metadata.annotations.'autoscaling.knative.dev/minScale')"
# Should output: 1
```

---

### Phase 2: Code Fix - Make MLflow Mandatory (30 minutes)

**Goal**: Trainer must validate MLflow is working BEFORE training starts.

**File**: `ml_platform/configs/services.py`

**Changes to TrainerModuleGenerator._generate_run_fn()**:

#### 2.1 Add MLflow health check function

```python
def _validate_mlflow_connection(tracking_uri: str, max_retries: int = 5) -> bool:
    """
    Validate MLflow server is reachable and responsive.
    Waits for cold start if necessary.

    Returns True if successful, raises exception on failure.
    """
    import urllib.request
    import urllib.error

    health_url = f"{tracking_uri}/health"

    for attempt in range(max_retries):
        try:
            # Simple GET request to health endpoint
            req = urllib.request.Request(health_url)
            req.add_header("Authorization", f"Bearer {_get_identity_token()}")

            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    logging.info(f"MLflow server healthy (attempt {attempt + 1})")
                    return True

        except Exception as e:
            wait_time = min(30, (attempt + 1) * 10)  # 10s, 20s, 30s, 30s, 30s
            logging.warning(f"MLflow health check failed (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                logging.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

    raise RuntimeError(
        f"MLflow server at {tracking_uri} is not reachable after {max_retries} attempts. "
        "Training cannot proceed without experiment tracking."
    )
```

#### 2.2 Modify MLflow initialization to be mandatory

Replace lines 2568-2597 with:

```python
    # =========================================================================
    # MLflow Initialization (MANDATORY - training will not proceed without it)
    # =========================================================================
    global _mlflow_client

    if not mlflow_tracking_uri:
        raise RuntimeError(
            "MLflow tracking URI not configured. "
            "Set mlflow_tracking_uri in custom_config or MLFLOW_TRACKING_URI env var."
        )

    # Step 1: Validate MLflow server is reachable
    logging.info(f"Validating MLflow connection: {mlflow_tracking_uri}")
    _validate_mlflow_connection(mlflow_tracking_uri)

    # Step 2: Initialize client and create run
    _mlflow_client = MLflowRestClient(mlflow_tracking_uri)

    experiment_id = _mlflow_client.set_experiment(MLFLOW_EXPERIMENT_NAME)
    if not experiment_id:
        raise RuntimeError(
            f"Failed to create/get MLflow experiment '{MLFLOW_EXPERIMENT_NAME}'. "
            "Training cannot proceed without experiment tracking."
        )

    mlflow_run_id = _mlflow_client.start_run(run_name=MLFLOW_RUN_NAME)
    if not mlflow_run_id:
        raise RuntimeError(
            f"Failed to start MLflow run. experiment_id={experiment_id}. "
            "Training cannot proceed without experiment tracking."
        )

    logging.info(f"MLflow initialized successfully:")
    logging.info(f"  Tracking URI: {mlflow_tracking_uri}")
    logging.info(f"  Experiment: {MLFLOW_EXPERIMENT_NAME} (id={experiment_id})")
    logging.info(f"  Run ID: {mlflow_run_id}")

    # Log parameters
    _mlflow_client.log_params({
        'epochs': epochs,
        'batch_size': batch_size,
        'learning_rate': learning_rate,
        ...
    })
```

#### 2.3 Remove conditional callback registration

Replace:
```python
if _mlflow_client:
    callbacks.append(MLflowCallback())
```

With:
```python
# MLflow callback is always added (we've validated MLflow is working)
callbacks.append(MLflowCallback())
```

---

### Phase 3: Add Diagnostic Artifact (10 minutes)

**Goal**: Even if something goes wrong, Django should know what happened.

**File**: `ml_platform/configs/services.py`

**Add to generated trainer code**:

```python
def _write_mlflow_status(gcs_output_path: str, status: dict):
    """Write MLflow initialization status to GCS for Django diagnostics."""
    if not gcs_output_path or not gcs_output_path.startswith('gs://'):
        return

    try:
        from google.cloud import storage

        path = gcs_output_path[5:]  # Remove 'gs://'
        bucket_name = path.split('/')[0]
        blob_path = '/'.join(path.split('/')[1:]) + '/mlflow_status.json'

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json.dumps(status, indent=2))

        logging.info(f"Wrote MLflow status to gs://{bucket_name}/{blob_path}")
    except Exception as e:
        logging.warning(f"Could not write MLflow status: {e}")
```

**Usage at start of run_fn**:
```python
# Write initial status
_write_mlflow_status(gcs_output_path, {
    'stage': 'initializing',
    'tracking_uri': mlflow_tracking_uri,
    'timestamp': datetime.utcnow().isoformat()
})
```

**On success**:
```python
_write_mlflow_status(gcs_output_path, {
    'stage': 'initialized',
    'run_id': mlflow_run_id,
    'experiment_name': MLFLOW_EXPERIMENT_NAME,
    'timestamp': datetime.utcnow().isoformat()
})
```

---

### Phase 4: Verification Test (15 minutes)

**Goal**: Test the fix before running a real experiment.

#### 4.1 Create a minimal test script

```python
# tests/test_mlflow_integration.py

"""
Standalone test for MLflow integration.
Run this BEFORE submitting a Quick Test to verify MLflow works.

Usage:
    poetry run python tests/test_mlflow_integration.py
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error
import urllib.parse

MLFLOW_TRACKING_URI = "https://mlflow-server-555035914949.europe-central2.run.app"
TEST_EXPERIMENT_NAME = "integration-test"

def get_identity_token():
    """Get identity token using gcloud CLI."""
    import subprocess
    result = subprocess.run(
        ['gcloud', 'auth', 'print-identity-token'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    raise RuntimeError(f"Failed to get identity token: {result.stderr}")

def test_mlflow_health():
    """Test 1: MLflow server is reachable."""
    print("\n=== Test 1: MLflow Server Health ===")

    token = get_identity_token()
    url = f"{MLFLOW_TRACKING_URI}/health"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            elapsed = time.time() - start
            print(f"✓ MLflow server healthy (response time: {elapsed:.1f}s)")
            return True
    except Exception as e:
        print(f"✗ MLflow server not reachable: {e}")
        return False

def test_create_experiment():
    """Test 2: Can create/get experiment."""
    print("\n=== Test 2: Create/Get Experiment ===")

    token = get_identity_token()

    # Try to get existing experiment
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/experiments/get-by-name?experiment_name={urllib.parse.quote(TEST_EXPERIMENT_NAME)}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            exp_id = result.get("experiment", {}).get("experiment_id")
            print(f"✓ Got existing experiment: {TEST_EXPERIMENT_NAME} (id={exp_id})")
            return exp_id
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Create new experiment
            print(f"  Experiment not found, creating...")
            url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/experiments/create"
            data = json.dumps({"name": TEST_EXPERIMENT_NAME}).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                exp_id = result.get("experiment_id")
                print(f"✓ Created experiment: {TEST_EXPERIMENT_NAME} (id={exp_id})")
                return exp_id
        print(f"✗ Failed to get/create experiment: {e}")
        return None

def test_create_run(experiment_id):
    """Test 3: Can create run and log metrics."""
    print("\n=== Test 3: Create Run and Log Metrics ===")

    token = get_identity_token()

    # Create run
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/create"
    data = json.dumps({
        "experiment_id": experiment_id,
        "run_name": f"test-run-{int(time.time())}"
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            run_id = result.get("run", {}).get("info", {}).get("run_id")
            print(f"✓ Created run: {run_id}")
    except Exception as e:
        print(f"✗ Failed to create run: {e}")
        return None

    # Log a metric
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/log-metric"
    data = json.dumps({
        "run_id": run_id,
        "key": "test_metric",
        "value": 0.95,
        "timestamp": int(time.time() * 1000),
        "step": 0
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"✓ Logged metric: test_metric=0.95")
    except Exception as e:
        print(f"✗ Failed to log metric: {e}")
        return run_id

    # End run
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/update"
    data = json.dumps({
        "run_id": run_id,
        "status": "FINISHED",
        "end_time": int(time.time() * 1000)
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"✓ Ended run successfully")
    except Exception as e:
        print(f"✗ Failed to end run: {e}")

    return run_id

def test_retrieve_metrics(run_id):
    """Test 4: Can retrieve logged metrics."""
    print("\n=== Test 4: Retrieve Metrics ===")

    token = get_identity_token()

    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/get?run_id={run_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            metrics = result.get("run", {}).get("data", {}).get("metrics", [])
            print(f"✓ Retrieved {len(metrics)} metrics")
            for m in metrics:
                print(f"    {m['key']}: {m['value']}")
            return True
    except Exception as e:
        print(f"✗ Failed to retrieve metrics: {e}")
        return False

def main():
    print("=" * 60)
    print("MLflow Integration Test")
    print("=" * 60)
    print(f"Tracking URI: {MLFLOW_TRACKING_URI}")

    all_passed = True

    # Test 1: Health
    if not test_mlflow_health():
        all_passed = False
        print("\n❌ FAILED: MLflow server not reachable. Check Cloud Run service.")
        return 1

    # Test 2: Experiment
    exp_id = test_create_experiment()
    if not exp_id:
        all_passed = False
        print("\n❌ FAILED: Cannot create experiment. Check IAM permissions.")
        return 1

    # Test 3: Run
    run_id = test_create_run(exp_id)
    if not run_id:
        all_passed = False
        print("\n❌ FAILED: Cannot create run. Check MLflow configuration.")
        return 1

    # Test 4: Retrieve
    if not test_retrieve_metrics(run_id):
        all_passed = False
        print("\n❌ FAILED: Cannot retrieve metrics.")
        return 1

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - MLflow integration is working!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

#### 4.2 Run the test

```bash
# From project root
python tests/test_mlflow_integration.py
```

Expected output:
```
============================================================
MLflow Integration Test
============================================================
Tracking URI: https://mlflow-server-555035914949.europe-central2.run.app

=== Test 1: MLflow Server Health ===
✓ MLflow server healthy (response time: 0.3s)

=== Test 2: Create/Get Experiment ===
✓ Got existing experiment: integration-test (id=4)

=== Test 3: Create Run and Log Metrics ===
✓ Created run: abc123...
✓ Logged metric: test_metric=0.95
✓ Ended run successfully

=== Test 4: Retrieve Metrics ===
✓ Retrieved 1 metrics
    test_metric: 0.95

============================================================
✅ ALL TESTS PASSED - MLflow integration is working!
============================================================
```

---

### Phase 5: Django Integration (10 minutes)

**Goal**: Django should check `mlflow_status.json` and show clear feedback when MLflow failed.

**File**: `ml_platform/experiments/services.py` - `_extract_results()`

Add after the existing `mlflow_info.json` extraction:

```python
# Also check mlflow_status.json for diagnostics
try:
    status_blob_path = mlflow_info_path.replace('mlflow_info.json', 'mlflow_status.json')
    status_blob = bucket.blob(status_blob_path)

    if status_blob.exists():
        status_content = status_blob.download_as_string().decode('utf-8')
        mlflow_status = json.loads(status_content)

        if mlflow_status.get('stage') == 'failed':
            quick_test.mlflow_error = mlflow_status.get('error', 'Unknown MLflow error')
            quick_test.save(update_fields=['mlflow_error'])
            logger.warning(
                f"MLflow initialization failed for {quick_test.display_name}: "
                f"{quick_test.mlflow_error}"
            )
except Exception as e:
    logger.debug(f"No mlflow_status.json found: {e}")
```

---

## Summary of Changes

| Phase | Description | Time | Files |
|-------|-------------|------|-------|
| 1 | Set min-instances=1 on MLflow Cloud Run | 5 min | Infrastructure |
| 2 | Make MLflow mandatory, add validation | 30 min | `configs/services.py` |
| 3 | Add diagnostic artifact | 10 min | `configs/services.py` |
| 4 | Create integration test | 15 min | `tests/test_mlflow_integration.py` |
| 5 | Django diagnostic extraction | 10 min | `experiments/services.py` |

**Total estimated time**: 70 minutes

---

## Verification Checklist

After implementing all phases:

- [ ] `gcloud run services describe mlflow-server` shows `minScale: 1`
- [ ] `python tests/test_mlflow_integration.py` passes all 4 tests
- [ ] New Quick Test fails immediately if MLflow is unreachable (no hour-long wait)
- [ ] New Quick Test with working MLflow creates `mlflow_info.json` with valid run_id
- [ ] Django UI shows training history for new experiments

---

## Rollback Plan

If issues arise:

1. **Revert code changes**: `git revert HEAD~N`
2. **Set min-instances back to 0**:
   ```bash
   gcloud run services update mlflow-server \
     --region=europe-central2 \
     --min-instances=0 \
     --project=b2b-recs
   ```

---

## Cost Impact

| Item | Before | After | Delta |
|------|--------|-------|-------|
| MLflow Cloud Run | ~$10/month (scale to 0) | ~$35/month (min=1) | +$25/month |
| Debugging time | Hours per experiment | 0 (fails fast) | Priceless |

---

## Appendix: Current Code Issues

### Issue 1: Silent Failure (lines 2595-2597)
```python
except Exception as e:
    logging.warning(f"MLflow initialization failed: {e}")
    _mlflow_client = None
# ← Training proceeds here without any check!
```

### Issue 2: Conditional Callback (line 2620)
```python
if _mlflow_client:
    callbacks.append(MLflowCallback())
# ← If MLflow failed, no callback added, no error raised
```

### Issue 3: No run_id Validation (line 2738)
```python
if mlflow_run_id and gcs_output_path:
    _write_mlflow_info(gcs_output_path, mlflow_run_id)
# ← If run_id is None, silently skips writing
```

### Issue 4: min-instances=0
```
AUTOSCALING.KNATIVE.DEV/MIN_SCALE
(empty) ← Defaults to 0, causes cold starts
```
