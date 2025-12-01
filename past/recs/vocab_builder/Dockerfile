FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code with product metadata support
COPY main.py .

# Set the entrypoint
ENTRYPOINT ["python", "main.py"]