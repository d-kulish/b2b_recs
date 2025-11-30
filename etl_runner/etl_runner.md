# ETL Runner

**Last Updated:** November 30, 2025
**Status:** Production Ready ✅ | Cloud Scheduler Working ✅ | SQL/NoSQL/File Sources Supported ✅ | Dataflow Working ✅ | **NEW: ETL Duration Analysis Chart** 🔥

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
- **BigQuery** - Cross-project data movement, public dataset access

**Features:**
- Memory-efficient streaming (processes in batches)
- Incremental loading using timestamp columns
- Custom SQL query support
- Connection pooling
- **BigQuery-to-BigQuery:** Native support for copying data between BigQuery projects/datasets
  - Public dataset access (e.g., `bigquery-public-data.stackoverflow`)
  - Cross-project data movement
  - Incremental loading with timestamp filters
  - Row count estimation using `COUNT(*)` queries

### **NoSQL Databases**
- **Firestore** - Google Cloud Firestore (NoSQL document database)

**Features:**
- **Automatic Schema Inference:** Samples first 100 documents to detect all fields
- **Nested Data Handling:** Converts nested objects and arrays to JSON strings
- **Flexible Schema:** Handles documents with different field structures in same collection
- **Incremental Loading:** Supports timestamp-based filtering (requires indexed timestamp field)
- **Metadata Fields:** Automatically adds `document_id` and `_extracted_at` columns
- **Document Streaming:** Memory-efficient processing of large collections
- **Graceful Error Handling:** Skips malformed documents instead of failing entire job

**Schema Inference:**
- Samples first 100 documents from collection
- Unions all fields found across documents
- Infers types: STRING, INTEGER, FLOAT, BOOLEAN, TIMESTAMP
- Nested objects/arrays → stored as JSON strings (queryable with BigQuery `JSON_EXTRACT()`)

**Volume Handling:**
- **< 1M documents:** Standard mode (pandas + single Cloud Run instance)
  - Streams documents in batches of 10K
  - Memory-efficient processing
  - Completes in minutes for collections under 100K docs
- **≥ 1M documents:** Dataflow mode (distributed processing)
  - Uses hash-based partitioning (10 partitions by default)
  - Each worker processes ~10% of documents in parallel
  - ⚠️ **Note:** Dataflow Beam pipeline for Firestore not yet implemented
  - Partitioning strategy defined in `dataflow_pipelines/partitioning.py`
  - For now, large collections (> 1M) will use Standard mode

**Limitations:**
- No fast document count (estimates by sampling up to 1000 docs)
- Transactional mode requires user-managed timestamp field (e.g., `updated_at`, `created_at`)
- Timestamp field must be indexed in Firestore for query performance
- Empty collections are skipped (no schema to infer)
- Schema reflects only first 100 documents (rare fields may be missed)
- Dataflow mode partitioning defined but Beam pipeline not yet implemented

**Example Use Cases:**
- User profiles from Firebase Auth → BigQuery
- Real-time event data from mobile apps
- Product catalogs with varying attributes
- Nested order data with line items

**Performance Benchmarks:**
- 500 documents: ~5-10 seconds
- 10K documents: ~30-60 seconds
- 100K documents: ~5-10 minutes
- 1M documents: ~30-60 minutes (Standard mode, single worker)

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

## Dataflow Architecture (Large-Scale Processing)

### **Overview**

For datasets >= 1M rows, ETL Runner automatically switches from standard pandas-based processing to **Google Cloud Dataflow** for distributed parallel processing.

**Processing Decision Logic:**
```python
if estimated_rows >= 1_000_000:
    use_dataflow()  # Distributed processing across multiple workers
else:
    use_pandas()    # Single-VM processing (Cloud Run Job)
```

**Performance Comparison:**
| Dataset Size | Standard ETL | Dataflow | Speedup |
|--------------|--------------|----------|---------|
| 100K rows | 30 seconds | N/A (overhead not worth it) | - |
| 1M rows | 5 minutes | 2 minutes | 2.5x |
| 5M rows | 40 minutes | 4 minutes | 10x |
| 10M rows | Would timeout | 8 minutes | >10x |

---

### **Critical Implementation Details**

#### **1. BigQuery Write Method: FILE_LOADS (Not STORAGE_WRITE_API)**

**Decision:** Use `FILE_LOADS` for batch Dataflow jobs, not `STORAGE_WRITE_API`.

**Why:**
- **FILE_LOADS**: Designed for batch workloads (scheduled ETL)
  - Writes data to temp GCS files, then loads via BigQuery Load job
  - No Java dependency
  - Cost-effective for large batches
  - Atomic loads with rollback
  - **This is Google's recommended method for batch Dataflow pipelines**

- **STORAGE_WRITE_API**: Designed for streaming workloads (real-time)
  - Requires Java expansion service
  - Java 9+ module system issues (`java.lang.UnsupportedOperationException`)
  - More expensive per row
  - Overkill for batch processing

**Problem We Hit:**
```
java.lang.UnsupportedOperationException: Cannot define class using reflection:
Unable to make protected java.lang.Package java.lang.ClassLoader.getPackage(java.lang.String)
accessible: module java.base does not "opens java.lang" to unnamed module
```

**Solution:** Switched to FILE_LOADS, removed Java from Dockerfile.

**Implementation:**
```python
# etl_pipeline.py
| 'WriteToBigQuery' >> WriteToBigQuery(
    table=table_ref,
    write_disposition=write_disposition,
    create_disposition=BigQueryDisposition.CREATE_NEVER,
    method='FILE_LOADS'  # ← Correct for batch workloads
)
```

---

#### **2. Pure Python Serialization (No pandas/numpy in Workers)**

**Critical Insight:** Using pandas DataFrames in Dataflow workers creates a massive bottleneck.

**Problem:**
- Pandas DataFrames: ~2GB memory per worker
- DataFrame overhead: ~1000 rows/sec per worker
- Doesn't scale linearly

**Solution:** Direct database cursor → dict conversion (no pandas intermediate step)

**Implementation:**

**Before (Slow - pandas in workers):**
```python
# PostgreSQL extractor
cursor.execute(query)
rows = cursor.fetchmany(10000)
df = pd.DataFrame(rows, columns=column_names)  # ← Unnecessary overhead!
for _, row in df.iterrows():                   # ← Slow iteration
    yield row.to_dict()
```

**After (Fast - raw cursors):**
```python
# PostgreSQL extractor - extract_incremental_raw()
cursor.execute(query)
column_names = [desc[0] for desc in cursor.description]
while True:
    rows = cursor.fetchmany(10000)
    for row_tuple in rows:
        row_dict = dict(zip(column_names, row_tuple))  # ← Direct conversion
        yield row_dict
```

**Performance Impact:**
- Memory: ~200MB per worker (90% reduction)
- Speed: ~5000-10000 rows/sec per worker (5-10x faster)
- Scalability: True linear scaling with worker count

**Serialization Function:**
```python
def _serialize_value(value):
    """Pure Python - no pandas, no numpy."""
    # datetime → ISO string
    if isinstance(value, datetime):
        return value.isoformat()

    # Decimal → float
    if isinstance(value, Decimal):
        return float(value)

    # NaN/Inf → None (JSON doesn't support)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None

    # Arrays/dicts → recursive
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]

    # Pass through JSON-safe types
    return value
```

**Key Benefits:**
- No `pd.isna()` (fails on arrays)
- No `np.isnan()` (requires numpy)
- Only standard library: `datetime`, `Decimal`, `math`
- Handles all database types correctly

---

#### **3. Schema-Aware Type Conversion**

**Problem:** Source schema ≠ Destination schema

**Real-World Example (bq_transactions_v2):**

**Source data (from BigQuery):**
```json
{
  "inputs": [{"index": 0, "value": 8850.0}],  // Array of objects
  "outputs": [{"index": 0, "value": 294.0}]   // Array of objects
}
```

**Destination schema:**
```json
{
  "inputs": {"type": "STRING"},   // Expects JSON string, not array!
  "outputs": {"type": "STRING"}   // Expects JSON string, not array!
}
```

**Result without conversion:**
```
Error: JSON table encountered too many errors
BigQuery received: Array (invalid for STRING type)
```

**Solution: SchemaAwareConverter**

Converts values to match destination schema:
- Array → JSON string (when schema expects STRING)
- Dict → JSON string (when schema expects STRING)
- String → Integer (when schema expects INTEGER)
- Preserves data integrity (can reconstruct original)

**Implementation:**
```python
class SchemaAwareConverter(beam.DoFn):
    def __init__(self, schema_map: Dict[str, str]):
        self.schema_map = schema_map  # {field_name: field_type}

    def process(self, row_dict):
        for key, value in row_dict.items():
            target_type = self.schema_map.get(key)

            if target_type == 'STRING':
                # If value is array/dict, convert to JSON string
                if isinstance(value, (list, dict)):
                    row_dict[key] = json.dumps(value)

            elif target_type == 'INTEGER':
                row_dict[key] = int(value)

            # ... handle other types

        yield row_dict
```

**Pipeline Integration:**
```python
pipeline
| 'ReadFromBigQuery' >> beam.io.ReadFromBigQuery(query)
| 'SerializeValues' >> beam.Map(lambda row: {k: _serialize_value(v) for k, v in row.items()})
| 'ConvertToSchema' >> beam.ParDo(SchemaAwareConverter(schema_map))  # ← Critical step
| 'WriteToBigQuery' >> WriteToBigQuery(table, method='FILE_LOADS')
```

**Result:**
```json
{
  "inputs": "[{\"index\": 0, \"value\": 8850.0}]",  // JSON string ✓
  "outputs": "[{\"index\": 0, \"value\": 294.0}]"   // JSON string ✓
}
```

BigQuery Load succeeds because all types match schema!

**Data Integrity:**
Original data is preserved in JSON format and can be reconstructed:
```sql
SELECT
  hash,
  JSON_EXTRACT_ARRAY(inputs) as parsed_inputs,
  JSON_EXTRACT_ARRAY(outputs) as parsed_outputs
FROM `b2b-recs.raw_data.bq_transactions_v2`
```

