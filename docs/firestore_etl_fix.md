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

## Verification

After table creation, the ETL job `memo2_firestore_memos_v2` should:
1. Pass the VALIDATE phase (`verify_table_exists()` returns True)
2. Extract ~600 documents from Firestore collection `memos`
3. Load them into `b2b-recs.raw_data.bq_memos`
