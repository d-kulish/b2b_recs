# BigQuery Table Setup Implementation

**Last Updated:** 2025-11-18
**Status:** ✅ COMPLETE
**Milestone:** 11.5 - BigQuery Table Schema Management

---

## Overview

This document describes the BigQuery table setup functionality implemented in the ETL wizard. This feature allows users to define and customize BigQuery table schemas before table creation, with intelligent auto-detection and validation.

### What Was Implemented

A complete **5-step ETL wizard** with a new dedicated step for BigQuery table configuration:

```
Step 1: Connection & Job Name
Step 2: Schema & Table Selection
Step 3: Configure Load Strategy
Step 4: BigQuery Table Setup ⭐ NEW
Step 5: Schedule & Review
```

---

## Architecture Overview

### Component Structure

```
Backend (Django)
├── ml_platform/utils/schema_mapper.py       # Type mapping logic
├── ml_platform/utils/bigquery_manager.py    # BigQuery table operations
├── ml_platform/utils/connection_manager.py  # Enhanced with schema mapping
└── ml_platform/views.py                     # api_etl_create_job updated

Frontend (HTML + JavaScript)
└── templates/ml_platform/model_etl.html
    ├── Step 4 HTML (schema editor UI)
    ├── Step 4 JavaScript functions
    └── Updated navigation logic (5 steps)
```

---

## Implementation Details

### 1. Backend: Schema Mapper (`schema_mapper.py`)

**Purpose:** Intelligently maps source database types to BigQuery types.

**Key Features:**
- **Type Mapping Dictionaries:**
  - PostgreSQL → BigQuery (40+ type mappings)
  - MySQL → BigQuery (30+ type mappings)
- **Smart Type Detection:**
  - Detects dates in VARCHAR fields (pattern: `YYYY-MM-DD`)
  - Detects timestamps in VARCHAR fields (pattern: `YYYY-MM-DD HH:MM:SS`)
  - Detects integers/floats stored as strings
  - Detects boolean values (true/false, yes/no, 0/1)
- **Confidence Scoring:**
  - `high`: Direct type mapping found
  - `medium`: Auto-detected from patterns or default to STRING
  - `low`: Needs user review
- **Warning System:**
  - Large TEXT/BLOB fields
  - Type mismatches
  - Missing required columns

**Core Method:**
```python
SchemaMapper.map_column(
    source_type='postgresql',
    column_name='created_at',
    column_type='timestamp without time zone',
    nullable=False,
    sample_values=['2024-01-15 10:30:00', ...]
)
# Returns:
{
    'name': 'created_at',
    'source_type': 'timestamp without time zone',
    'bigquery_type': 'TIMESTAMP',
    'bigquery_mode': 'REQUIRED',
    'confidence': 'high',
    'warning': None,
    'auto_detected': True
}
```

**Special Cases Handled:**
- MySQL `TINYINT(1)` → `BOOL` (not `INT64`)
- PostgreSQL `JSONB` → `JSON`
- Large `TEXT` fields → Warning about performance
- `VARCHAR` with date patterns → Suggest `DATE` or `TIMESTAMP`

---

### 2. Backend: BigQuery Manager (`bigquery_manager.py`)

**Purpose:** Manages BigQuery dataset and table creation with schema validation.

**Key Methods:**

#### `ensure_dataset_exists()`
- Creates `raw_data` dataset if it doesn't exist
- Sets location (default: `US`)
- Idempotent: safe to call multiple times

#### `create_table_from_schema()`
- **Input:**
  - Table name
  - List of column metadata (with `bigquery_type`, `bigquery_mode`)
  - Load type (`transactional` or `catalog`)
  - Timestamp column (for partitioning)
- **Actions:**
  1. Validates table doesn't already exist
  2. Generates BigQuery schema from column metadata
  3. Creates table with description
  4. For transactional loads:
     - Adds **DAY partitioning** on timestamp column
     - Adds **clustering** on timestamp column
  5. Returns full table path and metadata
- **Output:**
  ```python
  {
      'success': True,
      'table_id': 'bq_transactions',
      'full_table_id': 'project-id.raw_data.bq_transactions',
      'num_columns': 15,
      'partitioned': True,
      'message': 'Table bq_transactions created successfully'
  }
  ```

#### `validate_table_schema()`
- Compares existing table schema with expected schema
- Returns list of differences (missing columns, type mismatches)
- Used for schema evolution detection (future feature)

**Performance Optimizations:**
- **Partitioning:** Splits table by day based on timestamp column
  - Reduces query costs (only scans relevant partitions)
  - Improves query speed for date-filtered queries
- **Clustering:** Orders data within partitions by timestamp
  - Further reduces data scanned
  - Best for range queries

---

### 3. Backend: Connection Manager Enhancement

**What Changed:**

The `fetch_table_metadata()` function now:
1. Calls source-specific metadata fetchers (PostgreSQL/MySQL/BigQuery)
2. **Maps each column** using `SchemaMapper.map_column()`
3. Returns enhanced column metadata with BigQuery type info