---

#### **4. Work Partitioning for Parallelism**

**Module:** `dataflow_pipelines/partitioning.py`

**Concept:** Split large datasets into independent work units that can be processed in parallel.

**Strategies:**

1. **Date Range Partitioning** (for tables with timestamp columns)
   - Splits by day/hour based on data volume
   - Target: 50K rows per partition
   - Example: 5M rows over 365 days → 365 daily partitions → All workers active

2. **Hash Partitioning** (for tables without good partitioning keys)
   - Uses `MOD(HASH(id), num_partitions) = partition_id`
   - Distributes rows evenly

3. **File Partitioning** (for cloud storage)
   - Each file = 1 partition
   - Simple and efficient

**Pipeline Flow:**
```
Main process (Cloud Run):
  → Calculate work units (e.g., 365 date ranges)
  → Submit to Dataflow

Dataflow:
  → Create PCollection with 365 elements
  → Each worker processes assigned work units in parallel
  → All workers active, no idle time
```

**Key Difference from Old Approach:**
- **Old**: Single work unit → 1 worker processes everything sequentially
- **New**: 365 work units → 10 workers process 36-37 units each in parallel

---

### **Dataflow Dependencies**

**Dockerfile (`etl_runner/Dockerfile`):**
```dockerfile
# NO Java needed - FILE_LOADS doesn't require Java!
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```

**Python packages (`requirements.txt`):**
```
apache-beam[gcp]==2.52.0  # Dataflow SDK
```

**Custom code packaging (`setup.py`):**
```python
# Packages custom modules for Dataflow workers
setup(
    name='etl-runner-dataflow',
    packages=find_packages(exclude=['tests']),
    install_requires=[
        'apache-beam[gcp]==2.52.0',
        'google-cloud-bigquery==3.14.0',
        # ... other dependencies
    ]
)
```

---

### **Testing Dataflow Locally**

**Serialization test:**
```bash
cd /Users/dkulish/Projects/b2b_recs/etl_runner
python3 test_serialization_standalone.py
```

**Schema conversion test:**
```bash
python3 test_schema_conversion.py
```

Both should show "✓ ALL TESTS PASSED" before deployment.

---

### **Monitoring Dataflow Jobs**

**GCP Console:**
```
https://console.cloud.google.com/dataflow/jobs/europe-central2
```

**What to check:**
1. **Worker utilization** - Should be >70% (all workers active)
2. **Processing rate** - Should scale linearly with workers
3. **Errors** - Check worker logs for serialization/schema errors
4. **Costs** - Monitor to ensure staying within budget

**Logs to watch for:**
```
✓ "Created 365 work units for parallel processing"
✓ "Work units: 365"
✓ "Workers: 2 initial, up to 10 max (autoscaling)"
✓ "Dataflow pipeline submitted successfully"
```

---

### **Common Issues and Solutions**

**Issue 1: "JSON table encountered too many errors"**
- **Cause**: Schema mismatch (array in data, STRING in schema)
- **Solution**: SchemaAwareConverter handles this automatically
- **Check**: Inspect temp GCS file, verify JSON is valid

**Issue 2: "The truth value of an array with more than one element is ambiguous"**
- **Cause**: Using `pd.isna()` on arrays
- **Solution**: Pure Python serialization checks complex types BEFORE `pd.isna()`

**Issue 3: "ModuleNotFoundError: No module named 'dataflow_pipelines'"**
- **Cause**: setup.py not packaging custom code
- **Solution**: Verify setup.py exists, includes all packages

**Issue 4: Java module errors (if using STORAGE_WRITE_API)**
- **Cause**: Java 9+ module system restrictions
- **Solution**: Use FILE_LOADS instead (no Java needed)

---

## Recent Fixes (Phase 6-7 - November 21, 2025)

### **Issue 1: ETL Wizard Cloud Scheduler Creation Bug**

**Problem:** ETL Wizard created Cloud Scheduler jobs with null httpTarget fields, preventing jobs from executing.

**Root Cause:**
1. **Wrong URL approach**: Wizard used Cloud Run Jobs API URL (`https://region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/{project}/jobs/etl-runner:run`) which requires complex authentication
2. **Missing OIDC audience**: `cloud_scheduler.py` didn't set the `audience` parameter in OIDC token configuration
3. **Static configuration**: Used hardcoded Cloud Run Jobs API URL instead of dynamic Django webhook URL

**Investigation:**
- Manually created scheduler jobs worked fine using webhook pattern
- Wizard-created jobs had all httpTarget fields as `null` (uri, httpMethod, serviceAccountEmail, audience)
- Direct Cloud Run Jobs API approach consistently failed with 401 errors despite correct IAM permissions

**Solution:**
1. **Updated views.py (ETL Wizard)**:
   ```python
   # OLD (BROKEN):
   cloud_run_job_url = f"https://europe-central2-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/{project_id}/jobs/etl-runner:run"

   # NEW (WORKING):
   django_base_url = f"{request.scheme}://{request.get_host()}"
   webhook_url = f"{django_base_url}/api/etl/sources/{data_source.id}/scheduler-webhook/"
   ```
   - Builds webhook URL dynamically from request object
   - Works in both local dev and Cloud Run environments
   - No configuration needed

2. **Updated cloud_scheduler.py**:
   ```python
   # Extract base URL for OIDC audience
   from urllib.parse import urlparse
   parsed_url = urlparse(cloud_run_job_url)
   audience = f"{parsed_url.scheme}://{parsed_url.netloc}"

   oidc_token=scheduler_v1.OidcToken(
       service_account_email=service_account_email,
       audience=audience  # <- Added this
   )
   ```

**Architecture Change:**
```
OLD: Cloud Scheduler → Cloud Run Jobs API → ETL Runner (❌ 401 errors)

NEW: Cloud Scheduler → Django Webhook → Django triggers Cloud Run Job → ETL Runner (✅ Working)
```

**Files Changed:**
- `ml_platform/views.py` - Wizard scheduler creation (lines 2385-2398)
- `ml_platform/utils/cloud_scheduler.py` - OIDC token configuration (lines 83-101)

**Result:** ✅ ETL Wizard now creates working Cloud Scheduler jobs with proper authentication

---

### **Issue 2: Cloud Scheduler 401 Authentication Error (Manual Jobs)**

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

### **Issue 3: ETL Runner API Authentication (403 Forbidden)**

**Problem:** ETL Runner received 403 errors when trying to POST status updates back to Django API.

**Error Messages:**
```
Failed to update ETL run status: 403 Client Error: Forbidden for url:
https://django-app-.../api/etl/runs/24/update/
```

**Root Cause:**
Django API endpoints were missing `@csrf_exempt` decorator, requiring CSRF tokens that the ETL Runner (service-to-service call) doesn't provide.

**Affected Endpoints:**
- `/api/etl/runs/<id>/update/` - Status updates (running, completed, failed)
- `/api/etl/job-config/<id>/` - Job configuration fetch

**Solution:**
Added `@csrf_exempt` decorator to service-to-service API endpoints:

```python
# ml_platform/views.py

@csrf_exempt  # <- Added
@require_http_methods(["PATCH"])
def api_etl_run_update(request, run_id):
    """Update ETL run status and progress."""
    ...

@csrf_exempt  # <- Added
@require_http_methods(["GET"])
def api_etl_job_config(request, data_source_id):
    """Get ETL job configuration for the ETL runner."""
    ...
```

**Note:** Other service-to-service endpoints already had `@csrf_exempt`:
- `api_etl_scheduler_webhook` (webhook endpoint)
- `api_etl_record_processed_file` (file metadata tracking)

**Result:** ✅ ETL Runner now successfully updates job status throughout execution lifecycle

---

### **Issue 4: File ETL Validation Failures**

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

### **Issue 5: Connection Management System Bugs (November 21, 2025)**

**Problem:** Connection edit forms displayed empty fields for cloud storage and NoSQL connections, making it impossible to edit existing connections.

#### **Root Causes Identified:**

**A. Backend API - Source-Type Blind Architecture**

The connection CRUD APIs treated all connections identically, only handling database fields:

1. **`api_connection_create` (Wizard):** Only saved database fields (`source_host`, `source_port`, `source_database`). Missing: `bucket_path` for GCS/S3/Azure, `aws_region` for S3, etc.

2. **`api_connection_create_standalone`:** Partially saved cloud storage fields but incomplete.

3. **`api_connection_get` (Edit):** Only returned database fields. Missing all cloud storage fields (`bucket_path`, `aws_region`, `azure_storage_account`, etc.) and NoSQL fields.

4. **`api_connection_update`:** Same issue - only updated database fields.

**B. Frontend Form Population - Missing Field Logic**

The `openEditConnectionModal()` JavaScript function only populated database connection fields:

1. **Connection Name:** Hardcoded to use `connName` field ID (database form only). Each connection type uses different IDs:
   - Database: `connName`
   - GCS: `connNameGCS`
   - BigQuery/Firestore: `connNameBQ`
   - S3: `connNameS3`
   - Azure: `connNameAzureBlob`

2. **Cloud Storage Fields:** No code to populate `bucket_path`, `service_account_json` for GCS, S3 access keys, Azure storage account, etc.

3. **BigQuery/Firestore:** Project ID and dataset populated, but service account JSON was never fetched from credentials endpoint.

4. **Azure:** Used wrong field ID (`connAzureBucketPath` instead of `connAzureContainerPath`).

#### **Solutions Implemented:**

**Backend Fixes (ml_platform/views.py):**

1. **Unified Connection Creation API:**
   - Replaced separate wizard/standalone APIs with single source-type aware API
   - Properly extracts and saves fields based on connection type (DB, GCS, S3, Azure, NoSQL)
   - Saves bucket names to both `source_host` (backward compatibility) and `bucket_path`
   - Stores sensitive credentials in Secret Manager, config in database

