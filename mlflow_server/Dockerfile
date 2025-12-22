# MLflow Tracking Server for Cloud Run
# Uses Python 3.10 for compatibility with ML ecosystem

FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install system dependencies for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as non-root user for security
RUN useradd -m -u 1000 mlflow
USER mlflow

EXPOSE 8080

# Run MLflow server directly
# Environment variables required:
# - MLFLOW_BACKEND_STORE_URI: PostgreSQL connection string
# - MLFLOW_ARTIFACT_ROOT: GCS bucket for artifacts
CMD mlflow server \
    --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
    --default-artifact-root "${MLFLOW_ARTIFACT_ROOT}" \
    --host 0.0.0.0 \
    --port ${PORT} \
    --serve-artifacts \
    --workers 2
