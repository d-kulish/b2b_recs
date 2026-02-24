# Ranking Model Improvement: Probability-to-Buy (Ternopil)

**Date**: 2026-02-24

## 1. Goal

Train a TFRS ranking model predicting **probability to buy** (binary label: bought / didn't buy) for the Ternopil dataset. Iteratively improve data quality, loss function, and architecture to achieve production-quality predictions.

---

## 2. Experiment History

### 2.1 Full Experiment Table

| ID | Dataset | Loss | Features | Rating Head | LR | Batch | Epochs | Tower L2 | Val RMSE | Test RMSE |
|---|---|---|---|---|---|---|---|---|---|---|
| **151** | v1 (all products) | BCE* | 5 prod feats (incl. name) | 128→64→32→1 | 0.001 | 4096 | 100 | 0.01 | 0.3407 | 0.3398 |
| **152** | v1 | MSE | 5 prod feats | 128(l2)→drop→64(l2)→drop→32→1 | 0.0005 | 4096 | 50 | 0.02 | 0.3331 | 0.3321 |
| **153** | v1 | MSE | 5 prod feats | 128(l2)→drop(0.1)→64(l2)→drop(0.1)→32→1 | 0.0007 | 4096 | 70 | 0.01 | 0.3366 | 0.3364 |
| **154** | v2 (top-80%) | BCE** | 4 prod feats (no name) | 128→64→32→1 | 0.001 | 1024 | 100 | 0.01 | — | — |
| **155** | v2 | BCE | 4 prod feats | 128→64→32→1 | 0.001 | 1024 | 100 | 0.01 | 0.4379 | 0.4370 |
| **156** | v2 | **MSE** | 4 prod feats | 128→64→32→1 | 0.001 | 1024 | 100 | 0.01 | **0.2988** | **0.2979** |
| **157** | v2 | MSE | 5 prod feats (name back) | 128(l2)→drop(0.1)→64(l2)→drop(0.1)→32→1 | 0.001 | 2048 | 100 | 0.01 | **0.2954** | **0.2961** |
| **158** | v2 | MSE | 5 prod feats | **64(l2)→drop(0.1)→32→1** | 0.001 | 2048 | 100 | 0.01 | *running* | *running* |

*QT-151/155 BCE: used `Reduction.SUM` (bug) initially; QT-155 ran after the fix with auto class weights (~4.0).*
*QT-154: ran with `Reduction.SUM` bug, exploded (RMSE 15.0). Ignore.*

### 2.2 Key Transitions

- **QT-151 → QT-155**: Changed 3 things at once (v2 data, BCE fix, class weights) → RMSE degraded 0.34 → 0.44. Model collapsed to constant ~0.38 prediction.
- **QT-155 → QT-156**: Switched BCE back to MSE (no class weights) → RMSE improved to 0.298. Confirmed BCE + class weights was the primary problem.
- **QT-156 → QT-157**: Added dropout (0.1), L2 on rating head (0.01), `name` feature back, batch 2048 → marginal improvement (0.298 → 0.295). Overfitting pattern unchanged.
- **QT-157 → QT-158**: Reduced rating head from 128→64→32→1 to **64→32→1** (match input dimension). Currently running.

---

## 3. Analysis and Findings

### 3.1 BCE + Class Weights Caused Model Collapse (QT-155)

With v2 data having 20% positives, the auto-computed class weight was `(1 - 0.20) / 0.20 = 4.0`. This meant 80% of total loss came from positives (20% of samples x 4.0 weight), causing the model to push all predictions toward ~0.38 — the value that minimizes weighted BCE.

RMSE 0.44 matches the theoretical RMSE of predicting a constant 0.38 on 20% positive data. The model effectively stopped learning.

**Root cause**: class weights optimize for **balanced recall**, but RMSE evaluates **prediction magnitude accuracy**. These objectives directly conflict.

**Code issue**: `USE_CLASS_WEIGHTS` is hardcoded as `True` whenever `loss_function == 'binary_crossentropy'` in `ml_platform/configs/services.py`. There is no way to use BCE without class weights.

### 3.2 v1 Data Made the Problem Artificially Easy

The v1 BigQuery views (`sql/create_ternopil_prob_train_view.sql`) sampled negatives from all ~3,186 products. The downstream top-80% revenue filter then removed ~2/3 of negatives (tail products) while keeping most positives. This distorted the intended 1:4 ratio:

- v1 train: ~1:2 ratio (31% positive), v1 test: ~1:1.2 (45% positive)
- v2 train/test: 1:4 ratio (20% positive) as intended

v1 negatives were also **easy** (obscure tail products distinguishable by popularity alone). v2 negatives come from the same popular product pool — the model must learn actual customer-product affinity.

QT-151's RMSE 0.34 was partially inflated by these easier conditions.

### 3.3 MSE on v2 Data Works Well (QT-156)

Switching to MSE on v2 data achieved RMSE 0.298 — **0.10 below the theoretical baseline of 0.40** for 20% positive binary data. This confirms:
- The v2 data is valid and learnable
- MSE directly optimizes the evaluation metric (RMSE)
- No class weights needed for 1:4 imbalance

### 3.4 Regularization Alone Does Not Fix Overfitting (QT-157)

Adding dropout (0.1) and L2 (0.01) to the rating head in QT-157 produced marginal improvement (0.298 → 0.295) but the overfitting pattern persists: train loss drops to ~0.04 while val loss rises from ~0.07 to ~0.10.

**QT-157 training curve:**
```
Epoch  Train   Val     Val RMSE  Val MAE
  0    ~0.10   ~0.08   0.295     0.149
  5    ~0.06   ~0.07   0.280     0.140
 50    ~0.05   ~0.09   0.290     0.125
 99    ~0.06   ~0.08   0.295     0.137
```

The useful signal is learned in ~5 epochs. Everything after is memorization.

### 3.5 Rating Head Architecture Mismatch (Primary Overfitting Cause)

The buyer and product towers each output 32-dim embeddings, concatenated into a **64-dim input** to the rating head. But the rating head starts with **Dense(128)** — a 2x expansion:

```
Towers: 32 + 32 = 64-dim ──→ Rating head: Dense(128) → Dense(64) → Dense(32) → Dense(1)
                                            ↑
                                            64 inputs → 128 outputs = expansion
```

This creates 128 x 64 = 8,192 parameters in the first layer alone for only 64 input dimensions. The excess capacity enables memorization of specific (customer_id, product_id) pairs through the embedding space. On validation data with unseen pairs, this memorization doesn't help.

**Fix**: the rating head should funnel down from the input dimension, not expand:
- `64 → 32 → 1` (QT-158, currently running)
- Or `64 → 64 → 32 → 1` (match then narrow)

### 3.6 Deterministic Negatives Enable Memorization

The FARM_FINGERPRINT-based negative sampling produces the **exact same** negatives every time the view is queried. Across 100 epochs, the model sees identical (customer, product, label=0) tuples every epoch. It can memorize "Customer A + Product X → 0" as a lookup instead of learning generalizable patterns.

Dynamic negative re-sampling (different negatives per epoch) would force the model to learn general customer-product affinity. However, this requires significant changes to the TFX pipeline (ExampleGen materializes data once as TFRecords before training starts).

---

## 4. Resolved Issues

| Issue | Introduced | Fixed | How |
|---|---|---|---|
| `Reduction.SUM` in loss | QT-154 | Commit `a28ad98` | Changed to default `SUM_OVER_BATCH_SIZE` |
| v1 ratio distortion (1:4 → 1:2) | QT-151 | Commit `234cb5a` | v2 views bake top-80% filter before sampling |
| BCE + class weights collapse | QT-155 | QT-156 | Switched to MSE (no class weights) |

---

## 5. Open Issues

### 5.1 Rating Head Over-Capacity
**Status**: QT-158 running with fix (64→32→1 instead of 128→64→32→1).
Expected to reduce overfitting by eliminating the dimension expansion.

### 5.2 `USE_CLASS_WEIGHTS` Hardcoded to BCE
In `ml_platform/configs/services.py`, `USE_CLASS_WEIGHTS` auto-enables when `loss_function == 'binary_crossentropy'`. Should be a separate `ModelConfig` toggle so BCE can be used without class weights.

### 5.3 No Classification Metrics for Binary Targets
The ranking model only reports RMSE/MAE. For binary targets (bought/didn't buy), **AUC-ROC** should be shown alongside RMSE/MAE. It measures ranking quality (can the model rank buyers above non-buyers?) which is what matters for recommendations.

Should be auto-detected: if target column has only 2 unique values (0/1), show AUC-ROC automatically. No new user-facing parameters needed.

### 5.4 No Prediction Distribution Logging
A histogram of model predictions would immediately reveal failure modes:
- Healthy: bimodal distribution (peaks near 0 and 1)
- Collapsed: single peak near 0.3-0.4 (what happened in QT-155)

### 5.5 Deterministic Negative Sampling
FARM_FINGERPRINT creates fixed negatives, enabling memorization across epochs. Dynamic re-sampling would improve generalization but requires pipeline changes (in-trainer sampling or large negative pool with per-epoch subsampling).

---

## 6. Recommendations and Next Steps

### 6.1 Immediate (based on QT-158 results)

1. **Evaluate QT-158** — if the smaller rating head (64→32→1) reduces overfitting while maintaining val RMSE ~0.29, this confirms the architecture mismatch as the primary overfitting cause
2. If QT-158 succeeds, try **even simpler**: `32→1` (single layer) as a baseline
3. If overfitting persists, try **reducing embedding_dim** from 32 to 16 or 8 to limit memorization capacity

### 6.2 Short-Term Code Changes

4. **Add AUC-ROC** to ranking model training metrics — auto-detect binary targets, no new user parameters
5. **Decouple `USE_CLASS_WEIGHTS`** from loss function — make it a separate ModelConfig toggle
6. **Add class weight dampening** options if class weights are re-enabled: `sqrt`, `log(1+x)`, or capped

### 6.3 Medium-Term Improvements

7. **Add generalizable features** that transfer to unseen (customer, product) pairs:
   - Customer purchase frequency per category
   - Product popularity percentile
   - Customer-brand affinity score
   - Recency (days since last purchase in category)
8. **Learning rate scheduling** — cosine decay or reduce-on-plateau to stabilize later epochs
9. **Prediction histogram logging** in MetricsCollector

### 6.4 Longer-Term

10. **Dynamic negative sampling** — per-epoch re-sampling in the tf.data pipeline
11. **End-to-end evaluation** — does the ranking model improve retrieval results?
12. **Multi-city evaluation** — test on cities beyond Ternopil

---

## Appendix A: Theoretical RMSE Baselines

For binary labels {0, 1} with positive proportion `p`, predicting a constant `p` gives RMSE = `sqrt(p * (1 - p))`. Any model above this baseline is not learning.

| p (positive rate) | Baseline RMSE | Context |
|---|---|---|
| 0.20 | 0.400 | **v2 data** |
| 0.31 | 0.463 | **v1 train (approx, after filter distortion)** |
| 0.45 | 0.497 | **v1 test (approx)** |

## Appendix B: File References

| File | Purpose |
|---|---|
| `sql/create_ternopil_prob_train_view.sql` | v1 train view (all products, ratio distortion after filtering) |
| `sql/create_ternopil_prob_test_view.sql` | v1 test view |
| `sql/create_ternopil_prob_train_v2_view.sql` | v2 train view (top-80% pre-filtered, true 1:4 ratio) |
| `sql/create_ternopil_prob_test_v2_view.sql` | v2 test view |
| `ml_platform/configs/services.py` | Code generator — loss function, class weights, rating head generation |
| `models/qt-151/trainer_module.py` | Generated trainer for QT-151 (MSE, v1 data) |
| `models/qt-152/trainer_module.py` | Generated trainer for QT-152 (MSE, dropout, stronger L2) |
| Commit `95afdf3` | BCE class weights and conditional `from_logits` |
| Commit `234cb5a` | v2 views with top-80% product filter |
| Commit `a28ad98` | `Reduction.SUM` fix |

## Appendix C: Key Commits

| Commit | Date | Change |
|---|---|---|
| `de7853b` | 2026-02-23 | v1 probability-to-buy views |
| `a28ad98` | 2026-02-23 | Fix `Reduction.SUM` → default reduction |
| `234cb5a` | 2026-02-23 | v2 views with top-80% product filter |
| `95afdf3` | 2026-02-23 | BCE class weights and conditional `from_logits` |
