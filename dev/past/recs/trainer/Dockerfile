# Single VM Multi-GPU Optimized TensorFlow Docker Image with Early Stopping
FROM tensorflow/tensorflow:2.16.2-gpu

# Install additional dependencies for multi-GPU training
RUN apt-get update && apt-get install -y \
    git \
    libnccl2 \
    libnccl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set NCCL environment variables for optimal GPU communication within single VM
ENV NCCL_DEBUG=INFO
# Note: No need for TF_USE_LEGACY_KERAS as MirroredStrategy works fine with Keras 3

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the v2 trainer code with random split (production stable)
COPY main_v2.py .

# Set the entrypoint to use the v2 trainer
ENTRYPOINT ["python", "main_v2.py"]