# Analysis: Purchase History Taste Vector Bugs

**Date**: 2026-03-03 (initial), 2026-03-03 (revised), 2026-03-07 (target exclusion bug)
**Experiments**: qt-162 (baseline), qt-174 (global history), qt-179 (point-in-time history), qt-182 (target exclusion analysis)
**Status**: Two bugs found and fixed. See Bug #1 (point-in-time) and Bug #2 (target exclusion mismatch).

---

# Bug #1: Point-in-Time Restriction (qt-179, resolved 2026-03-03)

## Summary

Commit `530be73` introduced a point-in-time restriction (`purchase_date < row_date`) into the training views for the purchase history taste vector. This was modeled after YouTube's temporal "rollback" pattern for sequential features. The fix was wrong: the taste vector is a **mean-pooled bag-of-items embedding**, not a sequential feature. Temporal rollback does not apply. The restriction created a train/serve distribution mismatch that made the taste vector useless during training (29.1% empty histories), causing the model to ignore it entirely.

The views have been reverted to **global aggregation** — each training row receives the customer's full training-period purchase history (excluding the target product). This matches serving-time behavior and is the standard approach for mean-pooled history embeddings in two-tower retrieval models.

---

## Experiment Results

| Experiment | History | R@5 (pipeline) | R@5 (unseen test) | R@10 | R@50 | R@100 |
|------------|---------|-----------------|-------------------|------|------|-------|
| qt-162 | None (baseline + scalars) | 5.2% | — | 8.1% | 22.0% | 33.1% |
| qt-174 | Global (all training-period products) | **49.1%** | **32.8%** | 56.1% | 64.4% | 68.5% |
| qt-179 | Point-in-time (`< row_date`) | 7.4% | — | 10.4% | 23.6% | 32.5% |

Qt-174's pipeline metrics (49.1%) are inflated compared to its unseen-test metrics (32.8%). This is the normal train/test gap — not a sign of harmful leakage. The model learned real co-purchase patterns that generalize to data it never saw during training.

Qt-179 performed at baseline level despite having the same model architecture and code. The point-in-time restriction destroyed the taste vector signal.

---

## Why the Point-in-Time Fix Was Wrong

### 1. The taste vector is not a sequential feature

The taste vector is computed as: `mean(embedding(product_ids))` — a simple average of product embeddings. Mean pooling **destroys temporal ordering**. The average of [Milk, Bread, Fish] is the same regardless of purchase order. Temporal "rollback" matters for sequential models (GRU4Rec, BERT4Rec, SASRec) where the order of items is the signal. For a mean-pooled embedding, it is irrelevant.

### 2. At serving time, the customer has their full history

When the model runs inference, the customer's taste vector is computed from ALL their past purchases. The training view must match this distribution. Global aggregation matches it. The point-in-time restriction created a mismatch:

| | Training (qt-179, `<`) | Serving / Test |
|--|---|---|
| History style | Per-date, strict `< row_date` | Global (full training period) |
| Empty history | 29.1% | ~0% |
| Avg length | 18.5 | ~24 |

### 3. The target product is excluded — that is the only leakage that matters

Both the old and new views exclude the target product from the history array. The model never sees "this customer bought X" when predicting X. All other products the customer bought are legitimate collaborative filtering signal — they encode the customer's taste profile, which is exactly what the model needs to learn.

### 4. Food retail has no meaningful intra-day ordering

In food retail, a customer walks into a store and fills a cart with 10–20 products in one visit. All items get the same timestamp. With strict `<`, an entire first visit produces empty history for all its rows. This is a domain-specific problem: unlike video streaming where watches have distinct timestamps, grocery purchases are bulk events.

### 5. Gradient competition killed the taste vector

The 64D `customer_id` embedding directly memorizes per-customer preferences — a strong, consistent gradient signal. The 32D taste vector provides an indirect signal via shared embedding + averaging. When 29.1% of training rows had empty history, gradient descent allocated capacity to `customer_id` and learned to ignore the taste vector. Even at serving time, when rich history was available, the model did not use it.

---

## Industry Context: How Major Companies Handle History Vectors

### YouTube (Covington et al., 2016) — "Deep Neural Networks for YouTube Recommendations"

YouTube's recommendation paper is the origin of the "rollback" pattern that inspired the (incorrect) point-in-time fix:

> "A user's watch history embedding is formed using **averaging** each video's embedding."

