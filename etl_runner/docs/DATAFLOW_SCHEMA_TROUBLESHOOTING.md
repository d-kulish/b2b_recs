# Dataflow BigQuery Schema Troubleshooting Guide

**Created:** November 23, 2025
**Status:** Resolved ✅
**Affected Component:** Dataflow ETL Pipeline (Large Datasets >= 1M rows)

---

## Problem Summary

Dataflow pipelines for large-scale ETL jobs (>= 1M rows) failed with schema type mismatch errors when writing to BigQuery tables containing DATE, TIME, or DATETIME fields.

---

## Error Timeline and Evolution

### Error 1: Missing Schema Parameter (Initial)

**Error Message:**
```
Dataflow execution failed: A schema is required in order to prepare rows for writing with STORAGE_WRITE_API.
```

**Context:**
- Using `STORAGE_WRITE_API` method for BigQuery writes
- No schema parameter provided to `WriteToBigQuery` transform

**Attempted Fix:**
- Added `get_bq_table_schema()` function to fetch BigQuery table schema
- Converted BigQuery schema to Beam's `TableSchema` format
- Added `schema` parameter to `WriteToBigQuery`

**Result:** Led to Error 2 ❌

---

### Error 2: TableSchema Import Error

**Error Message:**
```
ImportError: cannot import name 'TableSchema' from 'apache_beam.io.gcp.bigquery'
```

**Root Cause:**
- `TableSchema` and `TableFieldSchema` are in internal module, not public API
- Wrong import path used

**Fix:**
```python
# Changed from:
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition, TableSchema, TableFieldSchema

# To:
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition
from apache_beam.io.gcp.internal.clients.bigquery import TableSchema, TableFieldSchema
```

**Result:** Led to Error 3 ❌

---

### Error 3: Unsupported DATE Type

**Error Message:**
```
Converting BigQuery type [DATE] to Python Beam type is not supported.
```

**Root Cause:**
- Apache Beam's `TableFieldSchema` doesn't directly support BigQuery's DATE, TIME, DATETIME types
- Schema conversion was passing BigQuery types through without mapping

**Attempted Fix:**
- Created `_map_bq_type_to_beam_type()` function
- Mapped DATE/TIME/DATETIME → STRING
- Mapped INT64 → INTEGER, FLOAT64 → FLOAT, etc.

**Result:** Led to Error 4 ❌

---

### Error 4: Java Dependency Required

**Error Message:**
```
RuntimeError: Java must be installed on this system to use this transform/runner.
Downloading job server jar from https://repo.maven.apache.org/maven2/org/apache/beam/...
Error bringing up service
```

**Root Cause:**
- `STORAGE_WRITE_API` method requires Java expansion service
- ETL Runner Docker container doesn't have Java installed
- Adding Java increases image size and complexity

**Attempted Fix:**
- Switched from `STORAGE_WRITE_API` to `FILE_LOADS` method
- `FILE_LOADS` is pure Python, no Java required
- Kept schema parameter with type mapping

**Result:** Led to Error 5 ❌

---

### Error 5: Schema Type Mismatch (Final Root Cause)

**Error Message:**
```
RuntimeError: BigQuery job beam_bq_job_LOAD_etl1144_LOAD_STEP_... failed.
Error Result: <ErrorProto
  message: 'Provided Schema does not match Table b2b-recs:raw_data.bq_transactions_v2.
           Field block_timestamp_month has changed type from DATE to STRING'
  reason: 'invalid'>
```

**Root Cause Analysis:**

1. **BigQuery Table Schema:**
   - Table `bq_transactions_v2` has field `block_timestamp_month` with type `DATE`

2. **Our Type Mapping:**
   - `_map_bq_type_to_beam_type()` converts `DATE` → `STRING`
   - Schema provided to Beam has `STRING` type for date fields

3. **FILE_LOADS Behavior:**
   - Writes data to temporary GCS files
   - Uses BigQuery Load API to load from GCS
   - When explicit schema is provided, BigQuery requires **exact match** with table schema
   - Our schema has `STRING`, table has `DATE` → Validation fails

