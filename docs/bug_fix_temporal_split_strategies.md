# Bug Fix: Temporal Split Strategies Using CURRENT_DATE()

**Date:** 2025-12-18
**File:** `ml_platform/datasets/services.py`
**Method:** `_generate_holdout_cte()` (lines 1265-1341)

## Problem Description

Experiments using `time_holdout` or `strict_time` split strategies failed with a `KeyError: 'customer_id'` error in the TFX Transform stage when the dataset contained historical data.

### Error Traceback

```
tensorflow.python.framework.errors_impl.InvalidArgumentError: {{function_node __inference_preprocessing_fn_169}}
KeyError: 'customer_id'
```

### Affected Configurations

- Split strategy: `strict_time` or `time_holdout`
- Dataset: Any dataset with historical data (dates not near current date)

## Root Cause Analysis

### Investigation Steps

1. **Initial hypothesis (incorrect):** Column name mismatch between Dataset and FeatureConfig
   - Verified `customer_id` was correctly configured in both Dataset and FeatureConfig
   - SQL generation was correct with `customer_id` in output

2. **Key diagnostic:** Examined TFRecords created by BigQueryExampleGen
   - Failed experiment (QuickTest 35): **20 bytes** (0 bytes uncompressed) - EMPTY
   - Successful experiment (QuickTest 33): **288KB** - contained data

3. **Root cause identified:** The `_generate_holdout_cte()` method used `CURRENT_DATE()` as the reference point for date calculations

### The Bug

The temporal split strategies calculated date windows relative to `CURRENT_DATE()`:

```python
# time_holdout - BUGGY CODE
WHERE date_column < UNIX_SECONDS(TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {holdout_days} DAY)))

# strict_time - BUGGY CODE
WHERE date_column >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {total_window} DAY)))
  AND date_column < UNIX_SECONDS(TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {test_days} DAY)))
```

### Why It Failed

For a dataset with data from **2024-01-01 to 2024-04-28**:

- `strict_time` with `train_days=60, val_days=7, test_days=2` calculated:
  - Window start: `CURRENT_DATE() - 69 days` = **2025-10-10**
  - Window end: `CURRENT_DATE() - 2 days` = **2025-12-16**

- **Result:** Zero overlap between data dates (ending 2024-04-28) and calculated window (2025-10-10 to 2025-12-16)

### Failure Cascade

```
0 rows returned by BigQuery
    ↓
Empty TFRecords created by BigQueryExampleGen
    ↓
Empty schema inferred by StatisticsGen/SchemaGen
    ↓
Transform stage fails with KeyError (no columns in schema)
```

## Solution

Modified `_generate_holdout_cte()` to use the MAX date from the dataset instead of `CURRENT_DATE()`.

### Fixed Code

Both strategies now use a CTE to find the MAX date once, then filter relative to it:

```python
# time_holdout - FIXED
WITH max_date_ref AS (
    SELECT DATE(TIMESTAMP_SECONDS(MAX({date_column}))) AS ref_date
    FROM {source_table}
)
SELECT base.*
FROM {source_table} base, max_date_ref
WHERE base.{date_column} < UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {holdout_days} DAY)))

# strict_time - FIXED
WITH max_date_ref AS (
    SELECT DATE(TIMESTAMP_SECONDS(MAX({date_column}))) AS ref_date
    FROM {source_table}
)
SELECT base.*
FROM {source_table} base, max_date_ref
WHERE base.{date_column} >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {total_window} DAY)))
  AND base.{date_column} < UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {test_days} DAY)))
```

### Timeline Illustration

```
Before (BUGGY):
Data:     [2024-01-01 -------- 2024-04-28]
Window:                                      [2025-10-10 -------- 2025-12-16]
Result:   NO OVERLAP → 0 rows

After (FIXED):
Data:     [2024-01-01 -------- 2024-04-28]  ← MAX date = 2024-04-28
Window:        [2024-02-19 ---- 2024-04-26] ← calculated from MAX date
Result:   OVERLAP → 4202 rows
```

## Verification

### Before Fix
```
Row count with strict_time: 0
TFRecord size: 20 bytes (empty)
Result: KeyError in Transform stage
```

### After Fix
```
Row count with strict_time: 4202
TFRecord size: Expected ~288KB (with data)
Result: Pipeline succeeds
```

## Files Modified

| File | Lines | Change |
|------|-------|--------|
| `ml_platform/datasets/services.py` | 1275-1302 | Updated docstring |
| `ml_platform/datasets/services.py` | 1303-1313 | Fixed `time_holdout` strategy |
| `ml_platform/datasets/services.py` | 1315-1337 | Fixed `strict_time` strategy |

## Lessons Learned

1. **Temporal split strategies should never use `CURRENT_DATE()`** - they should always be relative to the actual data in the dataset
2. **Empty TFRecords are a silent failure** - they don't cause immediate errors but lead to confusing downstream failures
3. **When debugging TFX pipelines**, check the TFRecords size/content early in the investigation
