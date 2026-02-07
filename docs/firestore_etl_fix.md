# Fix: Firestore ETL Job `memo2_firestore_memos_v2` — Deleted BQ Table Recovery

**Date:** 2026-02-06
**ETL Job:** `memo2_firestore_memos_v2` (DataSource ID: 14)
**Connection:** `memo2_firestore` (Connection ID: 3)
**Destination Table:** `b2b-recs.raw_data.bq_memos`

---

## Problem

The ETL job `memo2_firestore_memos_v2` stopped working after a BigQuery regional migration. The project's BigQuery was originally built in the **US** region. It was then rebuilt in the project region **europe-central2**, and during that migration the destination table `bq_memos` was deleted.

The ETL runner validates that the destination table exists before loading data (`etl_runner/main.py:1296-1302`):

```python
if not self.loader.verify_table_exists():
    raise ConfigurationError(
        f"Destination table does not exist: {self.loader.table_ref}. "
        f"Please create the table first using the ETL wizard."
    )
```

Additionally, the BigQuery loader uses `create_disposition='CREATE_NEVER'` (`etl_runner/loaders/bigquery_loader.py:149`), meaning it never auto-creates tables. The table must pre-exist.

With `bq_memos` deleted, the job fails at the VALIDATE phase.

---

## Analysis

### ETL Job Configuration (from Django DB)

| Field | Value |
|-------|-------|
| DataSource ID | 14 |
| DataSource name | `memo2_firestore_memos_v2` |
| Connection | `memo2_firestore` (ID: 3, type: `firestore`) |
| Firestore project | `memo2-456215` |
| Source collection | `memos` |
| Destination table | `bq_memos` (in `raw_data` dataset) |
| Load type | `transactional` |
| Timestamp column | `created_at` |
| Credentials | Secret Manager: `model-5-connection-3-credentials` |

### Schema Storage Gap

The ETL wizard infers the BigQuery schema (column names + types) from Firestore during job creation, but only persists **column names** in `DataSourceTable.selected_columns` (a list of strings). The full schema with types (`bq_schema_columns`) is used transiently during wizard execution and never saved to the database.

This means the table cannot be recreated from stored config alone — the schema must be re-inferred from the live Firestore data.

### Key Code Paths

| Component | File | Purpose |
|-----------|------|---------|
| Table existence check | `etl_runner/main.py:1296-1302` | Fails if destination table missing |
| Loader create disposition | `etl_runner/loaders/bigquery_loader.py:149` | `CREATE_NEVER` — no auto-create |
| Schema inference | `ml_platform/utils/connection_manager.py:1919` | `fetch_collection_metadata_firestore()` — samples 100 docs |
| Table creation | `ml_platform/utils/bigquery_manager.py:73` | `create_table_from_schema()` |
| Credentials retrieval | `ml_platform/utils/connection_manager.py` | `get_credentials_from_secret_manager()` |
| Selected columns storage | `ml_platform/models.py` DataSourceTable | `selected_columns` — names only, no types |

### Region Consideration

BigQuery datasets are region-locked, but the BigQuery client library auto-detects the dataset region from the table reference. The ETL runner does not need an explicit location parameter — it works correctly as long as the `raw_data` dataset exists (which it does, in `europe-central2`). Tables created within the dataset automatically inherit the region.

---

## Fix

Recreated the `bq_memos` table using a Django shell session that chains existing system functions. No new code was written.

### Steps Executed

**1. Retrieved ETL job configuration from Django DB:**

```python
from ml_platform.models import DataSource
ds = DataSource.objects.get(id=14)
table = ds.tables.first()
conn = ds.connection
# table.source_table_name = 'memos'
# table.dest_table_name = 'bq_memos'
# table.selected_columns = ['document_id', 'last_modified', ...] (20 columns)
# table.load_type = 'transactional'
# table.timestamp_column = 'created_at'
```

**2. Retrieved credentials from Secret Manager:**