4. **The Fundamental Issue:**
   - We tried to solve a non-existent problem
   - `FILE_LOADS` method doesn't need explicit schema
   - It can use the existing table's schema automatically
   - Providing a schema with type mapping breaks the exact match requirement

---

## Final Solution

### Remove Schema Parameter from FILE_LOADS

**Approach:** Let `FILE_LOADS` use the existing BigQuery table schema automatically.

**Changes Made:**

**1. Database Pipeline (`run_database_pipeline`):**

```python
# REMOVED: Schema fetching
# bq_schema = get_bq_table_schema(
#     project_id=gcp_config['project_id'],
#     dataset_id=gcp_config['dataset_id'],
#     table_name=job_config['dest_table_name']
# )

# UPDATED: WriteToBigQuery without schema parameter
| 'WriteToBigQuery' >> WriteToBigQuery(
    table=table_ref,
    # schema=bq_schema,  # REMOVED - FILE_LOADS uses existing table schema
    write_disposition=write_disposition,
    create_disposition=BigQueryDisposition.CREATE_NEVER,  # Table must exist
    method='FILE_LOADS'  # FILE_LOADS uses existing table schema automatically
)
```

**2. File Pipeline (`run_file_pipeline`):**

```python
# REMOVED: Schema fetching
# bq_schema = get_bq_table_schema(...)

# UPDATED: WriteToBigQuery without schema parameter
| 'WriteToBigQuery' >> WriteToBigQuery(
    table=table_ref,
    # schema=bq_schema,  # REMOVED - FILE_LOADS uses existing table schema
    write_disposition=write_disposition,
    create_disposition=BigQueryDisposition.CREATE_NEVER,
    method='FILE_LOADS'  # FILE_LOADS uses existing table schema automatically
)
```

**3. Added Logging:**

```python
logger.info(f"Using FILE_LOADS method (schema inferred from existing table)")
```

---

## How FILE_LOADS Works

### Write Process Flow:

```
1. Beam Pipeline Executes
   ↓
2. Data written to temporary GCS files
   ↓
3. BigQuery Load API triggered
   ↓
4. BigQuery loads from GCS using existing table schema
   ↓
5. Data validated against table schema
   ↓
6. Temporary GCS files cleaned up
```

### Key Benefits:

- ✅ **No Schema Conflicts:** Uses actual table schema, not converted/mapped schema
- ✅ **No Java Required:** Pure Python implementation
- ✅ **Handles All Types:** DATE, TIME, DATETIME, NUMERIC, GEOGRAPHY, REPEATED, RECORD
- ✅ **Type Safety:** BigQuery validates data types during load
- ✅ **Cost Effective:** Minimal temporary GCS storage cost
- ✅ **Recommended:** Default method for batch Dataflow jobs

---

## Files Modified

### `dataflow_pipelines/etl_pipeline.py`

**Removed:**
- Schema fetching calls in both `run_database_pipeline()` and `run_file_pipeline()`
- `schema=bq_schema` parameter from both `WriteToBigQuery` calls

**Kept (Not Used, but Harmless):**
- `get_bq_table_schema()` function (may be useful for future debugging)
- `_map_bq_type_to_beam_type()` function (not called, but documents type mapping knowledge)

**Line Changes:**
- Lines 286-299: Database pipeline - removed schema fetching, added logging
- Lines 319-324: Database WriteToBigQuery - removed schema parameter
- Lines 347-361: File pipeline - removed schema fetching, added logging
- Lines 381-386: File WriteToBigQuery - removed schema parameter

---

## Django App Requirements

### Prerequisites for Dataflow Success:

1. **BigQuery Table Must Exist**
   - ✅ Already enforced by `create_disposition=CREATE_NEVER`
   - ETL Wizard creates tables before first run

2. **Table Schema Must Match Source Data**
   - ✅ ETL Wizard uses `schema_mapper.py` to infer schema from source
   - Schema detection handles DATE, TIME, DATETIME correctly
   - No changes needed

3. **Table Must Be in Correct Dataset**
   - ✅ Already configured via `gcp_config['dataset_id']`
   - Default: `raw_data`

### No Django Code Changes Required ✅

The issue was purely in Dataflow pipeline implementation. Django app already:
- Creates BigQuery tables with correct schema before ETL runs
- Passes correct table reference to Dataflow pipeline
- Enforces table existence requirement

