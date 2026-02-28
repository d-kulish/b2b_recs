# Improving Retrieval Model Quality

**Date**: 2026-02-27 (analysis) · 2026-02-28 (experiments completed)
**Context**: QT-172 (`feat_retr_v6` + `mod_retr_v6`, `ternopil_train_v4`, `strict_time` split)
**Related**: `docs/phase_experiments.md` (History Feature Type section — taste vector design, validation, bug fixes)
**Status**: Tower sweep complete. **[64, 32] is optimal** — R@5=35.6%, R@100=66.8% (2.1x / 1.3x vs baseline). See Section 5 for all results, Section 6 for next steps.

---

## 1. Current State

### 1.1 Model Architecture

Two-tower TFRS retrieval model with shared product embedding:

```
BUYER TOWER                              PRODUCT TOWER
┌────────────────────────┐               ┌────────────────────────┐
│ customer_id → 64D      │               │ product_id → shared 32D│
│ history → shared avg 32D│              │ category, sub_cats,    │
│ date → cyclical+bucket │               │ brand, name → embeds   │
│ cust_value, RFM → norm │               │ pr_stats → norm+bucket │
│ + bucket               │               │ cross feature → 16D    │
│ cross feature → 16D    │               └───────────┬────────────┘
└───────────┬────────────┘                           │
            │                                        │
  Dense(256, relu, L2=0.02)              Dense(256, relu, L2=0.02)
  Dense(128, relu, L2=0.02)              Dense(128, relu, L2=0.02)
  Dense(64, relu)                        Dense(64, relu)
  Dense(32, relu) → query_emb           Dense(32, relu) → candidate_emb
            │                                        │
            └──────── tfrs.tasks.Retrieval() ────────┘
```

### 1.2 Loss Function

```python
self.task = tfrs.tasks.Retrieval()
```

Bare defaults — no temperature, no label smoothing, no hard negatives.

Under the hood `tfrs.tasks.Retrieval()` implements **in-batch softmax cross-entropy** (InfoNCE):

1. **Score matrix**: `scores[i][j] = dot(query_i, candidate_j)` — shape `[batch, batch]`
2. **Labels**: Identity matrix — `labels[i][i] = 1.0`, everything else `0.0`
3. **Loss**: `CategoricalCrossentropy(from_logits=True, reduction=SUM)` — softmax over the score row, cross-entropy against the one-hot label

With `batch_size=4096`, each positive (customer, product) pair is scored against 4,095 in-batch negatives. The loss pushes `scores[i][i]` higher than `scores[i][j]` for all `j != i`.

### 1.3 Observed Overfitting Pattern

Every experiment shows the same pattern — validation loss rises while training loss continues to drop:

| Epoch | Train Loss | Val Loss | Gap |
|---|---|---|---|
| 1 | 12,000 | 12,000 | 0% |
| 30 | 3,500 | 12,500 | 257% |
| 61 | 1,703 | 13,998 | 722% |
| 100 | 1,264 | 15,876 | 1,156% |

This is not a bug — it is a fundamental property of the current setup.

### 1.4 Evaluation Methodology Issue (QT-171)

QT-171 reported Recall@5=41.2%, Recall@100=87.6%. These metrics are inflated by the `random` hash-based split strategy. The hash split scatters each customer's transactions across train/eval/test splits. With `customer_id` embeddings and `purchase_history` features, the model memorizes per-customer preferences during training, then the test split asks the model to predict purchases for **the same customers** from **the same time period** — not a valid out-of-sample evaluation.

Genuine held-out evaluation on `ternopil_test_v4` (last day, temporally separated) shows Recall@5=16.2%, Recall@100=46.4%.

**Fix**: Use `strict_time` split strategy for all experiments with customer-level features.

---

## 2. Why Val Loss Always Rises

Three factors compound to create the train/val divergence:

### 2.1 SUM Reduction Amplifies Overfitting Signal

The default `CategoricalCrossentropy(reduction=SUM)` sums loss across the batch. Overfitting manifests as extreme confidence on training pairs: the model pushes `scores[i][i]` to very high positive values and `scores[i][j]` to very negative values. On validation data, the model encounters unseen (customer, product) pairs where its extreme confidence is wrong — producing large per-example losses that sum to massive totals.

