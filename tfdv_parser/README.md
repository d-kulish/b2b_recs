# TFDV Parser Cloud Run Service

A Cloud Run service for parsing TensorFlow Data Validation (TFDV) artifacts from TFX pipelines.

## Overview

This service runs Python 3.10 with full TFX/TFDV stack, providing REST API endpoints to parse pipeline artifacts that cannot be parsed in the main Django app (Python 3.12) due to TensorFlow version incompatibility.

## Features

- Parse `FeatureStats.pb` from StatisticsGen component
- Parse `schema.pbtxt` from SchemaGen component
- Generate TFDV HTML visualizations
- Rich statistics matching standard TFDV display:
  - Numeric: count, missing%, mean, std_dev, zeros%, min, median, max, histogram
  - Categorical: count, missing%, unique, top values, distribution

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/parse/statistics` | POST | Parse statistics from pipeline artifacts |
| `/parse/statistics/html` | POST | Get TFDV HTML visualization |
| `/parse/schema` | POST | Parse schema from pipeline artifacts |
| `/parse/all` | POST | Parse both statistics and schema |

### Request Format

```json
{
    "pipeline_root": "gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}",
    "include_html": false
}
```

### Response Format (Statistics)

```json
{
    "success": true,
    "statistics": {
        "available": true,
        "num_examples": 1234567,
        "num_features": 45,
        "num_numeric_features": 30,
        "num_categorical_features": 15,
        "avg_missing_pct": 2.3,
        "numeric_features": [...],
        "categorical_features": [...]
    }
}
```

## Deployment

### Prerequisites

1. GCP project with Cloud Run and Cloud Build enabled
2. Service account with required permissions
3. Artifact Registry repository for Docker images

### Step 1: Create Service Account

```bash
PROJECT_ID="b2b-recs"
SA_NAME="tfdv-parser"

# Create service account
gcloud iam service-accounts create $SA_NAME \
    --display-name="TFDV Parser Service Account" \
    --project=$PROJECT_ID

# Grant GCS read access
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.objectViewer"
```

### Step 2: Deploy with Cloud Build

```bash
cd /path/to/b2b_recs

# Deploy using Cloud Build
gcloud builds submit --config=tfdv_parser/cloudbuild.yaml \
    --project=$PROJECT_ID \
    --substitutions=COMMIT_SHA=$(git rev-parse HEAD)
```

### Step 3: Get Service URL

```bash
gcloud run services describe tfdv-parser \
    --region=europe-central2 \
    --format='value(status.url)' \
    --project=$PROJECT_ID
```

### Step 4: Update Django Environment

Add the service URL to your Django Cloud Run service:

```bash
TFDV_URL=$(gcloud run services describe tfdv-parser \
    --region=europe-central2 \
    --format='value(status.url)' \
    --project=$PROJECT_ID)

gcloud run services update <django-service-name> \
    --region=europe-central2 \
    --update-env-vars="TFDV_PARSER_URL=$TFDV_URL" \
    --project=$PROJECT_ID
```

### Step 5: Grant Django Service Account Invoker Permission

```bash
DJANGO_SA="<django-service-account>@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding tfdv-parser \
    --region=europe-central2 \
    --member="serviceAccount:$DJANGO_SA" \
    --role="roles/run.invoker" \
    --project=$PROJECT_ID
```

## Local Development

### Run Locally

```bash
cd tfdv_parser

# Create virtual environment with Python 3.10
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GCP_PROJECT_ID=b2b-recs
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Run Flask app
python main.py
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8080/health

# Parse statistics
curl -X POST http://localhost:8080/parse/statistics \
    -H "Content-Type: application/json" \
    -d '{"pipeline_root": "gs://b2b-recs-pipeline-staging/pipeline_root/test-run-123"}'
```

## Architecture

```
Django (Python 3.12)
    |
    | HTTP POST with auth token
    v
tfdv-parser (Python 3.10, Cloud Run)
    |
    | GCS read
    v
gs://b2b-recs-pipeline-staging/
    pipeline_root/{run_id}/
        StatisticsGen/.../FeatureStats.pb
        SchemaGen/.../schema.pbtxt
```

## Security

- Service is deployed with `--no-allow-unauthenticated`
- Django uses service-to-service authentication with IAM
- GCS access controlled via service account IAM

## Monitoring

View logs in Cloud Console:
```
resource.type="cloud_run_revision"
resource.labels.service_name="tfdv-parser"
```

## Troubleshooting

### "Data insights not available" Error

If the Data Insights tab shows "Data insights not available" even though the pipeline completed StatisticsGen and SchemaGen stages, check the following:

#### 1. Check Cloud Run Logs

Look for logs showing the GCS path being searched:
```
INFO - [STATS] Parsing from: gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}
INFO - Searching for statistics in gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}
INFO - Found 0 blobs in pipeline artifacts
WARNING - No FeatureStats.pb found in 0 blobs
```

If "Found 0 blobs", the artifacts may have been deleted.

#### 2. GCS Bucket Lifecycle Policy

**Root Cause (Dec 2025):** The `b2b-recs-pipeline-staging` bucket had a 3-day lifecycle policy that automatically deleted all pipeline artifacts after 3 days. This caused Data Insights to fail for experiments older than 3 days.

**Fix Applied:** Extended lifecycle policy to 360 days.

Check current lifecycle policy:
```bash
gsutil lifecycle get gs://b2b-recs-pipeline-staging
```

Expected output:
```json
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 360}}]}
```

If the policy is too short, update it:
```bash
gsutil lifecycle set /dev/stdin gs://b2b-recs-pipeline-staging << 'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 360}}]}
EOF
```

#### 3. Verify Artifacts Exist

Check if statistics files exist for a specific experiment:
```bash
gsutil ls -r "gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}/**/*FeatureStats*"
gsutil ls -r "gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}/**/*schema*"
```

#### 4. IPython Dependency

The service requires IPython for TFDV visualization APIs. Ensure `requirements.txt` includes:
```
tensorflow-data-validation[visualization]>=1.14.0
```

Without the `[visualization]` extra, you'll see this warning in logs:
```
Unable to import IPython: No module named 'IPython'.
TFDV visualization APIs will not function.
```
