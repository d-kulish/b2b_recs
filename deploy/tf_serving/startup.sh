#!/bin/bash
set -e

# MODEL_PATH should be set to GCS path, e.g., gs://bucket/training-runs/47/pushed_model
if [ -z "$MODEL_PATH" ]; then
    echo "ERROR: MODEL_PATH environment variable not set"
    echo "Usage: docker run -e MODEL_PATH=gs://bucket/path/to/pushed_model ..."
    exit 1
fi

echo "==================================================="
echo "TF Serving Container Startup"
echo "==================================================="
echo "MODEL_PATH: $MODEL_PATH"
echo "MODEL_NAME: ${MODEL_NAME:-recommender}"
echo "PORT: ${PORT:-8501}"
echo ""

# Create model directory structure
# TF Serving expects: /models/{model_name}/{version}/
MODEL_DIR="/models/${MODEL_NAME:-recommender}/1"
mkdir -p "$MODEL_DIR"

echo "Downloading model from $MODEL_PATH..."
gsutil -m cp -r "$MODEL_PATH/*" "$MODEL_DIR/"

# Verify model was downloaded
if [ ! -f "$MODEL_DIR/saved_model.pb" ]; then
    echo "ERROR: saved_model.pb not found in $MODEL_DIR"
    echo "Contents of $MODEL_DIR:"
    ls -la "$MODEL_DIR" || echo "Directory is empty"
    exit 1
fi

echo "Model downloaded successfully to $MODEL_DIR"
echo "Contents:"
ls -la "$MODEL_DIR"
echo ""

echo "Starting TensorFlow Serving..."
echo "  - Model: ${MODEL_NAME:-recommender}"
echo "  - REST API port: ${PORT:-8501}"
echo "  - gRPC port: 8500"
echo "  - Batching: enabled"
echo ""

# Start TF Serving with batching enabled
# Cloud Run sets PORT env var for the container to listen on
tensorflow_model_server \
    --port=8500 \
    --rest_api_port=${PORT:-8501} \
    --model_name=${MODEL_NAME:-recommender} \
    --model_base_path=/models/${MODEL_NAME:-recommender} \
    --enable_batching=true \
    --batching_parameters_file=/etc/tf_serving/batching_config.txt
