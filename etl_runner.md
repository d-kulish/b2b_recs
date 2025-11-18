# ETL Runner

**Last Updated:** November 18, 2025
**Status:** Phase 1 & Phase 2 COMPLETE ✅ | Ready for Data Loading

Cloud Run-based ETL execution engine for the B2B Recommendations Platform. Extracts data from source databases (PostgreSQL, MySQL) and loads to BigQuery.

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

**What's Missing:**
- ⚠️ Cloud Scheduler not yet creating jobs (need to test)
- ⚠️ Actual data loading not tested end-to-end
- ⚠️ Real-time status monitoring UI (Phase 3)

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

- **Multiple Source Types**: PostgreSQL, MySQL support
- **Two Load Modes**:
  - **Catalog**: Full snapshot (WRITE_TRUNCATE then WRITE_APPEND)
  - **Transactional**: Incremental (WRITE_APPEND only)
- **Memory Efficient**: Streams data in batches (default: 10K rows)
- **Progress Tracking**: Real-time status updates to Django
- **Error Handling**: Retry logic with exponential backoff
- **Cloud Logging**: JSON-formatted logs for Cloud Logging integration

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

## Permissions

The Cloud Run service account needs the following permissions:

### BigQuery
- `bigquery.tables.get` - Check if table exists
- `bigquery.tables.getData` - Read table metadata
- `bigquery.tables.updateData` - Load data to table

### Source Databases
- Network access to source database
- Valid database credentials (provided via Django API)

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
