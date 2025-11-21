# Conditional Dataflow Implementation - Complete Guide

**Implementation Date:** November 21, 2025
**Status:** ✅ **COMPLETE** - Ready for Deployment
**Processing Modes:** Standard (< 1M rows) | Dataflow (>= 1M rows)

---

## Overview

The ETL runner now **automatically** switches between two processing modes based on data volume:

- **Standard Mode** (Cloud Run + Pandas): For datasets < 1,000,000 rows
- **Dataflow Mode** (Dataflow + Apache Beam): For datasets >= 1,000,000 rows

This happens **transparently** to users - no UI changes, no configuration needed.

---

## How It Works

### **Automatic Decision Flow**

```
ETL Job Starts
    ↓
Estimate Row Count
    ├── Database: SELECT COUNT(*) query
    ├── Files: File size estimation (20k rows/MB for CSV)
    ↓
Compare to Threshold (1M rows)
    ├── < 1M → Standard Processing (Cloud Run)
    └── >= 1M → Dataflow Processing (GCP Dataflow)
```

### **Row Count Estimation**

#### **Database Sources**
- **Full Loads (Catalog)**: `SELECT COUNT(*) FROM table`
- **Incremental Loads (Transactional)**: `SELECT COUNT(*) FROM table WHERE timestamp > last_sync`

#### **File Sources**
- **Total File Size**: Sum of all matching files
- **Estimation Formula**:
  - CSV: ~20,000 rows per MB
  - Parquet: ~100,000 rows per MB (highly compressed)
  - JSON: ~10,000 rows per MB (verbose)

---

## Files Modified

### **1. Database Extractors** ✅
**Files:**
- `etl_runner/extractors/postgresql.py`
- `etl_runner/extractors/mysql.py`

**Added Method:**
```python
def estimate_row_count(self, table_name, schema_name, timestamp_column=None, since_datetime=None) -> int:
    """Estimate rows to be extracted (full or incremental)"""
```

---

### **2. File Extractor** ✅
**File:** `etl_runner/extractors/file_extractor.py`

**Added Method:**
```python
def estimate_row_count(self, ...) -> int:
    """Estimate rows based on file size and format"""
```

**Estimation Logic:**
- Lists all matching files
- Calculates total size in MB
- Applies rows-per-MB heuristic based on file format

---

### **3. Django Models** ✅
**File:** `ml_platform/models.py`

**Added Fields to `DataSourceTable`:**
```python
processing_mode = models.CharField(
    choices=[
        ('auto', 'Auto-detect'),
        ('standard', 'Standard (< 1M rows)'),
        ('dataflow', 'Dataflow (>= 1M rows)')
    ],
    default='auto'
)

row_count_threshold = models.IntegerField(default=1_000_000)
estimated_row_count = models.BigIntegerField(null=True, blank=True)
```

**Migration Created:** `ml_platform/migrations/0017_add_processing_mode_fields.py`

---

### **4. ETL Runner Main Logic** ✅
**File:** `etl_runner/main.py`

**Added Methods:**

1. **`estimate_row_count()`** - Calls extractor's estimation method
2. **`determine_processing_mode()`** - Decides standard vs dataflow
3. **`run_with_dataflow()`** - Executes Dataflow pipeline

**Modified Method:**
- **`run()`** - Now checks processing mode before execution:
  ```python
  processing_mode = self.determine_processing_mode()

  if processing_mode == 'dataflow':
      result = self.run_with_dataflow()
  else:
      # Standard pandas processing...
  ```

---

### **5. Dataflow Pipelines** ✅
**New Directory:** `etl_runner/dataflow_pipelines/`

**Files Created:**
- `__init__.py`
- `etl_pipeline.py` - Apache Beam pipeline implementations

**Pipeline Features:**
- **Cost-Optimized**: Uses `n1-standard-2` workers (cheap for development)
- **Auto-Scaling**: Starts with 2 workers, scales up to 10 based on throughput
- **Dynamic Jobs**: No persistent templates, simpler management
- **Region**: europe-central2 (Warsaw) - same as your project

