# Phase: Deployment Domain

## Document Purpose
This document provides detailed specifications for implementing the **Deployment** domain in the ML Platform. The Deployment domain handles model serving, version management, and production deployment.

**Last Updated**: 2026-01-31 (Endpoint View Modal with Results section and green/red header styling)

---

## Overview

### Purpose
The Deployment domain allows users to:
1. Deploy trained models to production
2. Manage model versions (rollback, traffic splitting)
3. Monitor serving performance
4. Access prediction API documentation

### Key Principle
**One-click deployment with easy rollback.** Users should be able to deploy a new model with a single click, and instantly roll back if issues arise.

### Output
- Model deployed to Cloud Run serving endpoint
- API endpoint URL for predictions
- Version history with rollback capability

---

## User Interface

### Deployment Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Model Deployment                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ CURRENT PRODUCTION                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ 🟢 LIVE: Training Run #46                                              │  │
│ │                                                                        │  │
│ │ Model:      config-042 (Large embeddings)                             │  │
│ │ Dataset:    Q4 2024 Training Data                                     │  │
│ │ Recall@100: 46.8%                                                     │  │
│ │ Deployed:   Nov 28, 2024 18:30 (6 hours ago)                          │  │
│ │                                                                        │  │
│ │ Endpoint:   https://model-serving-xxx.europe-central2.run.app         │  │
│ │             [Copy URL]                                                 │  │
│ │                                                                        │  │
│ │ Today:      12,450 predictions | Avg latency: 2.1ms | Errors: 0       │  │
│ │                                                                        │  │
│ │ [View Logs]  [API Docs]  [Health Check]                               │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ AVAILABLE FOR DEPLOYMENT                                                     │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ Training Run #47                                         ★ Better     │  │
│ │ config-042 (Large embeddings) | R@100: 47.2% (+0.4%)                  │  │
│ │ Completed: 2 hours ago                                                 │  │
│ │ [▶ Deploy]  [Compare with Current]                                    │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ VERSION HISTORY                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌──────────┬──────────────┬──────────┬─────────────────┬─────────────────┐  │
│ │ Version  │ Training Run │ R@100    │ Deployed        │ Status          │  │
│ ├──────────┼──────────────┼──────────┼─────────────────┼─────────────────┤  │
│ │ v3       │ Run #46      │ 46.8%    │ Nov 28, 18:30   │ 🟢 Current      │  │
│ │ v2       │ Run #45      │ 45.2%    │ Nov 21, 14:00   │ Available       │  │
│ │ v1       │ Run #42      │ 43.1%    │ Nov 14, 09:30   │ Available       │  │
│ └──────────┴──────────────┴──────────┴─────────────────┴─────────────────┘  │
│                                                                              │
│ [Rollback to v2]                                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Deploy Confirmation Dialog

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Deploy Model                                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ You are about to deploy:                                                     │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ Training Run #47                                                       │  │
│ │ Feature Config: config-042 (Large embeddings)                         │  │
│ │ Dataset: Q4 2024 Training Data (v3)                                   │  │
│ │ Recall@100: 47.2%                                                     │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ COMPARISON WITH CURRENT                                                      │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────┬───────────────────┬───────────────────┬────────────┐    │
│ │ Metric          │ Current (v3)      │ New (v4)          │ Change     │    │
│ ├─────────────────┼───────────────────┼───────────────────┼────────────┤    │
│ │ Recall@100      │ 46.8%             │ 47.2%             │ ↑ +0.4%    │    │
│ │ Recall@50       │ 39.2%             │ 39.8%             │ ↑ +0.6%    │    │
│ │ Recall@10       │ 18.9%             │ 19.2%             │ ↑ +0.3%    │    │
│ └─────────────────┴───────────────────┴───────────────────┴────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ DEPLOYMENT OPTIONS                                                           │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ● Immediate (100% traffic)                                                  │
│   Switch all traffic to new model immediately                                │
│                                                                              │
│ ○ Gradual rollout                                                           │
│   [10 ▼]% → [50 ▼]% → 100% over [1 hour ▼]                                  │
│   (requires Cloud Run traffic splitting)                                     │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ⚠️ The current model (v3) will remain available for instant rollback.       │
│                                                                              │
│                                                  [Cancel]  [▶ Deploy Now]   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Deployment Progress

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Deploying Model...                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────┐    │
│ │ ████████████████████████████████████░░░░░░░░░░░░░░░░░░░░░ 60%       │    │
│ └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│ ✅ Copying model artifacts to serving bucket                                │
│ ✅ Updating Cloud Run service configuration                                 │
│ 🔄 Deploying new revision...                                                │
│ ⏳ Running health checks                                                     │
│ ⏳ Switching traffic                                                         │
│                                                                              │
│ Estimated time remaining: ~1 minute                                          │
│                                                                              │
│                                                              [Cancel]        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### API Documentation View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Prediction API Documentation                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Base URL: https://model-serving-xxx.europe-central2.run.app                 │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ ENDPOINTS                                                                    │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ GET /health                                                            │  │
│ │ Health check endpoint                                                  │  │
│ │                                                                        │  │
│ │ Response:                                                              │  │
│ │ {                                                                      │  │
│ │   "status": "healthy",                                                 │  │
│ │   "model_version": "v4",                                               │  │
│ │   "training_run": 47                                                   │  │
│ │ }                                                                      │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ POST /recommend                                                        │  │
│ │ Get recommendations for a single customer                              │  │
│ │                                                                        │  │
│ │ Request:                                                               │  │
│ │ {                                                                      │  │
│ │   "customer_id": "C001234",                                            │  │
│ │   "top_k": 10                                                          │  │
│ │ }                                                                      │  │
│ │                                                                        │  │
│ │ Response:                                                              │  │
│ │ {                                                                      │  │
│ │   "customer_id": "C001234",                                            │  │
│ │   "recommendations": [                                                 │  │
│ │     {"product_id": "P5678", "score": 0.92},                            │  │
│ │     {"product_id": "P1234", "score": 0.87},                            │  │
│ │     ...                                                                │  │
│ │   ]                                                                    │  │
│ │ }                                                                      │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ POST /recommend-batch                                                  │  │
│ │ Get recommendations for multiple customers (max 1000)                  │  │
│ │                                                                        │  │
│ │ Request:                                                               │  │
│ │ {                                                                      │  │
│ │   "customer_ids": ["C001234", "C005678", ...],                         │  │
│ │   "top_k": 10                                                          │  │
│ │ }                                                                      │  │
│ │                                                                        │  │
│ │ Response:                                                              │  │
│ │ {                                                                      │  │
│ │   "results": [                                                         │  │
│ │     {"customer_id": "C001234", "recommendations": [...]},              │  │
│ │     ...                                                                │  │
│ │   ]                                                                    │  │
│ │ }                                                                      │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ AUTHENTICATION                                                               │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Include API key in header:                                                   │
│ Authorization: Bearer YOUR_API_KEY                                           │
│                                                                              │
│ [Generate API Key]  [View Existing Keys]                                    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ CODE EXAMPLES                                                                │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ [Python ▼]                                                                   │
│                                                                              │
│ ```python                                                                    │
│ import requests                                                              │
│                                                                              │
│ API_URL = "https://model-serving-xxx.europe-central2.run.app"               │
│ API_KEY = "your-api-key"                                                    │
│                                                                              │
│ response = requests.post(                                                   │
│     f"{API_URL}/recommend",                                                 │
│     json={"customer_id": "C001234", "top_k": 10},                           │
│     headers={"Authorization": f"Bearer {API_KEY}"}                          │
│ )                                                                            │
│                                                                              │
│ recommendations = response.json()["recommendations"]                         │
│ ```                                                                          │
│                                                                              │
│ [Copy Code]                                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### Django Models

