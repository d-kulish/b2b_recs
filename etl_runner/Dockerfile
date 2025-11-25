# Use official Python runtime as base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies with proper upgrade handling
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Verify critical imports work (catches namespace package conflicts early)
RUN python -c "from google.cloud import firestore; print('✓ Firestore import successful')" && \
    python -c "from google.cloud import bigquery; print('✓ BigQuery import successful')" && \
    python -c "from google.cloud import storage; print('✓ Storage import successful')" && \
    python -c "import apache_beam; print('✓ Apache Beam import successful')"

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 etl && chown -R etl:etl /app
USER etl

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Entry point
ENTRYPOINT ["python", "main.py"]
