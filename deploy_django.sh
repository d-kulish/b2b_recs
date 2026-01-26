#!/bin/bash
# Deploy Django App to Cloud Run
# Region: europe-central2 (Warsaw, Poland)

set -e

PROJECT_ID="b2b-recs"
REGION="europe-central2"
SERVICE_NAME="django-app"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Cloud SQL Configuration (same project)
CLOUD_SQL_INSTANCE="b2b-recs-db"
CLOUD_SQL_CONNECTION="${PROJECT_ID}:${REGION}:${CLOUD_SQL_INSTANCE}"

echo "================================"
echo "Django Cloud Run Deployment"
echo "================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Step 1: Build Docker image
echo "Step 1/4: Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME} --project ${PROJECT_ID}

echo ""
echo "Step 2/4: Deploying to Cloud Run..."

# Step 2: Deploy to Cloud Run
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --max-instances 10 \
    --min-instances 0 \
    --port 8080 \
    --set-env-vars "DJANGO_DEBUG=False" \
    --set-env-vars "DJANGO_ALLOWED_HOSTS=*" \
    --set-env-vars "CSRF_TRUSTED_ORIGINS=https://django-app-555035914949.europe-central2.run.app" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars "DB_ENGINE=postgresql" \
    --set-env-vars "DB_NAME=b2b_recs_dev" \
    --set-env-vars "DB_USER=django_user" \
    --set-env-vars "DB_HOST=/cloudsql/${CLOUD_SQL_CONNECTION}" \
    --add-cloudsql-instances "${CLOUD_SQL_CONNECTION}" \
    --set-secrets "DB_PASSWORD=django-db-password:latest" \
    --set-secrets "DJANGO_SECRET_KEY=django-secret-key:latest" \
    --service-account "django-app@b2b-recs.iam.gserviceaccount.com"

echo ""
echo "Step 3/4: Getting service URL..."
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format="value(status.url)")

echo ""
echo "✅ Django deployed successfully!"
echo "URL: $SERVICE_URL"
echo ""

# Step 3: Update ETL runner with Django URL
echo "Step 4/4: Updating ETL runner with Django URL..."
gcloud run jobs update etl-runner \
    --region ${REGION} \
    --update-env-vars "DJANGO_API_URL=${SERVICE_URL}"

echo ""
echo "✅ ETL runner updated with Django URL"
echo ""
echo "================================"
echo "Deployment Complete!"
echo "================================"
echo "Django App: $SERVICE_URL"
echo "Next steps:"
echo "1. Visit $SERVICE_URL/admin to access Django admin"
echo "2. Test ETL 'Run Now' functionality"
echo ""