```python
# ml_platform/models.py

class Deployment(models.Model):
    """
    Tracks a model deployment to production.
    """
    ml_model = models.ForeignKey('MLModel', on_delete=models.CASCADE, related_name='deployments')
    training_run = models.ForeignKey('TrainingRun', on_delete=models.PROTECT)

    # Version
    version = models.IntegerField()  # v1, v2, v3, etc.

    # Status
    STATUS_CHOICES = [
        ('deploying', 'Deploying'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('failed', 'Failed'),
        ('rolled_back', 'Rolled Back'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='deploying')

    # Cloud Run details
    cloud_run_service = models.CharField(max_length=255)
    cloud_run_revision = models.CharField(max_length=255, blank=True)
    endpoint_url = models.URLField()

    # Traffic allocation (for gradual rollouts)
    traffic_percent = models.IntegerField(default=100)

    # Model artifacts (copied to serving location)
    serving_model_path = models.CharField(max_length=500)

    # Metrics at deployment time (snapshot)
    recall_at_100 = models.FloatField(null=True, blank=True)
    recall_at_50 = models.FloatField(null=True, blank=True)
    recall_at_10 = models.FloatField(null=True, blank=True)

    # Timestamps
    deployed_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Who deployed
    deployed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    class Meta:
        ordering = ['-version']
        unique_together = ['ml_model', 'version']

    def save(self, *args, **kwargs):
        if not self.version:
            last_deploy = Deployment.objects.filter(ml_model=self.ml_model).order_by('-version').first()
            self.version = (last_deploy.version + 1) if last_deploy else 1
        super().save(*args, **kwargs)


class ServingMetrics(models.Model):
    """
    Tracks serving performance metrics (hourly aggregates).
    """
    deployment = models.ForeignKey(Deployment, on_delete=models.CASCADE, related_name='metrics')
    hour = models.DateTimeField()  # Start of the hour

    # Volume
    request_count = models.IntegerField(default=0)
    unique_customers = models.IntegerField(default=0)

    # Latency
    avg_latency_ms = models.FloatField(default=0)
    p50_latency_ms = models.FloatField(default=0)
    p95_latency_ms = models.FloatField(default=0)
    p99_latency_ms = models.FloatField(default=0)

    # Errors
    error_count = models.IntegerField(default=0)
    error_rate = models.FloatField(default=0)

    class Meta:
        ordering = ['-hour']
        unique_together = ['deployment', 'hour']


class APIKey(models.Model):
    """
    API keys for accessing the prediction endpoint.
    """
    ml_model = models.ForeignKey('MLModel', on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=255)
    key_hash = models.CharField(max_length=255)  # Hashed key
    key_prefix = models.CharField(max_length=8)  # First 8 chars for identification

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    def generate_key(self):
        """Generate a new API key. Returns the plain key (only shown once)."""
        import secrets
        key = secrets.token_urlsafe(32)
        self.key_prefix = key[:8]
        self.key_hash = self._hash_key(key)
        return key

    def _hash_key(self, key: str) -> str:
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()

    def verify_key(self, key: str) -> bool:
        return self._hash_key(key) == self.key_hash
```

---

## API Endpoints

### Deployment Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{model_id}/deployments/` | List deployments |
| POST | `/api/models/{model_id}/deployments/` | Create new deployment |
| GET | `/api/deployments/{deploy_id}/` | Get deployment details |
| POST | `/api/deployments/{deploy_id}/rollback/` | Rollback to this version |
| GET | `/api/deployments/{deploy_id}/metrics/` | Get serving metrics |

### API Keys

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{model_id}/api-keys/` | List API keys |
| POST | `/api/models/{model_id}/api-keys/` | Create API key |
| DELETE | `/api/api-keys/{key_id}/` | Revoke API key |

---

## Services

### Deployment Service

```python
# ml_platform/deployment/services.py

from google.cloud import run_v2
from google.cloud import storage

class DeploymentService:
    """
    Manages model deployments to Cloud Run.
    """

    def __init__(self, project_id: str, region: str):
        self.project_id = project_id
        self.region = region
        self.run_client = run_v2.ServicesClient()
        self.storage_client = storage.Client()

    def deploy_model(
        self,
        training_run: 'TrainingRun',
        ml_model: 'MLModel',
        traffic_percent: int = 100
    ) -> 'Deployment':
        """
        Deploy a trained model to Cloud Run.
        """
        # 1. Copy model artifacts to serving location
        serving_path = self._copy_model_to_serving(training_run)

        # 2. Update Cloud Run service
        revision = self._deploy_to_cloud_run(ml_model, serving_path)

        # 3. Create deployment record
        deployment = Deployment.objects.create(
            ml_model=ml_model,
            training_run=training_run,
            status='deploying',
            cloud_run_service=f"model-serving-{ml_model.id}",
            endpoint_url=f"https://model-serving-{ml_model.id}.{self.region}.run.app",
            serving_model_path=serving_path,
            recall_at_100=training_run.recall_at_100,
            recall_at_50=training_run.recall_at_50,
            recall_at_10=training_run.recall_at_10,
        )

        # 4. Wait for deployment and switch traffic
        self._wait_for_deployment(revision)
        self._switch_traffic(ml_model, revision, traffic_percent)

        # 5. Update status
        deployment.status = 'active'
        deployment.cloud_run_revision = revision
        deployment.deployed_at = timezone.now()
        deployment.save()

        # 6. Deactivate previous deployment
        self._deactivate_previous(ml_model, deployment)

        return deployment

    def _copy_model_to_serving(self, training_run: 'TrainingRun') -> str:
        """Copy model artifacts from training location to serving bucket."""
        source_path = training_run.artifacts.get('saved_model')
        dest_path = f"gs://{self.project_id}-serving/models/v{training_run.run_number}/"

        # Copy using gsutil or Storage API
        # ...

        return dest_path

    def _deploy_to_cloud_run(self, ml_model: 'MLModel', model_path: str) -> str:
        """Deploy new revision to Cloud Run."""
        service_name = f"model-serving-{ml_model.id}"

        # Update service with new model path
        request = run_v2.UpdateServiceRequest(
            service={
                "name": f"projects/{self.project_id}/locations/{self.region}/services/{service_name}",
                "template": {
                    "containers": [{
                        "image": f"gcr.io/{self.project_id}/model-serving:latest",
                        "env": [
                            {"name": "MODEL_PATH", "value": model_path},
                        ],
                        "resources": {
                            "limits": {"memory": "4Gi", "cpu": "2"}
                        }
                    }],
                    "scaling": {
                        "min_instance_count": 1,
                        "max_instance_count": 10
                    }
                }
            }
        )

        operation = self.run_client.update_service(request=request)
        result = operation.result()

        return result.latest_ready_revision

    def _switch_traffic(self, ml_model: 'MLModel', revision: str, percent: int):
        """Switch traffic to the new revision."""
        service_name = f"model-serving-{ml_model.id}"

        request = run_v2.UpdateServiceRequest(
            service={
                "name": f"projects/{self.project_id}/locations/{self.region}/services/{service_name}",
                "traffic": [
                    {"type_": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
                     "revision": revision,
                     "percent": percent}
                ]
            }
        )

        self.run_client.update_service(request=request)

    def rollback(self, deployment: 'Deployment') -> 'Deployment':
        """
        Rollback to a previous deployment.
        """
        # Reactivate the old deployment
        deployment.status = 'active'
        deployment.save()

        # Switch traffic to the old revision
        self._switch_traffic(
            deployment.ml_model,
            deployment.cloud_run_revision,
            100
        )

        # Deactivate the current deployment
        current = Deployment.objects.filter(
            ml_model=deployment.ml_model,
            status='active'
        ).exclude(id=deployment.id).first()

        if current:
            current.status = 'rolled_back'
            current.deactivated_at = timezone.now()
            current.save()

        return deployment

    def get_serving_metrics(self, deployment: 'Deployment') -> dict:
        """
        Get serving metrics from Cloud Monitoring.
        """
        # Query Cloud Monitoring API
        # ...
        pass


