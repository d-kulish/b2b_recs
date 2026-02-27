# Improving Retrieval Model Quality

**Date**: 2026-02-27
**Context**: QT-171 (`feat_retr_v6` + `mod_retr_v6`, `ternopil_train_v4`)
**Related**: `docs/phase_experiments.md` (History Feature Type section — taste vector design, validation, bug fixes)

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

## 5. Experiment Plan

### 5.1 Baseline (Control)

Re-run QT-171 config with `strict_time` split strategy to establish a valid baseline:

| Parameter | Value |
|---|---|
| Split strategy | `strict_time` |
| FeatureConfig | `feat_retr_v6` (FC#39) |
| ModelConfig | `mod_retr_v6` (MC#34) |
| Epochs | 100 |
| Everything else | Same as QT-171 |

### 5.2 Experiments (One Variable at a Time)

| # | Change from Baseline | What it tests |
|---|---|---|
| **E1** | `temperature=0.05` | Temperature alone |
| **E2** | L2-normalize outputs + `temperature=0.05` | Normalization + temperature |
| **E3** | `label_smoothing=0.1` | Label smoothing alone |
| **E4** | L2-normalize + `temperature=0.05` + `label_smoothing=0.1` | Combined |
| **E5** | E4 + `num_hard_negatives=10` | Add hard negative mining |
| **E6** | E4 + `Dropout(0.3, 0.2)` in towers | Add dropout |
| **E7** | E4 + early stopping (patience=10, restore_best_weights) | Stop before overfitting |

### 5.3 Success Criteria

Evaluate on `ternopil_test_v4` (temporal holdout) — the same data the inference notebook uses. Compare:

| Metric | QT-171 (notebook, 100% match) | Target |
|---|---|---|
| Recall@5 | 16.2% | > 20% |
| Recall@10 | 21.6% | > 28% |
| Recall@50 | 35.0% | > 45% |
| Recall@100 | 46.4% | > 55% |

Also monitor:
- Train/val loss gap at epoch 50 — should be < 3x (currently 12.6x)
- Convergence speed — better regularization may require more epochs to converge but produce better generalization

---

## 6. Implementation Scope

### 6.1 Changes to `TrainerModuleGenerator`

| Recommendation | Generator method | Scope |
|---|---|---|
| L2-normalize | `_generate_retrieval_model()` | Add `tf.math.l2_normalize` in `compute_loss()` |
| Temperature | `_generate_retrieval_model()` | Pass `temperature` param to `tfrs.tasks.Retrieval()` |
| Label smoothing | `_generate_retrieval_model()` | Pass custom loss to `tfrs.tasks.Retrieval()` |
| Hard negatives | `_generate_retrieval_model()` | Pass `num_hard_negatives` param |
| Dropout | `_generate_buyer_model()`, `_generate_product_model()` | Already supported via ModelConfig |
| Max-norm | `_generate_buyer_model()`, `_generate_product_model()` | Add `embeddings_constraint` to Embedding layers |
| Early stopping | `_generate_run_fn()` | Add EarlyStopping callback |
| `remove_accidental_hits` | `_generate_retrieval_model()` | Pass param + `candidate_ids` in `compute_loss()` |

### 6.2 Changes to `ModelConfig` (UI)

New fields (retrieval models only):

| Field | Type | Default | UI |
|---|---|---|---|
| `temperature` | float | `None` | Number input, tooltip explaining interaction with normalization |
| `label_smoothing` | float | `0.0` | Number input, range 0.0–0.5 |
| `l2_normalize_output` | bool | `false` | Toggle |
| `num_hard_negatives` | int | `None` | Number input |
| `remove_accidental_hits` | bool | `false` | Toggle |
| `early_stopping_patience` | int | `None` | Number input, 0 = disabled |

### 6.3 No Changes Needed

- Serve functions — normalization changes score magnitudes but not ranking order
- Transform — no preprocessing changes
- Dataset / ExampleGen — no data changes
- Feature Config — no feature changes

---

## 7. References

### TFRS Documentation

- [tfrs.tasks.Retrieval API](https://www.tensorflow.org/recommenders/api_docs/python/tfrs/tasks/Retrieval) — constructor parameters, call signature
- [TFRS Basic Retrieval Tutorial](https://www.tensorflow.org/recommenders/examples/basic_retrieval) — canonical two-tower example
- [TFRS Deep Recommenders Tutorial](https://www.tensorflow.org/recommenders/examples/deep_recommenders) — adding dense layers, regularization

### TFRS Source Code

- [`tensorflow_recommenders/tasks/retrieval.py`](https://github.com/tensorflow/recommenders/blob/main/tensorflow_recommenders/tasks/retrieval.py) — loss implementation, temperature, hard negatives
- [`tensorflow_recommenders/layers/loss.py`](https://github.com/tensorflow/recommenders/blob/main/tensorflow_recommenders/layers/loss.py) — `HardNegativeMining`, `RemoveAccidentalHits`

### TFRS GitHub Issues (Relevant Discussions)

- [Issue #633](https://github.com/tensorflow/recommenders/issues/633) — Temperature tuning impact (25% → 50% Hit Rate@10)
- [Issue #263](https://github.com/tensorflow/recommenders/issues/263) — Val loss vs. retrieval metric divergence
- [Issue #489](https://github.com/tensorflow/recommenders/issues/489) — Label smoothing + `remove_accidental_hits` incompatibility
- [Issue #140](https://github.com/tensorflow/recommenders/issues/140) — In-batch vs. sampled softmax discussion (TFRS maintainer: "in-batch softmax is definitely a very successful strategy")
- [Issue #134](https://github.com/tensorflow/recommenders/issues/134) — Increasing validation loss pattern

### Industry Systems

- **CLIP / SimCLR** — L2-normalized embeddings + learned temperature. SimCLR paper: "A Simple Framework for Contrastive Learning of Visual Representations" (Chen et al., 2020). Temperature is the single most important hyperparameter.
- **Snapchat Spotlight** — [Two-tower with L2-normalized outputs](https://eng.snap.com/embedding-based-retrieval). "We should keep the features from each side independent."
- **YouTube DNN** — [Deep Neural Networks for YouTube Recommendations](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/) (Covington et al., 2016). In-batch softmax with importance weighting for sampling correction.
- **Shaped.ai** — [Two-Tower Model Deep Dive](https://www.shaped.ai/blog/the-two-tower-model-for-recommendation-systems-a-deep-dive). Comprehensive overview of loss variants, temperature, hard negatives.

### Project Reference

- `past/recommenders.ipynb` — Google's TFX+TFRS tutorial (MovieLens 100K). Uses bare `tfrs.tasks.Retrieval()` with `Adagrad(0.1)` — shows the same val loss divergence pattern. No normalization, no temperature, no label smoothing. This is a minimal example, not a production recipe.
