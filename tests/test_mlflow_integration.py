#!/usr/bin/env python3
"""
MLflow Integration Test

Standalone test to verify MLflow integration works BEFORE running a Quick Test.
This simulates exactly what the Trainer does on Vertex AI.

Usage:
    python tests/test_mlflow_integration.py

Expected output: All 4 tests pass.
If any test fails, DO NOT run a Quick Test until fixed.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MLFLOW_TRACKING_URI = "https://mlflow-server-555035914949.europe-central2.run.app"
TEST_EXPERIMENT_NAME = "integration-test"


def get_identity_token():
    """Get identity token using gcloud CLI (same as Trainer uses metadata server)."""
    result = subprocess.run(
        ['gcloud', 'auth', 'print-identity-token'],
        capture_output=True,
        text=True,
        timeout=30
    )
    if result.returncode == 0:
        return result.stdout.strip()
    raise RuntimeError(f"Failed to get identity token: {result.stderr}")


def make_request(url, data=None, method=None, timeout=30):
    """Make authenticated request to MLflow API."""
    token = get_identity_token()

    if data is not None:
        data = json.dumps(data).encode()
        method = method or "POST"
    else:
        method = method or "GET"

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def test_1_health():
    """Test 1: MLflow server is reachable and healthy."""
    print("\n" + "=" * 60)
    print("TEST 1: MLflow Server Health")
    print("=" * 60)

    url = f"{MLFLOW_TRACKING_URI}/health"
    token = get_identity_token()

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            elapsed = time.time() - start
            status = resp.status
            print(f"  Status: {status}")
            print(f"  Response time: {elapsed:.2f}s")

            if elapsed > 5:
                print(f"  WARNING: Slow response ({elapsed:.1f}s) - possible cold start")

            if status == 200:
                print("  RESULT: PASS")
                return True
            else:
                print(f"  RESULT: FAIL - unexpected status {status}")
                return False

    except urllib.error.URLError as e:
        print(f"  Error: {e}")
        print("  RESULT: FAIL - server not reachable")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        print("  RESULT: FAIL")
        return False


def test_2_experiment():
    """Test 2: Can create or get an experiment."""
    print("\n" + "=" * 60)
    print("TEST 2: Create/Get Experiment")
    print("=" * 60)

    # Try to get existing experiment
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/experiments/get-by-name"
    url += f"?experiment_name={urllib.parse.quote(TEST_EXPERIMENT_NAME)}"

    token = get_identity_token()
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            exp_id = result.get("experiment", {}).get("experiment_id")
            print(f"  Found existing experiment: {TEST_EXPERIMENT_NAME}")
            print(f"  Experiment ID: {exp_id}")
            print("  RESULT: PASS")
            return exp_id

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  Experiment '{TEST_EXPERIMENT_NAME}' not found, creating...")

            # Create new experiment
            url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/experiments/create"
            try:
                result = make_request(url, {"name": TEST_EXPERIMENT_NAME})
                exp_id = result.get("experiment_id")
                print(f"  Created experiment: {TEST_EXPERIMENT_NAME}")
                print(f"  Experiment ID: {exp_id}")
                print("  RESULT: PASS")
                return exp_id
            except Exception as create_error:
                print(f"  Failed to create experiment: {create_error}")
                print("  RESULT: FAIL")
                return None
        else:
            print(f"  HTTP Error: {e.code} - {e.reason}")
            print("  RESULT: FAIL")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        print("  RESULT: FAIL")
        return None


def test_3_run_and_metrics(experiment_id):
    """Test 3: Can create a run and log metrics (simulates training)."""
    print("\n" + "=" * 60)
    print("TEST 3: Create Run and Log Metrics")
    print("=" * 60)

    if not experiment_id:
        print("  Skipped - no experiment_id from previous test")
        print("  RESULT: SKIP")
        return None

    # Create run
    print("  Creating run...")
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/create"
    run_name = f"test-run-{int(time.time())}"

    try:
        result = make_request(url, {
            "experiment_id": experiment_id,
            "run_name": run_name
        })
        run_id = result.get("run", {}).get("info", {}).get("run_id")
        print(f"  Run ID: {run_id}")
        print(f"  Run Name: {run_name}")
    except Exception as e:
        print(f"  Failed to create run: {e}")
        print("  RESULT: FAIL")
        return None

    # Log parameters (like trainer does)
    print("  Logging parameters...")
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/log-parameter"
    params = {"epochs": "10", "batch_size": "4096", "learning_rate": "0.001"}

    for key, value in params.items():
        try:
            make_request(url, {"run_id": run_id, "key": key, "value": value})
        except Exception as e:
            print(f"  Failed to log param {key}: {e}")
            print("  RESULT: FAIL")
            return run_id
    print(f"  Logged {len(params)} parameters")

    # Log metrics (simulate per-epoch logging)
    print("  Logging metrics (simulating 3 epochs)...")
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/log-metric"

    for epoch in range(3):
        loss = 0.5 - (epoch * 0.1)  # Decreasing loss
        try:
            make_request(url, {
                "run_id": run_id,
                "key": "loss",
                "value": loss,
                "timestamp": int(time.time() * 1000),
                "step": epoch
            })
        except Exception as e:
            print(f"  Failed to log metric at epoch {epoch}: {e}")
            print("  RESULT: FAIL")
            return run_id

    print(f"  Logged loss for 3 epochs: [0.5, 0.4, 0.3]")

    # Log final metrics
    print("  Logging final metrics...")
    final_metrics = {
        "final_loss": 0.3,
        "test_recall_at_10": 0.15,
        "test_recall_at_50": 0.35,
        "test_recall_at_100": 0.45
    }

    for key, value in final_metrics.items():
        try:
            make_request(url, {
                "run_id": run_id,
                "key": key,
                "value": value,
                "timestamp": int(time.time() * 1000)
            })
        except Exception as e:
            print(f"  Failed to log {key}: {e}")

    print(f"  Logged {len(final_metrics)} final metrics")

    # End run
    print("  Ending run...")
    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/update"
    try:
        make_request(url, {
            "run_id": run_id,
            "status": "FINISHED",
            "end_time": int(time.time() * 1000)
        })
        print("  Run ended successfully")
        print("  RESULT: PASS")
        return run_id
    except Exception as e:
        print(f"  Failed to end run: {e}")
        print("  RESULT: FAIL")
        return run_id


def test_4_retrieve(run_id):
    """Test 4: Can retrieve logged data (simulates Django fetching training history)."""
    print("\n" + "=" * 60)
    print("TEST 4: Retrieve Logged Data")
    print("=" * 60)

    if not run_id:
        print("  Skipped - no run_id from previous test")
        print("  RESULT: SKIP")
        return False

    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/runs/get?run_id={run_id}"

    try:
        result = make_request(url)
        run_data = result.get("run", {})

        # Check info
        info = run_data.get("info", {})
        print(f"  Run ID: {info.get('run_id', 'N/A')[:16]}...")
        print(f"  Status: {info.get('status', 'N/A')}")
        print(f"  Experiment ID: {info.get('experiment_id', 'N/A')}")

        # Check data
        data = run_data.get("data", {})

        # Parameters
        params = data.get("params", [])
        print(f"  Parameters: {len(params)}")
        for p in params:
            print(f"    {p['key']}: {p['value']}")

        # Metrics
        metrics = data.get("metrics", [])
        print(f"  Metrics: {len(metrics)}")
        for m in metrics:
            print(f"    {m['key']}: {m['value']} (step={m.get('step', 'N/A')})")

        if len(metrics) > 0:
            print("  RESULT: PASS")
            return True
        else:
            print("  RESULT: FAIL - no metrics found")
            return False

    except Exception as e:
        print(f"  Error: {e}")
        print("  RESULT: FAIL")
        return False


def test_5_metric_history(run_id):
    """Test 5: Can retrieve metric history (for training curves)."""
    print("\n" + "=" * 60)
    print("TEST 5: Retrieve Metric History (Training Curves)")
    print("=" * 60)

    if not run_id:
        print("  Skipped - no run_id from previous test")
        print("  RESULT: SKIP")
        return False

    url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/metrics/get-history"
    url += f"?run_id={run_id}&metric_key=loss"

    try:
        result = make_request(url, method="GET")
        metrics = result.get("metrics", [])

        print(f"  Retrieved {len(metrics)} data points for 'loss'")

        if len(metrics) > 0:
            print("  History:")
            for m in sorted(metrics, key=lambda x: x.get('step', 0)):
                print(f"    Step {m.get('step', 'N/A')}: {m['value']}")
            print("  RESULT: PASS")
            return True
        else:
            print("  RESULT: FAIL - no history found")
            return False

    except Exception as e:
        print(f"  Error: {e}")
        print("  RESULT: FAIL")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("         MLFLOW INTEGRATION TEST SUITE")
    print("=" * 60)
    print(f"Tracking URI: {MLFLOW_TRACKING_URI}")
    print(f"Test Experiment: {TEST_EXPERIMENT_NAME}")
    print("=" * 60)

    results = {}

    # Test 1: Health
    results['health'] = test_1_health()
    if not results['health']:
        print("\n" + "!" * 60)
        print("CRITICAL: MLflow server not reachable!")
        print("Check Cloud Run service status and IAM permissions.")
        print("!" * 60)
        return 1

    # Test 2: Experiment
    experiment_id = test_2_experiment()
    results['experiment'] = experiment_id is not None
    if not results['experiment']:
        print("\n" + "!" * 60)
        print("CRITICAL: Cannot create/get experiment!")
        print("Check MLflow database and permissions.")
        print("!" * 60)
        return 1

    # Test 3: Run and Metrics
    run_id = test_3_run_and_metrics(experiment_id)
    results['run_metrics'] = run_id is not None

    # Test 4: Retrieve
    results['retrieve'] = test_4_retrieve(run_id)

    # Test 5: Metric History
    results['history'] = test_5_metric_history(run_id)

    # Summary
    print("\n" + "=" * 60)
    print("                    SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        symbol = "+" if passed else "X"
        print(f"  [{symbol}] {test_name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\nALL TESTS PASSED")
        print("MLflow integration is working correctly.")
        print("You can now run Quick Tests with confidence.")
        return 0
    else:
        print("\nSOME TESTS FAILED")
        print("DO NOT run Quick Tests until issues are resolved.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
