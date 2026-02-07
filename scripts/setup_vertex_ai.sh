#!/bin/bash
# =============================================================================
# Vertex AI Pipeline Infrastructure Setup
# =============================================================================
# This script sets up the GCP infrastructure required for Quick Tests:
# - Enables Vertex AI API
# - Creates GCS buckets with lifecycle policies
# - Adds required IAM roles to the service account
#
# Usage: ./scripts/setup_vertex_ai.sh
# =============================================================================

set -e  # Exit on error

# Configuration
PROJECT_ID="b2b-recs"
REGION="europe-central2"
SERVICE_ACCOUNT="django-app@b2b-recs.iam.gserviceaccount.com"

# Bucket names
QUICKTEST_BUCKET="b2b-recs-quicktest-artifacts"
TRAINING_BUCKET="b2b-recs-training-artifacts"
STAGING_BUCKET="b2b-recs-pipeline-staging"
DATAFLOW_BUCKET="b2b-recs-dataflow"

echo "=============================================="
echo "Vertex AI Pipeline Infrastructure Setup"
echo "=============================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Account: $SERVICE_ACCOUNT"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Enable Vertex AI API
# -----------------------------------------------------------------------------
echo "[1/5] Enabling Vertex AI API..."
gcloud services enable aiplatform.googleapis.com --project=$PROJECT_ID
echo "      Vertex AI API enabled."

# -----------------------------------------------------------------------------
# Step 2: Add IAM roles to service account
# -----------------------------------------------------------------------------
echo ""
echo "[2/5] Adding IAM roles to service account..."

# Vertex AI User - allows running pipelines
echo "      Adding roles/aiplatform.user..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/aiplatform.user" \
    --quiet

# Storage Admin - allows creating/managing buckets and objects
echo "      Adding roles/storage.admin..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.admin" \
    --quiet

# Service Account User - allows impersonation for pipeline execution
echo "      Adding roles/iam.serviceAccountUser..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/iam.serviceAccountUser" \
    --quiet

echo "      IAM roles added successfully."

# -----------------------------------------------------------------------------
# Step 3: Create GCS buckets
# -----------------------------------------------------------------------------
echo ""
echo "[3/5] Creating GCS buckets..."

# Quick Test artifacts bucket (7-day lifecycle)
if gsutil ls -b gs://$QUICKTEST_BUCKET 2>/dev/null; then
    echo "      Bucket $QUICKTEST_BUCKET already exists."
else
    echo "      Creating $QUICKTEST_BUCKET..."
    gsutil mb -p $PROJECT_ID -l $REGION gs://$QUICKTEST_BUCKET/
fi

# Training artifacts bucket (no lifecycle — managed by cleanup command)
if gsutil ls -b gs://$TRAINING_BUCKET 2>/dev/null; then
    echo "      Bucket $TRAINING_BUCKET already exists."
else
    echo "      Creating $TRAINING_BUCKET..."
    gsutil mb -p $PROJECT_ID -l $REGION gs://$TRAINING_BUCKET/
fi

# Pipeline staging bucket (7-day lifecycle)
if gsutil ls -b gs://$STAGING_BUCKET 2>/dev/null; then
    echo "      Bucket $STAGING_BUCKET already exists."
else
    echo "      Creating $STAGING_BUCKET..."
    gsutil mb -p $PROJECT_ID -l $REGION gs://$STAGING_BUCKET/
fi

# Dataflow temp bucket (3-day lifecycle)
if gsutil ls -b gs://$DATAFLOW_BUCKET 2>/dev/null; then
    echo "      Bucket $DATAFLOW_BUCKET already exists."
else
    echo "      Creating $DATAFLOW_BUCKET..."
    gsutil mb -p $PROJECT_ID -l $REGION gs://$DATAFLOW_BUCKET/
fi

echo "      Buckets created."

# -----------------------------------------------------------------------------
# Step 4: Set lifecycle policies
# -----------------------------------------------------------------------------
echo ""
echo "[4/5] Setting lifecycle policies..."

# Quick Test: 7 days
echo "      Setting 7-day lifecycle on $QUICKTEST_BUCKET..."
cat << 'EOF' | gsutil lifecycle set /dev/stdin gs://$QUICKTEST_BUCKET/
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 7}
    }
  ]
}
EOF

# Training: NO lifecycle (managed by cleanup_gcs_artifacts command to preserve registered models)
echo "      Removing lifecycle on $TRAINING_BUCKET (managed by cleanup command)..."
cat << 'EOF' | gsutil lifecycle set /dev/stdin gs://$TRAINING_BUCKET/
{
  "rule": []
}
EOF

# Staging: 7 days
echo "      Setting 7-day lifecycle on $STAGING_BUCKET..."
cat << 'EOF' | gsutil lifecycle set /dev/stdin gs://$STAGING_BUCKET/
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 7}
    }
  ]
}
EOF

# Dataflow: 3 days
echo "      Setting 3-day lifecycle on $DATAFLOW_BUCKET..."
cat << 'EOF' | gsutil lifecycle set /dev/stdin gs://$DATAFLOW_BUCKET/
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 3}
    }
  ]
}
EOF

echo "      Lifecycle policies set."

# -----------------------------------------------------------------------------
# Step 5: Summary
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "Setup Complete!"
echo "=============================================="
echo ""
echo "Created resources:"
echo "  - Enabled: Vertex AI API"
echo "  - IAM roles added to $SERVICE_ACCOUNT:"
echo "    - roles/aiplatform.user"
echo "    - roles/storage.admin"
echo "    - roles/iam.serviceAccountUser"
echo "  - GCS Buckets:"
echo "    - gs://$QUICKTEST_BUCKET (7-day lifecycle)"
echo "    - gs://$TRAINING_BUCKET (no lifecycle — managed by cleanup_gcs_artifacts)"
echo "    - gs://$STAGING_BUCKET (7-day lifecycle)"
echo "    - gs://$DATAFLOW_BUCKET (3-day lifecycle)"
echo ""
echo "Next steps:"
echo "  1. Install new Python dependencies: pip install -r requirements.txt"
echo "  2. Run migrations: python manage.py migrate"
echo "  3. Test Vertex AI connection in Django shell"
echo ""
