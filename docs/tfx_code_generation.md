# TFX Code Generation

## Document Purpose
This document describes the automatic TFX code generation system that converts Feature Configs into executable TFX Transform and Trainer modules for Vertex AI Pipelines.

**Last Updated**: 2025-12-10

---

## Overview

The ML Platform automatically generates TFX-compatible Python code from Feature Config JSON schemas. This enables:

1. **No-code feature engineering** - Users configure features via the UI wizard
2. **Reproducible pipelines** - Generated code is stored and versioned with the config
3. **TFX/Vertex AI compatibility** - Output code works directly with TFX Transform and Trainer components

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FEATURE CONFIG (JSON)                              │
│                                                                              │
│  buyer_model_features: [...]                                                │
│  product_model_features: [...]                                              │
│  buyer_model_crosses: [...]                                                 │
│  product_model_crosses: [...]                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PreprocessingFnGenerator                                │
│                      (ml_platform/modeling/services.py)                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      GENERATED TRANSFORM CODE                                │
│                      (stored in FeatureConfig.generated_transform_code)      │
│                                                                              │
│  - preprocessing_fn(inputs) → outputs                                       │
│  - Vocabularies for text features                                           │
│  - Normalization/bucketization for numeric                                  │
│  - Cyclical encoding for temporal                                           │
│  - Cross feature hashing                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      TFX TRANSFORM COMPONENT                                 │
│                      (Vertex AI Pipeline)                                    │
│                                                                              │
│  Outputs:                                                                   │
│  - Transformed TFRecords with indices/floats                                │
│  - Vocabulary files as artifacts                                            │
│  - Transform graph for serving                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      TrainerModuleGenerator (FUTURE)                         │
│                                                                              │
│  - Load vocabularies from Transform artifacts                               │
│  - Create embeddings with configured dimensions                             │
│  - Build two-tower TFRS model                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### Database Schema

Three new fields were added to the `FeatureConfig` model:

```python
# ml_platform/models.py

class FeatureConfig(models.Model):
    # ... existing fields ...

    # Generated TFX code (stored as text for Cloud Run compatibility)
    generated_transform_code = models.TextField(
        blank=True,
        help_text="Auto-generated TFX Transform preprocessing_fn code"
    )
    generated_trainer_code = models.TextField(
        blank=True,
        help_text="Auto-generated TFX Trainer module code"
    )
    generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When code was last generated"
    )
```

**Design Decision**: Code is stored in the database (not filesystem) because:
- Cloud Run has ephemeral filesystem
- PostgreSQL in Cloud SQL handles text storage efficiently
- Code is versioned with the config for reproducibility

### PreprocessingFnGenerator

Located in `ml_platform/modeling/services.py`, this class generates TFX Transform `preprocessing_fn` code.

#### Feature Type Mappings

| Feature Config | TFX Transform Output | Output Name |
|----------------|---------------------|-------------|
| Text (data_type='text') | `tft.compute_and_apply_vocabulary()` | `{column}` (vocab index) |
| Numeric normalize | `tft.scale_to_z_score()` | `{column}_norm` (float) |
| Numeric bucketize | `tft.bucketize()` | `{column}_bucket` (bucket index) |
| Temporal normalize | `tft.scale_to_z_score()` | `{column}_norm` (float) |
| Temporal cyclical | `tf.sin/cos()` | `{column}_{cycle}_sin`, `{column}_{cycle}_cos` |
| Temporal bucketize | `tft.bucketize()` | `{column}_bucket` (bucket index) |
| Cross (text × text) | `tf.sparse.cross_hashed()` | `{col1}_x_{col2}_cross` |
| Cross (with numeric) | bucketize + hash | `{col1}_x_{col2}_cross` |

#### Cyclical Feature Encoding

Temporal features can have cyclical patterns encoded as sin/cos pairs:

| Cycle | Approximation | Output |
|-------|---------------|--------|
| Yearly | day_of_year / 365.25 | `{col}_yearly_sin`, `{col}_yearly_cos` |
| Quarterly | day_of_quarter / 91.31 | `{col}_quarterly_sin`, `{col}_quarterly_cos` |
| Monthly | day_of_month / 30.44 | `{col}_monthly_sin`, `{col}_monthly_cos` |
| Weekly | day_of_week / 7 (Monday=0) | `{col}_weekly_sin`, `{col}_weekly_cos` |
| Daily | hour / 24 | `{col}_daily_sin`, `{col}_daily_cos` |

#### Cross Feature Handling

Cross features require special handling for numeric/temporal columns:

1. **Text × Text**: Direct crossing via `tf.sparse.cross_hashed()`
2. **Numeric × Text**: Bucketize numeric first (using `crossing_buckets`), then cross
3. **Temporal × Anything**: Bucketize temporal first, then cross

