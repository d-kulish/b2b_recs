# SparseTensor Crash in TFX Transform — Nullable BigQuery Columns

**Date**: 2026-02-12
**Scope**: 1 file changed (`ml_platform/configs/services.py`), +18 / -5 lines

---

## 1. The Problem

The TFX Transform pipeline node crashes when a BigQuery source table contains NULL values. This happens when the dataset's SQL query uses LEFT JOINs — rows without a match in the joined table produce NULLs in the resulting columns. The error manifests during graph tracing of the generated `preprocessing_fn`, before any data is actually processed.

**Failing experiment**: `quick-tests/122`
**Configs**: Dataset `Lviv_retrival_v1`, Features `Lviv_features_retrival_v1`, Model `Lviv_retrival_v1`

### Error log (Vertex AI worker)

```
ERROR 2026-02-11T20:25:52.417Z [workerpool0-0]
File "/tmp/tmp9jpxz0d5/transform_module.py", line 121, in preprocessing_fn
    tf.strings.as_string(inputs['segment']),
...
TypeError: Expected binary or unicode string, got SparseTensor(
    indices=Tensor("inputs_2_copy:0", shape=(None, 2), dtype=int64),
    values=Tensor("inputs_3_copy:0", shape=(None,), dtype=string),
    dense_shape=Tensor("inputs_4_copy:0", shape=(2,), dtype=int64)
)
```

The crash occurs at `tft.get_analyze_input_columns()` → `impl_helper.trace_preprocessing_function()` → `preprocessing_fn(inputs_copy)`, during the initial graph tracing phase — not during actual data processing.

---

## 2. Analysis

### 2.1. How the Pipeline Gets Its Schema

The TFX pipeline is compiled with these components in sequence:

1. **BigQueryGen** — executes the SQL query, reads from BigQuery
2. **SchemaGen** — infers a schema from the data (column names, types, nullability)
3. **Transform** — applies the `preprocessing_fn` to transform raw features

SchemaGen inspects the actual data from BigQuery and produces a TensorFlow Metadata (TFMD) schema. For each column, it determines:
- The data type (`INT`, `FLOAT`, `BYTES`)
- The **presence** constraint (`REQUIRED` vs `NULLABLE`)

### 2.2. How NULLs Become SparseTensors

When a BigQuery column contains NULL values (common with LEFT JOINs), SchemaGen marks that column as `NULLABLE` in the schema. TFX Transform uses the schema to determine tensor representation:

| Schema presence | TFX tensor type | Python type in `preprocessing_fn` |
|---|---|---|
| `REQUIRED` | `FixedLenFeature` | `tf.Tensor` (dense) |
| `NULLABLE` | `VarLenFeature` | `tf.SparseTensor` |

This is by design — a nullable column has a variable number of values per row (0 or 1), so TFX represents it as a `VarLenFeature`, which materializes as a `tf.SparseTensor` at runtime.

### 2.3. The Generated Code Cannot Handle SparseTensors

The `PreprocessingFnGenerator` class (in `ml_platform/configs/services.py`, lines 840-1527) generates the `preprocessing_fn` Python module. It produces code that accesses input features with raw TensorFlow ops:

```python
# Text features (crosses) — generated code
tf.strings.as_string(inputs['segment'])

# Numeric features — generated code
tf.cast(inputs['price'], tf.float32)

# Temporal features — generated code
tf.cast(inputs['event_timestamp'], tf.int64)
```

All three of these operations (`tf.strings.as_string`, `tf.cast`) **require dense tensors**. When passed a `SparseTensor`, they raise `TypeError`. TFT-aware ops like `tft.compute_and_apply_vocabulary` handle SparseTensors internally, but the raw TF ops used for casting and cross-feature preparation do not.

### 2.4. Root Cause Summary

The pipeline generation assumed all BigQuery columns would be non-null (i.e., `REQUIRED` in the schema). When a LEFT JOIN query produces NULLs, SchemaGen correctly marks the column as `NULLABLE`, TFX materializes it as a `SparseTensor`, and the generated transform code crashes because it only handles dense tensors.

**Affected code paths in `PreprocessingFnGenerator`:**

