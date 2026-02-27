# Bug: ScaNN Serving Model — Product ID / Index Mismatch

**Date Identified:** 2026-02-27
**Status:** Open
**Severity:** High (wrong recommendations returned at inference time)
**Affected Path:** ScaNN serving only (`RETRIEVAL_ALGORITHM = 'scann'`)
**Not Affected:** Brute-force retrieval, Multitask (both use `tf.nn.top_k` positional indices)

---

## Summary

The ScaNN serving model returns **wrong product recommendations** because ScaNN index identifiers (vocab indices) are used as positional indices into the `serving_product_ids` array via `tf.gather`. These two index spaces are not aligned.

---

## Root Cause

In `ml_platform/configs/services.py`, the data flow through the ScaNN path is:

### 1. Candidate Embedding Precomputation (line ~4468)

```python
product_ids, product_embeddings = _precompute_candidate_embeddings(model, candidates_dataset)
```

Returns `product_ids` as **vocab indices** in encounter order, e.g. `[3, 7, 0, 12, ...]` (858 items).

### 2. Original Product ID Loading (line ~4477)

```python
original_product_ids = _load_original_product_ids(tf_transform_output, ...)
```

Returns the full TFT vocabulary in **vocab order**, e.g. `["P0", "P1", "P2", "P3", ...]` (904 items).

### 3. Serving Product ID Mapping (line ~4483)

```python
serving_product_ids = [original_product_ids[vid] for vid in product_ids]
```

Maps vocab indices to actual product IDs in **encounter order**: `["P3", "P7", "P0", "P12", ...]` (858 items). This is correct — each position aligns with the corresponding embedding.

### 4. ScaNN Index Build (line ~4492) — THE PROBLEM STARTS HERE

```python
scann_index = _build_scann_index(model.query_tower, product_ids, product_embeddings)
```

Inside `_build_scann_index` (line ~3634):

```python
candidates_dataset = tf.data.Dataset.from_tensor_slices((
    tf.constant(product_ids),   # vocab indices [3, 7, 0, 12, ...] used as IDENTIFIERS
    product_embeddings
)).batch(100)
scann_index.index_from_dataset(candidates_dataset)
```

When `index_from_dataset` receives `(identifier, embedding)` tuples, calling the index later returns the **identifier values** — not positional indices.

### 5. ScaNN Serving Model (line ~3553-3556) — THE BUG

```python
top_scores, top_vocab_indices = self.scann_index(transformed_features)
recommended_products = tf.gather(self.original_product_ids, top_vocab_indices)
```

`top_vocab_indices` contains identifier values like `[7, 3, 12, ...]` (vocab indices). But `self.original_product_ids` is `serving_product_ids` — a list in encounter order. `tf.gather(serving_product_ids, 7)` returns the **8th encountered product**, NOT the product with vocab index 7.

### Visual Example

```
product_ids (vocab indices, encounter order):  [3, 7, 0, 12, ...]
serving_product_ids (real IDs, encounter order): ["P3", "P7", "P0", "P12", ...]

ScaNN returns identifier 7 (meaning vocab index 7 = "P7")
tf.gather(serving_product_ids, 7) → serving_product_ids[7] → "P<whatever is at position 7>"
                                                               ≠ "P7" (unless by coincidence)
```

---

## Impact

- ScaNN serving models return **incorrect product recommendations**
- The recommendations are essentially scrambled — the scores are correct but mapped to wrong products
- Brute-force and multitask paths are NOT affected (they use `tf.nn.top_k` which returns positional indices)
- The bug only manifests when a model is deployed with `RETRIEVAL_ALGORITHM = 'scann'`

---

## Suggested Fix

**Option A — Pass `serving_product_ids` as ScaNN identifiers (recommended):**

ScaNN will return actual product ID strings directly, eliminating the need for `tf.gather`.

1. Change line ~4492:
```python
# Before:
scann_index = _build_scann_index(model.query_tower, product_ids, product_embeddings)

# After:
scann_index = _build_scann_index(model.query_tower, serving_product_ids, product_embeddings)
```

2. Simplify `ScaNNServingModel.serve()` (line ~3553-3556):
```python
# Before:
top_scores, top_vocab_indices = self.scann_index(transformed_features)
recommended_products = tf.gather(self.original_product_ids, top_vocab_indices)

# After:
top_scores, top_product_ids = self.scann_index(transformed_features)
# ScaNN returns the actual product IDs directly — no tf.gather needed
```

And return `top_product_ids` directly in the response dict.

3. The `original_product_ids` variable in `ScaNNServingModel.__init__` can be removed since it's no longer needed.

**Option B — Build ScaNN index without identifiers (embeddings only):**

ScaNN would return positional indices instead, which correctly align with `serving_product_ids`.

```python
# In _build_scann_index: only pass embeddings
candidates_dataset = tf.data.Dataset.from_tensor_slices(product_embeddings).batch(100)
scann_index.index_from_dataset(candidates_dataset)
```

Then `tf.gather(serving_product_ids, positional_index)` works correctly.

---

## Related Past Fixes

| Date | Bug | Fix |
|------|-----|-----|
| 2026-02-02 | Serving model returned vocab indices instead of product IDs | Added `_load_original_product_ids()` for all paths |
| 2026-02-07 | `_load_original_product_ids` definition missing from brute-force/multitask code gen | Added function to all code generation paths |
| 2026-02-22 | `product_ids` / `embeddings` misalignment in serving model | Added `serving_product_ids = [original_product_ids[vid] for vid in product_ids]` mapping |

The current bug is a residual from the 2026-02-22 fix: the mapping was applied correctly for brute-force (which passes `serving_product_ids` to `ServingModel`) but the ScaNN path still passes raw `product_ids` (vocab indices) to `_build_scann_index`.
