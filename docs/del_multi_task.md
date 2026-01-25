# Multitask Model Implementation

## Overview

This document describes the implementation of **Multitask (Hybrid) models** in the B2B Recommendations SaaS system. Multitask models combine both retrieval and ranking objectives in a single model, enabling simultaneous optimization for candidate generation and relevance scoring.

**Implementation Date:** 2026-01-12

## Table of Contents

1. [Background & Goal](#background--goal)
2. [Google TFRS Example Reference](#google-tfrs-example-reference)
3. [Architecture](#architecture)
4. [Implementation Details](#implementation-details)
5. [Files Modified](#files-modified)
6. [Testing & Validation](#testing--validation)
7. [Usage Guide](#usage-guide)

---

## Background & Goal

### The Challenge

Traditional recommendation systems use two separate models:

| Stage | Model Type | Objective | Output |
|-------|-----------|-----------|--------|
| **Retrieval** | Two-tower | Fast candidate generation | Top-K candidates from millions |
| **Ranking** | Rating prediction | Accurate relevance scoring | Sorted list of candidates |

This two-stage approach requires:
- Training and maintaining two separate models
- Sequential pipeline (retrieval → ranking)
- Separate feature engineering for each stage

### The Solution: Multitask Learning

Multitask models train a single model that optimizes both objectives simultaneously:

```
                    ┌─────────────────────┐
                    │   Shared Towers     │
                    │  (Query + Candidate)│
                    └──────────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                 │
     ┌────────▼────────┐              ┌────────▼────────┐
     │ Retrieval Task  │              │  Ranking Task   │
     │ (Dot Product)   │              │  (Rating Head)  │
     └────────┬────────┘              └────────┬────────┘
              │                                 │
              │   Retrieval Loss               │   Ranking Loss
              │                                 │
              └────────────────┬────────────────┘
                               │
                    Combined Loss = w₁ * L_retrieval + w₂ * L_ranking
```

**Benefits:**
- **Shared representations**: Both tasks benefit from learned embeddings
- **Single training pipeline**: One model, one training job
- **Flexible serving**: Serve retrieval, ranking, or both
- **Balanced optimization**: Configurable loss weights

---

## Google TFRS Example Reference

The implementation follows the official TensorFlow Recommenders multitask tutorial:

**Source:** [TensorFlow Recommenders - Multitask](https://www.tensorflow.org/recommenders/examples/multitask)

### Key Components from Google Example

#### 1. Model Architecture

```python
class MovielensModel(tfrs.models.Model):
    def __init__(self, rating_weight: float, retrieval_weight: float):
        super().__init__()

        # Shared towers
        self.user_model = UserModel()
        self.movie_model = MovieModel()

        # Rating head (dense layers for regression)
        self.rating_model = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation="relu"),
            tf.keras.layers.Dense(128, activation="relu"),
            tf.keras.layers.Dense(1),
        ])

        # Tasks
        self.retrieval_task = tfrs.tasks.Retrieval()
        self.ranking_task = tfrs.tasks.Ranking(
            loss=tf.keras.losses.MeanSquaredError(),
            metrics=[tf.keras.metrics.RootMeanSquaredError()]
        )

        # Loss weights
        self.rating_weight = rating_weight
        self.retrieval_weight = retrieval_weight
```

#### 2. Loss Computation

```python
def compute_loss(self, features, training=False):
    # Get embeddings
    user_embeddings = self.user_model(features["user_id"])
    movie_embeddings = self.movie_model(features["movie_title"])

    # Retrieval loss (contrastive learning)
    retrieval_loss = self.retrieval_task(user_embeddings, movie_embeddings)

    # Rating prediction
    rating_predictions = self.rating_model(
        tf.concat([user_embeddings, movie_embeddings], axis=1)
    )

    # Ranking loss (regression)
    ranking_loss = self.ranking_task(
        labels=features["user_rating"],
        predictions=rating_predictions
    )

    # Weighted combination
    return (self.retrieval_weight * retrieval_loss
            + self.rating_weight * ranking_loss)
```

#### 3. Key Insight: Shared vs. Separate

The Google example demonstrates that sharing tower representations between tasks enables transfer learning - patterns learned for retrieval (e.g., user preferences) also benefit ranking predictions.

---

## Architecture

### Database Schema

The `ModelConfig` model already includes multitask fields:

```python
# ml_platform/models.py

MODEL_TYPE_MULTITASK = 'multitask'  # Pre-existing constant

class ModelConfig(models.Model):
    model_type = models.CharField(choices=[
        ('retrieval', 'Retrieval'),
        ('ranking', 'Ranking'),
        ('multitask', 'Multitask'),  # Already supported
    ])

    # Multitask loss weights (pre-existing fields)
    retrieval_weight = models.FloatField(default=1.0)
    ranking_weight = models.FloatField(default=1.0)

    # Tower configurations (shared with retrieval/ranking)
    buyer_tower_layers = ArrayField(...)      # Query tower
    product_tower_layers = ArrayField(...)    # Candidate tower
    rating_head_layers = ArrayField(...)      # Rating prediction head
```

### UI Components (Pre-existing)

The Model Config form already includes loss weight sliders:
- Retrieval Weight (0.0 - 2.0, step 0.1)
- Ranking Weight (0.0 - 2.0, step 0.1)
- These appear when `model_type = 'multitask'`

### Code Generation Architecture

```
TrainerModuleGenerator
├── generate()
│   ├── model_type == 'retrieval' → _generate_retrieval_trainer()
│   ├── model_type == 'ranking'   → _generate_ranking_trainer()
│   └── model_type == 'multitask' → _generate_multitask_trainer()  ← NEW
│
└── _generate_multitask_trainer()  ← NEW (~1,100 lines)
    ├── _generate_header_multitask()
    ├── _generate_imports()          # Reused from retrieval
    ├── _generate_constants_multitask()
    ├── _generate_input_fn_multitask()
    ├── _generate_multitask_model()
    ├── _generate_serve_fn_multitask()
    ├── _generate_metrics_callback_multitask()
    └── _generate_run_fn_multitask()
```

---

## Implementation Details

### 1. Trainer Code Generation (`ml_platform/configs/services.py`)

#### Dispatch Logic (lines 1612-1613)

```python
def generate(self) -> str:
    """Generate complete trainer module code."""
    if self.model_type == 'retrieval':
        return self._generate_retrieval_trainer()
    elif self.model_type == 'ranking':
        return self._generate_ranking_trainer()
    elif self.model_type == 'multitask':
        return self._generate_multitask_trainer()  # NEW
```

#### Constants Generation (`_generate_constants_multitask()`)

Generates both retrieval and ranking configuration:

```python
# Loss weights (configurable via Model Config UI)
RETRIEVAL_WEIGHT = 1.0
RANKING_WEIGHT = 1.0

# Retrieval configuration
RETRIEVAL_ALGORITHM = 'brute_force'  # or 'scann'
TOP_K = 100

# Ranking configuration (from FeatureConfig.target_column)
TARGET_COLUMN = 'total_sales'
```

#### Model Class (`_generate_multitask_model()`)

Generates `MultitaskModel(tfrs.Model)`:

```python
class MultitaskModel(tfrs.Model):
    """Combined retrieval and ranking model."""

    def __init__(self, ...):
        super().__init__()

        # Shared embedding towers
        self.buyer_tower = tf.keras.Sequential([...])      # Query
        self.product_tower = tf.keras.Sequential([...])    # Candidate

        # Rating head for ranking task
        self.rating_head = tf.keras.Sequential([...])

        # Dual tasks
        self.retrieval_task = tfrs.tasks.Retrieval()
        self.ranking_task = tfrs.tasks.Ranking(
            loss=tf.keras.losses.MeanSquaredError(),
            metrics=[tf.keras.metrics.RootMeanSquaredError()]
        )

        # Loss weights from Model Config
        self.retrieval_weight = RETRIEVAL_WEIGHT
        self.ranking_weight = RANKING_WEIGHT

    def compute_loss(self, inputs, training=False):
        features, labels = inputs  # labels contains target column

        # Get embeddings from shared towers
        buyer_embedding = self.buyer_tower(features)
        product_embedding = self.product_tower(features)

        # Retrieval loss (contrastive)
        retrieval_loss = self.retrieval_task(
            buyer_embedding, product_embedding
        )

        # Rating prediction from concatenated embeddings
        combined = tf.concat([buyer_embedding, product_embedding], axis=1)
        rating_pred = self.rating_head(combined)

        # Ranking loss (regression against target column)
        ranking_loss = self.ranking_task(
            labels=labels,
            predictions=rating_pred
        )

        # Weighted combination
        return (self.retrieval_weight * retrieval_loss
                + self.ranking_weight * ranking_loss)
```

#### Serving Model (`_generate_serve_fn_multitask()`)

Generates `MultitaskServingModel` with **dual signatures**:

```python
class MultitaskServingModel(tf.keras.Model):
    """Serving model with both retrieval and ranking capabilities."""

    @tf.function
    def serve(self, serialized_examples):
        """Default signature: Retrieval (top-K candidates)."""
        # Parse and transform features
        # Return top-K product IDs and scores
        return {'product_ids': top_ids, 'scores': top_scores}

    @tf.function
    def serve_ranking(self, serialized_examples):
        """Ranking signature: Predict ratings for buyer-product pairs."""
        # Parse and transform features
        # Return rating predictions
        return {'predictions': rating_predictions}

# Export with dual signatures
signatures = {
    'serving_default': serving_model.serve,        # Retrieval (default)
    'serve_ranking': serving_model.serve_ranking   # Ranking
}
```

#### Weight Tracking Callback (`_generate_metrics_callback_multitask()`)

Tracks weights for 3 towers:

```python
class WeightStatsCallback(tf.keras.callbacks.Callback):
    """Track weight statistics for Query, Candidate, and Rating towers."""

    def on_epoch_end(self, epoch, logs=None):
        tower_stats = dict(query=[], candidate=[], rating_head=[])

        for layer in self.model.layers:
            # Categorize by tower name prefix
            if 'buyer' in layer.name:
                tower_stats['query'].extend(...)
            elif 'product' in layer.name:
                tower_stats['candidate'].extend(...)
            elif 'rating' in layer.name:
                tower_stats['rating_head'].extend(...)

        # Log mean/std for each tower to MLflow
```

#### Training Loop (`_generate_run_fn_multitask()`)

```python
def run_fn(fn_args):
    # Build model
    model = MultitaskModel(...)

    # Train with weighted loss
    model.fit(train_dataset, validation_data=val_dataset, epochs=EPOCHS)

    # Evaluate BOTH metrics
    # 1. Retrieval: Recall@K using BruteForce layer
    # 2. Ranking: RMSE/MAE on test set

    # Log to MLflow
    mlflow.log_metrics({
        'recall_at_5': ...,
        'recall_at_10': ...,
        'recall_at_50': ...,
        'recall_at_100': ...,
        'rmse': ...,
        'mae': ...,
    })

    # Export serving model with dual signatures
    tf.saved_model.save(serving_model, fn_args.serving_model_dir, signatures=...)
```

### 2. Backend API Updates (`ml_platform/experiments/api.py`)

#### Metrics Extraction (`_get_model_metrics()`)

Returns both retrieval and ranking metrics for multitask:

```python
def _get_model_metrics(quick_test, config_type):
    """Get metrics based on model type."""
    metrics = {}

    if config_type == 'retrieval':
        metrics = {'recall_at_5': ..., 'recall_at_100': ...}
    elif config_type == 'ranking':
        metrics = {'rmse': ..., 'mae': ..., 'test_rmse': ..., 'test_mae': ...}
    elif config_type == 'multitask':
        # Return ALL metrics for multitask
        metrics = {
            # Retrieval metrics
            'recall_at_5': ..., 'recall_at_10': ...,
            'recall_at_50': ..., 'recall_at_100': ...,
            # Ranking metrics
            'rmse': ..., 'mae': ...,
            'test_rmse': ..., 'test_mae': ...,
        }

    return metrics
```

#### Quick Test Serialization (`_serialize_quick_test()`)

Includes all 8 metrics when model_type is multitask:

```python
def _serialize_quick_test(quick_test, model_type=None):
    """Serialize QuickTest for API response."""
    result = {
        'id': quick_test.id,
        'status': quick_test.status,
        # ... other fields
    }

    if model_type == 'multitask':
        # Include ALL metrics
        result.update({
            'recall_at_5': quick_test.recall_at_5,
            'recall_at_10': quick_test.recall_at_10,
            'recall_at_50': quick_test.recall_at_50,
            'recall_at_100': quick_test.recall_at_100,
            'rmse': quick_test.rmse,
            'mae': quick_test.mae,
            'test_rmse': quick_test.test_rmse,
            'test_mae': quick_test.test_mae,
        })
    # ... retrieval/ranking specific returns
```

### 3. Validation (`ml_platform/experiments/services.py`)

Enhanced `validate_experiment_config()` with multitask-specific checks:

```python
def validate_experiment_config(feature_config, model_config, ...):
    errors = []

    mc_type = model_config.model_type
    retrieval_weight = getattr(model_config, 'retrieval_weight', 1.0)
    ranking_weight = getattr(model_config, 'ranking_weight', 1.0)

    if mc_type == 'multitask':
        # Check: At least one loss weight must be > 0
        if retrieval_weight == 0 and ranking_weight == 0:
            errors.append(
                "Multitask model requires at least one loss weight "
                "(retrieval or ranking) to be greater than 0"
            )

        # Check: Rating head layers required
        if not getattr(model_config, 'rating_head_layers', None):
            errors.append(
                "Multitask model requires rating_head_layers to be configured"
            )

        # Check: Target column required (for ranking component)
        if not feature_config.target_column:
            errors.append(
                "Multitask model requires a Feature Config with target_column "
                "set (needed for ranking loss calculation)"
            )

    return errors
```

### 4. Frontend Updates (`templates/ml_platform/model_experiments.html`)

#### Metrics Display in Experiment Cards

Two-row layout for multitask experiments:

```javascript
function renderMetricsRow(experiment) {
    const modelType = experiment.model_config?.model_type;

    if (modelType === 'multitask') {
        // Show BOTH metric types in two rows
        return `
            <div class="multitask-metrics">
                <div class="metrics-row retrieval-metrics">
                    <span class="metric-label">Retrieval:</span>
                    <span>R@5: ${formatPercent(metrics.recall_at_5)}</span>
                    <span>R@100: ${formatPercent(metrics.recall_at_100)}</span>
                </div>
                <div class="metrics-row ranking-metrics">
                    <span class="metric-label">Ranking:</span>
                    <span>RMSE: ${formatNumber(metrics.rmse)}</span>
                    <span>Test RMSE: ${formatNumber(metrics.test_rmse)}</span>
                </div>
            </div>
        `;
    }
    // ... retrieval or ranking specific display
}
```

#### Detail View Metrics Summary

Shows complete metrics breakdown when viewing experiment details:

```javascript
function renderMetricsSummary(experiment) {
    if (modelType === 'multitask') {
        return `
            <div class="metrics-section">
                <h4>Retrieval Metrics</h4>
                <div class="metric-item">
                    <span>Recall@5</span>
                    <span>${formatPercent(metrics.recall_at_5)}</span>
                </div>
                <div class="metric-item">
                    <span>Recall@10</span>
                    <span>${formatPercent(metrics.recall_at_10)}</span>
                </div>
                <div class="metric-item">
                    <span>Recall@50</span>
                    <span>${formatPercent(metrics.recall_at_50)}</span>
                </div>
                <div class="metric-item">
                    <span>Recall@100</span>
                    <span>${formatPercent(metrics.recall_at_100)}</span>
                </div>
            </div>
            <div class="metrics-section">
                <h4>Ranking Metrics</h4>
                <div class="metric-item">
                    <span>Validation RMSE</span>
                    <span>${formatNumber(metrics.rmse)}</span>
                </div>
                <div class="metric-item">
                    <span>Validation MAE</span>
                    <span>${formatNumber(metrics.mae)}</span>
                </div>
                <div class="metric-item">
                    <span>Test RMSE</span>
                    <span>${formatNumber(metrics.test_rmse)}</span>
                </div>
                <div class="metric-item">
                    <span>Test MAE</span>
                    <span>${formatNumber(metrics.test_mae)}</span>
                </div>
            </div>
        `;
    }
}
```

---

## Files Modified

| File | Lines | Changes |
|------|-------|---------|
| `ml_platform/configs/services.py` | 1612-1613, 4667-5767 | Dispatch logic + 10 new multitask generation methods (~1,100 lines) |
| `ml_platform/experiments/api.py` | 741-869, 943-1016 | `_get_model_metrics()`, `_serialize_quick_test()` for multitask |
| `ml_platform/experiments/services.py` | 26-98 | Enhanced `validate_experiment_config()` with multitask checks |
| `templates/ml_platform/model_experiments.html` | CSS + JS | `renderMetricsRow()`, `renderMetricsSummary()`, CSS styles |
| `scripts/test_multitask_generation.py` | New file | Test script for validating trainer code generation |

---

## Testing & Validation

### Test Script

```bash
python scripts/test_multitask_generation.py
```

**Output:**
```
======================================================================
TESTING MULTITASK TRAINER CODE GENERATION
======================================================================

Using FeatureConfig: cherng_v3_rank_#1 (ID: 5)
  - config_type: ranking
  - target_column: total_sales

ModelConfig details:
  - model_type: multitask
  - retrieval_weight: 1.0
  - ranking_weight: 1.0
  - output_embedding_dim: 64
  - loss_function: mse

======================================================================
GENERATING MULTITASK TRAINER CODE
======================================================================

Generated code length: 45234 characters
Generated code lines: 1127

======================================================================
VALIDATING PYTHON SYNTAX
======================================================================

[PASS] Generated code is valid Python!

======================================================================
CHECKING KEY COMPONENTS
======================================================================
  [PASS] MultitaskModel class
  [PASS] retrieval_task
  [PASS] ranking_task
  [PASS] RETRIEVAL_WEIGHT constant
  [PASS] RANKING_WEIGHT constant
  [PASS] compute_loss with weighted sum
  [PASS] MultitaskServingModel
  [PASS] serve function (retrieval)
  [PASS] serve_ranking function
  [PASS] Dual signatures
  [PASS] rating_head tower tracking

[SUCCESS] All component checks passed!

Generated code saved to: /tmp/generated_multitask_trainer.py
```

### Component Checklist

| Component | Status | Description |
|-----------|--------|-------------|
| `MultitaskModel(tfrs.Model)` | ✅ | Main model class with dual tasks |
| `retrieval_task` | ✅ | `tfrs.tasks.Retrieval()` |
| `ranking_task` | ✅ | `tfrs.tasks.Ranking(loss=MSE)` |
| `RETRIEVAL_WEIGHT` | ✅ | Configurable loss weight |
| `RANKING_WEIGHT` | ✅ | Configurable loss weight |
| Weighted `compute_loss` | ✅ | `w1 * L_retrieval + w2 * L_ranking` |
| `MultitaskServingModel` | ✅ | Serving wrapper class |
| `serve()` (retrieval) | ✅ | Default signature returns top-K |
| `serve_ranking()` | ✅ | Secondary signature returns predictions |
| Dual export signatures | ✅ | Both signatures in SavedModel |
| 3-tower weight tracking | ✅ | Query, Candidate, Rating Head |

---

## Usage Guide

### 1. Create a Feature Config

For multitask models, the Feature Config **must** have a `target_column` set:

1. Navigate to **Features Config** → **Create New**
2. Select `config_type = ranking` (this enables target column)
3. Configure buyer and product features
4. Set **Target Column** (e.g., `total_sales`, `conversion_rate`)
5. Save

### 2. Create a Model Config

1. Navigate to **Model Configs** → **Create New**
2. Set `model_type = multitask`
3. Configure towers:
   - **Buyer Tower Layers**: e.g., `[256, 128, 64]`
   - **Product Tower Layers**: e.g., `[256, 128, 64]`
   - **Rating Head Layers**: e.g., `[64, 32, 1]` (required for multitask)
4. Set **Loss Weights**:
   - **Retrieval Weight**: `1.0` (default)
   - **Ranking Weight**: `1.0` (default)
5. Configure retrieval settings:
   - **Retrieval Algorithm**: `brute_force` or `scann`
   - **Top K**: `100`
6. Save

### 3. Run an Experiment

1. Navigate to **Experiments** → **New Experiment**
2. Select your multitask Feature Config and Model Config
3. The system validates:
   - At least one loss weight > 0
   - Rating head layers configured
   - Target column set in Feature Config
4. Configure dataset and sampling
5. Submit

### 4. View Results

After completion, the experiment card shows:

```
┌────────────────────────────────────────────────┐
│ Experiment #42: Multitask Test                 │
│ Status: completed                              │
├────────────────────────────────────────────────┤
│ Retrieval:  R@5: 23.4%  R@100: 67.8%          │
│ Ranking:    RMSE: 0.234  Test RMSE: 0.245     │
└────────────────────────────────────────────────┘
```

### 5. Serve the Model

The exported model has two signatures:

```python
import tensorflow as tf

model = tf.saved_model.load('/path/to/model')

# Retrieval (default) - get top-K candidates
retrieval_result = model.serve(serialized_examples)
# Returns: {'product_ids': [...], 'scores': [...]}

# Ranking - predict ratings
ranking_result = model.serve_ranking(serialized_examples)
# Returns: {'predictions': [...]}
```

---

## Future Enhancements

1. **Dashboard Tab**: Add "Multitask" tab to experiments dashboard with combined metrics visualization
2. **Comparison**: Enable cross-model-type comparisons (retrieval vs. multitask)
3. **ScaNN Support**: Enable ScaNN for multitask retrieval serving (currently brute-force only)
4. **Custom Loss Functions**: Support other ranking losses (listwise, pairwise)
