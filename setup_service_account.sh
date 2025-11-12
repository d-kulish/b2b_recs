#!/bin/bash
# Service Account Setup Script for b2b-recs project
# Run this file: bash setup_service_account.sh

set -e  # Exit on error

echo "🚀 Setting up service account for b2b-recs Django app..."

# 1. Set project
echo "Setting GCP project to b2b-recs..."
gcloud config set project b2b-recs

# 2. Create service account
echo "Creating django-app service account..."
gcloud iam service-accounts create django-app \
    --display-name="Django Application" \
    --description="Service account for B2B Recs Django app"

# 3. Grant Secret Manager permissions
echo "Granting Secret Manager admin role..."
gcloud projects add-iam-policy-binding b2b-recs \
    --member="serviceAccount:django-app@b2b-recs.iam.gserviceaccount.com" \
    --role="roles/secretmanager.admin"

# 4. Create .gcp directory
echo "Creating .gcp directory..."
mkdir -p .gcp

# 5. Download JSON key
echo "Downloading service account key..."
gcloud iam service-accounts keys create .gcp/django-service-account.json \
    --iam-account=django-app@b2b-recs.iam.gserviceaccount.com

# 6. Set proper permissions
chmod 600 .gcp/django-service-account.json

echo ""
echo "✅ Service account created successfully!"
echo ""
echo "📁 Key saved to: $(pwd)/.gcp/django-service-account.json"
echo ""
echo "⚠️  IMPORTANT: Add this to your shell profile (~/.zshrc or ~/.bash_profile):"
echo "export GOOGLE_APPLICATION_CREDENTIALS=\"$(pwd)/.gcp/django-service-account.json\""
echo ""
echo "Then reload your shell: source ~/.zshrc"
