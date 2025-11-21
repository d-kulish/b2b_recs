# BigQuery to BigQuery ETL Testing Guide
**Testing Automatic Dataflow Detection with Stack Overflow Data**

---

## **Overview**

This guide will walk you through setting up a test ETL job that:
1. **Source**: BigQuery public dataset (Stack Overflow questions - ~20M records)
2. **Destination**: Your BigQuery table in `raw_data` dataset
3. **First run**: Loads last 200 days (~3.5M questions) → **Automatically uses Dataflow** ✅
4. **Daily runs**: Loads last 1 day (~7k questions) → **Automatically uses pandas** ✅

This tests the complete automatic decision-making system without any manual intervention.

---

## **Prerequisites**

✅ **Already completed** (you confirmed):
- Dataflow API enabled
- Service account has `roles/bigquery.dataViewer` and `roles/bigquery.jobUser`
- Migrations applied

**New requirement**:
- Service account needs `roles/bigquery.dataEditor` to create destination table

---

## **Step 1: Grant BigQuery Permissions**

```bash
# Your service account email
SERVICE_ACCOUNT="etl-runner@b2b-recs.iam.gserviceaccount.com"

# Grant permissions to write to raw_data dataset
gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/bigquery.dataEditor"

# Verify permissions
gcloud projects get-iam-policy b2b-recs \
  --flatten="bindings[].members" \
  --filter="bindings.members:${SERVICE_ACCOUNT}"
```

**Expected roles:**
- `roles/bigquery.jobUser` ✅
- `roles/bigquery.dataViewer` ✅
- `roles/bigquery.dataEditor` ✅ (just added)
- `roles/dataflow.developer` ✅ (from previous setup)
- `roles/dataflow.worker` ✅ (from previous setup)

---

## **Step 2: Create BigQuery Connection**

### **Option A: Via Django Admin UI** (Recommended)

1. **Navigate to**: `https://your-django-app.com/admin/ml_platform/connection/add/`

2. **Fill in the form:**

   **Connection Details:**
   - **Name**: `BigQuery - Stack Overflow Public Data`
   - **Source Type**: `BigQuery`
   - **Description**: `Testing automatic Dataflow detection with Stack Overflow questions`

   **BigQuery Configuration:**
   - **BigQuery Project**: `bigquery-public-data`
   - **BigQuery Dataset**: `stackoverflow`

   **Model Endpoint**: Select your model

3. **Save connection**

4. **Store credentials in Secret Manager:**

```bash
# Create service account JSON secret (use your default credentials)
cat > /tmp/bq-credentials.json <<EOF
{
  "service_account_json": ""
}
EOF

# Store in Secret Manager
gcloud secrets create bq-stackoverflow-connection \
  --data-file=/tmp/bq-credentials.json \
  --replication-policy="automatic"

# Clean up temp file
rm /tmp/bq-credentials.json
```

5. **Update connection in Django Admin:**
   - **Credentials Secret Name**: `bq-stackoverflow-connection`
   - Save

---

### **Option B: Via Direct Database Insert** (Faster)

```sql
-- Connect to your PostgreSQL database
\c your_database_name

-- Insert BigQuery connection
INSERT INTO ml_platform_connection (
  model_endpoint_id,
  name,
  source_type,
  bigquery_project,
  bigquery_dataset,
  credentials_secret_name,
  is_active,
  created_at,
  updated_at
) VALUES (
  1,  -- Replace with your model_endpoint_id
  'BigQuery - Stack Overflow Public Data',
  'bigquery',
  'bigquery-public-data',
  'stackoverflow',
  'bq-stackoverflow-connection',
  TRUE,
  NOW(),
  NOW()
) RETURNING id;

-- Note the returned ID (e.g., 15)
```

---

## **Step 3: Create Destination BigQuery Table**

The destination table will store Stack Overflow questions. Let's create it:

```bash
# Create BigQuery table for Stack Overflow questions
bq mk --table \
  b2b-recs:raw_data.stackoverflow_questions \
  id:INTEGER,title:STRING,creation_date:TIMESTAMP,score:INTEGER,view_count:INTEGER,answer_count:INTEGER,owner_user_id:INTEGER,tags:STRING
```

**Verify table created:**
```bash
bq show b2b-recs:raw_data.stackoverflow_questions
```