The `crossing_buckets` parameter is **separate** from the main tensor's bucketization to allow coarser granularity for crosses (typically 5-20 buckets vs 100 for main tensor).

### API Endpoints

#### Get Generated Code
```
GET /api/feature-configs/{config_id}/generated-code/
Query params: type=transform|trainer (default: transform)

Response:
{
  "success": true,
  "data": {
    "code": "# Auto-generated TFX Transform...",
    "code_type": "transform",
    "generated_at": "2025-12-10T10:30:00Z",
    "config_id": 5,
    "config_name": "Rich Features v1",
    "has_code": true
  }
}
```

#### Regenerate Code
```
POST /api/feature-configs/{config_id}/regenerate-code/

Response:
{
  "success": true,
  "data": {
    "code": "# Auto-generated TFX Transform...",
    "code_type": "transform",
    "generated_at": "2025-12-10T10:35:00Z"
  },
  "message": "Transform code regenerated successfully"
}
```

### Automatic Generation Triggers

Code is automatically generated when:

1. **Creating** a new feature config
2. **Updating** a feature config (if features changed)
3. **Cloning** a feature config

Code generation failures are logged but don't fail the main operation.

---

## Example Generated Code

For a Feature Config with:
- **Buyer**: customer_id (text, 64D), city (text, 16D), revenue (numeric, norm+bucket), trans_date (temporal, norm+weekly+monthly)
- **Product**: product_id (text, 32D), category (text, 16D)
- **Buyer Crosses**: customer_id × city

```python
# Auto-generated TFX Transform preprocessing_fn
# FeatureConfig: "Rich Features v1" (ID: 5)
# Generated at: 2025-12-10T10:30:00Z
#
# BuyerModel features: customer_id, city, revenue, trans_date
# ProductModel features: product_id, category
# Buyer crosses: customer_id × city
# Product crosses: none

import math
import tensorflow as tf
import tensorflow_transform as tft

NUM_OOV_BUCKETS = 1


def preprocessing_fn(inputs):
    """
    TFX Transform preprocessing function.

    Outputs vocabulary indices for text features, normalized values for numeric,
    cyclical encodings for temporal, and hashed indices for crosses.

    Embeddings are created in the Trainer module, not here.
    """
    outputs = {}

    # =========================================================================
    # TEXT FEATURES → Vocabulary lookup (outputs: vocab indices)
    # =========================================================================

    # customer_id: STRING → vocab index (embedding_dim=64 in Trainer)
    outputs['customer_id'] = tft.compute_and_apply_vocabulary(
        inputs['customer_id'],
        num_oov_buckets=NUM_OOV_BUCKETS,
        vocab_filename='customer_id_vocab'
    )

    # city: STRING → vocab index (embedding_dim=16 in Trainer)
    outputs['city'] = tft.compute_and_apply_vocabulary(
        inputs['city'],
        num_oov_buckets=NUM_OOV_BUCKETS,
        vocab_filename='city_vocab'
    )

    # product_id: STRING → vocab index (embedding_dim=32 in Trainer)
    outputs['product_id'] = tft.compute_and_apply_vocabulary(
        inputs['product_id'],
        num_oov_buckets=NUM_OOV_BUCKETS,
        vocab_filename='product_id_vocab'
    )

    # category: STRING → vocab index (embedding_dim=16 in Trainer)
    outputs['category'] = tft.compute_and_apply_vocabulary(
        inputs['category'],
        num_oov_buckets=NUM_OOV_BUCKETS,
        vocab_filename='category_vocab'
    )

    # =========================================================================
    # NUMERIC FEATURES → Normalize / Bucketize
    # =========================================================================

    # revenue: FLOAT64 → normalize + bucketize(100)
    revenue_float = tf.cast(inputs['revenue'], tf.float32)
    outputs['revenue_norm'] = tft.scale_to_z_score(revenue_float)
    outputs['revenue_bucket'] = tft.bucketize(revenue_float, num_buckets=100)

    # =========================================================================
    # TEMPORAL FEATURES → Normalize / Cyclical / Bucketize
    # =========================================================================

    # trans_date: TIMESTAMP → normalize + cyclical(weekly, monthly)
    # Convert timestamp to float seconds since epoch
    trans_date_seconds = tf.cast(
        tf.cast(inputs['trans_date'], tf.int64),
        tf.float32
    )

    # Normalize
    outputs['trans_date_norm'] = tft.scale_to_z_score(trans_date_seconds)

    # Cyclical encoding
    SECONDS_PER_DAY = 86400.0
    days_since_epoch = trans_date_seconds / SECONDS_PER_DAY

    # Weekly: day of week (Monday=0)
    # Unix epoch (1970-01-01) was Thursday, so +4 to align Monday=0
    day_of_week_frac = tf.math.mod(days_since_epoch + 4, 7.0) / 7.0
    outputs['trans_date_weekly_sin'] = tf.sin(2.0 * math.pi * day_of_week_frac)
    outputs['trans_date_weekly_cos'] = tf.cos(2.0 * math.pi * day_of_week_frac)

    # Monthly: day of month (approximated via 30.44 days)
    day_of_month_frac = tf.math.mod(days_since_epoch, 30.44) / 30.44
    outputs['trans_date_monthly_sin'] = tf.sin(2.0 * math.pi * day_of_month_frac)
    outputs['trans_date_monthly_cos'] = tf.cos(2.0 * math.pi * day_of_month_frac)

    # =========================================================================
    # CROSS FEATURES → Bucketize (for numeric/temporal) + Hash
    # =========================================================================

    # Cross: customer_id × city (buyerModel)
    outputs['customer_id_x_city_cross'] = tf.sparse.cross_hashed(
        inputs=[
            inputs['customer_id'],
            inputs['city']
        ],
        num_buckets=5000
    )

    return outputs
```

