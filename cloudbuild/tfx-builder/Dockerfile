# TFX Pipeline Compiler Image
#
# This image contains all dependencies needed to compile TFX pipelines
# for Vertex AI. It is hosted in the central platform project and shared
# across all client projects via IAM.
#
# Location: europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler
#
# Usage in Cloud Build:
#   steps:
#     - name: 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest'
#       entrypoint: 'python'
#       args: ['compile_script.py', ...]

FROM python:3.10-slim

LABEL maintainer="B2B Recs Platform"
LABEL description="TFX Pipeline Compiler for Vertex AI"
LABEL version="1.0.0"

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install TFX first - it will pull compatible versions of all dependencies
# including tensorflow, apache-beam, etc.
RUN pip install --no-cache-dir tfx==1.15.0

# Install KFP for Kubeflow pipeline compilation
# KFP is needed for kubeflow_v2_dag_runner
RUN pip install --no-cache-dir kfp>=2.0.0

# Install dill (required by tfx_bsl/beam)
# Use version compatible with apache-beam
RUN pip install --no-cache-dir "dill>=0.3.1.1,<0.3.2"

# Install additional Google Cloud SDKs (compatible versions)
RUN pip install --no-cache-dir \
    google-cloud-aiplatform>=1.38.0 \
    google-cloud-storage>=2.14.0 \
    google-cloud-bigquery>=3.14.0

# Verify TFX installation and key imports
RUN python -c "import tfx; print(f'TFX version: {tfx.__version__}')"
RUN python -c "import kfp; print(f'KFP version: {kfp.__version__}')"
RUN python -c "from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner; print('KubeflowV2DagRunner: OK')"
RUN python -c "from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen; print('BigQueryExampleGen: OK')"
RUN python -c "from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer; print('TFX Components: OK')"
RUN python -c "from google.cloud import aiplatform; print('Vertex AI SDK: OK')"
RUN python -c "from google.cloud import storage; print('GCS SDK: OK')"

# Set working directory
WORKDIR /workspace

# Default command (will be overridden by Cloud Build)
CMD ["python", "--version"]