| Method | Operation | Line (before fix) |
|---|---|---|
| `_generate_target_column_code` | `tf.cast(inputs[col], tf.float32)` | 1098, 1117 |
| `_generate_text_transforms` | `inputs[col]` passed to `tft.compute_and_apply_vocabulary` | 1213 |
| `_generate_numeric_transforms` | `tf.cast(inputs[col], tf.float32)` | 1265 |
| `_generate_temporal_transforms` | `tf.cast(inputs[col], tf.int64)` | 1338 |
| `_generate_cross_transforms` | `tf.cast(inputs[col], tf.float32)` and `tf.strings.as_string(inputs[col])` | 1458, 1466 |

Note: `tft.compute_and_apply_vocabulary` can handle SparseTensors, but wrapping it anyway ensures consistent behavior and makes the code defensive against future schema changes.

---

## 3. Evaluated Solutions

### Option A: Force `REQUIRED` in the Schema (Rejected)

Override SchemaGen output to mark all columns as `REQUIRED`. This would force TFX to treat NULLs as errors.

**Problem**: This doesn't solve the root cause — the data genuinely has NULLs. The pipeline would fail at data validation instead of transform.

### Option B: Fix NULLs in the SQL Query (Rejected)

Use `COALESCE()` or `IFNULL()` in the BigQuery SQL to replace NULLs with defaults.

**Problem**: The SQL is user-defined per dataset config. Forcing COALESCE on all columns would require parsing and rewriting arbitrary SQL, which is fragile and violates user expectations.

### Option C: Densify SparseTensors in `preprocessing_fn` (Selected)

Generate a helper function in the transform module that converts `SparseTensor` → dense `Tensor` with a type-appropriate default value. Wrap every `inputs[col]` access with this helper.

**Advantages**:
- Fixes the issue at the exact point of failure
- No changes needed to SQL, schema, or pipeline compilation
- Works for all existing and future feature configs
- The `isinstance` check evaluates at trace time (TFX traces `preprocessing_fn` once to build the graph), so there is zero runtime overhead — the correct branch is baked into the TF graph
- Training/serving consistency is preserved (see Section 5)

---

## 4. Fix Applied

### 4.1. New Helper Function

Added `_generate_helpers()` method to `PreprocessingFnGenerator` that emits a module-level `_densify` function into the generated transform code:

```python
def _densify(tensor, default_value):
    """Convert SparseTensor to dense if needed. Handles nullable BigQuery columns.

    VarLenFeature SparseTensors have shape (batch, ?). We force dense_shape
    to (batch, 1) and densify — matching the rank-2 shape that non-nullable
    FixedLenFeature columns produce.
    """
    if isinstance(tensor, tf.SparseTensor):
        return tf.sparse.to_dense(
            tf.SparseTensor(
                indices=tensor.indices,
                values=tensor.values,
                dense_shape=[tensor.dense_shape[0], 1]
            ),
            default_value=default_value
        )
    return tensor
```

This function is placed between the module constants and `preprocessing_fn` definition in the generated output.

The shape handling is critical — a plain `tf.sparse.to_dense()` preserves the SparseTensor's `dense_shape = (batch, ?)` with an unknown inner dimension, which TFX rejects. Forcing `dense_shape=[batch, 1]` produces `(batch, 1)` — matching the rank-2 shape that non-nullable `FixedLenFeature(shape=[1])` columns produce.

### 4.2. Wrapped Input Accesses

Every `inputs['{col}']` access in the generated code is now wrapped with `_densify()` using a type-appropriate default value:

| Feature type | Default value | Rationale |
|---|---|---|
| Text (`STRING`) | `b''` | Empty bytes = TF string representation. Hashes to a deterministic "unknown" bucket in vocabulary/cross features |
| Numeric (`INT64`/`FLOAT64`) | `0` | Zero integer, immediately cast to `float32` downstream |
| Temporal (`TIMESTAMP` → `int64`) | `0` | Unix epoch 0 — a recognizable sentinel value |
| Target (always numeric) | `0.0` | Float zero for ranking labels |

### 4.3. Example Generated Output (Before vs After)

