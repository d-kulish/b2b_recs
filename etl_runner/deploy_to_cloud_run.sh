#!/bin/bash

# Deploy ETL Runner to Cloud Run
# Project: b2b-recs

set -e

PROJECT_ID="b2b-recs"
REGION="europe-central2"
SERVICE_ACCOUNT="etl-runner@$PROJECT_ID.iam.gserviceaccount.com"

echo "=========================================="
echo "Deploying ETL Runner to Cloud Run"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Step 1: Build and push image
echo "Step 1: Building Docker image..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/etl-runner --project=$PROJECT_ID

echo ""
echo "Step 2: Deploying to Cloud Run Jobs..."

gcloud run jobs deploy etl-runner \
  --image gcr.io/$PROJECT_ID/etl-runner \
  --region $REGION \
  --memory 8Gi \
  --cpu 4 \
  --task-timeout 3600 \
  --max-retries 1 \
  --service-account $SERVICE_ACCOUNT \
  --set-env-vars GCP_PROJECT_ID=$PROJECT_ID,DJANGO_API_URL=https://django-app-3dmqemfmxq-lm.a.run.app,LOG_LEVEL=INFO,DATAFLOW_BUCKET=b2b-recs-dataflow,DATAFLOW_REGION=$REGION \
  --project=$PROJECT_ID

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Test the job:"
echo "  gcloud run jobs execute etl-runner --region $REGION --args='--data_source_id=1'"
echo ""
echo "View logs:"
echo "  gcloud logging tail 'resource.type=cloud_run_job'"
echo ""