**Before:**
```python
{
    'name': 'customer_id',
    'type': 'integer',
    'nullable': False,
    'is_primary_key': True,
    'sample_values': [1, 2, 3]
}
```

**After:**
```python
{
    'name': 'customer_id',
    'type': 'integer',
    'nullable': False,
    'is_primary_key': True,
    'sample_values': [1, 2, 3],
    'bigquery_type': 'INT64',          # NEW
    'bigquery_mode': 'REQUIRED',       # NEW
    'confidence': 'high',              # NEW
    'warning': None,                   # NEW
    'auto_detected': True              # NEW
}
```

---

### 4. Backend: ETL Job Creation Flow

**Updated `api_etl_create_job()` in `views.py`:**

```python
# NEW FLOW:
1. Extract payload data (including bigquery_table_name, bigquery_schema)
2. Validate all required fields
3. Get GCP project ID from settings
4. CREATE BIGQUERY DATASET (if needed)
5. CREATE BIGQUERY TABLE WITH SCHEMA
   - If table exists → Return error
   - If creation fails → Rollback and return error
6. Create Django DataSource record
7. Create Django DataSourceTable record(s)
   - Use BigQuery table name as dest_table_name
8. (Optional) Create Cloud Scheduler job
9. Return success with BigQuery table path
```

**Key Validations:**
- BigQuery table name is required
- BigQuery schema must have ≥1 column
- Table name must match regex: `^[a-zA-Z_][a-zA-Z0-9_]*$`
- Check for duplicate job names
- Verify connection exists

**Error Handling:**
- Dataset creation failure → Return 500 error
- Table creation failure → Return 500 error (no partial state)
- Table already exists → Clear error message to user

---

### 5. Frontend: Step 4 HTML Structure

**Location:** `templates/ml_platform/model_etl.html` (lines 390-525)

**UI Components:**

1. **Table Name Input**
   - Default: `bq_{source_table_name}`
   - Editable by user
   - Live preview of full path: `PROJECT.raw_data.{table_name}`

2. **Schema Editor Table**
   - **Columns:**
     - Column Name (with icons: 🔑 for PK, 🕐 for timestamps)
     - Source Type (readonly, from source DB)
     - **BigQuery Type** (editable dropdown with 13 types)
     - **Mode** (editable: NULLABLE/REQUIRED)
     - Sample Values (first 2 values shown)
   - **Interactive:**
     - User can change BigQuery type via dropdown
     - User can change mode (NULLABLE/REQUIRED)
     - Changes marked as user overrides
     - Reset button to revert to auto-detected defaults

3. **Performance Optimization Panel** (transactional loads only)
   - Shows partitioning configuration: `By {timestamp_column} (DAY)`
   - Shows clustering configuration: `By {timestamp_column}`
   - Explains benefits: "Improves query performance for date-based filtering"

4. **Schema Warnings Panel** (conditional)
   - Large TEXT fields warning
   - Type manually changed warnings
   - Missing timestamp column warning

5. **Summary Panel**
   - Full table path
   - Column count
   - Load type

**Visual Design:**
- Confidence indicators: 🟢 high, 🟡 medium, 🔴 low
- Warning icons: ⚠️ for issues
- Color coding: green=good, yellow=caution, red=review needed

---

### 6. Frontend: JavaScript Functions

**Location:** `templates/ml_platform/model_etl.html` (lines 4861-5072)

#### Key Functions:

**`proceedToStep4()`**
- Validates Step 3 (load strategy) is complete
- Generates default BigQuery table name: `bq_{source_table}`
- Calls `renderBigQuerySchemaEditor()`
- Shows/hides optimization settings based on load type
- Transitions to Step 4

**`renderBigQuerySchemaEditor()`**
- Filters columns to only selected columns from Step 3
- Stores schema in `window.bqSchemaColumns` (deep copy)
- Generates HTML table rows with:
  - Type dropdowns (13 BigQuery types)
  - Mode dropdowns (NULLABLE/REQUIRED)
  - Warning indicators
- Calls `updateSchemaWarnings()`

**`getBigQueryTypeOptions(selectedType)`**
- Returns HTML `<option>` elements for all BigQuery types
- Pre-selects the auto-detected type

**`onBqTypeChange(columnIndex, newType)`**
- Updates `window.bqSchemaColumns[columnIndex].bigquery_type`
- Marks column as `auto_detected = false` (user override)
- Triggers `updateSchemaWarnings()`

**`onBqModeChange(columnIndex, newMode)`**
- Updates `window.bqSchemaColumns[columnIndex].bigquery_mode`
- Triggers `updateSchemaWarnings()`

**`resetSchemaToDefaults()`**
- Confirms with user
- Re-renders schema from original auto-detected metadata
- Clears all user overrides

**`updateSchemaWarnings()`**
- Checks for:
  - Large STRING fields from TEXT source types
  - User-modified types (overrides)
  - Missing timestamp column for transactional loads
- Shows/hides warning panel based on issues found

---