**Before** (cross feature with text column):
```python
tf.strings.as_string(inputs['segment'])
```

**After**:
```python
tf.strings.as_string(_densify(inputs['segment'], b''))
```

**Before** (numeric feature):
```python
price_float = tf.cast(inputs['price'], tf.float32)
```

**After**:
```python
price_float = tf.cast(_densify(inputs['price'], 0), tf.float32)
```

### 4.4. Changes Summary

All changes in a single file — `ml_platform/configs/services.py`:

1. **New method**: `_generate_helpers()` — generates the `_densify` helper function
2. **`generate()`**: Added `helpers` to the section assembly between `constants` and `fn_start`
3. **`_generate_target_column_code()`**: Wrapped 2 `inputs[col]` accesses with `_densify(..., 0.0)`
4. **`_generate_text_transforms()`**: Wrapped 1 `inputs[col]` access with `_densify(..., b'')`
5. **`_generate_numeric_transforms()`**: Wrapped 1 `inputs[col]` access with `_densify(..., 0)`
6. **`_generate_temporal_transforms()`**: Wrapped 1 `inputs[col]` access with `_densify(..., 0)`
7. **`_generate_cross_transforms()`**: Wrapped 2 `inputs[col]` accesses — `_densify(..., 0)` for numeric/temporal, `_densify(..., b'')` for text

---

## 5. Training/Serving Consistency

A critical requirement is that inference-time behavior matches training-time behavior for the same input values.

**Training path** (TFX Transform on Vertex AI):
```
BigQuery NULL → SchemaGen NULLABLE → SparseTensor → _densify → dense b''/0
→ transform ops (vocabulary/normalize/bucketize) → model learns this as "unknown"
```

**Serving path** (Application sends request to deployed model):
```
App sends {'segment': ''} → dense tensor → TransformFeaturesLayer
→ same transform ops → same vocabulary/normalize/bucketize → same result
```

The key insight: at serving time, the application always sends concrete values (empty string `''` for missing text, `0` for missing numbers). `TransformFeaturesLayer` wraps them as dense tensors. The `_densify` function's `isinstance` check sees a dense tensor and passes it through unchanged. The downstream transform ops receive the same default value in both paths, producing identical outputs.

---

## 6. Custom Job Testing

The fix was validated using `scripts/test_services_transform.py`, which runs the Transform component in isolation on Vertex AI as a CustomJob, reusing BigQueryExampleGen and SchemaGen artifacts from the failed experiment `qt-122-20260211-200453`.

**Test config**: FeatureConfig ID 10 (`Lviv_features_retrival_v1`), 11 features, ~515k rows.

### 6.1. Job 1 — `NameError: name 'tft' is not defined`

**Job ID**: `1288393431776755712` — FAILED

The test runner script used `importlib.util.spec_from_file_location` to load the transform module. This does not register the module in `sys.modules`. Apache Beam's FnApiRunner serializes DoFns via `cloudpickle` — when the module is not registered, `preprocessing_fn` loses its module-level globals (`tf`, `tft`) on deserialization, causing `NameError`.

**Fix** (`scripts/test_services_transform.py`): Replaced `importlib` loading with standard `import transform_module` (after inserting the work directory into `sys.path`). Standard imports auto-register in `sys.modules`, preserving globals through cloudpickle serialization.

### 6.2. Job 2 — `ValueError: invalid shape (None, None) for FixedLenFeature`

**Job ID**: `8737347215447556096` — FAILED

The initial `_densify` used plain `tf.sparse.to_dense(tensor, default_value=default_value)`. This preserves the SparseTensor's original `dense_shape = (batch, ?)` — an unknown inner dimension. TFX Transform writes the output using `FixedLenFeature`, which requires a known shape. Shape `(None, None)` is rejected.

**Fix** (`ml_platform/configs/services.py`): Force `dense_shape` to `[tensor.dense_shape[0], 1]` before densifying. This produces `(batch, 1)` — a known inner dimension that TFX accepts.

### 6.3. Job 3 — `ValueError: Shapes must be equal rank, but are 1 and 2`

**Job ID**: `2792595707318501376` — FAILED

