# Ranking Model Training Fix

**Date:** 2026-01-09
**Status:** In Progress - Test Failed, Investigation Needed

---

## 1. Problem Statement

Ranking model pipelines were failing at the Trainer phase with the error:

```
NameError: name 'Tuple' is not defined. Did you mean: 'tuple'?
```

Additionally, analysis revealed that even if this error was fixed, the ranking trainer had multiple issues that would prevent training metrics from being saved to Django DB.

---

## 2. Root Cause Analysis

### Bug #1: Missing `Tuple` Import (CRITICAL)

**Location:** `ml_platform/configs/services.py:1751`

**Problem:** The `RankingModel.compute_loss` method uses `Tuple[Dict[str, tf.Tensor], tf.Tensor]` type hint, but the imports only included:

```python
from typing import Dict, List, Text  # Missing: Tuple
```

**Error from pipeline logs:**
```
File "/tmp/tmp5njnh5i1/trainer_module.py", line 462, in RankingModel
    features: Tuple[Dict[str, tf.Tensor], tf.Tensor],
NameError: name 'Tuple' is not defined. Did you mean: 'tuple'?
```

### Bug #2: `_metrics_collector.save()` Method Doesn't Exist

**Location:** `ml_platform/configs/services.py:3909` (ranking trainer)

**Problem:** The ranking trainer called `_metrics_collector.save()` but `MetricsCollector` class only has `save_to_gcs()`.

**Comparison:**
- **Retrieval trainer (line 3343):** `_metrics_collector.save_to_gcs()` - correct
- **Ranking trainer (line 3909):** `_metrics_collector.save()` - method doesn't exist

**Impact:** Training would fail with `AttributeError` when trying to save metrics.

### Bug #3: Missing `finally` Block in Ranking Trainer

**Location:** `ml_platform/configs/services.py:3907-3915` (ranking trainer)

**Problem:** Ranking trainer had metrics save inside `try` block, not in a `finally` block like retrieval.

**Retrieval pattern (correct):**
```python
finally:
    if _metrics_collector:
        try:
            _metrics_collector.save_to_gcs()
        except Exception as e:
            logging.warning(f"Error saving metrics: {e}")
```

**Ranking pattern (broken):**
```python
try:
    # ... training code ...
    _metrics_collector.save()  # Inside try, not finally
except Exception as e:
    raise
```

**Impact:** If training failed, no metrics would be saved.

### Bug #4: Missing Callbacks in Ranking Trainer

**Location:** `ml_platform/configs/services.py` - `_generate_metrics_callback_ranking()` and `_generate_run_fn_ranking()`

**Problem:** Ranking trainer only had `MetricsCallback`, missing 4 other callbacks that retrieval has:

| Callback | Retrieval | Ranking (Before Fix) |
|----------|-----------|----------------------|
| `MetricsCallback` | Yes | Yes |
| `WeightNormCallback` | Yes | No |
| `WeightStatsCallback` | Yes | No |
| `GradientCollapseCallback` | Yes | No |
| `GradientStatsCallback` | Yes | No |

**Impact:** Ranking models would not collect weight/gradient statistics needed for Training Analysis UI visualizations.

### Bug #5: Missing `_grad_accum` and `train_step` in RankingModel

**Problem:** `GradientStatsCallback` and `GradientCollapseCallback` require the model to have:
1. `_grad_accum` - tf.Variable accumulators for gradient statistics
2. Custom `train_step` - to populate the accumulators during training

Retrieval model had these (lines 2396-2486), but RankingModel did not.

---

## 3. Training Data Flow (How it Should Work)

```
TRAINER (Vertex AI)
    │
    ├─→ MetricsCollector.log_metric() - collects per-epoch metrics
    ├─→ MetricsCollector.log_weight_stats() - collects weight distributions
    ├─→ MetricsCollector.log_gradient_stats() - collects gradient distributions
    │
    └─→ MetricsCollector.save_to_gcs() - writes training_metrics.json to GCS
                    │
                    ▼
            gs://bucket/quick-tests/qt-XX/training_metrics.json
                    │
                    ▼
DJANGO (on pipeline completion or UI request)
    │
    └─→ TrainingCacheService._cache_from_gcs() - reads from GCS
                    │
                    ▼
            QuickTest.training_history_json = cached_data
            QuickTest.save()
```

