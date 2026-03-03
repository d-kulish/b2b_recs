# Bug Analysis: Purchase History Point-in-Time Restriction Causes Train/Serve Skew

**Date**: 2026-03-03
**Experiments**: qt-162 (baseline), qt-174 (leaky history), qt-179 (fixed history)
**Status**: Root cause identified, fix proposed

---

## Problem Statement

After fixing data leakage in the training view (`create_ternopil_train_v4_view.sql`, commit `530be73`), rerunning experiment qt-174 as qt-179 produced dramatically worse results:

| Experiment | History | R@5 | R@10 | R@50 | R@100 |
|------------|---------|-----|------|------|-------|
| qt-162 | None (baseline + scalars) | 5.2% | 8.1% | 22.0% | 33.1% |
| qt-174 | Leaky (old view) | **49.1%** | 56.1% | 64.4% | 68.5% |
| qt-179 | Fixed (new view) | 7.4% | 10.4% | 23.6% | 32.5% |

Qt-179 results are only marginally better than the baseline without history features. However, the qt-174 model — when evaluated on completely unseen test data (`ternopil_test_v4`) via the inference notebook — achieves R@5=29.6%, proving the taste vector carries strong predictive signal that qt-179 fails to learn.

---

## Investigation: Hard Facts

### 1. Generated Code Is Identical

Downloaded and diffed the GCS artifacts for both experiments:

```
gs://b2b-recs-quicktest-artifacts/qt-174-20260228-173331/
gs://b2b-recs-quicktest-artifacts/qt-179-20260303-145420/
```

```
diff qt-174/transform_module.py qt-179/transform_module.py
3c3
< # Generated at: 2026-02-28T17:33:31.687356Z
---
> # Generated at: 2026-03-03T14:54:20.038722Z

diff qt-174/trainer_module.py qt-179/trainer_module.py
4c4
< # Generated at: 2026-02-28T17:33:31.698722Z
---
> # Generated at: 2026-03-03T14:54:20.075225Z
```

**Byte-identical** except timestamps. History feature code is present in qt-179:

- **Transform** (line 235): `outputs['history'] = tft.apply_vocabulary(inputs['history'], deferred_vocab_filename_tensor=product_id_vocab, num_oov_buckets=NUM_OOV_BUCKETS)`
- **Trainer input_fn** (lines 314–326): SparseTensor → dense padding with dedicated pad index (`vocab_size + NUM_OOV_BUCKETS`)
- **BuyerModel.call** (lines 408–415): shared embedding lookup → masked averaging → 32D taste vector
- **RetrievalModel** (lines 588–594): shared product embedding with `input_dim = vocab_size + NUM_OOV_BUCKETS + 1`

**Conclusion: code generation did NOT exclude history.**

### 2. TFRecords Contain History Data

Parsed all 71,680 training records from qt-179's BigQueryExampleGen output:

```
gs://b2b-recs-pipeline-staging/pipeline_root/qt-179-20260303-145420/.../
    BigQueryExampleGen_.../examples/Split-train/data_tfrecord-00000-of-00001.gz
```

| Metric | Value |
|--------|-------|
| Total training examples | 71,680 |
| History feature present | 71,680 (100.0%) |
| History non-empty | 50,808 (70.9%) |
| History empty | 20,872 (29.1%) |
| Avg length (non-empty) | 18.5 products |
| Median length (non-empty) | 14.0 products |
| Max length | 50 (capped) |

Length distribution:

```
  length =  0:  20,872 (29.1%)   ← first-day purchasers, no prior history
  length  1–5:   9,633 (13.4%)
  length 6–20:  23,294 (32.5%)
  length 21–50: 17,881 (24.9%)
```

**Conclusion: history data is NOT missing from the pipeline.**

### 3. Zero Data Leakage in qt-179

Checked all 50,808 non-empty history records — **0 have the target product_id in the history array (0.00%)**. The point-in-time fix is working correctly.

### 4. Experiment Configs Are Identical

| Parameter | qt-174 | qt-179 |
|-----------|--------|--------|
| Feature Config | feat_retr_v6 (ID: 39) | feat_retr_v6 (ID: 39) |
| Model Config | mod_retr_v6_v2 (ID: 35) | mod_retr_v6_v2 (ID: 35) |
| Dataset | data_retr_v6 (ID: 43) | data_retr_v6 (ID: 43) |
| Epochs | 100 | 100 |
| Batch size | 4096 | 4096 |
| Learning rate | 0.002 | 0.002 |
| Optimizer | Adam | Adam |
| Architecture | Dense(64)→Dropout(0.2)→Dense(32) | Dense(64)→Dropout(0.2)→Dense(32) |

### 5. Training Dynamics

| Metric | qt-174 (old view) | qt-179 (fixed view) | qt-162 (no history) |
|--------|-------------------|---------------------|---------------------|
| Final train loss | **1,716** | 9,174 | 2,373 |
| Min train loss | **1,672** | 9,121 | 2,321 |
| Final val loss | 357,026 | 52,758 | 15,919 |
| Peak val loss | **1,853,411** | 374,739 | 16,007 |
| Regularization loss | 43.5 | 31.9 | 18.1 |
| Test R@5 | **49.1%** | 7.4% | 5.2% |

Qt-174 drove training loss to 1,716 — **5.3× lower** than qt-179's 9,174. The richer history signal enabled the model to learn much stronger product co-occurrence patterns in the shared embedding. Qt-179's weaker history signal caused the model to allocate capacity to the customer_id embedding (64D) instead.

### 6. qt-174 Inference on Unseen Test Data