### 7. Frontend: Navigation Logic Updates

**`updateProgress(step)` - Updated for 5 steps:**
```javascript
for (let i = 1; i <= 5; i++) {  // Changed from 4 to 5
    // Update progress bar
}
```

**`showStep(step)` - Added Step 4 handling:**
```javascript
// Step 4: BigQuery Table Setup (NEW)
else if (step === 4) {
    if (backButton) backButton.disabled = false;
    if (nextButton) {
        nextButton.disabled = false;
        nextButton.classList.remove('hidden');
        nextButton.innerHTML = '<i class="fas fa-chevron-right"></i>';
    }
    if (createButton) createButton.classList.add('hidden');
}

// Step 5: Schedule & Review (formerly Step 4)
else if (step === 5) {
    if (backButton) backButton.disabled = false;
    if (nextButton) nextButton.classList.add('hidden');
    if (createButton) {
        createButton.classList.remove('hidden');
        createButton.onclick = createETLJob;
        // ...
    }
}
```

**`nextStep()` - Added Step 3→4 and Step 4→5:**
```javascript
// STEP 3 -> STEP 4: Validate and proceed to BigQuery setup
if (currentWizardStep === 3) {
    // Validate load configuration
    // Call proceedToStep4()
}

// STEP 4 -> STEP 5: Validate BigQuery table configuration
if (currentWizardStep === 4) {
    const bqTableName = document.getElementById('bqTableName').value.trim();

    // Validate table name not empty
    // Validate table name format: ^[a-zA-Z_][a-zA-Z0-9_]*$
    // Validate schema has columns

    // Store BigQuery table name
    window.bqDestTableName = bqTableName;

    // Proceed to Step 5
    currentWizardStep = 5;
    showStep(5);
    updateSummary();
}
```

---

### 8. Frontend: Updated Payload

**`createETLJob()` - Enhanced payload:**
```javascript
const payload = {
    name: jobName,
    connection_id: window.selectedConnectionId,
    schema_name: window.selectedSchema,

    // Step 3: Load strategy
    load_type: loadType,
    timestamp_column: timestampColumn,
    historical_start_date: historicalStartDate,
    selected_columns: selectedColumns,

    // Step 4: BigQuery table setup (NEW)
    bigquery_table_name: bqTableName,
    bigquery_schema: bqSchemaColumns,  // Full array with types/modes

    // Step 5: Schedule
    schedule_type: scheduleType,

    tables: [
        {
            source_table_name: window.selectedTableName,
            dest_table_name: bqTableName,  // Use custom BQ name
            sync_mode: loadType === 'transactional' ? 'incremental' : 'replace',
            incremental_column: timestampColumn
        }
    ]
};
```

**Success Response Enhanced:**
```javascript
if (data.status === 'success') {
    alert(`ETL job "${data.job_name}" created successfully!

BigQuery table: ${data.bigquery_table}
Schedule: ${data.schedule_created ? 'Created' : 'Manual only'}`);
    // ...
}
```

---

## User Flow

### Complete Wizard Flow

```
USER STARTS WIZARD
│
├─ Step 1: Connection & Job Name
│  User selects existing connection or creates new one
│  User enters job name
│  Click "Next" →
│
├─ Step 2: Schema & Table Selection
│  User selects schema from dropdown (auto-loaded from connection)
│  User selects table from dropdown (auto-loaded from schema)
│  Click "Next" →
│
├─ Step 3: Configure Load Strategy
│  User sees table preview with columns
│  User selects load type: Transactional or Catalog
│
│  IF Transactional:
│  ├─ User selects timestamp column (auto-suggested)
│  ├─ User selects historical backfill range (All/30/60/90 days/Custom)
│  └─ User selects columns to sync (with Select All/Deselect All)
│
│  IF Catalog:
│  └─ User sees "Full snapshot" message
│
│  Click "Next" →
│
├─ Step 4: BigQuery Table Setup ⭐ NEW
│  │
│  ├─ AUTO-POPULATED:
│  │  • Table name: bq_{source_table_name}
│  │  • Schema editor shows all selected columns
│  │  • Each column has auto-detected BigQuery type
│  │  • Confidence indicators shown (🟢🟡🔴)
│  │  • Warnings shown for issues
│  │
│  ├─ USER CAN:
│  │  • Edit table name (must be valid: ^[a-zA-Z_][a-zA-Z0-9_]*$)
│  │  • Change BigQuery type for any column (dropdown)
│  │  • Change mode (NULLABLE/REQUIRED) for any column
│  │  • Reset to defaults if they made mistakes
│  │
│  ├─ USER SEES:
│  │  • Full table path preview: PROJECT.raw_data.{table_name}
│  │  • Performance optimization info (if transactional)
│  │  • Warnings about schema issues
│  │  • Summary: column count, load type
│  │
│  └─ Click "Next" →
│     (Validation: table name valid, schema not empty)
│
├─ Step 5: Schedule & Review
│  User selects schedule type: Manual/Hourly/Daily/Weekly/Monthly
│  User reviews summary of all settings
│  Click "Create ETL Job" →
│
└─ BACKEND PROCESSING:
   ├─ Validate all inputs
   ├─ Create BigQuery dataset (if needed)
   ├─ Create BigQuery table with schema
   │  (IF FAILS → Return error, no partial state)
   ├─ Create Django DataSource record
   ├─ Create Django DataSourceTable record
   ├─ (Optional) Create Cloud Scheduler job
   └─ Return success with BigQuery table path

   SUCCESS MESSAGE:
   "ETL job 'Job Name' created successfully!
    BigQuery table: project-id.raw_data.bq_transactions
    Schedule: Created / Manual only"
```

