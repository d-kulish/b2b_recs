# MLflow Integration Plan for Experiments Domain

## Overview

Integrate MLflow as a backend for structured experiment tracking in the b2b_recs SaaS platform. MLflow will be deployed as a Cloud Run service, with Django providing custom visualizations.

**Architecture**: MLflow Server (Cloud Run) ← REST API ← Django (Custom UI)

---

## Implementation Status

**Last Updated**: 2025-12-23

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| **Phase 1** | MLflow Cloud Run Infrastructure | ✅ COMPLETE | Deployed to Cloud Run |
| **Phase 2** | Trainer Module MLflow Integration | ✅ COMPLETE | Code generation updated |
| **Phase 3** | Django MLflow Service Client | ✅ COMPLETE | `mlflow_service.py` created |
| **Phase 4** | Experiment Comparison UI | ✅ COMPLETE | Compare modal implemented |
| **Phase 5** | Per-Epoch Training Charts | ✅ COMPLETE | Chart.js integration done |
| **Phase 6** | Experiments Dashboard & Heatmaps | ✅ COMPLETE | Dashboard chapter with leaderboard + heatmap |

### What's Working Now

**Backend:**
- MLflow server deployed at `https://mlflow-server-555035914949.europe-central2.run.app`
- Trainer code generation includes MLflow tracking (params, metrics, callbacks)
- MLflow run ID written to GCS and extracted by Django after pipeline completion
- QuickTest model has `mlflow_run_id` and `mlflow_experiment_name` fields
- Django MLflow service client (`ml_platform/experiments/mlflow_service.py`)
- Training history API endpoint fetches per-epoch metrics from MLflow
- Experiment comparison API endpoint for side-by-side analysis
- Leaderboard API endpoint sorted by metrics
- **NEW**: Heatmap API endpoint for config combination analysis
- **NEW**: Dashboard stats API endpoint for summary metrics

**Frontend:**
- Training tab with Chart.js visualizations (loss + recall curves)
- Compare modal with metrics/params tables and best value highlighting
- **NEW**: Experiments Dashboard chapter (separate from Quick Test)
- **NEW**: Summary cards (Total, Completed, Best R@100, Avg R@100)
- **NEW**: Sortable leaderboard table with clickable rows
- **NEW**: Configuration heatmap (grouped bar chart by config combinations)

### Files Created/Modified (All Phases)
| File | Action | Description |
|------|--------|-------------|
| `ml_platform/experiments/mlflow_service.py` | CREATED | MLflow REST API client |
| `ml_platform/experiments/artifact_service.py` | MODIFIED | `get_training_history()` now uses MLflowService |
| `ml_platform/experiments/api.py` | MODIFIED | Added `compare_experiments()`, `experiment_leaderboard()`, `experiment_heatmap()`, `experiment_dashboard_stats()` |
| `ml_platform/experiments/urls.py` | MODIFIED | Added routes for all MLflow endpoints |
| `templates/ml_platform/model_experiments.html` | MODIFIED | Added Chart.js, training charts, compare modal, Experiments Dashboard chapter |

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/quick-tests/<id>/training-history/` | GET | Per-epoch training metrics from MLflow |
| `/api/experiments/compare/` | POST | Compare multiple experiments side-by-side |
| `/api/experiments/leaderboard/` | GET | Ranked experiments by metric |
| `/api/experiments/heatmap/` | GET | Config combination matrix data |
| `/api/experiments/dashboard-stats/` | GET | Summary statistics for dashboard |

### UI Structure
```
model_experiments.html
├── Quick Test Chapter (existing)
│   ├── Experiment cards with checkboxes
│   ├── Compare button + modal
│   └── View modal with Training tab (charts)
│
└── Experiments Dashboard Chapter (NEW)
    ├── Summary Dashboard (4 stat cards)
    ├── Leaderboard Table (sortable, clickable)
    └── Configuration Heatmap (Chart.js grouped bar)
```

---

## Deployed Resources (Phase 1)

| Resource | Value |
|----------|-------|
| **MLflow Server URL** | `https://mlflow-server-555035914949.europe-central2.run.app` |
| **Service Account** | `mlflow-server@b2b-recs.iam.gserviceaccount.com` |
| **GCS Artifacts Bucket** | `gs://b2b-recs-mlflow-artifacts` |
| **Database** | `mlflow` on `b2b-recs-db` Cloud SQL instance |
| **Secret** | `mlflow-db-uri` in Secret Manager |
| **Django Setting** | `MLFLOW_TRACKING_URI` in `config/settings.py` |

---

## Phase Summary

| Phase | Description | Effort |
|-------|-------------|--------|
| **Phase 1** | MLflow Cloud Run Infrastructure | 1-2 days |
| **Phase 2** | Trainer Module MLflow Integration | 1 day |
| **Phase 3** | Django MLflow Service Client | 1 day |
| **Phase 4** | Experiment Comparison UI | 1-2 days |
| **Phase 5** | Per-Epoch Training Charts | 1 day |
| **Phase 6** | Configuration Heatmaps (Optional) | 1 day |

---

## Phase 1: MLflow Cloud Run Infrastructure ✅ COMPLETE

### Objective
Deploy MLflow Tracking Server as a Cloud Run service with PostgreSQL backend and GCS artifact storage.

### Implementation Notes
- Dockerfile uses CMD instead of ENTRYPOINT script (permission issues on Cloud Run)
- Added `--add-cloudsql-instances` flag for Cloud SQL connectivity
- Scale to 0 enabled for cost savings (~$10-15/month)

### Files to Create

```
mlflow_server/
├── Dockerfile                    # Python 3.10 + MLflow + gunicorn
├── cloudbuild.yaml               # Build → Push → Deploy pipeline
├── requirements.txt              # mlflow, google-cloud-storage, psycopg2
├── entrypoint.sh                 # MLflow server startup script
└── README.md                     # Deployment documentation
```

### 1.1 Dockerfile

```dockerfile
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Run as non-root user
RUN useradd -m -u 1000 mlflow
USER mlflow

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
```

### 1.2 requirements.txt

```
mlflow==2.9.2
google-cloud-storage==2.14.0
psycopg2-binary==2.9.9
gunicorn==21.2.0
```

### 1.3 entrypoint.sh

```bash
#!/bin/bash
set -e

# Environment variables expected:
# - MLFLOW_BACKEND_STORE_URI: postgresql://user:pass@host:5432/mlflow
# - MLFLOW_ARTIFACT_ROOT: gs://b2b-recs-mlflow-artifacts
# - PORT: 8080 (Cloud Run default)

mlflow server \
    --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
    --default-artifact-root "${MLFLOW_ARTIFACT_ROOT}" \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --serve-artifacts \
    --workers 2
```

### 1.4 cloudbuild.yaml