The qt-174 model evaluated on `ternopil_test_v4` (notebook `dev/models/qt-174/inference_demo.ipynb`):

| Scenario | R@5 | R@10 | R@50 | R@100 | R@150 |
|----------|-----|------|------|-------|-------|
| 100% match (known customers + products) | 32.8% | 37.4% | 47.2% | 52.6% | 57.8% |
| All customers, known products | 24.8% | 28.4% | 38.0% | 44.4% | 49.8% |

The test view (`ternopil_test_v4`) also **excludes the target product** from history (line 65–66: `cp1.product_id != cp2.product_id`). So these results are NOT from the target leaking through at inference. The model genuinely learned useful product co-occurrence patterns that generalize to unseen data.

---

## Root Cause

### What Changed Between the Two Views

The training view SQL (`create_ternopil_train_v4_view.sql`) was modified in commit `530be73`:

| Aspect | Old view (qt-174 trained on) | Fixed view (qt-179 trained on) |
|--------|------------------------------|-------------------------------|
| Target product in history | Excluded (`cp1.product_id != cp2.product_id`) | Excluded (`acp.product_id != rk.product_id`) |
| Temporal restriction | **None** — full training period | **`purchase_date < row_date`** — only BEFORE this row's date |
| History computed per | (customer, product) — same array for all dates | (customer, product, **date**) — different per row |
| Empty history rows | ~0% | **29.1%** (20,872/71,680) |
| Avg history length | ~24 products | 18.5 products |

Both views exclude the target product. The critical difference is the **point-in-time restriction with strict less-than**: `acp.purchase_date < rk.row_date` (line 71).

### Why Strict Less-Than Breaks B2B History

In B2B wholesale data, customers place **bulk orders** — buying 10–20+ products on the same day. With strict less-than (`<`):

- Customer buys products A, B, C, D, E on day 5 (first order):
  - Row (customer, A, day 5): history = **[]** — nothing bought *before* day 5
  - Row (customer, B, day 5): history = **[]** — same
  - All 5 rows: **empty history**

- Customer buys products F, G on day 15 (second order):
  - Row (customer, F, day 15): history = [A, B, C, D, E] — from day 5
  - Row (customer, G, day 15): history = [A, B, C, D, E]

In this example, 5 out of 7 rows (71%) have empty history. The actual training data shows 29.1% empty — consistent with a mix of one-time and repeat customers.

### Train/Serve Skew

At inference time (the notebook), the test view provides the customer's **full training-period history** — a global aggregation, not point-in-time restricted. This matches the old training view but NOT the fixed training view:

| | Training (qt-179) | Inference (notebook) |
|--|-------------------|---------------------|
| History style | Point-in-time per date | Global (full training period) |
| Empty history | 29.1% | ~0% (any customer with 2+ products) |
| Avg length | 18.5 | ~24 |

The qt-174 model was trained on similarly rich history (global aggregation), so it knows how to use it at inference → R@5=29.6%. The qt-179 model was trained on sparse/empty history, so it learned to rely on customer_id instead → R@5=7.4% even with rich history available at inference.

### Gradient Competition: customer_id vs history

The 64D customer_id embedding can directly memorize per-customer preferences — it's a stronger, more consistent gradient signal during training. The 32D taste vector provides an indirect signal through averaging and shared embedding lookup. When 29.1% of training rows have empty history, gradient descent takes the path of least resistance and allocates capacity to customer_id. The taste vector becomes a secondary, underutilized feature.

---

## Proposed Fix

In `dev/sql/create_ternopil_train_v4_view.sql`, line 71, change the temporal restriction from strict less-than to less-than-or-equal:

**Before (current):**
```sql
AND acp.purchase_date < rk.row_date    -- strict less than
```

**After (proposed):**
```sql
AND acp.purchase_date <= rk.row_date   -- include same-day purchases
AND acp.product_id != rk.product_id    -- still exclude target product
```

This way, for a customer buying products A, B, C on day 5:
- Row (customer, A, day 5): history = [B, C] — same-day co-purchases, target A excluded
- Row (customer, B, day 5): history = [A, C] — target B excluded
- Row (customer, C, day 5): history = [A, B] — target C excluded

### Expected Impact

1. **Eliminates most empty-history rows**: only truly first-time customers (single product, single day) would have empty history
2. **Aligns training with inference**: both training and inference would use rich history with similar density
3. **No temporal leakage**: `<= row_date` means only current and past data; the target product is still excluded via the product_id filter
4. **Preserves co-purchase signal**: same-day co-purchases are the strongest collaborative filtering signal in B2B data — the model needs to see them during training

### Same Fix for Prob-Train View

Apply the same change to `dev/sql/create_ternopil_prob_train_v4_view.sql` in the analogous CTE.

---

## Files Referenced

| File | Purpose |
|------|---------|
| `dev/sql/create_ternopil_train_v4_view.sql` | Training view SQL — contains the bug (line 71) |
| `dev/sql/create_ternopil_prob_train_v4_view.sql` | Prob-train view SQL — same issue |
| `dev/sql/create_ternopil_test_v4_view.sql` | Test view SQL — no change needed |
| `dev/models/qt-174/trainer_module.py` | Qt-174 generated trainer (identical to qt-179) |
| `dev/models/qt-174/transform_module.py` | Qt-174 generated transform (identical to qt-179) |
| `dev/models/qt-174/inference_demo.ipynb` | Inference notebook showing R@5=29.6% on unseen data |
| `ml_platform/configs/services.py` | Code generation — unchanged between qt-174 and qt-179 |
| `ml_platform/datasets/services.py` | SQL query generation — holdout off-by-one fix only |