---

## Schema Immutability Policy

**Critical Decision:** BigQuery table schemas **cannot be changed** after creation.

### Why This Design?

1. **BigQuery Limitation:** Schema changes are complex and risky
2. **Data Integrity:** Prevents accidental data loss or corruption
3. **ETL Consistency:** Historical data must match current schema
4. **User Clarity:** Clear expectation upfront

### What Users Should Do If They Need Schema Changes

**Option 1: Create New ETL Job**
- Create new job with different table name (e.g., `bq_transactions_v2`)
- Configure desired schema
- Run ETL job
- Switch applications to use new table
- Archive or delete old table

**Option 2: Create New Columns (Future Feature)**
- Add new nullable columns to existing table
- Requires schema evolution logic (not yet implemented)

**Option 3: Full Recreate**
- Delete ETL job (marks table for cleanup)
- Delete BigQuery table manually
- Create new ETL job with same table name
- Lose historical data

---

## Testing & Validation

### Manual Testing Checklist

#### Step 4 UI Testing
- [ ] Table name defaults to `bq_{source_table}`
- [ ] Table name is editable
- [ ] Table name preview updates in real-time
- [ ] Schema editor shows all selected columns from Step 3
- [ ] Source types display correctly
- [ ] BigQuery types show with correct defaults
- [ ] Mode (NULLABLE/REQUIRED) matches source nullability
- [ ] Dropdowns are functional (type/mode selection)
- [ ] Changing type marks as user override
- [ ] Reset to Defaults button works
- [ ] Warnings appear for TEXT fields
- [ ] Warnings appear for user overrides
- [ ] Optimization panel shows for transactional loads
- [ ] Optimization panel hidden for catalog loads
- [ ] Summary shows correct column count
- [ ] Summary shows correct load type

#### Backend Testing
- [ ] Dataset creation works (first time)
- [ ] Dataset creation is idempotent (subsequent calls)
- [ ] Table creation succeeds with valid schema
- [ ] Table creation fails if table exists (with clear error)
- [ ] Table creation fails if name is invalid (with clear error)
- [ ] Partitioning applied for transactional loads
- [ ] Clustering applied for transactional loads
- [ ] No partitioning for catalog loads
- [ ] DataSource record created with correct fields
- [ ] DataSourceTable record uses BigQuery table name

#### Integration Testing
- [ ] Complete wizard flow (5 steps)
- [ ] Verify BigQuery table created in correct dataset
- [ ] Verify table schema matches what was configured
- [ ] Verify partitioning (if transactional)
- [ ] Verify clustering (if transactional)
- [ ] Verify table description includes source info

### SQL Validation Queries

```sql
-- Check if table exists
SELECT * FROM `PROJECT.raw_data.INFORMATION_SCHEMA.TABLES`
WHERE table_name = 'bq_transactions';

-- Check table schema
SELECT column_name, data_type, is_nullable
FROM `PROJECT.raw_data.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'bq_transactions'
ORDER BY ordinal_position;

-- Check partitioning
SELECT * FROM `PROJECT.raw_data.INFORMATION_SCHEMA.PARTITIONS`
WHERE table_name = 'bq_transactions';

-- Check clustering
SELECT clustering_ordinal_position, column_name
FROM `PROJECT.raw_data.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'bq_transactions'
AND clustering_ordinal_position IS NOT NULL;
```

---

## Configuration Requirements

### Django Settings

```python
# settings.py or .env
GCP_PROJECT_ID = 'your-gcp-project-id'
```

### GCP Permissions Required

The service account used by Django must have:
- `bigquery.datasets.create` (to create `raw_data` dataset)
- `bigquery.tables.create` (to create tables)
- `bigquery.tables.get` (to check if table exists)
- `bigquery.tables.list` (to list tables in dataset)

**Recommended Role:** `BigQuery Data Editor` or custom role with above permissions.

---

## Next Steps: ETL Runner & Scheduler Implementation

Now that BigQuery tables are created upfront, we need to implement the actual ETL execution.

### Phase 1: Simple Cloud Run ETL Runner (Week 1-2)

**Goal:** Build a lightweight ETL runner for small-to-medium datasets (< 1M rows).

#### Architecture
```
Cloud Scheduler → Cloud Run Job → PostgreSQL/MySQL
                       ↓
                   BigQuery (table already exists)
```

#### Implementation Tasks