```yaml
steps:
  # Build Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:$COMMIT_SHA', '.']
    dir: 'mlflow_server'

  # Push to Artifact Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:$COMMIT_SHA']

  # Tag as latest
  - name: 'gcr.io/cloud-builders/docker'
    args: ['tag', 'europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:$COMMIT_SHA',
           'europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:latest']

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:latest']

  # Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'mlflow-server'
      - '--image=europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:$COMMIT_SHA'
      - '--region=europe-central2'
      - '--memory=2Gi'
      - '--cpu=2'
      - '--timeout=600'
      - '--concurrency=20'
      - '--min-instances=0'
      - '--max-instances=3'
      - '--no-allow-unauthenticated'
      - '--service-account=mlflow-server@$PROJECT_ID.iam.gserviceaccount.com'
      - '--set-secrets=MLFLOW_BACKEND_STORE_URI=mlflow-db-uri:latest'
      - '--set-env-vars=MLFLOW_ARTIFACT_ROOT=gs://b2b-recs-mlflow-artifacts'

images:
  - 'europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:$COMMIT_SHA'
  - 'europe-central2-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/mlflow-server:latest'
```

### 1.5 GCP Setup Commands

```bash
# 1. Create service account
gcloud iam service-accounts create mlflow-server \
    --display-name="MLflow Tracking Server"

# 2. Grant permissions
gcloud projects add-iam-policy-binding b2b-recs \
    --member="serviceAccount:mlflow-server@b2b-recs.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding b2b-recs \
    --member="serviceAccount:mlflow-server@b2b-recs.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"

# 3. Create GCS bucket for artifacts
gsutil mb -l europe-central2 gs://b2b-recs-mlflow-artifacts

# 4. Create database (use existing Cloud SQL instance - shared with Django)
gcloud sql databases create mlflow --instance=django-db

# 5. Create secret for DB connection string
echo -n "postgresql://mlflow_user:PASSWORD@/mlflow?host=/cloudsql/b2b-recs:europe-central2:django-db" | \
    gcloud secrets create mlflow-db-uri --data-file=-

# 6. Allow Django to invoke MLflow
gcloud run services add-iam-policy-binding mlflow-server \
    --region=europe-central2 \
    --member="serviceAccount:django-app@b2b-recs.iam.gserviceaccount.com" \
    --role="roles/run.invoker"

# 7. Build and deploy
gcloud builds submit --config=mlflow_server/cloudbuild.yaml
```

---

## Phase 2: Trainer Module MLflow Integration ✅ COMPLETE

### Objective
Modify `TrainerModuleGenerator` to inject MLflow logging into generated trainer code.

### Implementation Notes
- Added MLflow imports and constants to generated trainer code
- Created `MLflowCallback` class for per-epoch metric logging
- Modified `run_fn()` to initialize MLflow, log params/tags, and write `mlflow_info.json` to GCS
- MLflow tracking URI passed via `custom_config` (since env vars not available on Vertex AI)
- ExperimentService extracts MLflow run ID from GCS after pipeline completion
- Migration `0039_add_mlflow_tracking_fields.py` adds `mlflow_run_id` and `mlflow_experiment_name` to QuickTest

### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/configs/services.py` | Added `_generate_mlflow_callback()`, updated `_generate_imports()`, `_generate_constants()`, `_generate_run_fn()` |
| `ml_platform/experiments/services.py` | Added `mlflow_tracking_uri` to custom_config, extract MLflow info in `_extract_results()` |
| `ml_platform/models.py` | Added `mlflow_run_id` and `mlflow_experiment_name` fields to QuickTest |
| `ml_platform/migrations/0039_add_mlflow_tracking_fields.py` | Database migration |

### 2.1 Update TrainerModuleGenerator

**File**: `/Users/dkulish/Projects/b2b_recs/ml_platform/configs/services.py`

Add new methods to `TrainerModuleGenerator` class:

```python
# In _generate_imports() - add after existing imports:
def _generate_imports(self) -> str:
    # ... existing imports ...
    imports += '''
import mlflow
import mlflow.tensorflow
from mlflow.tracking import MlflowClient
'''
    return imports

# In _generate_constants() - add MLflow config:
def _generate_constants(self) -> str:
    # ... existing constants ...
    constants += f'''
# MLflow Configuration
MLFLOW_TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', '')
MLFLOW_EXPERIMENT_NAME = '{self.feature_config.dataset.model_endpoint.name}'
MLFLOW_RUN_NAME = os.environ.get('MLFLOW_RUN_NAME', 'quick-test')
'''
    return constants
```

Add new method `_generate_mlflow_callback()`:

```python
def _generate_mlflow_callback(self) -> str:
    return '''
class MLflowCallback(tf.keras.callbacks.Callback):
    """Log metrics to MLflow after each epoch."""

    def on_epoch_end(self, epoch, logs=None):
        if logs and mlflow.active_run():
            for metric_name, value in logs.items():
                mlflow.log_metric(metric_name, float(value), step=epoch)
'''
```

Modify `_generate_run_fn()` to wrap training in MLflow context:

```python
def _generate_run_fn(self) -> str:
    # ... existing setup code ...

    run_fn_code = '''
def run_fn(fn_args):
    """TFX Trainer entry point with MLflow tracking."""

    # ... existing transform output loading ...

    # Initialize MLflow
    if MLFLOW_TRACKING_URI:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    with mlflow.start_run(run_name=MLFLOW_RUN_NAME) as run:
        # Log parameters
        mlflow.log_params({
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': learning_rate,
            'optimizer': OPTIMIZER,
            'embedding_dim': EMBEDDING_DIM,
            'feature_config_id': {self.feature_config.id},
            'model_config_id': {self.model_config.id},
            'dataset_id': {self.feature_config.dataset.id},
        })

        # Log feature config details as tags
        mlflow.set_tags({
            'feature_config_name': '{self.feature_config.name}',
            'model_config_name': '{self.model_config.name}',
            'dataset_name': '{self.feature_config.dataset.name}',
            'model_type': '{self.model_config.model_type}',
        })

        # ... existing model building code ...

        # Add MLflow callback
        callbacks = [
            MLflowCallback(),
            # ... existing callbacks ...
        ]

        # Train
        history = model.fit(
            train_dataset,
            validation_data=eval_dataset,
            epochs=epochs,
            callbacks=callbacks
        )

        # Log final metrics
        final_metrics = history.history
        for metric_name, values in final_metrics.items():
            mlflow.log_metric(f'final_{metric_name}', float(values[-1]))

        # Log test metrics if available
        if test_dataset:
            test_results = model.evaluate(test_dataset, return_dict=True)
            for name, value in test_results.items():
                mlflow.log_metric(f'test_{name}', float(value))

        # Log model artifact
        mlflow.tensorflow.log_model(
            model,
            artifact_path='model',
            registered_model_name=None  # Don't register for quick tests
        )

        # Write run_id to GCS for Django to read
        run_id = run.info.run_id
        _write_mlflow_run_id(fn_args, run_id)

        # ... existing model saving code ...

def _write_mlflow_run_id(fn_args, run_id: str):
    """Write MLflow run ID to GCS for Django to retrieve."""
    from google.cloud import storage
    import json

    # Extract output path from custom_config
    output_path = fn_args.custom_config.get('gcs_output_path', '')
    if not output_path:
        return

    # Write to mlflow_info.json
    if output_path.startswith('gs://'):
        path = output_path[5:]
        bucket_name = path.split('/')[0]
        blob_path = '/'.join(path.split('/')[1:]) + '/mlflow_info.json'

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json.dumps({
            'run_id': run_id,
            'experiment_name': MLFLOW_EXPERIMENT_NAME,
        }))
'''
    return run_fn_code
```

