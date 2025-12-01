# Phase: Deployment Domain

## Document Purpose
This document provides detailed specifications for implementing the **Deployment** domain in the ML Platform. The Deployment domain handles model serving, version management, and production deployment.

**Last Updated**: 2025-12-01

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
- [ ] Create Django models (Deployment, ServingMetrics, APIKey)
- [ ] Create deployment sub-app structure
- [ ] Implement basic deployment API
- [ ] Create deployment dashboard UI

### Phase 2: Cloud Run Integration
- [ ] Implement DeploymentService
- [ ] Copy model artifacts to serving bucket
- [ ] Update Cloud Run service
- [ ] Traffic switching

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
