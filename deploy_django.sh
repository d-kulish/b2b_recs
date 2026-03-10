#!/bin/bash
# Deploy Django App to Cloud Run (both platform and website services)
# Platform: europe-central2 (Warsaw, Poland)
# Website (recs.studio): europe-west4 (Netherlands) — required for domain mapping

set -e

PROJECT_ID="b2b-recs"
REGION="europe-central2"
SERVICE_NAME="django-app"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

WEBSITE_SERVICE_NAME="django-app-website"
WEBSITE_REGION="europe-west4"

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
echo "Step 1/5: Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME} --project ${PROJECT_ID}

echo ""
echo "Step 2/5: Deploying to Cloud Run (platform)..."

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
echo "Step 3/5: Getting service URL..."
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format="value(status.url)")

echo ""
echo "✅ Django deployed successfully!"
echo "URL: $SERVICE_URL"
echo ""

# Step 3: Update ETL runner with Django URL
echo "Step 4/5: Updating ETL runner with Django URL..."
gcloud run jobs update etl-runner \
    --region ${REGION} \
    --update-env-vars "DJANGO_API_URL=${SERVICE_URL}"

echo ""
echo "✅ ETL runner updated with Django URL"
echo ""

# Step 5: Deploy to website service (recs.studio)
echo "Step 5/5: Deploying to Cloud Run (website — recs.studio)..."
gcloud run deploy ${WEBSITE_SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --region ${WEBSITE_REGION} \
    --platform managed \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --timeout 300 \
    --max-instances 3 \
    --min-instances 0 \
    --port 8080 \
    --set-env-vars "DJANGO_DEBUG=False" \
    --set-env-vars "DJANGO_ALLOWED_HOSTS=*" \
    --set-env-vars "CSRF_TRUSTED_ORIGINS=https://recs.studio,https://www.recs.studio,https://django-app-555035914949.europe-central2.run.app" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars "DB_ENGINE=postgresql" \
    --set-env-vars "DB_NAME=b2b_recs_dev" \
    --set-env-vars "DB_USER=django_user" \
    --set-env-vars "DB_HOST=/cloudsql/${CLOUD_SQL_CONNECTION}" \
    --add-cloudsql-instances "${CLOUD_SQL_CONNECTION}" \
    --set-secrets "DB_PASSWORD=django-db-password:latest" \
    --set-secrets "DJANGO_SECRET_KEY=django-secret-key:latest" \
    --service-account "django-app@b2b-recs.iam.gserviceaccount.com"

WEBSITE_URL=$(gcloud run services describe ${WEBSITE_SERVICE_NAME} --region ${WEBSITE_REGION} --format="value(status.url)")
echo ""
echo "✅ Website deployed successfully!"
echo ""
echo "================================"
echo "Deployment Complete!"
echo "================================"
echo "Platform: $SERVICE_URL"
echo "Website:  $WEBSITE_URL (recs.studio)"
echo ""
echo "Next steps:"
echo "1. Visit $SERVICE_URL/admin to access Django admin"
echo "2. Test ETL 'Run Now' functionality"
echo "3. Verify https://recs.studio shows updated content"
echo ""