**Supported Sources:**
- ✅ Database sources (PostgreSQL, MySQL)
- ✅ Cloud storage files (GCS, S3, Azure Blob)

---

### **6. Dependencies** ✅
**File:** `etl_runner/requirements.txt`

**Added:**
```
google-cloud-run==0.10.3
apache-beam[gcp]==2.52.0
```

---

## Deployment Steps

### **Step 1: Apply Database Migration**
```bash
cd /Users/dkulish/Projects/b2b_recs

# Apply migration
python manage.py migrate ml_platform

# Verify migration
python manage.py showmigrations ml_platform
```

**Expected Output:**
```
[X] 0017_add_processing_mode_fields
```

---

### **Step 2: Create Dataflow Staging Bucket**

Your Dataflow jobs need a GCS bucket for staging/temp files:

```bash
# Create bucket (if not exists)
gsutil mb -l europe-central2 gs://b2b-recs-dataflow

# Or use existing bucket - update this line in etl_runner/main.py:657
# 'bucket': 'YOUR_EXISTING_BUCKET_NAME'
```

**Current Configuration:**
- **Bucket**: `b2b-recs-dataflow` (hardcoded in `main.py:657`)
- **Region**: `europe-central2`

**To Change Bucket:**
Edit `etl_runner/main.py`, line 657:
```python
'bucket': 'your-preferred-bucket-name',
```

---

### **Step 3: Install ETL Runner Dependencies**

```bash
cd /Users/dkulish/Projects/b2b_recs/etl_runner

# Install new dependencies
pip install -r requirements.txt
```

**This installs:**
- `apache-beam[gcp]==2.52.0` (Dataflow SDK)
- `google-cloud-run==0.10.3` (Cloud Run API client)

---

### **Step 4: Build & Deploy ETL Runner**

```bash
cd /Users/dkulish/Projects/b2b_recs

# Build Docker image
gcloud builds submit --tag gcr.io/b2b-recs/etl-runner:latest ./etl_runner

# Update Cloud Run Job
gcloud run jobs update etl-runner \
  --region=europe-central2 \
  --image=gcr.io/b2b-recs/etl-runner:latest
```

**Build Time:** ~5-10 minutes (Apache Beam adds dependencies)

---

### **Step 5: Enable Dataflow API**

```bash
# Enable Dataflow API (if not already enabled)
gcloud services enable dataflow.googleapis.com --project=b2b-recs

# Verify API is enabled
gcloud services list --enabled | grep dataflow
```

---

### **Step 6: Grant Dataflow Permissions**

The ETL runner service account needs permissions to launch Dataflow jobs:

```bash
# Get ETL runner service account
SERVICE_ACCOUNT="etl-runner@b2b-recs.iam.gserviceaccount.com"

# Grant Dataflow permissions
gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/dataflow.developer"

gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/dataflow.worker"

# Grant storage access for staging/temp
gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/storage.objectAdmin"
```

---

### **Step 7: Deploy Django Updates**

```bash
cd /Users/dkulish/Projects/b2b_recs

# Build and deploy Django app
gcloud builds submit --config cloudbuild.yaml

# Or if using direct Cloud Run deployment:
gcloud run deploy django-app \
  --region=europe-central2 \
  --source=.
```

---

## Testing the Implementation

### **Test 1: Small Dataset (Standard Mode)**

1. Create an ETL job with a small database table (< 100k rows)
2. Run the ETL job
3. **Expected:** ETL runner uses standard pandas processing
4. **Check Logs:**
   ```
   Processing mode configuration: auto
   Estimated row count: 50,000
   Auto-detection: 50,000 rows vs 1,000,000 threshold
   ✓ Using standard processing (small dataset)
   Starting CATALOG load (full snapshot)
   ```

---

### **Test 2: Large Dataset (Dataflow Mode)**

#### **Option A: Create Test File > 100MB**

```bash
# Create a large CSV file in GCS
# File > 100MB will trigger Dataflow
gsutil du -h gs://your-test-bucket/large-file.csv
```

