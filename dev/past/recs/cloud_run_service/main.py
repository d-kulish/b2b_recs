#!/usr/bin/env python3
"""
Metro Recommender Cloud Run Service with Batch Processing - FastAPI Application
Serves trained recommendation models via REST API with support for batch processing up to 1000 requests
"""

import os
import time
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import asyncio

import tensorflow as tf
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pydantic models for request/response
class RecommendationRequest(BaseModel):
    customer_id: str = Field(..., description="Customer ID")
    city: str = Field(..., description="City name")
    revenue: float = Field(..., description="Revenue amount")
    timestamp: Optional[int] = Field(default=None, description="Unix timestamp (optional, uses current time if not provided)")
    num_recommendations: int = Field(default=100, ge=1, le=100, description="Number of recommendations")

class BatchCustomerRequest(BaseModel):
    customer_id: str = Field(..., description="Customer ID")
    city: str = Field(..., description="City name")
    revenue: float = Field(..., description="Revenue amount")
    timestamp: Optional[int] = Field(default=None, description="Unix timestamp (optional)")

class BatchRecommendationRequest(BaseModel):
    requests: List[BatchCustomerRequest] = Field(..., description="List of customer requests", min_length=1, max_length=1000)
    num_recommendations: int = Field(default=100, ge=1, le=100, description="Number of recommendations per customer")

class CustomerRecommendation(BaseModel):
    customer_id: str
    recommendations: List[Dict[str, Any]]
    inference_time_ms: float

class BatchRecommendationResponse(BaseModel):
    results: List[CustomerRecommendation]
    batch_size: int
    total_inference_time_ms: float
    avg_inference_time_ms: float
    model_version: str
    processing_mode: str  # 'batch' or 'chunked'

class RecommendationResponse(BaseModel):
    recommendations: List[Dict[str, Any]]
    model_version: str
    inference_time_ms: float
    total_products: int

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str
    timestamp: str
    batch_processing_enabled: bool
    max_batch_size: int

class ModelInfoResponse(BaseModel):
    model_version: str
    vocabularies: Dict[str, int]
    hyperparameters: Dict[str, Any]
    performance_metrics: Dict[str, float]
    batch_capabilities: Dict[str, Any]

class BatchMetrics(BaseModel):
    total_batches_processed: int
    total_customers_processed: int
    avg_batch_size: float
    avg_processing_time_ms: float
    p95_processing_time_ms: float
    largest_batch_size: int
    total_errors: int

# Global variables for models and vocabularies
saved_model = None
model_metadata = None

# Batch processing metrics
batch_metrics = {
    "total_batches": 0,
    "total_customers": 0,
    "batch_sizes": [],
    "processing_times": [],
    "errors": 0
}

# Thread pool for async batch processing
executor = ThreadPoolExecutor(max_workers=4)

# Configuration from environment variables
MODEL_BASE_PATH = os.getenv('MODEL_BASE_PATH', '/app/model')
VOCAB_PATH = os.getenv('VOCAB_PATH', '/app/vocab/vocabularies.json')
PORT = int(os.getenv('PORT', 8080))
MAX_BATCH_SIZE = int(os.getenv('MAX_BATCH_SIZE', 1000))
CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', 100))  # Process large batches in chunks

# Download models from GCS to local temp if needed
def download_models_if_needed():
    """Download models from GCS to local filesystem if MODEL_BASE_PATH is a GCS path."""
    global MODEL_BASE_PATH, VOCAB_PATH
    
    if MODEL_BASE_PATH.startswith('gs://'):
        logger.info(f"Downloading model from GCS: {MODEL_BASE_PATH}")
        import subprocess
        
        # Create local temp directories
        os.makedirs('/tmp/model', exist_ok=True)
        os.makedirs('/tmp/vocab', exist_ok=True)
        
        try:
            # Download model files
            logger.info("Downloading saved_model...")
            subprocess.run(['gsutil', '-m', 'cp', '-r', f'{MODEL_BASE_PATH}/saved_model', '/tmp/model/'], 
                         check=True, capture_output=True, text=True)
            
            logger.info("Downloading model_metadata.json...")
            subprocess.run(['gsutil', 'cp', f'{MODEL_BASE_PATH}/model_metadata.json', '/tmp/model/'], 
                         check=True, capture_output=True, text=True)
            
            logger.info("Downloading vocabularies.json...")
            subprocess.run(['gsutil', 'cp', VOCAB_PATH, '/tmp/vocab/vocabularies.json'], 
                         check=True, capture_output=True, text=True)
            
            # Update paths to local
            MODEL_BASE_PATH = '/tmp/model'
            VOCAB_PATH = '/tmp/vocab/vocabularies.json'
            
            logger.info(f"✅ Models downloaded successfully to local filesystem")
            logger.info(f"   Model path: {MODEL_BASE_PATH}")
            logger.info(f"   Vocab path: {VOCAB_PATH}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to download models from GCS: {e}")
            raise RuntimeError(f"Failed to download models: {e}")
    else:
        logger.info(f"Using local model path: {MODEL_BASE_PATH}")

