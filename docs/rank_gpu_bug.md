# Bug Report: Ranking Model Fails on Multi-GPU Training (training-runs/69)

**Date:** 2026-03-03
**Status:** Root cause identified, fix pending
**Severity:** Critical — blocks all ranking and multitask model training runs
**Affected Model Types:** Ranking, Multitask (retrieval is unaffected)

---

## 1. Problem Statement

| Run | Type | Model Type | Result |
|-----|------|------------|--------|
| quick-tests/177 | Experiment | Retrieval | **Succeeded** |
| training-runs/67 | Training | Retrieval | **Succeeded** |
| quick-tests/178 | Experiment | Ranking | **Succeeded** |
| training-runs/69 | Training | Ranking | **Failed** |

The ranking model validates successfully as an experiment (CPU) but fails when promoted to a full training run (2x T4 GPU). The retrieval model works in both contexts.

---

## 2. Root Cause

### 2.1 The Bug: Keras Loss Reduction Incompatible with MirroredStrategy

**Primary location:** `ml_platform/configs/services.py`, lines 4798-4814

The `TrainerModuleGenerator._generate_ranking_model()` generates Keras loss functions with the **default reduction mode** (`AUTO` → `SUM_OVER_BATCH_SIZE`):

```python
# configs/services.py, line 4809-4813
loss_mapping = {
    'mse': 'tf.keras.losses.MeanSquaredError()',              # ← default Reduction.AUTO
    'binary_crossentropy': bce_str,                            # ← default Reduction.AUTO
    'huber': 'tf.keras.losses.Huber()',                        # ← default Reduction.AUTO
}
```

This produces the following in the generated trainer module (verified in `dev/models/qt-178/trainer_module.py`, line 637):

```python
self.task = tfrs.tasks.Ranking(
    loss=tf.keras.losses.MeanSquaredError(),   # NO Reduction.SUM
)
```

When this model runs on 2x T4 GPU, TensorFlow creates a `MirroredStrategy` (trainer_module.py line 1289-1291). The ranking model uses a **custom `train_step`** (line 682) that calls `self.compute_loss()` → `self.task()` → the Keras loss function. TensorFlow raises:

```
ValueError: Please use `tf.keras.losses.Reduction.SUM` or
`tf.keras.losses.Reduction.NONE` for loss reduction when losses are
used with `tf.distribute.Strategy`, except for specifying losses in
`Model.compile()` for use by the built-in training loop `Model.fit()`.
```

The "except" clause does NOT apply because:
- `model.compile(optimizer=optimizer)` is called **without a loss parameter** (line 1425)
- Loss is computed in a **custom `train_step`** (line 682), not the built-in Keras training loop

### 2.2 Why Experiments Succeed

| Aspect | Experiments (quick-tests) | Training Runs |
|--------|--------------------------|---------------|
| Hardware | CPU only (default) | 2x T4 GPU (always) |
| Strategy | `tf.distribute.get_strategy()` (no-op) | `MirroredStrategy` (2 replicas) |
| Loss reduction validation | Not triggered | **Rejects `AUTO` in custom `train_step`** |

Experiments run on CPU by default — no `MirroredStrategy`, no reduction validation, no error.

Training runs **always** use 2x T4 GPU:
- `training/services.py` line 2942-2944: defaults `gpu_type='NVIDIA_TESLA_T4'`, `gpu_count=2`
- `training/services.py` line 3052: `custom_config["gpu_enabled"] = True`
- Generated trainer module line 1289: `strategy = tf.distribute.MirroredStrategy()`

### 2.3 Why Retrieval Models Are Unaffected

The retrieval model uses `tfrs.tasks.Retrieval()` (line 623 in qt-177/trainer_module.py):

```python
self.task = tfrs.tasks.Retrieval()   # No Keras loss function, no reduction issue
```

`tfrs.tasks.Retrieval` computes contrastive loss internally using in-batch negatives. It does not expose a Keras loss function with a reduction parameter. Therefore MirroredStrategy has no reduction mode to validate.

The ranking model uses `tfrs.tasks.Ranking(loss=MeanSquaredError())` which wraps a standard Keras loss — and that's what MirroredStrategy rejects.