### 2.2 Small Catalog + Large Batch = Easy Negatives

976 products with `batch_size=4096` means each batch contains every product ~4 times on average. The in-batch negatives become trivial to distinguish from the positive after a few epochs. The model quickly learns per-customer preferences (via the 64D customer_id embedding), then spends the remaining epochs memorizing individual (customer, product) affinities rather than learning generalizable patterns.

### 2.3 Unbounded Embedding Space

Tower outputs are unnormalized — values can grow without limit. The model exploits this by driving scores for memorized positive pairs to arbitrarily high values. Training loss approaches zero because the softmax becomes arbitrarily peaked. Validation loss explodes because the model's extreme confidence is wrong on unseen pairs — a single misranked pair produces a huge loss.

---

## 3. `tfrs.tasks.Retrieval` Parameters

The constructor accepts parameters that directly address the overfitting pattern:

```python
tfrs.tasks.Retrieval(
    loss: Optional[tf.keras.losses.Loss] = None,
    metrics: Optional[...] = None,
    temperature: Optional[float] = None,
    num_hard_negatives: Optional[int] = None,
    remove_accidental_hits: bool = False,
)
```

| Parameter | Default | Purpose |
|---|---|---|
| `loss` | `CategoricalCrossentropy(from_logits=True, reduction=SUM)` | Pluggable loss function |
| `temperature` | `None` (no scaling) | Divides logits before softmax |
| `num_hard_negatives` | `None` (use all) | Keep only top-N hardest negatives per query |
| `remove_accidental_hits` | `False` | Remove same-product duplicates from batch negatives |

Additional `call()` parameters:

| Parameter | Purpose |
|---|---|
| `candidate_sampling_probability` | Log-correction for sampling bias (popular items as negatives) |
| `candidate_ids` | Required for `remove_accidental_hits` |

---

## 4. Recommendations

### 4.1 L2-Normalize Tower Outputs + Temperature (Highest Impact)

**Problem**: Unbounded scores allow memorization via magnitude. The model pushes positive scores to infinity.

**Fix**: Constrain both tower outputs to unit sphere, then use temperature to control softmax sharpness.

```python
def compute_loss(self, features, training=False):
    query_embeddings = self.query_tower(features)
    candidate_embeddings = self.candidate_tower(features)

    # L2-normalize: scores now in [-1, 1]
    query_embeddings = tf.math.l2_normalize(query_embeddings, axis=-1)
    candidate_embeddings = tf.math.l2_normalize(candidate_embeddings, axis=-1)

    return self.task(query_embeddings, candidate_embeddings)
```

```python
self.task = tfrs.tasks.Retrieval(temperature=0.05)
```

**How it works**:

1. **Normalization** forces all embeddings onto the unit hypersphere. The dot product becomes cosine similarity, bounded to `[-1, 1]`. The model can no longer memorize via embedding magnitude — it must learn meaningful directions.

2. **Temperature** divides the logits before softmax: `scores = scores / temperature`. With normalized scores in `[-1, 1]`, a temperature of 1.0 produces a near-uniform softmax (all candidates score similarly). Low temperature (0.01–0.1) sharpens the distribution, making the softmax sensitive to small cosine differences.

**Why this is highest impact**: This is the approach used by CLIP, SimCLR, and Snapchat's production retrieval system. A TFRS practitioner reported Hit Rate@10 going from 25% to 50% purely from temperature tuning (TFRS GitHub Issue #633).

**Temperature tuning**: With L2-normalized embeddings, start at `0.05`. Tune in the range `[0.01, 0.1]`. Without normalization, temperature has minimal effect because scores are already large and the softmax is already peaked.

**Serving impact**: The serve function computes `similarities = matmul(query, candidates^T)` then `top_k(similarities)`. L2-normalization changes score magnitudes but not ranking order — `top_k` returns the same products. No changes needed to the serve function. Temperature only affects training loss, not inference.

### 4.2 Label Smoothing (High Impact)

**Problem**: Hard targets (1.0 for positive, 0.0 for negatives) push the model toward extreme confidence. In implicit feedback data, "negatives" are items the user hasn't seen — not items they dislike.

**Fix**: Soften the target distribution.

