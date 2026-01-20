# Model Deployment Guide

This document describes the model deployment architecture for TFRS (TensorFlow Recommenders) models trained via TFX pipelines. It covers past solutions, technical considerations, and the recommended deployment approach.

## Table of Contents

1. [Background & Context](#background--context)
2. [Past Solutions](#past-solutions)
3. [Technical Deep Dive: Serving Architectures](#technical-deep-dive-serving-architectures)
4. [TFRS Model Deployment Challenges](#tfrs-model-deployment-challenges)
5. [Current TFX ServingModel Architecture](#current-tfx-servingmodel-architecture)
6. [Deployment Options Comparison](#deployment-options-comparison)
7. [Recommended Solution: Cloud Run + TF Serving](#recommended-solution-cloud-run--tf-serving)
8. [Vertex AI Model Registry](#vertex-ai-model-registry)
9. [Implementation Plan](#implementation-plan)
10. [Reference Files](#reference-files)

---

## Background & Context

### The Problem

After training TFRS models (Retrieval, Ranking, Multitask) via TFX pipelines on Vertex AI, we need to:

1. **Register** the trained model for versioning and tracking
2. **Deploy** the model to a serving endpoint for inference
3. Support **batch processing** for efficient GPU utilization
4. Achieve **<20ms latency** for 5K-20K product catalogs

### Why This Is Non-Trivial

TFRS models have unique deployment challenges that standard TensorFlow models don't face:

- Two-Tower architecture (Query + Candidate towers)
- FactorizedTopK metric layer (training-only, doesn't serialize well)
- Need to pre-compute candidate embeddings
- Custom serving signatures for recommendation output format

---

## Past Solutions

### Custom Cloud Run + FastAPI Service

**Location:** `past/recs/cloud_run_service/main.py`

**What It Does:**
```python
# Loads SavedModel from GCS
saved_model = tf.saved_model.load(saved_model_path)

# Calls serving signature with RAW TENSORS
result = saved_model.signatures['serving_default'](
    customer_id=tf.constant(customer_id),
    city=tf.constant(city),
    revenue=tf.constant(revenue),
    timestamp=tf.constant(timestamp, dtype=tf.int64)
)
```

**Why It Was Created:**
1. Vertex AI Endpoints failed to deploy TFRS models (FactorizedTopK serialization issues)
2. Needed custom response format (product_ids + scores)
3. Wanted simple raw tensor inputs (not serialized tf.Examples)

**Pros:**
- Full control over serving logic
- Simple client interface (raw values, not protobufs)
- Easy to debug

**Cons:**
- ~300 lines of custom code to maintain
- Manual batch processing implementation required
- No automatic optimizations

### Custom Trainer with Embedded Serving Function

**Location:** `past/recs/trainer/main.py`

**What It Does:**
```python
# Lines 405-474: Creates serving function
def _get_simple_serve_fn(model, product_ids, ...):
    # Pre-compute ALL product embeddings at model save time
    all_candidate_embeddings = ...  # Computed once, embedded in graph

    @tf.function
    def serve_fn(customer_id, city, revenue, timestamp):
        query_embeddings = model.query_model(...)
        similarities = tf.linalg.matmul(query_embeddings, all_candidate_embeddings, transpose_b=True)
        top_scores, top_indices = tf.nn.top_k(similarities, k=100)
        return {'product_ids': ..., 'scores': top_scores}

    return serve_fn
```

**Key Design Decisions:**
1. **Pre-computed embeddings**: All product embeddings computed at save time, stored in the graph
2. **Brute-force top-k**: Simple matrix multiplication + top_k (efficient for <20K products)
3. **Raw tensor signature**: Accepts individual tensor inputs, not serialized Examples
4. **Self-contained model**: No external vocab files or embedding files needed at inference

**Why This Pattern Works:**
- Removes FactorizedTopK (the problematic training-only layer)
- All vocabularies embedded via StringLookup layers
- Single SavedModel contains everything needed for inference

---

## Technical Deep Dive: Serving Architectures

### TensorFlow Serving

TensorFlow Serving is Google's production model server (C++ binary):

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TENSORFLOW SERVING                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Input: SavedModel directory                                        │
│                                                                      │
│  Provides automatically:                                            │
│    - REST API: POST /v1/models/{name}:predict                      │
│    - gRPC API: PredictionService.Predict()                         │
│    - Automatic request batching                                     │
│    - Model version management                                       │
│    - Health checks                                                  │
│                                                                      │
│  You write: ZERO serving code                                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**TF Serving is software, not a cloud service.** It must run on a compute platform:
- Cloud Run (containerized)
- GCE VM
- GKE
- Vertex AI Endpoints (managed TF Serving)

### Serialized tf.Examples vs Raw Tensors

**Serialized tf.Examples** (TFX/TF Serving standard):
```python
# Client must serialize inputs to protobuf
example = tf.train.Example(features=tf.train.Features(feature={
    'customer_id': tf.train.Feature(bytes_list=tf.train.BytesList(value=[b'CUST123'])),
    'city': tf.train.Feature(bytes_list=tf.train.BytesList(value=[b'NYC'])),
    'revenue': tf.train.Feature(float_list=tf.train.FloatList(value=[100.0])),
}))
serialized = example.SerializeToString()

# Send binary blob to model
result = model.signatures['serving_default'](examples=tf.constant([serialized]))
```

**Raw Tensors** (simpler client code):
```python
# Client sends values directly
result = model.signatures['serving_default'](
    customer_id=tf.constant(['CUST123']),
    city=tf.constant(['NYC']),
    revenue=tf.constant([100.0])
)
```

**Current TFX ServingModel uses serialized tf.Examples** because:
- Standard format for TF Serving
- Same format as TFRecords (training data)
- Enables automatic batching optimizations

**Trade-off:**
- Serialized: More complex client, but standard and optimized
- Raw tensors: Simpler client, but non-standard

### Automatic Batching in TF Serving

TF Serving can batch multiple requests for GPU efficiency:

```
Request 1 (t=0ms)  ──┐
Request 2 (t=2ms)  ──┼──► TF Serving waits up to 10ms ──► Single GPU call ──► Split results
Request 3 (t=5ms)  ──┘
```

Configuration (`batching_parameters.txt`):
```
max_batch_size { value: 128 }
batch_timeout_micros { value: 10000 }
num_batch_threads { value: 4 }
pad_variable_length_inputs: true
```

This is **automatic** with TF Serving. With FastAPI, you must implement batching manually.

---

## TFRS Model Deployment Challenges

### Why Raw TFRS Models Don't Deploy Well

A typical TFRS Retrieval model:

```python
class RetrievalModel(tfrs.Model):
    def __init__(self):
        self.query_tower = QueryModel(...)
        self.candidate_tower = CandidateModel(...)

        # THIS IS THE PROBLEM
        self.task = tfrs.tasks.Retrieval(
            metrics=tfrs.metrics.FactorizedTopK(
                candidates=candidate_dataset.batch(128).map(self.candidate_tower)
            )
        )
```

**FactorizedTopK issues:**
1. Loads entire candidate dataset into memory during model construction
2. References external dataset (can't serialize)
3. Designed for training metrics, not serving

### The Solution: ServingModel Wrapper

Instead of deploying the raw TFRS model, we create a wrapper:

```python
class ServingModel(tf.keras.Model):
    def __init__(self, retrieval_model, product_ids, product_embeddings):
        # Store pre-computed embeddings as model variables
        self.product_ids = tf.Variable(product_ids, trainable=False)
        self.product_embeddings = tf.Variable(product_embeddings, trainable=False)
        self.query_tower = retrieval_model.query_tower

    @tf.function
    def serve(self, features):
        query_emb = self.query_tower(features)
        similarities = tf.matmul(query_emb, self.product_embeddings, transpose_b=True)
        top_scores, top_indices = tf.nn.top_k(similarities, k=100)
        return {'product_ids': tf.gather(self.product_ids, top_indices), 'scores': top_scores}
```

**This ServingModel:**
- ✅ No FactorizedTopK
- ✅ Pre-computed embeddings stored as tf.Variables
- ✅ Standard TF operations only
- ✅ Works with TF Serving and Vertex AI Endpoints

---

## Current TFX ServingModel Architecture

**Location:** `ml_platform/configs/services.py` (lines 2623-2680)

### Retrieval ServingModel

```python
class ServingModel(tf.keras.Model):
    """Wrapper model for serving that properly tracks all TFX Transform resources."""

    def __init__(self, retrieval_model, tf_transform_output, product_ids, product_embeddings):
        super().__init__()
        self.retrieval_model = retrieval_model

        # TFT layer contains all vocabularies (embedded in model)
        self.tft_layer = tf_transform_output.transform_features_layer()
        self._raw_feature_spec = tf_transform_output.raw_feature_spec()

        # Pre-computed embeddings (embedded in model)
        self.product_ids = tf.Variable(product_ids, trainable=False, name='product_ids')
        self.product_embeddings = tf.Variable(product_embeddings, trainable=False, name='product_embeddings')

    @tf.function(input_signature=[
        tf.TensorSpec(shape=[None], dtype=tf.string, name='examples')
    ])
    def serve(self, serialized_examples):
        # Parse serialized tf.Examples
        parsed_features = tf.io.parse_example(serialized_examples, self._raw_feature_spec)

        # Apply TFT preprocessing (uses embedded vocabularies)
        transformed_features = self.tft_layer(parsed_features)

        # Get query embeddings
        query_embeddings = self.retrieval_model.query_tower(transformed_features)

        # Brute-force similarity search
        similarities = tf.linalg.matmul(query_embeddings, self.product_embeddings, transpose_b=True)
        top_scores, top_indices = tf.nn.top_k(similarities, k=100)

        return {
            'product_ids': tf.gather(self.product_ids, top_indices),
            'scores': top_scores
        }
```

### Key Points

1. **Self-contained**: All vocabularies embedded via TFT layer, all embeddings pre-computed
2. **Serialized Examples input**: Standard TF Serving format
3. **No external dependencies**: No vocab files, no embedding files needed at inference
4. **ScaNN support**: Optional ScaNN index for faster ANN search (configured at training time)

### Model Types Supported

| Model Type | ServingModel Class | Signatures |
|------------|-------------------|------------|
| Retrieval | `ServingModel` | `serving_default` (top-K products) |
| Ranking | `RankingServingModel` | `serving_default` (predicted scores) |
| Multitask | `MultitaskServingModel` | `serving_default` (retrieval), `serve_ranking` (ranking) |

---

## Deployment Options Comparison

| Option | Infrastructure | Batching | Cost Model | Complexity |
|--------|---------------|----------|------------|------------|
| **Vertex AI Endpoints** | Managed | Automatic | Node-hours + predictions | Lowest |
| **Cloud Run + TF Serving** | Container | Automatic (TF Serving) | Per request, scale to zero | Low |
| **Cloud Run + FastAPI** | Container | Manual | Per request, scale to zero | Medium |
| **GKE + TF Serving** | Kubernetes | Automatic | Node-hours | High |

### Vertex AI Endpoints

**Pros:**
- Zero infrastructure code
- Auto-scaling, versioning, traffic splitting built-in
- Monitoring and logging built-in
- Managed TF Serving (Google handles everything)

**Cons:**
- Costs money even at low traffic (minimum node hours)
- Less control over serving configuration
- May have issues with custom model architectures (past experience)

**Cost:** ~$0.10/node-hour + $0.00005/prediction (varies by machine type)

### Cloud Run + TF Serving (RECOMMENDED)

**Pros:**
- Scale to zero (no cost when not in use)
- Pay per request only
- TF Serving handles batching automatically
- Full control over container configuration
- No custom serving code needed

**Cons:**
- Must build and manage container
- Cold start latency (first request after scale-down)
- Must configure batching parameters manually

**Cost:** ~$0.00001 per request + compute time (scale to zero = $0 when idle)

### Cloud Run + FastAPI

**Pros:**
- Full control over everything
- Simple raw tensor API
- Easy to debug

**Cons:**
- Must write and maintain serving code (~300 lines)
- Must implement batching manually
- No automatic optimizations

---

## Recommended Solution: Cloud Run + TF Serving

Given the requirements:
- Development phase (minimize costs)
- Scale to zero capability
- Automatic batching
- Minimal custom code

**Recommendation: Cloud Run + TensorFlow Serving**

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  TFX Pipeline (Vertex AI)                                           │
│       │                                                              │
│       ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Pusher Component                                             │   │
│  │   - Saves ServingModel to gs://bucket/pushed_model/         │   │
│  │   - Model is SELF-CONTAINED (vocabs + embeddings embedded)  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Vertex AI Model Registry (Optional but recommended)         │   │
│  │   - Register model version                                   │   │
│  │   - Track lineage (training run → model)                    │   │
│  │   - Store metrics as labels                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                              │
│       ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Cloud Run Deployment                                         │   │
│  │                                                              │   │
│  │   Container: TensorFlow Serving                              │   │
│  │   ┌─────────────────────────────────────────────────────┐   │   │
│  │   │ FROM tensorflow/serving:latest                      │   │   │
│  │   │ ENV MODEL_BASE_PATH=/models                         │   │   │
│  │   │ ENV MODEL_NAME=recommender                          │   │   │
│  │   │ # Model loaded from GCS at startup                  │   │   │
│  │   └─────────────────────────────────────────────────────┘   │   │
│  │                                                              │   │
│  │   Endpoints:                                                 │   │
│  │   - POST /v1/models/recommender:predict                     │   │
│  │                                                              │   │
│  │   Features:                                                  │   │
│  │   - Automatic batching                                       │   │
│  │   - Scale to zero                                           │   │
│  │   - Auto-scaling on load                                    │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Dockerfile

```dockerfile
FROM tensorflow/serving:2.15.0

# Environment variables for TF Serving
ENV MODEL_BASE_PATH=/models
ENV MODEL_NAME=recommender

# Batching configuration (optional)
COPY batching_config.txt /etc/tf_serving/batching_config.txt
ENV TF_SERVING_BATCHING_PARAMETERS_FILE=/etc/tf_serving/batching_config.txt

# The model will be loaded from GCS via MODEL_PATH environment variable
# Set at deployment time: --set-env-vars=MODEL_PATH=gs://bucket/pushed_model

# TF Serving entrypoint (built into base image)
# Serves on port 8501 (REST) and 8500 (gRPC)
```

### Batching Configuration

```text
# batching_config.txt
max_batch_size { value: 64 }
batch_timeout_micros { value: 10000 }
max_enqueued_batches { value: 100 }
num_batch_threads { value: 4 }
pad_variable_length_inputs: true
```

### Deployment Commands

```bash
# Build container
gcloud builds submit --tag gcr.io/${PROJECT_ID}/recommender-serving

# Deploy to Cloud Run
gcloud run deploy recommender-prod \
  --image=gcr.io/${PROJECT_ID}/recommender-serving \
  --port=8501 \
  --memory=4Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=10 \
  --set-env-vars="MODEL_PATH=gs://bucket/training-runs/47/pushed_model" \
  --allow-unauthenticated
```

### Client Code

```python
import requests
import tensorflow as tf

def get_recommendations(customer_id: str, city: str, revenue: float, timestamp: int):
    # Build tf.Example
    example = tf.train.Example(features=tf.train.Features(feature={
        'customer_id': tf.train.Feature(bytes_list=tf.train.BytesList(value=[customer_id.encode()])),
        'city': tf.train.Feature(bytes_list=tf.train.BytesList(value=[city.encode()])),
        'revenue': tf.train.Feature(float_list=tf.train.FloatList(value=[revenue])),
        'timestamp': tf.train.Feature(int64_list=tf.train.Int64List(value=[timestamp])),
    }))

    # Serialize
    serialized = example.SerializeToString()

    # Send to TF Serving
    response = requests.post(
        "https://recommender-prod-xxx.run.app/v1/models/recommender:predict",
        json={"instances": [{"b64": base64.b64encode(serialized).decode()}]}
    )

    return response.json()
```

---

## Vertex AI Model Registry

### What It Is

Vertex AI Model Registry is a centralized catalog for ML models:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VERTEX AI MODEL REGISTRY                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Model: "metro-recommender"                                         │
│  ├── Version 1 (2026-01-15)                                         │
│  │   ├── Artifacts: gs://bucket/training-runs/42/pushed_model      │
│  │   ├── Labels: {training_run_id: 42, recall_at_100: 0.47}        │
│  │   └── Status: Archived                                           │
│  │                                                                   │
│  ├── Version 2 (2026-01-18) ← DEPLOYED to Cloud Run                │
│  │   ├── Artifacts: gs://bucket/training-runs/45/pushed_model      │
│  │   ├── Labels: {training_run_id: 45, recall_at_100: 0.52}        │
│  │   └── Deployment: cloud-run/recommender-prod                     │
│  │                                                                   │
│  └── Version 3 (2026-01-20) ← BLESSED, pending deployment          │
│      ├── Artifacts: gs://bucket/training-runs/47/pushed_model      │
│      └── Labels: {training_run_id: 47, recall_at_100: 0.54}        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Benefits

| Benefit | Description |
|---------|-------------|
| **Version Control** | Track all model versions in one place |
| **Lineage Tracking** | Link models to training runs, datasets, experiments |
| **Labels & Metadata** | Store metrics, hyperparameters as searchable labels |
| **Deployment History** | See which version is deployed where |
| **Model Comparison** | Compare metrics across versions via UI/API |
| **Governance** | Audit trail, access control |

### Cost

**Model Registry itself is FREE.** You only pay for:
- GCS storage for model artifacts (you already pay this)
- API calls (free tier covers typical usage)

### Registration Code

```python
from google.cloud import aiplatform

def register_model(training_run):
    """Register a trained model in Vertex AI Model Registry."""

    aiplatform.init(project=PROJECT_ID, location=REGION)

    model = aiplatform.Model.upload(
        display_name=f"recommender-{training_run.id}",
        artifact_uri=f"gs://{BUCKET}/training-runs/{training_run.id}/pushed_model",
        serving_container_image_uri="tensorflow/serving:2.15.0",
        labels={
            "training_run_id": str(training_run.id),
            "model_type": training_run.model_type,
            "recall_at_100": str(training_run.recall_at_100),
            "is_blessed": str(training_run.is_blessed),
        }
    )

    # Update TrainingRun with registry info
    training_run.vertex_model_resource_name = model.resource_name
    training_run.vertex_model_name = model.display_name
    training_run.save()

    return model
```

---

## Implementation Plan

### Phase 1: Model Registry Integration

**Goal:** Register trained models in Vertex AI Model Registry after Pusher stage completes.

**Tasks:**
1. Add `register_model()` function to `ml_platform/training/services.py`
2. Call after successful pipeline completion (status=COMPLETED or NOT_BLESSED)
3. Update `TrainingRun` model with registry resource name
4. Add UI indicator showing model is registered

**Estimated effort:** 1-2 hours

### Phase 2: TF Serving Container

**Goal:** Create reusable TF Serving container for Cloud Run deployment.

**Tasks:**
1. Create `deploy/tf_serving/Dockerfile`
2. Create `deploy/tf_serving/batching_config.txt`
3. Add Cloud Build configuration for container
4. Test locally with a trained model

**Estimated effort:** 2-3 hours

### Phase 3: Deployment API

**Goal:** Add deployment functionality to Training page.

**Tasks:**
1. Add `deploy_to_cloud_run()` function to `ml_platform/training/services.py`
2. Create API endpoint `POST /api/training-runs/{id}/deploy/`
3. Add "Deploy" button to Training page UI
4. Support deployment to new or existing Cloud Run service
5. Update `TrainingRun` with deployment info (endpoint URL, deployed_at)

**Estimated effort:** 4-6 hours

### Phase 4: Deployment Management

**Goal:** Manage deployed models (undeploy, traffic management).

**Tasks:**
1. Add `undeploy()` function
2. Add revision management (deploy new model to same service)
3. Add deployment status tracking
4. Add health check monitoring

**Estimated effort:** 3-4 hours

---

## Reference Files

| File | Description |
|------|-------------|
| `past/recs/cloud_run_service/main.py` | Past FastAPI serving solution (reference) |
| `past/recs/trainer/main.py` | Past trainer with serving signature (reference) |
| `ml_platform/configs/services.py` | TFX module generator with ServingModel classes |
| `ml_platform/training/services.py` | TrainingService with deployment methods |
| `ml_platform/training/models.py` | TrainingRun model with deployment fields |

### Key Code Locations

**ServingModel classes:**
- Retrieval: `configs/services.py:2623-2680`
- Ranking: `configs/services.py:4108-4200`
- Multitask: `configs/services.py:5064-5200`

**Pre-computed embeddings:**
- `configs/services.py:2683-2739` (`_precompute_candidate_embeddings`)

**Model saving:**
- Retrieval: `configs/services.py:3743-3757`
- Ranking: `configs/services.py:4677-4691`
- Multitask: `configs/services.py:5843-5852`

**Existing deployment fields in TrainingRun:**
- `vertex_model_name`: Model name in registry
- `vertex_model_resource_name`: Full resource name
- `is_deployed`: Whether currently deployed
- `deployed_at`: Deployment timestamp
- `endpoint_resource_name`: Cloud Run service URL

---

## Open Questions

1. **Serving signature format:** Keep serialized tf.Examples (TF Serving standard) or change to raw tensors (simpler client)?
   - Recommendation: Keep serialized Examples for automatic batching support

2. **Model loading:** Bake model into container or load from GCS at startup?
   - Recommendation: Load from GCS (single container image for all models)

3. **Authentication:** Public endpoints or require authentication?
   - Recommendation: Start with authenticated (IAM), add public option later

4. **Cold start mitigation:** Minimum instances > 0 for production?
   - Recommendation: min-instances=0 for development, 1+ for production

---

## Summary

| Component | Technology | Status |
|-----------|------------|--------|
| Training Pipeline | TFX on Vertex AI | ✅ Implemented |
| ServingModel | TFX-generated wrapper | ✅ Implemented |
| Model Registry | Vertex AI Model Registry | 🔲 To implement |
| Serving Infrastructure | Cloud Run + TF Serving | 🔲 To implement |
| Deployment API | Django REST | 🔲 To implement |
| Deployment UI | React | 🔲 To implement |