### 2.4 History: Fix → Revert → Bug Returns

This exact bug was already identified, fixed, and then **reverted**:

**1. Original fix (2026-01-28)** — documented in `docs/phase_training.md` lines 3496-3589:

```python
# Fixed version (Jan 28)
'mse': 'tf.keras.losses.MeanSquaredError(reduction=tf.keras.losses.Reduction.SUM)',
```

**2. Revert** — current code at `configs/services.py` lines 4799-4803:

```python
# Use default reduction (SUM_OVER_BATCH_SIZE) for properly scaled gradients.
# Reduction.SUM was causing training instability: gradients were ~batch_size
# times too large, and clipnorm=1.0 created a fixed-step dynamic that
# prevented convergence (val loss diverged, predictions went far out of range).
# Default AUTO/SUM_OVER_BATCH_SIZE works correctly with MirroredStrategy in TF 2.x.
```

**The comment on line 4803 is factually incorrect.** `AUTO/SUM_OVER_BATCH_SIZE` does NOT work with `MirroredStrategy` when used in a custom `train_step`. It only works when the loss is passed via `model.compile(loss=...)` with the standard built-in training loop.

The revert fixed the gradient instability symptom but re-introduced the multi-GPU incompatibility.

---

## 3. Analysis Methodology

### 3.1 Compared Generated Code

Examined auto-generated TFX modules for both experiments side by side:

| File | Experiment | Model Type |
|------|-----------|------------|
| `dev/models/qt-177/transform_module.py` | quick-tests/177 | Retrieval |
| `dev/models/qt-177/trainer_module.py` | quick-tests/177 | Retrieval |
| `dev/models/qt-178/transform_module.py` | quick-tests/178 | Ranking |
| `dev/models/qt-178/trainer_module.py` | quick-tests/178 | Ranking |

Key structural differences found:

| Aspect | Retrieval (qt-177) | Ranking (qt-178) |
|--------|-------------------|-------------------|
| TFRS task | `tfrs.tasks.Retrieval()` | `tfrs.tasks.Ranking(loss=MeanSquaredError())` |
| `call()` method | Not present | Present (towers + rating_head → scalar) |
| `compute_loss` input | `features` (dict) | `(features, labels)` (tuple) |
| `_input_fn` label_key | None | `LABEL_KEY = 'label_target'` |
| Serving model | `ServingModel` (8 buyer inputs → top-K) | `RankingServingModel` (19 buyer+product inputs → score) |
| Rating head | None | Dense(128)→DO(0.2)→Dense(64)→Dense(32)→DO(0.1)→Dense(1,sigmoid) |
| Gradient towers | `['query', 'candidate']` | `['query', 'candidate', 'rating_head']` |

### 3.2 Compared Pipeline Architecture

| Aspect | Experiments Pipeline | Training Pipeline |
|--------|---------------------|-------------------|
| Service file | `experiments/services.py` | `training/services.py` |
| Compile script | `_get_compile_script()` (line 1081) | `_get_compile_script()` (line 2902) |
| Stages | 5: ExampleGen→Stats→Schema→Transform→Trainer | 7-9: + Evaluator + Pusher + Deploy |
| Trainer executor | Direct (CPU) or GenericExecutor (GPU optional) | GenericExecutor always (GPU mandatory) |
| Default image | `tfx-trainer:latest` (CPU) | `tfx-trainer-gpu:latest` (GPU) |
| GPU config | Optional (empty dict = CPU) | Always 2x T4 |
| GCS bucket | `quicktest-artifacts` | `training-artifacts` |

### 3.3 Traced Code Generation Path

Both experiments and training runs use identical code generators:

```
submit_training_pipeline() [training/services.py:2586]
  → PreprocessingFnGenerator(feature_config).generate_and_save()  [configs/services.py:888]
  → TrainerModuleGenerator(feature_config, model_config).generate_and_validate()  [configs/services.py:1682]
```

The generators produce identical code regardless of experiment vs training context. The difference is purely runtime: CPU (experiments) vs 2x GPU with MirroredStrategy (training).

