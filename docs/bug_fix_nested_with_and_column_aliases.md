# Bug Fix: Nested WITH Clauses & Column Aliases

**Date:** 2025-12-29
**Related Issue:** QuickTest #52 failed at BigQueryExampleGen

---

## Summary

This document describes two related bugs that were discovered and fixed:

1. **Nested WITH Clause Bug** - Invalid SQL syntax causing Dataflow pipeline failures
2. **Column Aliases Inconsistency** - Renamed columns not applied consistently throughout the system

---

## Bug 1: Nested WITH Clauses (Critical)

### Symptom

QuickTest #52 failed at the BigQueryExampleGen stage with Dataflow error after running for ~11 minutes. No detailed error message was available in the logs.

### Root Cause

The `generate_training_query()` function in `datasets/services.py` was wrapping the output of `generate_query()` in a CTE, creating invalid nested WITH clauses.

**Example of invalid SQL generated:**

```sql
WITH base_data AS (
  WITH filtered_data AS (...)  -- INVALID: nested WITH
  SELECT ... FROM filtered_data
),
holdout_filtered AS (
  WITH max_date_ref AS (...)   -- INVALID: nested WITH
  ...
)
SELECT * FROM holdout_filtered
```

BigQuery does not support nested WITH clauses. All CTEs must be defined at the top level.

### Files Changed

**`ml_platform/datasets/services.py`**

1. Added `return_structured=False` parameter to `generate_query()` method
   - When `True`, returns `{'ctes': [(name, body), ...], 'main_select': '...'}` instead of SQL string
   - Allows caller to merge CTEs at top level

2. Rewrote `generate_training_query()` to use structured approach:
   - Gets structured output from `generate_query()`
   - Merges all CTEs (from base query + holdout) at the same level
   - Builds single flat WITH clause

3. Renamed `_generate_holdout_cte()` to `_generate_holdout_ctes()`:
   - Now returns list of `(cte_name, cte_body)` tuples
   - Extracts `max_date_ref` as separate top-level CTE instead of nesting

**Result - Valid SQL:**

```sql
WITH
  filtered_data AS (...),
  base_data AS (SELECT ... FROM filtered_data),
  max_date_ref AS (SELECT MAX(...) FROM base_data),
  holdout_filtered AS (SELECT ... FROM base_data, max_date_ref)
SELECT * FROM holdout_filtered
```

---

## Bug 2: Column Aliases Not Applied Consistently

### Symptom

When a user renames columns in the Dataset configuration (e.g., `division_desc` → `category`), the renamed names were not used consistently:

- SQL output (without date filter): Used aliases ✓
- SQL output (with date filter): Used original names ✗
- Transform code generation: Used original names ✗
- Trainer code generation: Used original names ✗

This caused a mismatch: SQL would output `category` but transform code expected `inputs['division_desc']`.

### Data Model

The system stores both identifiers:

**Dataset.column_aliases:**
```json
{
  "tfrs_training_examples_division_desc": "category",
  "tfrs_training_examples_mge_cat_desc": "sub_category"
}
```

**FeatureConfig features:**
```json
{
  "column": "division_desc",      // Original name (for SQL source reference)
  "display_name": "category",     // Alias (for UI and generated code)
  "transforms": {...}
}
```

### Design Decision

- `column` field: Stores original BigQuery column name (used to reference source data)
- `display_name` field: Stores user's alias (used everywhere user sees the name)

The SQL should:
1. SELECT from original column names (BigQuery source)
2. Output columns with aliased names (AS clause)

Generated code should use `display_name` (alias) for `inputs['...']` since that's what the SQL outputs.

### Files Changed

**`ml_platform/datasets/services.py`**

1. Date filter path in `generate_query()` (lines 1188-1215):
   - Now applies `column_aliases` to filtered_data CTE output columns
   - Main SELECT when using filtered_data uses aliased names

**`ml_platform/configs/services.py`**

Changed all occurrences of:
```python
col = feature.get('column')
```
To:
```python
col = feature.get('display_name') or feature.get('column')
```

Affected methods:
- `get_feature_summary()`
- `_get_tensor_dimensions()`
- `_generate_header()` (TransformModuleGenerator)
- `_generate_header()` (TrainerModuleGenerator)
- `_generate_text_transform()` and related methods
- `_generate_numeric_transform()` and related methods
- `_generate_temporal_transform()` and related methods
- `_generate_cross_features()`
- `_generate_text_embedding_layers()`
- `_generate_numeric_embedding_layers()`
- `_generate_temporal_embedding_layers()`
- `_generate_feature_collection_code()`
- `_generate_serving_function()`
- Cross feature name extraction in multiple places

---

## What Was NOT Changed (Rolled Back)

Earlier in the debugging session, incorrect changes were made and subsequently rolled back:

1. ~~`experiments/services.py` - `_validate_column_names()` modification~~ - Rolled back
2. ~~`configs/api.py` - `get_dataset_columns()` returning aliased names as `name`~~ - Rolled back
3. ~~`configs/services.py` - SmartDefaultsService returning aliased names~~ - Rolled back

These changes were incorrect because they conflated the `column` field (which should remain the original name for SQL source references) with the display name.

---

## Tests Executed

### Unit Tests

```bash
./venv/bin/python manage.py test ml_platform.tests -v 1
```

**Result:** 39 tests passed, 1 skipped

### Specific Test Files

1. `ml_platform/tests/test_customer_filters.py` - 14 tests passed
   - Tests SQL generation with various filter types
   - Tests CTE structure
   - Tests WHERE clause generation

---

## Verification

After fixes, the data flow is now consistent:

| Component | Before Fix | After Fix |
|-----------|------------|-----------|
| SQL (date filter) | `SELECT division_desc` | `SELECT division_desc AS category` |
| SQL (no date filter) | `SELECT division_desc AS category` | `SELECT division_desc AS category` |
| Transform code | `inputs['division_desc']` | `inputs['category']` |
| Trainer code | `self.division_desc_embedding` | `self.category_embedding` |

---

## How to Test Manually

1. Create a Dataset with column aliases (rename columns in Step 3)
2. Create a FeatureConfig from that Dataset
3. Run a QuickTest with a date filter (rolling days)
4. Verify the experiment completes successfully
5. Check generated transform/trainer code uses aliased column names