---

## Next Steps

### 1. TrainerModuleGenerator (Priority: High)

Implement the companion generator that produces TFX Trainer module code:

```python
class TrainerModuleGenerator:
    """
    Generates TFX Trainer module from FeatureConfig.

    The generated code:
    - Loads vocabularies from Transform artifacts
    - Creates embeddings with configured dimensions
    - Builds BuyerModel (Query Tower) and ProductModel (Candidate Tower)
    - Configures TFRS retrieval model
    """
```

**Key responsibilities:**

1. **Load Transform artifacts**
   ```python
   tf_transform_output = tft.TFTransformOutput(transform_output_dir)
   vocab = tf_transform_output.vocabulary_by_name('customer_id_vocab')
   ```

2. **Create embeddings from vocab indices**
   ```python
   embedding = tf.keras.Sequential([
       tf.keras.layers.StringLookup(vocabulary=vocab, mask_token=None),
       tf.keras.layers.Embedding(vocab_size + 1, embedding_dim)
   ])
   ```

3. **Build two-tower architecture**
   ```python
   class BuyerModel(tf.keras.Model):
       # Query tower - concatenates all buyer feature embeddings

   class ProductModel(tf.keras.Model):
       # Candidate tower - concatenates all product feature embeddings
   ```

4. **Configure TFRS model**
   ```python
   model = tfrs.models.Model(
       query_model=BuyerModel(...),
       candidate_model=ProductModel(...)
   )
   ```

### 2. UI for Viewing Generated Code (Priority: Medium)

Add a "View Code" button in the Feature Config wizard that opens a modal showing:
- Generated Transform code with syntax highlighting
- Copy-to-clipboard functionality
- "Regenerate" button
- Timestamp of last generation

### 3. Quick Test Pipeline Integration (Priority: High)

Create Vertex AI Pipeline that:
1. Reads generated Transform code from database
2. Writes it to a temporary module file
3. Executes TFX pipeline: ExampleGen → StatisticsGen → SchemaGen → Transform → Trainer
4. Returns metrics to the platform

### 4. Code Validation (Priority: Medium)

Add optional syntax validation before saving:
```python
def validate_generated_code(code: str) -> tuple[bool, str]:
    """
    Validate generated Python code is syntactically correct.
    Returns (is_valid, error_message)
    """
    try:
        compile(code, '<generated>', 'exec')
        return True, ''
    except SyntaxError as e:
        return False, str(e)
```

### 5. Sparse Tensor Handling (Priority: Low)

Currently, `tf.sparse.cross_hashed()` outputs sparse tensors. Consider:
- Converting to dense in Transform (increases TFRecord size)
- Converting to dense in Trainer (current approach, handles in embedding lookup)

---

## Files Modified

| File | Changes |
|------|---------|
| `ml_platform/models.py` | Added `generated_transform_code`, `generated_trainer_code`, `generated_at` fields |
| `ml_platform/modeling/services.py` | Added `PreprocessingFnGenerator` class |
| `ml_platform/modeling/api.py` | Added generator calls to create/update/clone; Added `get_generated_code` and `regenerate_code` endpoints |
| `ml_platform/modeling/urls.py` | Added routes for generated code endpoints |
| `ml_platform/migrations/0024_add_generated_code_fields.py` | Database migration |
| `templates/ml_platform/model_modeling.html` | Fixed CSRF token bug |

---

## Related Documentation

- [Phase: Modeling Domain](phase_modeling.md) - Feature engineering UI and workflow
- [TFX Recommenders Notebook](../past/recommenders.ipynb) - Reference implementation