class HealthCheckService:
    """
    Performs health checks on deployed models.
    """

    def check_health(self, endpoint_url: str) -> dict:
        """Check if the serving endpoint is healthy."""
        try:
            response = requests.get(f"{endpoint_url}/health", timeout=10)
            return {
                "healthy": response.status_code == 200,
                "response": response.json() if response.ok else None,
                "latency_ms": response.elapsed.total_seconds() * 1000
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }

    def validate_predictions(self, endpoint_url: str, test_customers: list) -> dict:
        """
        Validate that the model returns sensible predictions.
        """
        try:
            response = requests.post(
                f"{endpoint_url}/recommend-batch",
                json={"customer_ids": test_customers, "top_k": 10},
                timeout=30
            )

            if response.ok:
                results = response.json()["results"]
                return {
                    "valid": True,
                    "customers_processed": len(results),
                    "all_have_recommendations": all(
                        len(r["recommendations"]) > 0 for r in results
                    )
                }
            else:
                return {"valid": False, "error": response.text}

        except Exception as e:
            return {"valid": False, "error": str(e)}
```

---

## Model Serving Service

The serving service is a FastAPI application deployed to Cloud Run:

```python
# model_serving/main.py

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import List, Optional
import tensorflow as tf
import numpy as np

app = FastAPI(title="Recommendation API")

# Global model instance
model = None
model_version = None

@app.on_event("startup")
async def load_model():
    global model, model_version
    model_path = os.environ["MODEL_PATH"]
    model = tf.saved_model.load(model_path)
    model_version = os.environ.get("MODEL_VERSION", "unknown")

# Request/Response models
class RecommendRequest(BaseModel):
    customer_id: str
    top_k: int = 10

class RecommendBatchRequest(BaseModel):
    customer_ids: List[str]
    top_k: int = 10

class Recommendation(BaseModel):
    product_id: str
    score: float

class RecommendResponse(BaseModel):
    customer_id: str
    recommendations: List[Recommendation]

# Endpoints
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model_version": model_version,
    }

@app.post("/recommend", response_model=RecommendResponse)
async def recommend(
    request: RecommendRequest,
    authorization: str = Header(...)
):
    """Get recommendations for a single customer."""
    # Validate API key
    if not validate_api_key(authorization):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get recommendations
    recommendations = get_recommendations(
        request.customer_id,
        request.top_k
    )

    return RecommendResponse(
        customer_id=request.customer_id,
        recommendations=recommendations
    )

@app.post("/recommend-batch")
async def recommend_batch(
    request: RecommendBatchRequest,
    authorization: str = Header(...)
):
    """Get recommendations for multiple customers."""
    if not validate_api_key(authorization):
        raise HTTPException(status_code=401, detail="Invalid API key")

    if len(request.customer_ids) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Maximum 1000 customers per batch"
        )

    results = []
    for customer_id in request.customer_ids:
        recommendations = get_recommendations(customer_id, request.top_k)
        results.append({
            "customer_id": customer_id,
            "recommendations": recommendations
        })

    return {"results": results}

def get_recommendations(customer_id: str, top_k: int) -> List[dict]:
    """
    Get top-k product recommendations for a customer.
    """
    # Create query embedding
    query_features = {"user_id": tf.constant([customer_id])}
    query_embedding = model.query_model(query_features)

    # Get scores for all candidates
    scores, product_ids = model.brute_force_index(query_embedding, k=top_k)

    # Format results
    recommendations = [
        {"product_id": pid.numpy().decode(), "score": float(score)}
        for pid, score in zip(product_ids[0], scores[0])
    ]

    return recommendations

def validate_api_key(auth_header: str) -> bool:
    """Validate the API key from Authorization header."""
    if not auth_header.startswith("Bearer "):
        return False

    key = auth_header[7:]
    # Validate against database or cached keys
    # ...
    return True
```

---

## Implementation Checklist

### Phase 1: Basic Deployment
- [x] Create Django models (DeployedEndpoint in `ml_platform/training/models.py`)
- [ ] Create deployment sub-app structure (using training app for now)
- [x] Implement basic deployment API (deployed-endpoints endpoints)
- [x] Create deployment dashboard UI (Serving Endpoints chapter)

### Phase 2: Cloud Run Integration
- [x] Implement DeploymentService (`deploy_to_cloud_run` in TrainingService)
- [x] Copy model artifacts to serving bucket (handled by TFX Pusher)
- [x] Update Cloud Run service (Python SDK `google-cloud-run`)
- [x] Delete Cloud Run service (`delete_cloud_run_service` method)
- [x] List Cloud Run services (`list_cloud_run_services` method)
- [ ] Traffic switching (future)

### Phase 3: Health & Monitoring
- [ ] Implement HealthCheckService
- [ ] Add health check UI
- [ ] Integrate with Cloud Monitoring
- [ ] Display serving metrics

### Phase 4: API Management
- [ ] Implement API key generation
- [ ] Add API key validation to serving
- [ ] Create API documentation page
- [ ] Code examples for different languages

### Phase 5: Rollback & Versioning
- [ ] Implement rollback functionality
- [ ] Version history UI
- [ ] Traffic splitting for gradual rollouts

---

## Dependencies on Other Domains

### Depends On
- **Training Domain**: Provides trained models for deployment
- **Experiments Domain**: Helps select best model

### Depended On By
- None (end of pipeline)

---

## Related Documentation

- [Implementation Overview](../implementation.md)
- [Training Phase](phase_training.md)
- [Experiments Phase](phase_experiments.md)

---

# Serving Endpoints Chapter (2026-01-29)

## Implementation Summary

The Serving Endpoints chapter displays all deployed ML serving endpoints (Cloud Run services with names ending in `-serving`) on the Deployment page. The UI follows the Models Registry chapter pattern from the Training page.

### Files Created/Modified

| File | Action | Purpose |
|------|--------|---------|
| `ml_platform/training/api.py` | Modified | Added 6 API functions + serializer |
| `ml_platform/training/urls.py` | Modified | Registered 6 new URL patterns |
| `ml_platform/training/services.py` | Modified | Added `delete_cloud_run_service()`, `redeploy_endpoint()`, `update_endpoint_config()`, `delete_endpoint_record()` methods |
| `templates/ml_platform/model_deployment.html` | Modified | Full chapter implementation |
| `static/js/endpoints_table.js` | Created | IIFE module for table management |
| `static/css/endpoints_table.css` | Created | Styles with `.endpoints-` prefix |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/deployed-endpoints/` | List endpoints with filters, pagination, KPIs |
| GET | `/api/deployed-endpoints/<id>/` | Get endpoint details |
| POST | `/api/deployed-endpoints/<id>/undeploy/` | Delete Cloud Run service, mark inactive |
| POST | `/api/deployed-endpoints/<id>/deploy/` | Re-deploy inactive endpoint with same config |
| PATCH | `/api/deployed-endpoints/<id>/config/` | Update config and redeploy (atomic) |
| DELETE | `/api/deployed-endpoints/<id>/delete/` | Delete endpoint record (only if inactive) |

### API Response Format (List)