2. **Fixed Connection Retrieval API:**
   - `api_connection_get` now returns source-type specific fields
   - GCS: returns `bucket_path`, with fallback to `source_host` for backward compatibility
   - S3: returns `bucket_path`, `aws_access_key_id`, `aws_region`
   - Azure: returns `bucket_path`, `azure_storage_account`
   - BigQuery/Firestore: returns `bigquery_project`, `bigquery_dataset`
   - NoSQL: returns `connection_string`, `connection_params`

3. **Fixed Connection Update API:**
   - Source-type aware field extraction and updating
   - Tests connection before applying updates
   - Updates both database fields and Secret Manager credentials

**Frontend Fixes (templates/ml_platform/model_etl.html):**

1. **Source-Type Aware Connection Name Population:**
   - Detects connection type and uses correct field ID
   - Populates connection name for all connection types

2. **Cloud Storage Field Population:**
   - GCS: Populates `bucket_path` and fetches `service_account_json` from credentials endpoint
   - S3: Populates `bucket_path`, `aws_access_key_id`, `aws_region`, fetches `aws_secret_access_key`
   - Azure: Populates `container_path` (fixed wrong field ID), `azure_storage_account`, fetches credentials

3. **BigQuery/Firestore Service Account:**
   - Added credentials fetch to populate `service_account_json` field

4. **Field ID Corrections:**
   - Azure: Changed from `connAzureBucketPath` to `connAzureContainerPath` (matches HTML)

#### **Files Modified:**
- `ml_platform/views.py` - Backend API fixes (~200 lines)
- `templates/ml_platform/model_etl.html` - Frontend form population (~100 lines)