After forcing `dense_shape=[batch, 1]`, the code also applied `tf.squeeze(dense, axis=1)` to produce `(batch,)` — rank 1. But non-nullable columns from the schema have shape `(batch, 1)` — rank 2. In cross features, `tf.strings.join` received mismatched ranks:

```
input shapes: [?], [], [?,1]
               ↑              ↑
         segment (squeezed)   cust_value (non-nullable, rank 2)
```

Only `segment` was nullable (`no shape → varlen_sparse_tensor`); all other features had `shape dim { size: 1 } → DenseTensor`.

**Fix** (`ml_platform/configs/services.py`): Removed `tf.squeeze(dense, axis=1)`. Output stays `(batch, 1)` — matching the rank-2 shape that non-nullable `FixedLenFeature(shape=[1])` columns produce.

### 6.4. Job 4 — SUCCESS

**Job ID**: `4206725990312837120` — `JOB_STATE_SUCCEEDED`

Transform completed on all 515,210 elements across 558 batches. Generated artifacts:
- `transform_fn/saved_model.pb` — the serialized transform graph
- `transform_fn/assets/` — 5 vocabulary files (category, sub_category, segment, product_id, customer_id)
- `transform_fn/variables/` — model variables
- `transformed_metadata/schema.pbtxt` — output schema

Schema confirmed: `segment` loaded as `varlen_sparse_tensor` (nullable), all 10 other features loaded as `DenseTensor` with `shape dim { size: 1 }` (non-nullable). The `_densify` function correctly converted `segment`'s SparseTensor to dense `(batch, 1)`, matching the other features.

---

## 7. Pipeline Integration

No changes needed to experiment compilation. The pipeline (`ml_platform/experiments/services.py`) regenerates the transform code fresh at submission time:

```
ExperimentService._submit_pipeline()
  → PreprocessingFnGenerator(feature_config).generate()   # fresh generation with _densify
  → upload to GCS as transform_module.py
  → pass GCS path to TFX Transform component
```

Any new experiment run automatically gets the fix.

---

## 8. Files Changed

| File | Change |
|---|---|
| `ml_platform/configs/services.py` | Added `_generate_helpers()` method, inserted into `generate()` assembly, wrapped 7 `inputs[col]` accesses with `_densify()` |
| `scripts/test_services_transform.py` | Fixed module import (standard import instead of `importlib.util`) |
| `docs/transform_nulls.md` | This document |

---

## 9. Follow-Up: Trainer Serve Function Shape Mismatch (qt-126)

**Date**: 2026-02-12

### 9.1. The Problem

After the `_densify` fix resolved the Transform step crash, experiment `qt-126` failed later in the pipeline at `tf.saved_model.save()` during the Trainer step. The root cause is the same nullable column (`segment`), but the failure point is different.

SchemaGen marks `segment` as `NULLABLE` → `VarLenFeature` (SparseTensor). The Trainer's generated serve function provides all inputs as dense tensors via `tf.expand_dims()`. TFT v2's `_apply_v2_transform_model` cannot convert a dense tensor into the SparseTensor that the transform graph expects, producing a shape mismatch: `(None, 2) vs (None, 1)`.

### 9.2. Why `_densify` Alone Is Insufficient

The `_densify` fix handles the Transform component correctly — it converts SparseTensors to dense inside `preprocessing_fn`. However, the saved transform graph still has SparseTensor *input signatures* for nullable columns. At serving time, the Trainer's serve function feeds dense tensors into this graph, and TFT v2 cannot reconcile the mismatch.

The real fix is to prevent NULLs from ever reaching SchemaGen, so all columns are marked `REQUIRED` (FixedLenFeature/dense) from the start. This makes the entire pipeline — SchemaGen, Transform, Trainer, and serving — work with consistent dense tensors.

### 9.3. Fix Applied — COALESCE in Generated SQL

Modified `BigQueryService.generate_query()` in `ml_platform/datasets/services.py` to wrap columns from LEFT-JOINed tables with `COALESCE()` when `for_tfx=True`.

**Changes:**