```json
{
  "success": true,
  "endpoints": [{
    "id": 1,
    "service_name": "my-model-serving",
    "service_url": "https://...",
    "deployed_version": "v1",
    "is_active": true,
    "model_name": "my-model",
    "model_type": "retrieval",
    "registered_model_id": 123,
    "deployment_config": {"memory": "4Gi", "cpu": "2", ...},
    "updated_at": "2026-01-28T..."
  }],
  "kpi": {"total": 5, "active": 4, "inactive": 1, "last_updated": "..."},
  "pagination": {"page": 1, "page_size": 10, "total_count": 5, ...},
  "model_names": ["model-a", "model-b"]
}
```

### UI Features

**KPI Summary Row (4 cards):**
- Total Endpoints
- Active (green)
- Inactive (red)
- Last Updated (blue, relative time)

**Filter Bar:**
- Model Type dropdown (All, Retrieval, Ranking, Multitask)
- Status dropdown (All, Active, Inactive)
- Model Name dropdown (populated dynamically)
- Search input (debounced)

**Endpoints Table Columns:**
1. # (row number)
2. Endpoint Name (service name + run number)
3. Model (type badge + model name)
4. Version (badge with icon)
5. URL (truncated with copy button)
6. Config (CPU/Memory)
7. Status (Active/Inactive badge)
8. Last Updated (relative time)
9. Actions (icon buttons)

**Action Buttons (Updated 2026-01-31):**

The action buttons now use a **2×2 grid layout** matching the Models Registry on the Training page:

```
┌──────────────┬──────────────┐
│ Deploy/      │    View      │  ← Row 1: Gold + Green text buttons
│ Undeploy     │              │
├──────────────┼──────────────┤
│              │ [Edit][Del]  │  ← Row 2: Spacer + Icon button group
└──────────────┴──────────────┘
```