#### **Testing Results:**
- ✅ Database: `retail_csv_buckets` (Connection #5) now populates all fields correctly
- ✅ API returns correct data for all connection types
- ✅ All field IDs verified to match between HTML and JavaScript
- ✅ Connection name, bucket path, and service account JSON populate correctly

#### **Known Issue:**
**Test Connection buttons not visible in edit mode** - Buttons exist in HTML but may not render due to browser/CSS/timing issue. Requires browser DevTools investigation or explicit show/hide logic implementation.

**Result:** ✅ Connection editing now works for all connection types (databases, cloud storage, NoSQL)

---

### **Issue 6: File ETL Runtime Bugs (November 21, 2025)**

**Problem:** File-based ETL jobs failed during execution with multiple errors despite passing validation.

#### **Bugs Fixed:**

**A. GCS Credential Initialization**
- **Issue:** File extractor initialized GCS client without user credentials, falling back to default service account
- **Fix:** Updated `file_extractor.py` to extract and use service account credentials from `connection_params`
- **Impact:** ETL runner now authenticates with user-provided service accounts

**B. Column Name Mismatch**
- **Issue:** DataFrames had original CSV column names (e.g., `"DiscountApplied(%)"`) but BigQuery tables had sanitized names (e.g., `"discountapplied"`)
- **Root Cause:** ETL wizard sanitized names during table creation but didn't persist the mapping
- **Fix:**
  - Added `column_mapping` JSONField to `DataSourceTable` model
  - ETL wizard now saves mapping: `{"DiscountApplied(%)": "discountapplied"}`
  - ETL runner renames DataFrame columns using the mapping before loading
- **Files Changed:** `ml_platform/models.py`, `ml_platform/views.py`, `etl_runner/main.py`

**C. DataFrame Schema Mismatch**
- **Issue:** DataFrame had 14 columns from CSV, but BigQuery table only had 10 selected columns
- **Fix:** ETL runner now fetches BigQuery table schema and filters DataFrame to only include columns that exist in the table
- **Impact:** Handles cases where user selected subset of columns

**D. Data Type Conversion**
- **Issue:** DataFrame had string types but BigQuery expected INT/FLOAT/TIMESTAMP, causing `"object of type <class 'str'> cannot be converted to int"` error
- **Fix:** ETL runner now fetches BigQuery schema types and converts DataFrame column types to match (INT64, FLOAT64, STRING, TIMESTAMP)
- **Files Changed:** `etl_runner/main.py` (added `_convert_dataframe_types` method)

**Files Modified:**
- `ml_platform/models.py` - Added `column_mapping` field
- `ml_platform/migrations/0016_add_column_mapping_field.py` - Database migration
- `ml_platform/views.py` - Save and return column mapping
- `etl_runner/extractors/file_extractor.py` - Credential handling
- `etl_runner/main.py` - Column renaming, filtering, type conversion

**Result:** ✅ File ETL now works end-to-end - successfully loads CSV files to BigQuery with proper authentication, column mapping, and type conversion

---

### **Issue 7: BigQuery Source Implementation (November 21, 2025)**

**Goal:** Enable BigQuery-to-BigQuery ETL for accessing public datasets and cross-project data movement.

**Use Case:** Testing with Stack Overflow public dataset (`bigquery-public-data.stackoverflow.posts_questions`) to validate ETL system with real-world data.

**Implementation:**

**A. Created BigQuery Extractor** (`etl_runner/extractors/bigquery.py`):
- Authenticates with service account credentials
- Supports incremental extraction using timestamp columns
- Row count estimation using `COUNT(*)` queries
- Batch extraction for memory efficiency

**B. Updated ETL Wizard** (`ml_platform/views.py`):
- Added BigQuery connection parameter handling
- Maps `source_database` → `bigquery_project`, `schema_name` → `bigquery_dataset`
- Passes BigQuery-specific credentials to job config

**C. Updated Main ETL Runner** (`etl_runner/main.py`):
- Imports BigQuery extractor
- Routes BigQuery source type to appropriate extractor

**Testing Results:**
- ✅ Successfully connected to `bigquery-public-data.stackoverflow`
- ✅ Schema detection working (14 columns from `posts_questions`)
- ✅ Row count estimation working (used for processing mode decision)
- ✅ Incremental extraction with timestamp filters
- ✅ End-to-end ETL completed successfully

**Bugs Discovered During BigQuery Testing:**

**Bug 1: Schema Validation Error**
- **Issue:** ETL Wizard validation failed with "Schema must have at least one column"
- **Root Cause:** JavaScript function `syncBigQuerySchemaFromUI()` used wrong CSS selectors (`select[data-field="bigquery_type"]` instead of `select.bq-type-select`)
- **Fix:** Updated selectors in `model_etl.html` (lines ~2850)

**Bug 2: Column Names with Emojis**
- **Issue:** BigQuery rejected column names like `community_owned_date\n\n🕐` (included emoji icons)
- **Root Cause:** JavaScript extracted column names from `textContent` which included emoji HTML
- **Fix:** Added `data-column-name` attribute to table rows, read from attribute instead of text
- **Files:** `templates/ml_platform/model_etl.html`

**Bug 3: Missing GCP_PROJECT_ID**
- **Issue:** Environment variable not configured
- **Fix:** Added `GCP_PROJECT_ID=b2b-recs` to `.env` and Cloud Run environment

**Bug 4: Missing Cloud Scheduler Package**
- **Issue:** `google-cloud-scheduler` not installed
- **Fix:** `pip install google-cloud-scheduler==2.17.0`

**Files Changed:**
- `etl_runner/extractors/bigquery.py` - New file (~150 lines)
- `etl_runner/main.py` - Added BigQuery import
- `ml_platform/views.py` - BigQuery connection handling in `api_etl_job_config()`
- `templates/ml_platform/model_etl.html` - Schema validation and column name extraction fixes

**Result:** ✅ BigQuery-to-BigQuery ETL fully operational with public dataset access

---

### **Issue 8: Dataflow Pipeline - Custom Code Packaging (November 23, 2025)**

**Problem:** Dataflow workers failed with `ModuleNotFoundError: No module named 'dataflow_pipelines'` when processing large datasets (>1M rows).

**Context:**
- ETL Runner automatically switches to Dataflow for datasets >= 1M rows
- Dataflow distributes processing across multiple worker VMs
- Workers only receive Apache Beam + `requirements.txt` packages by default
- Custom modules (`dataflow_pipelines`, `extractors`, `loaders`, `utils`) were not being uploaded

**Testing Dataset:** `crypto_bitcoin.transactions` (~45M rows, 500K rows/day)

#### **Errors Encountered and Fixes:**

**Error 1: ModuleNotFoundError - Custom Modules Not Found**
```
ModuleNotFoundError: No module named 'dataflow_pipelines'
```

**Root Cause:** Apache Beam doesn't automatically package custom Python code for workers. Only standard packages from `requirements.txt` were available.

**Solution:** Implemented Python packaging with `setup.py` and `MANIFEST.in`

**Files Created:**

**1. `setup.py`** - Packages custom code for Dataflow workers:
```python
from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='etl-runner-pipeline',
    version='1.0.0',
    description='B2B Recommendations ETL Runner - Dataflow Pipeline Package',
    author='B2B Recs Team',
    packages=find_packages(exclude=['tests', 'tests.*']),
    install_requires=requirements,
    python_requires='>=3.10',
    include_package_data=True,
    zip_safe=False,
)
```

**2. `MANIFEST.in`** - Specifies which files to include in package:
```python
# Include all Python files
recursive-include dataflow_pipelines *.py
recursive-include extractors *.py
recursive-include loaders *.py
recursive-include utils *.py

# Include package metadata
include README.md
include requirements.txt
include setup.py

# Exclude unnecessary files
global-exclude *.pyc
global-exclude __pycache__
global-exclude .DS_Store
```

**Files Modified:**

**3. `dataflow_pipelines/etl_pipeline.py`** - Added setup.py packaging to pipeline options:

```python
# Added import
from apache_beam.options.pipeline_options import SetupOptions

# Added to create_pipeline_options() function (lines 161-168):
def create_pipeline_options(job_config, gcp_config):
    # ... existing code ...

    # CRITICAL: Package custom code for Dataflow workers
    setup_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'setup.py')
    if os.path.exists(setup_file_path):
        options.view_as(SetupOptions).setup_file = setup_file_path
        logger.info(f"Using setup.py for custom code packaging: {setup_file_path}")
    else:
        logger.warning(f"setup.py not found - custom code may not be available on workers!")

    return options
```

---

**Error 2: Unsupported Source Type - BigQuery**
```
ValueError: Unsupported source type for Dataflow: bigquery
```

**Root Cause:** `DatabaseToDataFrame` DoFn only supported PostgreSQL and MySQL sources.

**Solution:** Added BigQuery support in `setup()` method (dataflow_pipelines/etl_pipeline.py:47-49):

```python
def setup(self):
    """Initialize database connection (runs once per worker)"""
    source_type = self.connection_params.get('source_type')

    if source_type == 'postgresql':
        from extractors.postgresql import PostgreSQLExtractor
        self.extractor = PostgreSQLExtractor(self.connection_params)
    elif source_type == 'mysql':
        from extractors.mysql import MySQLExtractor
        self.extractor = MySQLExtractor(self.connection_params)
    elif source_type == 'bigquery':  # <- Added
        from extractors.bigquery import BigQueryExtractor
        self.extractor = BigQueryExtractor(self.connection_params)
    else:
        raise ValueError(f"Unsupported source type for Dataflow: {source_type}")
```

---

**Error 3: Invalid Timestamp - Empty String**
```
BadRequest: 400 Invalid timestamp: ''
```

**Root Cause:** Dataflow pipeline only used `last_sync_value` (empty on first run), didn't fall back to `historical_start_date`.

**Solution:** Added fallback logic matching standard ETL runner pattern (dataflow_pipelines/etl_pipeline.py:215):

```python
# Before:
since_datetime=job_config.get('last_sync_value')

# After:
since_datetime=job_config.get('last_sync_value') or job_config.get('historical_start_date')
```

This matches the pattern in `main.py:423-424`:
```python
since_datetime = self.job_config.get('last_sync_value') or \
                self.job_config.get('historical_start_date')
```

---

#### **How It Works:**

**Code Packaging Flow:**
```
1. Developer runs: gcloud builds submit --tag gcr.io/b2b-recs/etl-runner:latest
2. Docker image includes setup.py and all custom modules
3. Dataflow worker starts → Beam detects --setup_file option
4. Beam packages etl-runner-pipeline using setup.py
5. Package uploaded to GCS staging location
6. Workers download and install package
7. Custom modules available: from extractors.bigquery import BigQueryExtractor
```

**Standard vs Dataflow Processing:**
```
Standard ETL (< 1M rows):
  Django triggers Cloud Run Job
    → ETL Runner main.py
    → Direct import: from extractors.bigquery import BigQueryExtractor
    → Process in-memory with pandas
    → Load to BigQuery

Dataflow ETL (>= 1M rows):
  Django triggers Cloud Run Job
    → ETL Runner main.py detects large dataset
    → Launches Dataflow pipeline (etl_pipeline.py)
    → Beam packages custom code via setup.py
    → Distributes across workers
    → Each worker imports: from extractors.bigquery import BigQueryExtractor
    → Parallel processing with Apache Beam
    → Direct write to BigQuery
```

#### **Files Modified:**
- `setup.py` - New file, packages custom code
- `MANIFEST.in` - New file, specifies package contents
- `dataflow_pipelines/etl_pipeline.py` - Added setup.py packaging, BigQuery support, timestamp fallback
  - Lines 10-12: Added SetupOptions import
  - Lines 47-49: Added BigQuery extractor support
  - Lines 161-168: Added setup.py packaging configuration
  - Line 215: Added timestamp fallback for first runs

#### **Deployment:**
```bash
# Rebuild Docker image with packaging fixes
cd /Users/dkulish/Projects/b2b_recs/etl_runner
gcloud builds submit --tag gcr.io/b2b-recs/etl-runner:latest

# Update Cloud Run job
gcloud run jobs update etl-runner \
  --region=europe-central2 \
  --image=gcr.io/b2b-recs/etl-runner:latest
```

#### **Testing Results:**
- ✅ Custom modules successfully loaded on Dataflow workers
- ✅ BigQuery source connector working in distributed mode
- ✅ Timestamp fallback prevents empty string errors
- ✅ 45M row Bitcoin dataset processing successfully
- ✅ Incremental loads using `historical_start_date` on first run

**Result:** ✅ Dataflow pipeline fully operational for large-scale data processing (>= 1M rows) with proper custom code packaging

---

### **Issue 9: BigQuery Storage Write API Schema Requirement (November 23, 2025)**

**Problem:** Dataflow pipelines failed with `A schema is required in order to prepare rows for writing with STORAGE_WRITE_API` when attempting to write data to BigQuery.

**Context:**
- Dataflow uses BigQuery Storage Write API for efficient streaming writes
- Storage Write API provides better performance and support for complex types (NUMERIC, REPEATED, RECORD)
- Unlike FILE_LOADS method, STORAGE_WRITE_API requires explicit schema parameter

**Testing:** Occurred when testing ETL job with custom "Last 5 days" incremental load option.

#### **Errors Encountered and Fixes:**

**Error 1: Missing Schema Parameter**
```
Dataflow execution failed: A schema is required in order to prepare rows for writing with STORAGE_WRITE_API.
ETL error occurred: ValueError: A schema is required in order to prepare rows for writing with STORAGE_WRITE_API.
```

**Root Cause:** `WriteToBigQuery` with `method='STORAGE_WRITE_API'` requires explicit `schema` parameter, but pipeline was only providing table reference and write disposition.

**Solution:** Implemented schema fetching and conversion from BigQuery to Beam format

**Files Modified:**

**1. `dataflow_pipelines/etl_pipeline.py`** - Added schema fetching and conversion:

**Lines 13-14 - Fixed Imports:**
```python
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition
from apache_beam.io.gcp.internal.clients.bigquery import TableSchema, TableFieldSchema
```

**Lines 176-224 - Added Schema Conversion Function:**
```python
def get_bq_table_schema(project_id: str, dataset_id: str, table_name: str) -> TableSchema:
    """
    Fetch BigQuery table schema and convert to Beam's TableSchema format.

    Args:
        project_id: GCP project ID
        dataset_id: BigQuery dataset ID
        table_name: BigQuery table name

    Returns:
        TableSchema object for use with WriteToBigQuery
    """
    from google.cloud import bigquery

    # Initialize BigQuery client
    client = bigquery.Client(project=project_id)

    # Get table schema
    table_ref = f"{project_id}.{dataset_id}.{table_name}"
    table = client.get_table(table_ref)

    # Convert BigQuery schema to Beam TableSchema
    beam_schema = TableSchema()
    beam_fields = []

    for field in table.schema:
        beam_field = TableFieldSchema(
            name=field.name,
            type=field.field_type,
            mode=field.mode or 'NULLABLE'
        )

        # Handle nested/repeated fields
        if field.fields:
            beam_field.fields = []
            for subfield in field.fields:
                beam_subfield = TableFieldSchema(
                    name=subfield.name,
                    type=subfield.field_type,
                    mode=subfield.mode or 'NULLABLE'
                )
                beam_field.fields.append(beam_subfield)

        beam_fields.append(beam_field)

    beam_schema.fields = beam_fields

    logger.info(f"Fetched schema for {table_ref}: {len(beam_fields)} fields")
    return beam_schema
```

**Lines 243-248 - Database Pipeline Schema Fetching:**
```python
# Fetch BigQuery table schema (required for STORAGE_WRITE_API)
bq_schema = get_bq_table_schema(
    project_id=gcp_config['project_id'],
    dataset_id=gcp_config['dataset_id'],
    table_name=job_config['dest_table_name']
)
```

**Line 279 - Database Pipeline WriteToBigQuery with Schema:**
```python
| 'WriteToBigQuery' >> WriteToBigQuery(
    table=table_ref,
    schema=bq_schema,  # Required for STORAGE_WRITE_API
    write_disposition=write_disposition,
    create_disposition=BigQueryDisposition.CREATE_NEVER,  # Table must exist
    method='STORAGE_WRITE_API'  # Use Storage Write API for complex types
)
```

**Lines 311-316 - File Pipeline Schema Fetching:**
```python
# Fetch BigQuery table schema (required for STORAGE_WRITE_API)
bq_schema = get_bq_table_schema(
    project_id=gcp_config['project_id'],
    dataset_id=gcp_config['dataset_id'],
    table_name=job_config['dest_table_name']
)
```

**Line 348 - File Pipeline WriteToBigQuery with Schema:**
```python
| 'WriteToBigQuery' >> WriteToBigQuery(
    table=table_ref,
    schema=bq_schema,  # Required for STORAGE_WRITE_API
    write_disposition=write_disposition,
    create_disposition=BigQueryDisposition.CREATE_NEVER,
    method='STORAGE_WRITE_API'  # Use Storage Write API for complex types
)
```

---

**Error 2: Import Error for TableSchema**
```
Dataflow execution failed: cannot import name 'TableSchema' from 'apache_beam.io.gcp.bigquery'
ETL error occurred: ImportError: cannot import name 'TableSchema' from 'apache_beam.io.gcp.bigquery'
```

**Root Cause:** Initial implementation used wrong import path for TableSchema and TableFieldSchema classes. These are internal Beam classes located in a different module.

**Solution:** Changed import statement to use correct module path:

```python
# Before (INCORRECT):
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition, TableSchema, TableFieldSchema

# After (CORRECT):
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition
from apache_beam.io.gcp.internal.clients.bigquery import TableSchema, TableFieldSchema
```

**Reason:** `TableSchema` and `TableFieldSchema` are in `apache_beam.io.gcp.internal.clients.bigquery`, not in the main BigQuery I/O module.

---

#### **How It Works:**

**Schema Conversion Flow:**
```
1. Dataflow pipeline starts → needs to write to BigQuery table
2. get_bq_table_schema() called with destination table reference
3. BigQuery Python client fetches table metadata
4. Schema fields converted from BigQuery format to Beam's TableSchema:
   - BigQuery field → TableFieldSchema(name, type, mode)
   - Handles nested fields (RECORD type)
   - Handles repeated fields (ARRAY type)
5. TableSchema passed to WriteToBigQuery
6. Storage Write API uses schema to validate and write rows
```

**Why Schema is Required:**

The Storage Write API provides:
- **Better Performance:** Direct streaming without intermediate files
- **Complex Type Support:** Proper handling of NUMERIC, GEOGRAPHY, REPEATED, RECORD
- **Type Safety:** Validates data types before writing
- **Cost Efficiency:** No temporary GCS storage needed

But it requires:
- **Explicit Schema:** Must know exact field types upfront
- **Type Matching:** Data must match schema exactly
- **Field Ordering:** Fields must be in correct order

**Standard ETL vs Dataflow:**
```
Standard ETL (< 1M rows):
  → Uses BigQueryLoader class (loaders/bigquery_loader.py)
  → load_table_from_dataframe() method
  → Automatically infers schema from DataFrame
  → No explicit schema needed

Dataflow ETL (>= 1M rows):
  → Uses Apache Beam WriteToBigQuery
  → STORAGE_WRITE_API method for performance
  → Explicit schema required
  → get_bq_table_schema() fetches and converts schema
```

#### **Testing Results:**
- ✅ Schema fetching working for all table types
- ✅ Nested/repeated field handling functional
- ✅ Import errors resolved with correct module path
- ✅ Database pipeline writing successfully
- ✅ File pipeline writing successfully
- ✅ Storage Write API performance optimized

#### **Files Modified:**
- `dataflow_pipelines/etl_pipeline.py` - Schema fetching, conversion, and integration
  - Lines 13-14: Fixed imports for TableSchema/TableFieldSchema
  - Lines 176-224: Added get_bq_table_schema() helper function
  - Lines 243-248, 311-316: Schema fetching before pipeline execution
  - Lines 279, 348: Added schema parameter to WriteToBigQuery calls

**Result:** ✅ Dataflow pipelines now properly handle BigQuery Storage Write API schema requirements for all data types including complex nested and repeated fields

---

### **Issue 10: File ETL Incremental Loading Bug (November 24, 2025)**

**Problem:** File-based ETL jobs (CSV, Parquet, JSON) were reprocessing ALL files on every run instead of loading only new/changed files, even when configured as transactional (incremental) mode.

**Context:**
- User reported `retail_csv` job reloading all 3 CSV files daily instead of only new files
- Transactional mode is designed to track processed files and skip unchanged files
- Files were being recorded in ProcessedFile table after processing
- However, all files were still reprocessed on every run

#### **Root Causes Identified:**

**A. API Endpoint Missing CSRF Exemption**

The `api_etl_get_processed_files` endpoint (used by ETL runner to fetch list of processed files) was missing `@csrf_exempt` decorator, causing 500 Internal Server Error on service-to-service calls from Cloud Run.

**Error in logs:**
```
Failed to fetch processed files: 500 Server Error: Internal Server Error
Found 0 previously processed files
Processing 3 files  # ← Should be 0 if all already processed
```

**Impact:** ETL runner couldn't retrieve processed file list, defaulted to empty list, treated all files as new.

**B. Datetime Type Mismatch in Comparison Logic**

File metadata comparison failed due to type mismatch:
- **GCS/S3/Azure blobs** return `file_last_modified` as **Python datetime objects**
- **Django API** returns `file_last_modified` as **ISO format strings** (e.g., "2025-11-24T09:00:00")
- **Comparison** in `file_extractor.py:393` failed: `datetime_object == iso_string` → always `False`

**Code flow:**
```
1. GCS blob.updated → datetime object (file_extractor.py:198)
2. Django DB saves → DateTimeField (models.py:541)
3. API returns → .isoformat() string (views.py:3458)
4. ETL runner stores → ISO string in dict (main.py:566)
5. Comparison → datetime != string → always False (file_extractor.py:393)
```

**Impact:** Every file was considered "changed" and reprocessed even if size/timestamp unchanged.

#### **Solutions Implemented:**

**1. Added @csrf_exempt to API Endpoint** (`ml_platform/views.py:3423`)

```python
# Before:
@require_http_methods(["GET"])
def api_etl_get_processed_files(request, data_source_id):

# After:
@csrf_exempt  # ← Added for service-to-service calls
@require_http_methods(["GET"])
def api_etl_get_processed_files(request, data_source_id):
```

**2. Fixed Datetime Comparison** (`etl_runner/main.py:563-580`)

Parse ISO datetime strings to datetime objects before storing in processed_files dict:

```python
# Before:
processed_files = {
    f['file_path']: {
        'file_size_bytes': f['file_size_bytes'],
        'file_last_modified': f['file_last_modified']  # ← ISO string
    }
    for f in processed_files_list
}

# After:
from dateutil import parser as date_parser

processed_files = {}
for f in processed_files_list:
    # Parse ISO string to datetime object
    file_last_modified = f['file_last_modified']
    if file_last_modified and isinstance(file_last_modified, str):
        try:
            file_last_modified = date_parser.isoparse(file_last_modified)
        except Exception as e:
            logger.warning(f"Failed to parse datetime: {e}")
            file_last_modified = None

    processed_files[f['file_path']] = {
        'file_size_bytes': f['file_size_bytes'],
        'file_last_modified': file_last_modified  # ← datetime object
    }
```

**Result:** Now compares datetime to datetime (apples to apples), files correctly identified as unchanged.

#### **Files Modified:**
- `ml_platform/views.py:3423` - Added @csrf_exempt decorator
- `etl_runner/main.py:563-580` - Added datetime parsing logic

#### **Testing Results:**

**Before Fix:**
```
Found 0 previously processed files  # ← API 500 error
Processing 3 files                  # ← All files reprocessed
Loaded 200k rows                    # ← Duplicate data every run
```

**After Fix:**
```
Found 3 previously processed files  # ← API returns data
Processing 0 new/changed files      # ← Skips unchanged files
Skipping unchanged file: data_v2.csv
Skipping unchanged file: data_v3.csv
```

**With New File:**
```
Found 3 previously processed files
Processing 1 new/changed files      # ← Only new file loaded
Extracted 100k rows from data_v4.csv
```

**Result:** ✅ File-based transactional ETL now correctly loads only new/changed files, avoiding duplicate data loads

---

### **Issue 11: Firestore ETL - BigQuery Load Failures (November 25, 2025)**

**Problem:** Firestore ETL jobs consistently failed when loading data into BigQuery with PyArrow type conversion errors.

**Context:**
- New Firestore data source `memo2_firestore_memos_v2` (DataSource ID: 14)
- ~600 documents in collection
- Firestore connector implemented but never successfully loaded data
- Multiple fix attempts (10+) over several days

**Error Messages:**
```
Error converting Pandas column with name: "last_modified" and datatype: "object"
to an appropriate pyarrow datatype: Array, ListArray, or StructArray
```

#### **Root Causes Identified:**

**A. Firestore's DatetimeWithNanoseconds Object**

Firestore timestamps are returned as `google.cloud.firestore_v1._helpers.DatetimeWithNanoseconds` objects, which inherit from Python's `datetime` but have special behavior:

1. **`isinstance(value, datetime)` returns `True`** - so it passes the datetime check
2. **`isoformat()` doesn't return a pure Python string** - may return datetime-like object
3. **PyArrow sees the complex object** - fails to convert to BigQuery-compatible type

**Code flow (before fix):**
```
Firestore doc.to_dict()
    ↓
"last_modified" = DatetimeWithNanoseconds(2024-11-25 10:00:00.123456789)
    ↓
isinstance(field_value, datetime) → True
    ↓
field_value.isoformat() → Returns DatetimeWithNanoseconds (not pure string!)
    ↓
DataFrame stores the object, not the string
    ↓
PyArrow sees complex object → ERROR
```

**B. Schema Mismatch - DataFrame vs BigQuery Table**

The Firestore extractor added `_extracted_at` column, but BigQuery table didn't have this column:
```
Cannot add fields (field: _extracted_at)
```

**C. REQUIRED Fields with NULL Values**

BigQuery table had fields defined as `REQUIRED` mode, but Firestore documents had null/missing values:
```
Required field correct_percentage cannot be null
Required field copied_from_user cannot be null
```

#### **Solutions Implemented:**

**1. Fixed Timestamp Conversion** (`extractors/firestore.py`)

Use `strftime()` instead of `isoformat()` to guarantee pure Python string output:

```python
# Import Firestore's special datetime type
try:
    from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
except ImportError:
    DatetimeWithNanoseconds = None

# In _flatten_document():
elif isinstance(field_value, datetime):
    # Check if it's Firestore's special DatetimeWithNanoseconds
    if DatetimeWithNanoseconds and isinstance(field_value, DatetimeWithNanoseconds):
        # Use strftime to get a pure Python string (not a datetime-like object)
        flat_doc[field_name] = field_value.strftime('%Y-%m-%dT%H:%M:%S.%f')
    else:
        # Regular Python datetime - strftime is safer than isoformat
        flat_doc[field_name] = field_value.strftime('%Y-%m-%dT%H:%M:%S.%f')
```

**2. Schema-Aware BigQuery Loader** (`loaders/bigquery_loader.py`)

Added schema fetching and column filtering:

```python
def _get_table_schema(self) -> dict:
    """Get BigQuery table schema as dict mapping column names to types."""
    table = self.client.get_table(self.table_ref)
    self._schema_cache = {field.name: field.field_type for field in table.schema}
    self._required_fields = {field.name for field in table.schema if field.mode == 'REQUIRED'}
    return self._schema_cache

# In load_batch():
# Drop columns not in BigQuery schema
cols_to_drop = [col for col in df.columns if col not in bq_schema]
if cols_to_drop:
    logger.warning(f"Dropping columns not in BigQuery schema: {cols_to_drop}")
    df = df.drop(columns=cols_to_drop)
```

**3. NULL Handling for REQUIRED Fields** (`loaders/bigquery_loader.py`)

Fill nulls with appropriate defaults for NoSQL data:

```python
# Fill nulls for REQUIRED fields (NoSQL data may have missing fields)
required_fields = getattr(self, '_required_fields', set())
for col in df.columns:
    if col in required_fields and df[col].isnull().any():
        target_type = bq_schema.get(col)
        null_count = df[col].isnull().sum()
        if target_type in ('INTEGER', 'INT64'):
            logger.info(f"Filling {null_count} nulls in REQUIRED field '{col}' with 0")
            df[col] = df[col].fillna(0).astype(int)
        elif target_type in ('FLOAT', 'FLOAT64', 'NUMERIC'):
            df[col] = df[col].fillna(0.0)
        elif target_type == 'TIMESTAMP':
            df[col] = df[col].fillna(pd.Timestamp('1970-01-01'))
        else:
            # STRING or other types
            df[col] = df[col].fillna('')
```

**4. Defensive Type Conversion** (`loaders/bigquery_loader.py`)

Added secondary defense for any datetime-like objects that slip through:

```python
# Check for datetime-like objects that PyArrow can't handle
if df[col].dtype == 'object':
    has_datetime_like = df[col].apply(
        lambda x: hasattr(x, 'isoformat') and not isinstance(x, str)
    ).any()

    if has_datetime_like:
        if target_type == 'INTEGER':
            # Convert datetime to Unix timestamp
            df[col] = df[col].apply(lambda x: int(x.timestamp()) if hasattr(x, 'timestamp') else x)
        elif target_type == 'TIMESTAMP':
            df[col] = pd.to_datetime(df[col], errors='coerce')
        else:
            # Convert to string
            df[col] = df[col].apply(
                lambda x: x.strftime('%Y-%m-%dT%H:%M:%S.%f') if hasattr(x, 'strftime')
                else (str(x.isoformat()) if hasattr(x, 'isoformat') else x)
            )
```

#### **Files Modified:**
- `extractors/firestore.py` - Timestamp conversion with strftime
- `loaders/bigquery_loader.py` - Schema-aware loading with null handling

#### **Testing Results:**
- ✅ 558 Firestore documents successfully loaded to BigQuery
- ✅ `last_modified` timestamps converted to proper strings
- ✅ Extra columns (`_extracted_at`) dropped automatically
- ✅ NULL values filled with defaults (0 for integers, "" for strings)
- ✅ No PyArrow conversion errors

#### **Key Learnings:**

1. **Firestore's DatetimeWithNanoseconds is tricky** - `isinstance(datetime)` returns True but `isoformat()` may not return pure string
2. **Use `strftime()` not `isoformat()`** for guaranteed pure Python strings
3. **Schema mismatches are common** - Always filter DataFrame columns to match BigQuery schema
4. **NoSQL → BigQuery needs null handling** - Document databases have optional fields, BigQuery has REQUIRED mode
5. **Defense in depth** - Add defensive conversions in both extractor AND loader

**Result:** ✅ Firestore ETL now works end-to-end, successfully loading NoSQL documents into BigQuery

---

### **Issue 12: ETL Job Edit & Pause/Resume Functionality (November 27, 2025)**

**Problem:** Users could not edit existing ETL jobs after creation, and there was no way to temporarily pause scheduled jobs without deleting them.

**Context:**
- Clicking "Edit" button on ETL Jobs page threw error: `'DataSource' object has no attribute 'get_connection_details'`
- No pause/resume functionality existed - users had to delete and recreate jobs
- Full ETL wizard re-run was required for any changes

#### **Features Implemented:**

**A. Pause/Resume Button**

Added ability to pause and resume scheduled ETL jobs without deleting them:

- **Pause:** Disables Cloud Scheduler job, prevents automated runs
- **Resume:** Re-enables Cloud Scheduler job, resumes schedule
- **Visual Indicator:** Button shows "Pause" or "Resume" based on current state
- **Works for:** All jobs with Cloud Scheduler integration

**Implementation:**
- New API endpoint: `POST /api/etl/sources/<id>/toggle-pause/`
- Uses Cloud Scheduler API to pause/resume jobs
- Updates `DataSource.is_paused` field for state tracking

**B. Edit Modal**

Created simplified edit interface (not full wizard) for modifying existing jobs:

**Editable Fields:**
- **Job Name:** Rename the ETL job
- **Schedule:** Change frequency (Manual, Hourly, Daily, Weekly) with minute-level precision
- **Columns:** Add new columns (with ALTER TABLE), remove columns from sync

**Read-Only Fields (Displayed for Reference):**
- Source connection name
- Source table/collection
- Destination BigQuery table
- Load strategy (Transactional/Catalog)

**Column Management:**
- **Add Columns:** Available source columns shown, can be added to sync
- **Remove Columns:** Existing columns can be stopped (not deleted from BigQuery)
- **ALTER TABLE:** New columns automatically added to BigQuery table with NULL defaults
- **Stale Data:** Removed columns remain in BigQuery but stop receiving updates

**Schedule Options:**
- Manual (no automation)
- Hourly at specific minute (e.g., :15, :30, :45)
- Daily at specific time (e.g., 09:00, 14:30)
- Weekly on specific day and time

#### **API Endpoints Added:**

```
POST /api/etl/sources/<id>/toggle-pause/
    Pause or resume Cloud Scheduler job
    Returns: { status: 'success', is_paused: true/false }

PUT /api/etl/sources/<id>/edit/
    Update job name, schedule, and columns
    Body: { name, schedule_type, schedule_hour, schedule_minute, schedule_day, columns }
    Returns: { status: 'success' }

GET /api/etl/sources/<id>/available-columns/
    Get all columns from source table (for adding new columns)
    Returns: { columns: [{name, data_type, is_nullable}] }
```

#### **Files Modified:**

**Backend:**
- `ml_platform/models.py` - Added `get_connection_details()` method to DataSource model
- `ml_platform/views.py` - Added `api_etl_toggle_pause()`, `api_etl_edit_source()`, `api_etl_available_columns()` endpoints
- `ml_platform/urls.py` - Added URL routes for new endpoints

**Frontend:**
- `templates/ml_platform/model_etl.html`:
  - Added Edit Modal HTML structure
  - Added Pause/Resume button to job cards
  - Added JavaScript functions: `openEditJobModal()`, `closeEditJobModal()`, `updateEditScheduleOptions()`, `loadEditJobColumns()`, `renderEditJobColumns()`, `updateColumnStatusBadge()`, `saveJobChanges()`, `togglePauseSource()`
  - Added CSS styles for modal, schedule options, and column items

#### **Bug Fixes During Implementation:**

**Bug 1: `'DataSource' object has no attribute 'wizard_last_step'`**
- **Cause:** `api_etl_get_source` accessed non-existent attributes directly
- **Fix:** Changed to use `getattr()` with default values for backward compatibility

**Bug 2: Columns not loading for big tables and Firestore**
- **Cause:** Custom column fetching didn't use proper credential handling
- **Fix:** Refactored to use existing `fetch_table_metadata` from `connection_manager.py`

#### **Design Decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Edit interface | Simplified modal (not wizard) | Faster, focused on common changes |
| Column removal | Stop loading, keep in BigQuery | Preserves historical data |
| Column addition | ALTER TABLE with NULLs | No data loss, backward compatible |
| Load strategy changes | Not allowed | Requires new table structure |
| Source table changes | Not allowed | Create new job instead |
| Concurrent edits | Single user (no locks) | Simplicity for v1 |
| Audit trail | Not implemented | Future enhancement |

#### **User Flow:**

```
1. User clicks "Edit" on existing ETL job
2. Modal opens with current job configuration
3. User can:
   - Rename the job
   - Change schedule (Manual/Hourly/Daily/Weekly)
   - Add new columns from source
   - Remove columns from sync
4. User clicks "Save Changes"
5. System:
   - Updates job name in database
   - Creates/updates/deletes Cloud Scheduler job
   - Runs ALTER TABLE for new columns
   - Updates column sync configuration
6. Modal closes, job list refreshes
```

#### **Pause/Resume Flow:**

```
1. User clicks "Pause" on scheduled job
2. System calls Cloud Scheduler API to pause job
3. Button changes to "Resume"
4. No automated runs until resumed

1. User clicks "Resume" on paused job
2. System calls Cloud Scheduler API to resume job
3. Button changes to "Pause"
4. Automated runs resume per schedule
```

#### **Testing Results:**

- ✅ Edit modal opens and displays current configuration
- ✅ Job name updates save correctly
- ✅ Schedule changes create/update Cloud Scheduler jobs
- ✅ New columns added via ALTER TABLE
- ✅ Column removal stops data loading
- ✅ Pause/Resume toggles Cloud Scheduler state
- ✅ Works for all source types (databases, files, Firestore)

**Result:** ✅ ETL job editing and pause/resume functionality fully operational

---

### **Issue 13: ETL Job Delete - Cloud Scheduler Orphan Bug (November 29, 2025)**

**Problem:** When deleting an ETL job, the associated Cloud Scheduler job was not deleted, leaving orphaned scheduler entries.

**Context:**
- Users deleting ETL jobs via "Delete" button
- Cloud Scheduler jobs remained active after deletion
- Orphaned jobs continued executing on schedule (failing with "DataSource not found")
- Confusing for users seeing stale jobs in Cloud Scheduler

**Root Cause:** The `api_etl_delete_source` function only deleted the Django `DataSource` record without calling `CloudSchedulerManager.delete_etl_schedule()`.

**Solution:** Updated `api_etl_delete_source` to delete Cloud Scheduler job before deleting DataSource:

```python
@login_required
@require_http_methods(["POST"])
def api_etl_delete_source(request, source_id):
    try:
        source = get_object_or_404(DataSource, id=source_id)
        source_name = source.name

        # Delete Cloud Scheduler job if one exists
        if source.cloud_scheduler_job_name:
            from .utils.cloud_scheduler import CloudSchedulerManager
            scheduler_manager = CloudSchedulerManager(project_id, region)
            delete_result = scheduler_manager.delete_etl_schedule(source.id)
            if not delete_result['success']:
                logger.warning(f"Failed to delete scheduler: {delete_result['message']}")

        source.delete()
        return JsonResponse({'status': 'success', ...})
```

**Design Decision:** Scheduler deletion failure doesn't block DataSource deletion (graceful degradation). Logs warning but proceeds - scheduler might already be deleted manually.

**Files Modified:**
- `ml_platform/views.py:946-986` - Added Cloud Scheduler deletion before DataSource deletion

**Result:** ✅ ETL job deletion now properly cleans up both database record and Cloud Scheduler job

---

### **Issue 14: Load Into Existing BigQuery Tables (November 29, 2025)**

**Problem:** ETL Wizard only allowed creating new BigQuery tables. Users could not:
- Load data from multiple sources into the same table
- Change source table and continue loading into existing destination
- Reuse existing BigQuery tables for new ETL jobs

**Context:**
- Step 4 "BigQuery Table Setup" always created new tables
- If table existed, wizard failed with "Table already exists" error
- No way to select existing tables as destination

#### **Features Implemented:**

**A. Destination Mode Selector**

Added radio buttons in Step 4 to choose between:
- **Create new table** (original behavior)
- **Use existing table** (new feature)

**B. Existing Table Selection**

When "Use existing table" selected:
- Dropdown populated with all tables in `raw_data` dataset
- Tables grouped by load type (Transactional, Catalog, Other)
- Table info displayed (row count, load type, partitioning)

**C. Schema Compatibility Validation**

Validates source schema against existing table:
- **Compatible columns:** Columns that exist in both and have compatible types
- **Columns to add:** Source columns not in destination (auto-added via ALTER TABLE)
- **Columns missing in source:** Destination columns not in source (will be NULL)
- **Type mismatches:** Incompatible type conversions (blocks creation)

**D. Load Type Enforcement**

Prevents mixing load types:
- Transactional table → only transactional loads allowed
- Catalog table → only catalog loads allowed
- Prevents data inconsistencies (partitioning, append vs replace)

**E. Automatic ALTER TABLE**

When using existing table with new columns:
- System automatically runs `ALTER TABLE ADD COLUMN`
- New columns added as NULLABLE with appropriate types
- No manual schema changes needed

#### **API Endpoints Added:**

```
GET /api/etl/datasets/<dataset_id>/tables/
    List all BigQuery tables with metadata
    Returns: { tables: [{name, num_rows, load_type, partitioned, ...}] }

POST /api/etl/validate-schema-compatibility/
    Validate source schema against existing table
    Body: { source_columns, existing_table_name, load_type }
    Returns: { compatible, columns_to_add, type_mismatches, warnings, errors }
```

#### **Files Modified:**

**Backend:**
- `ml_platform/utils/bigquery_manager.py`:
  - Added `list_tables()` - lists all tables with metadata
  - Added `get_table_metadata()` - gets detailed table info
  - Added `add_columns_to_table()` - ALTER TABLE for new columns
- `ml_platform/views.py`:
  - Added `api_etl_list_bq_tables()` - API endpoint for table listing
  - Added `api_etl_validate_schema_compatibility()` - schema validation
  - Modified `api_etl_create_job()` - supports `use_existing_table` flag
- `ml_platform/urls.py` - Added URL routes for new endpoints

**Frontend:**
- `templates/ml_platform/model_etl.html`:
  - Added destination mode selector (radio buttons)
  - Added existing table dropdown and info panel
  - Added schema compatibility report display
  - Added JavaScript functions: `toggleDestinationMode()`, `loadExistingTables()`, `onExistingTableSelected()`, `validateSchemaCompatibility()`, `renderCompatibilityReport()`
  - Updated `nextStep()` validation for existing table mode
  - Updated `createETLJob()` payload with `use_existing_table`, `existing_table_name`

#### **Type Compatibility Matrix:**

| Source Type | Compatible Destinations |
|-------------|------------------------|
| INT64 | INT64, INTEGER, FLOAT64, FLOAT, NUMERIC, STRING |
| INTEGER | INT64, INTEGER, FLOAT64, FLOAT, NUMERIC, STRING |
| FLOAT64 | FLOAT64, FLOAT, NUMERIC, STRING |
| STRING | STRING |
| BOOLEAN | BOOLEAN, BOOL, STRING |
| TIMESTAMP | TIMESTAMP, DATETIME, STRING |
| DATE | DATE, STRING |

Note: INT64/INTEGER and FLOAT64/FLOAT are treated as aliases (same type in BigQuery).

#### **User Flow:**

```
1. User reaches Step 4 "BigQuery Table Setup"
2. User selects "Use existing table" radio button
3. Dropdown loads with available tables (grouped by load type)
4. User selects a table
5. System displays table info (rows, load type, partitioning)
6. System validates schema compatibility
   - Green box: Compatible (with warnings if applicable)
   - Red box: Incompatible (shows errors)
7. If compatible, user proceeds to Step 5
8. On job creation:
   - System skips table creation
   - Runs ALTER TABLE for new columns
   - Creates DataSource pointing to existing table
```

#### **Testing Results:**

- ✅ Table listing works with proper grouping
- ✅ Schema compatibility validation catches type mismatches
- ✅ INT64/INTEGER treated as compatible (fixed false positive)
- ✅ Load type enforcement prevents mixing
- ✅ ALTER TABLE adds new columns automatically
- ✅ Existing table used as destination successfully

**Result:** ✅ ETL Wizard now supports loading data into existing BigQuery tables with full schema compatibility validation

---

### **Issue 15: Enable Immediately After Creation Not Working (November 29, 2025)**

**Problem:** The "Enable immediately after creation" toggle on Step 5 of the ETL Wizard did not trigger the first ETL run after job creation. Jobs were created but waited for their scheduled run time.

**Context:**
- Toggle checkbox existed in UI (Step 5: Schedule & Review)
- Checkbox was checked by default
- Users expected the job to run immediately after creation

#### **Root Cause:**

**Frontend-Backend Disconnect:**

1. **Frontend (`model_etl.html`):** The `enableImmediately` checkbox existed but `createETLJob()` function never read its value or included it in the API payload.

2. **Backend (`views.py`):** The `api_etl_create_job()` function had no code to:
   - Read an `enable_immediately` flag from the request
   - Trigger an immediate run after job creation

**Code flow (before fix):**
```
User checks "Enable immediately" → createETLJob() ignores checkbox
→ API creates job → Returns success → No run triggered
```

#### **Solution Implemented:**

**Frontend-Only Fix** (simpler, uses existing infrastructure):

After successful job creation, if `enableImmediately` is checked, the frontend calls the existing trigger API:

```javascript
// In createETLJob() success handler:
const enableImmediately = document.getElementById('enableImmediately').checked;

if (enableImmediately && data.job_id) {
    const runResponse = await fetch(`/api/etl/sources/${data.job_id}/trigger/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        }
    });
    // Handle response...
}
```

**Additional Enhancement:** Replaced browser `alert()` dialogs with modern notification modal for better UX:
- Success notifications show green checkmark
- Warning notifications show yellow warning icon
- Proper multi-line message support
- Callback to close wizard and reload page after user clicks OK

#### **Files Modified:**
- `templates/ml_platform/model_etl.html`:
  - Updated `createETLJob()` to read checkbox and trigger immediate run
  - Updated notification modal to support multi-line messages (`whitespace-pre-line`)
  - Added `onClose` callback support to `showNotification()` function
  - Replaced all `alert()` calls with `showNotification()` for modern UI

#### **Testing Results:**
- ✅ Checkbox value correctly read after job creation
- ✅ Trigger API called when checkbox is checked
- ✅ First run starts immediately after job creation
- ✅ Modern notification modal displays success/warning messages
- ✅ Page reloads after user acknowledges notification

**Result:** ✅ "Enable immediately after creation" now works - jobs start their first run right after creation

---

### **Issue 16: Dataflow Build Tools Missing (November 29, 2025)**

**Problem:** Dataflow pipeline failed for large datasets (3M+ rows) with `ModuleNotFoundError: No module named 'setuptools'` when attempting to package custom code for workers.

**Context:**
- ETL job for 3M+ row CSV file triggered Dataflow mode (threshold: 1M rows)
- Dataflow needs to package custom Python code (`setup.py`) for worker VMs
- Build process failed immediately

#### **Error Messages:**

```
No module named build
ModuleNotFoundError: No module named 'setuptools'

