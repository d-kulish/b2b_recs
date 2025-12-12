# TFX Code Generation

## Document Purpose
This document describes the automatic TFX code generation system that converts Feature Configs and Model Configs into executable TFX Transform and Trainer modules for Vertex AI Pipelines.

**Last Updated**: 2025-12-12

---

## Overview

The ML Platform automatically generates TFX-compatible Python code from Feature Config and Model Config JSON schemas. This enables:

1. **No-code feature engineering** - Users configure features via the UI wizard
2. **No-code model architecture** - Users configure neural network architecture via Model Config
3. **Reproducible pipelines** - Transform code stored with FeatureConfig, Trainer code generated at runtime
4. **TFX/Vertex AI compatibility** - Output code works directly with TFX Transform and Trainer components

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
│           FEATURE CONFIG + MODEL CONFIG (Combined at Runtime)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      TrainerModuleGenerator                                  │
│                      (ml_platform/modeling/services.py)                      │
│                                                                              │
│  REQUIRES BOTH:                                                             │
│  - FeatureConfig: defines feature transformations                           │
│  - ModelConfig: defines neural network architecture                         │
│                                                                              │
│  Features:                                                                  │
│  - Load vocabularies from Transform artifacts                               │
│  - Create embeddings with configured dimensions                             │
│  - Build BuyerModel (Query Tower) and ProductModel (Candidate Tower)        │
│  - Configure tower layers from ModelConfig (Dense/Dropout/BatchNorm)        │
│  - Support L1, L2, and L1+L2 (elastic net) regularization                  │
│  - 6 optimizers: Adagrad, Adam, SGD, RMSprop, AdamW, FTRL                  │
│  - Retrieval algorithms: Brute Force or ScaNN                              │
│  - Implement run_fn() for TFX Trainer component                             │
│  - Provide serving signature for raw input → recommendations                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      GENERATED TRAINER CODE                                  │
│                      (generated at runtime, NOT stored)                      │
│                                                                              │
│  - BuyerModel class (Query Tower)                                           │
│  - ProductModel class (Candidate Tower)                                     │
│  - RetrievalModel class (TFRS model with configurable towers)               │
│  - run_fn() TFX entry point with configured optimizer                       │
│  - Serving signature with pre-computed candidate embeddings                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decision: Split Code Generation

### Transform Code (Stored)
- **Generated from**: FeatureConfig only
- **Storage**: `FeatureConfig.generated_transform_code` field
- **Generated when**: FeatureConfig is created, updated, or cloned
- **Rationale**: Transform code only depends on feature definitions, not model architecture

### Trainer Code (Runtime)
- **Generated from**: FeatureConfig + ModelConfig combined
- **Storage**: NOT stored - generated at runtime
- **Generated when**: QuickTest is started or code preview is requested
- **Rationale**: Trainer code depends on both feature definitions AND model architecture

This split allows users to:
1. Preview transform code immediately after saving a FeatureConfig
2. Experiment with different ModelConfigs using the same FeatureConfig
3. Mix and match configurations without storing redundant trainer code

---

## Implementation Details

### Database Schema

```python
# ml_platform/models.py

class FeatureConfig(models.Model):
    # ... existing fields ...

    # Generated TFX Transform code (stored - only depends on FeatureConfig)
    generated_transform_code = models.TextField(
        blank=True,
        help_text="Auto-generated TFX Transform preprocessing_fn code"
    )
    # Note: generated_trainer_code removed - now generated at runtime with ModelConfig
    generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When transform code was last generated"
    )


class ModelConfig(models.Model):
    """
    Dataset-independent model architecture configuration.
    Can be reused across any dataset/FeatureConfig combination.
    """
    name = models.CharField(max_length=255)
    model_type = models.CharField(max_length=50)  # retrieval, ranking, multitask

    # Tower architecture (JSON arrays of layer configs)
    buyer_tower_layers = models.JSONField(default=list)
    product_tower_layers = models.JSONField(default=list)
    output_embedding_dim = models.PositiveIntegerField(default=32)

    # Training hyperparameters
    optimizer = models.CharField(max_length=50, default='adagrad')
    learning_rate = models.FloatField(default=0.1)
    batch_size = models.PositiveIntegerField(default=4096)
    epochs = models.PositiveIntegerField(default=10)

    # Retrieval settings
    retrieval_algorithm = models.CharField(max_length=50, default='brute_force')
    top_k = models.PositiveIntegerField(default=100)
    # ... ScaNN params ...
```

