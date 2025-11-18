# Django App Dockerfile for Cloud Run
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files (use dummy SECRET_KEY for build)
ENV DJANGO_SECRET_KEY=dummy-secret-key-for-collectstatic
RUN python manage.py collectstatic --noinput

# Create non-root user for security
RUN useradd -m -u 1000 django && chown -R django:django /app
USER django

# Expose port
EXPOSE 8080

# Run gunicorn
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 0 config.wsgi:application