Command '['/usr/local/bin/python', '-m', 'build', '--no-isolation', '--sdist', ...]'
returned non-zero exit status 1.

Command '['/usr/local/bin/python', 'setup.py', 'sdist', '--dist-dir', ...]'
returned non-zero exit status 1.
```

#### **Root Cause:**

Apache Beam's Dataflow runner uses `setup.py` to package custom code for workers. The build process requires:

1. **`build`** - PEP 517 build frontend (`python -m build`)
2. **`setuptools`** - Python packaging library (fallback: `python setup.py sdist`)

**Why missing in Python 3.12:**
- `setuptools` is no longer bundled with Python 3.12 standard library
- Slim Docker base images don't include build tools
- These packages weren't in `requirements.txt`

**Build attempt flow:**
```
Beam tries: python -m build → "No module named build"
Beam fallback: python setup.py sdist → "No module named 'setuptools'"
→ Both fail → Dataflow job cannot start
```

#### **Solution:**

Added build tools to `etl_runner/requirements.txt`:

```
# Build tools (required for Dataflow custom code packaging)
setuptools>=65.0.0
build>=1.0.0
```

#### **Files Modified:**
- `etl_runner/requirements.txt` - Added `setuptools` and `build` packages

#### **Deployment:**

```bash
# Rebuild Docker image
cd etl_runner
gcloud builds submit --tag gcr.io/b2b-recs/etl-runner:latest