**Design Decisions**:
- Transform code stored in database (Cloud Run has ephemeral filesystem)
- Trainer code generated at runtime (depends on both configs)
- ModelConfig is dataset-independent (global, reusable)

### PreprocessingFnGenerator

Located in `ml_platform/modeling/services.py`, generates TFX Transform `preprocessing_fn` code.

#### Feature Type Mappings

| Feature Config | TFX Transform Output | Output Name |
|----------------|---------------------|-------------|
| Text (data_type='text') | `tft.compute_and_apply_vocabulary()` | `{column}` (vocab index) |
| Numeric normalize | `tft.scale_to_z_score()` | `{column}_norm` (float) |
| Numeric bucketize | `tft.bucketize()` | `{column}_bucket` (bucket index) |
| Temporal normalize | `tft.scale_to_z_score()` | `{column}_norm` (float) |
| Temporal cyclical | `tf.sin/cos()` | `{column}_{cycle}_sin`, `{column}_{cycle}_cos` |
| Temporal bucketize | `tft.bucketize()` | `{column}_bucket` (bucket index) |
| Cross (text × text) | `tft.hash_strings()` | `{col1}_x_{col2}_cross` (dense INT64) |
| Cross (with numeric) | bucketize + `tft.hash_strings()` | `{col1}_x_{col2}_cross` (dense INT64) |

### TrainerModuleGenerator

Located in `ml_platform/modeling/services.py`, generates TFX Trainer module code.

**Constructor signature:**
```python
def __init__(self, feature_config: 'FeatureConfig', model_config: 'ModelConfig'):
    """
    Initialize with BOTH FeatureConfig and ModelConfig.

    Args:
        feature_config: Defines WHAT features are transformed (buyer/product features, crosses)
        model_config: Defines HOW the model is built (layers, optimizer, hyperparameters)
    """
```

#### Supported Layer Types

| Layer Type | Parameters | Code Generated |
|------------|------------|----------------|
| Dense | units, activation, l1_reg, l2_reg | `tf.keras.layers.Dense(units, activation, kernel_regularizer)` |
| Dropout | rate | `tf.keras.layers.Dropout(rate)` |
| BatchNorm | - | `tf.keras.layers.BatchNormalization()` |

#### Regularization Support

| Type | ModelConfig Field | Generated Code |
|------|-------------------|----------------|
| L1 only | `l1_reg > 0` | `kernel_regularizer=tf.keras.regularizers.l1(value)` |
| L2 only | `l2_reg > 0` | `kernel_regularizer=tf.keras.regularizers.l2(value)` |
| L1+L2 (elastic net) | both > 0 | `kernel_regularizer=tf.keras.regularizers.l1_l2(l1=val, l2=val)` |

#### Supported Optimizers

| Optimizer | ModelConfig Value | Generated Code |
|-----------|-------------------|----------------|
| Adagrad | `adagrad` | `tf.keras.optimizers.Adagrad(learning_rate)` |
| Adam | `adam` | `tf.keras.optimizers.Adam(learning_rate)` |
| SGD | `sgd` | `tf.keras.optimizers.SGD(learning_rate)` |
| RMSprop | `rmsprop` | `tf.keras.optimizers.RMSprop(learning_rate)` |
| AdamW | `adamw` | `tf.keras.optimizers.AdamW(learning_rate)` |
| FTRL | `ftrl` | `tf.keras.optimizers.Ftrl(learning_rate)` |

### API Endpoints

#### Get Generated Transform Code
```
GET /api/feature-configs/{config_id}/generated-code/?type=transform

Response:
{
  "success": true,
  "data": {
    "code": "# Auto-generated TFX Transform...",
    "code_type": "transform",
    "generated_at": "2025-12-10T10:30:00Z",
    "config_id": 5,
    "config_name": "Rich Features v1",
    "has_code": true,
    "is_valid": true
  }
}
```

Note: `type=trainer` is no longer supported here - use the combined endpoint below.