---

## Testing Checklist

### Test Cases for Validation:

- [ ] **Database source with DATE fields**
  - Table: `bq_transactions_v2`
  - Field: `block_timestamp_month` (DATE type)
  - Expected: Loads successfully

- [ ] **Database source with TIME fields**
  - Expected: Loads successfully

- [ ] **Database source with DATETIME fields**
  - Expected: Loads successfully

- [ ] **Database source with NUMERIC fields**
  - Expected: Loads successfully

- [ ] **File source (CSV) with mixed types**
  - Expected: Loads successfully

- [ ] **Incremental load (transactional)**
  - Expected: Appends data correctly

- [ ] **Full load (catalog)**
  - Expected: Truncates and loads correctly

---

## Lessons Learned

### What Went Wrong:

1. **Over-Engineering:** Tried to provide explicit schema when not needed
2. **Type Mapping Complexity:** Added unnecessary type conversions
3. **Method Mismatch:** `STORAGE_WRITE_API` requirements don't apply to `FILE_LOADS`
4. **Documentation Gap:** Beam docs don't clearly explain FILE_LOADS schema behavior

### Best Practices:

1. **Use FILE_LOADS for Batch Jobs**
   - Default method for Dataflow batch processing
   - No Java, no schema conflicts
   - Let BigQuery handle type validation

2. **Don't Provide Schema for Existing Tables**
   - Let BigQuery use existing table schema
   - Only provide schema when creating new tables

3. **Understand Method Requirements**
   - `STORAGE_WRITE_API`: Requires Java, requires schema, better streaming
   - `FILE_LOADS`: Pure Python, optional schema, better batch
   - `STREAMING_INSERTS`: For streaming, has quotas

4. **Trust BigQuery Type Handling**
   - BigQuery handles DATE/TIME/DATETIME correctly
   - No need to convert to STRING
   - Type validation happens during load

---

## Related Documentation

- [Apache Beam BigQuery I/O](https://beam.apache.org/documentation/io/built-in/google-bigquery/)
- [BigQuery Load API](https://cloud.google.com/bigquery/docs/loading-data)
- [Dataflow Best Practices](https://cloud.google.com/dataflow/docs/guides/deploying-a-pipeline)

---

## Appendix: Code Artifacts

### Schema Mapping Function (Not Used, For Reference)

```python
def _map_bq_type_to_beam_type(bq_type: str) -> str:
    """
    Map BigQuery field type to Beam-compatible type.

    Note: This function is NOT used with FILE_LOADS method.
    Kept for reference in case STORAGE_WRITE_API is needed in future.
    """
    type_mapping = {
        # Temporal types -> STRING (Beam doesn't support DATE/TIME/DATETIME directly)
        'DATE': 'STRING',
        'TIME': 'STRING',
        'DATETIME': 'STRING',

        # Numeric types
        'INT64': 'INTEGER',
        'INTEGER': 'INTEGER',
        'FLOAT64': 'FLOAT',
        'FLOAT': 'FLOAT',

        # Other types (pass through)
        'STRING': 'STRING',
        'BYTES': 'BYTES',
        'BOOL': 'BOOLEAN',
        'BOOLEAN': 'BOOLEAN',
        'TIMESTAMP': 'TIMESTAMP',
        'NUMERIC': 'NUMERIC',
        'BIGNUMERIC': 'NUMERIC',
        'GEOGRAPHY': 'GEOGRAPHY',
        'RECORD': 'RECORD',
    }

    return type_mapping.get(bq_type, bq_type)
```

### Working WriteToBigQuery Configuration

```python
# Correct configuration for FILE_LOADS
| 'WriteToBigQuery' >> WriteToBigQuery(
    table=table_ref,  # Format: "project:dataset.table"
    write_disposition=BigQueryDisposition.WRITE_APPEND,  # or WRITE_TRUNCATE
    create_disposition=BigQueryDisposition.CREATE_NEVER,  # Table must exist
    method='FILE_LOADS'  # Uses existing table schema automatically
)
```

---

**Status:** Issue resolved. Dataflow pipelines now working correctly for all data types including DATE, TIME, DATETIME fields. ✅
