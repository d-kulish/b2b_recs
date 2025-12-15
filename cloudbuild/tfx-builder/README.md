# TFX Compiler Image

Pre-built Docker image for compiling TFX pipelines for Vertex AI. This image is hosted in the central `b2b-recs-platform` project and shared across all client projects.

## Why This Image?

- **Problem**: TFX requires Python 3.9-3.10, but Django runs on Python 3.13
- **Old Solution**: Cloud Build with `python:3.10` + inline pip install (12-15 minutes)
- **New Solution**: Pre-built image with all dependencies (1-2 minutes)

## Image Location

```
europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest
```

## Contents

| Package | Version | Purpose |
|---------|---------|---------|
| Python | 3.10 | Base runtime |
| TFX | 1.15.0 | Pipeline framework |
| KFP | 2.4.0 | Kubeflow Pipelines SDK |
| google-cloud-aiplatform | 1.38.0 | Vertex AI SDK |
| google-cloud-storage | 2.14.0 | GCS access |
| google-cloud-bigquery | 3.14.0 | BigQuery access |
| apache-beam[gcp] | 2.52.0 | Data processing |
| dill | 0.3.7 | Serialization |

## Initial Setup (One-Time)

### 1. Create Artifact Registry Repository

```bash
# In the platform project (b2b-recs-platform)
gcloud artifacts repositories create tfx-builder \
    --repository-format=docker \
    --location=europe-central2 \
    --description="TFX Pipeline Compiler images" \
    --project=b2b-recs-platform
```

### 2. Build and Push the Image

**Option A: Using Cloud Build (Recommended)**

```bash
cd cloudbuild/tfx-builder
gcloud builds submit --config=cloudbuild.yaml --project=b2b-recs-platform
```

**Option B: Build Locally**

```bash
# Authenticate Docker
gcloud auth configure-docker europe-central2-docker.pkg.dev

# Build
cd cloudbuild/tfx-builder
docker build -t europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest .

# Push
docker push europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest

# Tag with version
docker tag europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest \
           europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:v1.0.0
docker push europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:v1.0.0
```

### 3. Verify the Image

```bash
# Pull and test
docker pull europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest

docker run --rm europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest \
    python -c "import tfx; print(f'TFX: {tfx.__version__}')"
```

## Client Project Setup

Each client project's Cloud Build service account needs read access to the shared image.

### Grant Access to Client Project

```bash
#!/bin/bash
# provision_tfx_image_access.sh

CLIENT_PROJECT=$1
PLATFORM_PROJECT="b2b-recs-platform"
REGION="europe-central2"

if [ -z "$CLIENT_PROJECT" ]; then
    echo "Usage: $0 <client-project-id>"
    exit 1
fi

# Get Cloud Build service account for client project
CB_SA_NUMBER=$(gcloud projects describe $CLIENT_PROJECT --format='value(projectNumber)')
CB_SA="${CB_SA_NUMBER}@cloudbuild.gserviceaccount.com"

echo "Granting access to: $CB_SA"

# Grant reader access to Artifact Registry
gcloud artifacts repositories add-iam-policy-binding tfx-builder \
    --project=$PLATFORM_PROJECT \
    --location=$REGION \
    --member="serviceAccount:$CB_SA" \
    --role="roles/artifactregistry.reader"

echo "Done! Client $CLIENT_PROJECT can now use the shared TFX compiler image."
```

### For Development (b2b-recs project)

```bash
# Get Cloud Build SA number
PROJECT_NUMBER=$(gcloud projects describe b2b-recs --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Grant access
gcloud artifacts repositories add-iam-policy-binding tfx-builder \
    --project=b2b-recs-platform \
    --location=europe-central2 \
    --member="serviceAccount:$CB_SA" \
    --role="roles/artifactregistry.reader"
```

## Updating the Image

When you need to update TFX version or add dependencies:

1. Update `Dockerfile` with new versions
2. Update version tag in `cloudbuild.yaml` (e.g., `v1.1.0`)
3. Run Cloud Build:
   ```bash
   cd cloudbuild/tfx-builder
   gcloud builds submit --config=cloudbuild.yaml --project=b2b-recs-platform
   ```
4. (Optional) Update `TFX_COMPILER_IMAGE` in Django settings to pin to new version

## Rollback

If issues occur with a new image version:

1. **Quick Fix**: Set `TFX_COMPILER_IMAGE` env var to previous version:
   ```bash
   TFX_COMPILER_IMAGE=europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:v1.0.0
   ```

2. **Emergency**: The code has a fallback - if the pre-built image fails, you can temporarily revert `services.py` to use `python:3.10` with inline pip install (slower but works).

## Troubleshooting

### "Permission denied" when pulling image

The Cloud Build service account doesn't have access. Run:
```bash
gcloud artifacts repositories add-iam-policy-binding tfx-builder \
    --project=b2b-recs-platform \
    --location=europe-central2 \
    --member="serviceAccount:YOUR_CB_SA@cloudbuild.gserviceaccount.com" \
    --role="roles/artifactregistry.reader"
```

### Image build fails

Check that all package versions are compatible. TFX has strict version requirements for TensorFlow and other dependencies.

### Pipeline compilation fails

1. Check Cloud Build logs in GCP Console
2. Verify TFX imports work: `python -c "import tfx; print(tfx.__version__)"`
3. Check that transform_module.py and trainer_module.py are valid Python

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         b2b-recs-platform                                │
│                      (SaaS Management Project)                           │
│                                                                          │
│  Artifact Registry: europe-central2-docker.pkg.dev                      │
│  └── tfx-builder/tfx-compiler:latest                                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
     ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
     │  client-a   │         │  client-b   │         │  b2b-recs   │
     │             │         │             │         │   (dev)     │
     │ Cloud Build │         │ Cloud Build │         │ Cloud Build │
     │ (pulls      │         │ (pulls      │         │ (pulls      │
     │  shared     │         │  shared     │         │  shared     │
     │  image)     │         │  image)     │         │  image)     │
     └─────────────┘         └─────────────┘         └─────────────┘
```

## Cost

- Artifact Registry storage: ~$0.10/GB/month
- Image size: ~2-3 GB
- Monthly cost: ~$0.30 total (one image for all clients)