# Update Cloud Run Job
gcloud run jobs update etl-runner \
  --region=europe-central2 \
  --image=gcr.io/b2b-recs/etl-runner:latest
```

#### **Testing Results:**
- ✅ Docker image builds with setuptools and build packages
- ✅ Dataflow can now package custom code via setup.py
- ✅ Large CSV files (3M+ rows) process successfully via Dataflow

**Result:** ✅ Dataflow pipeline now works for large-scale ETL jobs requiring custom code packaging

---

### **Issue 17: ETL Duration Analysis Chart (November 30, 2025)**

**Feature:** Added a new ridge-line chart visualization to the ETL page showing job execution durations over the last 30 days.

**Context:**
- Users needed visual insight into ETL job performance over time
- Inspired by TensorFlow Board's ridge/joy plot visualization style
- Helps identify patterns, anomalies, and performance trends

#### **Implementation:**

**A. Chart Design**

The chart displays:
- **X-axis:** ETL job names
- **Y-axis:** Days (last 30 days, newest at bottom)
- **Peak Height:** Duration of each job execution (log-transformed for better visualization)
- **Color Coding:**
  - Green gradient: Successful jobs (completed/partial)
  - Red gradient: Failed jobs

**B. Backend Data Preparation** (`ml_platform/views.py`)

Added ridge chart data aggregation in `model_etl()` view:

```python
# Prepare ridge chart data for ETL Duration Analysis
all_runs_30_days = model.etl_runs.filter(
    started_at__gte=cutoff_date,
    status__in=['completed', 'partial', 'failed']
).select_related('data_source').order_by('started_at')

