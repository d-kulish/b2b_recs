#!/bin/bash

# GCP Setup Script for B2B Recommendations ETL Platform
# Project: b2b-recs (555035914949)

set -e  # Exit on error

PROJECT_ID="b2b-recs"
PROJECT_NUMBER="555035914949"
REGION="europe-central2"

echo "=========================================="
echo "GCP Setup for ETL Platform"
echo "=========================================="
echo "Project ID: $PROJECT_ID"
echo "Project Number: $PROJECT_NUMBER"
echo "Region: $REGION"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Set active project
echo "Step 1: Setting active GCP project..."
gcloud config set project $PROJECT_ID
echo -e "${GREEN}✓${NC} Project set to $PROJECT_ID"
echo ""

# Step 2: Enable required APIs
echo "Step 2: Enabling required GCP APIs..."
echo "  This may take 2-3 minutes..."

apis=(
    "bigquery.googleapis.com"
    "cloudscheduler.googleapis.com"
    "run.googleapis.com"
    "cloudbuild.googleapis.com"
    "secretmanager.googleapis.com"
    "sqladmin.googleapis.com"
)

for api in "${apis[@]}"; do
    echo -n "  Enabling $api... "
    if gcloud services enable $api --project=$PROJECT_ID 2>&1 | grep -q "ERROR"; then
        echo -e "${RED}Failed${NC}"
        exit 1
    else
        echo -e "${GREEN}✓${NC}"
    fi
done
echo ""

# Step 3: Authenticate application default credentials
echo "Step 3: Setting up Application Default Credentials..."
echo "  A browser window will open for authentication..."
echo "  Please sign in with your Google account."
echo ""
read -p "Press Enter to continue..."

gcloud auth application-default login --project=$PROJECT_ID
echo -e "${GREEN}✓${NC} Application Default Credentials configured"
echo ""

# Step 4: Create service account for ETL Runner
echo "Step 4: Creating ETL Runner service account..."

SA_NAME="etl-runner"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Check if service account exists
if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID 2>/dev/null; then
    echo -e "${YELLOW}⚠${NC} Service account already exists: $SA_EMAIL"
else
    gcloud iam service-accounts create $SA_NAME \
        --display-name="ETL Runner Service Account" \
        --description="Service account for Cloud Run ETL jobs" \
        --project=$PROJECT_ID
    echo -e "${GREEN}✓${NC} Created service account: $SA_EMAIL"
fi
echo ""

# Step 5: Grant IAM permissions
echo "Step 5: Granting IAM permissions..."

roles=(
    "roles/bigquery.dataEditor"
    "roles/bigquery.jobUser"
    "roles/secretmanager.secretAccessor"
    "roles/run.invoker"
)

for role in "${roles[@]}"; do
    echo -n "  Granting $role... "
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --condition=None \
        --quiet > /dev/null 2>&1
    echo -e "${GREEN}✓${NC}"
done

# Grant Django app permissions (if using App Engine default service account)
echo -n "  Granting Cloud Scheduler admin to App Engine default SA... "
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_ID@appspot.gserviceaccount.com" \
    --role="roles/cloudscheduler.admin" \
    --condition=None \
    --quiet > /dev/null 2>&1
echo -e "${GREEN}✓${NC}"

echo ""

# Step 6: Create BigQuery dataset
echo "Step 6: Creating BigQuery dataset..."

DATASET_ID="raw_data"

if bq ls -d --project_id=$PROJECT_ID $DATASET_ID 2>/dev/null; then
    echo -e "${YELLOW}⚠${NC} Dataset already exists: $DATASET_ID"
else
    bq mk \
        --dataset \
        --location=$REGION \
        --description="Raw data from ETL pipelines" \
        --project_id=$PROJECT_ID \
        $DATASET_ID
    echo -e "${GREEN}✓${NC} Created dataset: $DATASET_ID"
fi
echo ""

# Step 7: Test permissions
echo "Step 7: Testing permissions..."

echo -n "  Testing BigQuery access... "
if bq ls --project_id=$PROJECT_ID > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}Failed${NC}"
    echo "  Please check your permissions"
fi

echo -n "  Testing Secret Manager access... "
if gcloud secrets list --project=$PROJECT_ID --limit=1 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC} (May not have any secrets yet)"
fi

echo ""

# Summary
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Configuration Summary:"
echo "  Project ID: $PROJECT_ID"
echo "  Region: $REGION"
echo "  BigQuery Dataset: $DATASET_ID"
echo "  Service Account: $SA_EMAIL"
echo ""
echo "Enabled APIs:"
for api in "${apis[@]}"; do
    echo "  ✓ $api"
done
echo ""
echo "Next Steps:"
echo "  1. Restart your Django development server"
echo "  2. Try creating an ETL job through the wizard"
echo "  3. The BigQuery table will be created automatically"
echo ""
echo "Optional (for Cloud Run deployment):"
echo "  Run: cd etl_runner && ./deploy_to_cloud_run.sh"
echo ""
echo "=========================================="
