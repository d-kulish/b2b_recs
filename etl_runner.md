# ETL Runner

**Last Updated:** November 21, 2025
**Status:** Production Ready ✅ | Cloud Scheduler Working ✅ | File & Database Sources Supported ✅

Cloud Run-based ETL execution engine that extracts data from databases and cloud storage files, transforms it, and loads into BigQuery for the B2B Recommendations Platform.

---

## Overview

The ETL Runner is a containerized Python application deployed as a **Cloud Run Job** that:
- Extracts data from multiple source types (databases, cloud storage files)
- Validates and transforms data
- Loads data into BigQuery with automatic schema management
- Supports two load strategies: **Transactional** (incremental) and **Catalog** (snapshot)
- Integrates with Cloud Scheduler for automated execution

**Architecture:**
```
Cloud Scheduler (OIDC auth)
    ↓
Django API Webhook (/api/etl/sources/<id>/scheduler-webhook/)
    ↓
Cloud Run Job (ETL Runner)
    ├── Fetch job config from Django API
    ├── Validate configuration
    ├── Extract from source (database or files)
    ├── Transform data
    └── Load to BigQuery
```

---

## Supported Data Sources

### **Databases**
- **PostgreSQL** - Full table extraction, incremental updates
- **MySQL** - Full table extraction, incremental updates
- **BigQuery** - Cross-project data movement

**Features:**
- Memory-efficient streaming (processes in batches)
- Incremental loading using timestamp columns
- Custom SQL query support
- Connection pooling

### **Cloud Storage Files**
- **Google Cloud Storage (GCS)**
- **AWS S3**
- **Azure Blob Storage**

**File Formats:**
- CSV (with configurable delimiter, encoding, headers)
- Parquet
- JSON/JSONL

**Features:**
- File pattern matching (glob patterns like `*.csv`, `data_*.parquet`)
- Metadata tracking (file size, last modified, processing status)
- Incremental loading (processes only new/changed files)
- Folder prefix support for organized data

---

## Load Strategies

### **1. Transactional (Incremental/Append-Only)**

**Use Case:** Event logs, transactions, immutable records

**How It Works:**
- **Databases**: Uses timestamp column (e.g., `created_at`) to track last sync value
- **Files**: Tracks processed files by name and last_modified timestamp

**Behavior:**
- First run: Loads all data
- Subsequent runs: Loads only new/changed records
- Data is appended to BigQuery table
- No deletions or updates

**Example:**
```yaml
Source: orders table
Timestamp Column: created_at
Last Sync: 2025-11-20 10:00:00

Next Run:
  → SELECT * FROM orders WHERE created_at > '2025-11-20 10:00:00'
  → Append to BigQuery
  → Update last_sync to latest timestamp
```

### **2. Catalog (Daily Snapshot)**

**Use Case:** Product catalogs, user profiles, dimensional data

**How It Works:**
- **Databases**: Extracts full table on every run
- **Files**: Processes latest file(s) or all files based on config

**Behavior:**
- Replaces entire BigQuery table on each run
- Captures current state of source data
- Suitable for slowly changing dimensions

**Example:**
```yaml
Source: products table
Mode: Catalog

Every Run:
  → SELECT * FROM products (full table)
  → Replace BigQuery table completely
  → Snapshot of current product catalog
```

---

## Configuration

ETL Runner receives configuration from Django API endpoint:

```json
{
  "source_type": "gcs",
  "connection_params": {
    "source_type": "gcs",
    "bucket": "my-bucket",
    "credentials": {...}
  },
  "load_type": "transactional",
  "dest_table_name": "raw_sales_data",

  // For files:
  "file_pattern": "*.csv",
  "file_format": "csv",
  "file_format_options": {
    "delimiter": ",",
    "encoding": "utf-8",
    "has_header": true
  },
  "selected_columns": [],  // empty = all columns

  // For databases:
  "source_table_name": "orders",
  "timestamp_column": "created_at",
  "selected_columns": ["id", "customer_id", "amount", "created_at"]
}
```

---

## Recent Fixes (Phase 6 - November 21, 2025)