### 2.2 Update ExperimentService

**File**: `/Users/dkulish/Projects/b2b_recs/ml_platform/experiments/services.py`

Pass MLflow environment variables to Cloud Build:

```python
def _trigger_cloud_build(self, ...):
    # ... existing code ...

    # Add MLflow URI to environment
    mlflow_uri = getattr(settings, 'MLFLOW_TRACKING_URI',
                         'https://mlflow-server-xxxxx.europe-central2.run.app')

    # In Cloud Build step, add environment variable:
    # --set-env-vars=MLFLOW_TRACKING_URI={mlflow_uri}
```

### 2.3 Update QuickTest Model

**File**: `/Users/dkulish/Projects/b2b_recs/ml_platform/models.py`

Add MLflow tracking fields to QuickTest:

```python
class QuickTest(models.Model):
    # ... existing fields ...

    # MLflow tracking
    mlflow_run_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="MLflow run ID for this experiment"
    )
    mlflow_experiment_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="MLflow experiment name"
    )
```

### 2.4 Update _extract_results()

**File**: `/Users/dkulish/Projects/b2b_recs/ml_platform/experiments/services.py`

Read MLflow run ID from GCS after completion:

```python
def _extract_results(self, quick_test):
    # ... existing metrics extraction ...

    # Read MLflow info
    mlflow_info_path = f"{quick_test.gcs_artifacts_path}/mlflow_info.json"
    # ... parse bucket/blob ...
    if blob.exists():
        mlflow_info = json.loads(blob.download_as_string().decode())
        quick_test.mlflow_run_id = mlflow_info.get('run_id', '')
        quick_test.mlflow_experiment_name = mlflow_info.get('experiment_name', '')
```

---

## Phase 3: Django MLflow Service Client 🔲 START HERE

### Objective
Create a service class to query MLflow REST API from Django.

### Prerequisites
- Run a Quick Test to verify MLflow tracking works end-to-end
- Check that `mlflow_run_id` is populated in QuickTest after completion

### Files to Create/Modify

| File | Action |
|------|--------|
| `ml_platform/experiments/mlflow_service.py` | CREATE - MLflow API client |
| `ml_platform/experiments/api.py` | MODIFY - Add MLflow endpoints |
| `ml_platform/experiments/urls.py` | MODIFY - Add routes |
| `config/settings.py` | Already done in Phase 1 |

### 3.1 MLflow Service Class

**File**: `/Users/dkulish/Projects/b2b_recs/ml_platform/experiments/mlflow_service.py`

```python
"""
MLflow Service Client

Provides Django interface to MLflow Tracking Server REST API.
Follows same pattern as artifact_service.py for service-to-service auth.
"""
import json
import logging
import os
import subprocess
from typing import Dict, List, Optional

import requests
import google.auth.transport.requests
import google.oauth2.id_token

logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.environ.get(
    'MLFLOW_TRACKING_URI',
    'https://mlflow-server-xxxxx.europe-central2.run.app'
)


class MLflowService:
    """
    Client for MLflow Tracking Server.

    Provides methods to query experiments, runs, and metrics
    for display in Django UI.
    """

    def __init__(self, model_endpoint=None):
        self.model_endpoint = model_endpoint
        self.tracking_uri = MLFLOW_TRACKING_URI
        self._token = None

    def _get_auth_token(self) -> Optional[str]:
        """Get identity token for Cloud Run service-to-service calls."""
        # Production: Use google.oauth2.id_token
        try:
            auth_req = google.auth.transport.requests.Request()
            return google.oauth2.id_token.fetch_id_token(auth_req, self.tracking_uri)
        except Exception:
            pass

        # Local dev fallback: gcloud CLI
        try:
            result = subprocess.run(
                ['gcloud', 'auth', 'print-identity-token'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return None

    def _api_call(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make authenticated API call to MLflow server."""
        url = f"{self.tracking_uri}/api/2.0/mlflow{endpoint}"

        headers = {'Content-Type': 'application/json'}
        token = self._get_auth_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            if method == 'GET':
                response = requests.get(url, params=data, headers=headers, timeout=30)
            else:
                response = requests.post(url, json=data, headers=headers, timeout=30)

            if response.ok:
                return response.json()
            else:
                logger.warning(f"MLflow API error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.exception(f"MLflow API call failed: {e}")
            return None

    # =========================================================================
    # Run Methods
    # =========================================================================

    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get details for a specific MLflow run."""
        result = self._api_call('GET', '/runs/get', {'run_id': run_id})
        return result.get('run') if result else None

    def get_run_metrics(self, run_id: str) -> Dict[str, List[Dict]]:
        """
        Get all metrics for a run (including per-epoch history).

        Returns:
            {
                'loss': [{'step': 0, 'value': 0.5, 'timestamp': ...}, ...],
                'val_loss': [...],
                ...
            }
        """
        run = self.get_run(run_id)
        if not run:
            return {}

        metrics = {}
        for metric in run.get('data', {}).get('metrics', []):
            metric_key = metric['key']
            # Get full metric history
            history = self._api_call('GET', '/metrics/get-history', {
                'run_id': run_id,
                'metric_key': metric_key
            })
            if history:
                metrics[metric_key] = history.get('metrics', [])

        return metrics

    def get_run_params(self, run_id: str) -> Dict[str, str]:
        """Get parameters for a run."""
        run = self.get_run(run_id)
        if not run:
            return {}

        params = {}
        for param in run.get('data', {}).get('params', []):
            params[param['key']] = param['value']

        return params

    # =========================================================================
    # Experiment Methods
    # =========================================================================

    def get_experiment_by_name(self, name: str) -> Optional[Dict]:
        """Get experiment by name."""
        result = self._api_call('GET', '/experiments/get-by-name', {'experiment_name': name})
        return result.get('experiment') if result else None

    def list_runs(
        self,
        experiment_name: str,
        max_results: int = 100,
        order_by: str = 'start_time DESC'
    ) -> List[Dict]:
        """
        List runs in an experiment.

        Args:
            experiment_name: Name of the experiment
            max_results: Maximum number of runs to return
            order_by: Ordering (e.g., 'metrics.recall_at_100 DESC')

        Returns:
            List of run dictionaries
        """
        experiment = self.get_experiment_by_name(experiment_name)
        if not experiment:
            return []

        result = self._api_call('POST', '/runs/search', {
            'experiment_ids': [experiment['experiment_id']],
            'max_results': max_results,
            'order_by': [order_by]
        })

        return result.get('runs', []) if result else []

    # =========================================================================
    # Comparison Methods
    # =========================================================================

    def compare_runs(self, run_ids: List[str]) -> Dict:
        """
        Compare multiple runs for side-by-side analysis.

        Returns:
            {
                'runs': [...],
                'metrics': {
                    'loss': {'run_1': 0.1, 'run_2': 0.2},
                    'recall_at_100': {...}
                },
                'params': {
                    'learning_rate': {'run_1': '0.001', 'run_2': '0.01'},
                    ...
                }
            }
        """
        runs = []
        all_metrics = {}
        all_params = {}

        for run_id in run_ids:
            run = self.get_run(run_id)
            if not run:
                continue

            runs.append(run)

            # Collect metrics
            for metric in run.get('data', {}).get('metrics', []):
                key = metric['key']
                if key not in all_metrics:
                    all_metrics[key] = {}
                all_metrics[key][run_id] = metric['value']

            # Collect params
            for param in run.get('data', {}).get('params', []):
                key = param['key']
                if key not in all_params:
                    all_params[key] = {}
                all_params[key][run_id] = param['value']

        return {
            'runs': runs,
            'metrics': all_metrics,
            'params': all_params
        }

    def get_best_run(
        self,
        experiment_name: str,
        metric: str = 'test_recall_at_100',
        ascending: bool = False
    ) -> Optional[Dict]:
        """Get the best run by a specific metric."""
        order = 'ASC' if ascending else 'DESC'
        runs = self.list_runs(
            experiment_name,
            max_results=1,
            order_by=f'metrics.{metric} {order}'
        )
        return runs[0] if runs else None
```