**Expected output:**
```
Table b2b-recs:raw_data.stackoverflow_questions

   Last modified         Schema         Total Rows   Total Bytes
 ----------------- ------------------- ------------ -------------
  DD MMM HH:MM:SS   |- id: integer     0            0
                    |- title: string
                    |- creation_date: timestamp
                    |- score: integer
                    |- view_count: integer
                    |- answer_count: integer
                    |- owner_user_id: integer
                    |- tags: string
```

---

## **Step 4: Create ETL Job via ETL Wizard**

### **4.1 Start ETL Wizard**

Navigate to: `https://your-django-app.com/ml-platform/models/{model_id}/etl/`

### **4.2 Step 1: Select Connection**

- **ETL Job Name**: `stackoverflow_questions_daily`
- **Connection**: Select `BigQuery - Stack Overflow Public Data`
- Click **Next**

### **4.3 Step 2: Select Table**

- **Schema**: `stackoverflow` (auto-filled)
- **Table Name**: `posts_questions`
- **Preview**: You'll see Stack Overflow questions with columns like `id`, `title`, `creation_date`, etc.
- Click **Next**

### **4.4 Step 3: Configure Load Strategy**

- **Load Type**: ✅ **Transactional (Append-Only)**
- **Timestamp Column**: `creation_date`
- **Historical Backfill**: Select **Custom date...**
  - Enter date: **200 days ago** (e.g., if today is Nov 21, 2025, enter `2025-05-05`)
  - This will load ~3.5M questions on first run → **triggers Dataflow** 🎯
- **Selected Columns**: Leave all selected (or select: `id`, `title`, `creation_date`, `score`, `view_count`, `answer_count`, `owner_user_id`, `tags`)
- Click **Next**

### **4.5 Step 4: BigQuery Table Setup**

- **BigQuery Table Name**: `stackoverflow_questions`
- **Schema**: Review auto-generated schema
- Modify if needed (e.g., set `view_count` to NULLABLE)
- Click **Next**

### **4.6 Step 5: Schedule**

- **Schedule Type**: **Daily**
- **Run Time**: Select a convenient time (e.g., `03:00 AM`)
- **Timezone**: Your timezone (e.g., `Europe/Warsaw`)
- Click **Create ETL Job**

---

## **Step 5: Verify ETL Job Created**

```sql
-- Check the ETL job was created
SELECT
  ds.id as data_source_id,
  ds.name,
  ds.source_type,
  ds.use_incremental,
  ds.incremental_column,
  ds.historical_start_date,
  dst.source_table_name,
  dst.dest_table_name,
  dst.load_type,
  dst.timestamp_column,
  dst.processing_mode,
  dst.row_count_threshold,
  dst.schedule_type
FROM ml_platform_datasource ds
JOIN ml_platform_datasourcetable dst ON dst.data_source_id = ds.id
WHERE ds.name = 'stackoverflow_questions_daily';
```

**Expected output:**
```
data_source_id | 42
name | stackoverflow_questions_daily
source_type | bigquery
use_incremental | true
incremental_column | creation_date
historical_start_date | 2025-05-05 (200 days ago)
source_table_name | posts_questions
dest_table_name | stackoverflow_questions
load_type | transactional
timestamp_column | creation_date
processing_mode | auto
row_count_threshold | 1000000
schedule_type | daily
```

---

## **Step 6: Run First ETL Load (Manual Trigger)**

Let's manually trigger the first load to test Dataflow detection:

### **6.1 Trigger ETL Run via UI**

1. Go to ETL jobs page
2. Find `stackoverflow_questions_daily`
3. Click **Run Now** button

### **6.2 OR Trigger via API**

```bash
# Get data source ID from previous SQL query (e.g., 42)
DATA_SOURCE_ID=42

curl -X POST \
  https://your-django-app.com/api/etl/sources/${DATA_SOURCE_ID}/trigger-now/ \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json"
```

---

## **Step 7: Monitor ETL Execution**

### **7.1 Watch ETL Runner Logs**

```bash
# Stream ETL runner logs in real-time
gcloud logging tail \
  'resource.type=cloud_run_job
   AND resource.labels.job_name=etl-runner' \
  --format=json \
  | jq -r '.textPayload // .jsonPayload.message'
```

**Expected log sequence:**

```
ETL RUN STARTED
DataSource ID: 42
Load Type: transactional
Source: stackoverflow.posts_questions

Processing mode configuration: auto
Estimated row count: 3,547,892
Auto-detection: 3,547,892 rows vs 1,000,000 threshold
✓ Using Dataflow processing (large dataset)

================================================================================
STARTING DATAFLOW EXECUTION
================================================================================

Launching Dataflow pipeline for DATABASE source
Dataflow job submitted: etl-42-1234567890

================================================================================
DATAFLOW JOB SUBMITTED
Job Name: etl-42-1234567890
Monitor at: https://console.cloud.google.com/dataflow/jobs/europe-central2/etl-42-1234567890
================================================================================
```