# Download models before loading
download_models_if_needed()

# Initialize FastAPI app
app = FastAPI(
    title="Metro Recommender API with Batch Processing",
    description="Product recommendation service with batch processing support (up to 1000 customers)",
    version="2.0.0"
)

def load_saved_model():
    """Load the production-ready saved model with serving signature."""
    global saved_model
    
    saved_model_path = f"{MODEL_BASE_PATH}/saved_model"
    logger.info(f"Loading saved model from: {saved_model_path}")
    
    try:
        saved_model = tf.saved_model.load(saved_model_path)
        
        # Check if serving signature exists
        if 'serving_default' in saved_model.signatures:
            logger.info("✅ Saved model loaded with serving signature")
            return True
        else:
            logger.error("❌ Saved model doesn't have serving signature")
            return False
            
    except Exception as e:
        logger.error(f"Failed to load saved model: {e}")
        return False

def load_model_metadata():
    """Load model metadata from local file or GCS."""
    global model_metadata
    
    metadata_path = f"{MODEL_BASE_PATH}/model_metadata.json"
    logger.info(f"Loading model metadata from: {metadata_path}")
    
    # Check if it's a local file path
    if not metadata_path.startswith('gs://'):
        # Local filesystem
        try:
            with open(metadata_path, 'r') as f:
                model_metadata = json.load(f)
            logger.info(f"Loaded model metadata from local file for version: {model_metadata['model_version']}")
            return True
        except Exception as e:
            logger.error(f"Failed to load local model metadata: {e}")
            return False
    
    # GCS path - try tf.io.gfile first, then fallback to gsutil
    try:
        # Try tf.io.gfile first
        with tf.io.gfile.GFile(metadata_path, 'r') as f:
            model_metadata = json.load(f)
        logger.info(f"Loaded model metadata for version: {model_metadata['model_version']}")
        return True
    except Exception as e:
        logger.warning(f"tf.io.gfile failed: {e}, trying gsutil fallback...")
        
        # Fallback to downloading with gsutil
        try:
            import subprocess
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp:
                result = subprocess.run(['gsutil', 'cat', metadata_path], 
                                      capture_output=True, text=True, check=True)
                tmp.write(result.stdout)
                tmp.flush()
                
                # Read the downloaded file
                with open(tmp.name, 'r') as f:
                    model_metadata = json.load(f)
                
                os.unlink(tmp.name)  # Clean up
                logger.info(f"Loaded model metadata via gsutil for version: {model_metadata['model_version']}")
                return True
                
        except Exception as e2:
            logger.error(f"Failed to load model metadata with both methods: {e2}")
            return False

def validate_model():
    """Validate that the saved model works correctly with batch processing."""
    logger.info("Validating saved model with batch support...")
    
    try:
        # Test single inference
        result = saved_model.signatures['serving_default'](
            customer_id=tf.constant('100000956201'),
            city=tf.constant('TERNOPIL'),
            revenue=tf.constant(100.0),
            timestamp=tf.constant(int(time.time()), dtype=tf.int64)
        )
        
        # Check that we get expected output structure
        if 'product_ids' in result and 'scores' in result:
            num_products = len(result['product_ids'])
            logger.info(f" Single inference validation successful - returns {num_products} products")
        else:
            logger.error(" Model validation failed - unexpected output structure")
            return False
        
        # Model only supports single requests - batch processing done in application layer
        logger.info(" Model validation successful - ready for batch processing")
        return True
            
    except Exception as e:
        logger.error(f"Model validation failed: {e}")
        import traceback
        logger.error(f"Error details: {traceback.format_exc()}")
        return False