### 3.2 Add API Endpoints

**File**: `/Users/dkulish/Projects/b2b_recs/ml_platform/experiments/api.py`

Add new endpoints:

```python
from .mlflow_service import MLflowService

@api_view(['GET'])
@require_model_access
def get_training_history(request, quick_test_id):
    """
    Get per-epoch training history from MLflow.

    Returns:
        {
            'available': true,
            'metrics': {
                'loss': [{'step': 0, 'value': 0.5}, ...],
                'val_loss': [...],
                ...
            }
        }
    """
    quick_test = get_object_or_404(QuickTest, pk=quick_test_id)

    if not quick_test.mlflow_run_id:
        return Response({
            'available': False,
            'message': 'No MLflow run associated with this experiment'
        })

    mlflow_service = MLflowService(quick_test.feature_config.dataset.model_endpoint)
    metrics = mlflow_service.get_run_metrics(quick_test.mlflow_run_id)

    return Response({
        'available': True,
        'metrics': metrics
    })


@api_view(['POST'])
@require_model_access
def compare_experiments(request):
    """
    Compare multiple experiments side-by-side.

    Request body:
        {'quick_test_ids': [1, 2, 3]}

    Returns comparison data for UI table/charts.
    """
    quick_test_ids = request.data.get('quick_test_ids', [])

    if len(quick_test_ids) < 2:
        return Response({'error': 'At least 2 experiments required'}, status=400)

    quick_tests = QuickTest.objects.filter(pk__in=quick_test_ids)
    run_ids = [qt.mlflow_run_id for qt in quick_tests if qt.mlflow_run_id]

    if len(run_ids) < 2:
        return Response({'error': 'Not enough experiments with MLflow data'}, status=400)

    mlflow_service = MLflowService()
    comparison = mlflow_service.compare_runs(run_ids)

    # Enrich with QuickTest metadata
    comparison['quick_tests'] = [
        {
            'id': qt.id,
            'experiment_number': qt.experiment_number,
            'feature_config': qt.feature_config.name,
            'model_config': qt.model_config.name if qt.model_config else None,
            'dataset': qt.feature_config.dataset.name,
            'mlflow_run_id': qt.mlflow_run_id,
        }
        for qt in quick_tests
    ]

    return Response(comparison)


@api_view(['GET'])
@require_model_access
def get_experiment_leaderboard(request, model_id):
    """
    Get leaderboard of experiments sorted by metric.

    Query params:
        metric: Metric to sort by (default: test_recall_at_100)
        limit: Max results (default: 20)
    """
    model_endpoint = get_object_or_404(ModelEndpoint, pk=model_id)
    metric = request.query_params.get('metric', 'test_recall_at_100')
    limit = int(request.query_params.get('limit', 20))

    mlflow_service = MLflowService(model_endpoint)
    runs = mlflow_service.list_runs(
        experiment_name=model_endpoint.name,
        max_results=limit,
        order_by=f'metrics.{metric} DESC'
    )

    # Map run_ids back to QuickTests
    run_id_to_run = {r['info']['run_id']: r for r in runs}
    quick_tests = QuickTest.objects.filter(
        mlflow_run_id__in=run_id_to_run.keys()
    ).select_related('feature_config', 'model_config', 'feature_config__dataset')

    leaderboard = []
    for qt in quick_tests:
        run = run_id_to_run.get(qt.mlflow_run_id, {})
        metrics = {m['key']: m['value'] for m in run.get('data', {}).get('metrics', [])}

        leaderboard.append({
            'rank': len(leaderboard) + 1,
            'experiment_number': qt.experiment_number,
            'quick_test_id': qt.id,
            'feature_config': qt.feature_config.name,
            'model_config': qt.model_config.name if qt.model_config else None,
            'dataset': qt.feature_config.dataset.name,
            'metrics': metrics,
            'created_at': qt.created_at.isoformat(),
        })

    # Sort by the requested metric
    leaderboard.sort(
        key=lambda x: x['metrics'].get(metric, 0),
        reverse=True
    )

    return Response({'leaderboard': leaderboard})
```

### 3.3 Update URLs

**File**: `/Users/dkulish/Projects/b2b_recs/ml_platform/experiments/urls.py`

```python
urlpatterns = [
    # ... existing URLs ...

    # MLflow integration
    path('api/quick-tests/<int:quick_test_id>/training-history/',
         api.get_training_history, name='api_quick_test_training_history'),
    path('api/experiments/compare/',
         api.compare_experiments, name='api_experiments_compare'),
    path('api/models/<int:model_id>/experiments/leaderboard/',
         api.get_experiment_leaderboard, name='api_experiments_leaderboard'),
]
```

### 3.4 Update Settings

**File**: `/Users/dkulish/Projects/b2b_recs/config/settings.py`

```python
# MLflow Configuration
MLFLOW_TRACKING_URI = os.environ.get(
    'MLFLOW_TRACKING_URI',
    'https://mlflow-server-xxxxx.europe-central2.run.app'
)
```

---

## Phase 4: Experiment Comparison UI

### Objective
Build comparison table with sorting, filtering, and selection for detailed comparison.

