# Experiment Stability Analysis Report

**Date:** 2026-01-03
**Issue:** Experiments producing 0% accuracy metrics while loss remains stable
**Status:** Root cause identified, implementation plan defined

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Analysis Methodology](#analysis-methodology)
3. [Findings](#findings)
4. [Root Cause Analysis](#root-cause-analysis)
5. [Implementation Plan](#implementation-plan)
6. [Next Steps](#next-steps)

---

## Problem Statement

Multiple experiments were producing unstable results:
- **Good experiments:** Positive recall metrics (e.g., Recall@100 = 5-7%)
- **Bad experiments:** Zero recall metrics (Recall@5/10/50/100 = 0.000000)
- **Common symptom:** Loss functions remain stable/constant in bad experiments

### Affected Experiments

| Exp # | Name | Status | Recall@100 |
|-------|------|--------|------------|
| 45 | chernigiv_23 | BAD | 0.000000 |
| 43 | chernigiv_21 | GOOD | 0.063990 |
| 42 | chernigiv_20 | BAD | 0.000000 |
| 41 | chernigiv_19 | BAD | 0.000000 |
| 40 | chernigiv_18 | BAD | 0.000000 |
| 39 | chernigiv_17 | GOOD | 0.055364 |

---

## Analysis Methodology

### 1. Accessing Training Data from Django Database

Used Django ORM to query experiment data:

```python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ml_platform.models import QuickTest, ModelConfig, FeatureConfig

# Query experiments by ID
exp_ids = [77, 75, 74, 73, 71]  # Exp #45=77, #43=75, etc.

for exp_id in exp_ids:
    qt = QuickTest.objects.get(id=exp_id)

    # Access training history (cached JSON)
    history = qt.training_history_json

    # Get metrics
    final_metrics = history.get('final_metrics', {})
    loss_data = history.get('loss', {})
    gradient_stats = history.get('gradient_stats', {})
    weight_stats = history.get('weight_stats', {})
    params = history.get('params', {})

    # Access related configs
    feature_config = qt.feature_config
    model_config = qt.model_config

    # Get GCS artifact path
    gcs_path = qt.gcs_artifacts_path
```

**Key Django Models Used:**
- `QuickTest` - Experiment tracking with metrics and GCS paths
- `FeatureConfig` - Feature transformation configuration
- `ModelConfig` - Neural network architecture configuration

**Database Fields Analyzed:**
- `training_history_json` - Cached training metrics from GCS
- `gcs_artifacts_path` - Path to experiment artifacts
- `recall_at_10`, `recall_at_50`, `recall_at_100` - Accuracy metrics
- `loss` - Final training loss

### 2. Accessing GCS Artifacts

Used `gsutil` to access experiment artifacts stored in Google Cloud Storage:

```bash
# List experiment artifacts
gsutil ls gs://b2b-recs-quicktest-artifacts/qt-75-20260102-204611/

# Download trainer module
gsutil cp "gs://b2b-recs-quicktest-artifacts/qt-75-20260102-204611/trainer_module.py" /tmp/

# Download training metrics
gsutil cat "gs://b2b-recs-quicktest-artifacts/qt-75-20260102-204611/training_metrics.json"
```

**Artifact Structure:**
```
gs://b2b-recs-quicktest-artifacts/qt-{id}-{timestamp}/
├── trainer_module.py       # Generated trainer code
├── training_metrics.json   # Training history & metrics
└── transform_module.py     # Generated transform code
```

### 3. Accessing Pipeline Artifacts (Transformed TFRecords)

Pipeline artifacts are stored in a different bucket with Vertex AI structure:

```bash
# Base path pattern
BASE="gs://b2b-recs-pipeline-staging/pipeline_root/qt-{id}-{timestamp}/{project_number}/{pipeline_name}/"

# List pipeline components
gsutil ls "$BASE"
# Output:
# BigQueryExampleGen_{id}/
# StatisticsGen_{id}/
# SchemaGen_{id}/
# Transform_{id}/
# Trainer_{id}/

# Access transformed examples
gsutil ls "$BASE/Transform_{id}/transformed_examples/Split-train/"
gsutil ls "$BASE/Transform_{id}/transformed_examples/Split-eval/"
gsutil ls "$BASE/Transform_{id}/transformed_examples/Split-test/"

# Access vocabulary files
gsutil ls "$BASE/Transform_{id}/transform_graph/transform_fn/assets/"
gsutil cat "$BASE/Transform_{id}/transform_graph/transform_fn/assets/product_id_vocab" | wc -l
```

### 4. Using Conda Environment for TensorFlow Analysis

Located TensorFlow installation in conda environments:

```bash
# List conda environments
ls /Users/dkulish/miniconda3/envs/

# Check for TensorFlow
/Users/dkulish/miniconda3/envs/tf/bin/pip list | grep -i tensor
# tensorflow                     2.16.1
# tensorflow-recommenders        0.7.2
```

**Analyzing TFRecords with TensorFlow:**

```python
# Use conda tf environment
/Users/dkulish/miniconda3/envs/tf/bin/python << 'EOF'
import tensorflow as tf

# Read transformed TFRecords
train_path = "gs://b2b-recs-pipeline-staging/.../transformed_examples-00000-of-00001.gz"
dataset = tf.data.TFRecordDataset(train_path, compression_type='GZIP')

# Parse and analyze records
for raw_record in dataset.take(1000):
    example = tf.train.Example()
    example.ParseFromString(raw_record.numpy())

    # Extract features
    product_id = example.features.feature['product_id'].int64_list.value[0]
    customer_id = example.features.feature['customer_id'].int64_list.value[0]

    # Analyze feature schema
    for feature_name in example.features.feature.keys():
        feature = example.features.feature[feature_name]
        # Check int64, float, or bytes type
EOF
```

### 5. Comparing with TFRS Official Tutorial

Fetched and analyzed the official TensorFlow Recommenders tutorial:
- URL: https://www.tensorflow.org/recommenders/examples/basic_retrieval
- Key configurations extracted: optimizer, learning rate, model architecture, candidate building

---

## Findings

### Finding 1: Learning Rate Correlation with Success/Failure

| Experiment | Learning Rate | Loss Change | Result |
|------------|---------------|-------------|--------|
| Exp #43 | **0.01** | -1126.69 | GOOD |
| Exp #39 | **0.05** | -963.03 | GOOD |
| Exp #38 | **0.01** | -1155.03 | GOOD |
| Exp #45 | **0.1** | +0.00 | BAD |
| Exp #42 | **0.1** | +0.00 | BAD |
| Exp #41 | **0.1** | -0.00 | BAD |
| Exp #40 | **0.1** | +0.00 | BAD |

### Finding 2: Gradient Collapse in Bad Experiments

**Good Experiment (Exp #43, LR=0.01):**
```
QUERY TOWER GRADIENTS:
  Norm (epoch 0 → final): 119.107964 → 6250.373749  ✓ Growing

CANDIDATE TOWER GRADIENTS:
  Norm (epoch 0 → final): 758.380099 → 7615.570891  ✓ Growing

LOSS: 4747.2236 → 3620.5366 (Δ = -1126.6870)  ✓ Decreasing
```

**Bad Experiment (Exp #45, LR=0.1):**
```
QUERY TOWER GRADIENTS:
  Norm (epoch 0 → final): 1664.252835 → 0.000000  ✗ COLLAPSED TO ZERO

CANDIDATE TOWER GRADIENTS:
  Norm (epoch 0 → final): 14829.182580 → 0.000000  ✗ COLLAPSED TO ZERO

LOSS: 775.6906 → 775.6906 (Δ = +0.0000)  ✗ NO CHANGE
```

### Finding 3: TFRecord Data is Valid

Both good and bad experiments have valid transformed data:

| Metric | Good (qt-75) | Bad (qt-77) |
|--------|--------------|-------------|
| Train records | ~80,000 | ~640,000 |
| Eval records | ~15,000 | ~120,000 |
| Unique products | 1,054 | 2,739 |
| Unique customers | 7,267 | 22,166 |
| Features valid | Yes | Yes |

### Finding 4: Vocabulary Files are Valid

```
Good Exp #43 vocabularies:
  customer_id_vocab: 7,267 entries
  product_id_vocab:  1,054 entries
  category_vocab:        7 entries
  sub_category_vocab:  247 entries

Bad Exp #45 vocabularies:
  customer_id_vocab: 22,166 entries
  product_id_vocab:   2,739 entries
  category_vocab:         9 entries
  segment_vocab:          9 entries
  sub_category_vocab:   415 entries
```

### Finding 5: Code Differences from TFRS Tutorial

| Aspect | TFRS Tutorial | Our Implementation |
|--------|---------------|-------------------|
| Model complexity | 1 embedding layer | 3-4 dense layers |
| FactorizedTopK metrics | Yes (during training) | No |
| Candidate source | Unique items | Transactions (duplicates) |
| Batch size | 8,192 | 2,048 |
| Product ID column | Explicit | Auto-detected |

---

## Root Cause Analysis

### Primary Root Cause: Gradient Collapse

The high learning rate (0.1) combined with deep architecture causes:

1. **First training step:** Large gradients (14,829 for candidate tower) × LR (0.1) = massive update
2. **Overshoot:** Model parameters jump far from optimal region
3. **Collapse:** Embeddings saturate or become NaN
4. **Zero gradients:** No further learning occurs
5. **Constant loss:** Model frozen in degenerate state

### Why TFRS Tutorial Works with LR=0.1

The official tutorial uses a **simpler architecture**:
- Single embedding layer per tower (no dense layers)
- Fewer total parameters
- Smaller gradient magnitudes
- More tolerant to aggressive learning rates

Our implementation has:
- 3-4 dense layers per tower
- Multiple embedding types (8D, 16D, 32D, 64D)
- ~10x more parameters
- Higher gradient magnitudes requiring lower learning rates

### Secondary Issues

1. **No FactorizedTopK Metrics:** Training doesn't compute retrieval accuracy, only loss
2. **Duplicate Candidates:** Eval files contain transactions, not unique products
3. **Auto-detected Product ID:** Guesses column name instead of using explicit config
4. **Duplicate Feature Bug:** Exp #45 has `cust_value` twice in BuyerModel features

---

## Implementation Plan

### Phase 1: Immediate Fixes (Training Stability)

#### 1.1 Add Learning Rate Validation

**File:** `ml_platform/configs/services.py`

```python
# In TrainerModuleGenerator class, add validation:

def _validate_learning_rate(self):
    """Validate learning rate is appropriate for architecture complexity."""
    num_dense_layers = len(self.model_config.buyer_tower_layers or [])

    if self.learning_rate >= 0.1 and num_dense_layers >= 3:
        logger.warning(
            f"Learning rate {self.learning_rate} may be too high for "
            f"{num_dense_layers}-layer architecture. Recommended: <= 0.05"
        )
```

#### 1.2 Add Gradient Clipping to Generated Code

**File:** `ml_platform/configs/services.py` (in `_generate_run_fn`)

```python
# Change optimizer creation to include gradient clipping:
optimizer = tf.keras.optimizers.{optimizer}(
    learning_rate=learning_rate,
    clipnorm=1.0  # Prevent gradient explosion
)
```

#### 1.3 Add Learning Rate Recommendations to UI

**File:** `ml_platform/experiments/api.py`

```python
# In experiment submission endpoint, add recommendation:
if learning_rate >= 0.1:
    warnings.append({
        'type': 'learning_rate',
        'message': 'Learning rate >= 0.1 may cause training instability. '
                   'Recommended: 0.01-0.05 for complex architectures.'
    })
```

### Phase 2: Code Quality Improvements

#### 2.1 Add Explicit ID Columns to FeatureConfig

**File:** `ml_platform/models.py`

```python
class FeatureConfig(models.Model):
    # ... existing fields ...

    # Add explicit ID column fields
    buyer_id_column = models.CharField(
        max_length=255,
        blank=True,
        help_text="Column name for buyer/user ID (e.g., 'customer_id')"
    )
    product_id_column = models.CharField(
        max_length=255,
        blank=True,
        help_text="Column name for product/item ID (e.g., 'product_id')"
    )
```

**Migration required:** Create migration for new fields

#### 2.2 Update Trainer Generation to Use Explicit Columns

**File:** `ml_platform/configs/services.py`

```python
# Replace auto-detection with explicit column:
def _get_product_id_column(self) -> str:
    """Get product ID column from FeatureConfig or fall back to detection."""
    if self.feature_config.product_id_column:
        return self.feature_config.product_id_column

    # Fall back to auto-detection with warning
    logger.warning("product_id_column not set, using auto-detection")
    return self._auto_detect_product_id_column()
```

#### 2.3 Fix Duplicate Candidate Issue

**File:** `ml_platform/configs/services.py` (in trainer generation)

```python
def _generate_precompute_candidates(self) -> str:
    """Generate code to precompute UNIQUE candidate embeddings."""
    return '''
def _precompute_candidate_embeddings(model, candidates_dataset, product_id_col, batch_size=128):
    """Pre-compute embeddings for UNIQUE candidates only."""
    seen_products = set()
    unique_product_ids = []
    unique_embeddings = []

    for batch in candidates_dataset.batch(batch_size):
        batch_embeddings = model.candidate_tower(batch)

        for i in range(len(batch[product_id_col])):
            pid = batch[product_id_col][i].numpy()
            if hasattr(pid, 'decode'):
                pid = pid.decode()

            if pid not in seen_products:
                seen_products.add(pid)
                unique_product_ids.append(pid)
                unique_embeddings.append(batch_embeddings[i])

    return unique_product_ids, tf.stack(unique_embeddings)
'''
```

### Phase 3: Enhanced Metrics

#### 3.1 Add FactorizedTopK Metrics During Training

**File:** `ml_platform/configs/services.py` (in `_generate_retrieval_model`)

```python
# Option to enable FactorizedTopK metrics (requires candidate pre-computation)
if self.model_config.enable_training_metrics:
    return '''
# Build candidate embeddings for metrics
candidates = train_dataset.batch(128).map(lambda x: model.candidate_tower(x))
metrics = tfrs.metrics.FactorizedTopK(candidates=candidates)
self.task = tfrs.tasks.Retrieval(metrics=metrics)
'''
```

#### 3.2 Add Early Stopping on Gradient Collapse

**File:** Generated trainer code

```python
class GradientCollapseCallback(tf.keras.callbacks.Callback):
    """Stop training if gradients collapse to zero."""

    def on_epoch_end(self, epoch, logs=None):
        # Check gradient norms from model accumulators
        for tower in ['query', 'candidate']:
            accum = self.model._grad_accum.get(tower, {})
            norm = float(accum.get('sum_sq', tf.constant(0.0)).numpy())

            if epoch > 0 and norm == 0.0:
                logging.error(f"Gradient collapse detected in {tower} tower!")
                self.model.stop_training = True
```

### Phase 4: Validation & Testing

#### 4.1 Add Feature Config Validation

**File:** `ml_platform/configs/services.py`

```python
def validate_feature_config(feature_config: FeatureConfig) -> List[str]:
    """Validate feature config for common issues."""
    errors = []

    # Check for duplicate features
    buyer_cols = [f.get('column') for f in feature_config.buyer_model_features]
    if len(buyer_cols) != len(set(buyer_cols)):
        errors.append("Duplicate columns in buyer_model_features")

    # Check ID columns are set
    if not feature_config.buyer_id_column:
        errors.append("buyer_id_column not set")
    if not feature_config.product_id_column:
        errors.append("product_id_column not set")

    return errors
```

---

## Next Steps

### Immediate (This Sprint)

1. [ ] **Add gradient clipping** to trainer code generation
2. [ ] **Add learning rate validation** with warnings in UI
3. [ ] **Re-run failed experiments** with LR=0.01 to verify fix
4. [ ] **Add GradientCollapseCallback** to detect issues early

### Short-term (Next Sprint)

5. [ ] **Create migration** for `buyer_id_column` and `product_id_column`
6. [ ] **Update UI** to require explicit ID columns
7. [ ] **Fix candidate deduplication** in trainer generation
8. [ ] **Add FeatureConfig validation** before experiment submission

### Medium-term (Following Sprint)

9. [ ] **Implement FactorizedTopK metrics** option for training
10. [ ] **Add early stopping** on gradient collapse
11. [ ] **Create experiment templates** with recommended hyperparameters
12. [ ] **Add hyperparameter search** functionality

### Testing Checklist

- [ ] Re-run Exp #45 with LR=0.01 → Expect positive recall
- [ ] Re-run Exp #42 with gradient clipping → Expect stable training
- [ ] Verify candidate deduplication improves recall metrics
- [ ] Test explicit ID column migration on existing data

---

## Appendix: Commands Reference

### Django Database Access

```bash
# Activate project venv
source venv/bin/activate

# Run Django shell
python manage.py shell

# Or use inline Python
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from ml_platform.models import QuickTest
# ... your code
"
```

### GCS Access

```bash
# List artifacts
gsutil ls gs://b2b-recs-quicktest-artifacts/

# Download file
gsutil cp gs://bucket/path/file.py /local/path/

# View file contents
gsutil cat gs://bucket/path/file.json

# Recursive listing
gsutil ls -r gs://bucket/path/
```

### TensorFlow Analysis

```bash
# Use conda environment with TensorFlow
/Users/dkulish/miniconda3/envs/tf/bin/python << 'EOF'
import tensorflow as tf
# ... your code
EOF
```

### Vocabulary Analysis

```bash
# Count vocabulary entries
gsutil cat gs://bucket/path/product_id_vocab | wc -l

# View vocabulary sample
gsutil cat gs://bucket/path/product_id_vocab | head -10
```
