# ETL Runner

**Last Updated:** November 20, 2025
**Status:** Phases 1-5 COMPLETE ✅ | File ETL Runner COMPLETE ✅

Cloud Run-based ETL execution engine for the B2B Recommendations Platform. Extracts data from source databases (PostgreSQL, MySQL) and cloud storage files (GCS, S3, Azure Blob) and loads to BigQuery.

## Current Status

### ✅ COMPLETED (Phase 1 + Phase 2)

**Phase 1: ETL Runner Implementation**
- ✅ Complete ETL runner codebase (~2,600 lines)
- ✅ PostgreSQL & MySQL extractors with memory-efficient streaming
- ✅ BigQuery loader with batch processing
- ✅ Deployed to Cloud Run (europe-central2)
- ✅ Docker image built and pushed to GCR
- ✅ Service accounts configured with proper IAM roles

**Phase 2: Django Integration & BigQuery Setup**
- ✅ BigQuery table creation during ETL wizard
- ✅ Django API endpoints for ETL runner communication
- ✅ Manual "Run Now" trigger functionality
- ✅ Cloud Scheduler utility module created
- ✅ IAM permissions configured (BigQuery Admin, Cloud Run Admin)
- ✅ Region configuration: europe-central2 (Warsaw, Poland)

**What Works Now:**
- ✅ Create ETL jobs through Django wizard (5 steps)
- ✅ BigQuery tables created automatically with schema
- ✅ Cloud Run ETL runner deployed and accessible
- ✅ Manual trigger API endpoint ready
- ✅ Progress tracking infrastructure in place

**Phase 3: Flat File ETL Wizard UI/UX (November 19-20, 2025)**
- ✅ Conditional Step 3 UI for database vs file sources
- ✅ File metadata tracking (file_size_bytes, file_last_modified)
- ✅ File selection with checkboxes (user picks specific files)
- ✅ Transactional vs Catalog load strategies for files
- ✅ Incremental file loading with metadata comparison
- ✅ Selected files stored in DataSourceTable.selected_files
- ✅ Database migration created and applied (0014)
- ✅ Minimalistic UI design with white backgrounds (Nov 20)
- ✅ Modern notification modal system (Nov 20)
- ✅ Smart navigation button states (Nov 20)
- ✅ Standardized button styling across all modals (Nov 20)

**Phase 4: Advanced Scheduling System (November 20, 2025)**
- ✅ Professional scheduling interface in Step 5
- ✅ Automatic timezone detection (uses browser timezone)
- ✅ Minute-level control for hourly schedules (0-59)
- ✅ Time picker for daily/weekly/monthly schedules
- ✅ Day-of-week selection for weekly schedules
- ✅ Day-of-month selection for monthly schedules (1st-31st)
- ✅ Dynamic cron expression generation
- ✅ Schedule data persistence in database
- ✅ Cloud Scheduler integration with full parameters

**Phase 5: File ETL Runner Implementation (November 20, 2025 - Evening)**
- ✅ FileExtractor class with GCS/S3/Azure Blob support
- ✅ File listing and metadata tracking
- ✅ CSV/Parquet/JSON format parsing
- ✅ Incremental file loading with ProcessedFile tracking
- ✅ Catalog and transactional load modes for files
- ✅ Django API endpoints for file tracking
- ✅ Full integration with main ETL runner

**What's Missing:**
- ⚠️ End-to-end testing with actual GCS bucket
- ⚠️ Real-time status monitoring UI (Phase 6)

## Overview

This ETL runner is designed to run as a Cloud Run Job, triggered either manually or by Cloud Scheduler. It:

1. Fetches job configuration from the Django API
2. Extracts data from source databases (PostgreSQL/MySQL)
3. Loads data to BigQuery in batches
4. Reports progress and status back to Django

## Architecture

```
Cloud Scheduler → Cloud Run Job → Source Database (PostgreSQL/MySQL)
                       ↓
                   BigQuery Table
                       ↓
                 Django API (status updates)
```

## Features

### Database Sources
- **Multiple Source Types**: PostgreSQL, MySQL support
- **Two Load Modes**:
  - **Catalog**: Full snapshot (WRITE_TRUNCATE then WRITE_APPEND)
  - **Transactional**: Incremental by timestamp column (WRITE_APPEND only)