### Files to Modify

| File | Changes |
|------|---------|
| `templates/ml_platform/model_experiments.html` | Add comparison table section |
| `static/js/experiments.js` | CREATE - Comparison logic |

### 4.1 Comparison Table UI

Add to `model_experiments.html` after existing experiment cards:

```html
<!-- Experiment Comparison Section -->
<div class="chapter-section" id="comparison-section">
    <div class="chapter-header">
        <div class="chapter-icon comparison">
            <i class="fas fa-balance-scale"></i>
        </div>
        <div>
            <h2 class="chapter-title">Compare Experiments</h2>
            <p class="chapter-subtitle">Select experiments to compare side-by-side</p>
        </div>
    </div>

    <!-- Selection Controls -->
    <div class="comparison-controls">
        <button class="btn btn-primary" id="compare-selected-btn" disabled>
            Compare Selected (0)
        </button>
        <button class="btn btn-secondary" id="clear-selection-btn">
            Clear Selection
        </button>
    </div>

    <!-- Comparison Table -->
    <div class="comparison-table-wrapper" id="comparison-table-wrapper" style="display: none;">
        <table class="comparison-table" id="comparison-table">
            <thead>
                <tr>
                    <th class="sticky-col">Metric</th>
                    <!-- Dynamic columns for each selected experiment -->
                </tr>
            </thead>
            <tbody>
                <!-- Rows for each metric -->
            </tbody>
        </table>
    </div>

    <!-- Leaderboard -->
    <div class="leaderboard-section">
        <h3>Leaderboard</h3>
        <div class="leaderboard-controls">
            <label>Sort by:</label>
            <select id="leaderboard-metric">
                <option value="test_recall_at_100">Recall@100</option>
                <option value="test_recall_at_50">Recall@50</option>
                <option value="test_recall_at_10">Recall@10</option>
                <option value="final_loss">Loss</option>
            </select>
        </div>
        <div id="leaderboard-container"></div>
    </div>
</div>
```

### 4.2 Comparison JavaScript

```javascript
// experiments.js

class ExperimentComparison {
    constructor() {
        this.selectedExperiments = new Set();
        this.bindEvents();
    }

    bindEvents() {
        // Checkbox selection on experiment cards
        document.querySelectorAll('.exp-card-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => this.toggleSelection(e));
        });

        document.getElementById('compare-selected-btn').addEventListener('click',
            () => this.compareSelected());
        document.getElementById('clear-selection-btn').addEventListener('click',
            () => this.clearSelection());
        document.getElementById('leaderboard-metric').addEventListener('change',
            () => this.loadLeaderboard());
    }

    toggleSelection(event) {
        const id = event.target.dataset.quickTestId;
        if (event.target.checked) {
            this.selectedExperiments.add(id);
        } else {
            this.selectedExperiments.delete(id);
        }
        this.updateCompareButton();
    }

    updateCompareButton() {
        const btn = document.getElementById('compare-selected-btn');
        const count = this.selectedExperiments.size;
        btn.textContent = `Compare Selected (${count})`;
        btn.disabled = count < 2;
    }

    async compareSelected() {
        const ids = Array.from(this.selectedExperiments);

        try {
            const response = await fetch('/api/experiments/compare/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ quick_test_ids: ids.map(Number) })
            });

            const data = await response.json();
            this.renderComparisonTable(data);
        } catch (error) {
            console.error('Comparison failed:', error);
        }
    }

    renderComparisonTable(data) {
        const wrapper = document.getElementById('comparison-table-wrapper');
        const table = document.getElementById('comparison-table');

        // Build header
        const headerRow = table.querySelector('thead tr');
        headerRow.innerHTML = '<th class="sticky-col">Metric</th>';
        data.quick_tests.forEach(qt => {
            headerRow.innerHTML += `
                <th>
                    <div class="exp-col-header">
                        <span class="exp-num">Exp #${qt.experiment_number}</span>
                        <span class="exp-config">${qt.feature_config}</span>
                    </div>
                </th>
            `;
        });

        // Build body
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';

        // Key metrics first
        const keyMetrics = [
            'test_recall_at_100', 'test_recall_at_50', 'test_recall_at_10',
            'final_loss', 'final_val_loss'
        ];

        keyMetrics.forEach(metric => {
            if (data.metrics[metric]) {
                const row = this.createMetricRow(metric, data.metrics[metric], data.quick_tests);
                tbody.appendChild(row);
            }
        });

        // Parameters
        const paramSection = document.createElement('tr');
        paramSection.innerHTML = '<td colspan="100" class="section-divider">Parameters</td>';
        tbody.appendChild(paramSection);

        Object.keys(data.params).forEach(param => {
            const row = this.createParamRow(param, data.params[param], data.quick_tests);
            tbody.appendChild(row);
        });

        wrapper.style.display = 'block';
    }

    createMetricRow(metric, values, quickTests) {
        const row = document.createElement('tr');

        // Find best value
        const numericValues = Object.values(values).map(Number);
        const isBetterHigher = !metric.includes('loss');
        const bestValue = isBetterHigher ? Math.max(...numericValues) : Math.min(...numericValues);

        row.innerHTML = `<td class="sticky-col metric-name">${this.formatMetricName(metric)}</td>`;

        quickTests.forEach(qt => {
            const val = values[qt.mlflow_run_id];
            const isBest = Number(val) === bestValue;
            row.innerHTML += `
                <td class="${isBest ? 'best-value' : ''}">
                    ${val ? Number(val).toFixed(4) : '-'}
                    ${isBest ? '<span class="best-badge">Best</span>' : ''}
                </td>
            `;
        });

        return row;
    }

    formatMetricName(metric) {
        return metric
            .replace('test_', '')
            .replace('final_', '')
            .replace(/_/g, ' ')
            .replace(/\b\w/g, l => l.toUpperCase());
    }

    async loadLeaderboard() {
        const metric = document.getElementById('leaderboard-metric').value;
        const modelId = window.MODEL_ID;  // Set in template

        try {
            const response = await fetch(
                `/api/models/${modelId}/experiments/leaderboard/?metric=${metric}`
            );
            const data = await response.json();
            this.renderLeaderboard(data.leaderboard);
        } catch (error) {
            console.error('Leaderboard load failed:', error);
        }
    }

    renderLeaderboard(leaderboard) {
        const container = document.getElementById('leaderboard-container');

        container.innerHTML = leaderboard.map((entry, i) => `
            <div class="leaderboard-entry ${i < 3 ? 'top-3' : ''}">
                <span class="rank">#${entry.rank}</span>
                <span class="exp-info">
                    Exp #${entry.experiment_number} - ${entry.feature_config}
                </span>
                <span class="metric-value">
                    ${Object.entries(entry.metrics).map(([k, v]) =>
                        `${k}: ${Number(v).toFixed(4)}`
                    ).join(' | ')}
                </span>
            </div>
        `).join('');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    new ExperimentComparison();
});
```