Uses shared CSS classes from `cards.css`:
- `.ml-card-col-actions`, `.ml-card-actions-grid`
- `.card-action-btn.deploy` (gold #c9a227)
- `.card-action-btn.view` (green #10b981)
- `.card-action-btn.icon-only.edit`, `.card-action-btn.icon-only.delete`
- `.card-action-btn-group` (groups Edit + Delete)

| Button | Active Endpoint | Inactive Endpoint |
|--------|-----------------|-------------------|
| **Deploy/Undeploy** | Shows "Undeploy" | Shows "Deploy" |
| **View** | Enabled (opens ExpViewModal) | Enabled |
| **Edit** | Enabled (opens config modal) | Disabled (grayed) |
| **Delete** | Disabled (grayed) | Enabled (removes DB record) |

**Edit Config Modal:**
- Preset cards (Development, Production, High Traffic)
- Advanced options (Memory, CPU, Min/Max Instances, Timeout)
- Warning about undeploy/redeploy process
- Applies changes via atomic undeploy + redeploy

### JavaScript Module: `EndpointsTable`

```javascript
// Usage
EndpointsTable.init({
    containerId: '#endpointsChapter',
    kpiContainerId: '#endpointsKpiSummary',
    filterBarId: '#endpointsFilterBar',
    tableContainerId: '#endpointsTable',
    emptyStateId: '#endpointsEmptyState',
    region: 'europe-central2',
    project: 'b2b-recs'
});
EndpointsTable.load();

// Public API
EndpointsTable.refresh()
EndpointsTable.setFilter(key, value)
EndpointsTable.handleSearch(value)
EndpointsTable.copyUrl(endpointId)
EndpointsTable.viewLogs(endpointId)
EndpointsTable.viewDetails(endpointId)
EndpointsTable.testEndpoint(endpointId)
EndpointsTable.confirmUndeploy(endpointId)
EndpointsTable.confirmDeploy(endpointId)   // Re-deploy inactive endpoint
EndpointsTable.confirmDelete(endpointId)   // Delete endpoint record
EndpointsTable.openEditModal(endpointId)   // Open config edit modal
EndpointsTable.closeEditModal()            // NEW: Close edit modal
EndpointsTable.selectPreset(presetName)    // NEW: Select config preset
EndpointsTable.toggleAdvancedOptions()     // NEW: Toggle advanced options
EndpointsTable.saveEndpointConfig()        // NEW: Save config changes
EndpointsTable.nextPage()
EndpointsTable.prevPage()
```

### Service Methods

```python
# ml_platform/training/services.py

def delete_cloud_run_service(self, service_name: str) -> bool:
    """Delete a Cloud Run service using Google Cloud Run Python SDK."""

def redeploy_endpoint(self, endpoint: DeployedEndpoint) -> str:
    """
    Re-deploy an inactive endpoint with its existing config.
    Returns new service URL.
    """

def update_endpoint_config(self, endpoint: DeployedEndpoint, new_config: dict) -> str:
    """
    Update endpoint configuration via atomic undeploy/redeploy.
    new_config can contain: memory, cpu, min_instances, max_instances, timeout
    Returns service URL after redeploy.
    """

def delete_endpoint_record(self, endpoint: DeployedEndpoint) -> bool:
    """
    Delete endpoint record from database.
    Only works for inactive endpoints.
    """
```

### Service Method Details: `delete_cloud_run_service`

```python
def delete_cloud_run_service(self, service_name: str) -> bool:
    """
    Delete a Cloud Run service using Google Cloud Run Python SDK.

    Args:
        service_name: Name of the Cloud Run service to delete

    Returns:
        bool: True if deletion was successful

    Raises:
        TrainingServiceError: If deletion fails
    """
```

---

# Cloud Run Python SDK Migration (2026-01-30)

## Bug Fix: gcloud CLI Not Available in Cloud Run Container

### Problem

When the Django app was deployed to Cloud Run and users tried to delete (undeploy) an endpoint, they received the error:

```
Failed to delete Cloud Run service: [Errno 2] No such file or directory: 'gcloud'
```

### Root Cause

Three functions in `ml_platform/training/services.py` were using `subprocess` to call the `gcloud` CLI:

1. `delete_cloud_run_service()` - Delete Cloud Run services
2. `list_cloud_run_services()` - List Cloud Run services
3. `deploy_to_cloud_run()` - Deploy models to Cloud Run

The Dockerfile (`python:3.12-slim` base image) does not include the Google Cloud SDK, so these commands fail when running inside the Cloud Run container.

### Solution

Replaced all `subprocess` + `gcloud` calls with the **Google Cloud Run Python SDK** (`google-cloud-run`), which was already in `requirements.txt`.

### Changes Made

| Function | Before | After |
|----------|--------|-------|
| `delete_cloud_run_service()` | `subprocess.run(['gcloud', 'run', 'services', 'delete', ...])` | `run_v2.ServicesClient().delete_service()` |
| `list_cloud_run_services()` | `subprocess.run(['gcloud', 'run', 'services', 'list', ...])` | `run_v2.ServicesClient().list_services()` |
| `deploy_to_cloud_run()` | `subprocess.run(['gcloud', 'run', 'deploy', ...])` | `run_v2.ServicesClient().update_service(allow_missing=True)` |

### Key Implementation Details

```python
from google.cloud import run_v2
from google.api_core import exceptions as google_exceptions

# Delete service
client = run_v2.ServicesClient()
service_path = f"projects/{project_id}/locations/{region}/services/{service_name}"
operation = client.delete_service(name=service_path)
operation.result(timeout=120)

# List services
for svc in client.list_services(parent=f"projects/{project_id}/locations/{region}"):
    name = svc.name.split('/')[-1]
    url = svc.uri
    # ...

# Deploy/update service (creates if not exists)
service = run_v2.Service(
    name=service_path,
    template=run_v2.RevisionTemplate(
        containers=[run_v2.Container(image=image, ports=[...], env=[...])],
        scaling=run_v2.RevisionScaling(min_instance_count=0, max_instance_count=10),
    ),
)
operation = client.update_service(service=service, allow_missing=True)
result = operation.result(timeout=300)
```

### Exception Handling

| gcloud subprocess | Python SDK |
|-------------------|------------|
| `subprocess.TimeoutExpired` | `google_exceptions.DeadlineExceeded` |
| Check stderr for "not found" | `google_exceptions.NotFound` |
| `result.returncode != 0` | Exception raised automatically |

### Testing

After redeploying the Django app to Cloud Run (`./deploy_django.sh`), the endpoint delete/undeploy functionality works correctly from the deployed application.

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Skip "Requests" KPI | Requires Cloud Monitoring integration; can add later |
| "Test" action as placeholder | Full testing feature documented below |
| Icon-only action buttons | Fits more actions in table row |
| 4 KPI cards (not 5) | Matches available data without Cloud Monitoring |
| Purple gradient icon (`#6366f1`) | Distinguishes from green (Models Registry) |
| Filter by model name | Useful when multiple models are deployed |

### Verification Steps

1. Navigate to `/models/<id>/deployment/`
2. Verify KPI cards show correct counts
3. Test all filters (Model Type, Status, Model Name, Search)
4. Verify table pagination
5. Test actions:
   - Copy URL: Check clipboard
   - View Logs: Opens GCP Console in new tab
   - View Details: Opens ExpViewModal
   - Undeploy: Shows confirmation, refreshes table

---

# Endpoint Testing & Validation (2026-01-29)

## Problem Statement

Models deployed to Cloud Run via TF Serving have never been validated end-to-end. We need a systematic way to:

1. Verify the deployed model accepts the expected input format
2. Confirm the model returns valid recommendations (product IDs + scores)
3. Measure inference latency and throughput
4. Provide confidence that the model works as trained

### Key Insight: Transform is Embedded

The `ServingModel` includes the TFT (TensorFlow Transform) layer with all vocabularies and normalization parameters embedded. This means:

- **No separate Transform step needed** when querying the endpoint
- **Raw feature values required** in the correct format (aliased column names)
- **Column names must match** the `FeatureConfig.buyer_model_features` display names

---

## Data Flow: Training vs Serving

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TRAINING TIME                                                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ Dataset Config (e.g., old_examples_chernigiv)                                │
│   • primary_table, secondary_tables                                          │
│   • column_aliases: {division_desc → category, mge_cat_desc → sub_category} │
│   • filters: date range, top products by revenue, etc.                       │
│                    │                                                          │
│                    ▼                                                          │
│ BigQueryExampleGen → TFRecords with aliased columns                          │
│                    │                                                          │
│                    ▼                                                          │
│ Transform Component (FeatureConfig preprocessing_fn)                          │
│   → Vocabularies, normalization, bucketization, cyclical encoding            │
│                    │                                                          │
│                    ▼                                                          │
│ Trainer → TFRS Two-Tower Model                                               │
│                    │                                                          │
│                    ▼                                                          │
│ Pusher → SavedModel with embedded TFT layer + product embeddings             │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ SERVING TIME                                                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ Client Request (JSON):                                                        │
│   {                                                                          │
│     "instances": [{                                                          │
│       "customer_id": "CUST123",                                              │
│       "category": "Electronics",         ← Aliased column names              │
│       "sub_category": "Laptops",                                             │
│       "revenue": 5000.0,                                                     │
│       "date": 1704067200                 ← Unix timestamp (INT64)            │
│     }]                                                                       │
│   }                                                                          │
│                    │                                                          │
│                    ▼                                                          │
│ ServingModel.serve():                                                        │
│   1. Apply TFT layer (vocab lookup, normalization)                           │
│   2. Get query embedding from buyer tower                                    │
│   3. Compute similarities with pre-computed product embeddings               │
│   4. Return top-100 product_ids + scores                                     │
│                    │                                                          │
│                    ▼                                                          │
│ Response: {"predictions": [{"product_ids": [...], "scores": [...]}]}         │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Endpoint Testing Service Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ENDPOINT TESTING SERVICE                                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ ┌─────────────────────────────────────────────────────────────────────────┐  │
│ │ 1. Test Data Generator                                                   │  │
│ │    • Input: dataset_id, feature_config_id, sample_count                 │  │
│ │    • Action: Query BigQuery using Dataset config (same as ExampleGen)   │  │
│ │    • Output: List of raw feature dicts ready for model input            │  │
│ └─────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                      │
│                                        ▼                                      │
│ ┌─────────────────────────────────────────────────────────────────────────┐  │
│ │ 2. Endpoint Caller                                                       │  │
│ │    • Input: endpoint_url, test_data                                     │  │
│ │    • Action: POST /v1/models/recommender:predict                        │  │
│ │    • Output: {predictions, latency, status}                             │  │
│ └─────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                      │
│                                        ▼                                      │
│ ┌─────────────────────────────────────────────────────────────────────────┐  │
│ │ 3. Response Validator                                                    │  │
│ │    • Validates: product_ids exists, scores are floats, count matches k  │  │
│ │    • Optional: Cross-reference product_ids against known product table  │  │
│ │    • Output: {valid: bool, issues: [], stats: {}}                       │  │
│ └─────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                      │
│                                        ▼                                      │
│ ┌─────────────────────────────────────────────────────────────────────────┐  │
│ │ 4. Results Report                                                        │  │
│ │    • Success rate, average latency, score distributions                 │  │
│ │    • Sample recommendations for review                                  │  │
│ │    • Comparison with expected behavior (if baseline exists)             │  │
│ └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: CLI Script (Quick Testing)

**File:** `scripts/test_deployed_endpoint.py`

A standalone script for immediate endpoint validation:

```bash
python scripts/test_deployed_endpoint.py \
  --endpoint-url="https://chern-retriv-v5-serving-555035914949.europe-central2.run.app" \
  --dataset-id=14 \
  --feature-config-id=9 \
  --sample-count=10
```

**Output:**
```
Endpoint Test Results
=====================
Endpoint: https://chern-retriv-v5-serving-...
Dataset: old_examples_chernigiv
Feature Config: chern_v2

Health Check: PASSED
Requests Sent: 10
Successful: 10
Failed: 0

Latency (ms):
  Avg: 245
  Min: 180
  Max: 320

Validation: ALL PASSED
  - All responses have product_ids (100 items each)
  - All responses have scores (sorted descending)

Sample Prediction:
  Input: {"customer_id": "12345", "category": "Electronics", ...}
  Top 5 Products: ["PROD001", "PROD002", "PROD003", "PROD004", "PROD005"]
  Top 5 Scores: [0.95, 0.87, 0.82, 0.79, 0.75]
```

### Phase 2: Django API Endpoint

**Endpoint:** `POST /api/deployed-endpoints/{id}/test/`

**Request:**
```json
{
  "sample_count": 10,
  "timeout_seconds": 30,
  "batch_size": 1
}
```

**Response:**
```json
{
  "success": true,
  "endpoint_url": "https://chern-retriv-v5-serving-...",
  "test_config": {
    "dataset": "old_examples_chernigiv",
    "feature_config": "chern_v2",
    "sample_count": 10
  },
  "health_check": {
    "healthy": true,
    "status_code": 200
  },
  "test_results": {
    "requests_sent": 10,
    "successful": 10,
    "failed": 0,
    "avg_latency_ms": 245,
    "min_latency_ms": 180,
    "max_latency_ms": 320
  },
  "validation": {
    "all_valid": true,
    "valid_count": 10,
    "total_count": 10,
    "issues": []
  },
  "sample_predictions": [
    {
      "input": {"customer_id": "12345", "category": "Electronics", ...},
      "output": {
        "product_ids": ["PROD001", "PROD002", ...],
        "scores": [0.95, 0.87, ...]
      }
    }
  ]
}
```

### Phase 3: UI Integration

Add a "Test Endpoint" button to:
- Training page (on deployed model cards)
- Models Registry page (on endpoint entries)

**Modal Features:**
- Configuration options (sample count, timeout)
- Real-time progress indicator
- Results display with sample predictions
- Export results as JSON

### Phase 4: Scheduled Health Checks

**Cloud Scheduler Job:**
- Run every 15 minutes for production endpoints
- Alert on failures via Cloud Monitoring
- Store results in `EndpointTestResult` model

---

## Component Specifications

### Component 1: EndpointTestDataExtractor

Extracts test data from BigQuery using the same query logic as training.

```python
class EndpointTestDataExtractor:
    """
    Extract test data from BigQuery using the same query logic as training,
    but formatted for endpoint inference.
    """

    def __init__(self, dataset: Dataset, feature_config: FeatureConfig):
        self.dataset = dataset
        self.feature_config = feature_config
        self.bq_service = BigQueryService(dataset.model_endpoint, dataset)

    def get_buyer_feature_columns(self) -> List[str]:
        """Get list of buyer feature column names (aliased)."""
        return [
            f.get('display_name') or f.get('column')
            for f in self.feature_config.buyer_model_features
        ]

    def get_input_schema(self) -> Dict[str, str]:
        """Get the expected input schema with types."""
        schema = {}
        for feature in self.feature_config.buyer_model_features:
            col_name = feature.get('display_name') or feature.get('column')
            bq_type = feature.get('bq_type', 'STRING')
            schema[col_name] = bq_type
        return schema

    def extract_test_samples(self, count: int = 10) -> List[Dict]:
        """
        Query BigQuery for raw test data.
        Returns list of dicts matching the model's input signature.
        """
        buyer_cols = self.get_buyer_feature_columns()
        query = self._build_test_query(buyer_cols, count)
        results = self.bq_service.execute_query(query)
        return self._format_for_inference(results)

    def _build_test_query(self, columns: List[str], limit: int) -> str:
        """Build a simple SELECT query for test data."""
        base_query = self.bq_service.generate_query(
            self.dataset,
            for_tfx=True  # Ensures TIMESTAMP → INT64 conversion
        )
        return f"""
        WITH base AS ({base_query})
        SELECT {', '.join(columns)}
        FROM base
        ORDER BY RAND()
        LIMIT {limit}
        """

    def _format_for_inference(self, rows) -> List[Dict]:
        """Format BQ results for TF Serving input."""
        formatted = []
        for row in rows:
            instance = {}
            for feature in self.feature_config.buyer_model_features:
                col_name = feature.get('display_name') or feature.get('column')
                bq_type = feature.get('bq_type', 'STRING')
                value = row.get(col_name)

                # Convert to expected type
                if bq_type in ('TIMESTAMP', 'DATETIME'):
                    instance[col_name] = int(value) if value else 0
                elif bq_type in ('FLOAT64', 'FLOAT', 'NUMERIC'):
                    instance[col_name] = float(value) if value else 0.0
                elif bq_type in ('INT64', 'INTEGER'):
                    instance[col_name] = int(value) if value else 0
                else:
                    instance[col_name] = str(value) if value else ""

            formatted.append(instance)
        return formatted
```

### Component 2: EndpointTester

Sends requests to the deployed endpoint and measures performance.

```python
class EndpointTester:
    """Test a deployed TF Serving endpoint."""

    def __init__(self, endpoint_url: str, model_name: str = 'recommender'):
        self.endpoint_url = endpoint_url.rstrip('/')
        self.model_name = model_name
        self.predict_url = f"{self.endpoint_url}/v1/models/{model_name}:predict"
        self.status_url = f"{self.endpoint_url}/v1/models/{model_name}"

    def health_check(self) -> Dict:
        """Check if the endpoint is healthy."""
        try:
            resp = requests.get(self.status_url, timeout=10)
            return {
                "healthy": resp.status_code == 200,
                "status_code": resp.status_code,
                "response": resp.json() if resp.ok else resp.text
            }
        except requests.RequestException as e:
            return {
                "healthy": False,
                "status_code": None,
                "error": str(e)
            }

    def predict(self, instances: List[Dict], timeout: int = 30) -> Dict:
        """Send prediction request and measure latency."""
        start = time.time()

        try:
            resp = requests.post(
                self.predict_url,
                json={"instances": instances},
                timeout=timeout
            )
            latency_ms = (time.time() - start) * 1000

            return {
                "success": resp.ok,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "predictions": resp.json().get('predictions') if resp.ok else None,
                "error": resp.text if not resp.ok else None
            }
        except requests.RequestException as e:
            return {
                "success": False,
                "status_code": None,
                "latency_ms": (time.time() - start) * 1000,
                "predictions": None,
                "error": str(e)
            }

    def run_test_suite(
        self,
        test_data: List[Dict],
        batch_size: int = 1,
        timeout: int = 30
    ) -> Dict:
        """Run full test suite with multiple requests."""
        results = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "latencies": [],
            "predictions": [],
            "errors": []
        }

        for i in range(0, len(test_data), batch_size):
            batch = test_data[i:i+batch_size]
            result = self.predict(batch, timeout=timeout)

            results["total_requests"] += 1
            if result["success"]:
                results["successful"] += 1
                results["latencies"].append(result["latency_ms"])
                results["predictions"].append({
                    "input": batch,
                    "output": result["predictions"]
                })
            else:
                results["failed"] += 1
                results["errors"].append({
                    "input": batch,
                    "error": result["error"],
                    "status_code": result["status_code"]
                })

        # Calculate statistics
        if results["latencies"]:
            results["avg_latency_ms"] = sum(results["latencies"]) / len(results["latencies"])
            results["min_latency_ms"] = min(results["latencies"])
            results["max_latency_ms"] = max(results["latencies"])
            results["p50_latency_ms"] = sorted(results["latencies"])[len(results["latencies"]) // 2]
            results["p95_latency_ms"] = sorted(results["latencies"])[int(len(results["latencies"]) * 0.95)]

        return results
```

### Component 3: ResponseValidator

Validates that prediction responses match the expected format.

```python
class ResponseValidator:
    """Validate prediction responses."""

    def __init__(self, expected_k: int = 100):
        self.expected_k = expected_k

    def validate(self, predictions: List[Dict]) -> Dict:
        """Validate prediction format and content."""
        issues = []
        valid_count = 0

        for i, pred in enumerate(predictions):
            pred_issues = self._validate_single(pred)

            if pred_issues:
                issues.append({"prediction_index": i, "issues": pred_issues})
            else:
                valid_count += 1

        return {
            "all_valid": len(issues) == 0,
            "valid_count": valid_count,
            "total_count": len(predictions),
            "issues": issues
        }

    def _validate_single(self, pred: Dict) -> List[str]:
        """Validate a single prediction."""
        issues = []

        # Check product_ids exists and is correct format
        if 'product_ids' not in pred:
            issues.append("Missing 'product_ids' field")
        elif not isinstance(pred['product_ids'], list):
            issues.append("'product_ids' is not a list")
        elif len(pred['product_ids']) != self.expected_k:
            issues.append(f"Expected {self.expected_k} products, got {len(pred['product_ids'])}")

        # Check scores exists and is correct format
        if 'scores' not in pred:
            issues.append("Missing 'scores' field")
        elif not isinstance(pred['scores'], list):
            issues.append("'scores' is not a list")
        elif 'product_ids' in pred and len(pred.get('scores', [])) != len(pred.get('product_ids', [])):
            issues.append("Scores and product_ids length mismatch")

        # Check scores are valid and sorted
        if 'scores' in pred and isinstance(pred['scores'], list) and len(pred['scores']) > 0:
            if not all(isinstance(s, (int, float)) for s in pred['scores']):
                issues.append("Scores contain non-numeric values")
            elif pred['scores'] != sorted(pred['scores'], reverse=True):
                issues.append("Scores not sorted in descending order")

        return issues
```

### Component 4: Test Orchestrator

Combines all components into a single test flow.

```python
def test_deployed_endpoint(
    endpoint_url: str,
    dataset_id: int,
    feature_config_id: int,
    sample_count: int = 10,
    batch_size: int = 1,
    timeout: int = 30
) -> Dict:
    """
    Complete endpoint test flow.

    Args:
        endpoint_url: Full URL of the deployed endpoint
        dataset_id: ID of the Dataset used for training
        feature_config_id: ID of the FeatureConfig used for training
        sample_count: Number of test samples to generate
        batch_size: Number of instances per request
        timeout: Request timeout in seconds

    Returns:
        Comprehensive test report dict
    """
    from ml_platform.models import Dataset, FeatureConfig

    # Load configs
    dataset = Dataset.objects.get(id=dataset_id)
    feature_config = FeatureConfig.objects.get(id=feature_config_id)

    # Initialize components
    extractor = EndpointTestDataExtractor(dataset, feature_config)
    tester = EndpointTester(endpoint_url)
    validator = ResponseValidator(expected_k=100)

    # Health check first
    health = tester.health_check()
    if not health["healthy"]:
        return {
            "success": False,
            "error": "Endpoint health check failed",
            "health_check": health
        }

    # Extract test data
    try:
        test_data = extractor.extract_test_samples(sample_count)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to extract test data: {str(e)}",
            "health_check": health
        }

    # Run predictions
    results = tester.run_test_suite(test_data, batch_size=batch_size, timeout=timeout)

    # Validate responses
    all_predictions = []
    for p in results["predictions"]:
        if p["output"]:
            all_predictions.extend(p["output"])

    validation = validator.validate(all_predictions)

    # Build report
    return {
        "success": results["failed"] == 0 and validation["all_valid"],
        "endpoint_url": endpoint_url,
        "test_config": {
            "dataset_id": dataset_id,
            "dataset_name": dataset.name,
            "feature_config_id": feature_config_id,
            "feature_config_name": feature_config.name,
            "sample_count": sample_count,
            "batch_size": batch_size
        },
        "input_schema": extractor.get_input_schema(),
        "health_check": health,
        "test_results": {
            "requests_sent": results["total_requests"],
            "successful": results["successful"],
            "failed": results["failed"],
            "avg_latency_ms": results.get("avg_latency_ms"),
            "min_latency_ms": results.get("min_latency_ms"),
            "max_latency_ms": results.get("max_latency_ms"),
            "p50_latency_ms": results.get("p50_latency_ms"),
            "p95_latency_ms": results.get("p95_latency_ms")
        },
        "validation": validation,
        "errors": results.get("errors", []),
        "sample_predictions": results["predictions"][:3]
    }
```

---

## Database Model

### EndpointTestResult (New Model)

Stores test results for historical tracking.

```python
class EndpointTestResult(models.Model):
    """Stores endpoint test results for tracking."""

    deployed_endpoint = models.ForeignKey(
        'DeployedEndpoint',
        on_delete=models.CASCADE,
        related_name='test_results'
    )

    # Test configuration
    dataset = models.ForeignKey('Dataset', on_delete=models.SET_NULL, null=True)
    feature_config = models.ForeignKey('FeatureConfig', on_delete=models.SET_NULL, null=True)
    sample_count = models.PositiveIntegerField()

    # Results
    success = models.BooleanField()
    requests_sent = models.PositiveIntegerField()
    requests_succeeded = models.PositiveIntegerField()
    requests_failed = models.PositiveIntegerField()

    # Latency metrics (ms)
    avg_latency_ms = models.FloatField(null=True)
    min_latency_ms = models.FloatField(null=True)
    max_latency_ms = models.FloatField(null=True)
    p50_latency_ms = models.FloatField(null=True)
    p95_latency_ms = models.FloatField(null=True)

    # Validation
    all_responses_valid = models.BooleanField()
    validation_issues = models.JSONField(default=list)

    # Full results (JSON)
    full_results = models.JSONField(default=dict)

    # Metadata
    triggered_by = models.CharField(max_length=50)  # 'manual', 'api', 'scheduled'
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['deployed_endpoint', '-created_at']),
            models.Index(fields=['success', '-created_at']),
        ]
```

---

## Manual Testing Guide

For immediate testing before the service is built:

### Step 1: Get Input Schema

```python
# Django shell
from ml_platform.models import FeatureConfig

fc = FeatureConfig.objects.get(name='chern_v2')
for f in fc.buyer_model_features:
    print(f"{f.get('display_name') or f.get('column')}: {f.get('bq_type')}")
```

### Step 2: Query Sample Data

```sql
-- Replace column names with actual buyer features from Step 1
SELECT
  customer_id,
  category,
  sub_category,
  revenue,
  UNIX_SECONDS(CAST(date AS TIMESTAMP)) as date
FROM `b2b-recs.raw_data.transactions` t
LEFT JOIN `b2b-recs.raw_data.products` p ON t.product_id = p.product_id
LIMIT 5
```

### Step 3: Test Endpoint

```bash
# Health check
curl "https://chern-retriv-v5-serving-555035914949.europe-central2.run.app/v1/models/recommender"

# Prediction request
curl -X POST \
  "https://chern-retriv-v5-serving-555035914949.europe-central2.run.app/v1/models/recommender:predict" \
  -H "Content-Type: application/json" \
  -d '{
    "instances": [
      {
        "customer_id": "12345",
        "category": "Electronics",
        "sub_category": "Laptops",
        "revenue": 5000.0,
        "date": 1704067200
      }
    ]
  }'
```

### Step 4: Verify Response

Expected format:
```json
{
  "predictions": [
    {
      "product_ids": ["PROD001", "PROD002", ...],
      "scores": [0.95, 0.87, ...]
    }
  ]
}
```

Validation checklist:
- [ ] Response status is 200
- [ ] `predictions` array exists
- [ ] Each prediction has `product_ids` (100 items)
- [ ] Each prediction has `scores` (100 items)
- [ ] Scores are sorted descending
- [ ] Product IDs are valid strings

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 404 Not Found | Model name mismatch | Check `MODEL_NAME` env var in Cloud Run |
| 400 Bad Request | Input schema mismatch | Verify column names match FeatureConfig |
| 500 Internal Error | Transform failure | Check model signature vs input types |
| Cold start timeout | Scale-to-zero + large model | Increase `min_instances` to 1 |
| Wrong product IDs | Model not properly saved | Verify `pushed_model` path has correct version |

### Debugging Commands

```bash
# Check Cloud Run service status
gcloud run services describe chern-retriv-v5-serving --region=europe-central2

# View service logs
gcloud run services logs read chern-retriv-v5-serving --region=europe-central2 --limit=50

# Check model signature
saved_model_cli show --dir=/path/to/model --all
```

---

## Endpoint Testing Roadmap

1. **Phase 1** (Current): CLI script for manual testing
2. **Phase 2**: Django API endpoint + test history storage
3. **Phase 3**: UI integration (Test button on deployed models)
4. **Phase 4**: Scheduled health checks with alerting
5. **Phase 5**: Load testing support (concurrent requests, throughput measurement)

---

# Endpoint View Modal (2026-01-31)

## Overview

The Endpoint View Modal provides a styled, tabbed interface for viewing endpoint details, replacing the basic alert dialog. It reuses the existing `ExpViewModal` component with a new `endpoint` mode.

### Modal Design

```
┌─────────────────────────────────────────────────────────────┐
│ Header: [Endpoint Name]    [Status Badge: ACTIVE/INACTIVE]  │
│         Green/red gradient                    [Check/Pause icon] │
├─────────────────────────────────────────────────────────────┤
│ [Overview] [Test] [Logs] [Versions]  ← Tab buttons          │
├─────────────────────────────────────────────────────────────┤
│ OVERVIEW TAB:                                               │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ RESULTS                                                  │ │
│ │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │ │
│ │ │  RMSE   │ │   MAE   │ │Test RMSE│ │Test MAE │        │ │
│ │ │  0.53   │ │  0.36   │ │  0.53   │ │  0.36   │        │ │
│ │ └─────────┘ └─────────┘ └─────────┘ └─────────┘        │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Service URL: https://xxx.run.app  [Copy]                │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ MODEL INFORMATION                                        │ │
│ │ Model: chern_hybrid_v1  |  Type: Retrieval               │ │
│ │ Version: v2  |  Run #: 47                                │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ HARDWARE CONFIGURATION                                   │ │
│ │ Memory: 4Gi  |  CPU: 2  |  Min: 0  |  Max: 10           │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                                              [Close]        │
└─────────────────────────────────────────────────────────────┘
```

### Tab Contents

| Tab | Content |
|-----|---------|
| **Overview** | **Results** (4 metric cards: RMSE/MAE/Test RMSE/Test MAE for ranking, Recall@5/10/50/100 for retrieval, R@50/R@100/Test RMSE/Test MAE for multitask), Service URL with copy button, Model info (name, type, version, run#), Hardware config (memory, CPU, instances) |
| **Test** | Placeholder with "Coming Soon" message |
| **Logs** | Placeholder with GCP Console link (opens in new tab) |
| **Versions** | Last 5 model versions with metrics tablets (reuses existing `renderVersionsTab`) |

### Header Styling

| Status | Gradient | Icon |
|--------|----------|------|
| Active | Green (`#dceade` → `#b2d4b7`) - matches registered model style | Checkmark (`fa-check`) |
| Inactive | Red (`#fee2e2` → `#fecaca`) - matches failed status style | Pause (`fa-pause`) |

## Files Modified

| File | Changes |
|------|---------|
| `ml_platform/training/api.py` | Added `endpoint_versions()` API endpoint |
| `ml_platform/training/urls.py` | Added URL route for versions endpoint |
| `templates/includes/_exp_view_modal.html` | Added Test and Logs tab buttons + content containers |
| `templates/ml_platform/model_deployment.html` | Added CSS, HTML include, and JS for ExpViewModal |
| `static/css/exp_view_modal.css` | Added `endpoint-mode` CSS classes |
| `static/js/exp_view_modal.js` | Added endpoint mode functions, state, exports |
| `static/js/endpoints_table.js` | Updated `viewDetails()` to call `openForEndpoint()` |

## API Endpoint

### GET `/api/deployed-endpoints/<id>/`

Returns detailed information about a specific deployed endpoint, including metrics from the deployed training run.

**Response:**
```json
{
  "success": true,
  "endpoint": {
    "id": 1,
    "service_name": "chern-rank-v4-serving",
    "service_url": "https://...",
    "deployed_version": "v4",
    "is_active": true,
    "model_name": "chern_rank_v4",
    "model_type": "ranking",
    "training_run_id": 47,
    "run_number": 47,
    "deployment_config": {"memory": "4Gi", "cpu": "2"},
    "metrics": {
      "rmse": 0.53,
      "mae": 0.36,
      "test_rmse": 0.53,
      "test_mae": 0.36
    },
    "created_at": "...",
    "updated_at": "..."
  }
}
```

**Metrics by model type:**
- **Ranking**: `rmse`, `mae`, `test_rmse`, `test_mae`
- **Retrieval**: `recall_at_5`, `recall_at_10`, `recall_at_50`, `recall_at_100`
- **Multitask**: All of the above (displayed as R@50, R@100, Test RMSE, Test MAE)

### GET `/api/deployed-endpoints/<id>/versions/`

Returns last 5 model versions for the endpoint's registered model.

**Response:**
```json
{
  "success": true,
  "model_name": "chern_hybrid_v1",
  "versions": [
    {
      "id": 123,
      "vertex_model_version": 2,
      "run_number": 47,
      "registered_at": "2026-01-30T...",
      "metrics": {
        "recall_at_5": 0.18,
        "recall_at_10": 0.25,
        "recall_at_50": 0.42,
        "recall_at_100": 0.48
      },
      "model_status": "deployed",
      "deployed_endpoint_info": {...}
    },
    ...
  ]
}
```

## JavaScript API

### New Functions

| Function | Description |
|----------|-------------|
| `ExpViewModal.openForEndpoint(endpointId)` | Entry point - fetches endpoint data and opens modal |
| `ExpViewModal.openWithEndpointData(endpoint)` | Opens modal with provided endpoint object |
| `ExpViewModal.getCurrentEndpoint()` | Returns current endpoint state |

### State Updates

```javascript
let state = {
    mode: 'endpoint',  // New mode added
    endpointId: null,
    currentEndpoint: null,
    // ... existing state
};
```

### Mode-Specific Tab Handling

```javascript
// In updateVisibleTabs()
if (state.mode === 'endpoint') {
    visibleTabs = ['overview', 'test', 'logs', 'versions'];
}

// In switchTab()
if (state.mode === 'endpoint') {
    if (tabName === 'test') renderEndpointTestTab();
    if (tabName === 'logs') renderEndpointLogsTab(endpoint);
    if (tabName === 'versions') loadEndpointVersions(endpoint.id);
}
```

## CSS Classes

### Header Classes
- `.exp-view-header.endpoint-mode.active` - Green gradient (matches registered model style)
- `.exp-view-header.endpoint-mode.inactive` - Red gradient (matches failed status style)
- `.exp-view-endpoint-name-text` - Large endpoint name
- `.exp-view-endpoint-status-inline.active/.inactive` - Status badge (green/red)

### Status Icons
- `.exp-view-status-icon.endpoint-active` - Green background (`#16a34a`)
- `.exp-view-status-icon.endpoint-inactive` - Red background (`#dc2626`)

### Content Classes
- `.exp-view-endpoint-url-section` - URL container with copy button
- `.exp-view-endpoint-info-card` - Information cards
- `.exp-view-endpoint-info-grid` - 2-column grid layout
- `.exp-view-endpoint-placeholder` - Placeholder for Test/Logs tabs

## Usage

The modal is triggered when clicking "View" on any endpoint in the Serving Endpoints table:

```javascript
// In endpoints_table.js
function viewDetails(endpointId) {
    if (typeof ExpViewModal !== 'undefined' &&
        typeof ExpViewModal.openForEndpoint === 'function') {
        ExpViewModal.openForEndpoint(endpointId);
    } else {
        // Fallback to alert
    }
}
```

## Template Requirements

The deployment page must include:

```html
<!-- CSS (load modals.css BEFORE exp_view_modal.css for proper cascade) -->
<link rel="stylesheet" href="{% static 'css/modals.css' %}?v=2">
<link rel="stylesheet" href="{% static 'css/exp_view_modal.css' %}?v=2">

<!-- HTML component -->
{% include 'includes/_exp_view_modal.html' %}

<!-- JavaScript (load BEFORE endpoints_table.js) -->
<script src="{% static 'js/exp_view_modal.js' %}?v=2"></script>
<script src="{% static 'js/endpoints_table.js' %}?v=5"></script>
```

## Future Enhancements

1. **Test Tab**: Interactive endpoint testing with sample requests
2. **Logs Tab**: Embedded log viewer instead of external link
3. **Metrics Tab**: Real-time serving metrics from Cloud Monitoring
4. **Actions**: Deploy/Undeploy buttons within modal
