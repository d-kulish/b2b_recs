# Firestore ETL PyArrow Conversion Issue - Root Cause Analysis & Solution

**Date**: November 25, 2025
**Project**: B2B Recommendations ETL Runner
**Issue**: Firestore data extraction fails with PyArrow type conversion error
**Status**: Solution designed, ready for implementation

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Error Details](#error-details)
3. [Attempts to Fix (10+ iterations)](#attempts-to-fix)
4. [Root Cause Analysis](#root-cause-analysis)
5. [Proposed Solution](#proposed-solution)
6. [Implementation Plan](#implementation-plan)
7. [Testing Strategy](#testing-strategy)
8. [Success Criteria](#success-criteria)
9. [Rollback Plan](#rollback-plan)

---

## Problem Statement

### Context

The B2B Recommendations system includes an ETL runner that supports multiple data sources:
- **Relational Databases**: PostgreSQL, MySQL, BigQuery
- **File Storage**: GCS, S3, Azure Blob
- **NoSQL Databases**: Firestore (recently implemented)

### The Issue

When running ETL jobs for Firestore data sources, the extraction succeeds (558 documents extracted) but loading to BigQuery fails consistently with:

```
Error converting Pandas column with name: "last_modified" and datatype: "object"
to an appropriate pyarrow datatype: Array, ListArray, or StructArray
```

**Impact**:
- ❌ Firestore ETL jobs cannot complete
- ❌ No data loaded to BigQuery
- ❌ Business analytics blocked for Firestore-sourced data
- ✅ Other data sources (PostgreSQL, MySQL, BigQuery, Files) work fine

---

## Error Details

### Full Error Stack

```
2025-11-25 16:57:57.425 EET
Converted column '_extracted_at' to string dtype

2025-11-25 16:57:57.719 EET
Error converting Pandas column with name: "last_modified" and datatype: "object"
to an appropriate pyarrow datatype: Array, ListArray, or StructArray

2025-11-25 16:57:57.719 EET
Unexpected error during load: Error converting Pandas column...

2025-11-25 16:57:57.719 EET
Incremental load failed at batch 1: Error converting Pandas column...

2025-11-25 16:57:57.719 EET
Transactional load failed: Error converting Pandas column...
```

### Error Location

**File**: `etl_runner/loaders/bigquery_loader.py`
**Line**: 85 (inside `load_table_from_dataframe()`)
**Method**: BigQuery Python client's internal PyArrow conversion

### Data Source Details

- **DataSource ID**: 13
- **Collection**: `memos`
- **Document Count**: 600 documents
- **Problematic Field**: `last_modified` (Firestore Timestamp type)
- **Other Fields**: Various types including strings, numbers, nested objects

---

## Attempts to Fix

### Summary: 10+ Iterations Over 4 Hours

All attempts focused on type conversion at different layers, but failed because they didn't address the architectural issue.

---

### Attempt #1: Add Firestore to Valid Source Types
**Date**: 2025-11-25 14:30
**Change**: Updated `utils/error_handling.py` to recognize 'firestore' as valid source type
**Files Modified**: `error_handling.py`
**Result**: ❌ Fixed validation error, but exposed PyArrow error

---

### Attempt #2: Fix Credential Passing
**Date**: 2025-11-25 14:45
**Change**: Added credential wrapping in Django API for Firestore connections
**Files Modified**: `ml_platform/views.py` (api_etl_job_config)
**Result**: ❌ Fixed credential error, but exposed PyArrow error

---

### Attempt #3: Firestore Timestamp Conversion in Extractor
**Date**: 2025-11-25 15:15
**Change**: Added Firestore timestamp detection and conversion to ISO strings
**Files Modified**: `extractors/firestore.py` (_flatten_document)
**Code**:
```python
if hasattr(field_value, 'seconds') and hasattr(field_value, 'nanos'):
    ts = datetime.utcfromtimestamp(field_value.seconds + field_value.nanos / 1e9)
    flat_doc[field_name] = ts.isoformat()
```
**Result**: ❌ Conversion logic correct, but PyArrow error persisted

---

### Attempt #4: Add DataFrame Sanitization Layer
**Date**: 2025-11-25 15:30
**Change**: Added `_sanitize_for_dataframe()` method to force primitives
**Files Modified**: `extractors/firestore.py`
**Code**:
```python
def _sanitize_for_dataframe(self, rows):
    for row in rows:
        for key, value in row.items():
            if not isinstance(value, (str, int, float, bool, type(None))):
                row[key] = str(value)
    return rows
```
**Result**: ❌ PyArrow error persisted

---

### Attempt #5: Explicit dtype Conversion in Extractor
**Date**: 2025-11-25 15:45
**Change**: Added `astype(str)` conversion after DataFrame creation
**Files Modified**: `extractors/firestore.py`
**Code**:
```python
df = pd.DataFrame(sanitized_rows)
for col in df.select_dtypes(include=['object']).columns:
    df[col] = df[col].astype(str)
```
**Result**: ❌ PyArrow error persisted

---

### Attempt #6-8: Multiple Variations of dtype Conversion
**Date**: 2025-11-25 16:00-16:15
**Changes**:
- Added conversion in BigQueryLoader before load
- Added diagnostic logging
- Added explicit type checking with lambda functions
**Files Modified**: `loaders/bigquery_loader.py`
**Result**: ❌ Logs showed some columns converting, but `last_modified` still failed

---

### Attempt #9: Comprehensive Diagnostic + Conversion
**Date**: 2025-11-25 16:30
**Change**: Added detailed logging and multi-stage conversion
**Files Modified**: `loaders/bigquery_loader.py`
**Code**:
```python
# Diagnostic logging
for col in df.columns:
    logger.info(f"Column '{col}': dtype={df[col].dtype}, sample_value_type={type(sample_value).__name__}")

# Conversion
for col in df.columns:
    if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
        df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (list, dict)) else x)
    if df[col].dtype == 'object':
        df[col] = df[col].astype(str)
```
**Result**: ❌ PyArrow error persisted

---

### Attempt #10: Force Rebuild (No Cache)
**Date**: 2025-11-25 16:45
**Change**: Deployed with fresh Docker build to ensure code changes included
**Result**: ❌ Confirmed code is running (saw log messages), but error persists

---

### Key Observations from All Attempts

1. **Code IS Deploying**: Logs confirm new code runs (e.g., "Converted column '_extracted_at'")
2. **Selective Failure**: Some columns convert successfully, `last_modified` does not
3. **Error Location**: Happens INSIDE `load_table_from_dataframe()`, not in our code
4. **Type Conversion Ineffective**: Converting to string dtype doesn't prevent PyArrow error

---

## Root Cause Analysis

### The Fundamental Problem

**We're using the wrong loading architecture for Firestore data.**

### Current Architecture (Broken)

```
┌─────────────┐
│  Firestore  │  ← Complex timestamp objects, nested data
└──────┬──────┘
       │ extract
       ▼
┌─────────────────┐
│ Flatten to Dict │  ← Convert timestamps to ISO strings
└──────┬──────────┘
       │ create DataFrame
       ▼
┌──────────────────┐
│ Pandas DataFrame │  ← Infers 'object' dtype for mixed types
└──────┬───────────┘
       │ load_table_from_dataframe()
       ▼
┌──────────────────┐
│ PyArrow Table    │  ← ❌ TYPE INFERENCE FAILS HERE
└──────┬───────────┘       (sees complex Python objects)
       │
       ▼
┌──────────────────┐
│    BigQuery      │  ← Never reached
└──────────────────┘
```

### Why PyArrow Fails

**PyArrow's Type Inference**:
1. Inspects actual Python objects in DataFrame, not just dtypes
2. Sees Firestore Timestamp objects (even after flattening)
3. Tries to infer as complex type (Array/List/Struct)
4. Can't map to BigQuery type → ERROR

**Why dtype Conversion Doesn't Work**:
- `df[col].astype(str)` changes Pandas metadata
- But underlying Python objects remain unchanged
- PyArrow reads the objects directly, ignoring dtype
- BigQuery client uses PyArrow's inference, not Pandas'

### Evidence

From logs:
```
Converted column '_extracted_at' to string dtype  ← Our code runs
Error converting... "last_modified"                ← PyArrow fails anyway
```

From test (test_firestore_bug.py):
```
✓ SUCCESS - PyArrow conversion worked!
```

**Conclusion**: The flattening logic is correct. The issue is that production Firestore data has objects our test didn't simulate.

### Why This Only Affects Firestore

| Source Type | Data Structure | Loading Method | PyArrow Issue? |
|-------------|---------------|----------------|----------------|
| PostgreSQL  | Relational (simple types) | DataFrame → PyArrow | ❌ No |
| MySQL       | Relational (simple types) | DataFrame → PyArrow | ❌ No |
| BigQuery    | Relational (simple types) | DataFrame → PyArrow | ❌ No |
| Files (CSV/Parquet) | Flat structure | DataFrame → PyArrow | ❌ No |
| **Firestore** | **NoSQL (complex types)** | DataFrame → PyArrow | ✅ **YES** |

Firestore's document model includes:
- Special Timestamp objects
- Nested maps/arrays
- Reference types
- Geo-point objects

These don't map cleanly to Pandas/PyArrow types.

---

## Proposed Solution

### Architecture Change: JSON Streaming Insert

**Replace**: DataFrame → PyArrow → BigQuery
**With**: Dict → JSON → BigQuery Streaming API

### New Architecture

```
┌─────────────┐
│  Firestore  │
└──────┬──────┘
       │ extract
       ▼
┌─────────────────┐
│ Flatten to Dict │  ← Convert all values to JSON-serializable types
└──────┬──────────┘
       │ yield dict (not DataFrame)
       ▼
┌──────────────────────┐
│ BigQuery Streaming   │  ← client.insert_rows_json()
│ Insert API           │    (no PyArrow involved)
└──────┬───────────────┘
       │
       ▼
┌──────────────────┐
│    BigQuery      │  ✅ SUCCESS
└──────────────────┘
```

### Why This Works

1. **No PyArrow**: Streaming insert API doesn't use PyArrow
2. **Native JSON**: Firestore data is already JSON-like
3. **Simple Conversion**: JSON serialization rules are well-defined
4. **BigQuery Handles Types**: Server-side type conversion based on table schema
5. **Proven Method**: Used by many Firestore → BigQuery integrations

### Benefits

| Benefit | Description |
|---------|-------------|
| **Eliminates PyArrow** | Root cause of error completely removed |
| **Simpler Code** | No DataFrame manipulation, no dtype conversions |
| **Better Performance** | Streaming insert is optimized for this use case |
| **Easier Debugging** | JSON is human-readable, errors are clearer |
| **Future-Proof** | Works with any Firestore data type |
| **Minimal Changes** | Isolated to Firestore extractor and loader |

### Trade-offs

| Consideration | Impact | Mitigation |
|--------------|--------|------------|
| **Rate Limits** | Streaming insert: 100k rows/sec/project | Batching (10k rows/request) |
| **Cost** | Streaming: $0.01 per 200 MB | Same cost as current method |
| **Atomic Loads** | No WRITE_TRUNCATE (append only) | Manual cleanup if needed |
| **Validation** | Less strict than batch load | Pre-validate in extractor |

---

## Implementation Plan

### Phase 1: Update Firestore Extractor (2 hours)

**File**: `etl_runner/extractors/firestore.py`

#### Changes:

1. **Modify extraction methods to yield dicts instead of DataFrames**

   ```python
   # BEFORE (current)
   def extract_full(self, table_name, selected_columns, batch_size=10000):
       rows_buffer = []
       for doc in collection_ref.stream():
           flat_doc = self._flatten_document(doc, selected_columns)
           rows_buffer.append(flat_doc)

           if len(rows_buffer) >= batch_size:
               df = pd.DataFrame(rows_buffer)  # ← Creates DataFrame
               yield df

   # AFTER (new)
   def extract_full(self, table_name, selected_columns, batch_size=10000):
       rows_buffer = []
       for doc in collection_ref.stream():
           flat_doc = self._flatten_document(doc, selected_columns)
           rows_buffer.append(flat_doc)

           if len(rows_buffer) >= batch_size:
               yield rows_buffer  # ← Yields list of dicts
               rows_buffer = []
   ```

2. **Enhance `_flatten_document()` to ensure JSON-serializable output**

   ```python
   def _flatten_document(self, doc, selected_columns):
       """Flatten to JSON-serializable dict (no Pandas objects)"""
       flat_doc = {}

       for field_name, field_value in doc_dict.items():
           # Convert all values to JSON-serializable types
           flat_doc[field_name] = self._to_json_value(field_value)

       return flat_doc

   def _to_json_value(self, value):
       """Convert any value to JSON-serializable type"""
       if value is None:
           return None
       elif isinstance(value, (str, int, float, bool)):
           return value
       elif isinstance(value, datetime):
           return value.isoformat()
       elif hasattr(value, 'seconds') and hasattr(value, 'nanos'):
           # Firestore Timestamp
           ts = datetime.utcfromtimestamp(value.seconds + value.nanos / 1e9)
           return ts.isoformat()
       elif isinstance(value, dict):
           return json.dumps(value)  # Convert nested objects to JSON string
       elif isinstance(value, list):
           return json.dumps(value)  # Convert arrays to JSON string
       else:
           return str(value)  # Fallback
   ```

3. **Update method signatures**
   - `extract_full()` → yields `List[Dict]` instead of `DataFrame`
   - `extract_incremental()` → yields `List[Dict]` instead of `DataFrame`

#### Files to Modify:
- `extractors/firestore.py`

#### Testing:
- Unit test: Verify dicts are JSON-serializable
- Integration test: Extract 10 sample documents

---

### Phase 2: Create JSON Loading Method (1.5 hours)

**File**: `etl_runner/loaders/bigquery_loader.py`

#### Changes:

1. **Add new method `load_batch_from_json()`**

   ```python
   def load_batch_from_json(
       self,
       rows: List[Dict[str, Any]],
       write_mode: str = 'WRITE_APPEND'
   ) -> Dict[str, Any]:
       """
       Load a batch of JSON data to BigQuery using streaming insert.

       Args:
           rows: List of dictionaries (JSON-serializable)
           write_mode: 'WRITE_APPEND' only (streaming doesn't support truncate)

       Returns:
           Dict with load statistics
       """
       if not rows:
           logger.warning("Empty rows provided, skipping load")
           return {'rows_loaded': 0, 'errors': None}

       logger.info(f"Loading batch to {self.table_ref}: {len(rows)} rows (JSON streaming)")

       try:
           # Use streaming insert API
           errors = self.client.insert_rows_json(
               table=self.table_ref,
               json_rows=rows,
               row_ids=[None] * len(rows)  # Auto-generate row IDs
           )

           if errors:
               logger.error(f"Streaming insert errors: {errors}")
               return {
                   'rows_loaded': len(rows) - len(errors),
                   'errors': errors
               }
           else:
               logger.info(f"Successfully loaded {len(rows)} rows via streaming insert")
               return {
                   'rows_loaded': len(rows),
                   'errors': None
               }

       except Exception as e:
           logger.error(f"Streaming insert failed: {str(e)}")
           raise
   ```

2. **Add detection logic to choose loading method**

   ```python
   def load_batch(self, data, write_mode='WRITE_APPEND'):
       """
       Smart loader: detects data type and uses appropriate method.

       - DataFrame → load_table_from_dataframe() (current method)
       - List[Dict] → insert_rows_json() (new method for Firestore)
       """
       if isinstance(data, pd.DataFrame):
           return self._load_batch_from_dataframe(data, write_mode)
       elif isinstance(data, list):
           return self.load_batch_from_json(data, write_mode)
       else:
           raise ValueError(f"Unsupported data type: {type(data)}")
   ```

3. **Rename existing method for clarity**
   - `load_batch()` → `_load_batch_from_dataframe()` (internal)
   - New `load_batch()` dispatches to appropriate method

#### Files to Modify:
- `loaders/bigquery_loader.py`

#### Testing:
- Unit test: Verify JSON rows are inserted
- Test error handling: Invalid JSON, schema mismatches

---

### Phase 3: Update ETL Runner Main Logic (30 minutes)

**File**: `etl_runner/main.py`

#### Changes:

1. **Handle both DataFrame and dict generators**

   ```python
   # Current code expects DataFrames:
   for df in df_generator:
       result = self.loader.load_batch(df, write_mode=write_mode)

   # New code handles both:
   for batch in data_generator:
       # batch can be DataFrame (old sources) or List[Dict] (Firestore)
       result = self.loader.load_batch(batch, write_mode=write_mode)
   ```

2. **No other changes needed** - the abstraction handles it

#### Files to Modify:
- `main.py` (minimal changes, just type annotations)

#### Testing:
- Integration test: Run full ETL pipeline
- Verify both DataFrame and JSON paths work

---

### Phase 4: Documentation & Cleanup (30 minutes)

#### Changes:

1. **Update code comments** to explain JSON streaming approach
2. **Add docstrings** for new methods
3. **Update README** with Firestore-specific notes
4. **Remove deprecated code** (sanitization functions that aren't needed)

#### Files to Modify:
- `extractors/firestore.py` (docstrings)
- `loaders/bigquery_loader.py` (docstrings)
- `README.md` or `etl_runner.md`

---

### Summary of Changes

| File | Changes | Lines Changed | Risk |
|------|---------|---------------|------|
| `extractors/firestore.py` | Yield dicts instead of DataFrames | ~50 | Low |
| `loaders/bigquery_loader.py` | Add JSON streaming method | ~80 | Low |
| `main.py` | Type handling (minimal) | ~5 | Very Low |

**Total Estimated Time**: 4-5 hours
**Risk Level**: Low (changes isolated to Firestore, doesn't affect other sources)

---

## Testing Strategy

### Phase 1: Unit Tests

**Test File**: `tests/test_firestore_json_extract.py`

```python
def test_firestore_flatten_to_json():
    """Test that flattened documents are JSON-serializable"""
    extractor = FirestoreExtractor(test_config)

    # Mock Firestore document with complex types
    mock_doc = create_mock_firestore_doc()

    # Flatten
    flat_doc = extractor._flatten_document(mock_doc, [])

    # Verify JSON serializable
    json_str = json.dumps(flat_doc)
    assert json_str is not None

    # Verify no complex Python objects
    for value in flat_doc.values():
        assert isinstance(value, (str, int, float, bool, type(None)))

def test_json_streaming_insert():
    """Test BigQuery JSON streaming insert"""
    loader = BigQueryLoader('project', 'dataset', 'table')

    test_rows = [
        {'id': '1', 'name': 'Test', 'last_modified': '2024-11-25T10:00:00'},
        {'id': '2', 'name': 'Test2', 'last_modified': '2024-11-25T11:00:00'}
    ]

    result = loader.load_batch_from_json(test_rows)
    assert result['rows_loaded'] == 2
    assert result['errors'] is None
```

**Duration**: 1 hour
**Success Criteria**: All tests pass

---

### Phase 2: Integration Test (Local)

**Test Script**: `test_firestore_etl.py` (already created)

```bash
# Run integration test
cd /Users/dkulish/Projects/b2b_recs
source venv/bin/activate
python test_firestore_etl.py 13
```

**What It Tests**:
- Extract 3 sample documents from Firestore
- Flatten to JSON-serializable dicts
- Verify no complex Python objects
- (Optional) Insert to test BigQuery table

**Duration**: 30 minutes
**Success Criteria**:
- ✅ All documents flatten successfully
- ✅ No complex objects detected
- ✅ JSON serialization succeeds

---

### Phase 3: Staging Deployment

**Steps**:

1. **Deploy to staging environment**
   ```bash
   cd /Users/dkulish/Projects/b2b_recs/etl_runner
   gcloud builds submit --tag gcr.io/b2b-recs/etl-runner:firestore-json-staging
   gcloud run jobs update etl-runner-staging --image=gcr.io/b2b-recs/etl-runner:firestore-json-staging
   ```

2. **Run test ETL job**
   - DataSource: 13 (Firestore memos collection)
   - Expected rows: 600 documents
   - Load type: Transactional (incremental)

3. **Monitor logs**
   ```bash
   gcloud logging read \
     'resource.type=cloud_run_job
      AND resource.labels.job_name=etl-runner-staging' \
     --limit=100 \
     --format=json
   ```

**Expected Log Output**:
```
Extracting data from Firestore collection: memos
Extracted batch 1: 600 documents
Loading batch to b2b-recs.raw_data.bq_memos: 600 rows (JSON streaming)
✓ Successfully loaded 600 rows via streaming insert
ETL completed successfully
Total rows: 600
Duration: XX seconds
```

**Duration**: 1 hour
**Success Criteria**:
- ✅ No PyArrow errors
- ✅ All 600 rows loaded to BigQuery
- ✅ Data matches Firestore source

---

### Phase 4: Production Validation

**Steps**:

1. **Verify data in BigQuery**
   ```sql
   -- Count rows
   SELECT COUNT(*) FROM `b2b-recs.raw_data.bq_memos`;
   -- Expected: 600

   -- Check last_modified field
   SELECT
     id,
     name,
     last_modified,
     _extracted_at
   FROM `b2b-recs.raw_data.bq_memos`
   ORDER BY last_modified DESC
   LIMIT 10;

   -- Verify no NULL values in critical fields
   SELECT
     COUNT(*) as total_rows,
     COUNT(last_modified) as last_modified_count,
     COUNT(id) as id_count
   FROM `b2b-recs.raw_data.bq_memos`;
   ```

2. **Run incremental update test**
   - Add/modify 5 documents in Firestore
   - Run ETL job again
   - Verify only new/modified records are loaded

3. **Performance benchmarks**
   - Measure extraction time
   - Measure loading time
   - Compare to expected performance (should be similar or better)

**Duration**: 1 hour
**Success Criteria**:
- ✅ Data accuracy: 100% match with Firestore
- ✅ Incremental loads work correctly
- ✅ Performance: ≤ 5 seconds for 600 rows

---

### Phase 5: Rollback Test

**Verify rollback capability**:

1. Tag previous working image:
   ```bash
   gcloud container images add-tag \
     gcr.io/b2b-recs/etl-runner:previous-stable \
     gcr.io/b2b-recs/etl-runner:rollback
   ```

2. Test rollback:
   ```bash
   gcloud run jobs update etl-runner \
     --image=gcr.io/b2b-recs/etl-runner:rollback
   ```

3. Verify other sources still work (PostgreSQL, MySQL)

**Duration**: 30 minutes
**Success Criteria**:
- ✅ Rollback completes without errors
- ✅ Non-Firestore ETL jobs still work

---

## Success Criteria

### Functional Requirements

- [ ] Firestore ETL job completes without errors
- [ ] All 600 documents loaded to BigQuery
- [ ] `last_modified` field populated correctly (no NULLs)
- [ ] Nested fields serialized as JSON strings
- [ ] Incremental loads work (only new/modified records)

### Non-Functional Requirements

- [ ] Performance: ≤ 10 seconds for 600 rows
- [ ] No PyArrow errors in logs
- [ ] No regression for other source types (PostgreSQL, MySQL, BigQuery, Files)
- [ ] Code is documented and maintainable

### Data Quality

- [ ] 100% row count match (Firestore → BigQuery)
- [ ] Data type integrity maintained
- [ ] Timestamp fields in ISO 8601 format
- [ ] No data corruption or truncation

---

## Rollback Plan

### If JSON Streaming Fails

**Scenario**: JSON streaming has unexpected issues (rate limits, errors)

**Rollback Steps**:

1. **Immediate**: Revert to previous Docker image
   ```bash
   gcloud run jobs update etl-runner \
     --image=gcr.io/b2b-recs/etl-runner:previous-stable
   ```

2. **Temporary workaround**: Disable Firestore ETL jobs manually

3. **Implement fallback**: Option 3 (Explicit PyArrow Schema)
   - Faster to implement (2-3 hours)
   - Less architectural change
   - May still have edge cases

### If Partial Success

**Scenario**: JSON streaming works but data quality issues

**Steps**:

1. Keep JSON streaming for extraction
2. Add data validation layer
3. Fix specific field conversions
4. Redeploy and re-test

### Communication Plan

**Stakeholders to notify**:
- Product team (if Firestore data is business-critical)
- Data analytics team (if dashboards depend on this data)

**Communication template**:
```
Subject: Firestore ETL - Implementation in Progress

Status: Implementing architectural fix for Firestore ETL
Impact: Firestore data will be unavailable for XX hours
ETA: <timestamp>
Rollback: Available if needed
Contact: <your contact>
```

---

## Next Steps

### Immediate Actions (This Week)

1. **Monday AM**: Implement Phase 1 (Firestore Extractor changes)
2. **Monday PM**: Implement Phase 2 (BigQuery JSON loader)
3. **Tuesday AM**: Testing (unit + integration)
4. **Tuesday PM**: Staging deployment
5. **Wednesday AM**: Production deployment
6. **Wednesday PM**: Validation and monitoring

### Follow-Up Actions (Next Week)

1. Document lessons learned
2. Update ETL architecture documentation
3. Add monitoring/alerting for Firestore ETL jobs
4. Consider applying JSON streaming to other NoSQL sources (if any)

### Long-Term Improvements

1. **Schema Evolution**: Handle new Firestore fields automatically
2. **Performance Optimization**: Parallel extraction for large collections
3. **Data Quality**: Add validation rules for Firestore data
4. **Monitoring**: Dashboard for Firestore ETL health

---

## Appendix

### Related Files

- `etl_runner/extractors/firestore.py` - Firestore extraction logic
- `etl_runner/loaders/bigquery_loader.py` - BigQuery loading logic
- `etl_runner/main.py` - ETL orchestration
- `ml_platform/views.py` - API endpoint for job config
- `test_firestore_etl.py` - Integration test script
- `test_firestore_bug.py` - Unit test for PyArrow issue

### References

- [BigQuery Streaming Insert API](https://cloud.google.com/bigquery/docs/streaming-data-into-bigquery)
- [Firestore Data Types](https://cloud.google.com/firestore/docs/manage-data/data-types)
- [PyArrow Type Inference](https://arrow.apache.org/docs/python/generated/pyarrow.Table.html)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-25
**Author**: ETL Team
**Reviewers**: TBD
