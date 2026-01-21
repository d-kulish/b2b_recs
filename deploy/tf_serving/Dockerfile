# Python-based model serving container for Cloud Run deployment
# Uses TensorFlow directly (not TF Serving) to properly load ScaNN models
# Based on Google Deep Learning Container for TF 2.15 + Python 3.10 compatibility

FROM gcr.io/deeplearning-platform-release/tf2-cpu.2-15.py310

LABEL maintainer="B2B Recs Platform"
LABEL description="Python model server with ScaNN support for TFRS models"

# Install gsutil for GCS model download
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - \
    && apt-get update && apt-get install -y google-cloud-cli \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install ScaNN and Flask for serving
RUN pip install --no-cache-dir --no-deps scann==1.3.0
RUN pip install --no-cache-dir flask gunicorn

# Verify ScaNN installation
RUN python -c "import scann; print('ScaNN: installed')"
RUN python -c "import tensorflow as tf; import scann; print('TF + ScaNN: OK')"

# Copy server files
COPY server.py /app/server.py
COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

# Environment variables (can be overridden at runtime)
ENV MODEL_BASE_PATH=/models
ENV MODEL_NAME=recommender
ENV PORT=8501

# Expose REST API port (Cloud Run uses this)
EXPOSE 8501

# Working directory
WORKDIR /app

# Use startup script as entrypoint
ENTRYPOINT ["/startup.sh"]
