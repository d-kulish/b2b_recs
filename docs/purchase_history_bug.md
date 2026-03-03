# Analysis: Purchase History Taste Vector — Global Aggregation Is Correct

**Date**: 2026-03-03 (initial), 2026-03-03 (revised)
**Experiments**: qt-162 (baseline), qt-174 (global history), qt-179 (point-in-time history)
**Status**: Root cause identified, views reverted to global aggregation

---

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

| Priority | Action | Rationale |
|----------|--------|-----------|
| 1 | Early stopping (patience ~5 on val loss) | Overfitting starts at ~epoch 13 for taste vector models |
| 2 | Reduce `customer_id` embedding (64D → 16–32D) | Reduces gradient competition with the 32D taste vector |
| 3 | Add `history_length` as numeric buyer feature | Lets the model adapt to cold-start vs mature customers |
| 4 | Attention-weighted pooling | Learn which past purchases are most relevant per prediction |
| 5 | Multi-embedding clustering (PinnerSage-style) | Separate taste vectors per interest cluster for diverse shoppers |

---

## Files Referenced

| File | Purpose |
|------|---------|
| `dev/sql/create_ternopil_train_v4_view.sql` | Training view — reverted to global aggregation |
| `dev/sql/create_ternopil_prob_train_v4_view.sql` | Ranking training view — reverted to global aggregation |
| `dev/sql/create_ternopil_test_v4_view.sql` | Test view — unchanged (already correct) |
| `dev/sql/create_ternopil_prob_test_v4_view.sql` | Ranking test view — unchanged (already correct) |
| `dev/models/qt-174/inference_demo.ipynb` | Inference notebook showing R@5=32.8% on unseen data |
| `ml_platform/configs/services.py` | Code generation — unchanged |
