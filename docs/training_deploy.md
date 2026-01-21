# Model Deployment Guide

This document describes the model deployment architecture for TFRS (TensorFlow Recommenders) models trained via TFX pipelines. It covers the implementation details, configuration options, and usage instructions.

**Last Updated:** 2026-01-21

**Status:** Implemented

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Phase 1: Model Registry Integration](#phase-1-model-registry-integration)
4. [Phase 2: Raw Tensor Serving Signature](#phase-2-raw-tensor-serving-signature)
5. [Phase 3: TF Serving Container](#phase-3-tf-serving-container)
6. [Phase 4: Deployment API & UI](#phase-4-deployment-api--ui)
7. [Configuration Reference](#configuration-reference)
8. [Usage Guide](#usage-guide)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The deployment system enables one-click deployment of trained recommendation models to Cloud Run with TensorFlow Serving. Key features:

- **Automatic Model Registration**: Models are registered to Vertex AI Model Registry after training completion
- **Simple JSON Interface**: Raw tensor inputs for easy client integration (no protobuf serialization required)
- **Serverless Deployment**: Cloud Run with scale-to-zero for cost efficiency
- **Automatic Batching**: TF Serving handles request batching for GPU efficiency

### Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Serving Interface** | Raw Tensors (Simple JSON) | Simple client experience; same as past FastAPI solution |
| **Deployment Target** | Cloud Run + TF Serving | Scale-to-zero minimizes costs during development |
| **Model Types** | Retrieval first | Polish one type before expanding to Ranking/Multitask |
| **Container Registry** | Artifact Registry | Regional (europe-central2), integrated with Cloud Build |
| **TF Serving Version** | 2.19.0 | Latest stable version available |

### Client Interface

**Request:**
```json
POST https://{service-name}.run.app/v1/models/recommender:predict
{
  "instances": [
    {
      "customer_id": "CUST123",
      "city": "Warsaw",
      "revenue": 5000.0,
      "segment": "enterprise"
    }
  ]
}
```

**Response:**
```json
{
  "predictions": [
    {
      "product_ids": ["PROD001", "PROD002", "PROD003", ...],
      "scores": [0.95, 0.87, 0.82, ...]
    }
  ]
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TFX Pipeline (Vertex AI)                                                   │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Pusher Component                                                     │   │
│  │   - Saves ServingModel to gs://bucket/training-runs/{id}/pushed_model│   │
│  │   - Model has RAW TENSOR signature (simple JSON interface)          │   │
│  │   - Self-contained (vocabs + embeddings embedded)                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ▼ (automatic after pipeline completion)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Vertex AI Model Registry                                             │   │
│  │   - Auto-registered via _register_to_model_registry()               │   │
│  │   - Labels: training_run_id, model_type, metrics, is_blessed        │   │
│  │   - Enables version tracking and lineage                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ▼ (one-click from UI)                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Cloud Run Service                                                    │   │
│  │   ┌─────────────────────────────────────────────────────────────┐   │   │
│  │   │ TF Serving Container (europe-central2-docker.pkg.dev/...)   │   │   │
│  │   │                                                              │   │   │
│  │   │ startup.sh:                                                  │   │   │
│  │   │   1. Downloads model from GCS (MODEL_PATH env var)          │   │   │
│  │   │   2. Starts tensorflow_model_server with batching           │   │   │
│  │   │                                                              │   │   │
│  │   │ Endpoints:                                                   │   │   │
│  │   │   - REST: POST /v1/models/recommender:predict               │   │   │
│  │   │   - gRPC: port 8500                                         │   │   │
│  │   └─────────────────────────────────────────────────────────────┘   │   │
│  │                                                                      │   │
│  │   Configuration:                                                     │   │
│  │   - Memory: 4Gi (configurable)                                      │   │
│  │   - CPU: 2 (configurable)                                           │   │
│  │   - Min instances: 0 (scale to zero)                                │   │
│  │   - Max instances: 10                                               │   │
│  │   - Batching: enabled (max 64 requests)                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Model Registry Integration

### Implementation

Models are automatically registered to Vertex AI Model Registry after training pipeline completion.

**File:** `ml_platform/training/services.py`

**Method:** `_register_to_model_registry()`

```python
def _register_to_model_registry(self, training_run: TrainingRun) -> None:
    """
    Register trained model to Vertex AI Model Registry.
    Called automatically after pipeline completion.
    """
    # Build display name with version
    model_name = f"{self.ml_model.slug}-v{training_run.run_number}"
    artifact_uri = f"{training_run.gcs_artifacts_path}/pushed_model"

    # Labels for tracking (values must be strings, max 63 chars)
    labels = {
        'training_run_id': str(training_run.id),
        'model_endpoint_id': str(self.ml_model.id),
        'model_type': training_run.model_type,
        'is_blessed': str(training_run.is_blessed).lower(),
    }

    # Add metrics as labels
    if training_run.recall_at_100:
        labels['recall_at_100'] = f"{training_run.recall_at_100:.4f}"

    model = aiplatform.Model.upload(
        display_name=model_name,
        artifact_uri=artifact_uri,
        serving_container_image_uri="tensorflow/serving:2.19.0",
        labels=labels,
    )

    # Update TrainingRun
    training_run.vertex_model_resource_name = model.resource_name
    training_run.vertex_model_name = model.display_name
    training_run.registered_at = timezone.now()
    training_run.save()
```

### Trigger Point

Registration is triggered in `_extract_results()` after blessing status is determined:

```python
# After saving is_blessed status
training_run.save(update_fields=['is_blessed'])

# Register to Model Registry (regardless of blessing status)
try:
    self._register_to_model_registry(training_run)
except Exception as e:
    logger.warning(f"Model registration failed (non-fatal): {e}")
```

### Database Fields

**TrainingRun model** (`ml_platform/training/models.py`):

| Field | Type | Description |
|-------|------|-------------|
| `vertex_model_resource_name` | CharField(500) | Full Vertex AI Model resource name |
| `vertex_model_name` | CharField(255) | Display name in Model Registry |
| `registered_at` | DateTimeField | When the model was registered |

### Viewing in Console

Registered models appear in:
- Google Cloud Console → Vertex AI → Model Registry
- Filter by labels: `training_run_id`, `model_type`, `is_blessed`

---

## Phase 2: Raw Tensor Serving Signature

### Implementation

The ServingModel is generated with a dynamic input signature based on buyer features, enabling simple JSON requests.

**File:** `ml_platform/configs/services.py`

### Helper Method: `_generate_raw_tensor_signature()`

Generates TensorFlow input signature based on buyer features from FeatureConfig:

```python
def _generate_raw_tensor_signature(self) -> tuple:
    """
    Generate raw tensor input signature based on buyer features.

    Returns:
        tuple: (signature_specs, param_names, raw_features_dict_lines)
    """
    signature_specs = []
    param_names = []
    raw_features_lines = []

    # Type mapping: BigQuery type → TensorFlow dtype
    type_mapping = {
        'STRING': 'tf.string',
        'BYTES': 'tf.string',
        'INT64': 'tf.int64',
        'INTEGER': 'tf.int64',
        'FLOAT64': 'tf.float32',
        'FLOAT': 'tf.float32',
        'NUMERIC': 'tf.float32',
        'TIMESTAMP': 'tf.int64',
        'DATETIME': 'tf.int64',
        'DATE': 'tf.string',
    }

    for feature in self.buyer_features:
        col_name = feature.get('display_name') or feature.get('column')
        bq_type = (feature.get('bq_type') or feature.get('data_type') or 'STRING').upper()
        tf_dtype = type_mapping.get(bq_type, 'tf.string')

        signature_specs.append(
            f"        tf.TensorSpec(shape=[None], dtype={tf_dtype}, name='{col_name}'),"
        )
        param_names.append(col_name)
        raw_features_lines.append(f"            '{col_name}': {col_name},")

    return signature_specs, param_names, raw_features_lines
```

### Generated ServingModel

The `_generate_brute_force_serve_fn()` method generates:

```python
class ServingModel(tf.keras.Model):
    """
    Wrapper model for serving with raw tensor inputs.
    Accepts simple JSON: {"customer_id": "X", "city": "Y", "revenue": 100.0, ...}
    """

    def __init__(self, retrieval_model, tf_transform_output, product_ids, product_embeddings):
        super().__init__()
        self.retrieval_model = retrieval_model
        self.tft_layer = tf_transform_output.transform_features_layer()
        self.product_ids = tf.Variable(product_ids, trainable=False)
        self.product_embeddings = tf.Variable(product_embeddings, trainable=False)

    @tf.function(input_signature=[
        tf.TensorSpec(shape=[None], dtype=tf.string, name='customer_id'),
        tf.TensorSpec(shape=[None], dtype=tf.string, name='city'),
        tf.TensorSpec(shape=[None], dtype=tf.float32, name='revenue'),
        # ... dynamically generated based on buyer features
    ])
    def serve(self, customer_id, city, revenue, ...):
        # Build raw features dict from inputs
        raw_features = {
            'customer_id': customer_id,
            'city': city,
            'revenue': revenue,
            # ...
        }

        # Apply TFT preprocessing (vocabularies, normalization, etc.)
        transformed_features = self.tft_layer(raw_features)

        # Get query embeddings from buyer tower
        query_embeddings = self.retrieval_model.query_tower(transformed_features)

        # Compute similarities with all product embeddings
        similarities = tf.linalg.matmul(
            query_embeddings,
            self.product_embeddings,
            transpose_b=True
        )

        # Get top-100 recommendations
        top_scores, top_indices = tf.nn.top_k(similarities, k=100)
        recommended_products = tf.gather(self.product_ids, top_indices)

        return {
            'product_ids': recommended_products,
            'scores': top_scores
        }
```

### Type Mapping

| BigQuery Type | TensorFlow dtype | JSON Example |
|---------------|------------------|--------------|
| STRING, BYTES | tf.string | `"customer_id": "CUST123"` |
| INT64, INTEGER | tf.int64 | `"timestamp": 1705849200` |
| FLOAT64, FLOAT, NUMERIC | tf.float32 | `"revenue": 5000.0` |
| TIMESTAMP, DATETIME | tf.int64 | `"created_at": 1705849200` |
| DATE | tf.string | `"date": "2026-01-21"` |

---

## Phase 3: TF Serving Container

### Directory Structure

```
deploy/tf_serving/
├── Dockerfile           # TF Serving container with GCS support
├── startup.sh           # Model download and server startup
├── batching_config.txt  # Request batching configuration
└── cloudbuild.yaml      # Cloud Build configuration
```

### Dockerfile

**File:** `deploy/tf_serving/Dockerfile`

```dockerfile
FROM tensorflow/serving:2.19.0

# Install gsutil for GCS model download
RUN apt-get update && apt-get install -y curl gnupg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Copy configuration files
COPY batching_config.txt /etc/tf_serving/batching_config.txt
COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

# Environment variables (can be overridden at runtime)
ENV MODEL_BASE_PATH=/models
ENV MODEL_NAME=recommender
ENV PORT=8501

EXPOSE 8501

ENTRYPOINT ["/startup.sh"]
```

### Startup Script

**File:** `deploy/tf_serving/startup.sh`

```bash
#!/bin/bash
set -e

# MODEL_PATH must be set to GCS path
if [ -z "$MODEL_PATH" ]; then
    echo "ERROR: MODEL_PATH environment variable not set"
    exit 1
fi

# Create model directory structure (TF Serving expects /models/{name}/{version}/)
MODEL_DIR="/models/${MODEL_NAME:-recommender}/1"
mkdir -p "$MODEL_DIR"

# Download model from GCS
echo "Downloading model from $MODEL_PATH..."
gsutil -m cp -r "$MODEL_PATH/*" "$MODEL_DIR/"

# Verify model was downloaded
if [ ! -f "$MODEL_DIR/saved_model.pb" ]; then
    echo "ERROR: saved_model.pb not found"
    exit 1
fi

# Start TF Serving with batching enabled
tensorflow_model_server \
    --port=8500 \
    --rest_api_port=${PORT:-8501} \
    --model_name=${MODEL_NAME:-recommender} \
    --model_base_path=/models/${MODEL_NAME:-recommender} \
    --enable_batching=true \
    --batching_parameters_file=/etc/tf_serving/batching_config.txt
```

### Batching Configuration

**File:** `deploy/tf_serving/batching_config.txt`

```
# Maximum batch size for inference
max_batch_size { value: 64 }

# Maximum time to wait for a batch to fill (microseconds)
# 10ms = good balance between latency and throughput
batch_timeout_micros { value: 10000 }

# Maximum number of batches waiting in queue
max_enqueued_batches { value: 100 }

# Number of threads for processing batches
num_batch_threads { value: 4 }

# Allow variable-length inputs
pad_variable_length_inputs: true
```

### Cloud Build Configuration

**File:** `deploy/tf_serving/cloudbuild.yaml`

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'europe-central2-docker.pkg.dev/$PROJECT_ID/ml-serving/tf-serving:latest'
      - '-t'
      - 'europe-central2-docker.pkg.dev/$PROJECT_ID/ml-serving/tf-serving:$SHORT_SHA'
      - '.'
    dir: 'deploy/tf_serving'

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'europe-central2-docker.pkg.dev/$PROJECT_ID/ml-serving/tf-serving:latest']

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'europe-central2-docker.pkg.dev/$PROJECT_ID/ml-serving/tf-serving:$SHORT_SHA']

images:
  - 'europe-central2-docker.pkg.dev/$PROJECT_ID/ml-serving/tf-serving:latest'
  - 'europe-central2-docker.pkg.dev/$PROJECT_ID/ml-serving/tf-serving:$SHORT_SHA'

options:
  logging: CLOUD_LOGGING_ONLY
  machineType: 'E2_HIGHCPU_8'

timeout: '600s'
```

### Building the Container

```bash
# From project root
SHORT_SHA=$(git rev-parse --short HEAD)
gcloud builds submit --config=deploy/tf_serving/cloudbuild.yaml --substitutions=SHORT_SHA=$SHORT_SHA .
```

### Container Registry

- **Location:** `europe-central2-docker.pkg.dev/b2b-recs/ml-serving/tf-serving`
- **Tags:** `latest`, `{git-short-sha}`

---

## Phase 4: Deployment API & UI

### TrainingService Method

**File:** `ml_platform/training/services.py`

**Method:** `deploy_to_cloud_run()`

```python
def deploy_to_cloud_run(self, training_run: TrainingRun) -> str:
    """
    Deploy trained model to Cloud Run with TF Serving.

    Args:
        training_run: TrainingRun instance to deploy

    Returns:
        str: Cloud Run service URL

    Raises:
        TrainingServiceError: If deployment fails
    """
    # Validate prerequisites
    if not training_run.vertex_model_resource_name:
        raise TrainingServiceError("Model not registered in Model Registry")

    if training_run.status not in [TrainingRun.STATUS_COMPLETED, TrainingRun.STATUS_NOT_BLESSED]:
        raise TrainingServiceError(f"Cannot deploy model with status: {training_run.status}")

    # Build service name
    service_name = f"{self.ml_model.slug}-serving".lower().replace('_', '-')

    # Get deployment config
    deployment_config = training_run.deployment_config or {}
    memory = deployment_config.get('memory', '4Gi')
    cpu = deployment_config.get('cpu', '2')
    min_instances = deployment_config.get('min_instances', 0)
    max_instances = deployment_config.get('max_instances', 10)

    # Model path in GCS
    model_path = f"{training_run.gcs_artifacts_path}/pushed_model"

    # TF Serving container image
    tf_serving_image = f"europe-central2-docker.pkg.dev/{self.project_id}/ml-serving/tf-serving:latest"

    # Deploy using gcloud CLI
    cmd = [
        'gcloud', 'run', 'deploy', service_name,
        f'--image={tf_serving_image}',
        f'--region={self.REGION}',
        f'--project={self.project_id}',
        f'--memory={memory}',
        f'--cpu={cpu}',
        f'--min-instances={min_instances}',
        f'--max-instances={max_instances}',
        f'--set-env-vars=MODEL_PATH={model_path},MODEL_NAME=recommender',
        '--port=8501',
        '--allow-unauthenticated',
        '--format=value(status.url)',
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    service_url = result.stdout.strip()

    # Update TrainingRun
    training_run.is_deployed = True
    training_run.deployed_at = timezone.now()
    training_run.endpoint_resource_name = service_url
    training_run.save()

    return service_url
```

### API Endpoint

**File:** `ml_platform/training/api.py`

**Endpoint:** `POST /api/training-runs/{id}/deploy-cloud-run/`

```python
@csrf_exempt
@require_http_methods(["POST"])
def training_run_deploy_cloud_run(request, training_run_id):
    """Deploy a trained model to Cloud Run with TF Serving."""

    training_run = TrainingRun.objects.get(id=training_run_id)

    # Validate state
    if training_run.status not in [TrainingRun.STATUS_COMPLETED, TrainingRun.STATUS_NOT_BLESSED]:
        return JsonResponse({'error': 'Invalid status'}, status=400)

    if not training_run.vertex_model_resource_name:
        return JsonResponse({'error': 'Model not registered'}, status=400)

    # Deploy
    service = TrainingService(model_endpoint)
    endpoint_url = service.deploy_to_cloud_run(training_run)

    return JsonResponse({
        'success': True,
        'endpoint_url': endpoint_url,
        'message': f"Model deployed to Cloud Run: {endpoint_url}"
    })
```

### URL Route

**File:** `ml_platform/training/urls.py`

```python
path(
    'api/training-runs/<int:training_run_id>/deploy-cloud-run/',
    api.training_run_deploy_cloud_run,
    name='training_run_deploy_cloud_run'
),
```

### UI Integration

**File:** `static/js/training_cards.js`

The "Cloud Run" button appears for completed training runs that are not yet deployed:

```javascript
// Deploy to Cloud Run button (for completed runs with registered model)
if (allowedActions.includes('deployCloudRun') && run.status === 'completed' && !run.is_deployed) {
    primaryButtons.push(`
        <button class="card-action-btn deploy"
                onclick="event.stopPropagation(); TrainingCards.deployRunCloudRun(${run.id})"
                title="Deploy to Cloud Run">Cloud Run</button>
    `);
}
```

---

## Configuration Reference

### Deployment Configuration

Default values can be overridden via `training_run.deployment_config`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `memory` | `4Gi` | Cloud Run instance memory |
| `cpu` | `2` | Number of vCPUs |
| `min_instances` | `0` | Minimum instances (0 = scale to zero) |
| `max_instances` | `10` | Maximum instances |
| `timeout` | `300` | Request timeout in seconds |

### Batching Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_batch_size` | `64` | Maximum requests per batch |
| `batch_timeout_micros` | `10000` | Wait time for batch (10ms) |
| `max_enqueued_batches` | `100` | Maximum pending batches |
| `num_batch_threads` | `4` | Batch processing threads |

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `MODEL_PATH` | GCS path to model | `gs://bucket/training-runs/47/pushed_model` |
| `MODEL_NAME` | TF Serving model name | `recommender` |
| `PORT` | REST API port | `8501` |

---

## Usage Guide

### Deploying a Model

1. **Train a model** via the Training page
2. Wait for pipeline completion (model is automatically registered)
3. Click **"Cloud Run"** button on the training card
4. Confirm deployment
5. Copy the endpoint URL from the response

### Making Predictions

```python
import requests

# Get recommendations
response = requests.post(
    "https://{service-name}.run.app/v1/models/recommender:predict",
    json={
        "instances": [
            {
                "customer_id": "CUST123",
                "city": "Warsaw",
                "revenue": 5000.0,
                "segment": "enterprise"
            }
        ]
    }
)

result = response.json()
product_ids = result['predictions'][0]['product_ids']
scores = result['predictions'][0]['scores']
```

### Batch Predictions

```python
# Multiple customers in single request
response = requests.post(
    "https://{service-name}.run.app/v1/models/recommender:predict",
    json={
        "instances": [
            {"customer_id": "CUST1", "city": "Warsaw", "revenue": 5000.0},
            {"customer_id": "CUST2", "city": "Krakow", "revenue": 3000.0},
            {"customer_id": "CUST3", "city": "Gdansk", "revenue": 7000.0}
        ]
    }
)
```

### Updating a Deployment

To deploy a newer model version:

1. Train a new model
2. Click **"Cloud Run"** on the new training run
3. The existing Cloud Run service is updated with the new model

### Health Check

```bash
curl https://{service-name}.run.app/v1/models/recommender
```

---

## Troubleshooting

### Model Registration Failed

**Symptoms:** `vertex_model_resource_name` is empty after training completion

**Solutions:**
1. Check Vertex AI API is enabled
2. Verify IAM permissions for Model Registry
3. Check logs: `TrainingService._register_to_model_registry()`

### Deployment Failed

**Symptoms:** Error when clicking "Cloud Run" button

**Common causes:**
- Model not registered (wait for registration)
- Cloud Run API not enabled
- IAM permissions missing
- Image not found in Artifact Registry

**Debug:**
```bash
# Check service status
gcloud run services describe {service-name} --region=europe-central2

# Check logs
gcloud run services logs read {service-name} --region=europe-central2
```

### Inference Errors

**404 Not Found:**
- Model name mismatch (check `MODEL_NAME` env var)
- Model not loaded (check startup logs)

**Input validation errors:**
- Feature name mismatch (check FeatureConfig)
- Type mismatch (see Type Mapping table)

**Cold start timeout:**
- Increase `min_instances` to 1+
- Increase Cloud Run timeout

### Container Build Failed

```bash
# Rebuild container
SHORT_SHA=$(git rev-parse --short HEAD)
gcloud builds submit --config=deploy/tf_serving/cloudbuild.yaml --substitutions=SHORT_SHA=$SHORT_SHA .
```

---

## Summary

| Component | Technology | Status |
|-----------|------------|--------|
| Training Pipeline | TFX on Vertex AI | Implemented |
| ServingModel (Raw Tensors) | Dynamic code generation | Implemented |
| Model Registry | Vertex AI Model Registry | Implemented |
| TF Serving Container | Cloud Run + TF Serving 2.19.0 | Implemented |
| Deployment API | Django REST | Implemented |
| Deployment UI | Training page integration | Implemented |

### Files Modified/Created

| File | Changes |
|------|---------|
| `ml_platform/training/services.py` | Added `_register_to_model_registry()`, `deploy_to_cloud_run()` |
| `ml_platform/training/models.py` | Added `registered_at` field |
| `ml_platform/training/api.py` | Added `training_run_deploy_cloud_run()` endpoint |
| `ml_platform/training/urls.py` | Added Cloud Run deploy URL route |
| `ml_platform/configs/services.py` | Added `_generate_raw_tensor_signature()`, updated `_generate_brute_force_serve_fn()` |
| `static/js/training_cards.js` | Added Cloud Run deploy button and function |
| `deploy/tf_serving/Dockerfile` | Created TF Serving container |
| `deploy/tf_serving/startup.sh` | Created startup script |
| `deploy/tf_serving/batching_config.txt` | Created batching config |
| `deploy/tf_serving/cloudbuild.yaml` | Created Cloud Build config |
