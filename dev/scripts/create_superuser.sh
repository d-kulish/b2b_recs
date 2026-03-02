#!/bin/bash
# Create Django superuser on Cloud Run

set -e

PROJECT_ID="b2b-recs"
REGION="europe-central2"
SERVICE_URL="https://django-app-555035914949.europe-central2.run.app"

USERNAME="${1:-dkulish}"
EMAIL="${2:-kulish.dmytro@gmail.com}"
PASSWORD="${3:-admin123}"

echo "Creating Django superuser..."
echo "Username: $USERNAME"
echo "Email: $EMAIL"
echo ""

# Create superuser job
gcloud run jobs create django-createsuperuser \
    --image gcr.io/${PROJECT_ID}/django-app:latest \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --set-cloudsql-instances "b2b-recs:europe-central2:b2b-recs-db" \
    --set-env-vars "DJANGO_DEBUG=False" \
    --set-env-vars "DJANGO_ALLOWED_HOSTS=*" \
    --set-env-vars "CSRF_TRUSTED_ORIGINS=${SERVICE_URL}" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars "DB_ENGINE=postgresql" \
    --set-env-vars "DB_NAME=b2b_recs_dev" \
    --set-env-vars "DB_USER=django_user" \
    --set-env-vars "DB_HOST=/cloudsql/b2b-recs:europe-central2:b2b-recs-db" \
    --set-env-vars "DB_PORT=5432" \
    --set-env-vars "DJANGO_SUPERUSER_USERNAME=${USERNAME}" \
    --set-env-vars "DJANGO_SUPERUSER_EMAIL=${EMAIL}" \
    --set-env-vars "DJANGO_SUPERUSER_PASSWORD=${PASSWORD}" \
    --set-secrets "DB_PASSWORD=django-db-password:latest" \
    --set-secrets "DJANGO_SECRET_KEY=django-secret-key:latest" \
    --service-account "django-app@b2b-recs.iam.gserviceaccount.com" \
    --command "python" \
    --args "manage.py,createsuperuser,--noinput" \
    --max-retries 0 \
    --task-timeout 2m \
    2>/dev/null || echo "Job may already exist"

# Execute the job
echo "Creating superuser..."
gcloud run jobs execute django-createsuperuser \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --wait

echo ""
echo "✅ Superuser created successfully!"
echo "   Username: $USERNAME"
echo "   Password: $PASSWORD"
echo ""
echo "Login at: ${SERVICE_URL}/admin/"
