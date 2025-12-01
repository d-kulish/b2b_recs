# Data Extractor Component - With Product Metadata

Extracts customer transaction data from BigQuery with product metadata for enhanced recommendation quality in the Metro Recommender system.

## Overview

This component:
- **90-day extraction**: Recent transaction data for training
- **Product metadata**: Extracts product names, categories, and subcategories
- **Top 80% products**: Revenue-based product filtering across all cities
- **Customer total revenue**: Aggregated spending across all transactions
- **Timestamp-enhanced**: Unix timestamps for temporal pattern analysis

## Current Version: Product Metadata Enhanced (Latest)

### Features Extracted

| Feature | Type | Description |
|---------|------|-------------|
| `cust_person_id` | string | Customer identifier |
| `product_id` | int64 | Product identifier (art_no * 1000000 + var_tu_key) |
| `revenue` | float32 | Customer total revenue across all transactions |
| `city` | string | City where the transaction occurred |
| `timestamp` | int64 | Unix timestamp from date_of_day for temporal patterns |
| `art_name` | string | Product name in local language |
| `stratbuy_domain_desc` | string | Product category (24 unique categories) |
| `mge_main_cat_desc` | string | Product subcategory (125 unique subcategories) |


## Usage

### Command Line

```bash
python main.py \
    --project_id cf-mccuagcf-recommenders-ht \
    --region europe-west4 \
    --dataset_id segmentation \
    --target_cities TERNOPIL LUTSK CHERNIGIV \
    --output_path gs://metro_recs3/raw_data \
    --num_days 90 \
    --execution_date 2025-08-01 \
    --runner DataflowRunner
```

### As Vertex AI Custom Job

```python
job_spec = {
    "display_name": f"data-extractor-prod-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    "job_spec": {
        "worker_pool_specs": [{
            "machine_spec": {"machine_type": "n1-standard-4"},
            "replica_count": 1,
            "container_spec": {
                "image_uri": "europe-west4-docker.pkg.dev/cf-mccuagcf-recommenders-ht/metro-recs-repo/data-extractor:latest",
                "command": ["python", "main.py"],
                "args": [
                    "--project_id", "cf-mccuagcf-recommenders-ht",
                    "--region", "europe-west4",
                    "--dataset_id", "segmentation",
                    "--target_cities", "TERNOPIL", "LUTSK", "CHERNIGIV",
                    "--output_path", "gs://metro_recs3/raw_data_prod",
                    "--num_days", "90",
                    "--execution_date", "2025-08-01",
                    "--runner", "DataflowRunner"
                ]
            }
        }],
        "service_account": "1032729337493-compute@developer.gserviceaccount.com"
    }
}
```

## Parameters

| Parameter | Required | Description | Default/Example |
|-----------|----------|-------------|-----------------|
| `--project_id` | Yes | Google Cloud project ID | `cf-mccuagcf-recommenders-ht` |
| `--region` | Yes | Google Cloud region | `europe-west4` |
| `--dataset_id` | Yes | BigQuery dataset ID | `segmentation` |
| `--target_cities` | Yes | Target city names (space-separated) | `TERNOPIL LUTSK CHERNIGIV` |
| `--output_path` | Yes | GCS output path | `gs://metro_recs3/raw_data` |
| `--num_days` | No | Number of days to extract | `90` |
| `--execution_date` | No | Reference date for calculation (YYYY-MM-DD) | `today` |
| `--sample_fraction` | No | Data sampling fraction (0.0-1.0) | `1.0` |
| `--runner` | No | Beam runner type | `DataflowRunner` |

## Output Structure

```
gs://bucket/output_path/
├── metadata.json              # Dataset metadata and statistics
└── all_data/                  # Complete dataset for functional splitting
    ├── data-00000-of-00025.tfrecord.gz
    ├── data-00001-of-00025.tfrecord.gz
    └── ...
```

### Metadata Format

```json
{
  "dataset_info": {
    "project_id": "cf-mccuagcf-recommenders-ht",
    "dataset_id": "segmentation",
    "target_cities": ["TERNOPIL", "LUTSK", "CHERNIGIV"],
    "sample_fraction": 1.0,
    "extraction_type": "recent_days_with_product_metadata",
    "period": {
      "start_date": "2025-04-03",
      "end_date": "2025-08-01"
    }
  },
  "total_examples": 552262,
  "data_pattern": "gs://bucket/path/all_data/data-*.tfrecord.gz",
  "splitting_methodology": "single_dataset_for_functional_splitting",
  "features": {
    "cust_person_id": {"dtype": "string"},
    "product_id": {"dtype": "int64"},
    "revenue": {"dtype": "float32", "description": "Customer total revenue"},
    "city": {"dtype": "string"},
    "timestamp": {"dtype": "int64", "description": "Unix timestamp"},
    "art_name": {"dtype": "string", "description": "Product name in local language"},
    "stratbuy_domain_desc": {"dtype": "string", "description": "Product category (66 unique values)"},
    "mge_main_cat_desc": {"dtype": "string", "description": "Product sub-category (427 unique values)"}
  }
}
```

## How It Works

1. **Date calculation**: Extracts last `num_days` from execution_date
2. **Product filtering**: Top 80% revenue products across all cities
3. **Product metadata join**: Gets latest product info from articles table
4. **Missing data handling**: Uses 'N/A' for missing product metadata
5. **TFRecord output**: 8 features including product metadata

### BigQuery Query Structure

The extraction query:
1. Calculates top 80% products by revenue
2. Gets latest product metadata (handles updates)
3. Joins transaction data with product info
4. Adds customer total revenue and timestamps
5. Filters by cities and date range

## Product Metadata Details

### Categories (stratbuy_domain_desc)
- 24 unique product categories
- Examples: "Fresh Produce", "Dairy", "Electronics"
- Used for high-level product grouping

### Subcategories (mge_main_cat_desc)
- 125 unique subcategories
- Examples: "Fruits", "Milk Products", "Television"
- Provides finer product classification


## Integration

The Data Extractor is the first component in the pipeline:

1. **Data Extractor** ← You are here (extracts data with metadata)
2. Vocab Builder (builds vocabularies including categories)
3. Trainer (uses metadata for enhanced embeddings)


## Docker Image

Current production image: `europe-west4-docker.pkg.dev/cf-mccuagcf-recommenders-ht/metro-recs-repo/data-extractor:latest`