**Key insight:** If `save_to_gcs()` is never called (due to Bug #2), `training_metrics.json` is never written to GCS, so `TrainingCacheService` has nothing to read, and Django DB stays empty.

---

## 4. Fixes Applied

### Fix #1: Add `Tuple` to Imports

**File:** `ml_platform/configs/services.py:1751`

```python
# Before
from typing import Dict, List, Text

# After
from typing import Dict, List, Text, Tuple
```

### Fix #2: Change `save()` to `save_to_gcs()` with `finally` Block

**File:** `ml_platform/configs/services.py` - `_generate_run_fn_ranking()`

**Before (lines 3907-3915):**
```python
        # Save metrics
        if _metrics_collector:
            _metrics_collector.save()

    except Exception as e:
        logging.error(f"Training failed: {e}")
        import traceback
        traceback.print_exc()
        raise
```

**After:**
```python
    except Exception as e:
        logging.error(f"Training failed: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        # Save all collected metrics to GCS
        if _metrics_collector:
            try:
                _metrics_collector.save_to_gcs()
                logging.info("Training metrics saved to GCS successfully")
            except Exception as e:
                logging.warning(f"Error saving metrics to GCS: {e}")
```

### Fix #3: Add All Callbacks to Ranking Trainer

**File:** `ml_platform/configs/services.py` - `_generate_run_fn_ranking()`

Added to callbacks list:
```python
callbacks.append(MetricsCallback())
callbacks.append(WeightNormCallback())
callbacks.append(WeightStatsCallback())
callbacks.append(GradientCollapseCallback(min_grad_norm=1e-7, patience=3))
callbacks.append(GradientStatsCallback())
```

### Fix #4: Add Callback Class Definitions to Ranking Trainer

**File:** `ml_platform/configs/services.py` - `_generate_metrics_callback_ranking()`

Added full callback class definitions (matching retrieval) with support for 3 towers:
- `query` (buyer tower)
- `candidate` (product tower)
- `rating_head` (ranking head)

### Fix #5: Add `_grad_accum` and `train_step` to RankingModel

**File:** `ml_platform/configs/services.py` - `_generate_ranking_model()`

Added to `RankingModel.__init__`:
```python
# Gradient statistics accumulators (tf.Variables for graph-mode updates)
self._grad_accum = {}
for tower in ['query', 'candidate', 'rating_head']:
    self._grad_accum[tower] = {
        'sum': tf.Variable(0.0, trainable=False, name=f'{tower}_grad_sum'),
        'sum_sq': tf.Variable(0.0, trainable=False, name=f'{tower}_grad_sum_sq'),
        'count': tf.Variable(0.0, trainable=False, name=f'{tower}_grad_count'),
        'min': tf.Variable(float('inf'), trainable=False, name=f'{tower}_grad_min'),
        'max': tf.Variable(float('-inf'), trainable=False, name=f'{tower}_grad_max'),
        'hist_counts': tf.Variable(tf.zeros(25, dtype=tf.int32), trainable=False, name=f'{tower}_grad_hist'),
    }
```

Added `train_step` method to accumulate gradient statistics during training (same pattern as retrieval).

---

## 5. Test Execution

### Test Method
Used `scripts/test_services_trainer.py` to run a CustomJob that tests the generated trainer code.

### Test Configuration
- **Feature Config ID:** 9 (cherng_v3_rank_#1)
- **Model Config ID:** 15 (chernigiv_rank_1)
- **Source Experiment:** qt-94-20260108-204730 (provides Transform artifacts)
- **Epochs:** 2
- **Learning Rate:** 0.01

### Test Command
```bash
./venv/bin/python scripts/test_services_trainer.py \
    --feature-config-id 9 \
    --model-config-id 15 \
    --source-exp qt-94-20260108-204730 \
    --epochs 2 \
    --learning-rate 0.01
```

### Test Result
**Status:** FAILED

**Job ID:** 7621800310092070912

**Artifacts:**
- Generated trainer: `gs://b2b-recs-quicktest-artifacts/services-test-20260109-114824/trainer_module.py`
- Runner script: `gs://b2b-recs-quicktest-artifacts/services-test-20260109-114824/runner.py`

### Failure Investigation
The exact error is not yet determined. Logs are not yet available in Cloud Logging. Further investigation needed.

**Possible causes:**
1. Data format mismatch between Transform output and trainer expectations
2. Feature name differences between FeatureConfig and actual transformed features
3. Runner script issues (e.g., missing test split handling)

---

## 6. Next Steps

1. **Investigate job failure** - Check Cloud Logging for detailed error messages
2. **Verify generated code** - Compare generated trainer with working retrieval trainer
3. **Run local test** - Test trainer module locally with sample data
4. **Re-run with more logging** - Add verbose logging to runner script
5. **Verify Django DB storage** - Once training succeeds, confirm `training_history_json` is populated

---

## 7. Files Modified

| File | Changes |
|------|---------|
| `ml_platform/configs/services.py` | Added Tuple import, fixed save_to_gcs, added callbacks, added _grad_accum and train_step |

---

## 8. Related Documentation

- `docs/custom_job_test.md` - How to run CustomJob tests
- `docs/ranking_implementation.md` - Ranking model implementation details
- `docs/phase_experiments.md` - Experiments and training history flow