1. **Create ETL Runner Directory Structure**
   ```
   etl_runner/
   ├── Dockerfile
   ├── requirements.txt
   ├── main.py                 # Entry point
   ├── config.py              # Configuration management
   ├── extractors/
   │   ├── __init__.py
   │   ├── base.py            # BaseExtractor abstract class
   │   ├── postgresql.py      # PostgreSQLExtractor
   │   ├── mysql.py           # MySQLExtractor
   │   └── bigquery.py        # BigQueryExtractor (future)
   ├── loaders/
   │   ├── __init__.py
   │   └── bigquery_loader.py # BigQueryLoader
   └── utils/
       ├── __init__.py
       ├── logging_config.py
       └── error_handling.py
   ```

2. **Build BaseExtractor Class**
   ```python
   class BaseExtractor:
       """Abstract base class for data extractors"""

       def extract_full(self, table_name, schema_name, selected_columns):
           """Extract all data from table"""
           raise NotImplementedError

       def extract_incremental(self, table_name, schema_name,
                              timestamp_column, since_date, selected_columns):
           """Extract data since last sync"""
           raise NotImplementedError

       def get_row_count(self, table_name, schema_name):
           """Get total row count"""
           raise NotImplementedError
   ```

3. **Implement PostgreSQLExtractor**
   ```python
   class PostgreSQLExtractor(BaseExtractor):
       def __init__(self, connection_params):
           self.host = connection_params['host']
           self.port = connection_params['port']
           self.database = connection_params['database']
           self.username = connection_params['username']
           self.password = connection_params['password']

       def extract_incremental(self, table_name, schema_name,
                              timestamp_column, since_date, selected_columns):
           """
           Extract data incrementally using timestamp column.

           Args:
               table_name: Source table name
               schema_name: Schema name
               timestamp_column: Column for filtering (e.g., 'created_at')
               since_date: Start date (e.g., '2024-01-01')
               selected_columns: List of columns to extract

           Returns:
               Generator yielding batches of rows (pandas DataFrame)
           """
           import psycopg2
           import pandas as pd

           conn = psycopg2.connect(...)

           # Build query
           cols = ', '.join(f'"{col}"' for col in selected_columns)
           query = f"""
               SELECT {cols}
               FROM "{schema_name}"."{table_name}"
               WHERE "{timestamp_column}" >= %s
               ORDER BY "{timestamp_column}"
           """

           # Use server-side cursor for memory efficiency
           with conn.cursor(name='etl_cursor') as cursor:
               cursor.itersize = 10000  # Fetch 10K rows at a time
               cursor.execute(query, (since_date,))

               while True:
                   rows = cursor.fetchmany(10000)
                   if not rows:
                       break

                   df = pd.DataFrame(rows, columns=selected_columns)
                   yield df
   ```

4. **Implement BigQueryLoader**
   ```python
   class BigQueryLoader:
       def __init__(self, project_id, dataset_id, table_name):
           from google.cloud import bigquery
           self.client = bigquery.Client(project=project_id)
           self.table_ref = f"{project_id}.{dataset_id}.{table_name}"

       def load(self, df, mode='WRITE_APPEND'):
           """
           Load DataFrame to BigQuery.

           Args:
               df: pandas DataFrame
               mode: WRITE_APPEND or WRITE_TRUNCATE
           """
           from google.cloud import bigquery

           job_config = bigquery.LoadJobConfig(
               write_disposition=mode,
               create_disposition='CREATE_NEVER'  # Table must exist
           )

           job = self.client.load_table_from_dataframe(
               df, self.table_ref, job_config=job_config
           )

           job.result()  # Wait for completion

           return {
               'rows_loaded': len(df),
               'errors': job.errors
           }
   ```

