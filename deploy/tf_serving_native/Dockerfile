# Native TensorFlow Serving container for Cloud Run deployment
# Optimized for non-ScaNN models with ~10-15ms lower latency than Python server
#
# Based on official TensorFlow Serving image with gsutil for GCS model download

FROM tensorflow/serving:2.19.0

LABEL maintainer="B2B Recs Platform"
LABEL description="Native TensorFlow Serving for non-ScaNN TFRS models"

# Install gsutil for GCS model download
RUN apt-get update && apt-get install -y curl gnupg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Copy configuration files
COPY batching_config.txt /etc/tf_serving/batching_config.txt
COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

# Environment variables (can be overridden at runtime)
ENV MODEL_BASE_PATH=/models
ENV MODEL_NAME=recommender
ENV PORT=8501

# Expose REST API port (Cloud Run uses this)
EXPOSE 8501

# Use startup script as entrypoint
ENTRYPOINT ["/startup.sh"]