🎉 **SUCCESS!** The system automatically detected 3.5M rows and chose Dataflow!

---

### **7.2 Monitor Dataflow Job**

**GCP Console:**
https://console.cloud.google.com/dataflow/jobs?project=b2b-recs&region=europe-central2

**CLI:**
```bash
# List running Dataflow jobs
gcloud dataflow jobs list --region=europe-central2 --status=active

# Get job details
gcloud dataflow jobs describe JOB_ID --region=europe-central2
```

**Expected Dataflow job:**
- **Name**: `etl-42-XXXXXXXX`
- **Region**: `europe-central2`
- **Workers**: 2-10 (auto-scaling)
- **Status**: Running
- **Records**: ~3.5M

**Estimated Duration:** 10-20 minutes for 3.5M rows

---

### **7.3 Monitor Progress in BigQuery**

```sql
-- Check rows loaded so far
SELECT
  COUNT(*) as total_rows,
  MIN(creation_date) as earliest_date,
  MAX(creation_date) as latest_date
FROM `b2b-recs.raw_data.stackoverflow_questions`;

-- Refresh every minute to see progress
-- Expected final count: ~3.5M rows
```

---

## **Step 8: Verify First Load Completed**

### **8.1 Check ETL Run Status**

```sql
-- Check ETL run completed
SELECT
  id,
  status,
  started_at,
  completed_at,
  total_rows_extracted,
  rows_loaded,
  duration_seconds,
  ROUND(duration_seconds::numeric / 60, 2) as duration_minutes
FROM ml_platform_etlrun
WHERE etl_config_id IN (
  SELECT etl_config_id
  FROM ml_platform_datasource
  WHERE name = 'stackoverflow_questions_daily'
)
ORDER BY started_at DESC
LIMIT 1;
```

**Expected:**
```
status | completed
total_rows_extracted | ~3,500,000
rows_loaded | ~3,500,000
duration_minutes | 10-20
```

---

### **8.2 Verify Data in BigQuery**

```sql
-- Sample loaded data
SELECT
  id,
  title,
  creation_date,
  score,
  view_count,
  tags
FROM `b2b-recs.raw_data.stackoverflow_questions`
WHERE creation_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 200 DAY)
ORDER BY creation_date DESC
LIMIT 10;
```

**Expected:** Recent Stack Overflow questions from the last 200 days

---

### **8.3 Check Last Sync Value Updated**

```sql
-- Verify last_sync_value was updated
SELECT
  id,
  name,
  last_sync_value,
  incremental_column
FROM ml_platform_datasource
WHERE name = 'stackoverflow_questions_daily';
```

**Expected:**
```
last_sync_value | 2025-11-21T12:34:56.789Z (most recent creation_date from loaded data)
```

---

## **Step 9: Test Daily Incremental Load (Pandas)**

Now let's test that **daily incremental loads automatically use pandas** (because ~7k rows < 1M).

### **9.1 Wait for Scheduled Run or Trigger Manually**

**Option A: Wait for scheduled daily run** (e.g., tomorrow at 3 AM)

**Option B: Trigger manually right now:**

```bash
# Trigger second run
curl -X POST \
  https://your-django-app.com/api/etl/sources/${DATA_SOURCE_ID}/trigger-now/ \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

---

### **9.2 Watch Logs for Automatic pandas Selection**

```bash
# Stream logs
gcloud logging tail \
  'resource.type=cloud_run_job
   AND resource.labels.job_name=etl-runner' \
  --format=json \
  | jq -r '.textPayload // .jsonPayload.message'
```

**Expected log sequence:**

```
ETL RUN STARTED
DataSource ID: 42
Load Type: transactional

Processing mode configuration: auto
Estimated row count: 7,234
Auto-detection: 7,234 rows vs 1,000,000 threshold
✓ Using standard processing (small dataset)

Starting TRANSACTIONAL load (incremental)
Extracting data since: 2025-11-21T12:34:56.789Z
Starting incremental data extraction...
Extracted batch 1: 7234 rows
Transactional load completed successfully: 7,234 rows in 1 batches
```

🎉 **SUCCESS!** The system automatically detected 7k rows and chose pandas!

---

### **9.3 Verify Incremental Load**

```sql
-- Check second ETL run used pandas (smaller duration)
SELECT
  id,
  status,
  total_rows_extracted,
  rows_loaded,
  duration_seconds,
  ROUND(duration_seconds::numeric / 60, 2) as duration_minutes