1. **`left_join_tables` set**: After the `column_types` dict is built, identifies which table aliases come from LEFT JOINs by inspecting `dataset.join_config`. The default join type is `LEFT`, matching existing behavior.

2. **`_coalesce_expr()` helper**: Wraps a column reference with `COALESCE(col, default)` if the column's table is in `left_join_tables`. Type-appropriate defaults:

   | BigQuery type | Default | Rationale |
   |---|---|---|
   | `STRING`, `BYTES` | `''` | Empty string — hashes to a deterministic "unknown" bucket |
   | `INT64`, `INTEGER` | `0` | Zero integer |
   | `FLOAT64`, `FLOAT`, `NUMERIC`, `BIGNUMERIC` | `0.0` | Zero float |
   | `BOOLEAN`, `BOOL` | `FALSE` | Boolean false |
   | `TIMESTAMP`, `DATE`, `DATETIME` | `COALESCE(UNIX_SECONDS(...), 0)` | Wrapped at the UNIX_SECONDS level |

3. **Applied in both SELECT loops**: The main SELECT loop and the `filtered_data` CTE SELECT loop both use `_coalesce_expr()` / COALESCE-wrapped UNIX_SECONDS to build column expressions.

**Example generated SQL (before):**
```sql
SELECT
  transactions.`customer_id` AS `customer_id`,
  customers.`segment` AS `segment`
FROM `project.dataset.transactions` AS transactions
LEFT JOIN `project.dataset.customers` AS customers ON transactions.customer_id = customers.customer_id
```

**Example generated SQL (after, with `for_tfx=True`):**
```sql
SELECT
  transactions.`customer_id` AS `customer_id`,
  COALESCE(customers.`segment`, '') AS `segment`
FROM `project.dataset.transactions` AS transactions
LEFT JOIN `project.dataset.customers` AS customers ON transactions.customer_id = customers.customer_id
```

### 9.4. Interaction with `_densify`

The `_densify` helper in the generated `preprocessing_fn` remains as defense-in-depth. With COALESCE in place, SchemaGen marks all columns as `REQUIRED`, so `_densify`'s `isinstance(tensor, tf.SparseTensor)` check is always `False` — the function becomes a no-op with zero overhead. If a future query path somehow produces NULLs (e.g., a non-LEFT-JOIN source of nullability), `_densify` still provides a safety net.

### 9.5. Downstream Inheritance

- `generate_training_query()` calls `generate_query(for_tfx=True)` — inherits the fix
- `generate_split_queries()` wraps the base query — inherits the fix
- Non-TFX paths (`for_tfx=False`) are unaffected — no COALESCE wrapping

### 9.6. Files Changed

| File | Change |
|---|---|
| `ml_platform/datasets/services.py` | Added `left_join_tables` set, `_coalesce_expr()` helper, COALESCE wrapping in both SELECT loops of `generate_query()` |
| `docs/transform_nulls.md` | Added Section 9 (this section) |

---

## 10. COALESCE Fix Fails — Intrinsic NULLs in Source Data (qt-127)

**Date**: 2026-02-12

### 10.1. The Problem

Experiment `qt-127` (`quicktest-qt-127-20260212-171803-20260212172027`) fails with the identical error as qt-126: shape mismatch at `tf.saved_model.save()` during the Trainer step.

**Pipeline**: `quicktest-qt-127-20260212-171803-20260212172027`
**Experiment**: `quick-tests/127`
**Configs**: Same as qt-122/126 — Dataset `Lviv_retrival_v1`, Features `Lviv_features_retrival_v1`, Model `Lviv_retrival_v1`

### 10.2. Error Logs (Vertex AI worker)

Training completes successfully — metrics are saved to GCS at `18:32:54 UTC`. The crash occurs immediately after, during model export:

```
File "/tmp/tmpqve6fosu/trainer_module.py", line 1521, in run_fn
    tf.saved_model.save(
...
File "/tmp/tmpqve6fosu/trainer_module.py", line 600, in serve
    transformed_features = self.tft_layer(raw_features)
...
File "/opt/conda/lib/python3.10/site-packages/tensorflow_transform/saved/saved_transform_io_v2.py", line 348, in _apply_v2_transform_model
    raise ValueError('{}: {}'.format(input_t, e))

ValueError: Tensor("ExpandDims_3:0", shape=(None, 2) and (None, 1) are incompatible
```