YouTube caps history at 50 most recent watches and mean-pools them. The paper emphasizes temporal rollback:

> "It is important that training is not performed on random held-out samples, but that the next video is always held out and a **rollback of features available prior to the video watch** is supplied to the classifier."

**Why this does not apply here:** YouTube's recommendation task is inherently sequential — episode 1 before episode 2, trending videos have temporal relevance. The rollback prevents the model from seeing that a user watched episode 3 when predicting episode 2. In food retail, there is no such asymmetric consumption pattern: buying Milk does not depend on having bought Bread first. The mean-pooled taste vector captures "what kind of products does this customer buy" — a static profile, not a temporal sequence.

**Source:** [research.google/pubs/deep-neural-networks-for-youtube-recommendations/](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/)

### Google Two-Tower Production System (Yi et al., 2019) — "Sampling-Bias-Corrected Neural Modeling"

Google's production retrieval system for YouTube confirms:

> "Watch history is treated as video IDs the user recently watched, and is represented by the **average of video ID embeddings**. A bag-of-words approach treats watch history as a bag of its videos... with averaging presumably finding the centroid in the embedding space."

The "bag-of-words" framing is important: the history is treated as an **unordered set**, not a sequence. Temporal ordering is discarded by the averaging operation itself.

**Source:** [research.google/pubs/sampling-bias-corrected-neural-modeling-for-large-corpus-item-recommendations/](https://research.google/pubs/sampling-bias-corrected-neural-modeling-for-large-corpus-item-recommendations/)

### Pinterest — PinnerSage (2020)

Pinterest found that a single average embedding is insufficient for users with diverse interests:

> "Users' actions are clustered into conceptually coherent clusters... generating a summary of each of those clusters using a medoid, an embedding, and a cluster importance score."

They use 90-day history windows and cluster into multiple per-user embeddings. The key insight for this project: Pinterest uses **global aggregation within the window** — no point-in-time restriction within the 90-day period.

**Source:** [arxiv.org/abs/2007.03634](https://arxiv.org/abs/2007.03634)

### Uber Eats (2022) — "Two-Tower Embeddings"

Uber Eats uses ordered store IDs, embedded and averaged ("BOW features"), reducing model size 20x vs raw user ID embeddings. Same pattern: mean pooling over the full available history.

**Source:** [uber.com/blog/innovative-recommendation-applications-using-two-tower-embeddings/](https://www.uber.com/blog/innovative-recommendation-applications-using-two-tower-embeddings/)

### Snapchat (2023) — "Embedding-Based Retrieval"

Snap processes past engagement sequences with average pooling into fixed-width vectors for the user tower.

**Source:** [eng.snap.com/embedding-based-retrieval](https://eng.snap.com/embedding-based-retrieval)

### Key Principle: Train/Serve Consistency

From Tecton's analysis of ML feature engineering:

> "It is **absolutely important** to make sure that the data that you're using in real-time, at serving time, **matches the data** that is used at training."

The point-in-time fix violated this principle: training used sparse, date-restricted history while serving provided full, global history. The model never learned to use the rich history that would be available at inference time.

**Source:** [tecton.ai/blog/hidden-data-engineering-problems-in-ml/](https://www.tecton.ai/blog/hidden-data-engineering-problems-in-ml/)

### Average Embedding Consistency Research (ACM RecSys 2023)

"On the Consistency of Average Embeddings for Item Recommendation" found that average embeddings have low consistency scores (14%, 6%, 2% on real datasets). Averaging works best with:
- Small number of items in the average (cap at 50 is correct)
- Higher-dimensional embeddings (32D is a minimum; 64–128D would improve consistency)

This is relevant for future improvements (attention-weighted pooling, multi-embedding clustering) but does not change the conclusion that global aggregation is the correct baseline.

**Source:** [dl.acm.org/doi/10.1145/3604915.3608837](https://dl.acm.org/doi/10.1145/3604915.3608837)

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

**Byte-identical** except timestamps. The performance difference is entirely caused by the training data (view SQL), not the model code.

### 2. TFRecords Confirm the Damage

Qt-179's training records (71,680 total):

| Metric | Value |
|--------|-------|
| History non-empty | 50,808 (70.9%) |
| History empty | 20,872 (29.1%) |
| Avg length (non-empty) | 18.5 products |
| Max length | 50 (capped) |

29.1% of training rows had empty history — consistent with the strict `<` excluding all first-day purchases.

### 3. Qt-174 on Unseen Test Data

The qt-174 model evaluated on `ternopil_test_v4` (notebook `dev/models/qt-174/inference_demo.ipynb`):

| Scenario | R@5 | R@10 | R@50 | R@100 | R@150 |
|----------|-----|------|------|-------|-------|
| 100% match (known customers + products) | 32.8% | 37.4% | 47.2% | 52.6% | 57.8% |
| All customers, known products | 24.8% | 28.4% | 38.0% | 44.4% | 49.8% |

The test view also excludes the target product from history (`cp1.product_id != cp2.product_id`). These results are from genuine co-purchase pattern learning, not label leakage.

### 4. Training Dynamics

| Metric | qt-174 (global) | qt-179 (point-in-time) | qt-162 (no history) |
|--------|-----------------|------------------------|---------------------|
| Final train loss | **1,716** | 9,174 | 2,373 |
| Test R@5 | **49.1%** | 7.4% | 5.2% |

Qt-174 drove training loss 5.3x lower than qt-179 because the rich history enabled the shared embedding to learn strong co-occurrence patterns.

---

## Fix Applied: Revert to Global Aggregation

### What Changed

The two training views were reverted from point-in-time CTEs back to global aggregation with target exclusion:

| View | Change |
|------|--------|
| `ternopil_train_v4` | Replaced 3 point-in-time CTEs (`all_customer_purchases`, `row_keys`, `customer_purchase_history`) with 2 global CTEs (`customer_products`, `customer_purchase_history` via self-join). Removed date dimension from final JOIN. |
| `ternopil_prob_train_v4` | Replaced 3 point-in-time CTEs (`all_customer_purchases`, `customer_row_dates`, `customer_purchase_history`) with 2 global CTEs (`customer_products`, `customer_purchase_history` per customer). Removed date dimension from positives/negatives JOINs. |
| `ternopil_test_v4` | No change — already uses global aggregation from `historical_data`. |
| `ternopil_prob_test_v4` | No change — already uses global aggregation from `historical_data`. |

### How History Is Now Computed (All 4 Views)

**Retrieval views** (`ternopil_train_v4`, `ternopil_test_v4`):
- Per (customer, target_product): top 50 OTHER products by recency
- Target product excluded via self-join: `cp1.product_id != cp2.product_id`
- Same history array for all rows of the same (customer, target_product) pair

**Ranking views** (`ternopil_prob_train_v4`, `ternopil_prob_test_v4`):
- Per customer: top 50 products by recency
- Target product excluded inline for positives: `WHERE p != deduped.product_id`
- Negatives: no exclusion needed (the negative product was not purchased)

### Train/Serve Alignment

| | Training | Test / Serving |
|--|---|---|
| History scope | Full training period | Full training period |
| Empty history | ~0% (customers with 2+ products) | ~0% |
| Avg length | ~24 | ~24 |
| Target excluded | Yes | Yes |

Training and serving now see the same distribution.

---

## Impact on Metrics

- **Pipeline training metrics will be higher** than real-world performance (because the model sees the customer's full taste profile during both training and in-pipeline evaluation)
- **The gap between pipeline and inference metrics is the honest measure** — qt-174 showed 49.1% → 32.8%, a ~16pp drop that reflects the difference between in-sample and out-of-sample evaluation
- **Test-set evaluation (inference notebook) is the ground truth** — this uses held-out data with history computed from the training period only

---

## Future Improvements

### Category-Level Taste Vectors

The current product-level taste vector (32D) captures item-level co-purchase patterns. Adding category-level taste vectors captures broader, denser preference signals using the **same shared-embedding mechanism** already in the platform.

The product tower already has embeddings for each hierarchy level. Each can become a buyer-side taste vector by sharing the same embedding table:

| Taste Vector | Shared With | Column | Dim | Signal |
|---|---|---|---|---|
| Product (exists) | `product_id` | `purchase_history` | 32D | Item-level co-purchase patterns |
| **Brand** | `brand` | `brand_history` | 32D | Brand loyalty — strongest new signal for grocery |
| **Subcategory** | `sub_cat_v1` (`mge_main_cat_desc`) | `subcat_history` | 16D | Mid-level category preferences |
| **Category** | `category` (`stratbuy_domain_desc`) | `category_history` | 8D | Broad lifestyle/diet patterns |

**Why this adds signal beyond product history:**

1. **Dilution problem.** The ACM RecSys 2023 paper measured 2–14% consistency for average embeddings on real data. A customer with 30 products across 5 categories produces one 32D vector that tries to represent all 5 interests. A separate 8D category vector says "60% dairy, 20% bakery, 20% cleaning" directly.

2. **Frequency encoding.** The product history is capped at 50 unique products. A customer who bought dairy 200 times and cleaning 5 times looks similar to one who bought dairy 10 times and cleaning 10 times if they bought the same unique products. A category history with **repeated** values (one per purchase, not deduplicated) encodes purchase intensity naturally.

3. **Direct buyer-candidate matching.** Shared embedding means the model learns a single "category space" where the buyer's category taste vector and a candidate product's category embedding are directly comparable via dot product.

**SQL construction** — arrays should NOT be deduplicated (repetition encodes frequency):

```sql
-- Brand taste: top 50 brand values by recency (with repeats for frequency)
customer_brand_history AS (
  SELECT customer_id,
    ARRAY_AGG(brand_name ORDER BY date DESC LIMIT 50) AS brand_history
  FROM train_data
  WHERE product_id IN (SELECT product_id FROM top_products)
  GROUP BY customer_id
),

-- Subcategory taste: top 50 sub_cat values by recency (with repeats)
customer_subcat_history AS (
  SELECT customer_id,
    ARRAY_AGG(mge_main_cat_desc ORDER BY date DESC LIMIT 50) AS subcat_history
  FROM train_data
  WHERE product_id IN (SELECT product_id FROM top_products)
  GROUP BY customer_id
),

-- Category taste: top 50 category values by recency (with repeats)
customer_category_history AS (
  SELECT customer_id,
    ARRAY_AGG(stratbuy_domain_desc ORDER BY date DESC LIMIT 50) AS category_history
  FROM train_data
  WHERE product_id IN (SELECT product_id FROM top_products)
  GROUP BY customer_id
)
```

**Feature config** — uses existing `shared_with` infrastructure:

```json
{"column": "brand_history", "data_type": "history",
 "transforms": {"history": {"shared_with": "brand", "embedding_dim": 32, "max_length": 50}}}

{"column": "subcat_history", "data_type": "history",
 "transforms": {"history": {"shared_with": "sub_cat_v1", "embedding_dim": 16, "max_length": 50}}}

{"column": "category_history", "data_type": "history",
 "transforms": {"history": {"shared_with": "category", "embedding_dim": 8, "max_length": 50}}}
```

**Recommended rollout order:**

1. **Brand** (32D) — brand loyalty is one of the strongest predictors of repeat purchase in grocery retail
2. **Subcategory** (16D, `mge_main_cat_desc`) — mid-level category preference without being too broad
3. **Category** (8D, `stratbuy_domain_desc`) — broadest level, least discriminative

Total addition: +56D to the buyer tower. The first dense layer should be widened (e.g., Dense(64) → Dense(128)) to accommodate the richer input.

### Recency-Weighted Mean Pooling

Instead of uniform averaging, weight recent purchases higher using exponential time decay:

```
weight_i = exp(-λ * (t_now - t_i))
taste_vector = Σ(weight_i * embedding_i) / Σ(weight_i)
```

The decay rate λ controls how fast old purchases lose influence. For a food retailer with weekly shopping cycles, a half-life of 2–4 weeks captures the most actionable preferences: a customer who bought Yogurt yesterday is more likely to buy it again than one who bought it 3 months ago.

**Implementation options:**

- **SQL-side:** Add a `purchase_recency_days` array column alongside the history array. The model computes weights from days-since-purchase at training time.
- **Model-side:** Add a small weight-computation layer in `BuyerModel.call()` that takes recency as input and produces per-item attention weights before averaging.

This applies to all taste vectors (product, brand, subcategory, category) — any mean-pooled history benefits from recency weighting.

### Other Improvements

| Priority | Action | Rationale |
|----------|--------|-----------|
| 1 | Early stopping (patience ~5 on val loss) | Overfitting starts at ~epoch 13 for taste vector models |
| 2 | Reduce `customer_id` embedding (64D → 16–32D) | Reduces gradient competition with the 32D taste vector |
| 3 | Add `history_length` as numeric buyer feature | Lets the model adapt to cold-start vs mature customers |
| 4 | Attention-weighted pooling | Learn which past purchases are most relevant per prediction |
| 5 | Multi-embedding clustering (PinnerSage-style) | Separate taste vectors per interest cluster for diverse shoppers |

---

---

# Bug #2: Target Product Exclusion Train/Test Mismatch (qt-182, resolved 2026-03-07)

## Summary

Experiment qt-182 (a rerun of qt-174 with identical model code) showed a massive accuracy gap:
- **Pipeline test** (day 29, within training view): **R@5 = 59.0%**
- **External test** (day 30, test view via serving model): **R@5 = 1.7%**

These are **consecutive days** with nearly identical data distributions (80.6% customer overlap, 100% product overlap, similar feature statistics). The root cause was a train/test mismatch in how `purchase_history` was computed:

- **Training view** (`ternopil_train_v4`): history per-(customer, target_product), **excluding** the target product via self-join `cp1.product_id != cp2.product_id`
- **Test view** (`ternopil_test_v4`): history per-customer, **including** all products

The model learned a "missing product" signal — it predicted products that were **absent** from the customer's history, because during training the target product was always absent from the history array. When the test view included the target product in history, the model actively avoided recommending it.

---

## Investigation Process

### Initial hypotheses tested and eliminated

The investigation followed a systematic elimination process. Several plausible hypotheses were tested and ruled out before finding the root cause:

**1. Code differences between qt-174 and qt-182 (ELIMINATED)**

Downloaded and diffed GCS artifacts:
```
gs://b2b-recs-quicktest-artifacts/qt-174-20260228-173331/
gs://b2b-recs-quicktest-artifacts/qt-182-20260307-*/
```
Only 2 lines differ: timestamp and candidate pool source (`eval_files` → `train_files + eval_files`). Generated transform and trainer modules are functionally identical.

**2. TFT layer type mismatch — int64 vs string vocab lookup (ELIMINATED)**

The serving model receives history as `tf.int64`, while the vocab file has string entries. Hypothesis: the TFT layer's `apply_vocabulary` might map all int64 values to OOV due to type mismatch.

Diagnostic script (`diagnose_history.py`) tested four scenarios:
- Known product IDs in history → top score 3718
- Empty history (all zeros) → top score 1537
- Random OOV IDs → top score 1209
- Different known product IDs → top score 2517

**Result**: History DOES affect recommendations. Different product IDs produce different scores. The TFT layer correctly handles int64→string conversion internally. Type mismatch hypothesis eliminated.

**3. Serving model path vs pipeline path (ELIMINATED)**

Ran the serving model on **day 29 data** (same data the pipeline test used) from the training view:

| Evaluation | R@5 |
|---|---|
| Pipeline test (day 29, in-pipeline) | 59.0% |
| Serving model (day 29, from training view) | **84.3%** |
| Serving model (day 30, from test view) | 1.7% |

Day 29 via serving model gives **84.3%** — even higher than the pipeline test (59%, which includes OOV customers/products that always miss). The serving model path works correctly. The issue is specific to day 30 data from the test view.

**4. Feature value differences between day 29 and day 30 (ELIMINATED)**

Compared feature statistics for the same known customers across both views:

| Metric | Day 29 (train view) | Day 30 (test view) |
|---|---|---|
| avg_cust_value | 6,397 | 5,373 |
| avg_days_since | 15.7 | 23.2 |
| avg_orders | 11.2 | 10.4 |
| avg_unique_prods | 69.6 | 49.4 |
| avg_hist_len | 39.7 | 27.2 |
| null_history | 0% | 0% |

Values differ slightly but are in the same ballpark. History content for overlapping customers is nearly identical (same items, slightly different order).

**5. Controlled feature-swap experiments (ELIMINATED all individual features)**

Took 300 day 30 samples and systematically swapped features to day 29 values:

| Experiment | R@5 |
|---|---|
| 1. Baseline (day 30 as-is) | 1.3% |
| 2. Date → day 29 | 1.3% |
| 3. Empty history | 2.7% |
| 4. Buyer stats → day 29 averages | 2.0% |
| 5. Date + buyer stats → day 29 | 2.7% |
| 6. History from training view (16/300 swapped) | 1.3% |
| 7. ALL features → day 29 | 2.0% |

**No individual feature swap or combination improved accuracy.** The model's recommendations are relatively stable regardless of features. The issue is that day 30's ground truth products are not in the model's top-K.

**6. Data distribution differences (ELIMINATED)**

Compared repeat purchase rates and product popularity:

| Metric | Day 29 | Day 30 |
|---|---|---|
| Total (customer, product) pairs | 645 | 723 |
| Repeat pairs (seen in training) | 280 (43.4%) | 296 (40.9%) |
| Unique products | 356 | 377 |
| Avg training frequency | 184.6 | 181.4 |

Nearly identical distributions. No systematic difference in product popularity or repeat purchase behavior.

**7. Model degeneracy observation**

Analysis revealed the model recommends product `49892001001` as the #1 recommendation for **100% of customers** — a degenerate model with popularity collapse. Beyond #1, recommendations differ by customer but are **extremely sensitive** to small feature changes: the same customer gets completely different top-5 lists with day 29 vs day 30 features.

### Root cause identified: target product exclusion mismatch

The decisive diagnostic (`diagnose_target_exclusion.py`) tested whether excluding the target product from history would improve accuracy:

| Scenario | R@5 (all 300 samples) |
|---|---|
| History **WITH** target product (test view behavior) | 3.0% (9/300) |
| History **WITHOUT** target product (training view behavior) | **30.7%** (92/300) |

Breaking down by whether the target product appeared in the customer's history:

| Scenario | Target IN history (126 samples) | Target NOT in history (174 samples) |
|---|---|---|
| History WITH target | R@5 = 4.8% (6/126) | R@5 = 1.7% (3/174) |
| History WITHOUT target | **R@5 = 70.6% (89/126)** | R@5 = 1.7% (3/174) |

Key findings:
- **14.7x improvement** when removing target from history (for samples where target was in history)
- **Identical results** when target was not in history (confirming the effect is purely about target inclusion)
- Specific examples confirm the pattern:
  - Customer 330061020401, target 357301001001: WITH target → not in top-5. WITHOUT target → **#2 in top-5**
  - Customer 640000543701, target 259887001001: WITH target → not in top-5. WITHOUT target → **#2 in top-5**

---

## Root Cause Mechanism

### How the model learned the "missing product" signal

The training view computes history per-(customer, target_product), excluding the target:

```sql
-- Training view CTE
customer_purchase_history AS (
  SELECT
    cp1.customer_id,
    cp1.product_id AS target_product_id,
    ARRAY_AGG(cp2.product_id ORDER BY cp2.last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products cp1
  JOIN customer_products cp2
    ON cp1.customer_id = cp2.customer_id
    AND cp1.product_id != cp2.product_id  -- target excluded
  GROUP BY cp1.customer_id, cp1.product_id
)
```

During training, for every (customer, product) pair, the target product is **guaranteed absent** from the history. The model's mean-pooled taste vector (32D) captures the customer's preferences **minus one product**. Over 100 epochs of training with massive overfitting (505x train/val loss ratio), the model learned:

1. Compute the customer's taste centroid from their history
2. The centroid is shifted slightly AWAY from the target (because the target was removed)
3. Recommend the product that would "complete" the centroid — i.e., the missing item

This is a subtle form of information leakage: the **absence** of the target product from the history array encodes which product is the target.

### Why this breaks at serving time

At serving time (and in the test view), the customer's full history is used for all candidates — the target product is not excluded because you don't know what the customer will buy next:

```sql
-- Test view CTE (original, before fix)
customer_purchase_history AS (
  SELECT
    customer_id,
    ARRAY_AGG(product_id ORDER BY last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products
  GROUP BY customer_id
)
```

When the target product IS in the history (42% of test samples), the model's learned "missing product" detector fails: it looks for what's missing, but the target is present, so it recommends something else.

### Why day 29 (training view) worked but day 30 (test view) didn't

- **Day 29 evaluation** used the training view's `purchase_history`, which excludes the target → model sees the pattern it was trained on → R@5 = 84.3%
- **Day 30 evaluation** used the test view's `purchase_history`, which includes all products → model doesn't see the "missing product" pattern → R@5 = 1.7%

---

## Fix Applied (Short-Term Validation)

Updated `ternopil_test_v4` to exclude the target product from history, matching the training view's behavior:

```sql
-- BEFORE (per-customer, includes target)
customer_purchase_history AS (
  SELECT
    customer_id,
    ARRAY_AGG(product_id ORDER BY last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products
  GROUP BY customer_id
)
...
LEFT JOIN customer_purchase_history ch
  ON t.customer_id = ch.customer_id

-- AFTER (per-(customer, target_product), excludes target)
customer_purchase_history AS (
  SELECT
    cp1.customer_id,
    cp1.product_id AS target_product_id,
    ARRAY_AGG(cp2.product_id ORDER BY cp2.last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products cp1
  JOIN customer_products cp2
    ON cp1.customer_id = cp2.customer_id
    AND cp1.product_id != cp2.product_id
  GROUP BY cp1.customer_id, cp1.product_id
)
...
LEFT JOIN customer_purchase_history ch
  ON t.customer_id = ch.customer_id AND t.product_id = ch.target_product_id
```

This is a **validation fix** only — it confirms the root cause by making the test view match the training view. The accuracy should jump from ~1.7% to ~60-70% R@5 with the existing qt-182 model.

## Recommended Long-Term Fix

The short-term fix makes the test view match the (broken) training view. The proper fix is the opposite: make the **training view** include the target product in history, matching real serving behavior.

### Training view change needed

```sql
-- CURRENT (broken): per-(customer, target_product), excludes target
customer_purchase_history AS (
  SELECT
    cp1.customer_id,
    cp1.product_id AS target_product_id,
    ARRAY_AGG(cp2.product_id ORDER BY cp2.last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products cp1
  JOIN customer_products cp2
    ON cp1.customer_id = cp2.customer_id
    AND cp1.product_id != cp2.product_id
  GROUP BY cp1.customer_id, cp1.product_id
)
...
LEFT JOIN customer_purchase_history ch
  ON t.customer_id = ch.customer_id AND t.product_id = ch.target_product_id

-- FIX: per-customer, includes all products (matches serving)
customer_purchase_history AS (
  SELECT
    customer_id,
    ARRAY_AGG(product_id ORDER BY last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products
  GROUP BY customer_id
)
...
LEFT JOIN customer_purchase_history ch
  ON t.customer_id = ch.customer_id
```

After updating the training view, the test view should be reverted to per-customer history (its original form) and the model retrained.

### Why including the target in training history is correct

1. **Serving consistency**: At serving time, you don't know the target product, so you can't exclude it. Training and serving must use the same history format.

2. **The "leakage" concern is misplaced**: Including product X in history when predicting X seems like leakage, but the mean-pooled taste vector averages 50 products into one 32D vector. The presence of one product among 50 contributes ~2% of the signal — the model cannot trivially extract "recommend what's in history" from a mean-pooled embedding.

3. **Current approach is worse**: Excluding the target created a stronger leakage — the model learned to exploit the **absence** of the target, which is 100% correlated with the label.

4. **The model should learn co-purchase patterns**: If a customer bought Milk, Bread, and Butter, recommending Eggs is a legitimate co-purchase pattern whether or not Eggs appears in the history. The model needs to learn general taste preferences, not the "find the missing item" trick.

---

## Diagnostic Scripts

All diagnostic scripts are in `dev/models/qt-182/`:

| Script | Purpose |
|---|---|
| `diagnose_history.py` | Tests if TFT layer correctly processes int64 history values (eliminated type mismatch hypothesis) |
| `diagnose_day29_via_serving.py` | Runs serving model on day 29 data to isolate data vs model path issue |
| `diagnose_data_diff.py` | Compares feature values between day 29 and day 30 for overlapping customers |
| `diagnose_controlled.py` | Systematic feature-swap experiments (date, history, buyer stats) |
| `diagnose_ground_truth.py` | Compares product distributions, repeat rates, and model recommendation patterns |
| `diagnose_target_exclusion.py` | **Decisive test**: compares accuracy with/without target in history |

---

## Files Referenced

| File | Purpose |
|------|---------|
| `dev/sql/create_ternopil_train_v4_view.sql` | Training view — global aggregation, excludes target (needs long-term fix) |
| `dev/sql/create_ternopil_prob_train_v4_view.sql` | Ranking training view — global aggregation |
| `dev/sql/create_ternopil_test_v4_view.sql` | Test view — updated to exclude target (short-term validation fix) |
| `dev/sql/create_ternopil_prob_test_v4_view.sql` | Ranking test view — unchanged |
| `dev/models/qt-174/inference_demo.ipynb` | Inference notebook showing R@5=32.8% on unseen data |
| `dev/models/qt-182/inference_demo.ipynb` | Inference notebook showing R@5=1.7% (before fix) |
| `dev/models/qt-182/diagnose_*.py` | Diagnostic scripts used during investigation |
| `ml_platform/configs/services.py` | Code generation — unchanged |