5. **Create Main Entry Point (main.py)**
   ```python
   import argparse
   import json
   import logging
   from extractors.postgresql import PostgreSQLExtractor
   from extractors.mysql import MySQLExtractor
   from loaders.bigquery_loader import BigQueryLoader

   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument('--data_source_id', required=True, type=int)
       parser.add_argument('--etl_run_id', type=int)
       args = parser.parse_args()

       # Fetch job config from Django API
       job_config = fetch_job_config(args.data_source_id)

       # Initialize extractor
       if job_config['source_type'] == 'postgresql':
           extractor = PostgreSQLExtractor(job_config['connection_params'])
       elif job_config['source_type'] == 'mysql':
           extractor = MySQLExtractor(job_config['connection_params'])

       # Initialize loader
       loader = BigQueryLoader(
           project_id=job_config['project_id'],
           dataset_id='raw_data',
           table_name=job_config['dest_table_name']
       )

       # Execute ETL based on load type
       if job_config['load_type'] == 'transactional':
           # Incremental load
           for batch_df in extractor.extract_incremental(
               table_name=job_config['source_table_name'],
               schema_name=job_config['schema_name'],
               timestamp_column=job_config['timestamp_column'],
               since_date=job_config['last_sync_value'] or job_config['historical_start_date'],
               selected_columns=job_config['selected_columns']
           ):
               result = loader.load(batch_df, mode='WRITE_APPEND')
               logging.info(f"Loaded {result['rows_loaded']} rows")

       else:  # catalog
           # Full replace
           first_batch = True
           for batch_df in extractor.extract_full(
               table_name=job_config['source_table_name'],
               schema_name=job_config['schema_name'],
               selected_columns=job_config['selected_columns']
           ):
               mode = 'WRITE_TRUNCATE' if first_batch else 'WRITE_APPEND'
               result = loader.load(batch_df, mode=mode)
               first_batch = False
               logging.info(f"Loaded {result['rows_loaded']} rows")

       # Update ETL run status in Django
       update_etl_run_status(args.etl_run_id, 'completed', total_rows=...)

   def fetch_job_config(data_source_id):
       """Fetch job config from Django API"""
       import requests
       response = requests.get(
           f'https://your-django-app.run.app/api/etl/job-config/{data_source_id}/',
           headers={'Authorization': 'Bearer ...'}
       )
       return response.json()

   def update_etl_run_status(etl_run_id, status, total_rows):
       """Update ETL run status in Django"""
       import requests
       requests.post(
           f'https://your-django-app.run.app/api/etl/runs/{etl_run_id}/update/',
           json={'status': status, 'total_rows': total_rows},
           headers={'Authorization': 'Bearer ...'}
       )

   if __name__ == '__main__':
       main()
   ```

6. **Create Dockerfile**
   ```dockerfile
   FROM python:3.10-slim

   WORKDIR /app

   # Install dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Copy application code
   COPY . .

   # Run as non-root user
   RUN useradd -m -u 1000 etl && chown -R etl:etl /app
   USER etl

   ENTRYPOINT ["python", "main.py"]
   ```

7. **Create requirements.txt**
   ```
   google-cloud-bigquery==3.14.0
   pandas==2.1.4
   psycopg2-binary==2.9.9
   pymysql==1.1.0
   requests==2.31.0
   ```

8. **Deploy to Cloud Run**
   ```bash
   # Build and push image
   gcloud builds submit --tag gcr.io/PROJECT_ID/etl-runner

   # Deploy to Cloud Run
   gcloud run deploy etl-runner \
       --image gcr.io/PROJECT_ID/etl-runner \
       --platform managed \
       --region us-central1 \
       --memory 8Gi \
       --timeout 3600 \
       --no-allow-unauthenticated \
       --max-instances 10 \
       --service-account etl-runner@PROJECT_ID.iam.gserviceaccount.com
   ```

---

### Phase 2: Cloud Scheduler Integration (Week 2)

**Goal:** Automatically trigger ETL jobs on schedule.

#### Implementation Tasks

1. **Create Cloud Scheduler Helper in Django**

   Create `ml_platform/utils/cloud_scheduler.py`:
   ```python
   from google.cloud import scheduler_v2
   import json

   def create_etl_schedule(project_id, region, data_source):
       """
       Create Cloud Scheduler job for ETL automation.

       Args:
           project_id: GCP project ID
           region: Region (e.g., 'us-central1')
           data_source: DataSource model instance
       """
       client = scheduler_v2.CloudSchedulerClient()

       parent = f"projects/{project_id}/locations/{region}"
       job_name = f"{parent}/jobs/etl-job-{data_source.id}"

       # Get cron schedule
       schedule = get_cron_expression(data_source.schedule_type)

       # Get Cloud Run ETL runner URL
       etl_runner_url = f"https://etl-runner-{project_id}.run.app/execute"

       # Create job configuration
       job = {
           'name': job_name,
           'description': f'ETL schedule for {data_source.name}',
           'schedule': schedule,
           'time_zone': 'UTC',
           'http_target': {
               'uri': etl_runner_url,
               'http_method': scheduler_v2.HttpMethod.POST,
               'headers': {'Content-Type': 'application/json'},
               'body': json.dumps({
                   'data_source_id': data_source.id,
                   'trigger': 'scheduled'
               }).encode('utf-8'),
               'oidc_token': {
                   'service_account_email': f'etl-runner@{project_id}.iam.gserviceaccount.com'
               }
           }
       }

       created_job = client.create_job(request={'parent': parent, 'job': job})

       return {
           'success': True,
           'job_name': created_job.name,
           'schedule': schedule
       }

   def get_cron_expression(schedule_type):
       """Convert schedule_type to cron expression"""
       cron_map = {
           'hourly': '0 * * * *',        # Every hour at minute 0
           'daily': '0 2 * * *',         # Daily at 2:00 AM UTC
           'weekly': '0 2 * * 0',        # Weekly on Sunday at 2:00 AM
           'monthly': '0 2 1 * *',       # Monthly on 1st at 2:00 AM
       }
       return cron_map.get(schedule_type, '0 2 * * *')

   def delete_etl_schedule(project_id, region, data_source_id):
       """Delete Cloud Scheduler job"""
       client = scheduler_v2.CloudSchedulerClient()
       job_name = f"projects/{project_id}/locations/{region}/jobs/etl-job-{data_source_id}"

       try:
           client.delete_job(request={'name': job_name})
           return {'success': True}
       except Exception as e:
           return {'success': False, 'message': str(e)}
   ```

