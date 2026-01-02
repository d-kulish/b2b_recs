# MLflow Integration Documentation

## Document Purpose

This document provides a **complete reference** of the MLflow integration in the B2B Recommendations system. It captures all implementation details, data flows, and configuration so that if this approach is ever needed again, it can be reconstructed without reinventing the architecture.

**Last Updated**: 2026-01-02

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Components](#components)
3. [Data Flow](#data-flow)
4. [Implementation Details](#implementation-details)
5. [Configuration Reference](#configuration-reference)
6. [API Reference](#api-reference)
7. [Database Schema](#database-schema)
8. [Metrics Catalog](#metrics-catalog)
9. [Authentication](#authentication)
10. [Deployment](#deployment)
11. [File Reference](#file-reference)

---

## Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRAINING (Vertex AI)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   trainer.py (generated from ml_platform/configs/services.py)                │
│       │                                                                      │
│       ├── MLflowRestClient                                                   │
│       │       ├── set_experiment()   ──────┐                                 │
│       │       ├── start_run()        ──────┤                                 │
│       │       ├── log_params()       ──────┤                                 │
│       │       └── end_run()          ──────┤                                 │
│       │                                    │                                 │
│       ├── MLflowCallback.on_epoch_end()    │                                 │
│       │       └── log_metric()       ──────┤                                 │
│       │                                    │   REST API calls                │
│       ├── WeightNormCallback               │   (per epoch)                   │
│       │       └── log_metric()       ──────┤                                 │
│       │                                    │                                 │
│       ├── WeightStatsCallback              │                                 │
│       │       ├── log_metric()       ──────┤                                 │
│       │       └── log_param()        ──────┤   (histogram bin edges)         │
│       │                                    │                                 │
│       └── GradientStatsCallback            │                                 │
│               ├── log_metric()       ──────┤                                 │
│               └── log_param()        ──────┘                                 │
│                                                                              │
│   At training completion:                                                    │
│       └── _write_mlflow_info() ─────────────────────► GCS: mlflow_info.json  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MLFLOW SERVER (Cloud Run)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   mlflow_server/                                                             │
│       ├── Dockerfile         - Python 3.10 with mlflow==2.9.2                │
│       ├── entrypoint.sh      - Server startup script                         │
│       └── requirements.txt   - mlflow, psycopg2, google-cloud-storage        │
│                                                                              │
│   URL: https://mlflow-server-{project}.europe-central2.run.app               │
│                                                                              │
│   REST API endpoints:                                                        │
│       POST /api/2.0/mlflow/experiments/get-by-name                           │
│       POST /api/2.0/mlflow/experiments/create                                │
│       POST /api/2.0/mlflow/runs/create                                       │
│       POST /api/2.0/mlflow/runs/log-metric                                   │
│       POST /api/2.0/mlflow/runs/log-parameter                                │
│       POST /api/2.0/mlflow/runs/log-batch                                    │
│       POST /api/2.0/mlflow/runs/update                                       │
│       GET  /api/2.0/mlflow/runs/get                                          │
│       GET  /api/2.0/mlflow/metrics/get-history                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MLFLOW DATABASE (Cloud SQL)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   PostgreSQL instance: mlflow-db (europe-central2)                           │
│                                                                              │
│   Tables:                                                                    │
│       experiments     - Experiment metadata                                  │
│       runs            - Individual training runs                             │
│       metrics         - Time-series metric values (millions of rows)         │
│       params          - Run parameters (hyperparameters)                     │
│       tags            - Run tags and metadata                                │
│       latest_metrics  - Most recent metric values per run                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                                      │
                                                      │ (REST API queries)
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DJANGO APP (Cloud Run)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ml_platform/experiments/                                                   │
│       ├── mlflow_service.py          - MLflow REST API client                │
│       ├── training_cache_service.py  - Caching layer (MLflow → Django DB)    │
│       ├── services.py                - Reads mlflow_info.json from GCS       │
│       └── api.py                     - API endpoints for UI                  │
│                                                                              │
│   QuickTest model:                                                           │
│       ├── mlflow_run_id              - Links to MLflow run                   │
│       ├── mlflow_experiment_name     - Experiment grouping                   │
│       └── training_history_json      - Cached training data                  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Purpose & Design Goals

MLflow was integrated to provide:

1. **Experiment Tracking**: Track multiple training runs with different hyperparameters
2. **Metrics Storage**: Store per-epoch loss curves, recall metrics, weight/gradient statistics
3. **Experiment Comparison**: Compare runs side-by-side to find best configurations
4. **Standard Interface**: Use MLflow's standard REST API for logging/querying

### Why This Architecture Was Chosen

| Decision | Rationale |
|----------|-----------|
| Cloud Run for MLflow server | Auto-scaling, serverless, integrates with Cloud SQL |
| Cloud SQL PostgreSQL | Reliable, managed, supports MLflow's backend requirements |
| REST API (not Python SDK) | Works from Vertex AI training jobs without dependency conflicts |
| Django caching layer | Eliminates repeated MLflow queries, sub-second UI response |
| GCS for mlflow_info.json | Bridge between Vertex AI training and Django (no direct DB access) |

---

## Components

### 1. MLflow Server (Cloud Run)

**Location:** `mlflow_server/`

**Dockerfile:**
```dockerfile
FROM python:3.10-slim

# Install dependencies
RUN pip install mlflow==2.9.2 psycopg2-binary==2.9.9 google-cloud-storage==2.14.0

# Non-root user
RUN useradd -m -u 1000 mlflow
USER mlflow

# Expose port
EXPOSE 8080

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

**entrypoint.sh:**
```bash
#!/bin/bash
set -e

# Validate required environment variables
: "${MLFLOW_BACKEND_STORE_URI:?MLFLOW_BACKEND_STORE_URI is required}"
: "${MLFLOW_ARTIFACT_ROOT:?MLFLOW_ARTIFACT_ROOT is required}"

# Start MLflow server
exec mlflow server \
    --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
    --default-artifact-root "$MLFLOW_ARTIFACT_ROOT" \
    --host 0.0.0.0 \
    --port 8080 \
    --workers ${MLFLOW_WORKERS:-2} \
    --gunicorn-opts "--timeout 120"
```

**Requirements:**
- mlflow==2.9.2
- psycopg2-binary==2.9.9
- google-cloud-storage==2.14.0

---

### 2. MLflow REST Client (Trainer-side)

**Location:** `ml_platform/configs/services.py` (lines 1538-1827)

**Purpose:** Lightweight REST client for logging metrics during training (no mlflow package dependency)

```python
class MLflowRestClient:
    """
    Lightweight MLflow REST API client for training jobs.

    Uses REST API instead of mlflow package to avoid dependency conflicts
    in Vertex AI training containers.
    """

    def __init__(self, tracking_uri: str):
        self.tracking_uri = tracking_uri.rstrip('/')
        self._token = None
        self._token_expiry = 0
        self.run_id = None
        self.experiment_id = None

    def _get_identity_token(self) -> str:
        """Get GCP identity token for Cloud Run authentication."""
        # Method 1: google.oauth2.id_token
        try:
            from google.oauth2 import id_token
            from google.auth.transport.requests import Request
            return id_token.fetch_id_token(Request(), self.tracking_uri)
        except Exception:
            pass

        # Method 2: Metadata server (Vertex AI)
        try:
            import urllib.request
            url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={self.tracking_uri}"
            req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode('utf-8')
        except Exception:
            pass

        return None

    def _request(self, endpoint: str, data: dict, method: str = 'POST') -> dict:
        """Make authenticated request to MLflow API."""
        url = f"{self.tracking_uri}/api/2.0/mlflow/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        token = self._get_identity_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode('utf-8'),
                    headers=headers,
                    method=method
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    return json.loads(response.read().decode('utf-8'))
            except Exception as e:
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
                else:
                    raise

    def set_experiment(self, name: str) -> str:
        """Get or create experiment, returns experiment_id."""
        # Try to get existing
        try:
            resp = self._request('experiments/get-by-name', {'experiment_name': name})
            self.experiment_id = resp['experiment']['experiment_id']
            return self.experiment_id
        except Exception:
            pass

        # Create new
        resp = self._request('experiments/create', {'name': name})
        self.experiment_id = resp['experiment_id']
        return self.experiment_id

    def start_run(self, run_name: str = None) -> str:
        """Start a new run, returns run_id."""
        data = {'experiment_id': self.experiment_id}
        if run_name:
            data['run_name'] = run_name

        resp = self._request('runs/create', data)
        self.run_id = resp['run']['info']['run_id']
        return self.run_id

    def log_param(self, key: str, value) -> None:
        """Log a parameter."""
        self._request('runs/log-parameter', {
            'run_id': self.run_id,
            'key': key,
            'value': str(value)
        })

    def log_metric(self, key: str, value: float, step: int = None) -> None:
        """Log a metric with optional step."""
        data = {
            'run_id': self.run_id,
            'key': key,
            'value': float(value),
            'timestamp': int(time.time() * 1000)
        }
        if step is not None:
            data['step'] = step
        self._request('runs/log-metric', data)

    def end_run(self, status: str = 'FINISHED') -> None:
        """End the run."""
        self._request('runs/update', {
            'run_id': self.run_id,
            'status': status,
            'end_time': int(time.time() * 1000)
        })

    def wait_for_ready(self, timeout: int = 120) -> bool:
        """Wait for MLflow server to be ready (handles cold starts)."""
        start = time.time()
        delay = 5

        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(
                    f"{self.tracking_uri}/health",
                    headers={'Authorization': f'Bearer {self._get_identity_token()}'}
                )
                urllib.request.urlopen(req, timeout=10)
                return True
            except Exception:
                logging.info(f"MLflow not ready, waiting {delay}s...")
                time.sleep(delay)
                delay = min(delay + 5, 20)

        return False
```

---

### 3. Training Callbacks

**Location:** `ml_platform/configs/services.py` (lines 2692-2868)

#### MLflowCallback
Logs all standard Keras metrics per epoch:

```python
class MLflowCallback(tf.keras.callbacks.Callback):
    """Log all epoch metrics to MLflow."""

    def on_epoch_end(self, epoch, logs=None):
        if _mlflow_client and logs:
            for metric_name, value in logs.items():
                _mlflow_client.log_metric(metric_name, float(value), step=epoch)
```

#### WeightNormCallback
Tracks L2 norms of trainable weights:

```python
class WeightNormCallback(tf.keras.callbacks.Callback):
    """Log weight L2 norms per tower."""

    def on_epoch_end(self, epoch, logs=None):
        if not _mlflow_client:
            return

        total_norm = 0.0
        query_norm = 0.0
        candidate_norm = 0.0

        for var in self.model.trainable_variables:
            weights = var.numpy().flatten()
            norm = np.sqrt(np.sum(weights ** 2))
            total_norm += norm ** 2

            var_name = var.name.lower()
            if 'query' in var_name or 'buyer' in var_name:
                query_norm += norm ** 2
            elif 'candidate' in var_name or 'product' in var_name:
                candidate_norm += norm ** 2

        _mlflow_client.log_metric('weight_norm', np.sqrt(total_norm), step=epoch)
        _mlflow_client.log_metric('query_weight_norm', np.sqrt(query_norm), step=epoch)
        _mlflow_client.log_metric('candidate_weight_norm', np.sqrt(candidate_norm), step=epoch)
```

#### WeightStatsCallback
Tracks weight distribution statistics and histograms:

```python
class WeightStatsCallback(tf.keras.callbacks.Callback):
    """Log weight statistics and histograms per tower."""

    NUM_HISTOGRAM_BINS = 25

    def on_epoch_end(self, epoch, logs=None):
        if not _mlflow_client:
            return

        for tower in ['query', 'candidate']:
            # Collect weights for this tower
            weights = []
            for var in self.model.trainable_variables:
                var_name = var.name.lower()
                if tower == 'query' and ('query' in var_name or 'buyer' in var_name):
                    weights.append(var.numpy().flatten())
                elif tower == 'candidate' and ('candidate' in var_name or 'product' in var_name):
                    weights.append(var.numpy().flatten())

            if not weights:
                continue

            all_weights = np.concatenate(weights)

            # Summary statistics
            _mlflow_client.log_metric(f'{tower}_weights_mean', float(np.mean(all_weights)), step=epoch)
            _mlflow_client.log_metric(f'{tower}_weights_std', float(np.std(all_weights)), step=epoch)
            _mlflow_client.log_metric(f'{tower}_weights_min', float(np.min(all_weights)), step=epoch)
            _mlflow_client.log_metric(f'{tower}_weights_max', float(np.max(all_weights)), step=epoch)

            # Histogram
            counts, bin_edges = np.histogram(all_weights, bins=self.NUM_HISTOGRAM_BINS)

            # Log bin edges once (epoch 0 only)
            if epoch == 0:
                edges_str = ','.join([f'{e:.6f}' for e in bin_edges])
                _mlflow_client.log_param(f'{tower}_hist_bin_edges', edges_str)

            # Log bin counts per epoch
            for i, count in enumerate(counts):
                _mlflow_client.log_metric(f'{tower}_hist_bin_{i}', int(count), step=epoch)
```

#### GradientStatsCallback
Tracks gradient distribution statistics and histograms:

```python
class GradientStatsCallback(tf.keras.callbacks.Callback):
    """Log gradient statistics and histograms per tower."""

    NUM_HISTOGRAM_BINS = 25
    HISTOGRAM_RANGE = (-1.0, 1.0)  # Fixed range for stability

    def on_epoch_end(self, epoch, logs=None):
        if not _mlflow_client:
            return

        for tower in ['query', 'candidate']:
            grads = self.model._gradient_stats.get(tower, [])
            if not grads:
                continue

            all_grads = np.concatenate(grads)

            # Summary statistics
            _mlflow_client.log_metric(f'{tower}_grad_mean', float(np.mean(all_grads)), step=epoch)
            _mlflow_client.log_metric(f'{tower}_grad_std', float(np.std(all_grads)), step=epoch)
            _mlflow_client.log_metric(f'{tower}_grad_min', float(np.min(all_grads)), step=epoch)
            _mlflow_client.log_metric(f'{tower}_grad_max', float(np.max(all_grads)), step=epoch)
            _mlflow_client.log_metric(f'{tower}_grad_norm', float(np.sqrt(np.sum(all_grads**2))), step=epoch)

            # Histogram (fixed range)
            counts, bin_edges = np.histogram(
                all_grads,
                bins=self.NUM_HISTOGRAM_BINS,
                range=self.HISTOGRAM_RANGE
            )

            if epoch == 0:
                edges_str = ','.join([f'{e:.6f}' for e in bin_edges])
                _mlflow_client.log_param(f'{tower}_grad_hist_bin_edges', edges_str)

            for i, count in enumerate(counts):
                _mlflow_client.log_metric(f'{tower}_grad_hist_bin_{i}', int(count), step=epoch)

        # Reset accumulators for next epoch
        self.model._gradient_stats = {'query': [], 'candidate': []}
```

---

### 4. MLflow Service (Django-side)

**Location:** `ml_platform/experiments/mlflow_service.py`

**Purpose:** Query MLflow REST API to retrieve training history for UI display

```python
class MLflowService:
    """Client for querying MLflow tracking server from Django."""

    def __init__(self, tracking_uri: str = None):
        self.tracking_uri = tracking_uri or settings.MLFLOW_TRACKING_URI

    def _get_auth_token(self) -> str:
        """Get identity token for Cloud Run service-to-service auth."""
        try:
            from google.oauth2 import id_token
            from google.auth.transport.requests import Request
            return id_token.fetch_id_token(Request(), self.tracking_uri)
        except Exception:
            # Fallback to gcloud CLI (local development)
            import subprocess
            result = subprocess.run(
                ['gcloud', 'auth', 'print-identity-token', f'--audiences={self.tracking_uri}'],
                capture_output=True, text=True
            )
            return result.stdout.strip()

    def _api_call(self, endpoint: str, params: dict = None) -> dict:
        """Make authenticated GET request to MLflow API."""
        url = f"{self.tracking_uri}/api/2.0/mlflow/{endpoint}"
        headers = {'Authorization': f'Bearer {self._get_auth_token()}'}

        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_run(self, run_id: str) -> dict:
        """Get run details."""
        return self._api_call('runs/get', {'run_id': run_id})

    def get_run_metrics(self, run_id: str) -> dict:
        """Get all metrics with full history."""
        run = self.get_run(run_id)
        metrics = {}

        # Get latest values
        for metric in run.get('run', {}).get('data', {}).get('metrics', []):
            key = metric['key']
            # Fetch full history for each metric
            history = self._api_call('metrics/get-history', {
                'run_id': run_id,
                'metric_key': key
            })
            metrics[key] = [
                {'step': m['step'], 'value': m['value']}
                for m in history.get('metrics', [])
            ]

        return metrics

    def get_run_params(self, run_id: str) -> dict:
        """Get run parameters."""
        run = self.get_run(run_id)
        params = {}
        for param in run.get('run', {}).get('data', {}).get('params', []):
            params[param['key']] = param['value']
        return params

    def get_training_history(self, run_id: str) -> dict:
        """
        Get complete training history formatted for UI charts.

        Returns:
        {
            'available': True,
            'epochs': [0, 1, 2, ...],
            'loss': {
                'train': [...],
                'val': [...],
                'regularization': [...],
                'val_regularization': [...],
                'total': [...],
                'val_total': [...]
            },
            'gradient': {
                'total': [...],
                'query': [...],
                'candidate': [...]
            },
            'weight_stats': {
                'query': {
                    'mean': [...],
                    'std': [...],
                    'min': [...],
                    'max': [...],
                    'histogram': {
                        'bin_edges': [...],
                        'counts': [[...], [...], ...]  # per epoch
                    }
                },
                'candidate': { ... }
            },
            'gradient_stats': {
                'query': { ... },
                'candidate': { ... }
            },
            'final_metrics': {
                'final_loss': ...,
                'test_recall_at_100': ...,
                ...
            },
            'params': {
                'epochs': ...,
                'batch_size': ...,
                ...
            }
        }
        """
        metrics = self.get_run_metrics(run_id)
        params = self.get_run_params(run_id)

        # Determine epochs from loss metric
        epochs = []
        if 'loss' in metrics:
            epochs = sorted([m['step'] for m in metrics['loss']])

        # Extract loss curves
        loss = {}
        loss_mappings = {
            'loss': 'train',
            'val_loss': 'val',
            'regularization_loss': 'regularization',
            'val_regularization_loss': 'val_regularization',
            'total_loss': 'total',
            'val_total_loss': 'val_total'
        }
        for metric_key, display_key in loss_mappings.items():
            if metric_key in metrics:
                loss[display_key] = [m['value'] for m in sorted(metrics[metric_key], key=lambda x: x['step'])]

        # Extract gradient norms
        gradient = {}
        gradient_mappings = {
            'weight_norm': 'total',
            'query_weight_norm': 'query',
            'candidate_weight_norm': 'candidate'
        }
        for metric_key, display_key in gradient_mappings.items():
            if metric_key in metrics:
                gradient[display_key] = [m['value'] for m in sorted(metrics[metric_key], key=lambda x: x['step'])]

        # Extract weight/gradient stats and histograms
        weight_stats = self._extract_stats(metrics, params, 'weights')
        gradient_stats = self._extract_stats(metrics, params, 'grad')

        # Extract final metrics
        final_metrics = {}
        for key, values in metrics.items():
            if key.startswith('final_') or key.startswith('test_'):
                final_metrics[key] = values[-1]['value'] if values else None

        return {
            'available': True,
            'epochs': epochs,
            'loss': loss,
            'gradient': gradient,
            'weight_stats': weight_stats,
            'gradient_stats': gradient_stats,
            'final_metrics': final_metrics,
            'params': params
        }

    def _extract_stats(self, metrics: dict, params: dict, prefix: str) -> dict:
        """Extract weight or gradient statistics for both towers."""
        stats = {}

        for tower in ['query', 'candidate']:
            tower_stats = {}

            # Summary stats
            for stat in ['mean', 'std', 'min', 'max', 'norm']:
                key = f'{tower}_{prefix}_{stat}'
                if key in metrics:
                    tower_stats[stat] = [m['value'] for m in sorted(metrics[key], key=lambda x: x['step'])]

            # Histogram
            edges_key = f'{tower}_{prefix.replace("_stats", "")}_hist_bin_edges'
            if edges_key in params:
                bin_edges = [float(x) for x in params[edges_key].split(',')]

                # Get bin counts for each epoch
                counts = []
                for epoch in sorted(set(m['step'] for k, v in metrics.items() for m in v if f'{tower}_{prefix}' in k)):
                    epoch_counts = []
                    for i in range(25):  # NUM_HISTOGRAM_BINS
                        bin_key = f'{tower}_{prefix.replace("_stats", "")}_hist_bin_{i}'
                        if bin_key in metrics:
                            bin_values = {m['step']: m['value'] for m in metrics[bin_key]}
                            epoch_counts.append(bin_values.get(epoch, 0))
                    if epoch_counts:
                        counts.append(epoch_counts)

                tower_stats['histogram'] = {
                    'bin_edges': bin_edges,
                    'counts': counts
                }

            if tower_stats:
                stats[tower] = tower_stats

        return stats

    def get_histogram_data(self, run_id: str, data_type: str = 'weights', tower: str = 'query') -> dict:
        """Get histogram data for on-demand fetching (not cached)."""
        metrics = self.get_run_metrics(run_id)
        params = self.get_run_params(run_id)

        prefix = 'hist' if data_type == 'weights' else 'grad_hist'
        edges_key = f'{tower}_{prefix}_bin_edges'

        if edges_key not in params:
            return {'available': False}

        bin_edges = [float(x) for x in params[edges_key].split(',')]

        # Get bin counts
        counts = []
        epochs = []

        bin_0_key = f'{tower}_{prefix}_bin_0'
        if bin_0_key in metrics:
            epoch_steps = sorted(set(m['step'] for m in metrics[bin_0_key]))

            for epoch in epoch_steps:
                epochs.append(epoch)
                epoch_counts = []
                for i in range(25):
                    bin_key = f'{tower}_{prefix}_bin_{i}'
                    if bin_key in metrics:
                        bin_values = {m['step']: m['value'] for m in metrics[bin_key]}
                        epoch_counts.append(bin_values.get(epoch, 0))
                counts.append(epoch_counts)

        return {
            'available': True,
            'epochs': epochs,
            'bin_edges': bin_edges,
            'counts': counts
        }
```

---

### 5. Training Cache Service

**Location:** `ml_platform/experiments/training_cache_service.py`

**Purpose:** Cache training history from MLflow to Django DB for instant UI response

```python
class TrainingCacheService:
    """Cache training history from MLflow to Django DB."""

    EPOCH_SAMPLE_INTERVAL = 5  # Cache every 5th epoch

    def __init__(self):
        self.mlflow_service = MLflowService()

    def cache_training_history(self, quick_test: QuickTest) -> bool:
        """
        Fetch training history from MLflow and cache in Django DB.

        Returns True if successful, False otherwise.
        """
        if not quick_test.mlflow_run_id:
            logger.info(f"No MLflow run ID for QuickTest {quick_test.id}")
            return False

        try:
            # Fetch from MLflow
            full_history = self.mlflow_service.get_training_history(quick_test.mlflow_run_id)

            if not full_history.get('available'):
                return False

            # Sample epochs to reduce cache size
            sampled_history = self._sample_epochs(full_history)

            # Remove histogram data (fetched on-demand)
            sampled_history.pop('weight_stats', None)
            sampled_history.pop('gradient_stats', None)
            sampled_history['histogram_available'] = True

            # Add metadata
            sampled_history['cached_at'] = datetime.utcnow().isoformat()
            sampled_history['mlflow_run_id'] = quick_test.mlflow_run_id

            # Store in DB
            quick_test.training_history_json = sampled_history
            quick_test.save(update_fields=['training_history_json'])

            logger.info(f"Cached training history for QuickTest {quick_test.id}")
            return True

        except Exception as e:
            logger.exception(f"Failed to cache training history: {e}")
            return False

    def _sample_epochs(self, history: dict) -> dict:
        """Sample every Nth epoch to reduce cache size."""
        epochs = history.get('epochs', [])
        if not epochs:
            return history

        # Get sample indices
        sample_indices = [i for i, e in enumerate(epochs) if e % self.EPOCH_SAMPLE_INTERVAL == 0]
        # Always include last epoch
        if len(epochs) - 1 not in sample_indices:
            sample_indices.append(len(epochs) - 1)

        sampled = {
            'available': True,
            'epochs': [epochs[i] for i in sample_indices],
            'loss': {},
            'gradient': {},
            'final_metrics': history.get('final_metrics', {}),
            'params': history.get('params', {})
        }

        # Sample loss curves
        for key, values in history.get('loss', {}).items():
            sampled['loss'][key] = [values[i] for i in sample_indices if i < len(values)]

        # Sample gradient norms
        for key, values in history.get('gradient', {}).items():
            sampled['gradient'][key] = [values[i] for i in sample_indices if i < len(values)]

        return sampled

    def get_training_history(self, quick_test: QuickTest) -> dict:
        """Get training history from cache or fetch from MLflow."""
        if quick_test.training_history_json:
            return quick_test.training_history_json

        # Cache miss - fetch and cache
        if self.cache_training_history(quick_test):
            return quick_test.training_history_json

        return {'available': False}
```

---

## Data Flow

### Training Phase

```
1. Vertex AI starts training job
   └── Trainer code executes (generated from configs/services.py)

2. MLflowRestClient.wait_for_ready()
   └── Waits up to 120s for Cloud Run cold start
   └── Exponential backoff: 5s, 10s, 15s, 20s...

3. MLflowRestClient.set_experiment("model-endpoint-name")
   └── POST /api/2.0/mlflow/experiments/get-by-name
   └── If not found: POST /api/2.0/mlflow/experiments/create

4. MLflowRestClient.start_run("quick-test-{id}")
   └── POST /api/2.0/mlflow/runs/create

5. MLflowRestClient.log_params(...)
   └── POST /api/2.0/mlflow/runs/log-batch
   └── Parameters: epochs, batch_size, learning_rate, optimizer, etc.

6. For each epoch:
   ├── MLflowCallback: logs loss, val_loss, regularization_loss, etc.
   ├── WeightNormCallback: logs weight_norm, query_weight_norm, candidate_weight_norm
   ├── WeightStatsCallback: logs {tower}_weights_{mean,std,min,max}, histogram bins
   └── GradientStatsCallback: logs {tower}_grad_{mean,std,min,max,norm}, histogram bins

7. MLflowRestClient.end_run()
   └── POST /api/2.0/mlflow/runs/update (status=FINISHED)

8. _write_mlflow_info(gcs_path, run_id)
   └── Writes JSON to GCS: {gcs_path}/mlflow_info.json
   └── Content: {"run_id": "...", "tracking_uri": "..."}
```

### Retrieval Phase

```
1. Django polls for training completion
   └── Reads mlflow_info.json from GCS
   └── Stores mlflow_run_id in QuickTest model

2. User opens Training tab
   └── API: GET /api/quick-tests/{id}/training-history/

3. TrainingCacheService.get_training_history()
   ├── If training_history_json exists: return immediately (<1s)
   └── If cache miss:
       ├── MLflowService.get_training_history(run_id)
       │   └── 50+ REST API calls to MLflow
       ├── Sample epochs (every 5th)
       ├── Store in training_history_json
       └── Return cached data

4. User clicks Weight Analysis
   └── API: GET /api/quick-tests/{id}/histogram-data/
   └── MLflowService.get_histogram_data(run_id)
   └── Returns histogram data on-demand (not cached)
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MLFLOW_TRACKING_URI` | `https://mlflow-server-{project}.europe-central2.run.app` | MLflow server URL |
| `MLFLOW_BACKEND_STORE_URI` | (Cloud SQL connection) | PostgreSQL connection string |
| `MLFLOW_ARTIFACT_ROOT` | `gs://{project}-mlflow-artifacts` | GCS bucket for artifacts |
| `MLFLOW_WORKERS` | `2` | Number of gunicorn workers |
| `MLFLOW_RUN_NAME` | `quick-test` | Default run name prefix |

### Django Settings

**Location:** `config/settings.py`

```python
MLFLOW_TRACKING_URI = os.environ.get(
    'MLFLOW_TRACKING_URI',
    'https://mlflow-server-555035914949.europe-central2.run.app'
)
```

---

## API Reference

### Training History API

**Endpoint:** `GET /api/quick-tests/{id}/training-history/`

**Response:**
```json
{
  "available": true,
  "epochs": [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 49],
  "loss": {
    "train": [0.5, 0.4, 0.35, 0.32, 0.30, 0.28, 0.27, 0.26, 0.25, 0.25, 0.24],
    "val": [0.55, 0.45, 0.40, 0.38, 0.36, 0.34, 0.33, 0.32, 0.31, 0.31, 0.30],
    "total": [0.6, 0.5, 0.45, 0.42, 0.40, 0.38, 0.37, 0.36, 0.35, 0.35, 0.34],
    "val_total": [0.65, 0.55, 0.50, 0.48, 0.46, 0.44, 0.43, 0.42, 0.41, 0.41, 0.40]
  },
  "gradient": {
    "total": [1.2, 1.1, 1.0, 0.95, 0.90, 0.88, 0.85, 0.83, 0.82, 0.81, 0.80],
    "query": [0.8, 0.75, 0.70, 0.68, 0.65, 0.63, 0.62, 0.61, 0.60, 0.60, 0.59],
    "candidate": [0.9, 0.85, 0.80, 0.78, 0.75, 0.73, 0.72, 0.71, 0.70, 0.70, 0.69]
  },
  "final_metrics": {
    "final_loss": 0.24,
    "final_val_loss": 0.30,
    "test_loss": 0.28,
    "test_recall_at_5": 0.002,
    "test_recall_at_10": 0.005,
    "test_recall_at_50": 0.035,
    "test_recall_at_100": 0.075
  },
  "params": {
    "epochs": "50",
    "batch_size": "2048",
    "learning_rate": "0.01",
    "optimizer": "adagrad",
    "embedding_dim": "32"
  },
  "cached_at": "2026-01-02T10:30:00Z",
  "mlflow_run_id": "abc123def456",
  "histogram_available": true
}
```

### Histogram Data API

**Endpoint:** `GET /api/quick-tests/{id}/histogram-data/?type={weights|gradients}&tower={query|candidate}`

**Response:**
```json
{
  "available": true,
  "epochs": [0, 1, 2, 3, 4, 5, ...],
  "bin_edges": [-0.31, -0.28, -0.25, ..., 0.28, 0.31],
  "counts": [
    [5, 120, 890, 2345, 4567, ...],
    [4, 115, 920, 2400, 4600, ...],
    ...
  ]
}
```

---

## Database Schema

### QuickTest Model Fields

```python
class QuickTest(models.Model):
    # ... other fields ...

    # MLflow tracking
    mlflow_run_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="MLflow run ID for this experiment"
    )

    mlflow_experiment_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="MLflow experiment name (typically model endpoint name)"
    )

    # Cached training data
    training_history_json = models.JSONField(
        null=True,
        blank=True,
        help_text="Cached training history data for fast loading"
    )
```

### MLflow Database Tables

```sql
-- experiments table
CREATE TABLE experiments (
    experiment_id INTEGER PRIMARY KEY,
    name VARCHAR(256) UNIQUE,
    artifact_location VARCHAR(256),
    lifecycle_stage VARCHAR(32),
    creation_time BIGINT,
    last_update_time BIGINT
);

-- runs table
CREATE TABLE runs (
    run_uuid VARCHAR(32) PRIMARY KEY,
    name VARCHAR(250),
    source_type VARCHAR(20),
    source_name VARCHAR(500),
    entry_point_name VARCHAR(50),
    user_id VARCHAR(256),
    status VARCHAR(9),
    start_time BIGINT,
    end_time BIGINT,
    source_version VARCHAR(50),
    lifecycle_stage VARCHAR(20),
    artifact_uri VARCHAR(200),
    experiment_id INTEGER REFERENCES experiments
);

-- metrics table (time-series data)
CREATE TABLE metrics (
    key VARCHAR(250),
    value DOUBLE PRECISION,
    timestamp BIGINT,
    run_uuid VARCHAR(32) REFERENCES runs,
    step BIGINT,
    is_nan BOOLEAN,
    PRIMARY KEY (key, timestamp, step, run_uuid, is_nan)
);

-- params table
CREATE TABLE params (
    key VARCHAR(250),
    value VARCHAR(500),
    run_uuid VARCHAR(32) REFERENCES runs,
    PRIMARY KEY (key, run_uuid)
);

-- tags table
CREATE TABLE tags (
    key VARCHAR(250),
    value VARCHAR(5000),
    run_uuid VARCHAR(32) REFERENCES runs,
    PRIMARY KEY (key, run_uuid)
);
```

---

## Metrics Catalog

### Loss Metrics

| Metric | Logged By | Description |
|--------|-----------|-------------|
| `loss` | Keras | Primary training loss |
| `val_loss` | Keras | Validation loss |
| `regularization_loss` | Keras | L2 regularization loss |
| `val_regularization_loss` | Keras | Validation regularization |
| `total_loss` | Keras | Training + regularization |
| `val_total_loss` | Keras | Validation + regularization |

### Weight Metrics

| Metric | Logged By | Description |
|--------|-----------|-------------|
| `weight_norm` | WeightNormCallback | Total L2 norm of all weights |
| `query_weight_norm` | WeightNormCallback | L2 norm of query tower weights |
| `candidate_weight_norm` | WeightNormCallback | L2 norm of candidate tower weights |
| `{tower}_weights_mean` | WeightStatsCallback | Mean of tower weights |
| `{tower}_weights_std` | WeightStatsCallback | Std dev of tower weights |
| `{tower}_weights_min` | WeightStatsCallback | Min of tower weights |
| `{tower}_weights_max` | WeightStatsCallback | Max of tower weights |
| `{tower}_hist_bin_{0-24}` | WeightStatsCallback | Histogram bin counts |

### Gradient Metrics

| Metric | Logged By | Description |
|--------|-----------|-------------|
| `{tower}_grad_mean` | GradientStatsCallback | Mean gradient value |
| `{tower}_grad_std` | GradientStatsCallback | Gradient std dev |
| `{tower}_grad_min` | GradientStatsCallback | Min gradient |
| `{tower}_grad_max` | GradientStatsCallback | Max gradient |
| `{tower}_grad_norm` | GradientStatsCallback | L2 norm of gradients |
| `{tower}_grad_hist_bin_{0-24}` | GradientStatsCallback | Gradient histogram bins |

### Parameters

| Parameter | Description |
|-----------|-------------|
| `{tower}_hist_bin_edges` | Weight histogram bin edges (26 values) |
| `{tower}_grad_hist_bin_edges` | Gradient histogram bin edges (26 values) |
| `epochs` | Total training epochs |
| `batch_size` | Training batch size |
| `learning_rate` | Initial learning rate |
| `optimizer` | Optimizer name (adagrad, adam, etc.) |
| `embedding_dim` | Embedding dimension |

### Final/Test Metrics

| Metric | Description |
|--------|-------------|
| `final_loss` | Final training loss |
| `final_val_loss` | Final validation loss |
| `test_loss` | Test set loss |
| `test_recall_at_5` | Recall@5 on test set |
| `test_recall_at_10` | Recall@10 on test set |
| `test_recall_at_50` | Recall@50 on test set |
| `test_recall_at_100` | Recall@100 on test set |

---

## Authentication

### Service-to-Service Authentication

MLflow on Cloud Run uses GCP Identity-Aware authentication:

```
┌──────────────────┐         ┌──────────────────┐
│  Vertex AI Job   │         │   Django App     │
│  (Training)      │         │   (Cloud Run)    │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         │ 1. Get identity token      │ 1. Get identity token
         │    (metadata server)       │    (google.oauth2)
         │                            │
         ▼                            ▼
┌─────────────────────────────────────────────────┐
│              MLflow Server (Cloud Run)           │
│                                                  │
│  Validates: Authorization: Bearer {token}        │
│  Checks: Token audience matches service URL      │
└─────────────────────────────────────────────────┘
```

### Token Acquisition Methods

**Method 1: google.oauth2.id_token (preferred)**
```python
from google.oauth2 import id_token
from google.auth.transport.requests import Request

token = id_token.fetch_id_token(Request(), audience)
```

**Method 2: GCP Metadata Server (Vertex AI)**
```python
url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={audience}"
req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
token = urllib.request.urlopen(req).read().decode('utf-8')
```

**Method 3: gcloud CLI (local development)**
```bash
gcloud auth print-identity-token --audiences=https://mlflow-server-xxx.run.app
```

---

## Deployment

### Cloud Run Service

**Service:** `mlflow-server`
**Region:** `europe-central2`
**URL:** `https://mlflow-server-{project-number}.europe-central2.run.app`

**Deployment command:**
```bash
gcloud run deploy mlflow-server \
    --source mlflow_server/ \
    --region europe-central2 \
    --platform managed \
    --allow-unauthenticated=false \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 2 \
    --set-env-vars "MLFLOW_BACKEND_STORE_URI=postgresql://..." \
    --set-env-vars "MLFLOW_ARTIFACT_ROOT=gs://..." \
    --service-account mlflow-server@project.iam.gserviceaccount.com
```

### Cloud SQL Instance

**Instance:** `mlflow-db`
**Type:** PostgreSQL 15
**Region:** `europe-central2`
**Tier:** `db-f1-micro` (for cost savings)

**Connection string:**
```
postgresql://mlflow:PASSWORD@/mlflow?host=/cloudsql/PROJECT:europe-central2:mlflow-db
```

### GCS Bucket

**Bucket:** `gs://{project}-mlflow-artifacts`
**Purpose:** MLflow artifact storage (not actively used - metrics in DB)

### IAM Permissions

**MLflow Service Account:**
- `roles/cloudsql.client` - Connect to Cloud SQL
- `roles/storage.objectAdmin` - Write artifacts to GCS

**Django Service Account:**
- `roles/run.invoker` - Call MLflow Cloud Run service

**Vertex AI Service Account:**
- `roles/run.invoker` - Call MLflow Cloud Run service

---

## File Reference

### Files to Keep for Reference

| File | Purpose |
|------|---------|
| `mlflow_server/Dockerfile` | MLflow server container definition |
| `mlflow_server/entrypoint.sh` | Server startup script |
| `mlflow_server/requirements.txt` | Python dependencies |
| `mlflow_server/README.md` | Setup and deployment instructions |
| `ml_platform/experiments/mlflow_service.py` | Django MLflow client (~800 lines) |
| `ml_platform/configs/services.py` | Trainer callbacks and REST client |
| `ml_platform/experiments/training_cache_service.py` | Caching layer |
| `tests/test_mlflow_integration.py` | Integration tests |

### Key Code Locations

| Component | File | Lines |
|-----------|------|-------|
| MLflowRestClient | `ml_platform/configs/services.py` | 1538-1827 |
| MLflowCallback | `ml_platform/configs/services.py` | 2692-2698 |
| WeightNormCallback | `ml_platform/configs/services.py` | 2701-2738 |
| WeightStatsCallback | `ml_platform/configs/services.py` | 2741-2795 |
| GradientStatsCallback | `ml_platform/configs/services.py` | 2798-2868 |
| _write_mlflow_info | `ml_platform/configs/services.py` | 2871-2891 |
| run_fn MLflow setup | `ml_platform/configs/services.py` | 2956-3105 |
| MLflowService class | `ml_platform/experiments/mlflow_service.py` | 36-826 |
| TrainingCacheService | `ml_platform/experiments/training_cache_service.py` | All |
| QuickTest MLflow fields | `ml_platform/models.py` | 1773-1787 |
| MLFLOW_TRACKING_URI setting | `config/settings.py` | 203-211 |

---

## Estimated Costs

| Resource | Monthly Cost |
|----------|--------------|
| Cloud Run (MLflow server) | ~$20 |
| Cloud SQL (db-f1-micro) | ~$30 |
| GCS (artifacts) | ~$1 |
| **Total** | **~$50/month** |

---

## Lessons Learned

### What Worked Well

1. **REST API approach**: Using REST instead of MLflow Python SDK avoided dependency conflicts in Vertex AI containers
2. **Django caching**: Caching in Django DB reduced Training tab load time from 2-3 min to <1 sec
3. **GCS bridge file**: `mlflow_info.json` in GCS provided reliable handoff between training and Django
4. **Per-tower metrics**: Separating query/candidate tower metrics enabled better debugging

### What Didn't Work Well

1. **Cold start latency**: Cloud Run cold starts of 5-15 seconds impacted UX
2. **N+1 API calls**: Fetching metric history required 50+ sequential HTTP calls
3. **Infrastructure overhead**: Maintaining separate service for a write-once-read-rarely pattern
4. **Cost/value ratio**: ~$50/month for functionality mostly replaced by caching

### Recommendations for Future

If re-implementing experiment tracking:

1. **Consider direct GCS storage**: Write training metrics as JSON to GCS, read directly from Django
2. **Use batch logging**: Log metrics in batches at training end rather than per-epoch REST calls
3. **Pre-compute charts**: Store chart-ready data structures, not raw metric values
4. **Evaluate alternatives**: Weights & Biases, Neptune.ai, or custom BigQuery solution

---

*This document captures the complete MLflow integration as of January 2026. Use it as a reference if this architecture needs to be reconstructed.*