```python
from ml_platform.utils.connection_manager import get_credentials_from_secret_manager
creds = get_credentials_from_secret_manager(conn.credentials_secret_name)
sa_json = creds['service_account_json']  # Credentials are wrapped in a dict
```

Note: `get_credentials_from_secret_manager` returns a dict with all connection fields. The actual service account JSON is nested under the `service_account_json` key.

**3. Re-inferred schema from live Firestore (samples 100 documents):**

```python
from ml_platform.utils.connection_manager import fetch_collection_metadata_firestore
result = fetch_collection_metadata_firestore(
    collection_name=table.source_table_name,  # 'memos'
    project_id=conn.bigquery_project,          # 'memo2-456215'
    service_account_json=sa_json,
)
# Result: 21 columns inferred, ~600 documents in collection
```

**4. Built BigQuery schema filtered to selected columns:**

```python
selected = set(table.selected_columns)
bq_schema = []
for col in result['columns']:
    if col['name'] not in selected:
        continue  # Skips 'embedding' column (not in original selection)
    bq_type = col['type'].replace(' (JSON)', '')  # 'STRING (JSON)' -> 'STRING'
    bq_schema.append({
        'name': col['name'],
        'bigquery_type': bq_type,
        'bigquery_mode': 'NULLABLE',
    })
```

**5. Created the table in BigQuery:**

```python
from ml_platform.utils.bigquery_manager import BigQueryTableManager
bq = BigQueryTableManager(project_id='b2b-recs', dataset_id='raw_data')
result = bq.create_table_from_schema(
    table_name='bq_memos',
    schema_columns=bq_schema,
    load_type='transactional',
    timestamp_column='created_at',
    description='ETL source: memos from memo2_firestore (transactional load)',
)
# Result: success, 20 columns, partitioned by created_at
```

### Recreated Table Schema

| Column | BigQuery Type |
|--------|--------------|
| `document_id` | STRING |
| `created_at` | TIMESTAMP |
| `question` | STRING |
| `answer` | STRING |
| `total_completed_reviews` | INTEGER |
| `user_name` | STRING |
| `correct_percentage` | FLOAT |
| `user_email` | STRING |
| `topic` | STRING |
| `last_percentage_update` | TIMESTAMP |
| `review_plan` | STRING |
| `user_id` | STRING |
| `memo_status` | STRING |
| `last_modified` | TIMESTAMP |
| `total_correct_reviews` | INTEGER |
| `question_number` | INTEGER |
| `status` | STRING |
| `original_memo_id` | STRING |
| `copied_from_user` | STRING |
| `source` | STRING |

- **Partitioned by:** `created_at` (DAY)
- **Clustered by:** `created_at`
- **All columns:** NULLABLE (Firestore documents may have missing fields)
- **1 column excluded:** `embedding` (not in original `selected_columns`)

---

## Post-Recovery: Stale Watermark + `processed_files` Bug Fix

**Date:** 2026-02-07

After recreating the empty `bq_memos` table (Feb 6), the ETL job ran successfully but loaded **0 rows**. Two bugs were identified and fixed in `etl_runner/main.py`.

### Bug 1: Stale Watermark

`DataSource.last_sync_value` was not reset when the table was recreated empty. The ETL queried Firestore with `created_at > 2025-12-02T15:11:20.083199`, skipping all ~600 existing documents. With 0 rows extracted, the watermark never advances — a permanent 0-row loop.

**Fix** (`main.py` — `run_transactional_load()`, after timestamp resolution):

After resolving `since_datetime` from `last_sync_value`, check if the destination BQ table has 0 rows via `self.loader.get_table_info()`. If the table is empty and `last_sync_value` was used:
- Log a warning about the stale watermark
- Fall back to `historical_start_date`
- If `historical_start_date` is also not set, use `"2000-01-01T00:00:00"` as a safe catch-all
- Wrapped in `try/except` so a failure to check row count doesn't break the ETL

