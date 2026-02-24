# Ranking Model Experiment Analysis: QT-151 vs QT-155

## Document Purpose
Detailed post-mortem analysis of the ranking model degradation observed between experiments QT-151 (RMSE 0.34) and QT-155 (RMSE 0.44). Identifies root causes, provides data-backed evidence, and recommends concrete next steps.

**Date**: 2026-02-24

---

## 1. Context

The goal is to train a TFRS ranking model predicting **probability to buy** (binary label: bought / didn't buy) for the Ternopil dataset. Two key experiments were run:

- **QT-151** — first attempt, known data issues, relatively good results (RMSE 0.34)
- **QT-155** — after "fixing everything" (data ratio, BCE loss, class weights), results got significantly worse (RMSE 0.44)

Three changes were introduced between QT-151 and QT-155:
1. New v2 BigQuery views baking in the top-80% product filter
2. BCE loss fix (conditional `from_logits`, removed `Reduction.SUM`)
3. Automatic class weights for imbalanced binary labels

---

## 2. Experiment Configurations Compared

### 2.1 Saved Local Experiments (QT-151 and QT-152)

Both QT-151 and QT-152 are saved in `models/qt-151/` and `models/qt-152/`. They both use **v1 views** and **MSE loss** (no BCE, no class weights). QT-155 is not saved locally — it was run through the platform with the post-fix code.

| Parameter | QT-151 | QT-152 | QT-155 (inferred) |
|---|---|---|---|
| Feature Config | feat_rank_prob_v1 (ID: 32) | feat_rank_prob_v1 (ID: 32) | feat_rank_prob_v1 (ID: 32) |
| Model Config | mod_rank_prob_v1 (ID: 25) | mod_rank_prob_v2 (ID: 26) | mod_rank_prob_v2 (ID: 26) |
| Dataset | rank_prob_v1 (ID: 37) | rank_prob_v1 (ID: 37) | **rank_prob_v2** (v2 views) |
| Loss Function | **MSE** | **MSE** | **BCE** |
| Class Weights | None | None | **Auto (~4.0)** |
| `from_logits` | N/A (MSE) | N/A (MSE) | False (sigmoid detected) |
| Reduction | Default | Default | Default |
| Epochs | 100 | 50 | ~50-100 |
| Learning Rate | 0.001 | 0.0005 | 0.0005 |
| Batch Size | 4096 | 4096 | 4096 |
| Optimizer | Adam | Adam | Adam |
| L2 (towers) | 0.01 | 0.02 | 0.02 |
| Rating Head | Dense(128)→Dense(64)→Dense(32)→Dense(1,sigmoid) | Dense(128,l2)→Drop(0.2)→Dense(64,l2)→Drop(0.2)→Dense(32)→Dense(1,sigmoid) | Dense(128,l2)→Drop(0.2)→Dense(64,l2)→Drop(0.2)→Dense(32)→Dense(1,sigmoid) |
| Output Activation | sigmoid | sigmoid | sigmoid |

### 2.2 Results Compared

| Metric | QT-151 | QT-152 | QT-155 |
|---|---|---|---|
| Test RMSE | **0.3398** | 0.3321 | **~0.44** |
| Test MAE | **0.1890** | 0.2097 | **~0.26** |
| Val RMSE | 0.3407 | 0.3331 | ~0.44 |
| Val MAE | 0.1892 | 0.2094 | ~0.26 |
| Converged? | Yes (100 epochs) | Yes (50 epochs) | Unclear |

### 2.3 Key Differences: QT-151 vs QT-152

QT-152 introduced dropout (0.2) in the rating head, stronger L2 (0.02), and lower LR (0.0005). The RMSE improved slightly (0.3398 → 0.3321) but MAE degraded (0.1890 → 0.2097), suggesting slightly wider prediction spread with more regularization.

---

## 3. Data Analysis

### 3.1 View Definitions

**v1 views** (`sql/create_ternopil_prob_train_view.sql`):
- Product catalog: **all ~3,186 products** from the full Ternopil table
- Positive examples: all (customer, product) transaction pairs
- Negative sampling: 1:4 per customer from the full product catalog
- No product revenue filtering

**v2 views** (`sql/create_ternopil_prob_train_v2_view.sql`):
- Product catalog: restricted to **top 80% products by cumulative revenue** (~981 products)
- Positive examples: filtered to top-80% products only
- Negative sampling: 1:4 per customer from top-80% products only
- The `top_products` CTE uses window-function cumulative revenue threshold

### 3.2 How the v1 Ratio Got Distorted

The v1 view sampled 1:4 across all 3,186 products. But the downstream **Dataset config** applied a top-80% revenue filter, keeping only ~981 products. This filter had asymmetric impact:

- **Positives** (transactions): concentrated on popular products → most survived the filter
- **Negatives** (sampled from all 3,186): many were from tail products → ~2/3 removed

Result: the intended 1:4 ratio was distorted to approximately:
- **Train set**: ~1:2 (roughly 31% positive)
- **Test set**: ~1:1.2 (roughly 45% positive)

### 3.3 How v2 Fixes the Ratio

The v2 views bake the top-80% filter into the `product_catalog` CTE before negative sampling. Both positives and negatives come from the same ~981 products. The 1:4 ratio is preserved end-to-end:
- **Train set**: 1:4 (20% positive)
- **Test set**: 1:4 (20% positive)

### 3.4 Negative Quality Difference

This is a critical but subtle change:

| Aspect | v1 negatives | v2 negatives |
|---|---|---|
| Pool | All 3,186 products | Top-80% (~981 products) |
| Difficulty | **Easy** — many obscure tail products | **Hard** — all popular, relevant products |
| Overlap with positives | Low (tail products rarely purchased) | High (popular products frequently purchased) |

v2 negatives are **harder to distinguish from positives** because they come from the same popular product set. The model must learn finer-grained customer-product affinity instead of relying on product popularity as a shortcut.

---

## 4. Theoretical RMSE Baselines

For binary labels {0, 1} with proportion `p` of positives, the **optimal constant prediction** is `p`, giving RMSE = `sqrt(p * (1-p))`. Any model worse than this is not learning.

| Strategy | v1 actual (~31% pos) | v1 test (~45% pos) | v2 (20% pos) |
|---|---|---|---|
| Predict the mean (optimal constant) | 0.463 | 0.497 | **0.400** |
| Always predict 0.30 | 0.458 | 0.510 | 0.412 |
| Always predict 0.35 | 0.464 | 0.504 | 0.427 |
| Always predict 0.40 | 0.478 | 0.505 | **0.447** |
| Always predict 0.50 | 0.500 | 0.500 | 0.500 |

**Key findings:**
- QT-151 achieved 0.34 vs baseline 0.46 → model learned **0.12 RMSE below baseline** — strong learning
- QT-151 test RMSE 0.34 vs test baseline 0.50 → even stronger result on near-balanced test data
- QT-155 achieved ~0.44 vs baseline 0.40 → model is **0.04 RMSE above baseline** — **worse than a constant**
- QT-155's RMSE of 0.44 corresponds to a model predicting ~0.38 for everything — the model has collapsed

---

## 5. Root Cause Analysis

Three factors compounded to produce the degradation, in order of impact:

### 5.1 Root Cause #1: Class Weight Overcompensation (Critical)

**Mechanism:** With 20% positives in v2 data, the auto-computed class weight is:

```
label_mean = 0.20
pos_class_weight = (1.0 - 0.20) / 0.20 = 4.0
```

This means in `compute_loss()`:
- Each positive sample's loss is multiplied by **4.0**
- Each negative sample's loss is multiplied by 1.0
- Effective loss contribution: 20% of samples × 4.0 weight = **80% of total loss** from positives

**Effect:** The model is **4x more penalized for false negatives than false positives**. With sigmoid output (bounded [0, 1]), the safest strategy is to push all predictions higher (toward 0.35-0.50) to minimize the weighted loss on positives. This explains predictions clustering around ~0.38 and RMSE = 0.44.

**Evidence:** RMSE 0.44 matches the theoretical RMSE of a model predicting ~0.38-0.40 for everything (see table above). The model has effectively collapsed to a near-constant output.

**Why this is a fundamental problem:** Class weights optimize for **balanced accuracy / recall**, but RMSE penalizes deviation from the true label. These objectives directly conflict — class weights pull predictions toward the decision boundary (0.5), while RMSE wants predictions near 0 for negatives and near 1 for positives.

### 5.2 Root Cause #2: v2 Data is Genuinely Harder

**Smaller negative pool → harder negatives:**
v1 negatives from 3,186 products included many irrelevant tail products. The model could achieve good RMSE by learning a simple "popular product = likely positive" heuristic. v2 negatives from 981 top products force the model to learn actual customer-product affinity.

**Lower baseline → less headroom:**
v2's lower positive rate (20%) gives baseline RMSE 0.40 vs v1's 0.46. There is inherently less room for the model to improve beyond the baseline.

**Consistent test ratio:**
v1's test set had ~45% positives (nearly balanced), making it easy to score well. v2's test set maintains 1:4, which is harder and more representative of production.

### 5.3 Root Cause #3: Loss Function Change (MSE → BCE)

QT-151/152 used **MSE** which directly optimizes for RMSE (the evaluation metric). Switching to **BCE** optimizes for log-likelihood of the binary labels — a different objective.

For binary labels:
- **MSE** gradient: `2 * (prediction - label)` — linear, proportional to error magnitude
- **BCE** gradient: `(prediction - label) / (prediction * (1 - prediction))` — stronger near 0 and 1, weaker near 0.5

BCE with sigmoid naturally pushes predictions toward the extremes (0 or 1), which is good for classification but not necessarily for RMSE. Combined with class weights, the interaction becomes pathological.

---

## 6. Compounding Effect

The three changes interact multiplicatively:

```
v2 data (harder negatives)
  × BCE loss (different gradient dynamics)
  × Class weight 4.0 (massive positive overweighting)
  = Model collapse to constant ~0.38 prediction
```

Any single change might have been tolerable. All three simultaneously created a pathological training dynamic.

---

## 7. Why QT-151 Looked Surprisingly Good

QT-151's results (RMSE 0.34) were partially inflated by the v1 data distortion:

1. **Easy negatives** from tail products → model could separate by product popularity alone
2. **Near-balanced test set** (~45% positive) → lower bar for good RMSE
3. **MSE loss aligned with metric** → direct optimization of the evaluation target
4. **No class weights** → no prediction bias

The v1 "bugs" were accidentally making the problem easier. Fixing them exposed the true difficulty of the task.

---

## 8. Recommendations

### 8.1 Immediate Experiments (Priority Order)

#### Experiment A: MSE on v2 data (control experiment)
**Goal:** Isolate whether the problem is the data or the loss function.

```
Loss: MSE (no class weights)
Data: v2 views (1:4 ratio)
Everything else same as QT-152
```

Expected: RMSE ~0.38-0.42. If close to 0.40, the harder v2 data is the dominant factor. If much better, the loss/weights are the problem.

#### Experiment B: BCE on v2 data, NO class weights
**Goal:** Test whether BCE alone (without class weights) works.

```
Loss: BCE (from_logits=False, since sigmoid output)
Class weights: DISABLED (USE_CLASS_WEIGHTS = False)
Data: v2 views (1:4 ratio)
```

Expected: Should perform better than QT-155. The 1:4 ratio is moderate imbalance — BCE handles it fine without reweighting. Most real-world classifiers train on far worse imbalance (1:100) without class weights.

#### Experiment C: BCE with dampened class weights
**Goal:** Test milder class weight formulas.

```
Loss: BCE
Class weight: sqrt((1-p)/p) = sqrt(4.0) = 2.0 instead of 4.0
Data: v2 views
```

Three dampening options to try:
- `sqrt`: `sqrt(4.0) = 2.0`
- `log`: `log(1 + 4.0) = 1.61`
- `capped`: `min(pos_class_weight, 2.0)`

### 8.2 Code Changes

#### A. Add class weight dampening option to code generator

In `ml_platform/configs/services.py`, the class weight computation in `_generate_run_fn_ranking()` currently uses:
```python
pos_class_weight = (1.0 - label_mean) / max(label_mean, 1e-7)
```

Add a dampening strategy (could be a ModelConfig parameter):
```python
# Dampen class weight to avoid over-correction
raw_weight = (1.0 - label_mean) / max(label_mean, 1e-7)
pos_class_weight = math.sqrt(raw_weight)  # Geometric dampening
```

#### B. Add option to disable class weights with BCE

Currently `USE_CLASS_WEIGHTS` is automatically True when loss is BCE. Consider making it a separate ModelConfig toggle so BCE can be used without class weights.

#### C. Consider Focal Loss as an alternative to weighted BCE

Focal Loss naturally down-weights easy examples and focuses on hard ones, without the blunt instrument of class weights:
```python
focal_loss = -alpha * (1 - p_t)^gamma * log(p_t)
```
With `gamma=2.0` and `alpha=0.25`, this achieves class-aware training without collapsing predictions.

### 8.3 Evaluation Metric Improvements

#### A. Add AUC-ROC and F1 to ranking metrics

RMSE/MAE are regression metrics. For binary classification, also track:
- **AUC-ROC** — measures ranking quality regardless of threshold
- **AUC-PR** — better metric for imbalanced data
- **F1 at optimal threshold** — classification quality

This would show whether QT-155 is actually a better **classifier** despite worse RMSE.

#### B. Log prediction distribution

Add histogram of predictions to the training metrics. This would immediately reveal the "collapsed to constant" failure mode:
- Healthy model: bimodal distribution (peaks near 0 and near 1)
- Collapsed model: single peak near 0.3-0.4

### 8.4 Architecture Improvements for v2 Data

The harder v2 negatives require the model to learn finer-grained patterns:

1. **Cross-features between towers** — add explicit buyer-product interaction features before the rating head (e.g., category affinity scores)
2. **Wider rating head** — increase from Dense(128→64→32) to Dense(256→128→64) to add capacity for harder discrimination
3. **Attention mechanism** — replace simple concatenation with a dot-product attention between tower embeddings
4. **Feature engineering** — add derived features like:
   - Customer purchase frequency in each category
   - Product popularity percentile
   - Customer-brand affinity score

---

## 9. Next Steps

### Phase 1: Controlled Experiments (immediate)

1. **Download QT-155 artifacts** to `models/qt-155/` for local analysis (trainer_module.py, training_metrics.json, saved model)
2. Run **Experiment A** (MSE + v2 data) as the control
3. Run **Experiment B** (BCE + v2 data, no class weights) to test the hypothesis
4. Compare all three: QT-151 baseline, Experiment A, Experiment B

### Phase 2: Code Improvements (after Phase 1 confirms hypothesis)

5. Make class weights configurable (on/off/dampened) independent of loss function
6. Add AUC-ROC/AUC-PR to ranking model metrics
7. Add prediction histogram logging to `MetricsCollector`
8. Consider implementing Focal Loss as a fourth loss option

### Phase 3: Model Quality (after Phase 2)

9. Tune the best-performing loss configuration on v2 data
10. Experiment with wider architectures and cross-features
11. Evaluate on production-representative data (beyond Ternopil single city)

---

## Appendix A: QT-151 Training Curve

```
Epoch    Loss     Val RMSE   Val MAE    Val Loss
  0      0.161    0.4146     0.3543     0.1842
 10      0.081    0.3726     0.2523     0.1267
 25      0.077    0.3549     0.2092     0.1130
 50      0.085    0.3430     0.1990     0.1064
 75      0.074    0.3400     0.1917     0.1052
 99      0.069    0.3407     0.1892     0.1055
```

Training loss consistently decreased. Validation RMSE/MAE improved rapidly until ~epoch 50, then plateaued. No overfitting — val loss stable. Regularization loss dropped from 1.15 → 0.002, indicating L2 penalty was initially dominant then faded as weights shrunk.

## Appendix B: QT-152 Training Curve

```
Epoch    Loss     Val RMSE   Val MAE    Val Loss
  0      0.177    0.4227     0.3606     0.1753
 10      0.088    0.3726     0.2519     0.1263
 25      0.095    0.3507     0.2176     0.1155
 49      0.106    0.3331     0.2094     0.1093
```

Similar pattern but with higher regularization penalty initially (4.79 vs 1.15 in QT-151 due to L2=0.02 vs 0.01). Converging but likely needed more epochs — RMSE was still improving at epoch 49.

## Appendix C: Theoretical RMSE Reference

For binary labels with proportion `p` positive:

| p (positive rate) | Optimal Constant | Baseline RMSE | Interpretation |
|---|---|---|---|
| 0.10 | 0.10 | 0.300 | Highly imbalanced |
| 0.15 | 0.15 | 0.357 | |
| 0.20 | 0.20 | 0.400 | **v2 data** |
| 0.25 | 0.25 | 0.433 | |
| 0.31 | 0.31 | 0.463 | **v1 train (approx)** |
| 0.40 | 0.40 | 0.490 | |
| 0.45 | 0.45 | 0.497 | **v1 test (approx)** |
| 0.50 | 0.50 | 0.500 | Perfectly balanced |

Formula: `RMSE_baseline = sqrt(p * (1 - p))`

Any model achieving RMSE below the baseline is learning. A model above the baseline is worse than predicting a constant.

## Appendix D: File References

| File | Purpose |
|---|---|
| `models/qt-151/trainer_module.py` | Generated TFX module for QT-151 (MSE, no class weights) |
| `models/qt-151/training_metrics.json` | 100-epoch training history for QT-151 |
| `models/qt-152/trainer_module.py` | Generated TFX module for QT-152 (MSE, dropout, stronger L2) |
| `models/qt-152/training_metrics.json` | 50-epoch training history for QT-152 |
| `sql/create_ternopil_prob_train_view.sql` | v1 train view (all products, ratio distortion) |
| `sql/create_ternopil_prob_test_view.sql` | v1 test view (all products, ratio distortion) |
| `sql/create_ternopil_prob_train_v2_view.sql` | v2 train view (top-80% products, true 1:4 ratio) |
| `sql/create_ternopil_prob_test_v2_view.sql` | v2 test view (top-80% products, true 1:4 ratio) |
| `ml_platform/configs/services.py` | Code generator — BCE/class weight logic at lines 4297-4419 |
| Commit `95afdf3` | BCE class weights and conditional from_logits |
| Commit `234cb5a` | v2 views with top-80% product filter |
| Commit `a28ad98` | Reduction.SUM fix |