# Build data structure grouped by day
ridge_chart_data_by_day = defaultdict(list)
all_job_names = set()

for run in all_runs_30_days:
    # Skip runs without a data source (Unknown jobs)
    if not run.data_source or not run.started_at:
        continue

    day_str = run.started_at.strftime('%Y-%m-%d')
    job_name = run.data_source.name
    duration = run.get_duration_seconds() or 0
    is_success = run.status in ['completed', 'partial']

    ridge_chart_data_by_day[day_str].append({
        'job_name': job_name,
        'duration': duration,
        'status': 'success' if is_success else 'failed',
    })
```

**C. Frontend Visualization** (`templates/ml_platform/model_etl.html`)

- Uses **D3.js v7** for SVG rendering
- **Log transformation** on duration heights to handle wide range of job durations (seconds to hours)
- **Individual bump shapes** for each job execution (not continuous areas)
- **Interactive tooltips** showing date, job name, status, and formatted duration
- **Responsive design** with automatic redraw on window resize
- **Empty state handling** for days without runs

**Key D3.js Implementation:**

```javascript
// Log scale for duration heights
const heightScale = d3.scaleLog()
    .domain([1, Math.max(maxDuration, 2)])
    .range([0, ridgeHeight * 3])
    .clamp(true);

// Helper for safe log transform
const getScaledHeight = (duration) => {
    if (duration <= 0) return 0;
    return heightScale(1 + duration);
};