def initialize_service():
    """Initialize the recommendation service with batch processing support."""
    logger.info("🚀 Initializing Metro Recommender Service with Batch Processing...")
    logger.info(f"📊 Max batch size: {MAX_BATCH_SIZE}")
    logger.info(f"📦 Chunk size for large batches: {CHUNK_SIZE}")
    
    # Load model metadata
    if not load_model_metadata():
        raise RuntimeError("Failed to load model metadata")
    
    # Load saved model with serving signature
    if not load_saved_model():
        raise RuntimeError("Failed to load saved model")
    
    # Validate model works correctly with batches
    if not validate_model():
        raise RuntimeError("Model validation failed")
    
    logger.info(" Service initialized with batch processing support")

def get_recommendations(customer_id: str, city: str, revenue: float, timestamp: int, num_recommendations: int) -> tuple[List[Dict[str, Any]], float]:
    """Generate recommendations for a single customer."""
    start_time = time.time()
    
    try:
        # Call the saved model's serving signature with timestamp
        result = saved_model.signatures['serving_default'](
            customer_id=tf.constant(customer_id),
            city=tf.constant(city),
            revenue=tf.constant(revenue),
            timestamp=tf.constant(timestamp, dtype=tf.int64)
        )
        
        # Extract product IDs and scores
        product_ids = result['product_ids'].numpy()
        scores = result['scores'].numpy()
        
        # Build recommendations list (limit to requested number)
        recommendations = []
        for i in range(min(num_recommendations, len(product_ids))):
            recommendations.append({
                'product_id': product_ids[i].decode('utf-8'),
                'score': float(scores[i]),
                'rank': i + 1
            })
        
        inference_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        return recommendations, inference_time
        
    except Exception as e:
        logger.error(f"Error in get_recommendations: {e}")
        raise

def process_batch_chunk(customer_ids: List[str], cities: List[str], revenues: List[float], 
                       timestamps: List[int], num_recommendations: int) -> List[CustomerRecommendation]:
    """Process a chunk of batch requests by iterating through individual requests."""
    results = []
    
    for i, customer_id in enumerate(customer_ids):
        customer_start_time = time.time()
        
        try:
            # Process individual request (model only supports scalar inputs)
            predictions = saved_model.signatures['serving_default'](
                customer_id=tf.constant(customer_id),
                city=tf.constant(cities[i]),
                revenue=tf.constant(revenues[i]),
                timestamp=tf.constant(timestamps[i], dtype=tf.int64)
            )
            
            # Extract product IDs and scores for this customer
            product_ids = predictions['product_ids'].numpy()
            scores = predictions['scores'].numpy()
            
            # Initialize recommendations list for this customer
            recommendations = []
            for j in range(min(num_recommendations, len(product_ids))):
                product_id = product_ids[j]
                # Handle both string and bytes
                if isinstance(product_id, bytes):
                    product_id = product_id.decode('utf-8')
                
                recommendations.append({
                    "rank": j + 1,
                    "product_id": product_id,
                    "score": float(scores[j])
                })
            
            inference_time_ms = (time.time() - customer_start_time) * 1000
            
            results.append(CustomerRecommendation(
                customer_id=customer_id,
                recommendations=recommendations,
                inference_time_ms=inference_time_ms
            ))
            
        except Exception as e:
            logger.error(f"Error processing customer {customer_id}: {e}")
            # Add empty result for failed customer
            results.append(CustomerRecommendation(
                customer_id=customer_id,
                recommendations=[],
                inference_time_ms=0.0
            ))
    
    return results

