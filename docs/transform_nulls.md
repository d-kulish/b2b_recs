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
    """Convert SparseTensor to dense if needed. Handles nullable BigQuery columns."""
    if isinstance(tensor, tf.SparseTensor):
        return tf.sparse.to_dense(tensor, default_value=default_value)
    return tensor
```

This function is placed between the module constants and `preprocessing_fn` definition in the generated output.

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

## 6. Verification Steps

1. **Regenerate transform code**: Trigger `generate_and_save()` for any feature config and inspect the `generated_transform_code` field — confirm `_densify` function and wrapped `inputs` calls appear
2. **Run tests**: `python -m pytest ml_platform/tests/ -x`
3. **Re-run experiment**: Re-run `quick-tests/122` — confirm the Transform node succeeds and the pipeline progresses to Trainer
