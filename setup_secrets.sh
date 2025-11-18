#!/bin/bash
# Setup required secrets for Django Cloud Run deployment

set -e

PROJECT_ID="b2b-recs"

echo "================================"
echo "Setting up Cloud Secrets"
echo "================================"
echo ""

# Check if DB password secret exists
if gcloud secrets describe django-db-password --project=${PROJECT_ID} &>/dev/null; then
    echo "✓ Secret 'django-db-password' already exists"
else
    echo "Creating secret 'django-db-password'..."
    echo -n "Venera244" | gcloud secrets create django-db-password \
        --data-file=- \
        --replication-policy="automatic" \
        --project=${PROJECT_ID}
    echo "✓ Created 'django-db-password'"
fi

# Check if Django secret key exists
if gcloud secrets describe django-secret-key --project=${PROJECT_ID} &>/dev/null; then
    echo "✓ Secret 'django-secret-key' already exists"
else
    echo "Creating secret 'django-secret-key'..."
    # Generate a random secret key (50 chars of alphanumeric + special chars)
    SECRET_KEY=$(openssl rand -base64 50 | tr -d "=+/" | cut -c1-50)
    echo -n "$SECRET_KEY" | gcloud secrets create django-secret-key \
        --data-file=- \
        --replication-policy="automatic" \
        --project=${PROJECT_ID}
    echo "✓ Created 'django-secret-key'"
fi

echo ""
echo "================================"
echo "Granting access to secrets..."
echo "================================"

# Grant Cloud Run service account access to secrets
SERVICE_ACCOUNT="django-app@b2b-recs.iam.gserviceaccount.com"

for secret in django-db-password django-secret-key; do
    echo "Granting access to $secret..."
    gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --project=${PROJECT_ID} \
        --quiet
done

echo ""
echo "✅ All secrets configured successfully!"
echo ""