### 3.4 Identified the Loss Reduction as Root Cause

Traced the loss function through:

1. `TrainerModuleGenerator._generate_ranking_model()` → `configs/services.py:4809` → generates `MeanSquaredError()` with default reduction
2. Generated code → `qt-178/trainer_module.py:637` → `tfrs.tasks.Ranking(loss=MeanSquaredError())`
3. Custom `train_step` → `qt-178/trainer_module.py:682` → `self.compute_loss(data)` → `self.task(labels, predictions)`
4. MirroredStrategy validates reduction mode → **ValueError**

Cross-referenced with existing documentation at `docs/phase_training.md:3496-3589` which describes the identical bug and its original fix.

---

## 4. Suggested Fix

### 4.1 Primary Fix: Loss Reduction + Manual Scaling

The original fix (`Reduction.SUM` alone) was correct for GPU compatibility but broke gradient scaling. The proper fix requires **both** changes:

**A. In `ml_platform/configs/services.py` — Ranking model generator (~line 4809):**

Change the loss_mapping to use `Reduction.SUM`:

```python
loss_mapping = {
    'mse': 'tf.keras.losses.MeanSquaredError(reduction=tf.keras.losses.Reduction.SUM)',
    'binary_crossentropy': bce_str.replace(')', ', reduction=tf.keras.losses.Reduction.SUM)'),
    'huber': 'tf.keras.losses.Huber(reduction=tf.keras.losses.Reduction.SUM)',
}
```

**B. In the generated `compute_loss` method — divide loss by batch size:**

In `_generate_ranking_model()`, update the generated `compute_loss` to normalize:

```python
def compute_loss(self, features, training=False):
    feature_dict, labels = features
    predictions = self(feature_dict)
    loss = self.task(labels=labels, predictions=predictions)
    # Scale loss: Reduction.SUM returns sum over batch.
    # Divide by per-replica batch size to restore mean-scaled gradients.
    loss = loss / tf.cast(tf.shape(labels)[0], tf.float32)
    return loss
```

This gives:
- `Reduction.SUM` → MirroredStrategy compatible (no ValueError)
- Division by batch size → gradients identical to `SUM_OVER_BATCH_SIZE` → no instability
- `clipnorm=1.0` behaves correctly again

**C. Apply the same fix to multitask model generator (~line 6066).**

The multitask generator at `configs/services.py:6066` has the identical issue (see line 6060: `# See ranking model comment for details on why Reduction.SUM was removed.`).

### 4.2 Verification Steps

1. Generate trainer code for a ranking FeatureConfig + ModelConfig
2. Verify the generated code contains `Reduction.SUM` and the batch-size division
3. Run a quick-test experiment on CPU — confirm it still works
4. Run a training run on 2x T4 GPU — confirm it no longer raises ValueError
5. Compare loss/gradient magnitudes between CPU and GPU runs — confirm they are similar
6. Check convergence: val_loss should decrease, predictions should stay in range

---

## 5. Secondary Bug: Hardcoded `blessing_metric` in Training Wizard

### Location

`static/js/training_wizard.js` — lines 1809, 1898, 1965

### Problem

All three payload builders (`buildWizardConfig`, `buildEditPayload`, `buildPayload`) hardcode:

```javascript
blessing_threshold: {
    metric: 'recall_at_100',    // ← ALWAYS recall_at_100, even for ranking models
    min_value: parseFloat(evaluator.blessingThreshold)
}
```

For ranking models, this should be `'rmse'` or `'mae'`.

### Current Impact

**Low** — the Evaluator is disabled by default (`training_wizard.js` line 80: `enabled: false`). This bug only triggers if a user manually enables the Evaluator for a ranking model.

### Additional Sub-issue

`training/services.py` line 3130:
```python
tfma.ModelSpec(label_key='label')  # Will be ignored for retrieval models
```

For ranking models, the Transform module outputs the target as `label_target` (not `label`). When TFMA looks for `label_key='label'` in the transformed examples, it won't find it. This would cause the Evaluator to fail even if the metric were correct.

### Suggested Fix

In `training_wizard.js`, make `metric` dynamic based on model type:

