#!/bin/bash
set -e

# MLflow Tracking Server Entrypoint
#
# Environment variables expected:
# - MLFLOW_BACKEND_STORE_URI: PostgreSQL connection string
#   Format: postgresql://user:pass@host:5432/mlflow
#   Or with Cloud SQL: postgresql://user:pass@/mlflow?host=/cloudsql/PROJECT:REGION:INSTANCE
# - MLFLOW_ARTIFACT_ROOT: GCS bucket for artifacts
#   Format: gs://bucket-name/path
# - PORT: Server port (default 8080, set by Cloud Run)

# Default values
PORT="${PORT:-8080}"
WORKERS="${MLFLOW_WORKERS:-2}"

# Validate required environment variables
if [ -z "$MLFLOW_BACKEND_STORE_URI" ]; then
    echo "ERROR: MLFLOW_BACKEND_STORE_URI is not set"
    exit 1
fi

if [ -z "$MLFLOW_ARTIFACT_ROOT" ]; then
    echo "ERROR: MLFLOW_ARTIFACT_ROOT is not set"
    exit 1
fi

echo "Starting MLflow Tracking Server..."
echo "  Backend Store: ${MLFLOW_BACKEND_STORE_URI%%@*}@[REDACTED]"
echo "  Artifact Root: ${MLFLOW_ARTIFACT_ROOT}"
echo "  Port: ${PORT}"
echo "  Workers: ${WORKERS}"

# Start MLflow server
exec mlflow server \
    --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
    --default-artifact-root "${MLFLOW_ARTIFACT_ROOT}" \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --serve-artifacts \
    --workers "${WORKERS}"