#### Regenerate Transform Code
```
POST /api/feature-configs/{config_id}/regenerate-code/
Body: { "type": "transform" }

Response:
{
  "success": true,
  "data": {
    "transform_code": "# Auto-generated TFX Transform...",
    "generated_at": "2025-12-10T10:35:00Z",
    "config_id": 5,
    "config_name": "Rich Features v1",
    "validation": {
      "transform_valid": true
    }
  },
  "message": "Transform code regenerated successfully"
}
```

#### Generate Trainer Code (NEW - Requires Both Configs)
```
POST /api/modeling/generate-trainer-code/
Body: {
  "feature_config_id": 5,
  "model_config_id": 3
}

Response:
{
  "success": true,
  "data": {
    "feature_config_id": 5,
    "feature_config_name": "Rich Features v1",
    "model_config_id": 3,
    "model_config_name": "Standard Retrieval",
    "trainer_code": "# Auto-generated TFX Trainer Module...",
    "transform_code": "# Auto-generated TFX Transform...",
    "validation": {
      "is_valid": true
    }
  },
  "message": "Trainer code generated successfully"
}
```

### Automatic Generation Triggers

**Transform code** is automatically generated when:
1. **Creating** a new feature config
2. **Updating** a feature config (if features changed)
3. **Cloning** a feature config

**Trainer code** is generated at runtime when:
1. **Starting a QuickTest** (with both feature_config_id and model_config_id)
2. **Requesting code preview** via `/api/modeling/generate-trainer-code/`

---

## Quick Test Pipeline Integration

### Overview

Quick Test is a mini TFX pipeline on Vertex AI that validates feature configurations before expensive full training runs. It now requires **both** a FeatureConfig (features) and a ModelConfig (architecture).

### API Changes

**Start Quick Test (Updated)**
```
POST /api/feature-configs/{config_id}/quick-test/
Body: {
  "model_config_id": 3,     // REQUIRED - Model Config to use
  "epochs": 10,             // Optional - overrides ModelConfig value
  "batch_size": 4096,       // Optional - overrides ModelConfig value
  "learning_rate": 0.001    // Optional - overrides ModelConfig value
}
```

The trainer code is generated at submission time using both configs.

### Data Flow

```
FeatureConfig + ModelConfig → TrainerModuleGenerator → trainer_code (runtime)
                                      ↓
                              Upload to GCS
                                      ↓
                          Vertex AI Pipeline
                                      ↓
           Pipeline: ExampleGen → StatisticsGen → SchemaGen → Transform → Trainer
                                      ↓
                          metrics.json → QuickTest model → UI
```

---

## UI Changes

### Features Chapter
- **Code button**: Shows transform code only (stored in FeatureConfig)
- **Test button**: Opens dialog requiring ModelConfig selection

### Model Structure Chapter
- **No Code button**: Removed - trainer code requires FeatureConfig to be selected
- **Clone button**: Only action available on ModelConfig cards

### QuickTest Dialog
- **ModelConfig selector**: Required dropdown to select model architecture
- **Training params**: Pre-filled from selected ModelConfig, can be overridden

---

## Files Modified

| File | Changes |
|------|---------|
| `ml_platform/models.py` | Removed `generated_trainer_code` from FeatureConfig; Added `model_config` FK to QuickTest |
| `ml_platform/modeling/services.py` | Updated `TrainerModuleGenerator` to require ModelConfig; Added L1/L2/L1+L2 regularization; Added 6 optimizer support |
| `ml_platform/modeling/api.py` | Added `generate_trainer_code` endpoint; Updated `regenerate_code` to only support transform; Removed trainer generation from create/update/clone |
| `ml_platform/modeling/urls.py` | Added route for `generate-trainer-code` |
| `ml_platform/pipelines/api.py` | Updated `start_quick_test` to require `model_config_id`; Generate trainer code at runtime |
| `ml_platform/pipelines/services.py` | Updated `submit_quick_test` to accept `model_config` and `trainer_code` |
| `templates/ml_platform/model_modeling.html` | Added ModelConfig selector to QuickTest dialog; Removed Code button from Model Structure chapter |

---

## Related Documentation

- [Phase: Modeling Domain](phase_modeling.md) - Feature engineering UI and workflow
- [Phase: Model Structure](phase_model_structure.md) - Model architecture configuration
- [TFX Recommenders Notebook](../past/recommenders.ipynb) - Reference implementation