### **Issue 1: Cloud Scheduler 401 Authentication Error**

**Problem:** Cloud Scheduler failed to trigger ETL jobs with UNAUTHENTICATED error.

**Root Causes:**
1. Cloud Scheduler service agent lacked `iam.serviceAccountTokenCreator` permission
2. Wrong API endpoint (v1 instead of v2)
3. Direct OIDC invocation of Cloud Run Jobs API was unreliable

**Solution:** Implemented webhook pattern
- Cloud Scheduler → Django webhook → Cloud Run Job
- Added `/api/etl/sources/<id>/scheduler-webhook/` endpoint
- Configured proper IAM permissions

**Result:** ✅ Automated scheduling now working

---

### **Issue 2: File ETL Validation Failures**

**Problem:** Validation logic rejected file sources and required incorrect fields.

**Issues Fixed:**
1. Source type validation only recognized databases (`postgresql`, `mysql`, `bigquery`)
2. `timestamp_column` incorrectly required for file transactional loads
3. `selected_columns` incorrectly required to be non-empty
4. API didn't send file-specific configuration fields

**Solution:**
- Updated validation to recognize file source types (`gcs`, `s3`, `azure_blob`)
- Made `timestamp_column` optional for file sources
- Made `selected_columns` optional for file sources (empty = all columns)
- Updated API to build file-specific config with `file_pattern`, `file_format`, etc.

**Files Changed:**
- `etl_runner/utils/error_handling.py` - Validation logic
- `ml_platform/views.py` - API configuration builder

**Result:** ✅ File sources now pass validation and execute successfully

---

## Deployment

### **Infrastructure**

- **Platform:** Google Cloud Run (Job)
- **Region:** europe-central2 (Warsaw, Poland)
- **Project:** b2b-recs (555035914949)
- **Image:** `gcr.io/b2b-recs/etl-runner:latest`
- **Resources:**
  - Memory: 8Gi
  - CPU: 4
  - Timeout: 3600s (1 hour)
  - Max retries: 3

### **Service Account**

**Name:** `etl-runner@b2b-recs.iam.gserviceaccount.com`

**Permissions:**
- `roles/bigquery.dataEditor` - Write to BigQuery tables
- `roles/bigquery.jobUser` - Execute BigQuery jobs
- `roles/secretmanager.secretAccessor` - Read credentials from Secret Manager
- `roles/storage.objectViewer` - Read GCS files
- `roles/run.developer` - Execute Cloud Run Jobs (for Django to trigger)

### **Environment Variables**

```bash
DJANGO_API_URL=https://django-app-555035914949.europe-central2.run.app
GCP_PROJECT_ID=b2b-recs
BIGQUERY_DATASET=raw_data
LOG_LEVEL=INFO
```

---

## Usage

### **1. Via Django UI (ETL Wizard)**

1. Navigate to Model → ETL page
2. Click "Add Data Source"
3. Follow 5-step wizard:
   - **Step 1:** Select connection
   - **Step 2:** Choose table/files
   - **Step 3:** Preview and select columns
   - **Step 4:** Configure load strategy
   - **Step 5:** Set schedule (optional)
4. Save → ETL job created
5. Click "Run Now" to trigger immediately, or wait for scheduled run

### **2. Via API (Manual Trigger)**

```bash
# Trigger ETL job for data source ID 5
curl -X POST \
  -H "Content-Type: application/json" \
  https://django-app-555035914949.europe-central2.run.app/api/etl/sources/5/scheduler-webhook/
```

### **3. Via Cloud Scheduler (Automated)**

Cloud Scheduler jobs are created automatically when you set a schedule in the ETL Wizard.

**Example Schedule:**
- **Daily at 9 AM (Europe/Kiev):** `0 9 * * *`
- **Hourly at minute 30:** `30 * * * *`
- **Weekly on Monday at 6 AM:** `0 6 * * 1`

---

## Monitoring

### **Cloud Run Job Executions**

