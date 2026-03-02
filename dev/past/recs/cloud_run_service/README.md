# Metro Recommender Cloud Run Service

FastAPI-based REST API service for serving Metro Recommender model predictions on Google Cloud Run with **batch processing capabilities** for high-throughput recommendation serving.

## Features
- **BATCH PROCESSING** - Handle up to 1000 customers in single request
- **Scalable** Cloud Run deployment with auto-scaling
- **Production Ready** - Deployed and validated with real customer data

## API Endpoints

### Core Endpoints

- **GET `/health`** - Health check and service status with batch processing info
- **POST `/recommend`** - Get product recommendations (individual customer)
- **POST `/recommend-batch`** - Get recommendations for multiple customers (NEW)
- **GET `/model-info`** - Model metadata and performance metrics
- **GET `/`** - Service information and endpoint listing

## Request/Response Format

### Individual Recommendation Request
```json
{
  "customer_id": "100000956201",
  "city": "ODESA",
  "revenue": 100.0,
  "timestamp": 1722347400,
  "num_recommendations": 10
}
```

### Batch Recommendation Request (NEW)
```json
{
  "requests": [
    {"customer_id": "100001", "city": "ODESA", "revenue": 100.0},
    {"customer_id": "100002", "city": "TERNOPIL", "revenue": 200.0},
    {"customer_id": "100003", "city": "LUTSK", "revenue": 150.0}
  ],
  "num_recommendations": 100
}
```

### Batch Response Format
```json
{
  "batch_size": 3,
  "total_inference_time_ms": 8.45,
  "avg_inference_time_ms": 2.82,
  "processing_mode": "batch",
  "model_version": "v6-single-vm-multigpu",
  "results": [
    {
      "customer_id": "100001",
      "recommendations": [
        {"product_id": "380929001001", "score": 951.31, "rank": 1},
        {"product_id": "268370001001", "score": 951.12, "rank": 2}
      ],
      "inference_time_ms": 2.8
    }
  ]
}
```

## Local Testing

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables
```bash
export MODEL_BASE_PATH="/path/to/model"
export VOCAB_PATH="/path/to/vocab/vocabularies.json"
export PORT=9090
```

### 3. Run Service Locally
```bash
python main.py
```

### 4. Test Batch Processing
```bash
# Health check
curl http://localhost:9090/health

# Individual recommendation
curl -X POST "http://localhost:9090/recommend" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "100000956201", "city": "ODESA", "revenue": 100.0, "num_recommendations": 5}'

# Batch recommendations
curl -X POST "http://localhost:9090/recommend-batch" \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"customer_id": "100001", "city": "ODESA", "revenue": 100.0},
      {"customer_id": "100002", "city": "TERNOPIL", "revenue": 200.0}
    ],
    "num_recommendations": 10
  }'
```

## Cloud Run Deployment

### Current Deployment
- **Service URL**: `https://metro-recommender-1032729337493.europe-west4.run.app`
- **Status**: Production Ready - BATCH PROCESSING ENABLED
- **Performance**: 2ms average inference time per customer, **47% Recall@100**
- **Batch Capability**: Up to 1000 customers per request

### Build and Deploy Process

# Deploy to Cloud Run
gcloud run deploy metro-recommender \
  --image $IMAGE_URI \
  --platform managed \
  --region europe-west4 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 600 \
  --concurrency 10 \
  --max-instances 5 \
  --cpu-throttling \
  --cpu-boost \
  --min-instances=1
```

### Testing Production Deployment
```bash
# Test health endpoint
curl -X GET "https://metro-recommender-1032729337493.europe-west4.run.app/health" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token --audiences=https://metro-recommender-1032729337493.europe-west4.run.app)"

# Test batch processing
curl -X POST "https://metro-recommender-1032729337493.europe-west4.run.app/recommend-batch" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token --audiences=https://metro-recommender-1032729337493.europe-west4.run.app)" \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"customer_id": "100001", "city": "ODESA", "revenue": 100.0},
      {"customer_id": "100002", "city": "TERNOPIL", "revenue": 200.0}
    ],
    "num_recommendations": 100
  }'
```
