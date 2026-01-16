# TFX Trainer GPU Image with TensorFlow Recommenders and ScaNN
#
# GPU-enabled extension of the TFX trainer for full-scale model training.
# Based on Google Deep Learning Container with TFX, TFRS, and ScaNN added.
#
# Location: europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer-gpu
#
# Key differences from CPU trainer (tfx-trainer):
# - GPU support via CUDA (included in DL Container)
# - NCCL for multi-GPU communication (MirroredStrategy)
# - TF_FORCE_GPU_ALLOW_GROWTH for memory optimization
#
# Build command:
#   cd cloudbuild/tfx-trainer-gpu
#   gcloud builds submit --config=cloudbuild.yaml --project=b2b-recs

# Use Google Deep Learning Container with TF 2.15 and Python 3.10
# This ensures compatibility with TFX 1.15.0 which requires Python 3.9-3.10
# Reference: https://cloud.google.com/deep-learning-containers/docs/choosing-container
FROM gcr.io/deeplearning-platform-release/tf2-gpu.2-15.py310

LABEL maintainer="B2B Recs Platform"
LABEL description="TFX Trainer with GPU support for TFRS models"
LABEL version="1.0.0"
LABEL tfx_version="1.15.0"
LABEL tensorflow_version="2.15.x"
LABEL python_version="3.10"

# Install system dependencies for multi-GPU training
# Note: Google DL containers already include NCCL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set environment variables for GPU training
ENV NCCL_DEBUG=INFO
ENV TF_FORCE_GPU_ALLOW_GROWTH=true

# Install TFX and core dependencies
# TFX 1.15.0 is compatible with TensorFlow 2.15.x and Python 3.9-3.10
RUN pip install --no-cache-dir \
    tfx==1.15.0 \
    kfp>=2.0.0

# Install TensorFlow Recommenders (compatible with TF 2.15)
RUN pip install --no-cache-dir tensorflow-recommenders>=0.7.3

# Install ScaNN for approximate nearest neighbor search
# ScaNN 1.3.0 is compiled against TensorFlow 2.15
# Use --no-deps to prevent dependency conflicts
RUN pip install --no-cache-dir --no-deps scann==1.3.0

# Install additional Google Cloud SDKs for pipeline artifacts
RUN pip install --no-cache-dir \
    google-cloud-aiplatform>=1.38.0 \
    google-cloud-storage>=2.14.0 \
    google-cloud-bigquery>=3.14.0

# Verify TensorFlow installation and GPU support
RUN python -c "\
import tensorflow as tf; \
print(f'TensorFlow version: {tf.__version__}'); \
print(f'CUDA built: {tf.test.is_built_with_cuda()}'); \
print(f'GPU devices: {tf.config.list_physical_devices(\"GPU\")}'); \
"

# Verify TFX installation
RUN python -c "import tfx; print(f'TFX version: {tfx.__version__}')"

# Verify TFRS installation
RUN python -c "import tensorflow_recommenders as tfrs; print(f'TFRS version: {tfrs.__version__}')"

# Verify ScaNN installation
RUN python -c "import scann; print('ScaNN: installed')"
RUN python -c "from tensorflow_recommenders.layers.factorized_top_k import ScaNN; print('ScaNN layer: available')"

# Verify KFP for pipeline submission
RUN python -c "import kfp; print(f'KFP version: {kfp.__version__}')"

# Verify TFX components
RUN python -c "\
from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen; \
from tfx.components import StatisticsGen, SchemaGen, Transform, Trainer, Evaluator, Pusher; \
print('TFX Components: OK'); \
"

# Verify multi-GPU strategy is available
RUN python -c "\
import tensorflow as tf; \
strategy = tf.distribute.MirroredStrategy(); \
print(f'MirroredStrategy: available (replicas: {strategy.num_replicas_in_sync})'); \
"

# Set working directory
WORKDIR /workspace

# Default command (will be overridden by Cloud Build or Vertex AI)
CMD ["python", "--version"]
