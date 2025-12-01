# VocabBuilder Component - Enhanced with Product Metadata

The VocabBuilder extracts vocabularies from TFRecord files with product metadata, creating comprehensive vocabulary mappings for enhanced model training with product intelligence.

## Overview

This component:
- Extracts vocabularies from compressed TFRecord files (complete dataset approach)
- **Processes 8 features**: customer_id, product_id, revenue, city, timestamp, **art_name, categories, subcategories**
- Creates discrete vocabulary mappings for categorical features including **product metadata**
- Generates configurable revenue buckets for customer segmentation
- Creates timestamp buckets for temporal pattern analysis  
- **Builds product metadata vocabularies** for enhanced product understanding
- Computes comprehensive statistics for all features
- Outputs vocabularies in JSON format compatible with trainer

## Enhanced Product Metadata Processing

### Features Processed

| Feature | Type | Processing | Description |
|---------|------|------------|-------------|
| `cust_person_id` | string | Sorted unique customer IDs | Customer identifiers |
| `product_id` | int64 | Converted to strings, sorted unique product IDs | Product identifiers |
| `revenue` | float32 | Statistical analysis + bucket creation | Customer total revenue |
| `city` | string | Sorted unique city names | Transaction cities |
| `timestamp` | int64 | Unix timestamps + bucket creation | Temporal patterns |
| **`art_name`** | **string** | **Unique product names vocabulary** | **Product names in local language** |
| **`stratbuy_domain_desc`** | **string** | **Unique category vocabulary** | **Product categories (24 unique)** |
| **`mge_main_cat_desc`** | **string** | **Unique subcategory vocabulary** | **Product subcategories (125 unique)** |

### Key Product Metadata Enhancements

- **Product Names**: Full vocabulary of product names in local language
- **Categories**: ~24 unique product categories (Dairy, Electronics, Fresh Produce, etc.)
- **Subcategories**: ~125 unique subcategories (Milk Products, Smartphones, Fruits, etc.)
- **Hierarchical Structure**: Category → Subcategory → Product mapping for intelligent recommendations

### Enhanced Characteristics

- **Complete dataset processing**: Processes all data from `all_data/` folder
- **Multi-city support**: Handles multiple cities in single vocabulary extraction
- **Product intelligence**: Creates metadata vocabularies for enhanced product understanding
- **Configurable buckets**: Default 1000 revenue buckets, 100 timestamp buckets
- **Batch processing**: Processes in batches of 1000 examples for memory efficiency
- **Metadata validation**: Handles missing product metadata gracefully with fallback values

## Usage

### Command Line

```bash
python main.py \
    --input_path "gs://bucket/all_data/*.tfrecord.gz" \
    --output_path "gs://bucket/vocabularies" \
    --num_revenue_buckets 1000
```

### As Vertex AI Custom Job

```python
job_spec = {
    "display_name": f"vocab-builder-metadata-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    "job_spec": {
        "worker_pool_specs": [{
            "machine_spec": {"machine_type": "n1-standard-4"},
            "replica_count": 1,
            "container_spec": {
                "image_uri": "europe-west4-docker.pkg.dev/PROJECT_ID/metro-recs-repo/vocab_builder:latest",
                "command": ["python", "main.py"],
                "args": [
                    "--input_path", "gs://bucket/all_data/*.tfrecord.gz",
                    "--output_path", "gs://bucket/vocabularies",
                    "--num_revenue_buckets", "1000"
                ]
            }
        }],
        "service_account": "your-service-account@project.iam.gserviceaccount.com"
    }
}
```


## Enhanced Input Format

Expects TFRecord files with product metadata schema (from DataExtractor with metadata):
```python
{
    # Core features
    'cust_person_id': tf.string,    # Customer identifier
    'product_id': tf.int64,         # Product identifier  
    'revenue': tf.float32,          # Customer total revenue
    'city': tf.string,              # City name
    'timestamp': tf.int64,          # Unix timestamp
    
    # Product metadata features
    'art_name': tf.string,          # Product name ("Молоко Селянське 2.5%")
    'stratbuy_domain_desc': tf.string,  # Category ("Dairy")
    'mge_main_cat_desc': tf.string  # Subcategory ("Milk Products")
}
```

## Output Structure