2. **Update `api_etl_create_job()` to Create Scheduler**

   In `ml_platform/views.py`, after creating DataSourceTable:
   ```python
   # Create Cloud Scheduler job (if scheduled)
   if schedule_type != 'manual':
       from .utils.cloud_scheduler import create_etl_schedule

       scheduler_result = create_etl_schedule(
           project_id=project_id,
           region='us-central1',
           data_source=data_source
       )

       if scheduler_result['success']:
           logger.info(f"Created Cloud Scheduler job: {scheduler_result['job_name']}")
           schedule_created = True
       else:
           logger.warning(f"Failed to create scheduler: {scheduler_result.get('message')}")
           schedule_created = False

   return JsonResponse({
       'status': 'success',
       'message': f'ETL job "{job_name}" created successfully',
       'job_id': data_source.id,
       'job_name': data_source.name,
       'bigquery_table': table_result['full_table_id'],
       'schedule_created': schedule_created,  # NEW
   })
   ```

3. **Add Manual "Run Now" Functionality**

   Create endpoint `api_etl_trigger_now(request, data_source_id)`:
   ```python
   @login_required
   @require_http_methods(["POST"])
   def api_etl_trigger_now(request, data_source_id):
       """Manually trigger ETL run for a data source"""
       from google.cloud import run_v2

       data_source = get_object_or_404(DataSource, id=data_source_id)

       # Create ETL run record
       etl_run = ETLRun.objects.create(
           etl_config=data_source.etl_config,
           model_endpoint=data_source.etl_config.model_endpoint,
           status='pending',
           triggered_by=request.user,
           started_at=timezone.now(),
       )

       # Trigger Cloud Run job
       client = run_v2.JobsClient()
       job_name = f'projects/{project_id}/locations/{region}/jobs/etl-runner'

       request = run_v2.RunJobRequest(
           name=job_name,
           overrides={
               'container_overrides': [{
                   'args': [
                       '--data_source_id', str(data_source_id),
                       '--etl_run_id', str(etl_run.id)
                   ]
               }]
           }
       )

       operation = client.run_job(request=request)

       return JsonResponse({
           'status': 'success',
           'message': f'ETL run triggered for "{data_source.name}"',
           'run_id': etl_run.id,
           'execution_name': operation.name
       })
   ```

---

### Phase 3: Status Tracking & Monitoring (Week 3)

**Goal:** Real-time visibility into ETL execution status.

#### Implementation Tasks

1. **Enhance ETLRun Model**
   ```python
   class ETLRun(models.Model):
       # Existing fields...

       # Enhanced tracking fields
       execution_id = models.CharField(max_length=255, blank=True)  # Cloud Run execution ID
       cloud_run_logs_url = models.URLField(blank=True)

       # Detailed progress
       extraction_started_at = models.DateTimeField(null=True, blank=True)
       extraction_completed_at = models.DateTimeField(null=True, blank=True)
       loading_started_at = models.DateTimeField(null=True, blank=True)
       loading_completed_at = models.DateTimeField(null=True, blank=True)

       # Performance metrics
       rows_extracted = models.BigIntegerField(default=0)
       rows_loaded = models.BigIntegerField(default=0)
       bytes_processed = models.BigIntegerField(default=0)
       duration_seconds = models.IntegerField(null=True, blank=True)
   ```

2. **Add Status Polling Endpoint**
   ```python
   @login_required
   def api_etl_run_status(request, run_id):
       """Get real-time ETL run status"""
       etl_run = get_object_or_404(ETLRun, id=run_id)

       return JsonResponse({
           'status': etl_run.status,
           'started_at': etl_run.started_at.isoformat() if etl_run.started_at else None,
           'completed_at': etl_run.completed_at.isoformat() if etl_run.completed_at else None,
           'rows_extracted': etl_run.rows_extracted,
           'rows_loaded': etl_run.rows_loaded,
           'duration_seconds': etl_run.duration_seconds,
           'error_message': etl_run.error_message,
           'logs_url': etl_run.cloud_run_logs_url
       })
   ```

3. **Add Real-Time Status Updates to ETL Runner**

   In `etl_runner/main.py`:
   ```python
   def update_etl_run_progress(etl_run_id, phase, rows_processed):
       """Update ETL run progress in real-time"""
       update_data = {
           'rows_extracted': rows_processed if phase == 'extraction' else None,
           'rows_loaded': rows_processed if phase == 'loading' else None,
       }

       requests.patch(
           f'{DJANGO_API_URL}/api/etl/runs/{etl_run_id}/update/',
           json=update_data,
           headers={'Authorization': f'Bearer {API_TOKEN}'}
       )

   # Call during ETL execution
   for batch_df in extractor.extract_incremental(...):
       total_extracted += len(batch_df)
       update_etl_run_progress(etl_run_id, 'extraction', total_extracted)

       result = loader.load(batch_df)
       total_loaded += result['rows_loaded']
       update_etl_run_progress(etl_run_id, 'loading', total_loaded)
   ```

