# MLflow Tracking Server

Cloud Run service for MLflow experiment tracking, used by the b2b_recs ML platform.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Django App     │────▶│  MLflow Server  │────▶│  Cloud SQL      │
│  (UI/API)       │     │  (Cloud Run)    │     │  (PostgreSQL)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  GCS Bucket     │
                        │  (Artifacts)    │
                        └─────────────────┘
```

## Prerequisites

- GCP Project with Cloud Run, Cloud SQL, Secret Manager, and GCS enabled
- Existing Cloud SQL PostgreSQL instance (or create new one)
- `gcloud` CLI authenticated with appropriate permissions

## Setup Instructions

### 1. Create Service Account

```bash
# Create service account for MLflow server
gcloud iam service-accounts create mlflow-server \
    --display-name="MLflow Tracking Server"

# Grant GCS permissions for artifact storage
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:mlflow-server@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"

# Grant Cloud SQL client permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:mlflow-server@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"
```

### 2. Create GCS Bucket for Artifacts

```bash
# Create bucket in same region as Cloud Run
gsutil mb -l europe-central2 gs://$PROJECT_ID-mlflow-artifacts

# Set lifecycle policy (optional - delete old artifacts after 90 days)
cat > /tmp/lifecycle.json << 'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 90}
      }
    ]
  }
}
EOF
gsutil lifecycle set /tmp/lifecycle.json gs://$PROJECT_ID-mlflow-artifacts
```

### 3. Setup Database

#### Option A: Use Existing Cloud SQL Instance

```bash
# Create mlflow database on existing instance
gcloud sql databases create mlflow --instance=YOUR_INSTANCE_NAME

# Create mlflow user (generate a secure password)
gcloud sql users create mlflow_user \
    --instance=YOUR_INSTANCE_NAME \
    --password=YOUR_SECURE_PASSWORD
```

#### Option B: Create New Cloud SQL Instance

```bash
# Create new PostgreSQL instance (db-f1-micro for cost savings)
gcloud sql instances create mlflow-db \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=europe-central2 \
    --storage-size=10GB \
    --storage-auto-increase

# Create database and user
gcloud sql databases create mlflow --instance=mlflow-db
gcloud sql users create mlflow_user \
    --instance=mlflow-db \
    --password=YOUR_SECURE_PASSWORD
```

### 4. Store Database URI in Secret Manager

```bash
# For Cloud SQL with Unix socket connection
# Format: postgresql://USER:PASSWORD@/DATABASE?host=/cloudsql/PROJECT:REGION:INSTANCE

echo -n "postgresql://mlflow_user:YOUR_SECURE_PASSWORD@/mlflow?host=/cloudsql/$PROJECT_ID:europe-central2:YOUR_INSTANCE_NAME" | \
    gcloud secrets create mlflow-db-uri --data-file=-

# Grant MLflow service account access to the secret
gcloud secrets add-iam-policy-binding mlflow-db-uri \
    --member="serviceAccount:mlflow-server@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

### 5. Deploy MLflow Server

```bash
# Deploy using Cloud Build
gcloud builds submit --config=mlflow_server/cloudbuild.yaml

# Or deploy manually
cd mlflow_server
gcloud run deploy mlflow-server \
    --source . \
    --region europe-central2 \
    --memory 2Gi \
    --cpu 2 \
    --timeout 600 \
    --concurrency 20 \
    --min-instances 0 \
    --max-instances 3 \
    --no-allow-unauthenticated \
    --service-account mlflow-server@$PROJECT_ID.iam.gserviceaccount.com \
    --set-secrets MLFLOW_BACKEND_STORE_URI=mlflow-db-uri:latest \
    --set-env-vars MLFLOW_ARTIFACT_ROOT=gs://$PROJECT_ID-mlflow-artifacts
```

### 6. Grant Django Access to MLflow

```bash
# Allow Django service account to invoke MLflow
gcloud run services add-iam-policy-binding mlflow-server \
    --region=europe-central2 \
    --member="serviceAccount:YOUR_DJANGO_SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.invoker"
```

### 7. Get MLflow Server URL

```bash
# Get the deployed service URL
gcloud run services describe mlflow-server \
    --region=europe-central2 \
    --format='value(status.url)'

# Add to Django settings (MLFLOW_TRACKING_URI)
```

## Configuration

| Environment Variable | Description | Example |
|---------------------|-------------|---------|
| `MLFLOW_BACKEND_STORE_URI` | PostgreSQL connection string | `postgresql://user:pass@/mlflow?host=/cloudsql/...` |
| `MLFLOW_ARTIFACT_ROOT` | GCS bucket for artifacts | `gs://project-mlflow-artifacts` |
| `PORT` | Server port (set by Cloud Run) | `8080` |
| `MLFLOW_WORKERS` | Number of gunicorn workers | `2` |

## API Endpoints

MLflow exposes a REST API at `/api/2.0/mlflow/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/experiments/get-by-name` | GET | Get experiment by name |
| `/runs/search` | POST | Search runs with filters |
| `/runs/get` | GET | Get single run details |
| `/metrics/get-history` | GET | Get metric history for a run |

## Cost Estimate

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| Cloud Run (scale to 0) | ~$5-10 | 5-10s cold start after idle |
| Cloud SQL (shared) | $0 | Use existing instance |
| GCS artifacts | ~$1-5 | Depends on experiment volume |
| **Total** | **~$10-15** | Per environment |

## Troubleshooting

### Cold Start Issues

With `min-instances=0`, the first request after idle will take 5-10 seconds. If this is problematic:

```bash
# Set minimum instances to 1 (adds ~$30/month)
gcloud run services update mlflow-server \
    --region europe-central2 \
    --min-instances 1
```

### Database Connection Issues

1. Check Cloud SQL instance is running
2. Verify service account has `cloudsql.client` role
3. Check secret value in Secret Manager

```bash
# Test secret access
gcloud secrets versions access latest --secret=mlflow-db-uri
```

### Authentication Issues

Django must use identity tokens to call MLflow:

```python
import google.auth.transport.requests
import google.oauth2.id_token

def get_mlflow_token():
    auth_req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_req, MLFLOW_TRACKING_URI)
```

## Local Development

For local testing, you can run MLflow with SQLite:

```bash
pip install mlflow

# Run with local SQLite backend
mlflow server \
    --backend-store-uri sqlite:///mlflow.db \
    --default-artifact-root ./mlflow-artifacts \
    --host 0.0.0.0 \
    --port 5000
```