Call arguments received by `TransformFeaturesLayer`:
```
inputs={
    'customer_id': 'tf.Tensor(shape=(None, 1), dtype=int64)',
    'date':        'tf.Tensor(shape=(None, 1), dtype=int64)',
    'cust_value':  'tf.Tensor(shape=(None, 1), dtype=float32)',
    'segment':     'tf.Tensor(shape=(None, 1), dtype=string)'
}
```

`ExpandDims_3` is the 4th input (0-indexed) — `segment`. The transform graph expects `(None, 2)` (SparseTensor indices for a NULLABLE VarLenFeature), but the serve function provides `(None, 1)` (dense tensor from `tf.expand_dims(segment, -1)`).

The error mechanism is identical to qt-126 (Section 9.1): SchemaGen marks `segment` as NULLABLE → SparseTensor input in transform graph → serve function provides dense tensor → shape mismatch.

### 10.3. Why the COALESCE Fix (Section 9.3) Did Not Apply

The COALESCE fix targets columns from LEFT-JOINed secondary tables. The dataset `Lviv_retrival_v1` has **no secondary tables and no joins**:

```
PRIMARY TABLE:    raw_data.tfrs_training_examples  (a BigQuery VIEW)
SECONDARY TABLES: []
JOIN CONFIG:      {}
```

All 11 columns come from a single denormalized view. The COALESCE logic in `generate_query()` builds `left_join_tables` from `dataset.secondary_tables`:

```python
left_join_tables = set()
if for_tfx:
    for sec_table in (dataset.secondary_tables or []):  # ← empty list, loop never executes
        ...
```

Result: `left_join_tables` is empty. The `_coalesce_expr()` guard `if table_alias not in left_join_tables: return raw` fires for every column. No column gets COALESCE wrapping. The generated SQL confirms:

```sql
tfrs_training_examples.`segment` AS `segment`   -- raw, no COALESCE
```

### 10.4. Source of NULLs

The NULLs are intrinsic to the source data in the BigQuery view `raw_data.tfrs_training_examples`. The dataset's `summary_snapshot.column_stats` shows:

| Column | Type | Null Count | Null % |
|--------|------|-----------|--------|
| `segment` | STRING | 242,626 | 11.92% |
| All other 10 columns | various | 0 | 0% |

11.92% of rows have `segment = NULL` — customers without an assigned segment. These NULLs exist in the source view, not from any JOIN operation. The COALESCE fix (Section 9.3) was built on a false assumption: that NULLs originate from LEFT JOIN mismatches. This dataset has no joins at all.

### 10.5. Timeline

| Time (UTC) | Event |
|------------|-------|
| 17:14:19 | Commit `a207a34` — COALESCE fix committed |
| 17:18:03 | `_submit_pipeline()` generates SQL for qt-127 (`run_id` timestamp via `datetime.utcnow()`) |
| 17:20:27 | Vertex AI pipeline starts |
| 18:32:54 | Training completes, `tf.saved_model.save()` crashes |

The COALESCE code was active when qt-127 was submitted (3m44s after commit, Django auto-reload via `runserver`). The fix was present but irrelevant — it only inspects `secondary_tables`, which is empty.

### 10.6. Conclusion

The fix must ensure **no NULLs reach TFRecords regardless of source** — whether from LEFT JOIN mismatches, intrinsic source data NULLs, or any other origin. The COALESCE wrapping in `generate_query()` must apply to **all columns** when `for_tfx=True`, not just columns from LEFT-JOINed tables. Default fill values: `'unknown'` for strings, `0` for integers, `0.0` for floats.

---

## 11. COALESCE All Nullable Columns via `column_stats` (qt-127 resolution)

**Date**: 2026-02-12

### 11.1. Problem