4. **Add Frontend Status Viewer**

   In `model_etl.html`, add status modal:
   ```html
   <!-- ETL Run Status Modal -->
   <div id="etlStatusModal" class="hidden">
       <div class="bg-white rounded-lg p-6">
           <h3>ETL Run Status</h3>

           <div id="etlStatusContent">
               <div class="status-item">
                   <span class="label">Status:</span>
                   <span id="runStatus" class="status-badge">Running</span>
               </div>

               <div class="progress-bar">
                   <div id="extractionProgress" class="progress"></div>
               </div>

               <div class="metrics">
                   <div>Rows Extracted: <span id="rowsExtracted">0</span></div>
                   <div>Rows Loaded: <span id="rowsLoaded">0</span></div>
                   <div>Duration: <span id="duration">0s</span></div>
               </div>

               <a id="logsLink" href="#" target="_blank">View Cloud Logs</a>
           </div>
       </div>
   </div>
   ```

   Add JavaScript polling:
   ```javascript
   function pollETLRunStatus(runId) {
       const pollInterval = setInterval(async () => {
           const response = await fetch(`/api/etl/runs/${runId}/status/`);
           const data = await response.json();

           // Update UI
           document.getElementById('runStatus').textContent = data.status;
           document.getElementById('rowsExtracted').textContent = data.rows_extracted.toLocaleString();
           document.getElementById('rowsLoaded').textContent = data.rows_loaded.toLocaleString();
           document.getElementById('duration').textContent = data.duration_seconds + 's';

           // Stop polling if completed/failed
           if (['completed', 'failed'].includes(data.status)) {
               clearInterval(pollInterval);
           }
       }, 2000);  // Poll every 2 seconds
   }
   ```

---

## Known Limitations

1. **Schema Immutability:** Cannot change schema after table creation
2. **No Schema Evolution:** Cannot automatically add new columns from source
3. **Single Table Per Job:** Each job creates one BigQuery table
4. **No Custom Transformations:** Data is loaded as-is from source
5. **Limited BigQuery Types:** Supports 13 common types, not all BigQuery types

---

## Future Enhancements

### Short Term (Milestone 12)
- [ ] Add validation for compatible type changes (e.g., INT64 → FLOAT64)
- [ ] Show estimated BigQuery storage cost based on schema
- [ ] Add "Preview Schema" feature before Step 5
- [ ] Support for ARRAY and STRUCT types

### Medium Term (Milestone 13)
- [ ] Schema evolution: detect new columns and prompt user
- [ ] Multiple tables per job (bulk configuration)
- [ ] Custom type casting rules (e.g., VARCHAR → DATE with format)
- [ ] Schema versioning and history

### Long Term (Milestone 14+)
- [ ] Visual schema designer (drag-and-drop)
- [ ] Schema templates (common patterns)
- [ ] Automatic schema optimization suggestions
- [ ] Integration with dbt for transformations

---

## Troubleshooting

### Common Issues

**Issue:** "GCP_PROJECT_ID not configured in settings"
- **Solution:** Add `GCP_PROJECT_ID` to `settings.py` or `.env` file

**Issue:** "Failed to create BigQuery table: Table already exists"
- **Solution:** Either:
  1. Delete the existing table manually in BigQuery
  2. Choose a different table name in Step 4
  3. Delete the existing ETL job first

**Issue:** "Permission denied: bigquery.tables.create"
- **Solution:** Grant `BigQuery Data Editor` role to service account

**Issue:** "Invalid table name format"
- **Solution:** Table name must:
  - Start with letter or underscore
  - Contain only letters, numbers, underscores
  - Example: `bq_transactions` ✅, `transactions-2024` ❌

**Issue:** Schema editor shows wrong types
- **Solution:** User can manually override types in Step 4 dropdowns

---

## Files Modified/Created

### Created Files
- `ml_platform/utils/schema_mapper.py` (368 lines)
- `ml_platform/utils/bigquery_manager.py` (219 lines)
- `BQ_TABLE_SETUP.md` (this file)

### Modified Files
- `ml_platform/utils/connection_manager.py` (enhanced `fetch_table_metadata()`)
- `ml_platform/views.py` (enhanced `api_etl_create_job()`)
- `templates/ml_platform/model_etl.html` (added Step 4, 300+ lines added)

### Total Lines of Code Added: ~1,100 lines

---

## References

- [BigQuery Table Schema Documentation](https://cloud.google.com/bigquery/docs/schemas)
- [BigQuery Partitioning](https://cloud.google.com/bigquery/docs/partitioned-tables)
- [BigQuery Clustering](https://cloud.google.com/bigquery/docs/clustered-tables)
- [BigQuery Standard SQL Data Types](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-types)

---

**Document Version:** 1.0
**Author:** Claude Code
**Date:** 2025-11-18
