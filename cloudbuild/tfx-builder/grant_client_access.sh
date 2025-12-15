#!/bin/bash
# Grant a client project's Cloud Build service account access to the shared TFX compiler image
#
# Usage:
#   ./grant_client_access.sh <client-project-id>
#
# Example:
#   ./grant_client_access.sh b2b-recs
#   ./grant_client_access.sh client-acme-prod

set -e

CLIENT_PROJECT=$1
PLATFORM_PROJECT="b2b-recs-platform"
REGION="europe-central2"

if [ -z "$CLIENT_PROJECT" ]; then
    echo "Usage: $0 <client-project-id>"
    echo ""
    echo "Examples:"
    echo "  $0 b2b-recs           # Development project"
    echo "  $0 client-acme-prod   # Client project"
    exit 1
fi

echo "=============================================="
echo "Granting TFX Compiler Image Access"
echo "=============================================="
echo "Platform Project: $PLATFORM_PROJECT"
echo "Client Project:   $CLIENT_PROJECT"
echo "Region:           $REGION"
echo ""

# Get Cloud Build service account for client project
echo "Looking up Cloud Build service account..."
CB_SA_NUMBER=$(gcloud projects describe $CLIENT_PROJECT --format='value(projectNumber)')
CB_SA="${CB_SA_NUMBER}@cloudbuild.gserviceaccount.com"
echo "Cloud Build SA: $CB_SA"
echo ""

# Grant reader access to Artifact Registry
echo "Granting artifactregistry.reader role..."
gcloud artifacts repositories add-iam-policy-binding tfx-builder \
    --project=$PLATFORM_PROJECT \
    --location=$REGION \
    --member="serviceAccount:$CB_SA" \
    --role="roles/artifactregistry.reader" \
    --quiet

echo ""
echo "=============================================="
echo "SUCCESS!"
echo "=============================================="
echo ""
echo "Client project '$CLIENT_PROJECT' can now pull:"
echo "  europe-central2-docker.pkg.dev/$PLATFORM_PROJECT/tfx-builder/tfx-compiler:latest"
echo ""
echo "Test with:"
echo "  gcloud builds submit --no-source --project=$CLIENT_PROJECT \\"
echo "    --config=- <<EOF"
echo "  steps:"
echo "    - name: 'europe-central2-docker.pkg.dev/$PLATFORM_PROJECT/tfx-builder/tfx-compiler:latest'"
echo "      args: ['python', '-c', 'import tfx; print(tfx.__version__)']"
echo "  EOF"