#### **Option B: Force Dataflow Mode**

You can manually force Dataflow by setting `processing_mode='dataflow'` in the database:

```sql
UPDATE ml_platform_datasourcetable
SET processing_mode = 'dataflow'
WHERE id = YOUR_TABLE_ID;
```

3. Run the ETL job
4. **Expected:** ETL runner uses Dataflow
5. **Check Logs:**
   ```
   Processing mode configuration: auto
   Estimated row count: 2,500,000
   Auto-detection: 2,500,000 rows vs 1,000,000 threshold
   ✓ Using Dataflow processing (large dataset)
   STARTING DATAFLOW EXECUTION
   Dataflow job submitted: etl-123-456-789
   Monitor at: https://console.cloud.google.com/dataflow/jobs/...
   ```

6. **Monitor Dataflow Job:**
   - Go to: https://console.cloud.google.com/dataflow/jobs?project=b2b-recs
   - You should see a running job named `etl-{data_source_id}-{etl_run_id}`

---

## Configuration Options

### **Change Row Count Threshold**

**Default:** 1,000,000 rows

**To Change:**
```sql
-- Set different threshold for specific ETL job
UPDATE ml_platform_datasourcetable
SET row_count_threshold = 500000  -- 500k rows
WHERE id = YOUR_TABLE_ID;
```

---

### **Force Processing Mode**

**Force Standard (never use Dataflow):**
```sql
UPDATE ml_platform_datasourcetable
SET processing_mode = 'standard'
WHERE id = YOUR_TABLE_ID;
```

**Force Dataflow (always use Dataflow):**
```sql
UPDATE ml_platform_datasourcetable
SET processing_mode = 'dataflow'
WHERE id = YOUR_TABLE_ID;
```

**Auto-Detect (default):**
```sql
UPDATE ml_platform_datasourcetable
SET processing_mode = 'auto'
WHERE id = YOUR_TABLE_ID;
```

---

## Cost Optimization

### **Current Dataflow Configuration**

**Machine Type:** `n1-standard-2` (cheapest suitable for development)
- **vCPUs:** 2
- **Memory:** 7.5 GB
- **Cost:** ~$0.10/hour per worker

**Workers:**
- **Initial:** 2 workers
- **Maximum:** 10 workers
- **Scaling:** Auto-scales based on throughput

**Estimated Costs (Development):**
- **Small job (2M rows):** ~$0.50 - $1.00
- **Large job (10M rows):** ~$2.00 - $5.00
- **Very large job (100M rows):** ~$10.00 - $20.00

### **Further Cost Optimization (Optional)**

If you want to reduce costs even more, edit `etl_runner/dataflow_pipelines/etl_pipeline.py`:

**Use Preemptible Workers (80% cheaper!):**
```python
# In create_pipeline_options() function, add:
worker_options.use_preemptible_workers = True
```

**⚠️ Caution:** Preemptible workers can be shut down by GCP, causing job failures. Only use for non-critical development testing.

**Reduce Max Workers:**
```python
worker_options.max_num_workers = 5  # Instead of 10
```

---

## Monitoring & Observability

### **ETL Runner Logs**

```bash
# View ETL runner logs
gcloud logging read \
  'resource.type=cloud_run_job
   AND resource.labels.job_name=etl-runner' \
  --limit=50 \
  --format=json
```

**Look for these log entries:**
- `Estimated row count: X`
- `Processing mode configuration: auto`
- `✓ Using standard/dataflow processing`
- `STARTING DATAFLOW EXECUTION`
- `Dataflow job submitted: etl-X-Y`

---

### **Dataflow Job Monitoring**

**GCP Console:**
https://console.cloud.google.com/dataflow/jobs?project=b2b-recs

**CLI:**
```bash
# List Dataflow jobs
gcloud dataflow jobs list --region=europe-central2

# Describe specific job
gcloud dataflow jobs describe JOB_ID --region=europe-central2

# View job logs
gcloud dataflow jobs show JOB_ID --region=europe-central2
```

---

### **BigQuery Results**