def process_batch_in_chunks(requests: List[BatchCustomerRequest], num_recommendations: int, 
                           chunk_size: int = CHUNK_SIZE) -> List[CustomerRecommendation]:
    """Process large batches in smaller chunks to avoid memory issues."""
    all_results = []
    
    for i in range(0, len(requests), chunk_size):
        chunk = requests[i:i+chunk_size]
        
        # Extract data for this chunk
        customer_ids = [req.customer_id for req in chunk]
        cities = [req.city for req in chunk]
        revenues = [req.revenue for req in chunk]
        timestamps = [req.timestamp if req.timestamp else int(time.time()) for req in chunk]
        
        # Process chunk
        chunk_results = process_batch_chunk(
            customer_ids, cities, revenues, timestamps, num_recommendations
        )
        
        all_results.extend(chunk_results)
        
        logger.info(f"Processed chunk {i//chunk_size + 1}/{(len(requests) + chunk_size - 1)//chunk_size}")
    
    return all_results

def update_batch_metrics(batch_size: int, processing_time_ms: float):
    """Update batch processing metrics."""
    batch_metrics["total_batches"] += 1
    batch_metrics["total_customers"] += batch_size
    batch_metrics["batch_sizes"].append(batch_size)
    batch_metrics["processing_times"].append(processing_time_ms)
    
    # Keep only last 1000 measurements to avoid memory issues
    if len(batch_metrics["batch_sizes"]) > 1000:
        batch_metrics["batch_sizes"] = batch_metrics["batch_sizes"][-1000:]
        batch_metrics["processing_times"] = batch_metrics["processing_times"][-1000:]