---

## Phase 5: Per-Epoch Training Charts

### Objective
Display training curves (loss, metrics over epochs) using Chart.js.

### 5.1 Add Chart.js to Template

```html
<!-- In model_experiments.html -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

<!-- Training History Section in View Modal -->
<div class="tab-pane" id="training-history-tab">
    <div class="training-charts-container">
        <div class="chart-wrapper">
            <h4>Loss</h4>
            <canvas id="loss-chart"></canvas>
        </div>
        <div class="chart-wrapper">
            <h4>Validation Metrics</h4>
            <canvas id="metrics-chart"></canvas>
        </div>
    </div>
    <div id="training-history-loading">Loading training history...</div>
    <div id="training-history-unavailable" style="display: none;">
        Training history not available for this experiment.
    </div>
</div>
```

### 5.2 Chart Rendering JavaScript

```javascript
async function loadTrainingHistory(quickTestId) {
    try {
        const response = await fetch(`/api/quick-tests/${quickTestId}/training-history/`);
        const data = await response.json();

        if (!data.available) {
            document.getElementById('training-history-loading').style.display = 'none';
            document.getElementById('training-history-unavailable').style.display = 'block';
            return;
        }

        renderLossChart(data.metrics);
        renderMetricsChart(data.metrics);

        document.getElementById('training-history-loading').style.display = 'none';
    } catch (error) {
        console.error('Failed to load training history:', error);
    }
}

function renderLossChart(metrics) {
    const ctx = document.getElementById('loss-chart').getContext('2d');

    const lossData = metrics['loss'] || [];
    const valLossData = metrics['val_loss'] || [];

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: lossData.map(p => `Epoch ${p.step + 1}`),
            datasets: [
                {
                    label: 'Training Loss',
                    data: lossData.map(p => p.value),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'Validation Loss',
                    data: valLossData.map(p => p.value),
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top' },
                title: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    title: { display: true, text: 'Loss' }
                }
            }
        }
    });
}

function renderMetricsChart(metrics) {
    const ctx = document.getElementById('metrics-chart').getContext('2d');

    // Find recall metrics
    const recallMetrics = Object.keys(metrics).filter(k => k.includes('recall') || k.includes('accuracy'));

    const datasets = recallMetrics.map((key, i) => {
        const colors = ['#10b981', '#8b5cf6', '#ec4899', '#06b6d4'];
        return {
            label: key.replace('factorized_top_k/', '').replace(/_/g, ' '),
            data: metrics[key].map(p => p.value),
            borderColor: colors[i % colors.length],
            tension: 0.3,
            fill: false
        };
    });

    if (datasets.length === 0) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: metrics[recallMetrics[0]].map(p => `Epoch ${p.step + 1}`),
            datasets
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top' }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 1,
                    title: { display: true, text: 'Accuracy' }
                }
            }
        }
    });
}
```

---

## Phase 6: Configuration Heatmaps (Optional)

### Objective
Visualize which feature/model config combinations produce best results.

This phase creates a heatmap showing average metrics across different configuration combinations.

### 6.1 API Endpoint for Aggregated Data

```python
@api_view(['GET'])
@require_model_access
def get_config_heatmap_data(request, model_id):
    """
    Get aggregated metrics for feature config × model config combinations.
    """
    model_endpoint = get_object_or_404(ModelEndpoint, pk=model_id)
    metric = request.query_params.get('metric', 'recall_at_100')

    # Get completed quick tests
    quick_tests = QuickTest.objects.filter(
        feature_config__dataset__model_endpoint=model_endpoint,
        status=QuickTest.STATUS_COMPLETED
    ).select_related('feature_config', 'model_config')

    # Aggregate by feature_config × model_config
    aggregations = {}
    for qt in quick_tests:
        fc_name = qt.feature_config.name
        mc_name = qt.model_config.name if qt.model_config else 'Default'

        key = (fc_name, mc_name)
        if key not in aggregations:
            aggregations[key] = {'values': [], 'count': 0}

        metric_value = getattr(qt, metric, None)
        if metric_value is not None:
            aggregations[key]['values'].append(metric_value)
            aggregations[key]['count'] += 1

    # Calculate averages
    feature_configs = sorted(set(k[0] for k in aggregations.keys()))
    model_configs = sorted(set(k[1] for k in aggregations.keys()))

    matrix = []
    for fc in feature_configs:
        row = []
        for mc in model_configs:
            key = (fc, mc)
            if key in aggregations and aggregations[key]['values']:
                avg = sum(aggregations[key]['values']) / len(aggregations[key]['values'])
                row.append({'value': avg, 'count': aggregations[key]['count']})
            else:
                row.append(None)
        matrix.append(row)

    return Response({
        'feature_configs': feature_configs,
        'model_configs': model_configs,
        'matrix': matrix,
        'metric': metric
    })
```

### 6.2 Heatmap UI Component

```html
<div class="heatmap-container">
    <h3>Configuration Impact Analysis</h3>
    <div class="heatmap-controls">
        <label>Metric:</label>
        <select id="heatmap-metric">
            <option value="recall_at_100">Recall@100</option>
            <option value="recall_at_50">Recall@50</option>
            <option value="loss">Loss</option>
        </select>
    </div>
    <div id="heatmap-chart"></div>
</div>
```