```javascript
blessing_threshold: {
    metric: state.formData.modelType === 'ranking' ? 'rmse' : 'recall_at_100',
    min_value: parseFloat(evaluator.blessingThreshold)
}
```

In `training/services.py` line 3130, use the transformed label key:

```python
tfma.ModelSpec(label_key='label_target')  # Matches Transform output key
```

---

## 6. File Reference

### Core Files (Primary Bug)

| File | Lines | Role |
|------|-------|------|
| `ml_platform/configs/services.py` | 4798-4814 | **BUG LOCATION** — Ranking loss_mapping with default reduction |
| `ml_platform/configs/services.py` | 6058-6071 | **BUG LOCATION** — Multitask loss_mapping (same issue) |
| `ml_platform/configs/services.py` | 4777+ | `_generate_ranking_model()` — generates RankingModel class |
| `ml_platform/configs/services.py` | 888-1400 | `PreprocessingFnGenerator` — generates transform_module.py |
| `ml_platform/configs/services.py` | 1682-2500 | `TrainerModuleGenerator` — generates trainer_module.py |
| `ml_platform/training/services.py` | 2586-2736 | `submit_training_pipeline()` — code generation + Cloud Build trigger |
| `ml_platform/training/services.py` | 2902-3192 | `_get_compile_script()` — TFX training pipeline definition |
| `ml_platform/training/services.py` | 2942-2944 | GPU defaults: always 2x T4 |
| `ml_platform/training/services.py` | 3081-3092 | Trainer with GenericExecutor (GPU) |
| `ml_platform/experiments/services.py` | 1095-1282 | Experiment pipeline (CPU path for comparison) |

### Generated Code (Evidence)

| File | Content |
|------|---------|
| `dev/models/qt-177/trainer_module.py` | Retrieval trainer — line 623: `tfrs.tasks.Retrieval()` (no Keras loss) |
| `dev/models/qt-177/transform_module.py` | Retrieval transform — no target column |
| `dev/models/qt-178/trainer_module.py` | Ranking trainer — line 637: `MeanSquaredError()` (**no Reduction.SUM**) |
| `dev/models/qt-178/transform_module.py` | Ranking transform — line 273: `outputs['label_target']` |

### Secondary Bug Files

| File | Lines | Role |
|------|-------|------|
| `static/js/training_wizard.js` | 1809, 1898, 1965 | Hardcoded `metric: 'recall_at_100'` |
| `static/js/training_wizard.js` | 79-80 | Evaluator disabled by default |
| `ml_platform/training/services.py` | 3128-3145 | TFMA EvalConfig with wrong `label_key` |

### Documentation

| File | Lines | Content |
|------|-------|---------|
| `docs/phase_training.md` | 3496-3589 | Original bug fix documentation (2026-01-28) |
| `docs/phase_training.md` | 3513-3517 | Why retrieval models are unaffected |
| `docs/phase_training.md` | 3519-3524 | Why ranking/multitask models fail |
| `docs/phase_experiments.md` | Full | Experiments domain spec |
| `docs/phase_training.md` | Full | Training domain spec |

### Model Definitions

| File | Lines | Model |
|------|-------|-------|
| `ml_platform/models.py` | 1683-2000 | QuickTest model (experiments) |
| `ml_platform/training/models.py` | 403-930 | TrainingRun model |
| `ml_platform/training/models.py` | 13-141 | RegisteredModel |

---

## 7. Next Steps

1. **Fix the primary bug** in `configs/services.py`:
   - Add `Reduction.SUM` to ranking loss_mapping (~line 4809)
   - Add `Reduction.SUM` to multitask loss_mapping (~line 6066)
   - Add batch-size division in generated `compute_loss` for both model types

2. **Test locally** — generate trainer code and verify syntax + reduction present

3. **Deploy and re-run training-runs/69** (or create a new ranking training run)

4. **Fix the secondary blessing_metric bug** in `training_wizard.js` (lower priority)

5. **Fix the `label_key` mismatch** in `training/services.py` line 3130 (lower priority, only matters when Evaluator is enabled)

6. **Update `docs/phase_training.md`** changelog with the fix details, referencing this document