# API Routes

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with batch processing status."""
    return HealthResponse(
        status="healthy",
        model_loaded=saved_model is not None,
        model_version=model_metadata['model_version'] if model_metadata else "unknown",
        timestamp=datetime.now().isoformat(),
        batch_processing_enabled=True,
        max_batch_size=MAX_BATCH_SIZE
    )

@app.post("/recommend", response_model=RecommendationResponse)
async def recommend(request: RecommendationRequest):
    """Generate product recommendations for a single customer."""
    
    if saved_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Use provided timestamp or current time
        timestamp = request.timestamp
        if timestamp is None:
            timestamp = int(time.time())
        
        recommendations, inference_time = get_recommendations(
            customer_id=request.customer_id,
            city=request.city,
            revenue=request.revenue,
            timestamp=timestamp,
            num_recommendations=request.num_recommendations
        )
        
        return RecommendationResponse(
            recommendations=recommendations,
            model_version=model_metadata['model_version'],
            inference_time_ms=inference_time,
            total_products=model_metadata['vocabularies']['num_products']
        )
        
    except Exception as e:
        logger.error(f"Recommendation error: {e}")
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")

@app.post("/recommend-batch", response_model=BatchRecommendationResponse)
async def recommend_batch(batch_request: BatchRecommendationRequest):
    """Generate recommendations for multiple customers in a single batch (up to 1000)."""
    
    if saved_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    start_time = time.time()
    batch_size = len(batch_request.requests)
    
    logger.info(f"Processing batch of {batch_size} customers")
    
    try:
        # Determine processing mode based on batch size
        if batch_size <= CHUNK_SIZE:
            # Process as single batch
            processing_mode = "batch"
            customer_ids = [req.customer_id for req in batch_request.requests]
            cities = [req.city for req in batch_request.requests]
            revenues = [req.revenue for req in batch_request.requests]
            timestamps = [req.timestamp if req.timestamp else int(time.time()) for req in batch_request.requests]
            
            results = process_batch_chunk(
                customer_ids, cities, revenues, timestamps, 
                batch_request.num_recommendations
            )
        else:
            # Process in chunks
            processing_mode = "chunked"
            results = process_batch_in_chunks(
                batch_request.requests, 
                batch_request.num_recommendations
            )
        
        # Calculate timing
        total_time_ms = (time.time() - start_time) * 1000
        avg_time_ms = total_time_ms / batch_size
        
        # Update metrics
        update_batch_metrics(batch_size, total_time_ms)
        
        logger.info(f"Batch processed: {batch_size} customers in {total_time_ms:.2f}ms "
                   f"(avg: {avg_time_ms:.2f}ms/customer)")
        
        return BatchRecommendationResponse(
            results=results,
            batch_size=batch_size,
            total_inference_time_ms=total_time_ms,
            avg_inference_time_ms=avg_time_ms,
            model_version=model_metadata.get("model_version", "unknown") if model_metadata else "unknown",
            processing_mode=processing_mode
        )
        
    except Exception as e:
        batch_metrics["errors"] += 1
        logger.error(f"Batch inference failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch inference failed: {str(e)}")

@app.post("/recommend-batch-async")
async def recommend_batch_async(batch_request: BatchRecommendationRequest):
    """Async batch processing for better concurrency."""
    
    if saved_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # Run batch processing in thread pool
    loop = asyncio.get_event_loop()
    
    try:
        # Process asynchronously
        result = await loop.run_in_executor(
            executor,
            process_batch_in_chunks,
            batch_request.requests,
            batch_request.num_recommendations
        )
        
        # Calculate metrics
        batch_size = len(batch_request.requests)
        total_time_ms = sum(r.inference_time_ms for r in result)
        avg_time_ms = total_time_ms / batch_size if batch_size > 0 else 0
        
        return BatchRecommendationResponse(
            results=result,
            batch_size=batch_size,
            total_inference_time_ms=total_time_ms,
            avg_inference_time_ms=avg_time_ms,
            model_version=model_metadata.get("model_version", "unknown") if model_metadata else "unknown",
            processing_mode="async_chunked"
        )
        
    except Exception as e:
        logger.error(f"Async batch processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Async batch processing failed: {str(e)}")

@app.get("/batch-metrics", response_model=BatchMetrics)
async def get_batch_metrics():
    """Get batch processing metrics and statistics."""
    
    if len(batch_metrics["batch_sizes"]) == 0:
        return BatchMetrics(
            total_batches_processed=0,
            total_customers_processed=0,
            avg_batch_size=0,
            avg_processing_time_ms=0,
            p95_processing_time_ms=0,
            largest_batch_size=0,
            total_errors=batch_metrics["errors"]
        )
    
    return BatchMetrics(
        total_batches_processed=batch_metrics["total_batches"],
        total_customers_processed=batch_metrics["total_customers"],
        avg_batch_size=np.mean(batch_metrics["batch_sizes"]),
        avg_processing_time_ms=np.mean(batch_metrics["processing_times"]),
        p95_processing_time_ms=np.percentile(batch_metrics["processing_times"], 95),
        largest_batch_size=max(batch_metrics["batch_sizes"]),
        total_errors=batch_metrics["errors"]
    )

@app.get("/model-info", response_model=ModelInfoResponse)
async def get_model_info():
    """Get model information and metadata with batch capabilities."""
    
    if model_metadata is None:
        raise HTTPException(status_code=503, detail="Model metadata not loaded")
    
    return ModelInfoResponse(
        model_version=model_metadata['model_version'],
        vocabularies=model_metadata['vocabularies'],
        hyperparameters=model_metadata['hyperparameters'],
        performance_metrics=model_metadata['metrics']['test_metrics'],
        batch_capabilities={
            "max_batch_size": MAX_BATCH_SIZE,
            "chunk_size": CHUNK_SIZE,
            "async_processing": True,
            "endpoints": ["/recommend-batch", "/recommend-batch-async"]
        }
    )

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Metro Recommender API with Batch Processing",
        "version": "2.0.0",
        "status": "running",
        "batch_processing": {
            "enabled": True,
            "max_batch_size": MAX_BATCH_SIZE,
            "chunk_size": CHUNK_SIZE
        },
        "endpoints": {
            "health": "/health",
            "recommend": "/recommend (single)",
            "recommend_batch": "/recommend-batch (up to 1000)",
            "recommend_batch_async": "/recommend-batch-async (async processing)",
            "batch_metrics": "/batch-metrics",
            "model_info": "/model-info",
            "docs": "/docs"
        }
    }

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    try:
        initialize_service()
        logger.info("🎉 Metro Recommender Service with Batch Processing started successfully")
        logger.info(f"📊 Max batch size: {MAX_BATCH_SIZE} customers")
        logger.info(f"📦 Processing chunks of: {CHUNK_SIZE} customers")
    except Exception as e:
        logger.error(f"Failed to initialize service: {e}")
        raise

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    executor.shutdown(wait=True)
    logger.info("Service shutdown complete")

if __name__ == "__main__":
    # Run the service
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        access_log=True
    )