```python
if last_sync_value and since_datetime == last_sync_value:
    try:
        table_info = self.loader.get_table_info()
        if table_info.get('num_rows', -1) == 0:
            fallback = historical_start_date or "2000-01-01T00:00:00"
            logger.warning(
                f"Destination table is empty but last_sync_value is "
                f"'{last_sync_value}' — stale watermark detected. "
                f"Falling back to '{fallback}'"
            )
            since_datetime = fallback
    except Exception as e:
        logger.warning(f"Could not check destination table row count: {e}")
```

### Bug 2: `processed_files` TypeError

`estimate_row_count()` passed `processed_files=None` to all extractors, but only `FileExtractor` accepts that parameter. All other extractors (Firestore, PostgreSQL, MySQL, BigQuery) raised a `TypeError`, caught as a warning:
```
WARNING Failed to estimate row count: ... unexpected keyword argument 'processed_files'
```

**Fix** (`main.py` — `estimate_row_count()`):

Build kwargs dict and only include `processed_files` when it's not `None`:

```python
estimate_kwargs = {
    'table_name': table_name,
    'schema_name': schema_name,
    'timestamp_column': timestamp_column,
    'since_datetime': since_datetime,
}
if processed_files is not None:
    estimate_kwargs['processed_files'] = processed_files
estimated_rows = self.extractor.estimate_row_count(**estimate_kwargs)
```

### Bug 3: numpy `int64` not JSON serializable

After bugs 1 & 2 were fixed, the ETL job (execution `etl-runner-z7srb`) successfully extracted and loaded **567 rows** to BigQuery, but crashed during finalization when sending run results back to the Django API:

```
ETL error occurred [load]: TypeError: Object of type int64 is not JSON serializable
```

`df.memory_usage(deep=True).sum()` returns numpy `int64`, which accumulates into `self.total_bytes_processed`. When this value is passed to `requests.patch(url, json=payload)` in `config.py:150`, `json.dumps()` fails on the numpy type.

**Fix** (`main.py` — 4 `counting_generator` / extraction sites + final payload):

Cast `.sum()` to native `int` at all accumulation sites:

```python
self.total_bytes_processed += int(df.memory_usage(deep=True).sum())
```

Defensive cast in the final status payload:

```python
'rows_extracted': int(self.total_rows_extracted),
'rows_loaded': int(self.total_rows_loaded),
'bytes_processed': int(self.total_bytes_processed),
```

### Bug 4: ETL deploy script using wrong Dockerfile

The initial redeployment (execution `etl-runner-6rwgx`) failed with `Application failed to start`. Cloud Build log showed it built with `CMD exec gunicorn ... config.wsgi:application` — the root Django `Dockerfile` instead of `etl_runner/Dockerfile`.

`etl_runner/deploy_to_cloud_run.sh` ran `gcloud builds submit` without a source directory argument, so it used CWD (the project root) as build context.

**Fix** (`etl_runner/deploy_to_cloud_run.sh`):

Resolve the script's own directory and pass it as the build source:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gcloud builds submit --tag gcr.io/$PROJECT_ID/etl-runner --project=$PROJECT_ID "$SCRIPT_DIR"
```

---

## Verification (Completed 2026-02-07)

After all fixes were deployed and the ETL job re-executed:

| Check | Result |
|-------|--------|
| BQ table `bq_memos` row count | **567 rows** |
| BQ `created_at` range | `2025-04-09 17:21:55` — `2025-12-02 15:11:20` |
| Django `last_sync_value` | `2025-12-02T15:11:20.083199` (matches max `created_at`) |
| `processed_files` TypeError | No longer appears |
| Deploy script | Builds correct Dockerfile regardless of CWD |
| JSON serialization | No int64 errors during finalization |

Data was loaded by execution `etl-runner-z7srb` (first attempt). The int64 crash occurred *after* BQ load succeeded but *before* Django status update. Subsequent runs correctly report 0 new rows (no Firestore documents newer than the watermark).