```
gs://bucket/output_path/
└── vocabularies.json              # Enhanced vocabulary mappings with metadata
```

### Enhanced Vocabularies Format

```json
{
  "product_id": ["100007001001", "100007001002", ...],
  "customer_id": ["100005103501", "100005144201", ...], 
  "city": ["CHERNIGIV", "LUTSK", "TERNOPIL"],
  "revenue_buckets": [4.92, 184.99, 365.06, ...],
  "timestamp_buckets": [1748736000.0, 1748783127.27, ...],
  
  "art_name": [
    "Молоко Селянське 2.5%",
    "Samsung Galaxy S24",
    "Хліб Київський",
    ...
  ],
  "stratbuy_domain_desc": [
    "Dairy", 
    "Electronics", 
    "Fresh Produce", 
    "Bakery",
    ...
  ],
  "mge_main_cat_desc": [
    "Milk Products",
    "Smartphones", 
    "Fruits",
    "Bread",
    ...
  ],
  
  "metadata": {
    "total_examples": 552262,
    "vocab_sizes": {
      "products": 1460,
      "customers": 34521,
      "cities": 3,
      "revenue_buckets": 1000,
      "timestamp_buckets": 100,
      "art_names": 1460,
      "categories": 24,
      "subcategories": 125
    },
    "product_metadata_stats": {
      "total_products_with_metadata": 1460,
      "categories_found": 24,
      "subcategories_found": 125,
      "coverage": "100%"
    },
    "revenue_stats": {
      "min": 4.92,
      "max": 358456.0,
      "mean": 8903.71,
      "std": 23174.29
    },
    "timestamp_stats": {
      "min": 1748736000,
      "max": 1753401600,
      "range_days": 120,
      "approach": "tensorflow_linear_buckets"
    }
  }
}
```

## Enhanced Processing Workflow

### 1. TFRecord Processing with Metadata
- Reads compressed TFRecord files using TensorFlow
- Handles both single files and glob patterns
- Processes product metadata fields in addition to core features
- Processes in batches for memory efficiency

### 2. Enhanced Vocabulary Extraction
```python
# Core features
product_ids = set()     # Convert int64 to strings
customer_ids = set()    # String customer IDs
cities = set()          # String city names
revenues = []           # Float values for statistics
timestamps = []         # Int64 Unix timestamps

# NEW: Product metadata vocabularies
art_names = set()       # Product names in local language
categories = set()      # Product categories
subcategories = set()   # Product subcategories
```

### 3. Product Metadata Intelligence

**Product Names:**
```python
# Extract unique product names
art_names = sorted(list(set(art_names)))
# Example: ["Молоко Селянське 2.5%", "Samsung Galaxy S24", ...]
```

**Product Categories:**
```python
# Extract hierarchical categories  
categories = sorted(list(set(categories)))
# Example: ["Bakery", "Dairy", "Electronics", "Fresh Produce", ...]
```

**Product Subcategories:**
```python
# Extract detailed subcategories
subcategories = sorted(list(set(subcategories)))
# Example: ["Bread", "Fruits", "Milk Products", "Smartphones", ...]
```

## Performance

### Machine Requirements
- **Production**: `n1-standard-8` for larger datasets with metadata

### Processing Time
- ~3-4 minutes for 550K examples with metadata on n1-standard-4
- Memory usage: ~3-5GB for typical datasets with product metadata
- I/O bound - depends on GCS read/write speed and metadata processing

## Integration

The Enhanced VocabBuilder is the second component in the pipeline:

1. **DataExtractor** - Creates TFRecord files **with product metadata**
2. **VocabBuilder** ← You are here - Creates vocabularies **including metadata vocabularies**
3. **Trainer** - Uses TFRecords + enhanced vocabularies for **metadata-aware training**

## Docker Image

Current production image: `vocab_builder:latest` (with product metadata support)

## Troubleshooting

### Enhanced Validation

Check enhanced vocabulary output:
```bash
gsutil cat gs://bucket/vocabularies/vocabularies.json | python -m json.tool

# Verify metadata vocabularies
gsutil cat gs://bucket/vocabularies/vocabularies.json | jq '.stratbuy_domain_desc | length'
gsutil cat gs://bucket/vocabularies/vocabularies.json | jq '.mge_main_cat_desc | length'
```