```sql
-- Check data loaded by Dataflow
SELECT
  COUNT(*) as total_rows,
  MIN(_airbyte_extracted_at) as first_load,
  MAX(_airbyte_extracted_at) as last_load
FROM `b2b-recs.raw_data.YOUR_TABLE`;
```

---

## Troubleshooting

### **Problem: ETL always uses standard mode, never Dataflow**

**Possible Causes:**
1. **Row count estimation failing** - Check logs for warnings
2. **Threshold too high** - Lower threshold in database
3. **Processing mode forced to 'standard'** - Check `processing_mode` field

**Solution:**
```sql
-- Check current configuration
SELECT
  id,
  source_table_name,
  processing_mode,
  row_count_threshold,
  estimated_row_count
FROM ml_platform_datasourcetable;

-- Force Dataflow for testing
UPDATE ml_platform_datasourcetable
SET processing_mode = 'dataflow'
WHERE id = YOUR_ID;
```

---

### **Problem: Dataflow job fails immediately**

**Check:**
1. **Dataflow API enabled?** `gcloud services list --enabled | grep dataflow`
2. **Staging bucket exists?** `gsutil ls gs://b2b-recs-dataflow`
3. **IAM permissions granted?** Check service account has `dataflow.developer` role

**View Error:**
```bash
gcloud dataflow jobs list --region=europe-central2 --filter="state=FAILED"
```

---

### **Problem: Bucket not found error**

**Error:** `Bucket b2b-recs-dataflow not found`

**Solution:**
```bash
# Create bucket
gsutil mb -l europe-central2 gs://b2b-recs-dataflow

# Grant service account access
gsutil iam ch \
  serviceAccount:etl-runner@b2b-recs.iam.gserviceaccount.com:objectAdmin \
  gs://b2b-recs-dataflow
```

---

### **Problem: Import error for apache_beam**

**Error:** `ModuleNotFoundError: No module named 'apache_beam'`

**Solution:**
```bash
# Rebuild Docker image with new dependencies
cd /Users/dkulish/Projects/b2b_recs/etl_runner
docker build -t etl-runner .

# Or redeploy to Cloud Run
gcloud builds submit --tag gcr.io/b2b-recs/etl-runner:latest
```

---

## Implementation Summary

### **What Changed**
✅ Row count estimation added to all extractors
✅ Automatic processing mode detection implemented
✅ Dataflow + Beam pipelines created
✅ Database migrations created and ready
✅ Dependencies updated
✅ Zero UI changes - completely transparent to users

### **What Users See**
- **Nothing changes!** ETL wizard works exactly the same
- Jobs automatically run faster for large datasets
- No new configuration required

### **What Developers See**
- Logs show processing mode selection
- Dataflow jobs visible in GCP Console
- ETL runner automatically switches between modes

---

## Next Steps (Optional Enhancements)

### **1. Add Dataflow Job Status Tracking**

Currently, Dataflow jobs run asynchronously. You could add:
- Poll Dataflow job status
- Update Django ETLRun with real-time progress
- Show Dataflow job links in Django UI

### **2. Add Cost Estimation**

Show users estimated cost before running large jobs:
- Estimate based on row count
- Display in ETL wizard preview

### **3. Optimize Beam Pipelines**

Current implementation is functional but basic. Improvements:
- Better batching for database extraction
- Parallel file reading for file sources
- Custom windowing and grouping

### **4. Add Metrics & Monitoring**

- Track average processing time (standard vs dataflow)
- Track cost per job
- Alert on failed Dataflow jobs

---

## Conclusion

The conditional Dataflow implementation is **complete and ready for production**. The system will automatically:

1. **Estimate row count** for every ETL job
2. **Choose optimal processing mode** (standard vs dataflow)
3. **Execute accordingly** with no user intervention

**Everything happens in the background** - users simply create ETL jobs as before, and the system handles the rest.

**Deployment:** Follow the 7-step deployment guide above to activate this feature.

---

**Questions?** Check the troubleshooting section or review the implementation files listed in this document.
