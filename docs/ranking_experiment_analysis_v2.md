# Ranking Experiment Analysis v2: QT-151 vs QT-155

## Date: 2026-02-24

## 1. Problem Statement

Training a TFRS ranking model to predict **probability to buy** (binary label: bought/didn't buy) for the Ternopil dataset. Two experiments were run:

- **QT-151** — first attempt with known data issues, achieved **RMSE 0.34 / MAE 0.19**
- **QT-155** — after fixing data ratio, switching to BCE loss, and adding class weights, achieved **RMSE 0.44 / MAE 0.26**

Three changes were introduced simultaneously between QT-151 and QT-155:

1. New v2 BigQuery views baking the top-80% product filter into negative sampling
2. Loss function changed from MSE to BCE (with conditional `from_logits`, fixed `Reduction.SUM`)
3. Automatic class weights for imbalanced binary labels (pos_class_weight ~4.0)

The paradox: every individual change was a "fix" or "improvement", yet the combined result is significantly worse.

---

## 2. Analysis Performed

### 2.1 Codebase and Documentation Review

- Project architecture: `README.md`, `docs/phase_experiments.md`, `docs/phase_configs.md`
- Code generation: `ml_platform/configs/services.py` — `TrainerModuleGenerator` class, specifically ranking model generation (`_generate_ranking_model`, `_generate_run_fn_ranking`)
- Experiment models: `ml_platform/models.py` — `QuickTest`, `ModelConfig`, `FeatureConfig`, `Dataset`
- Training infrastructure: `ml_platform/training/models.py`, `ml_platform/training/services.py`

### 2.2 Training History Comparison

Analyzed saved trainer modules and training metrics:

- `models/qt-151/trainer_module.py` and `models/qt-151/training_metrics.json` (100 epochs)
- `models/qt-152/trainer_module.py` and `models/qt-152/training_metrics.json` (50 epochs)
- QT-155 not saved locally — run through the platform with post-fix code

### 2.3 Experiment Configurations Compared

| Parameter | QT-151 | QT-152 | QT-155 (inferred) |
|---|---|---|---|
| Feature Config | feat_rank_prob_v1 (ID: 32) | feat_rank_prob_v1 (ID: 32) | feat_rank_prob_v1 (ID: 32) |
| Model Config | mod_rank_prob_v1 (ID: 25) | mod_rank_prob_v2 (ID: 26) | mod_rank_prob_v2 (ID: 26) |
| Dataset | rank_prob_v1 (ID: 37, v1 views) | rank_prob_v1 (ID: 37, v1 views) | **rank_prob_v2 (v2 views)** |
| Loss Function | **MSE** | **MSE** | **BCE** |
| Class Weights | None | None | **Auto (~4.0)** |
| `from_logits` | N/A (MSE) | N/A (MSE) | False (sigmoid detected) |
| Epochs | 100 | 50 | ~50-100 |
| Learning Rate | 0.001 | 0.0005 | 0.0005 |
| Batch Size | 4096 | 4096 | 4096 |
| Optimizer | Adam | Adam | Adam |
| L2 (towers) | 0.01 | 0.02 | 0.02 |
| Rating Head | Dense(128)→64→32→1(sigmoid) | Dense(128,l2)→Drop(0.2)→64→Drop(0.2)→32→1(sigmoid) | Same as QT-152 |
| Output Activation | sigmoid | sigmoid | sigmoid |

### 2.4 Results Compared

| Metric | QT-151 | QT-152 | QT-155 |
|---|---|---|---|
| Test RMSE | **0.3398** | 0.3321 | **~0.44** |
| Test MAE | **0.1890** | 0.2097 | **~0.26** |
| Val RMSE | 0.3407 | 0.3331 | ~0.44 |
| Val MAE | 0.1892 | 0.2094 | ~0.26 |
| Converged? | Yes (100 epochs) | Yes (50 epochs) | Unclear |

QT-152 improved RMSE over QT-151 (0.3398 → 0.3321) with added dropout, stronger L2, and lower LR, but MAE degraded slightly (0.1890 → 0.2097), suggesting wider prediction spread with more regularization.

### 2.5 Data Views Compared

Analyzed the four SQL view definitions:

- `sql/create_ternopil_prob_train_view.sql` (v1 train)
- `sql/create_ternopil_prob_test_view.sql` (v1 test)
- `sql/create_ternopil_prob_train_v2_view.sql` (v2 train)
- `sql/create_ternopil_prob_test_v2_view.sql` (v2 test)

### 2.6 Git History Reviewed

| Commit | Description |
|---|---|
| `95afdf3` | Automatic BCE class weights and conditional `from_logits` for ranking models |
| `234cb5a` | v2 probability-to-buy views with top-80% product filter |
| `a28ad98` | Replace `Reduction.SUM` with default reduction in ranking/multitask loss functions |
| `de7853b` | Add probability-to-buy train/test views for Ternopil ranking model |

---

## 3. Findings

### 3.1 v1 Data Had an Accidental Ratio Distortion That Made the Problem Easier

**v1 views** sampled negatives 1:4 per customer from **all ~3,186 products**. The downstream Dataset config then applied a top-80% revenue filter, keeping only ~981 products. This filter had asymmetric impact:

- **Positives** (actual transactions) are concentrated on popular products — most survived the filter
- **Negatives** (sampled from all 3,186 products) included many tail products — ~2/3 were removed by the filter

The intended 1:4 ratio was distorted to:
- **Train set**: ~1:2 (roughly 31% positive)
- **Test set**: ~1:1.2 (roughly 45% positive)

**v2 views** fix this by baking the top-80% filter into the `top_products` CTE before negative sampling. Both positives and negatives come from the same ~981 products. The 1:4 ratio is preserved end-to-end (20% positive in both train and test).

### 3.2 v2 Negatives Are Fundamentally Harder to Distinguish

| Aspect | v1 negatives | v2 negatives |
|---|---|---|
| Product pool | All 3,186 products | Top-80% (~981 products) |
| Difficulty | **Easy** — many obscure tail products | **Hard** — all popular, relevant products |
| Overlap with positives | Low (tail products rarely purchased) | High (popular products frequently purchased) |

In v1, the model could achieve good RMSE by learning "popular product = likely positive" as a shortcut. In v2, all negatives are also popular products, so the model must learn actual customer-product affinity — a harder signal.

### 3.3 Class Weights (4.0) Caused Model Collapse

With 20% positives in v2 data, the auto-computed class weight is:

```
label_mean = 0.20
pos_class_weight = (1.0 - 0.20) / 0.20 = 4.0
```

In `compute_loss()`:
- Each positive sample's loss is multiplied by 4.0
- Each negative sample's loss is multiplied by 1.0
- Effective loss contribution: 20% of samples x 4.0 = **80% of total loss from positives**

The model becomes 4x more penalized for false negatives than false positives. With sigmoid output (bounded [0,1]), the safest strategy is to push all predictions higher (toward 0.35-0.50) to minimize the weighted loss. This explains prediction collapse to ~0.38 and RMSE = 0.44.

**The fundamental conflict**: class weights optimize for **balanced accuracy / recall** (minimize misclassification of positives), but RMSE penalizes **deviation from the true label** (wants predictions near 0 for negatives and near 1 for positives). These objectives directly contradict each other.

### 3.4 MSE→BCE Loss Change Misaligns Optimization with Evaluation

QT-151/152 used MSE, which directly optimizes RMSE (the evaluation metric). BCE optimizes log-likelihood — a different objective:

- **MSE gradient**: `2 * (prediction - label)` — linear, proportional to error magnitude
- **BCE gradient**: `(prediction - label) / (prediction * (1 - prediction))` — stronger near 0 and 1, weaker near 0.5

Alone, BCE might have been fine. But combined with class weights, the interaction becomes pathological: BCE's gradient dynamics amplify the class weight bias.

### 3.5 Theoretical RMSE Baselines Confirm Model Collapse

For binary labels {0, 1} with proportion `p` positive, the optimal constant prediction is `p`, giving RMSE = `sqrt(p * (1 - p))`:

| Strategy | v1 train (~31% pos) | v1 test (~45% pos) | v2 (20% pos) |
|---|---|---|---|
| Predict the mean (optimal constant) | 0.463 | 0.497 | **0.400** |
| Always predict 0.38 | 0.470 | 0.505 | **0.443** |
| Always predict 0.50 | 0.500 | 0.500 | 0.500 |

- QT-151 achieved 0.34 vs baseline 0.46 — model learned **0.12 below baseline** (strong learning)
- QT-155 achieved ~0.44 vs baseline 0.40 — model is **0.04 above baseline** (worse than predicting a constant)
- QT-155's RMSE of 0.44 matches a model predicting ~0.38 for everything — **the model has collapsed**

### 3.6 QT-151 Results Were Partially Inflated

QT-151's RMSE 0.34 was a genuine signal, but the v1 data made the task artificially easier:

1. Easy negatives from tail products — model separated by product popularity alone
2. Near-balanced test set (~45% positive) — lower bar for good RMSE
3. MSE loss aligned with the RMSE metric — direct optimization of the evaluation target
4. No class weights — no prediction bias

The v1 "bugs" were accidentally making the problem easier. Fixing them exposed the true difficulty.

### 3.7 `USE_CLASS_WEIGHTS` Is Hardcoded to BCE

In `ml_platform/configs/services.py`, the generated code sets:

```python
USE_CLASS_WEIGHTS = {self.loss_function == 'binary_crossentropy'}
```

There is no way to use BCE **without** class weights, or to use class weights with other losses. This coupling forced QT-155 into the pathological configuration.

### 3.8 Training Curves Show QT-151/152 Converged Healthily

**QT-151** (100 epochs, MSE, v1 data):
```
Epoch    Loss     Val RMSE   Val MAE    Val Loss
  0      0.161    0.4146     0.3543     0.1842
 10      0.081    0.3726     0.2523     0.1267
 25      0.077    0.3549     0.2092     0.1130
 50      0.085    0.3430     0.1990     0.1064
 75      0.074    0.3400     0.1917     0.1052
 99      0.069    0.3407     0.1892     0.1055
```

Smooth convergence, no overfitting. Regularization loss dropped from 1.15 → 0.002 as L2 stabilized weights.

**QT-152** (50 epochs, MSE, v1 data, stronger regularization):
```
Epoch    Loss     Val RMSE   Val MAE    Val Loss
  0      0.177    0.4227     0.3606     0.1753
 10      0.088    0.3726     0.2519     0.1263
 25      0.095    0.3507     0.2176     0.1155
 49      0.106    0.3331     0.2094     0.1093
```

Similar pattern. Higher regularization penalty initially (4.79 vs 1.15, due to L2=0.02 vs 0.01). RMSE was still improving at epoch 49 — could benefit from more epochs.

---

## 4. Problems Found

### 4.1 Three Simultaneous Changes (Critical Process Issue)

Three variables changed between QT-151 and QT-155 (data, loss, class weights). This makes it impossible to attribute the degradation to any single cause without follow-up controlled experiments. Standard ML experiment practice: change one variable at a time.

### 4.2 Automatic Class Weight Overcompensation (Critical Bug)

The formula `(1 - p) / p` produces aggressive weights that dominate the loss:

| Positive Rate | Class Weight | % Loss from Positives |
|---|---|---|
| 50% | 1.0 | 50% (balanced) |
| 33% | 2.0 | 50% |
| 25% | 3.0 | 60% |
| **20%** | **4.0** | **80%** |
| 10% | 9.0 | 90% |
| 5% | 19.0 | 95% |

At 20% positives, 4.0 is too aggressive. Inverse-frequency weighting is a textbook approach for **classification accuracy**, but it conflicts with RMSE evaluation.

### 4.3 `USE_CLASS_WEIGHTS` Coupled to Loss Function (Design Bug)

There is no way to use BCE without class weights. The toggle is hardcoded as `loss_function == 'binary_crossentropy'`. This should be an independent configuration option.

### 4.4 Missing Classification Metrics (Observability Gap)

The ranking model only tracks RMSE and MAE — regression metrics. For binary classification tasks, there is no AUC-ROC, AUC-PR, or F1. It is possible that QT-155 is a better **classifier** despite having worse RMSE, but there is no way to know.

### 4.5 No Prediction Distribution Logging (Observability Gap)

There is no histogram of model predictions in the training metrics. The "collapsed to constant" failure mode (all predictions ~0.38) would be immediately visible in a prediction histogram but is invisible with only aggregate metrics.

### 4.6 Metric-Loss Misalignment

The evaluation metric is RMSE, but BCE optimizes log-likelihood. MSE directly optimizes for RMSE. Switching loss without switching evaluation metrics creates a disconnect where the model may improve on its loss objective while degrading on the reported metric.

---

## 5. Recommendations

### 5.1 Immediate Controlled Experiments

Run these in priority order, changing **one variable at a time** from the QT-152 baseline:

#### Experiment A: MSE + v2 data (control)

Isolates the data change from loss/weight changes.

```
Loss: MSE (no class weights)
Data: v2 views (1:4 ratio, top-80% products)
Model: mod_rank_prob_v2 (same as QT-152)
LR: 0.0005, Epochs: 100, Batch: 4096
```

**Expected**: RMSE 0.36-0.40. This establishes the true difficulty of v2 data with the loss function that worked well before. If RMSE is ~0.36, the v2 data is moderately harder. If ~0.40, the data difficulty is the dominant factor.

#### Experiment B: BCE + v2 data, NO class weights

Tests whether BCE alone works on moderate (1:4) imbalance.

```
Loss: BCE (from_logits=False, sigmoid output)
Class weights: DISABLED
Data: v2 views
Everything else same as Experiment A
```

**Expected**: Should be competitive with Experiment A. 1:4 imbalance is moderate — most classifiers handle it fine without reweighting. Real-world systems routinely train on 1:100 imbalance without class weights.

#### Experiment C: BCE + v2 data, dampened class weights

Tests milder reweighting.

```
Loss: BCE
Class weight: sqrt((1 - p) / p) = sqrt(4.0) = 2.0
Data: v2 views
```

Dampening options to try:
- `sqrt(raw_weight)` → 2.0
- `log(1 + raw_weight)` → 1.61
- `min(raw_weight, 2.0)` → 2.0

#### Experiment D: MSE + v1 data + QT-152 config (reproduction check)

Reproduce QT-152 to confirm the baseline is stable and results are not due to data drift or infrastructure changes.

### 5.2 Platform Code Changes

#### A. Decouple class weights from loss function

Make `USE_CLASS_WEIGHTS` a separate `ModelConfig` boolean field (default: False) instead of auto-enabling on BCE. This allows:
- BCE with no class weights
- BCE with class weights
- MSE with class weights (possible use case for regression on imbalanced data)

#### B. Add class weight dampening options

Add a `class_weight_strategy` field to `ModelConfig` with options:
- `inverse_frequency`: current behavior, `(1-p)/p`
- `sqrt`: `sqrt((1-p)/p)` — geometric dampening
- `log`: `log(1 + (1-p)/p)` — logarithmic dampening
- `none`: no class weights (even with BCE)

#### C. Consider Focal Loss

Focal Loss is a purpose-built alternative that naturally handles class imbalance without the blunt instrument of sample weighting:

```
focal_loss = -alpha * (1 - p_t)^gamma * log(p_t)
```

With `gamma=2.0`, it down-weights easy (well-classified) examples and focuses training on hard examples. No class weight computation needed.

### 5.3 Observability Improvements

#### A. Add classification metrics for binary ranking targets

Track alongside RMSE/MAE:
- **AUC-ROC** — ranking quality independent of threshold
- **AUC-PR** — better for imbalanced data (20% positive)
- **F1 at optimal threshold** — classification accuracy

This would reveal whether a model with worse RMSE is actually a better classifier.

#### B. Log prediction distribution

Add per-epoch histogram of model predictions to `MetricsCollector`. Failure modes become immediately visible:
- Healthy model: bimodal distribution (peaks near 0 and near 1)
- Collapsed model: single peak near 0.3-0.4
- Overconfident model: all predictions at 0.0 or 1.0

#### C. Log class weight and label statistics

Already partially done (commit `95afdf3` logs `use_class_weights` and `class_weight_positive`). Ensure these are surfaced in the experiment comparison UI.

### 5.4 Architecture Improvements for v2 Data

v2 negatives require the model to learn finer-grained customer-product affinity (can't shortcut via product popularity). Consider:

1. **Cross-features between towers** — explicit buyer-product interaction features before the rating head (e.g., customer category purchase counts x product category)
2. **Wider rating head** — increase from Dense(128 -> 64 -> 32) to Dense(256 -> 128 -> 64) for more capacity on the harder discrimination task
3. **Attention mechanism** — replace simple concatenation of tower embeddings with dot-product or multi-head attention
4. **Derived features** — customer purchase frequency per category, product popularity percentile, customer-brand affinity scores

---

## 6. Next Steps

### Phase 1: Controlled Experiments (immediate)

1. Download QT-155 artifacts to `models/qt-155/` for local inspection (trainer_module.py, training_metrics.json)
2. Run **Experiment A** (MSE + v2 data) — the control experiment
3. Run **Experiment B** (BCE + v2 data, no class weights) — test the class weight hypothesis
4. Compare: QT-152 baseline vs Experiment A vs Experiment B vs QT-155
5. Based on results, optionally run Experiment C (dampened weights) and D (reproduction check)

### Phase 2: Platform Changes (after Phase 1 confirms hypotheses)

6. Decouple `USE_CLASS_WEIGHTS` from loss function — make it a separate `ModelConfig` toggle
7. Add class weight dampening strategy selector to `ModelConfig`
8. Add AUC-ROC, AUC-PR, F1 to ranking model training metrics
9. Add prediction histogram logging to `MetricsCollector`
10. Consider implementing Focal Loss as a fourth loss function option

### Phase 3: Model Quality (after Phase 2)

11. Tune the best-performing loss/weight configuration on v2 data
12. Experiment with wider architectures and cross-features
13. Evaluate on production-representative data beyond Ternopil

---

## Appendix A: Theoretical RMSE Baselines

For binary labels {0, 1} with proportion `p` positive, predicting a constant `p` gives RMSE = `sqrt(p * (1 - p))`. Any model above this baseline is not learning.

| p (positive rate) | Optimal Constant | Baseline RMSE | Context |
|---|---|---|---|
| 0.10 | 0.10 | 0.300 | Highly imbalanced |
| 0.15 | 0.15 | 0.357 | |
| 0.20 | 0.20 | 0.400 | **v2 data** |
| 0.25 | 0.25 | 0.433 | |
| 0.31 | 0.31 | 0.463 | **v1 train (approx)** |
| 0.45 | 0.45 | 0.497 | **v1 test (approx)** |
| 0.50 | 0.50 | 0.500 | Perfectly balanced |

## Appendix B: File References

| File | Purpose |
|---|---|
| `models/qt-151/trainer_module.py` | Generated TFX module for QT-151 (MSE, L2=0.01, LR=0.001, no dropout) |
| `models/qt-151/training_metrics.json` | 100-epoch training history for QT-151 |
| `models/qt-152/trainer_module.py` | Generated TFX module for QT-152 (MSE, L2=0.02, LR=0.0005, dropout=0.2) |
| `models/qt-152/training_metrics.json` | 50-epoch training history for QT-152 |
| `sql/create_ternopil_prob_train_view.sql` | v1 train view (all 3,186 products, ratio distortion after filtering) |
| `sql/create_ternopil_prob_test_view.sql` | v1 test view (all products, ~45% positive after filtering) |
| `sql/create_ternopil_prob_train_v2_view.sql` | v2 train view (top-80% products pre-filtered, true 1:4 ratio) |
| `sql/create_ternopil_prob_test_v2_view.sql` | v2 test view (top-80% products, true 1:4 ratio) |
| `ml_platform/configs/services.py` | Code generator — BCE/class weight logic (lines ~4290-4420) |
| `ml_platform/models.py` | QuickTest, ModelConfig, FeatureConfig, Dataset models |
| Commit `95afdf3` | BCE class weights and conditional `from_logits` |
| Commit `234cb5a` | v2 views with top-80% product filter |
| Commit `a28ad98` | `Reduction.SUM` fix |

## Appendix C: Key Terminology

| Term | Definition |
|---|---|
| **TFRS** | TensorFlow Recommenders — framework for building recommendation models |
| **TFX** | TensorFlow Extended — production ML pipeline framework |
| **BCE** | Binary Cross Entropy — loss function for binary classification |
| **MSE** | Mean Squared Error — loss function for regression |
| **RMSE** | Root Mean Squared Error — evaluation metric |
| **Class weight** | Multiplier applied to loss for specific classes to handle imbalance |
| **from_logits** | Whether BCE expects raw logits (True) or probabilities after sigmoid (False) |
| **Focal Loss** | Modified BCE that down-weights easy examples; handles imbalance without sample weights |
| **Negative sampling** | Generating (customer, product) pairs that didn't occur as negative examples |
| **Top-80% filter** | Keeping only products that contribute to the top 80% of cumulative revenue |