- **Memory Efficient**: Streams data in batches (default: 10K rows)
- **Progress Tracking**: Real-time status updates to Django
- **Error Handling**: Retry logic with exponential backoff
- **Cloud Logging**: JSON-formatted logs for Cloud Logging integration

### Flat File Sources (NEW - Nov 19, 2025)
- **Cloud Storage Support**: Google Cloud Storage (GCS), AWS S3, Azure Blob Storage
- **File Formats**: CSV, Parquet, JSON/JSONL
- **File Selection**: User can select specific files via checkboxes (prevents accidental loading)
- **Two Load Strategies**:
  - **Transactional (Incremental)**:
    - Tracks processed files by path, size, and modification date
    - Only loads new or changed files
    - Appends to BigQuery table
    - Detects file changes automatically
  - **Catalog (Snapshot)**:
    - User chooses: "Latest file only" or "All matched files"
    - Replaces BigQuery table on each run
    - Best for daily snapshots or multi-region merges
- **Schema Detection**: Automatic schema inference from sample file
- **ProcessedFile Tracking**: Prevents duplicate loads and detects file changes

### Advanced Scheduling (NEW - Nov 20, 2025)

Professional-grade scheduling system integrated with Google Cloud Scheduler:

**Schedule Types:**
- **Manual**: No automatic execution (run on demand only)
- **Hourly**: Every hour at a specified minute (0-59)
  - Example: `:00`, `:15`, `:30`, `:45`
  - Use case: Near real-time data sync
- **Daily**: Once per day at a specific time
  - Example: `09:00`, `14:30`, `23:00`
  - Use case: Daily reports, overnight batch processing
- **Weekly**: Once per week on a specific day and time
  - Days: Monday through Sunday
  - Example: "Every Friday at 17:00"
  - Use case: Weekly aggregations, end-of-week reports
- **Monthly**: Once per month on a specific day and time
  - Days: 1st through 31st
  - Example: "15th of every month at 14:00"
  - Use case: Monthly reconciliation, billing cycles

**Key Features:**
- ✅ **Automatic Timezone Detection**: Uses user's browser timezone (no manual selection needed)
- ✅ **Minute-level Precision**: Hourly jobs can run at any minute (:00, :15, :30, :45, etc.)
- ✅ **Flexible Time Selection**: 24-hour time picker for daily/weekly/monthly schedules
- ✅ **Dynamic UI**: Schedule options appear/disappear based on selected type
- ✅ **Cloud Scheduler Integration**: Automatically creates/updates Cloud Scheduler jobs
- ✅ **Cron Expression Generation**: Converts user-friendly selections to cron syntax

**Generated Cron Examples:**
```
Hourly at :30     → 30 * * * *
Daily at 09:00    → 0 9 * * *
Daily at 14:30    → 30 14 * * *
Weekly (Fri 17:00)→ 0 17 * * 5
Monthly (15th 14:00)→ 0 14 15 * *
```

**Database Fields:**
- `schedule_type`: Schedule frequency (manual/hourly/daily/weekly/monthly)
- `schedule_timezone`: User's timezone (auto-detected)
- `schedule_time`: Time in HH:MM format (for daily/weekly/monthly)
- `schedule_minute`: Minute 0-59 (for hourly)
- `schedule_day_of_week`: 0=Monday through 6=Sunday
- `schedule_day_of_month`: 1-31 for monthly schedules

## Directory Structure

```
etl_runner/
├── main.py                 # Entry point and orchestrator
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container image definition
├── extractors/
│   ├── base.py           # BaseExtractor abstract class
│   ├── postgresql.py     # PostgreSQL extractor
│   └── mysql.py          # MySQL extractor
├── loaders/
│   └── bigquery_loader.py # BigQuery loader
└── utils/
    ├── logging_config.py  # Logging configuration
    └── error_handling.py  # Error handling utilities
```

## Configuration

The ETL runner is configured via environment variables:

### Required Environment Variables

- `GCP_PROJECT_ID`: GCP project ID
- `DJANGO_API_URL`: Django API base URL (e.g., `https://app.example.com`)

### Optional Environment Variables