```javascript
function renderHeatmap(data) {
    const container = document.getElementById('heatmap-chart');

    // Create table-based heatmap
    let html = '<table class="heatmap-table"><thead><tr><th></th>';
    data.model_configs.forEach(mc => {
        html += `<th>${mc}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Find min/max for color scaling
    const allValues = data.matrix.flat().filter(v => v).map(v => v.value);
    const minVal = Math.min(...allValues);
    const maxVal = Math.max(...allValues);

    data.feature_configs.forEach((fc, i) => {
        html += `<tr><td class="row-header">${fc}</td>`;
        data.matrix[i].forEach(cell => {
            if (cell) {
                const normalized = (cell.value - minVal) / (maxVal - minVal);
                const color = getHeatmapColor(normalized);
                html += `<td style="background-color: ${color}" title="${cell.value.toFixed(4)} (n=${cell.count})">
                    ${cell.value.toFixed(3)}
                </td>`;
            } else {
                html += '<td class="no-data">-</td>';
            }
        });
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

function getHeatmapColor(normalized) {
    // Green gradient: darker = better
    const r = Math.round(255 - (normalized * 200));
    const g = Math.round(255 - (normalized * 50));
    const b = Math.round(255 - (normalized * 200));
    return `rgb(${r}, ${g}, ${b})`;
}
```

---

## Critical Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `mlflow_server/Dockerfile` | CREATE | MLflow server container |
| `mlflow_server/cloudbuild.yaml` | CREATE | Deployment pipeline |
| `mlflow_server/entrypoint.sh` | CREATE | Server startup |
| `ml_platform/configs/services.py` | MODIFY | Add MLflow to trainer code generation |
| `ml_platform/experiments/mlflow_service.py` | CREATE | MLflow REST API client |
| `ml_platform/experiments/services.py` | MODIFY | Pass MLflow config, extract run_id |
| `ml_platform/experiments/api.py` | MODIFY | Add comparison endpoints |
| `ml_platform/experiments/urls.py` | MODIFY | Route new endpoints |
| `ml_platform/models.py` | MODIFY | Add mlflow_run_id to QuickTest |
| `templates/ml_platform/model_experiments.html` | MODIFY | Comparison UI, charts |
| `static/js/experiments.js` | CREATE | Comparison & chart logic |
| `config/settings.py` | MODIFY | MLflow URI config |

---

## Testing Checklist

- [ ] MLflow server deploys and is accessible
- [ ] Django can authenticate to MLflow via identity token
- [ ] Trainer logs params and metrics to MLflow
- [ ] mlflow_run_id is written to GCS and read by Django
- [ ] Training history endpoint returns per-epoch data
- [ ] Comparison table renders with multiple experiments
- [ ] Charts display loss and metric curves
- [ ] Leaderboard sorts by selected metric

---

## Cost Estimate

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| MLflow Cloud Run (scale to 0) | ~$5-10 | 5-10s cold start after idle |
| Cloud SQL (shared with Django) | $0 | Use existing instance |
| GCS artifacts | ~$1-5 | Depends on experiment volume |
| **Total per client** | **~$10-15** |

---

## Configuration Decisions

Based on requirements discussion:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Database** | Shared Cloud SQL | No extra cost, sufficient for experiment tracking |
| **MLflow Scaling** | min-instances=0 | Cost savings; cold start acceptable for analytics UI |
| **Implementation Scope** | All 6 phases | Comprehensive plan for future reference |

---

## Appendix A: MLflow REST API Reference

### Useful Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/2.0/mlflow/experiments/get-by-name` | GET | Get experiment by name |
| `/api/2.0/mlflow/runs/search` | POST | Search runs with filters |
| `/api/2.0/mlflow/runs/get` | GET | Get single run details |
| `/api/2.0/mlflow/metrics/get-history` | GET | Get metric history for a run |
| `/api/2.0/mlflow/runs/log-metric` | POST | Log a metric |
| `/api/2.0/mlflow/runs/log-param` | POST | Log a parameter |
| `/api/2.0/mlflow/runs/set-tag` | POST | Set a tag on a run |

### Example: Search Runs by Metric

```python
response = mlflow_client.search_runs(
    experiment_ids=["1"],
    filter_string="metrics.recall_at_100 > 0.4",
    order_by=["metrics.recall_at_100 DESC"],
    max_results=10
)
```

### Example: Get Metric History

```python
history = mlflow_client.get_metric_history(run_id, "loss")
# Returns: [Metric(key='loss', value=0.5, timestamp=..., step=0), ...]
```

---

## Appendix B: Generated Trainer Code Template

The `TrainerModuleGenerator` will produce code following this structure:

```python
"""
Auto-generated TFX Trainer Module with MLflow Integration
Generated: {timestamp}
FeatureConfig: {feature_config_name} (ID: {feature_config_id})
ModelConfig: {model_config_name} (ID: {model_config_id})
"""

import os
import json
import tensorflow as tf
import tensorflow_transform as tft
import tensorflow_recommenders as tfrs
from tfx import v1 as tfx

# MLflow imports
import mlflow
import mlflow.tensorflow

# =============================================================================
# CONSTANTS
# =============================================================================

EMBEDDING_DIM = {embedding_dim}
LEARNING_RATE = {learning_rate}
BATCH_SIZE = {batch_size}
EPOCHS = {epochs}
OPTIMIZER = '{optimizer}'

# MLflow Configuration
MLFLOW_TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', '')
MLFLOW_EXPERIMENT_NAME = '{experiment_name}'
MLFLOW_RUN_NAME = os.environ.get('MLFLOW_RUN_NAME', 'quick-test')

# =============================================================================
# MODELS (generated based on FeatureConfig + ModelConfig)
# =============================================================================

class BuyerModel(tf.keras.Model):
    """Query tower for buyer/user representation."""
    # ... generated based on buyer_model_features ...

class ProductModel(tf.keras.Model):
    """Candidate tower for product representation."""
    # ... generated based on product_model_features ...

class RetrievalModel(tfrs.Model):
    """Two-tower retrieval model."""
    # ... combines BuyerModel + ProductModel ...

# =============================================================================
# MLFLOW CALLBACK
# =============================================================================

class MLflowCallback(tf.keras.callbacks.Callback):
    """Log metrics to MLflow after each epoch."""

    def on_epoch_end(self, epoch, logs=None):
        if logs and mlflow.active_run():
            for metric_name, value in logs.items():
                mlflow.log_metric(metric_name, float(value), step=epoch)

# =============================================================================
# RUN FUNCTION (TFX Entry Point)
# =============================================================================

def run_fn(fn_args):
    """TFX Trainer entry point with MLflow tracking."""

    # Load transform output
    tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)

    # Get custom config
    custom_config = fn_args.custom_config or {}
    epochs = custom_config.get('epochs', EPOCHS)
    batch_size = custom_config.get('batch_size', BATCH_SIZE)
    learning_rate = custom_config.get('learning_rate', LEARNING_RATE)
    gcs_output_path = custom_config.get('gcs_output_path', '')

    # Build datasets
    train_dataset = _input_fn(fn_args.train_files, ...)
    eval_dataset = _input_fn(fn_args.eval_files, ...)

    # Initialize MLflow
    if MLFLOW_TRACKING_URI:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    # Start MLflow run
    with mlflow.start_run(run_name=MLFLOW_RUN_NAME) as run:

        # Log parameters
        mlflow.log_params({
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': learning_rate,
            'optimizer': OPTIMIZER,
            'embedding_dim': EMBEDDING_DIM,
            'feature_config_id': {feature_config_id},
            'model_config_id': {model_config_id},
        })

        # Log tags for filtering
        mlflow.set_tags({
            'feature_config_name': '{feature_config_name}',
            'model_config_name': '{model_config_name}',
            'dataset_name': '{dataset_name}',
        })

        # Build and compile model
        model = RetrievalModel(...)
        model.compile(optimizer=...)

        # Train with MLflow callback
        history = model.fit(
            train_dataset,
            validation_data=eval_dataset,
            epochs=epochs,
            callbacks=[MLflowCallback()]
        )

        # Log final metrics
        for metric_name, values in history.history.items():
            mlflow.log_metric(f'final_{metric_name}', float(values[-1]))

        # Evaluate on test set (if strict_time split)
        if test_dataset:
            test_results = model.evaluate(test_dataset, return_dict=True)
            for name, value in test_results.items():
                mlflow.log_metric(f'test_{name}', float(value))

        # Write MLflow run_id to GCS for Django
        _write_mlflow_info(gcs_output_path, run.info.run_id)

        # Save model (TFX requirement)
        serving_model = ServingModel(...)
        tf.saved_model.save(serving_model, fn_args.serving_model_dir, ...)


def _write_mlflow_info(gcs_output_path: str, run_id: str):
    """Write MLflow run ID to GCS for Django retrieval."""
    if not gcs_output_path or not gcs_output_path.startswith('gs://'):
        return

    from google.cloud import storage

    path = gcs_output_path[5:]  # Remove 'gs://'
    bucket_name = path.split('/')[0]
    blob_path = '/'.join(path.split('/')[1:]) + '/mlflow_info.json'

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(json.dumps({
        'run_id': run_id,
        'experiment_name': MLFLOW_EXPERIMENT_NAME,
    }))
```

---

## Appendix C: Django Template Snippets

### Experiment Card with Selection Checkbox

```html
<div class="exp-card-new" data-quick-test-id="{{ qt.id }}">
    <div class="exp-card-columns">
        <!-- Column 0: Selection checkbox -->
        <div class="exp-card-col-select">
            <input type="checkbox"
                   class="exp-card-checkbox"
                   data-quick-test-id="{{ qt.id }}"
                   {% if not qt.mlflow_run_id %}disabled title="No MLflow data"{% endif %}>
        </div>

        <!-- Column 1: Experiment Info -->
        <div class="exp-card-col-info">
            <div class="exp-card-status {{ qt.status }}">
                <!-- Status icon -->
            </div>
            <div class="exp-card-info-text">
                <div class="exp-card-name">
                    Exp #{{ qt.experiment_number }}
                    {% if qt.experiment_name %}
                    <span class="exp-card-custom-name">{{ qt.experiment_name }}</span>
                    {% endif %}
                </div>
                <div class="exp-card-configs">
                    {{ qt.feature_config.name }} + {{ qt.model_config.name }}
                </div>
            </div>
        </div>

        <!-- Column 2: Metrics (if completed) -->
        {% if qt.status == 'completed' and qt.recall_at_100 %}
        <div class="exp-card-col-metrics">
            <div class="metric-chip primary">
                <span class="metric-value">{{ qt.recall_at_100|floatformat:3 }}</span>
                <span class="metric-label">R@100</span>
            </div>
            <div class="metric-chip">
                <span class="metric-value">{{ qt.recall_at_50|floatformat:3 }}</span>
                <span class="metric-label">R@50</span>
            </div>
        </div>
        {% endif %}

        <!-- Column 3: Actions -->
        <div class="exp-card-col-actions">
            <button class="btn-view" onclick="openExperimentModal({{ qt.id }})">
                View
            </button>
        </div>
    </div>
</div>
```

### Training History Tab in Modal

```html
<div class="tab-content" id="training-history-content">
    <div class="training-history-header">
        <h3>Training Progress</h3>
        <div class="chart-controls">
            <button class="chart-btn active" data-chart="loss">Loss</button>
            <button class="chart-btn" data-chart="metrics">Metrics</button>
        </div>
    </div>

    <div class="chart-container">
        <canvas id="training-chart" height="300"></canvas>
    </div>

    <div class="epoch-table-container">
        <table class="epoch-table">
            <thead>
                <tr>
                    <th>Epoch</th>
                    <th>Loss</th>
                    <th>Val Loss</th>
                    <th>R@100</th>
                </tr>
            </thead>
            <tbody id="epoch-table-body">
                <!-- Populated by JavaScript -->
            </tbody>
        </table>
    </div>

    <div id="training-history-loading" class="loading-state">
        <div class="spinner"></div>
        <p>Loading training history...</p>
    </div>

    <div id="training-history-unavailable" class="empty-state" style="display: none;">
        <i class="fas fa-chart-line"></i>
        <p>Training history not available for this experiment.</p>
        <small>MLflow integration may not have been active when this experiment ran.</small>
    </div>
</div>
```

---

## Appendix D: Error Handling Patterns

### MLflow Service Error Handling

```python
class MLflowService:

    def _api_call(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make authenticated API call with comprehensive error handling."""
        url = f"{self.tracking_uri}/api/2.0/mlflow{endpoint}"

        try:
            token = self._get_auth_token()
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = f'Bearer {token}'

            if method == 'GET':
                response = requests.get(url, params=data, headers=headers, timeout=30)
            else:
                response = requests.post(url, json=data, headers=headers, timeout=30)

            if response.ok:
                return response.json()

            # Handle specific error codes
            if response.status_code == 401:
                logger.error("MLflow authentication failed - check service account permissions")
            elif response.status_code == 404:
                logger.warning(f"MLflow resource not found: {endpoint}")
            elif response.status_code == 503:
                logger.warning("MLflow server unavailable (possibly cold starting)")
            else:
                logger.warning(f"MLflow API error {response.status_code}: {response.text}")

            return None

        except requests.exceptions.Timeout:
            logger.warning(f"MLflow request timed out: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"MLflow connection failed - server may be starting")
            return None
        except Exception as e:
            logger.exception(f"MLflow API call failed: {e}")
            return None
```

### Graceful Degradation in UI

```javascript
async function loadTrainingHistory(quickTestId) {
    const loadingEl = document.getElementById('training-history-loading');
    const unavailableEl = document.getElementById('training-history-unavailable');
    const contentEl = document.getElementById('training-history-content');

    loadingEl.style.display = 'block';
    unavailableEl.style.display = 'none';

    try {
        const response = await fetch(`/api/quick-tests/${quickTestId}/training-history/`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (!data.available) {
            loadingEl.style.display = 'none';
            unavailableEl.style.display = 'block';
            return;
        }

        renderTrainingCharts(data.metrics);
        loadingEl.style.display = 'none';

    } catch (error) {
        console.error('Failed to load training history:', error);
        loadingEl.style.display = 'none';
        unavailableEl.style.display = 'block';
        unavailableEl.querySelector('p').textContent =
            'Unable to load training history. MLflow server may be unavailable.';
    }
}
```

---

## Appendix E: Database Migration

### Migration for QuickTest MLflow Fields

```python
# ml_platform/migrations/XXXX_add_mlflow_fields.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', 'previous_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='quicktest',
            name='mlflow_run_id',
            field=models.CharField(
                blank=True,
                help_text='MLflow run ID for this experiment',
                max_length=255
            ),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='mlflow_experiment_name',
            field=models.CharField(
                blank=True,
                help_text='MLflow experiment name',
                max_length=255
            ),
        ),
        migrations.AddIndex(
            model_name='quicktest',
            index=models.Index(
                fields=['mlflow_run_id'],
                name='ml_platform_mlflow_run_idx'
            ),
        ),
    ]
```

### Cloud SQL Database Setup

```sql
-- Run on existing Cloud SQL instance
CREATE DATABASE mlflow;

CREATE USER mlflow_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow_user;

-- MLflow will auto-create tables on first startup
```