Experiments qt-122 through qt-127 fail with a shape mismatch at `tf.saved_model.save()` during the Trainer step. The `segment` column has 11.92% intrinsic NULLs (242,626 rows — customers without an assigned segment) in the BigQuery view `raw_data.tfrs_training_examples`. These NULLs pass through to SchemaGen, which marks `segment` as `NULLABLE` (`VarLenFeature` / SparseTensor). The Trainer's serve function provides all inputs as dense tensors via `tf.expand_dims()`, but the transform graph expects a SparseTensor for `segment`, producing:

```
ValueError: Tensor("ExpandDims_3:0", shape=(None, 2) and (None, 1) are incompatible
```

### 11.2. Discovered Root Cause

The COALESCE fix from Section 9.3 only targets columns from LEFT-JOINed secondary tables. It builds `left_join_tables` from `dataset.secondary_tables`:

```python
left_join_tables = set()
for sec_table in (dataset.secondary_tables or []):  # empty list → loop never runs
    ...
```

The dataset `Lviv_retrival_v1` has **no secondary tables and no joins** — it reads from a single denormalized view. `left_join_tables` is always empty, so `_coalesce_expr()` returns every column raw (no COALESCE wrapping). The NULLs are intrinsic to the source data, not from any JOIN operation.

The underlying assumption was wrong: NULLs only come from LEFT JOIN mismatches. In reality, NULLs can exist in the source data itself.

### 11.3. Applied Fix

Modified `BigQueryService.generate_query()` in `ml_platform/datasets/services.py` to use the existing `column_stats` data (already stored in `dataset.summary_snapshot`) to detect ANY column with NULLs and apply COALESCE when `for_tfx=True`.

**1. Build `nullable_columns` set** — alongside the existing `column_types` dict, from `column_stats` entries where `null_count > 0`:

```python
nullable_columns = set()
if for_tfx and dataset.summary_snapshot:
    column_stats = dataset.summary_snapshot.get('column_stats', {})
    for col_key, stats in column_stats.items():
        if stats.get('null_count', 0) > 0:
            nullable_columns.add(col_key)
```

**2. Extend `_coalesce_expr()` guard** — apply COALESCE when a column is in a LEFT-JOINed table OR has intrinsic NULLs:

```python
# Before
if table_alias not in left_join_tables:
    return raw
# After
col_key = f"{table_alias}.{col}"
if table_alias not in left_join_tables and col_key not in nullable_columns:
    return raw
```

**3. Extend TIMESTAMP COALESCE guards** — same change in both the main SELECT loop and the `filtered_data` CTE loop:

```python
# Before
if table_alias in left_join_tables:
# After
if table_alias in left_join_tables or col_key in nullable_columns:
```

The fix is additive: `left_join_tables` still handles the JOIN-based case (even for columns not yet in `column_stats`), while `nullable_columns` catches intrinsic NULLs that `left_join_tables` misses.

### 11.4. Expected Behavior

With this fix, `generate_query(for_tfx=True)` produces COALESCE-wrapped SQL for any column that has NULLs in its source data:

```sql
-- Before (no COALESCE — NULLs pass through to TFRecords)
SELECT
  tfrs_training_examples.`segment` AS `segment`

-- After (COALESCE applied based on column_stats null_count)
SELECT
  COALESCE(tfrs_training_examples.`segment`, '') AS `segment`
```

The downstream pipeline chain becomes:

1. **BigQueryExampleGen** reads the COALESCE-wrapped query — no NULLs in output
2. **SchemaGen** marks all columns as `REQUIRED` (`FixedLenFeature` / dense tensors)
3. **Transform** receives dense tensors — `_densify` is a no-op (defense-in-depth preserved)
4. **Trainer** serve function provides dense `(batch, 1)` tensors — matches transform graph input signatures
5. **`tf.saved_model.save()`** succeeds — no shape mismatch

Non-TFX paths (`for_tfx=False`) are unaffected — no COALESCE wrapping is applied.

### 11.5. Files Changed

| File | Change |
|---|---|
| `ml_platform/datasets/services.py` | Added `nullable_columns` set from `column_stats`, extended `_coalesce_expr()` guard and both TIMESTAMP COALESCE guards to check `nullable_columns` |
| `docs/transform_nulls.md` | Added Section 11 (this section) |