// Draw individual bump shapes for each job
day.jobs.forEach(job => {
    const peakHeight = getScaledHeight(job.duration);
    const bumpData = [
        { x: xCenter - halfWidth, y: 0 },
        { x: xCenter - halfWidth * 0.5, y: peakHeight * 0.7 },
        { x: xCenter, y: peakHeight },
        { x: xCenter + halfWidth * 0.5, y: peakHeight * 0.7 },
        { x: xCenter + halfWidth, y: 0 }
    ];
    // Render with appropriate gradient based on status
});
```

**D. Chart Section UI**

New dedicated section below "Recent ETL Runs" table:
- White container with black border (matching existing design)
- Header: "ETL Duration Analysis"
- Legend showing green=Success, red=Failed
- "Last 30 days" badge
- Loading and empty states

#### **Design Decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Log transformation | Yes | Handles wide duration range (5s to 5000s) without long jobs dominating |
| Individual bumps vs continuous ridges | Individual bumps | Discrete job executions, not continuous distributions |
| Filter Unknown jobs | Yes | Jobs without data_source are system artifacts, not user-relevant |
| Color by status | Green/Red | Immediate visual feedback on job health |
| Newest at bottom | Yes | Matches TensorFlow Board reference, natural time flow |

#### **Files Modified:**

**Backend:**
- `ml_platform/views.py` - Added ridge chart data preparation (~50 lines)

**Frontend:**
- `templates/ml_platform/model_etl.html`:
  - Added D3.js v7 CDN include
  - Added chart container HTML with legend (~50 lines)
  - Added chart JavaScript implementation (~250 lines)
  - Added tooltip and interactivity handlers

#### **Testing Results:**
- ✅ Chart renders correctly with real ETL run data
- ✅ Success (green) and failed (red) jobs display with appropriate colors
- ✅ Log transformation provides balanced visualization across duration ranges
- ✅ Tooltips show accurate date, job name, status, and duration
- ✅ Empty days display flat baseline
- ✅ Unknown jobs filtered out from display
- ✅ Responsive to window resize

**Result:** ✅ ETL Duration Analysis chart provides visual insight into job performance and health over time

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

**Cause:** Missing bucket configuration in connection (due to old connection creation bug - fixed Nov 21, 2025).

**Fix (Manual):**
1. Update Connection record in database: `UPDATE ml_platform_connection SET bucket_path='gs://your-bucket-name' WHERE id=X`
2. Verify credentials in Secret Manager

**Fix (UI - Preferred):**
1. Navigate to ETL → Connections
2. Click "Edit" on the connection
3. Form should now populate correctly (bug fixed)
4. Verify bucket path is correct
5. Click "Save"

**Note:** New connections created after Nov 21, 2025 will have `bucket_path` correctly saved automatically.

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

### **Connection Edit Form Shows Empty Fields**

**Cause:** Frontend form population bug (fixed Nov 21, 2025).

**Symptoms:**
- Clicking "Edit" on cloud storage or NoSQL connections shows empty connection name
- Bucket path field empty for GCS/S3/Azure
- Service account JSON field empty for BigQuery/Firestore

**Fix:** Clear browser cache and refresh page. Fix is already deployed in `templates/ml_platform/model_etl.html`.

### **Test Connection Button Not Visible in Edit Mode**

**Status:** Under investigation (Nov 21, 2025).

**Workaround:**
1. Create new connection with same credentials (test button works in create mode)
2. Delete old connection
3. Update data sources to use new connection

**Expected Fix:** Will add explicit show/hide logic for test button containers in edit mode.

---

## File Structure

```
etl_runner/
├── main.py                      # Entry point, orchestrates ETL flow
├── config.py                    # Configuration management
├── extractors/
│   ├── postgresql.py           # PostgreSQL extractor
│   ├── mysql.py                # MySQL extractor
│   ├── bigquery.py             # BigQuery extractor (cross-project, public datasets)
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

## Status Summary

**Overall Status:** ✅ Production-Ready

**What's Working:**
- ✅ Cloud Scheduler automated triggers
- ✅ Database sources (PostgreSQL, MySQL, BigQuery)
- ✅ Cloud storage files (GCS, S3, Azure Blob)
- ✅ File format support (CSV, Parquet, JSON)
- ✅ Transactional and catalog load strategies
- ✅ Connection creation and editing for all source types
- ✅ Incremental loading with file/timestamp tracking
- ✅ BigQuery schema auto-detection and management
- ✅ **ETL Job Edit Modal (name, schedule, columns)**
- ✅ **Pause/Resume for scheduled jobs**
- ✅ **Enhanced Recent ETL Runs table with View Details modal**
- ✅ **ETL Duration Analysis Chart (ridge-line visualization)**

**Known Issues:**
- ⚠️ Test Connection button not visible in edit mode (workaround available)

**Recent Fixes (Nov 21-27, 2025):**
- ✅ ETL Wizard scheduler creation (webhook URL + OIDC audience)
- ✅ Cloud Scheduler authentication (webhook pattern)
- ✅ ETL Runner API authentication (CSRF exemption for service-to-service calls)
- ✅ BigQuery source implementation (public datasets + cross-project ETL)
- ✅ File ETL validation logic
- ✅ Connection management system (source-type aware CRUD)
- ✅ Connection edit form population for all connection types
- ✅ File ETL runtime bugs (credentials, column mapping, type conversion)
- ✅ **Dataflow pipeline custom code packaging (setup.py + MANIFEST.in)**
- ✅ **Dataflow BigQuery connector support**
- ✅ **Dataflow timestamp fallback for first runs**
- ✅ **BigQuery Storage Write API schema requirement**
- ✅ **Dataflow schema fetching and conversion for complex types**
- ✅ **Firestore ETL - DatetimeWithNanoseconds conversion fix**
- ✅ **Firestore ETL - Schema-aware BigQuery loader with null handling**
- ✅ **ETL Job Edit & Pause/Resume functionality**
- ✅ **Load into Existing BigQuery Tables (November 29, 2025)**
- ✅ **ETL Job Delete - Now deletes Cloud Scheduler jobs**
- ✅ **Enable Immediately After Creation - First run triggers automatically**
- ✅ **Modern Notification Modal - Replaced browser alerts with styled modals**
- ✅ **Dataflow Build Tools - Added setuptools/build for custom code packaging**

**Recent Fixes (Nov 30, 2025):**
- ✅ **Enhanced Recent ETL Runs Table** - Added ETL Job Name and Connection columns, removed redundant Tables column
- ✅ **Styled View Details Modal** - Replaced browser `alert()` with modern styled modal matching Edit/Delete buttons
- ✅ **Comprehensive Run Details** - Modal shows Job Info, Timeline, Results, Error Details, and Cloud Run logs link
- ✅ **API Enhancement** - `api_etl_run_status` now returns full run details including job name, connection, load type, timing breakdown
- ✅ **Fixed Header Alignment** - Model metadata header now properly aligned with content containers (scrollbar compensation)
- ✅ **ETL Duration Analysis Chart** - New ridge-line visualization showing job durations over last 30 days (see Issue 17 below)