```bash
# List recent executions
gcloud run jobs executions list \
  --job=etl-runner \
  --region=europe-central2 \
  --limit=10

# View logs for specific execution
gcloud logging read \
  'resource.type=cloud_run_job
   AND resource.labels.job_name=etl-runner
   AND labels."run.googleapis.com/execution_name"="etl-runner-abc123"' \
  --limit=100 \
  --format=json
```

### **Cloud Scheduler Jobs**

```bash
# List all scheduler jobs
gcloud scheduler jobs list --location=europe-central2

# View specific job
gcloud scheduler jobs describe etl-job-5 --location=europe-central2

# Manually trigger
gcloud scheduler jobs run etl-job-5 --location=europe-central2
```

### **BigQuery**

```sql
-- Check ETL results
SELECT
  COUNT(*) as row_count,
  MIN(_airbyte_extracted_at) as first_load,
  MAX(_airbyte_extracted_at) as last_load
FROM `b2b-recs.raw_data.your_table`;
```

---

## Key Features

✅ **Multi-Source Support** - Databases and cloud storage files
✅ **Automatic Schema Detection** - Infers BigQuery schema from source
✅ **Incremental Loading** - Process only new/changed data
✅ **Memory Efficient** - Streaming processing with configurable batch sizes
✅ **Error Handling** - Retries, detailed logging, status tracking
✅ **Flexible Scheduling** - Minute-level precision with timezone support
✅ **Column Sanitization** - Auto-fixes column names for BigQuery compatibility
✅ **Metadata Tracking** - File processing history, last sync values
✅ **Secure** - Credentials in Secret Manager, IAM-based access control

---

## Troubleshooting

### **"Cannot determine path without bucket name"**

**Cause:** Missing bucket configuration in connection.

**Fix:**
1. Update Connection record in database: `UPDATE ml_platform_connection SET source_host='your-bucket-name' WHERE id=X`
2. Verify credentials in Secret Manager

### **"timestamp_column is required for transactional loads"**

**Cause:** Using old ETL runner version.

**Fix:**
1. Redeploy ETL runner: `gcloud run jobs update etl-runner --image=gcr.io/b2b-recs/etl-runner:latest`
2. Validation now allows empty timestamp_column for file sources

### **Cloud Scheduler 401 Error**

**Cause:** Missing IAM permissions.

**Fix:**
```bash
# Grant Cloud Scheduler permission to create OIDC tokens
gcloud iam service-accounts add-iam-policy-binding etl-runner@b2b-recs.iam.gserviceaccount.com \
  --member="serviceAccount:service-555035914949@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

---

## File Structure

```
etl_runner/
├── main.py                      # Entry point, orchestrates ETL flow
├── config.py                    # Configuration management
├── extractors/
│   ├── postgresql.py           # PostgreSQL extractor
│   ├── mysql.py                # MySQL extractor
│   └── file_extractor.py       # GCS/S3/Azure file extractor
├── loaders/
│   └── bigquery_loader.py      # BigQuery loader with batching
├── utils/
│   ├── error_handling.py       # Error handling and validation
│   ├── logging_config.py       # Structured logging
│   └── schema_mapper.py        # BigQuery schema inference
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container image definition
└── README.md                    # Developer docs
```

---

## Development

### **Local Testing**

```bash
# Set environment variables
export DJANGO_API_URL=http://localhost:8000
export GCP_PROJECT_ID=b2b-recs
export BIGQUERY_DATASET=raw_data

# Run ETL job locally
python main.py --data_source_id=5 --log_level=DEBUG

# Build Docker image
docker build -t etl-runner .

# Run in container
docker run --rm \
  -e DJANGO_API_URL=$DJANGO_API_URL \
  -e GCP_PROJECT_ID=$GCP_PROJECT_ID \
  etl-runner --data_source_id=5
```

### **Deploy to Cloud Run**

```bash
# Build and push image
gcloud builds submit --tag gcr.io/b2b-recs/etl-runner

# Update Cloud Run Job
gcloud run jobs update etl-runner \
  --region=europe-central2 \
  --image=gcr.io/b2b-recs/etl-runner:latest
```

---

**Status:** Production-ready with automated scheduling and multi-source support. GCS bucket configuration pending for DataSource #5.
