#!/bin/bash
# Deploy the public website to its own Cloud Run service and image.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="b2b-recs"
REGION="europe-west4"
SERVICE_NAME="django-app-website"
IMAGE_NAME="gcr.io/${PROJECT_ID}/website-app"

PLATFORM_SERVICE_NAME="django-app"
PLATFORM_REGION="europe-central2"
DEFAULT_PLATFORM_URL="https://django-app-555035914949.europe-central2.run.app"

# Cloud SQL Configuration (same project)
CLOUD_SQL_INSTANCE="b2b-recs-db"
CLOUD_SQL_CONNECTION="${PROJECT_ID}:${PLATFORM_REGION}:${CLOUD_SQL_INSTANCE}"

echo "================================"
echo "Website Cloud Run Deployment"
echo "================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

PLATFORM_URL=$(gcloud run services describe ${PLATFORM_SERVICE_NAME} \
    --region ${PLATFORM_REGION} \
    --format="value(status.url)" 2>/dev/null || true)
PLATFORM_URL=${PLATFORM_URL:-$DEFAULT_PLATFORM_URL}

WEBSITE_SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --region ${REGION} \
    --format="value(status.url)" 2>/dev/null || true)

CSRF_TRUSTED_ORIGINS="https://recs.studio,https://www.recs.studio"
if [ -n "${WEBSITE_SERVICE_URL}" ]; then
    CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS},${WEBSITE_SERVICE_URL}"
fi

echo "Step 1/2: Building website Docker image..."
gcloud builds submit "${REPO_ROOT}" \
    --project ${PROJECT_ID} \
    --config "${SCRIPT_DIR}/cloudbuild.yaml" \
    --substitutions _IMAGE_NAME=${IMAGE_NAME}

echo ""
echo "Step 2/2: Deploying website to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --region ${REGION} \
    --project ${PROJECT_ID} \
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
    --set-env-vars "^##^CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS}" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars "DB_ENGINE=postgresql" \
    --set-env-vars "DB_NAME=b2b_recs_dev" \
    --set-env-vars "DB_USER=django_user" \
    --set-env-vars "DB_HOST=/cloudsql/${CLOUD_SQL_CONNECTION}" \
    --set-env-vars "PLATFORM_BASE_URL=${PLATFORM_URL}" \
    --add-cloudsql-instances "${CLOUD_SQL_CONNECTION}" \
    --set-secrets "DB_PASSWORD=django-db-password:latest" \
    --set-secrets "DJANGO_SECRET_KEY=django-secret-key:latest" \
    --set-secrets "RESEND_API_KEY=resend-api-key:latest" \
    --service-account "django-app@b2b-recs.iam.gserviceaccount.com"

WEBSITE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format="value(status.url)")

echo ""
echo "================================"
echo "Deployment Complete!"
echo "================================"
echo "Website:  $WEBSITE_URL"
echo "Platform: $PLATFORM_URL"
echo ""
echo "Next steps:"
echo "1. Verify $WEBSITE_URL serves only the public website"
echo "2. Verify https://recs.studio shows updated content"
echo "3. Confirm authenticated website redirects land on ${PLATFORM_URL}/dashboard/"
echo ""