- `ETL_API_TOKEN`: Bearer token for Django API authentication
- `BIGQUERY_DATASET`: BigQuery dataset name (default: `raw_data`)
- `ETL_BATCH_SIZE`: Rows per batch (default: `10000`)
- `ETL_MAX_RETRIES`: Max retry attempts (default: `3`)
- `ETL_RETRY_DELAY`: Initial retry delay in seconds (default: `5`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

## External Database Access Configuration

### Connecting to Cloud SQL in Other Projects

When extracting data from Cloud SQL databases in different GCP projects (e.g., memo2 project):

**Required Setup:**
1. **Enable Public IP** on source Cloud SQL instance
2. **Whitelist Cloud Run IPs** in source database authorized networks:
   - Go to Cloud Console → Source Project → Cloud SQL → Instance → Connections → Networking
   - Add authorized network: `0.0.0.0/0` (for testing/development)
   - **Production**: Narrow to specific Cloud Run IP ranges or use Cloud NAT with static IP

**Connection Configuration:**
- Host: Source Cloud SQL public IP (e.g., `34.116.170.252`)
- Port: `5432` (PostgreSQL) or `3306` (MySQL)
- Database: Database name
- Username: Database user
- Password: Database password (stored in Django, retrieved by ETL runner)

**Security Notes:**
- `0.0.0.0/0` allows access from anywhere - only use for testing
- Cloud Run uses dynamic IPs from Google's IP ranges
- For production: Use Cloud NAT ($40/month) for static IP or whitelist specific IP ranges
- Alternative: VPC peering between projects (complex setup)

### Quick Open/Test/Close for memo2 Database

**When you need to test ETL with memo2:**

```bash
# 1. OPEN - Allow all IPs temporarily
gcloud sql instances patch memo2-db \
  --project=memo2-456215 \
  --authorized-networks=0.0.0.0/0 \
  --quiet

# 2. TEST - Run your ETL job from Django UI
# Visit: https://django-app-3dmqemfmxq-lm.a.run.app
# Navigate to model → ETL → Run Now

# 3. CLOSE - Remove all access
gcloud sql instances patch memo2-db \
  --project=memo2-456215 \
  --clear-authorized-networks \
  --quiet
```

**Current Status:** memo2-db is **CLOSED** (no authorized networks)

## Usage

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GCP_PROJECT_ID="your-project-id"
export DJANGO_API_URL="http://localhost:8000"

# Run ETL job
python main.py --data_source_id 123 --etl_run_id 456
```

### Docker

```bash
# Build image
docker build -t etl-runner .

# Run container
docker run \
  -e GCP_PROJECT_ID="your-project-id" \
  -e DJANGO_API_URL="https://app.example.com" \
  etl-runner \
  --data_source_id 123 \
  --etl_run_id 456
```

### Cloud Run Deployment

```bash
# Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/etl-runner

# Deploy to Cloud Run Jobs
gcloud run jobs deploy etl-runner \
  --image gcr.io/PROJECT_ID/etl-runner \
  --region us-central1 \
  --memory 8Gi \
  --cpu 4 \
  --timeout 3600 \
  --max-retries 1 \
  --service-account etl-runner@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=PROJECT_ID,DJANGO_API_URL=https://app.example.com
```

### Executing Cloud Run Job

```bash
# Execute manually
gcloud run jobs execute etl-runner \
  --region us-central1 \
  --args="--data_source_id=123,--etl_run_id=456"
```

## Command-Line Arguments

- `--data_source_id` (required): DataSource ID to process
- `--etl_run_id` (optional): ETL Run ID for status tracking
- `--log_level` (optional): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--json_logs` (optional): Use JSON log formatting (default: True)

## Django API Endpoints

The ETL runner expects the following Django API endpoints:

### `GET /api/etl/job-config/{data_source_id}/`

Returns job configuration:

```json
{
  "source_type": "postgresql",
  "connection_params": {
    "host": "db.example.com",
    "port": 5432,
    "database": "mydb",
    "username": "user",
    "password": "pass"
  },
  "source_table_name": "transactions",
  "schema_name": "public",
  "dest_table_name": "bq_transactions",
  "load_type": "transactional",
  "timestamp_column": "created_at",
  "selected_columns": ["id", "amount", "created_at"],
  "last_sync_value": "2024-01-01T00:00:00",
  "historical_start_date": "2023-01-01"
}
```

### `PATCH /api/etl/runs/{etl_run_id}/update/`

Updates ETL run status:

```json
{
  "status": "completed",
  "rows_extracted": 50000,
  "rows_loaded": 50000,
  "duration_seconds": 120
}
```

## Permissions & IAM Configuration

### Required Service Accounts

**1. Django App Service Account:** `django-app@b2b-recs.iam.gserviceaccount.com`
- Used by Django app running on Cloud Run
- Creates and manages Cloud Scheduler jobs
- Triggers ETL runner executions

**2. ETL Runner Service Account:** `etl-runner@b2b-recs.iam.gserviceaccount.com`
- Used by ETL runner Cloud Run Job
- Accesses source data (databases, cloud storage)
- Writes to BigQuery

### IAM Roles Granted

#### Django App Service Account Permissions:
```bash
# Cloud Scheduler management
roles/cloudscheduler.admin
  - cloudscheduler.jobs.create
  - cloudscheduler.jobs.delete
  - cloudscheduler.jobs.get
  - cloudscheduler.jobs.update
  - cloudscheduler.jobs.run
  - cloudscheduler.jobs.pause
  - cloudscheduler.jobs.resume

# Service account impersonation (to act as etl-runner)
roles/iam.serviceAccountUser on etl-runner@b2b-recs.iam.gserviceaccount.com
  - iam.serviceAccounts.actAs
  - iam.serviceAccounts.getAccessToken

# BigQuery (for table creation during wizard)
roles/bigquery.admin
  - bigquery.datasets.create
  - bigquery.tables.create
  - bigquery.tables.get

# Cloud Run (for triggering etl-runner)
roles/run.admin
  - run.jobs.run
  - run.operations.get

# Secret Manager (for fetching credentials)
roles/secretmanager.admin
  - secretmanager.versions.access
```

#### ETL Runner Service Account Permissions:
```bash
# BigQuery data operations
roles/bigquery.dataEditor
  - bigquery.tables.get
  - bigquery.tables.getData
  - bigquery.tables.updateData

roles/bigquery.user
  - bigquery.jobs.create

# Cloud Run invocation (so Cloud Scheduler can trigger it)
roles/run.invoker
  - run.jobs.run

# Cloud Storage (for file-based sources)
roles/storage.objectViewer (inherited from project)
  - storage.buckets.get
  - storage.objects.get
  - storage.objects.list
```

### Setup Commands

**Enable required APIs:**
```bash
gcloud services enable cloudscheduler.googleapis.com --project=b2b-recs
gcloud services enable run.googleapis.com --project=b2b-recs
gcloud services enable bigquery.googleapis.com --project=b2b-recs
```

**Grant permissions to Django app:**
```bash
# Cloud Scheduler admin
gcloud projects add-iam-policy-binding b2b-recs \
    --member="serviceAccount:django-app@b2b-recs.iam.gserviceaccount.com" \
    --role="roles/cloudscheduler.admin"

# Service account user (to act as etl-runner)
gcloud iam service-accounts add-iam-policy-binding \
    etl-runner@b2b-recs.iam.gserviceaccount.com \
    --member="serviceAccount:django-app@b2b-recs.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"
```

**Grant permissions to ETL runner:**
```bash
# Cloud Run invoker
gcloud projects add-iam-policy-binding b2b-recs \
    --member="serviceAccount:etl-runner@b2b-recs.iam.gserviceaccount.com" \
    --role="roles/run.invoker"

# BigQuery permissions (already configured in project IAM)
```

### For Local Development:

Grant your user account the same permissions for testing:
```bash
# Cloud Scheduler admin
gcloud projects add-iam-policy-binding b2b-recs \
    --member="user:kulish.dmytro@gmail.com" \
    --role="roles/cloudscheduler.admin"

# Service account user
gcloud iam service-accounts add-iam-policy-binding \
    etl-runner@b2b-recs.iam.gserviceaccount.com \
    --member="user:kulish.dmytro@gmail.com" \
    --role="roles/iam.serviceAccountUser"
```

### Source Data Access

#### For Database Sources:
- Network access to source database (IP whitelisting if needed)
- Valid database credentials stored in Secret Manager
- Firewall rules allowing outbound connections from Cloud Run

#### For Cloud Storage Sources:
- Service account JSON credentials stored in Secret Manager
- Bucket-level IAM permissions (already handled by service account credentials)

## Error Handling

The ETL runner implements robust error handling:

1. **Retry Logic**: Failed operations retry up to 3 times with exponential backoff
2. **Status Updates**: All failures reported back to Django API
3. **Detailed Logging**: Full error stack traces in Cloud Logging
4. **Graceful Shutdown**: Properly closes database connections on failure

### Common Errors

**ConfigurationError**: Invalid job configuration
- Check required fields in job config
- Verify timestamp_column for transactional loads

**ConnectionError**: Cannot connect to source database
- Verify database credentials
- Check network connectivity
- Verify firewall rules

**LoadError**: BigQuery load failed
- Verify table exists
- Check BigQuery permissions
- Verify schema matches

## Monitoring

### Cloud Logging

All logs are output in JSON format for Cloud Logging:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "severity": "INFO",
  "message": "Batch 5 loaded: 10000 rows",
  "data_source_id": 123,
  "etl_run_id": 456
}
```

### Metrics

Key metrics tracked:
- `rows_extracted`: Total rows extracted from source
- `rows_loaded`: Total rows loaded to BigQuery
- `batches_loaded`: Number of batches processed
- `duration_seconds`: Total execution time

## Development

### Adding a New Database Source

1. Create new extractor in `extractors/`:

```python
from extractors.base import BaseExtractor