```python
self.task = tfrs.tasks.Retrieval(
    loss=tf.keras.losses.CategoricalCrossentropy(
        from_logits=True,
        label_smoothing=0.1,
        reduction=tf.keras.losses.Reduction.SUM
    )
)
```

**How it works**: Instead of targets `[0, 0, ..., 1, ..., 0]`, label smoothing produces `[ε/N, ε/N, ..., 1-ε+ε/N, ..., ε/N]` where `ε=0.1` and `N=batch_size`. The model is no longer rewarded for pushing scores to infinity — there's a soft ceiling because even a perfect prediction would have some loss from the smoothed labels.

**Tuning range**: `0.05` to `0.2`. Start at `0.1`.

**Caveat**: Incompatible with `remove_accidental_hits=True` without a custom fix (TFRS Issue #489). The accidental hit masking sets logits to negative infinity, which interacts poorly with the smoothed label distribution.

### 4.3 Hard Negative Mining (Medium Impact)

**Problem**: With 4,096 in-batch negatives and only 976 unique products, most negatives are easy — the model wastes gradient updates on trivially distinguishable products.

**Fix**: Focus the loss on the most confusing negatives.

```python
self.task = tfrs.tasks.Retrieval(num_hard_negatives=10)
```

**How it works**: For each query, the loss is computed using only the top-10 highest-scoring negatives (plus the positive). These are the products the model currently confuses with the positive — the most informative signal for learning. Easy negatives (products the model already ranks low) contribute zero gradient.

**Tuning range**: `5` to `50`. With 976 products, `10` is a reasonable starting point.

**Interaction with normalization**: Hard negative mining is most effective with L2-normalized embeddings, where all scores are in the same range. Without normalization, "hardness" is confounded by score magnitude.

### 4.4 Dropout in Tower Dense Layers (Medium Impact)

**Problem**: Current towers have L2 regularization on the first two dense layers only. No dropout anywhere.

**Fix**: Add dropout between dense layers.

Current:
```
Dense(256, relu, L2=0.02) → Dense(128, relu, L2=0.02) → Dense(64, relu) → Dense(32, relu)
```

Proposed:
```
Dense(256, relu, L2=0.02) → Dropout(0.3) → Dense(128, relu, L2=0.02) → Dropout(0.2) → Dense(64, relu) → Dense(32, relu)
```

**How it works**: Dropout randomly zeroes neuron outputs during training, preventing co-adaptation. Forces the network to learn redundant representations that generalize better.

**Implementation**: The `ModelConfig` already supports dropout rates per layer. The `TrainerModuleGenerator` generates `Dropout(rate)` layers when configured.

**Tuning range**: `0.1` to `0.5`. Higher dropout = more regularization = slower convergence but better generalization. Start at `0.2`–`0.3`.

### 4.5 Embedding Max-Norm Constraints (Low-Medium Impact)

**Problem**: Embedding vectors can grow unboundedly, allowing the model to encode memorized preferences in embedding magnitudes.

**Fix**: Constrain embedding norms.

```python
tf.keras.layers.Embedding(
    vocab_size, dim,
    embeddings_constraint=tf.keras.constraints.MaxNorm(max_value=3.0)
)
```

**How it works**: After each gradient update, embedding vectors with L2 norm > `max_value` are rescaled to exactly `max_value`. Prevents any single customer or product embedding from dominating the score computation.

**Applies to**: `customer_id` embedding (64D), `shared_product_embedding` (32D), category/brand/name embeddings.

**Tuning range**: `2.0` to `5.0`. Start at `3.0`.

**Interaction with L2-normalization**: If tower outputs are L2-normalized, embedding constraints become less critical (normalization already bounds the final score). Still useful for controlling intermediate computations.

### 4.6 Early Stopping on Validation Metric (Essential)

**Problem**: Training for 100 epochs when val loss peaks at epoch ~13 wastes compute and degrades the model.

**Important nuance**: Per TFRS Issue #263, validation loss and retrieval metrics can diverge — loss may increase while Recall@K is still improving. The loss measures softmax confidence, but recall only cares about ranking order. Early stopping should monitor the metric you care about, not raw loss.

**Options**:

| Monitor | When to use |
|---|---|
| `val_loss` | Simple, built into Keras. Stops when model confidence becomes harmful |
| `val_recall_at_K` | Ideal, but requires FactorizedTopK metrics during training (slow) |
| `val_loss` with patience=10 | Compromise — allows loss to fluctuate before stopping |

**Implementation**: Add `tf.keras.callbacks.EarlyStopping` to the training callbacks:

```python
early_stopping = tf.keras.callbacks.EarlyStopping(
    monitor='val_loss',
    patience=10,
    restore_best_weights=True
)
```

`restore_best_weights=True` is critical — it reverts the model to the epoch with lowest val loss, not the final epoch.

### 4.7 Reduce Embedding Dimensions (Low Impact)

The customer_id embedding is 64D for ~7,124 customers. The product embedding is 32D for 976 products. These sizes are reasonable, but if overfitting persists after applying the above fixes, reducing dimensions provides implicit regularization by limiting model capacity.

| Feature | Current | Conservative |
|---|---|---|
| customer_id | 64D | 32D |
| product_id (shared) | 32D | 16D |
| Tower output | 32D | 16D |

### 4.8 `remove_accidental_hits` (Context-Dependent)

```python
self.task = tfrs.tasks.Retrieval(remove_accidental_hits=True)
```

With `batch_size=4096` and 976 products, each product appears ~4 times per batch. When computing the loss for query `i`, other rows with the same product_id as `i`'s positive are "accidental positives" treated as negatives. Removing them prevents penalizing the model for scoring a product highly that the current query's customer actually bought.

Requires passing `candidate_ids` in the `call()`:

```python
return self.task(
    query_embeddings,
    candidate_embeddings,
    candidate_ids=features['product_id']
)
```

---

## 5. Experiment Results (2026-02-28)

### 5.1 Methodology

Experiments were run using `scripts/test_model_improvements.py`, which downloads QT-172's `trainer_module.py` from GCS, applies targeted regex patches, and submits as Vertex AI Custom Jobs reusing QT-172's Transform/Schema artifacts. This allowed ~15 min iteration per experiment instead of ~1.5 hours for a full pipeline.

**Baseline**: QT-172 (`strict_time` split, 100 epochs, batch_size=4096, LR=0.001).

### 5.2 Results

#### Round 1

| Experiment | Change | Epochs | R@5 | R@10 | R@50 | R@100 | Val Loss |
|---|---|---|---|---|---|---|---|
| **QT-172** (baseline) | — | 100 | **17.0%** | **24.5%** | **42.2%** | **51.6%** | 392,065 |
| **A**: L2-norm + temp=0.05 | Normalize + sharp softmax | 100 | 8.6% | 12.8% | 29.7% | 40.6% | 42,496 |
| **B**: EarlyStopping (val_loss, p=10) | Stop on val_loss | 11 | 0.5% | 1.1% | 5.2% | 12.1% | 64,644 |

**Exp A** reduced the overfitting gap dramatically (val_loss 42K vs 392K) but recall dropped across the board. Temperature 0.05 was hypothesized to be too aggressive, so round 2 tested warmer temperatures.

**Exp B** stopped at epoch 11 because `val_loss` was lowest at epoch 0 (before the model learned anything). With in-batch softmax on a small catalog, val_loss is a poor early stopping signal — it rises monotonically from epoch 1.

#### Round 2

| Experiment | Change | Epochs | R@5 | R@10 | R@50 | R@100 | Val Loss |
|---|---|---|---|---|---|---|---|
| **QT-172** (baseline) | — | 100 | **17.0%** | **24.5%** | **42.2%** | **51.6%** | 392,065 |
| **A2**: L2-norm + temp=0.2 | Warmer temperature | 100 | 8.9% | 12.0% | 25.2% | 33.6% | 32,331 |
| **A3**: L2-norm + temp=0.5 | Even warmer | 100 | 6.1% | 7.9% | 16.7% | 25.0% | 31,556 |
| **A4**: L2-norm + temp=1.0 | No sharpening | 100 | 3.3% | 5.4% | 14.8% | 22.3% | 31,654 |
| **B2**: EarlyStopping (loss, p=15) | Stop on train loss | 100 | 14.2% | 20.4% | 38.6% | 48.7% | 1,952,862 |

**Temperature sweep (A, A2, A3, A4)**: Warmer temperatures made recall **worse**, not better. The coldest temperature (0.05) had the highest recall of any L2-normalized variant. This rules out temperature tuning as the issue — **L2 normalization itself is the problem**.

**Exp B2**: EarlyStopping on train loss never triggered (train loss monotonically decreases across all experiments). The run completed all 100 epochs. Results are slightly below baseline, likely due to the `restore_best_weights=True` parameter restoring to a suboptimal checkpoint.

#### Round 3: Smaller Architecture

| Experiment | Change | Epochs | R@5 | R@10 | R@50 | R@100 | Val Loss |
|---|---|---|---|---|---|---|---|
| **QT-172** (baseline) | [256,128,64,32], emb 64/32 | 100 | 17.0% | 24.5% | 42.2% | 51.6% | 392,065 |
| **F**: Smaller towers | [128,64,32], emb 64/32 | 100 | 26.0% | 35.1% | 52.2% | 60.6% | 2,083,308 |
| **G**: Smaller embeddings | [256,128,64,32], emb 32/16 | 100 | 13.4% | 18.5% | 38.1% | 51.1% | 1,319,959 |
| **H**: Both combined | [128,64,32], emb 32/16 | 100 | 19.5% | 27.5% | 49.2% | 57.5% | 2,966,725 |

**Exp F** — R@5 +53% relative improvement (17.0% → 26.0%), R@100 +17% (51.6% → 60.6%). Removing the Dense(256) layer reduced model capacity just enough to prevent the worst memorization while keeping the expressive 64D/32D embeddings.

**Exp G** (smaller embeddings only) hurt recall — the 64D customer and 32D product embeddings carry important signal that shouldn't be compressed.

**Exp H** (combined) improved over baseline but underperformed F — the smaller embeddings partially offset the tower improvement.

#### Round 4: Tower Size Sweep

Exp F's success prompted a full tower depth sweep to find the optimal architecture:

| Experiment | Tower | Layers | R@5 | R@10 | R@50 | R@100 | Val Loss |
|---|---|---|---|---|---|---|---|
| **QT-172** (baseline) | [256, 128, 64, 32] | 4 | 17.0% | 24.5% | 42.2% | 51.6% | 392,065 |
| **F** | [128, 64, 32] | 3 | 26.0% | 35.1% | 52.2% | 60.6% | 2,083,308 |
| **F2** | **[64, 32]** | **2** | **35.6%** | **44.3%** | **60.8%** | **66.8%** | 2,584,987 |
| **F3** | [32] | 1 | 35.1% | 42.5% | 59.7% | 65.3% | 1,108,010 |

**Exp F2 [64, 32] is the optimal architecture.** Each layer removed improved recall until the single-layer F3, which was marginally worse. The Dense(64) layer provides essential non-linear mixing of the raw feature embeddings before projecting to 32D — removing it (F3) loses this transformation capacity.

The full tower sweep shows a clear trend — recall improves monotonically as tower depth decreases from 4 → 3 → 2 layers, then plateaus/slightly drops at 1 layer:

```
R@5 by tower depth:
  4 layers [256,128,64,32]: 17.0%  ████████▌
  3 layers [128,64,32]:     26.0%  █████████████
  2 layers [64,32]:         35.6%  █████████████████▊  ← optimal
  1 layer  [32]:            35.1%  █████████████████▌
```

### 5.3 Key Findings

#### Tower Depth Is the Dominant Factor (Exp F → F2 → F3)

The tower size sweep across 12 experiments revealed that **tower depth is the single most impactful parameter** for this model. The original [256, 128, 64, 32] architecture was massively over-parameterized for 976 products. Each Dense layer adds a multiplicative number of parameters that provide excess capacity for memorizing individual transactions rather than learning generalizable patterns.

The optimal architecture is **[64, 32]** — two Dense layers per tower. This provides:
- Dense(64): Non-linear mixing of raw feature embeddings (essential — removing it in F3 slightly hurt recall)
- Dense(32): Final projection to the 32D embedding space for dot-product scoring

The improvement from baseline to F2 is dramatic: **R@5 more than doubled** (17.0% → 35.6%), **R@100 up 29%** (51.6% → 66.8%). This was achieved purely by removing layers — no new techniques, no hyperparameter changes, no additional data.

#### L2 Normalization Hurts Recall (Disproven Hypothesis)

The theoretical analysis in Section 4.1 predicted L2 normalization would be the "highest impact" improvement, citing CLIP, SimCLR, and production retrieval systems. **The experiments conclusively disproved this for our setting.**

**Why it failed**: The baseline model's "overfitting" (huge val_loss gap) is actually the model **memorizing useful co-occurrence patterns** that generalize to test-set recall. With only 976 products and ~90K transactions, the model benefits from encoding strong per-customer and per-product signals in embedding magnitudes. L2 normalization destroys this information by projecting all embeddings onto the unit sphere, forcing the model to rely solely on angular relationships between embeddings — which are less expressive for a small catalog.

**Why CLIP/SimCLR are different**: Those systems operate on millions of unique items (images, text) where magnitude-based memorization is impossible. The normalization constraint helps them learn generalizable semantic features. With 976 products, our model can and should memorize product-level patterns.

The val_loss reduction (392K → 32-42K) looks like an improvement but is misleading — it reflects the model being **less confident**, not more accurate. Lower confidence produces lower loss but worse rankings.

#### Embedding Dimensions Should Stay Large

Exp G (customer 64→32, product 32→16) degraded recall, while Exp F kept embeddings at 64/32 and improved. The embeddings are the model's primary information carriers — compressing them loses signal. This is consistent with the small-catalog regime: with only 976 products, the model needs expressive per-product embeddings to capture nuanced relationships.

#### Early Stopping Has No Valid Signal

Neither `val_loss` nor `loss` works as an early stopping monitor for this model:

- **`val_loss`** rises from epoch 1 — stopping early means stopping before learning (Exp B: 0.5% R@5)
- **`loss`** monotonically decreases — early stopping never triggers (Exp B2: ran all 100 epochs)

A proper early stopping signal would be `val_recall_at_K`, but this requires FactorizedTopK metrics during training, which the current architecture avoids due to serialization issues with `tf.data.Dataset.map()` and stateful Embedding layers.

#### Val Loss Is Decoupled From Recall

Across all 12 experiments, the models with the **worst** val_loss (H: 3.0M, F2: 2.6M) have the **best** recall. The models with the **best** val_loss (A3: 31.5K) have the worst recall. This confirms the TFRS Issue #263 observation: val_loss measures softmax confidence, recall measures ranking order. For retrieval, **ranking order is what matters**. Val loss should not be used to compare models or guide architecture decisions.

### 5.4 Summary: What Works and What Doesn't

| Change | R@5 | vs Baseline | Verdict |
|---|---|---|---|
| **Tiny towers [64, 32]** | **35.6%** | **+109%** | **Best — optimal tower depth** |
| Minimal towers [32] | 35.1% | +106% | Near-optimal, but Dense(64) mixing helps |
| Smaller towers [128, 64, 32] | 26.0% | +53% | Good, but not deep enough cut |
| Smaller towers + smaller embeddings | 19.5% | +15% | Smaller embeddings dilute the gain |
| Baseline [256, 128, 64, 32] | 17.0% | — | Over-parameterized |
| EarlyStopping (train loss) | 14.2% | -16% | Never triggers; restore_best_weights hurts |
| Smaller embeddings only | 13.4% | -21% | Hurts — embeddings carry important signal |
| L2-norm + temp=0.2 | 8.9% | -48% | L2-norm destroys magnitude-based patterns |
| L2-norm + temp=0.05 | 8.6% | -49% | Same — temperature doesn't help |
| L2-norm + temp=0.5 | 6.1% | -64% | Worse with warmer temperature |
| L2-norm + temp=1.0 | 3.3% | -81% | Worst — no sharpening + no magnitudes |
| EarlyStopping (val_loss) | 0.5% | -97% | Stops at epoch 11 before learning |

---

## 6. Next Steps

### 6.1 Adopt [64, 32] Tower as New Default

Exp F2's [64, 32] tower architecture should become the new baseline. Create a new `mod_retr_v7` via ModelConfig UI:

| Parameter | v6 (current) | v7 (proposed) |
|---|---|---|
| Tower layers | [256, 128, 64, 32] | **[64, 32]** |
| Embedding dims | customer=64, product=32 | customer=64, product=32 (keep) |
| L2 regularization | 0.02 on first 2 layers | 0.02 on Dense(64) |
| Everything else | Same | Same |

Run a full Quick Test with `strict_time` split to confirm the improvement holds through the full pipeline (not just patched Custom Jobs).

### 6.2 Further Tuning on Top of F2

The F2 result (R@5=35.6%, R@100=66.8%) is the new baseline. Next experiments should tune on top of it:

| Parameter | Current (F2) | Experiments to Try | Rationale |
|---|---|---|---|
| **Dropout** | 0.0 | 0.1, 0.2 between Dense(64) and Dense(32) | Additional regularization on the 2-layer tower |
| **L2 regularization** | 0.02 on Dense(64) | 0.01, 0.05; also try on Dense(32) | May need less/more reg with fewer layers |
| **Learning rate** | 0.001 | 0.0005, 0.002 | Smaller model may tolerate different LR |
| **Batch size** | 4096 | 2048 | Different in-batch negative distribution |
| **Epochs** | 100 | 150, 200 | Smaller model may need longer to converge |

These are all configurable via ModelConfig UI or via the experiment script.

### 6.3 Deferred (Disproven or Low Priority)

| Change | Status | Notes |
|---|---|---|
| L2 normalization | **Tested, hurts recall** | Destroys magnitude-based patterns for small catalogs |
| Temperature scaling | **Tested, hurts recall** | Only meaningful with L2-norm |
| Smaller embeddings | **Tested, hurts recall** | Embeddings carry important signal at 64/32D |
| EarlyStopping | **Tested, no valid signal** | val_loss and loss both fail as monitors |
| Label smoothing | Not tested standalone | Lower priority given F2 success |
| Hard negatives | Not tested standalone | Lower priority given F2 success |
| FactorizedTopK metrics | Not implemented | Would enable val_recall early stopping |

### 6.4 Experiment Tooling

The `scripts/test_model_improvements.py` script proved valuable for fast iteration (~15 min/experiment vs ~1.5 hr for full pipeline). It can be reused for future experiments by:
- Adding new patch functions for whatever changes need testing
- Using `--dry-run` to validate patches before submitting
- Running CPU jobs in `europe-central2` (default) to avoid GPU costs for small datasets

---

## 7. Experiment Artifacts

### 7.1 GCS Paths

| Experiment | Result | Artifacts |
|---|---|---|
| QT-172 (baseline) | R@5=17.0% | `gs://b2b-recs-quicktest-artifacts/qt-172-20260227-153721/` |
| A: L2+temp=0.05 | R@5=8.6% | `gs://b2b-recs-quicktest-artifacts/improvement-A-l2-norm-temp-20260228-124031/` |
| B: EarlyStopping val_loss | R@5=0.5% | `gs://b2b-recs-quicktest-artifacts/improvement-B-early-stopping-20260228-124107/` |
| A2: L2+temp=0.2 | R@5=8.9% | `gs://b2b-recs-quicktest-artifacts/improvement-A2-l2-norm-temp02-20260228-132152/` |
| A3: L2+temp=0.5 | R@5=6.1% | `gs://b2b-recs-quicktest-artifacts/improvement-A3-l2-norm-temp05-20260228-132157/` |
| A4: L2+temp=1.0 | R@5=3.3% | `gs://b2b-recs-quicktest-artifacts/improvement-A4-l2-norm-temp10-20260228-132159/` |
| B2: EarlyStopping train loss | R@5=14.2% | `gs://b2b-recs-quicktest-artifacts/improvement-B2-earlystop-trainloss-20260228-132232/` |
| F: 3-layer towers | R@5=26.0% | `gs://b2b-recs-quicktest-artifacts/improvement-F-smaller-towers-20260228-141314/` |
| G: Smaller embeddings | R@5=13.4% | `gs://b2b-recs-quicktest-artifacts/improvement-G-smaller-embeddings-20260228-141318/` |
| H: Both combined | R@5=19.5% | `gs://b2b-recs-quicktest-artifacts/improvement-H-smaller-all-20260228-141319/` |
| **F2: 2-layer towers** | **R@5=35.6%** | `gs://b2b-recs-quicktest-artifacts/improvement-F2-tiny-towers-20260228-151314/` |
| F3: 1-layer tower | R@5=35.1% | `gs://b2b-recs-quicktest-artifacts/improvement-F3-minimal-towers-20260228-154405/` |

### 7.2 Vertex AI Job IDs

| Experiment | Job ID | Region |
|---|---|---|
| A2 | `122137050148241408` | europe-central2 |
| A3 | `5383467314823823360` | europe-central2 |
| A4 | `2323552843002281984` | europe-central2 |
| B2 | `6501485922318548992` | europe-central2 |
| F | `778818170814201856` | europe-central2 |
| G | `7727872395846877184` | europe-central2 |
| H | `5944446943408160768` | europe-central2 |
| F2 | `2391951262342971392` | europe-central2 |
| F3 | `4963506649571524608` | europe-central2 |

### 7.3 Script

`scripts/test_model_improvements.py` — downloads QT-172's trainer, applies patches, submits Custom Jobs. Supports `--experiment A/B/.../F/F2/F3/G/H`, `--dry-run`, `--gpu`, `--epochs`, `--lr`.

---

## 8. References

### TFRS Documentation

- [tfrs.tasks.Retrieval API](https://www.tensorflow.org/recommenders/api_docs/python/tfrs/tasks/Retrieval) — constructor parameters, call signature
- [TFRS Basic Retrieval Tutorial](https://www.tensorflow.org/recommenders/examples/basic_retrieval) — canonical two-tower example
- [TFRS Deep Recommenders Tutorial](https://www.tensorflow.org/recommenders/examples/deep_recommenders) — adding dense layers, regularization

### TFRS Source Code

- [`tensorflow_recommenders/tasks/retrieval.py`](https://github.com/tensorflow/recommenders/blob/main/tensorflow_recommenders/tasks/retrieval.py) — loss implementation, temperature, hard negatives
- [`tensorflow_recommenders/layers/loss.py`](https://github.com/tensorflow/recommenders/blob/main/tensorflow_recommenders/layers/loss.py) — `HardNegativeMining`, `RemoveAccidentalHits`

### TFRS GitHub Issues (Relevant Discussions)

- [Issue #633](https://github.com/tensorflow/recommenders/issues/633) — Temperature tuning impact (25% → 50% Hit Rate@10). **Note**: This result was for a large catalog; our 976-product catalog behaves differently.
- [Issue #263](https://github.com/tensorflow/recommenders/issues/263) — Val loss vs. retrieval metric divergence. **Confirmed by our experiments** — val_loss and recall are inversely correlated.
- [Issue #489](https://github.com/tensorflow/recommenders/issues/489) — Label smoothing + `remove_accidental_hits` incompatibility
- [Issue #140](https://github.com/tensorflow/recommenders/issues/140) — In-batch vs. sampled softmax discussion (TFRS maintainer: "in-batch softmax is definitely a very successful strategy")
- [Issue #134](https://github.com/tensorflow/recommenders/issues/134) — Increasing validation loss pattern

### Industry Systems

- **CLIP / SimCLR** — L2-normalized embeddings + learned temperature. Works at scale (millions of items). **Not directly applicable** to small-catalog retrieval.
- **Snapchat Spotlight** — [Two-tower with L2-normalized outputs](https://eng.snap.com/embedding-based-retrieval). Large catalog, different regime.
- **YouTube DNN** — [Deep Neural Networks for YouTube Recommendations](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/) (Covington et al., 2016). In-batch softmax with importance weighting for sampling correction.
- **Shaped.ai** — [Two-Tower Model Deep Dive](https://www.shaped.ai/blog/the-two-tower-model-for-recommendation-systems-a-deep-dive). Comprehensive overview of loss variants, temperature, hard negatives.

### Project Reference

- `past/recommenders.ipynb` — Google's TFX+TFRS tutorial (MovieLens 100K). Uses bare `tfrs.tasks.Retrieval()` with `Adagrad(0.1)` — shows the same val loss divergence pattern. No normalization, no temperature, no label smoothing. This is a minimal example, not a production recipe.
- `scripts/test_model_improvements.py` — Custom Job experiment runner used for this analysis.