FROM ml_platform_etlrun
WHERE etl_config_id IN (
  SELECT etl_config_id
  FROM ml_platform_datasource
  WHERE name = 'stackoverflow_questions_daily'
)
ORDER BY started_at DESC
LIMIT 2;
```

**Expected:**
```
Run 1 (First load - Dataflow):
  total_rows_extracted | ~3,500,000
  duration_minutes | 10-20

Run 2 (Incremental - pandas):
  total_rows_extracted | ~7,000
  duration_minutes | 0.5-2
```

---

## **Success Criteria**

✅ **First load (200 days)**:
- Estimated ~3.5M rows
- Automatically selected Dataflow
- Dataflow job visible in GCP Console
- Data loaded to BigQuery successfully

✅ **Incremental loads (daily)**:
- Estimated ~7k rows per day
- Automatically selected pandas
- Completed in < 2 minutes
- Only new questions loaded (since last_sync_value)

✅ **Zero manual intervention**:
- No manual `processing_mode` changes
- System automatically decides based on row count
- Logs show clear decision-making

---

## **Troubleshooting**

### **Problem: "Destination table does not exist"**

**Cause:** Destination table not created in Step 3

**Solution:**
```bash
bq mk --table \
  b2b-recs:raw_data.stackoverflow_questions \
  id:INTEGER,title:STRING,creation_date:TIMESTAMP,score:INTEGER,view_count:INTEGER,answer_count:INTEGER,owner_user_id:INTEGER,tags:STRING
```

---

### **Problem: "Permission denied" on BigQuery**

**Cause:** Service account missing BigQuery permissions

**Solution:**
```bash
SERVICE_ACCOUNT="etl-runner@b2b-recs.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/bigquery.dataEditor"
```

---

### **Problem: ETL uses pandas for first load (should use Dataflow)**

**Possible causes:**
1. Historical date too recent (< 200 days) → Try 365 days
2. Row count estimation failed → Check logs for errors
3. Threshold too high → Lower threshold to 500k for testing

**Debug:**
```sql
-- Check configuration
SELECT processing_mode, row_count_threshold, historical_start_date
FROM ml_platform_datasourcetable
WHERE dest_table_name = 'stackoverflow_questions';

-- Expected:
-- processing_mode = 'auto'
-- row_count_threshold = 1000000
-- historical_start_date = ~200 days ago
```

---

### **Problem: Dataflow job fails immediately**

**Check:**
```bash
# View Dataflow job logs
gcloud dataflow jobs list --region=europe-central2 --status=failed

# Get error message
gcloud dataflow jobs describe FAILED_JOB_ID --region=europe-central2
```

**Common issues:**
- Staging bucket doesn't exist → Create `gs://b2b-recs-dataflow`
- Missing Dataflow permissions → Grant `roles/dataflow.developer`
- Invalid service account → Check credentials in Secret Manager

---

## **Next Steps After Testing**

1. **Monitor daily runs**: Check that incremental loads run smoothly daily
2. **Review costs**: Check Dataflow costs in GCP Billing
3. **Adjust threshold**: If needed, change `row_count_threshold` for your use case
4. **Add more ETL jobs**: Apply same pattern to other BigQuery datasets

---

## **Testing Checklist**

- [ ] BigQuery connection created
- [ ] Destination table created
- [ ] ETL job created with 200-day historical range
- [ ] First load triggered manually
- [ ] Logs show "Using Dataflow processing"
- [ ] Dataflow job visible in GCP Console
- [ ] ~3.5M rows loaded successfully
- [ ] Second incremental load triggered
- [ ] Logs show "Using standard processing"
- [ ] ~7k rows loaded in < 2 minutes
- [ ] No manual intervention needed

---

## **Summary**

This test validates the complete automatic conditional loading system:

1. ✅ **Row count estimation** works for BigQuery sources
2. ✅ **Automatic threshold comparison** (3.5M > 1M → Dataflow, 7k < 1M → pandas)
3. ✅ **Dataflow execution** for large initial load
4. ✅ **Pandas execution** for small incremental loads
5. ✅ **Zero manual configuration** - system decides automatically
6. ✅ **Incremental tracking** works (last_sync_value updated)

**The system is production-ready!** 🚀