class NewDBExtractor(BaseExtractor):
    def extract_full(self, ...):
        # Implementation
        pass

    def extract_incremental(self, ...):
        # Implementation
        pass
```

2. Update `main.py` to instantiate new extractor:

```python
elif source_type == 'newdb':
    return NewDBExtractor(connection_params)
```

3. Add driver to `requirements.txt`

### Testing

```bash
# Run with debug logging
python main.py \
  --data_source_id 123 \
  --log_level DEBUG \
  --json_logs False
```

## Production Checklist

- [ ] Set appropriate memory/CPU for Cloud Run Job (8Gi/4 CPU recommended)
- [ ] Configure service account with minimal required permissions
- [ ] Set up Cloud Scheduler for automated runs
- [ ] Enable Cloud Logging for monitoring
- [ ] Set up alerting for failed ETL runs
- [ ] Test with production data volume
- [ ] Document recovery procedures

## Troubleshooting

### Job times out

- Increase `--timeout` in Cloud Run deployment
- Reduce `ETL_BATCH_SIZE` to lower memory usage
- Check for slow queries in source database

### Out of memory

- Increase `--memory` in Cloud Run deployment
- Reduce `ETL_BATCH_SIZE`
- Use server-side cursors (already implemented)

### BigQuery load fails

- Verify table schema matches source columns
- Check for data type mismatches
- Verify BigQuery quotas not exceeded

## Next Steps

### Immediate (Testing & Validation)

1. **Test End-to-End Data Loading**
   - Click "Run Now" on an existing ETL job
   - Verify Cloud Run job executes successfully
   - Check BigQuery table for loaded data
   - Review Cloud Run logs for errors

2. **Test Cloud Scheduler Integration**
   - Create an ETL job with "Hourly" schedule
   - Verify Cloud Scheduler job is created in GCP Console
   - Wait for scheduled execution or manually trigger
   - Confirm data appears in BigQuery

3. **Validate Progress Tracking**
   - Monitor ETLRun status in Django admin
   - Check if `rows_loaded`, `duration_seconds` are populated
   - Verify error messages appear when jobs fail

### Phase 3: Status Monitoring UI (1-2 weeks)

1. **Real-Time Status Viewer**
   - ETL run status modal with polling
   - Progress bars for extraction/loading phases
   - Live row count updates
   - Link to Cloud Run logs

2. **ETL History Page**
   - View all historical runs for each job
   - Filter by status (completed/failed/running)
   - Metrics: avg duration, success rate, total rows

3. **Dashboard Metrics**
   - Success/failure rate visualization
   - Data volume trends over time
   - Job performance comparison

### Phase 4: Error Handling & Alerts (1 week)

1. **Enhanced Error Handling**
   - Retry logic for transient failures
   - Batch-level error tracking
   - Resume from checkpoint on failure

2. **Alerting System**
   - Email notifications on failures
   - Slack webhook integration
   - Configurable alert rules per job

### Phase 5: Advanced Features (2-3 weeks)

1. **Schema Evolution**
   - Detect new columns in source tables
   - Prompt user to add columns to BigQuery
   - Version schema changes

2. **Data Quality**
   - Row count validation (source vs destination)
   - Null percentage checks
   - Custom quality rules

3. **Multi-Table Jobs**
   - Extract multiple tables in single job
   - Shared schedule for related tables

---

## License

Proprietary - B2B Recommendations Platform
