# Phase: Model Structure

## Document Purpose
This document provides detailed specifications for implementing the **Model Structure** chapter in the ML Platform Modeling page. This feature enables users to configure neural network architecture independently from feature engineering, allowing flexible experimentation with different model architectures.

**Last Updated**: 2025-12-14

---

## Implementation Status

### Completed (Phase 1 - Retrieval)

| Component | Status | Notes |
|-----------|--------|-------|
| **Backend** | | |
| `ModelConfig` Django model | ✅ Done | `ml_platform/models.py:745-955` |
| Database migration | ✅ Done | `ml_platform/migrations/0028_add_model_config.py` |
| ModelConfig API endpoints | ✅ Done | `ml_platform/modeling/api.py:981-1501` |
| URL routing | ✅ Done | `ml_platform/modeling/urls.py:50-75` |
| Django admin registration | ✅ Done | `ml_platform/admin.py:141-168` |
| Preset system (5 presets) | ✅ Done | minimal, standard, deep, asymmetric, regularized |
| Retrieval algorithm fields | ✅ Done | `retrieval_algorithm`, `top_k`, `scann_num_leaves`, `scann_leaves_to_search` |
| **Frontend** | | |
| Model Structure chapter UI | ✅ Done | Cards grid with loading/empty states |
| ModelConfig card component | ✅ Done | Shows type badge, tower summaries, training params |
| 3-step wizard modal | ✅ Done | Basic Info → Architecture → Training |
| Step 1: Model type + presets | ✅ Done | Retrieval active, Ranking/Multitask disabled |
| Step 2: Tower builder | ✅ Done | Layer list with drag-drop reordering, layer edit modals |
| Step 2: Retrieval Algorithm | ✅ Done | Brute Force (default) / ScaNN selection with Top-K config |
| Step 2: Model summary | ✅ Done | Keras-style params display (Total/Trainable/Non-trainable) |
| Step 3: Training parameters | ✅ Done | Card-based layout: Optimizer panel (6 options with auto-LR suggest) + Hyperparameters panel (LR with presets, batch size) |
| View/Edit/Clone/Delete | ✅ Done | All CRUD operations functional |
| Layer drag-drop reordering | ✅ Done | Layers movable except output layer (locked at bottom) |
| Unified layer edit modals | ✅ Done | Consistent styling with dimension button selectors |

### Completed (Phase 2 - Ranking) - 2025-12-13 (Updated)

| Component | Status | Notes |
|-----------|--------|-------|
| **Backend** | | |
| `loss_function` field on ModelConfig | ✅ Done | `ml_platform/models.py` - MSE, Binary CE, Huber |
| `rating_column` field on QuickTest | ✅ Done | Stored per test, not per ModelConfig (dataset-independent) |
| Migration 0031 (loss_function) | ✅ Done | `ml_platform/migrations/0031_add_loss_function_to_modelconfig.py` |
| Migration 0032 (rating_column) | ✅ Done | `ml_platform/migrations/0032_add_rating_column_to_quicktest.py` |
| Rating Head presets API | ✅ Done | `/api/model-configs/rating-head-presets/` - Minimal, Standard, Deep |
| Loss function info API | ✅ Done | `/api/model-configs/loss-functions/` |
| Updated serialization | ✅ Done | `serialize_model_config()` includes `loss_function`, `loss_function_display` |
| Updated create/update/clone | ✅ Done | Handle `loss_function` and `rating_head_layers` |
| **Frontend - Wizard** | | |
| Step 1: Enable Ranking button | ✅ Done | Ranking model type now selectable |
| Step 2: Rating Head builder | ✅ Done | Violet themed section below towers |
| Step 2: Rating Head auto-population | ✅ Done | Layers derived from tower preset (no separate presets) |
| Step 3: Loss Function selector | ✅ Done | MSE, Binary CE, Huber with help text |
| **Frontend - Display** | | |
| Model cards: 3-row layout | ✅ Done | Row 1: Buyer/Product bars, Row 2: Params/Ranking bar |
| Model cards: Ranking bar visualization | ✅ Done | Same proportional bar style as Buyer/Product (violet) |
| Model cards: Loss function badge | ✅ Done | Shows loss function on Ranking cards |
| View modal: Rating Head section | ✅ Done | Same card-layer style as Buyer/Product towers (violet) |
| **QuickTest Integration** | | |
| Rating column selector UI | ✅ Done | In QuickTest dialog, only for Ranking models |
| Dynamic column population | ✅ Done | Fetches numeric columns from dataset |
| Validation | ✅ Done | Requires rating column for Ranking models |
| API payload update | ✅ Done | `rating_column` included in QuickTest request |

### Completed (Phase 3 - Multitask) - 2025-12-14

| Component | Status | Notes |
|-----------|--------|-------|
| **Frontend - Wizard** | | |
| Step 1: Enable Multitask button | ✅ Done | Multitask model type now selectable |
| Step 2: Show Rating Head + Retrieval Algorithm | ✅ Done | Both sections visible for Multitask |
| Step 2: Multitask Architecture Diagram | ✅ Done | Visual diagram showing both paths (retrieval + ranking) |
| Step 3: Loss Function selector | ✅ Done | Same as Ranking models (MSE, BCE, Huber) |
| Step 3: Loss Weight sliders | ✅ Done | Retrieval Weight + Ranking Weight (0.0-1.0 each) |
| Step 3: Weight validation | ✅ Done | At least one weight must be > 0 |
| **Frontend - Display** | | |
| Model cards: Multitask badge | ✅ Done | Pink gradient badge for Multitask models |
| Model cards: Weights display | ✅ Done | Shows "Ret 1.0 / Rank 1.0" on Multitask cards |
| Summary panel: Weights row | ✅ Done | Shows both retrieval and ranking info |
| **State & API** | | |
| mcState: retrievalWeight/rankingWeight | ✅ Done | Default: 1.0 / 1.0 (balanced start) |
| Save/Load/Edit/Reset for weights | ✅ Done | Full CRUD support for Multitask configs |

### Pending

| Component | Status | Notes |
|-----------|--------|-------|
| **Code Generation** | | |
| TrainerModuleGenerator for Ranking | ⏳ Pending | Generate RankingModel with Rating Head |
| TrainerModuleGenerator for Multitask | ⏳ Pending | Generate MultitaskModel with both tasks |
| Generate MSE/BCE/Huber loss code | ⏳ Pending | Based on `loss_function` selection |
| Ranking model serving signature | ⏳ Pending | Input → rating prediction |
| Multitask model serving signature | ⏳ Pending | Input → (similarity, rating) outputs |

### API Endpoints Implemented

| Method | Endpoint | Status |
|--------|----------|--------|
| `GET` | `/api/model-configs/` | ✅ |
| `POST` | `/api/model-configs/create/` | ✅ |
| `GET` | `/api/model-configs/{id}/` | ✅ |
| `PUT` | `/api/model-configs/{id}/update/` | ✅ |
| `DELETE` | `/api/model-configs/{id}/delete/` | ✅ |
| `POST` | `/api/model-configs/{id}/clone/` | ✅ |
| `GET` | `/api/model-configs/presets/` | ✅ |
| `GET` | `/api/model-configs/presets/{name}/` | ✅ |
| `POST` | `/api/model-configs/validate/` | ✅ |
| `GET` | `/api/model-configs/rating-head-presets/` | ✅ |
| `GET` | `/api/model-configs/loss-functions/` | ✅ |

### Recent Updates (December 2025)

#### Ranking Model Support (2025-12-13, Updated)

**Phase 2 Complete:** Full Ranking model configuration is now available.

**Update (2025-12-13):** Simplified Rating Head configuration:
- Removed separate Rating Head preset selector from Step 2
- Rating Head layers now auto-derived from tower preset selected in Step 1
- Updated color scheme from pink to violet for better business appearance
- Model cards now show Ranking bar with same proportional visualization as Buyer/Product
- View modal uses consistent card-layer styling across all 3 towers

**Architecture:**
Ranking models differ from Retrieval models by concatenating buyer and product embeddings, then passing them through a Rating Head to predict a scalar rating:

```
Ranking Model Architecture:
┌───────────┐   ┌───────────┐
│   Buyer   │   │  Product  │
│   Tower   │   │   Tower   │
└─────┬─────┘   └─────┬─────┘
      │               │
      └───────┬───────┘
          [concat]
              ↓
      ┌─────────────┐
      │ Rating Head │
      │ Dense(256)  │
      │ Dense(64)   │
      │ Dense(1)    │
      └──────┬──────┘
             ↓
         rating (scalar)
```

**Rating Head Architecture:**
The Rating Head layers are automatically derived from the tower preset selected in Step 1:

| Tower Preset | Tower Structure | Rating Head Structure |
|--------------|-----------------|----------------------|
| Minimal | 64→32 | 64→32→1 |
| Standard | 128→64→32 | 128→64→32→1 |
| Deep | 256→128→64→32 | 256→128→64→32→1 |
| Regularized | 128→64→32 (with dropout) | 128→64→32→1 (no dropout) |

**Key Design Decisions:**
- Rating Head follows the same Dense layer structure as the towers
- No regularization (L2, dropout) in Rating Head by default
- Final Dense(1) layer with linear activation for scalar output
- Users can manually edit layers in Step 2 if needed

**Loss Functions:**
| Loss | Field Value | Use Case |
|------|-------------|----------|
| Mean Squared Error | `mse` | Continuous ratings (1.0-5.0) |
| Binary Crossentropy | `binary_crossentropy` | Binary feedback (click/no-click) |
| Huber | `huber` | Ratings with outliers (robust) |

**Rating Column Selection:**
- Rating column is selected at QuickTest time, NOT stored in ModelConfig
- This keeps ModelConfig dataset-independent (reusable across datasets)
- Only numeric columns from the dataset are shown as options

**UI Changes:**
- Step 1: Ranking button enabled; preset selection applies to all 3 models (Buyer, Product, Rating Head)
- Step 2: Rating Head builder section (violet theme) appears below towers for Ranking models
  - No separate preset selector for Rating Head (removed)
  - Layers auto-populated from tower preset + Dense(1) output
  - Users can manually edit layers if needed
- Step 3: Loss Function selector with help text (MSE recommended for continuous ratings)
- Model cards layout for Ranking:
  - Row 1: Buyer bar (blue) | Product bar (green)
  - Row 2: Hyperparameters | Ranking bar (violet)
  - All bars use proportional width based on total neurons
- View modal: Rating Head section with same card-layer style as Buyer/Product (violet theme)

**Files Modified:**
- `ml_platform/models.py` - Added `loss_function` field, rating head presets
- `ml_platform/modeling/api.py` - New endpoints, updated serialization
- `ml_platform/modeling/urls.py` - Added rating head presets and loss function routes
- `templates/ml_platform/model_modeling.html` - Wizard and display updates
- `templates/ml_platform/model_experiments.html` - Rating column selector in QuickTest

#### Multitask Model Support (2025-12-14)

**Phase 3 Complete:** Full Multitask model configuration is now available.

**Architecture:**
Multitask models combine both Retrieval and Ranking tasks, training both objectives simultaneously with configurable loss weights:

```
Multitask Model Architecture:
┌───────────┐   ┌───────────┐
│   Buyer   │   │  Product  │
│   Tower   │   │   Tower   │
└─────┬─────┘   └─────┬─────┘
      │               │
      ▼               ▼
 [32D embed]    [32D embed]
      │               │
      ├───────┬───────┤
      │       │       │
      ▼       ▼       ▼
┌──────────┐  ┌────────────────────┐
│Dot Product│  │   Concatenate     │
│(Retrieval)│  │      [64D]        │
└────┬─────┘  └─────────┬──────────┘
     │                  │
     ▼                  ▼
[Similarity]     ┌─────────────┐
                 │ Rating Head │
                 │ 128→64→32→1 │
                 └──────┬──────┘
                        │
                        ▼
                   [Rating]

Combined Loss = retrieval_weight × Retrieval Loss + ranking_weight × Ranking Loss
```

**Loss Weighting Strategy:**
- **Independent weights** (not normalized to sum to 1.0)
- Allows users to emphasize one task without diminishing the other
- Example: retrieval_weight=1.0, ranking_weight=0.5 emphasizes retrieval
- Validation: At least one weight must be > 0
- Default: 1.0 / 1.0 (balanced start for initial experiments)

**Weight Guidelines:**
| Scenario | Retrieval Weight | Ranking Weight | Use Case |
|----------|-----------------|----------------|----------|
| Balanced | 1.0 | 1.0 | Default starting point |
| Retrieval-focused | 1.0 | 0.3 | When finding candidates is priority |
| Ranking-focused | 0.3 | 1.0 | When accurate rating prediction is critical |
| Retrieval-only | 1.0 | 0.0 | Same as pure Retrieval model |

**UI Changes:**
- Step 1: Multitask button enabled (no longer grayed out)
- Step 2: Shows both Retrieval Algorithm section AND Rating Head builder
- Step 2: Multitask Architecture Diagram - Visual representation of combined model
- Step 3: Loss Function selector (same as Ranking)
- Step 3: Loss Weighting panel with dual sliders:
  - Retrieval Weight slider (0.0-1.0, blue gradient)
  - Ranking Weight slider (0.0-1.0, amber gradient)
  - Real-time validation warning if both weights are 0
  - Info banner explaining transfer learning benefits
- Model cards: Pink badge with "Multitask" label
- Model cards: Shows weights in hyperparameters section

**Files Modified:**
- `templates/ml_platform/model_modeling.html`:
  - Step 1: Enabled multitask option with onclick handler
  - Step 2: Added `multitaskArchSection` with visual architecture diagram
  - Step 3: Added `multitaskWeightSection` with weight sliders
  - JavaScript: Added weight slider functions and validation
  - CSS: Added styles for weight sliders and architecture diagram
  - Updated save/load/reset functions to handle weights

#### Step 3 Training UI Redesign (2025-12-11)

**UI Changes:**
- **Card-based layout** - Two-panel design matching Step 2 (Optimizer + Hyperparameters)
- **6 optimizers** - Added RMSprop, AdamW, FTRL to Adagrad/Adam/SGD
- **Auto-suggest learning rate** - Selecting an optimizer automatically sets recommended LR
- **LR preset buttons** - Quick-select buttons (0.001, 0.01, 0.05, 0.1) centered below input
- **Epochs removed** - No longer configured in ModelConfig; set per experiment/training run
- **Button renamed** - Changed from "Create" to "Save" for consistency

**Backend Changes:**
- Added `OPTIMIZER_RMSPROP`, `OPTIMIZER_ADAMW`, `OPTIMIZER_FTRL` constants
- Removed `epochs` from ModelConfig wizard (still available for experiments)

**JavaScript Functions Added:**
- `selectOptimizer(optimizer)` - Handles optimizer selection + auto-LR suggest
- `setLearningRate(value)` - Sets LR and highlights matching preset button
- `getSelectedOptimizer()` - Returns currently selected optimizer

---

## Overview

### Problem Statement
The current system generates Trainer code with a fixed architecture (128→64→32 dense layers). Users cannot:
- Experiment with different tower architectures
- Configure training hyperparameters
- Choose between model types (Retrieval, Ranking, Multitask)
- Test various architecture combinations with the same feature set

### Solution
Introduce **ModelConfig** as a separate entity from **FeatureConfig**, enabling:
1. Independent architecture configuration
2. Reusable model configurations across different feature sets
3. Visual tower builder UI
4. Support for multiple model types (phased rollout)

### Key Principle
**Separation of Concerns:**
- **FeatureConfig** = WHAT features and how to transform them (embeddings, crosses, normalizations)
- **ModelConfig** = HOW to process those features (tower architecture, training params)

---

## Architecture Overview

### Entity Relationships

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ENTITY RELATIONSHIPS                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Dataset (1) ──────────────< FeatureConfig (N)                         │
│                                     │                                    │
│                                     │ (selected for training)            │
│                                     ▼                                    │
│   ModelConfig (independent) ───────(*)───────────────> QuickTest (N)    │
│                                                                          │
│   FeatureConfig: Defines input tensors (Buyer: 104D, Product: 72D)      │
│   ModelConfig:   Defines how to process tensors (tower layers, optimizer)│
│   QuickTest:     Combines both for training validation                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Model Types (All Implemented)

| Phase | Model Type | Description | Use Case | Status |
|-------|------------|-------------|----------|--------|
| **1** | Retrieval | Two-tower model with dot-product similarity | Large catalog, fast ANN serving, Recall@K optimization | ✅ Done |
| **2** | Ranking | Concatenated embeddings → rating prediction | Re-ranking shortlist, explicit rating prediction, RMSE optimization | ✅ Done |
| **3** | Multitask | Combined retrieval + ranking with loss weights | Sparse data, transfer learning, balanced optimization | ✅ Done |

### Reference Implementations

Based on official TensorFlow Recommenders tutorials:

| Model Type | Reference Notebook | Key Components |
|------------|-------------------|----------------|
| Retrieval | `past/recommenders.ipynb` | `tfrs.tasks.Retrieval`, `FactorizedTopK` metrics |
| Ranking | `past/ranking_tfx.ipynb` | `tfrs.tasks.Ranking`, `MeanSquaredError` loss |
| Multitask | `past/multitask.ipynb` | Both tasks with configurable loss weights |

---

## Data Model

### ModelConfig Entity

```python
# ml_platform/models.py

class ModelConfig(models.Model):
    """
    Defines neural network architecture and training configuration.
    Completely independent from Dataset/FeatureConfig - can be used with any feature set.
    """

    # ═══════════════════════════════════════════════════════════════
    # BASIC INFO
    # ═══════════════════════════════════════════════════════════════

    name = models.CharField(
        max_length=255,
        help_text="Descriptive name (e.g., 'Standard Retrieval v1')"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of this configuration"
    )

    # ═══════════════════════════════════════════════════════════════
    # MODEL TYPE
    # ═══════════════════════════════════════════════════════════════

    MODEL_TYPE_CHOICES = [
        ('retrieval', 'Retrieval'),
        ('ranking', 'Ranking'),
        ('multitask', 'Multitask'),
    ]
    model_type = models.CharField(
        max_length=20,
        choices=MODEL_TYPE_CHOICES,
        default='retrieval',
        help_text="Type of recommendation model"
    )

    # ═══════════════════════════════════════════════════════════════
    # TOWER ARCHITECTURE
    # ═══════════════════════════════════════════════════════════════

    buyer_tower_layers = models.JSONField(
        default=list,
        help_text="Buyer/Query tower layer configurations"
    )
    # Schema: Array of layer config objects
    # [
    #   {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
    #   {"type": "dropout", "rate": 0.2},
    #   {"type": "batch_norm"},
    #   {"type": "layer_norm", "epsilon": 1e-6},
    #   {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
    #   {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0}
    # ]

    product_tower_layers = models.JSONField(
        default=list,
        help_text="Product/Candidate tower layer configurations"
    )

    rating_head_layers = models.JSONField(
        default=list,
        help_text="Rating prediction layers for ranking/multitask (after embedding concatenation)"
    )
    # Used only for ranking/multitask models
    # [
    #   {"type": "dense", "units": 256, "activation": "relu"},
    #   {"type": "dense", "units": 64, "activation": "relu"},
    #   {"type": "dense", "units": 1, "activation": null}  # Final scalar output
    # ]

    output_embedding_dim = models.IntegerField(
        default=32,
        help_text="Dimension of final tower output embeddings (must match between towers)"
    )

    share_tower_weights = models.BooleanField(
        default=False,
        help_text="Use identical weights for both towers (requires identical architecture)"
    )

    # ═══════════════════════════════════════════════════════════════
    # TRAINING HYPERPARAMETERS
    # ═══════════════════════════════════════════════════════════════

    OPTIMIZER_CHOICES = [
        ('adagrad', 'Adagrad'),
        ('adam', 'Adam'),
        ('sgd', 'SGD'),
        ('rmsprop', 'RMSprop'),
        ('adamw', 'AdamW'),
        ('ftrl', 'FTRL'),
    ]
    optimizer = models.CharField(
        max_length=20,
        choices=OPTIMIZER_CHOICES,
        default='adagrad',
        help_text="Optimizer algorithm"
    )

    learning_rate = models.FloatField(
        default=0.1,
        help_text="Learning rate for optimizer"
    )

    batch_size = models.IntegerField(
        default=4096,
        help_text="Training batch size"
    )

    # Note: epochs is NOT stored in ModelConfig. It is specified per experiment/training run
    # to allow flexibility in experimentation (e.g., quick test with 2 epochs, full training with 20+).

    # ═══════════════════════════════════════════════════════════════
    # MULTITASK CONFIGURATION
    # ═══════════════════════════════════════════════════════════════

    retrieval_weight = models.FloatField(
        default=1.0,
        help_text="Weight for retrieval loss in multitask model (0.0-1.0)"
    )

    ranking_weight = models.FloatField(
        default=0.0,
        help_text="Weight for ranking loss in multitask model (0.0-1.0)"
    )

    # Note: rating_column is NOT stored here because ModelConfig is dataset-independent.
    # It is specified at QuickTest time when the user selects which column to use.

    # ═══════════════════════════════════════════════════════════════
    # RETRIEVAL ALGORITHM CONFIGURATION
    # ═══════════════════════════════════════════════════════════════

    RETRIEVAL_ALGORITHM_BRUTE_FORCE = 'brute_force'
    RETRIEVAL_ALGORITHM_SCANN = 'scann'

    RETRIEVAL_ALGORITHM_CHOICES = [
        (RETRIEVAL_ALGORITHM_BRUTE_FORCE, 'Brute Force'),
        (RETRIEVAL_ALGORITHM_SCANN, 'ScaNN'),
    ]

    retrieval_algorithm = models.CharField(
        max_length=20,
        choices=RETRIEVAL_ALGORITHM_CHOICES,
        default=RETRIEVAL_ALGORITHM_BRUTE_FORCE,
        help_text="Algorithm for top-K candidate retrieval"
    )

    top_k = models.IntegerField(
        default=100,
        help_text="Number of top candidates to retrieve"
    )

    # ScaNN-specific parameters (only used when retrieval_algorithm='scann')
    scann_num_leaves = models.IntegerField(
        default=100,
        help_text="Number of partitions for ScaNN index (recommended: sqrt(catalog_size))"
    )

    scann_leaves_to_search = models.IntegerField(
        default=10,
        help_text="Number of partitions to search at query time"
    )

    # ═══════════════════════════════════════════════════════════════
    # METADATA
    # ═══════════════════════════════════════════════════════════════

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Model Configuration'
        verbose_name_plural = 'Model Configurations'

    def __str__(self):
        return f"{self.name} ({self.get_model_type_display()})"

    # ═══════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════════

    def get_buyer_tower_summary(self):
        """Return human-readable summary like '128→64→32'"""
        units = [l['units'] for l in self.buyer_tower_layers if l.get('type') == 'dense']
        return '→'.join(map(str, units)) if units else 'Empty'

    def get_product_tower_summary(self):
        """Return human-readable summary like '128→64→32'"""
        units = [l['units'] for l in self.product_tower_layers if l.get('type') == 'dense']
        return '→'.join(map(str, units)) if units else 'Empty'

    def get_rating_head_summary(self):
        """Return human-readable summary for rating head"""
        units = [l['units'] for l in self.rating_head_layers if l.get('type') == 'dense']
        return '→'.join(map(str, units)) if units else 'None'

    def count_layers(self, tower='buyer'):
        """Count total layers in a tower"""
        layers = self.buyer_tower_layers if tower == 'buyer' else self.product_tower_layers
        return len(layers)

    def towers_are_identical(self):
        """Check if both towers have identical architecture (required for weight sharing)"""
        return self.buyer_tower_layers == self.product_tower_layers

    def estimate_params(self, buyer_input_dim=None, product_input_dim=None):
        """
        Estimate total trainable parameters.

        Args:
            buyer_input_dim: Input dimension from FeatureConfig buyer tensor
            product_input_dim: Input dimension from FeatureConfig product tensor

        Returns:
            Estimated parameter count (int)
        """
        total = 0

        # Buyer tower
        prev_dim = buyer_input_dim or 100  # Default estimate
        for layer in self.buyer_tower_layers:
            if layer.get('type') == 'dense':
                units = layer['units']
                total += prev_dim * units + units  # weights + bias
                prev_dim = units

        # Product tower (skip if sharing weights)
        if not self.share_tower_weights:
            prev_dim = product_input_dim or 50  # Default estimate
            for layer in self.product_tower_layers:
                if layer.get('type') == 'dense':
                    units = layer['units']
                    total += prev_dim * units + units
                    prev_dim = units

        # Rating head (for ranking/multitask)
        if self.model_type in ['ranking', 'multitask'] and self.rating_head_layers:
            # Input is concatenated embeddings
            prev_dim = self.output_embedding_dim * 2
            for layer in self.rating_head_layers:
                if layer.get('type') == 'dense':
                    units = layer['units']
                    total += prev_dim * units + units
                    prev_dim = units

        return total

    def validate(self):
        """
        Validate configuration and return list of errors.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Basic validation
        if not self.buyer_tower_layers:
            errors.append("Buyer tower must have at least one layer")

        if not self.product_tower_layers:
            errors.append("Product tower must have at least one layer")

        # Weight sharing requires identical architectures
        if self.share_tower_weights and not self.towers_are_identical():
            errors.append("Weight sharing requires identical tower architectures")

        # Ranking/Multitask validation
        if self.model_type in ['ranking', 'multitask']:
            if not self.rating_head_layers:
                errors.append("Rating head layers required for ranking/multitask models")

            # Check rating head ends with units=1
            if self.rating_head_layers:
                last_layer = self.rating_head_layers[-1]
                if last_layer.get('type') == 'dense' and last_layer.get('units') != 1:
                    errors.append("Rating head must end with Dense(1) for scalar output")

        # Multitask weight validation
        if self.model_type == 'multitask':
            if self.retrieval_weight == 0 and self.ranking_weight == 0:
                errors.append("At least one loss weight must be greater than 0")

        # Output embedding dimension validation
        if self.output_embedding_dim < 8:
            errors.append("Output embedding dimension should be at least 8")
        if self.output_embedding_dim > 512:
            errors.append("Output embedding dimension should not exceed 512")

        return errors

    @classmethod
    def get_default_layers(cls):
        """Return default tower layers (standard preset)"""
        return [
            {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
        ]

    @classmethod
    def get_preset(cls, preset_name):
        """
        Return preset configuration dictionary.

        Args:
            preset_name: One of 'minimal', 'standard', 'deep', 'asymmetric', 'regularized'

        Returns:
            Dictionary with preset values
        """
        presets = {
            'minimal': {
                'name': 'Minimal',
                'description': 'Fast training, 2 layers, good for initial testing',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~3 min',
            },
            'standard': {
                'name': 'Standard',
                'description': 'Balanced architecture, 3 layers, recommended starting point',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~8 min',
            },
            'deep': {
                'name': 'Deep',
                'description': 'Maximum capacity, 4 layers, best for large datasets',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~15 min',
            },
            'asymmetric': {
                'name': 'Asymmetric',
                'description': 'Larger buyer tower for context-heavy features, smaller product tower',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                ],
                'output_embedding_dim': 64,
                'estimated_time': '~10 min',
            },
            'regularized': {
                'name': 'Regularized',
                'description': 'With dropout and L2 regularization to prevent overfitting',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.01},
                    {"type": "dropout", "rate": 0.2},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.01},
                    {"type": "dropout", "rate": 0.1},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.01},
                    {"type": "dropout", "rate": 0.2},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.01},
                    {"type": "dropout", "rate": 0.1},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~10 min',
            },
        }
        return presets.get(preset_name, presets['standard'])

    @classmethod
    def get_default_rating_head(cls):
        """Return default rating head layers for ranking/multitask"""
        return [
            {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 1, "activation": None},
        ]
```

### Layer Configuration Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Tower Layer Configuration",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["type"],
    "oneOf": [
      {
        "properties": {
          "type": {"const": "dense"},
          "units": {
            "type": "integer",
            "minimum": 1,
            "maximum": 2048,
            "description": "Number of neurons"
          },
          "activation": {
            "enum": ["relu", "leaky_relu", "gelu", "tanh", "sigmoid", null],
            "default": "relu",
            "description": "Activation function (null for linear)"
          },
          "l2_reg": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "default": 0.0,
            "description": "L2 regularization strength"
          }
        },
        "required": ["type", "units"]
      },
      {
        "properties": {
          "type": {"const": "dropout"},
          "rate": {
            "type": "number",
            "minimum": 0,
            "maximum": 0.9,
            "default": 0.2,
            "description": "Fraction of units to drop"
          }
        },
        "required": ["type", "rate"]
      },
      {
        "properties": {
          "type": {"const": "batch_norm"}
        },
        "required": ["type"]
      },
      {
        "properties": {
          "type": {"const": "layer_norm"},
          "epsilon": {
            "type": "number",
            "minimum": 1e-7,
            "maximum": 0.001,
            "default": 1e-6,
            "description": "Small constant for numerical stability"
          }
        },
        "required": ["type"]
      }
    ]
  }
}
```

### Updated QuickTest Model

```python
class QuickTest(models.Model):
    """
    Tracks quick test runs combining a FeatureConfig + ModelConfig.
    """

    # ═══════════════════════════════════════════════════════════════
    # CONFIGURATION REFERENCES
    # ═══════════════════════════════════════════════════════════════

    feature_config = models.ForeignKey(
        'FeatureConfig',
        on_delete=models.CASCADE,
        related_name='quick_tests',
        help_text="Feature configuration defining input tensors"
    )

    model_config = models.ForeignKey(
        'ModelConfig',
        on_delete=models.CASCADE,
        related_name='quick_tests',
        help_text="Model configuration defining architecture"
    )

    # ═══════════════════════════════════════════════════════════════
    # RUNTIME CONFIGURATION
    # ═══════════════════════════════════════════════════════════════

    # Rating column (specified at test time for ranking/multitask)
    # This comes from the Dataset columns, not from ModelConfig
    rating_column = models.CharField(
        max_length=255,
        blank=True,
        help_text="Column name for rating label (required for ranking/multitask)"
    )

    # Override training params for quick iteration (null = use ModelConfig defaults)
    epochs_override = models.IntegerField(
        null=True,
        blank=True,
        help_text="Override epochs from ModelConfig"
    )
    batch_size_override = models.IntegerField(
        null=True,
        blank=True,
        help_text="Override batch size from ModelConfig"
    )
    learning_rate_override = models.FloatField(
        null=True,
        blank=True,
        help_text="Override learning rate from ModelConfig"
    )

    # ═══════════════════════════════════════════════════════════════
    # EXISTING FIELDS (from current implementation)
    # ═══════════════════════════════════════════════════════════════

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Pipeline tracking
    vertex_pipeline_id = models.CharField(max_length=255, blank=True)
    current_stage = models.CharField(max_length=100, blank=True)
    progress_percent = models.IntegerField(default=0)

    # Results
    loss = models.FloatField(null=True, blank=True)
    recall_at_10 = models.FloatField(null=True, blank=True)
    recall_at_50 = models.FloatField(null=True, blank=True)
    recall_at_100 = models.FloatField(null=True, blank=True)

    # Ranking-specific metrics (Phase 2)
    rmse = models.FloatField(null=True, blank=True)
    mae = models.FloatField(null=True, blank=True)

    # Vocabulary stats (JSON)
    vocabulary_stats = models.JSONField(default=dict)

    # Warnings (JSON list)
    warnings = models.JSONField(default=list)

    # Cost and duration
    duration_seconds = models.IntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Error information
    error_message = models.TextField(blank=True)
    error_stage = models.CharField(max_length=100, blank=True)

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Quick Test'
        verbose_name_plural = 'Quick Tests'

    def get_effective_epochs(self):
        """Return epochs to use (override or model config default)"""
        return self.epochs_override or self.model_config.epochs

    def get_effective_batch_size(self):
        """Return batch size to use"""
        return self.batch_size_override or self.model_config.batch_size

    def get_effective_learning_rate(self):
        """Return learning rate to use"""
        return self.learning_rate_override or self.model_config.learning_rate
```

---

## API Endpoints

### ModelConfig CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/model-configs/` | List all model configs |
| `POST` | `/api/model-configs/` | Create new model config |
| `GET` | `/api/model-configs/{id}/` | Get model config details |
| `PUT` | `/api/model-configs/{id}/` | Update model config |
| `DELETE` | `/api/model-configs/{id}/` | Delete model config |
| `POST` | `/api/model-configs/{id}/clone/` | Clone model config |

### Presets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/model-configs/presets/` | List all available presets |
| `GET` | `/api/model-configs/presets/{name}/` | Get specific preset configuration |

### Code Generation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate-trainer-code/` | Generate trainer code for FeatureConfig + ModelConfig |
| `GET` | `/api/quick-tests/{id}/generated-code/` | Get generated code for a specific quick test |

#### Generate Trainer Code Request

```json
POST /api/generate-trainer-code/
{
  "feature_config_id": 5,
  "model_config_id": 3,
  "rating_column": "user_rating"  // Optional, required for ranking/multitask
}
```

#### Generate Trainer Code Response

```json
{
  "success": true,
  "data": {
    "trainer_code": "# Auto-generated TFX Trainer Module...",
    "is_valid": true,
    "validation_error": null,
    "feature_config": {
      "id": 5,
      "name": "Rich Features v2",
      "buyer_tensor_dim": 104,
      "product_tensor_dim": 72
    },
    "model_config": {
      "id": 3,
      "name": "Standard Retrieval",
      "model_type": "retrieval",
      "buyer_tower_summary": "128→64→32",
      "product_tower_summary": "128→64→32"
    }
  }
}
```

### Updated QuickTest Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/quick-tests/` | Start quick test (new format) |
| `GET` | `/api/quick-tests/{id}/` | Get status and results |
| `POST` | `/api/quick-tests/{id}/cancel/` | Cancel running test |
| `GET` | `/api/feature-configs/{id}/quick-tests/` | List tests for feature config |
| `GET` | `/api/model-configs/{id}/quick-tests/` | List tests for model config |

#### Start Quick Test Request (Updated)

```json
POST /api/quick-tests/
{
  "feature_config_id": 5,
  "model_config_id": 3,
  "rating_column": "user_rating",      // Optional, for ranking/multitask
  "epochs_override": 2,                 // Optional
  "batch_size_override": 4096,          // Optional
  "learning_rate_override": 0.1         // Optional
}
```

---

## User Interface

### Page Layout

The Model Structure chapter sits between Features and Quick Test on the Modeling page:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Modeling                                                                 │
│ Model: Customer Purchase Recommendations                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ ┌─ Chapter: Features ─────────────────────────────────────── [Compare] ─┐
│ │  [Existing Feature Config cards and wizard]                           │
│ └───────────────────────────────────────────────────────────────────────┘
│                                                                          │
│ ┌─ Chapter: Model Structure ─────────────────────────── [+ New Model] ─┐
│ │                                                                       │
│ │  ┌─────────────────────────────────────────────────────────────────┐ │
│ │  │ Standard Retrieval v1                            [View] [Edit]  │ │
│ │  │ Retrieval • Buyer: 128→64→32 • Product: 128→64→32               │ │
│ │  │ Adagrad @ 0.1 • Batch: 4096 • Output: 32D                       │ │
│ │  │ Updated: 2 hours ago                              [Clone] [Del] │ │
│ │  └─────────────────────────────────────────────────────────────────┘ │
│ │                                                                       │
│ │  ┌─────────────────────────────────────────────────────────────────┐ │
│ │  │ Deep Asymmetric v2                               [View] [Edit]  │ │
│ │  │ Retrieval • Buyer: 256→128→64 • Product: 128→64                 │ │
│ │  │ Adam @ 0.01 • Batch: 8192 • Output: 64D                         │ │
│ │  │ Updated: 1 day ago                                [Clone] [Del] │ │
│ │  └─────────────────────────────────────────────────────────────────┘ │
│ │                                                                       │
│ │  (max-height with scroll for many configs)                            │
│ │                                                                       │
│ └───────────────────────────────────────────────────────────────────────┘
│                                                                          │
│ ┌─ Chapter: Quick Test ──────────────────────────────────────────────┐  │
│ │  Feature Config: [Select ▼]    Model Config: [Select ▼]           │  │
│ │  [▶ Run Quick Test]                                                │  │
│ └───────────────────────────────────────────────────────────────────────┘
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Model Config Card Component

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Standard Retrieval v1                                    [View] [Edit]  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ ┌──────────────┐  Type: Retrieval                                       │
│ │  RETRIEVAL   │  Buyer Tower:   128 → 64 → 32                          │
│ │  Two-Tower   │  Product Tower: 128 → 64 → 32                          │
│ └──────────────┘  Output: 32D embedding                                 │
│                                                                          │
│ Optimizer: Adagrad @ 0.1    Batch: 4096    Epochs: 5                    │
│                                                                          │
│ ─────────────────────────────────────────────────────────────────────── │
│ Updated: 2 hours ago                                     [Clone] [Del]  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Wizard Step 1: Basic Info & Model Type

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Create Model Configuration                                  Step 1 of 3 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Model Name *                                                            │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Standard Retrieval v1                                             │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  Description                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Default 3-layer retrieval model for product recommendations       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  MODEL TYPE                                                              │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  ● RETRIEVAL                                                       │ │
│  │  ┌──────────────────────────────────────────────────────────────┐  │ │
│  │  │                                                              │  │ │
│  │  │     ┌───────────┐              ┌───────────┐                 │  │ │
│  │  │     │   Buyer   │              │  Product  │                 │  │ │
│  │  │     │   Tower   │              │   Tower   │                 │  │ │
│  │  │     │           │              │           │                 │  │ │
│  │  │     │  Dense    │              │  Dense    │                 │  │ │
│  │  │     │  layers   │              │  layers   │                 │  │ │
│  │  │     │     ↓     │              │     ↓     │                 │  │ │
│  │  │     │  32D emb  │              │  32D emb  │                 │  │ │
│  │  │     └─────┬─────┘              └─────┬─────┘                 │  │ │
│  │  │           │                          │                       │  │ │
│  │  │           └──────────┬───────────────┘                       │  │ │
│  │  │                      │                                       │  │ │
│  │  │               [dot product]                                  │  │ │
│  │  │                      ↓                                       │  │ │
│  │  │                 similarity                                   │  │ │
│  │  │                                                              │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  │                                                                     │ │
│  │  Two-Tower Architecture                                             │ │
│  │  • Best for large product catalogs (millions of items)              │ │
│  │  • Enables fast Approximate Nearest Neighbor (ANN) serving          │ │
│  │  • Optimizes Recall@K metrics                                       │ │
│  │                                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  ○ RANKING                                               (Phase 2) │ │
│  │  ┌──────────────────────────────────────────────────────────────┐  │ │
│  │  │                                                              │  │ │
│  │  │     ┌───────────┐   ┌───────────┐                            │  │ │
│  │  │     │   Buyer   │   │  Product  │                            │  │ │
│  │  │     │   Tower   │   │   Tower   │                            │  │ │
│  │  │     └─────┬─────┘   └─────┬─────┘                            │  │ │
│  │  │           │               │                                  │  │ │
│  │  │           └───────┬───────┘                                  │  │ │
│  │  │               [concat]                                       │  │ │
│  │  │                   ↓                                          │  │ │
│  │  │           ┌─────────────┐                                    │  │ │
│  │  │           │ Rating Head │                                    │  │ │
│  │  │           │   Dense     │                                    │  │ │
│  │  │           │   layers    │                                    │  │ │
│  │  │           └──────┬──────┘                                    │  │ │
│  │  │                  ↓                                           │  │ │
│  │  │               rating                                         │  │ │
│  │  │                                                              │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  │                                                                     │ │
│  │  Single-Tower + Rating Head                                         │ │
│  │  • Best for re-ranking a shortlist of candidates                    │ │
│  │  • Predicts explicit ratings (e.g., 1-5 stars)                      │ │
│  │  • Optimizes RMSE/MAE metrics                                       │ │
│  │  • Requires: Rating column in dataset                               │ │
│  │                                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  ○ MULTITASK                                             (Phase 3) │ │
│  │  ┌──────────────────────────────────────────────────────────────┐  │ │
│  │  │                                                              │  │ │
│  │  │     ┌───────────┐   ┌───────────┐                            │  │ │
│  │  │     │   Buyer   │   │  Product  │                            │  │ │
│  │  │     │   Tower   │   │   Tower   │                            │  │ │
│  │  │     └─────┬─────┘   └─────┬─────┘                            │  │ │
│  │  │           │               │                                  │  │ │
│  │  │           ├───────────────┤                                  │  │ │
│  │  │           │               │                                  │  │ │
│  │  │     [dot product]    [concat]                                │  │ │
│  │  │           ↓               ↓                                  │  │ │
│  │  │      similarity    ┌─────────────┐                           │  │ │
│  │  │           │        │ Rating Head │                           │  │ │
│  │  │           │        └──────┬──────┘                           │  │ │
│  │  │           │               ↓                                  │  │ │
│  │  │           │            rating                                │  │ │
│  │  │           │               │                                  │  │ │
│  │  │           └───────┬───────┘                                  │  │ │
│  │  │                   ↓                                          │  │ │
│  │  │          [weighted loss]                                     │  │ │
│  │  │                                                              │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  │                                                                     │ │
│  │  Combined Retrieval + Ranking                                       │ │
│  │  • Best for sparse interaction data (transfer learning)             │ │
│  │  • Learns from both implicit (watches) and explicit (ratings)       │ │
│  │  • Configurable loss weights for each task                          │ │
│  │  • Requires: Rating column in dataset                               │ │
│  │                                                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│                                               [Cancel]  [Continue →]    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Wizard Step 2: Tower Architecture (Visual Builder)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Create Model Configuration                                  Step 2 of 3 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  ARCHITECTURE PRESETS                                          [Custom] │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │ ○ Minimal   │ │ ● Standard  │ │ ○ Deep      │ │ ○ Asymmetric│        │
│  │   64→32     │ │  128→64→32  │ │ 256→128→   │ │ Buyer:      │        │
│  │   64→32     │ │  128→64→32  │ │  64→32     │ │  256→128→64 │        │
│  │             │ │             │ │ 256→128→   │ │ Product:    │        │
│  │   ~3 min    │ │   ~8 min    │ │  64→32     │ │  128→64     │        │
│  │             │ │             │ │   ~15 min  │ │   ~10 min   │        │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘        │
│                                                                          │
│  ┌─────────────┐                                                        │
│  │ ○ Regulariz.│  ⓘ Select a preset to start, then customize below      │
│  │  128→64→32  │                                                        │
│  │  +Dropout   │                                                        │
│  │  +L2 reg    │                                                        │
│  │   ~10 min   │                                                        │
│  └─────────────┘                                                        │
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  TOWER CONFIGURATION                                                     │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│  │ BUYER TOWER                     │  │ PRODUCT TOWER                   │
│  │                                 │  │                [Copy from Buyer]│
│  │ ┌─────────────────────────────┐ │  │ ┌─────────────────────────────┐ │
│  │ │ ▼ INPUT                     │ │  │ │ ▼ INPUT                     │ │
│  │ │   Buyer features tensor     │ │  │ │   Product features tensor   │ │
│  │ │   (dimension from Features) │ │  │ │   (dimension from Features) │ │
│  │ └─────────────────────────────┘ │  │ └─────────────────────────────┘ │
│  │              │                  │  │              │                  │
│  │              ▼                  │  │              ▼                  │
│  │ ┌─────────────────────────────┐ │  │ ┌─────────────────────────────┐ │
│  │ │ ≡ Dense(128)          ⚙ 🗑 │ │  │ │ ≡ Dense(128)          ⚙ 🗑 │ │
│  │ │   ReLU                      │ │  │ │   ReLU                      │ │
│  │ └─────────────────────────────┘ │  │ └─────────────────────────────┘ │
│  │              │                  │  │              │                  │
│  │              ▼                  │  │              ▼                  │
│  │ ┌─────────────────────────────┐ │  │ ┌─────────────────────────────┐ │
│  │ │ ≡ Dense(64)           ⚙ 🗑 │ │  │ │ ≡ Dense(64)           ⚙ 🗑 │ │
│  │ │   ReLU                      │ │  │ │   ReLU                      │ │
│  │ └─────────────────────────────┘ │  │ └─────────────────────────────┘ │
│  │              │                  │  │              │                  │
│  │              ▼                  │  │              ▼                  │
│  │ ┌─────────────────────────────┐ │  │ ┌─────────────────────────────┐ │
│  │ │ ≡ Dense(32)           ⚙ 🗑 │ │  │ │ ≡ Dense(32)           ⚙ 🗑 │ │
│  │ │   ReLU • Output Embedding   │ │  │ │   ReLU • Output Embedding   │ │
│  │ └─────────────────────────────┘ │  │ └─────────────────────────────┘ │
│  │                                 │  │                                 │
│  │ [+ Add Layer ▼]                 │  │ [+ Add Layer ▼]                 │
│  │                                 │  │                                 │
│  │ ───────────────────────────────│  │ ───────────────────────────────│
│  │ 3 layers • Est. ~12K params    │  │ 3 layers • Est. ~8K params     │
│  └─────────────────────────────────┘  └─────────────────────────────────┘
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  OUTPUT EMBEDDING                                                        │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  Dimension:  [8]  [16]  [32]  [64]  [128]  [Custom: ____]               │
│                          ▲                                               │
│  ⓘ Both towers output embeddings of this size for dot-product similarity│
│                                                                          │
│  ☐ Share tower weights                                                   │
│    Use identical weights for both towers. Requires identical             │
│    architecture. Recommended for small datasets to reduce overfitting.   │
│                                                                          │
│                                     [Cancel]  [← Back]  [Continue →]    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Layer Block Components

```
Dense Layer (default):
┌─────────────────────────────────────────────────────┐
│ ≡  Dense(128)                                 ⚙ 🗑 │  ← Blue left border
│    ReLU                                            │
└─────────────────────────────────────────────────────┘

Dense Layer with L2 regularization:
┌─────────────────────────────────────────────────────┐
│ ≡  Dense(128)                                 ⚙ 🗑 │  ← Blue left border
│    ReLU • L2: 0.01                                 │
└─────────────────────────────────────────────────────┘

Dropout Layer:
┌─────────────────────────────────────────────────────┐
│ ≡  Dropout(0.2)                               ⚙ 🗑 │  ← Orange left border
│    20% drop rate                                   │
└─────────────────────────────────────────────────────┘

Batch Normalization:
┌─────────────────────────────────────────────────────┐
│ ≡  BatchNorm                                  ⚙ 🗑 │  ← Purple left border
│    Normalize activations                           │
└─────────────────────────────────────────────────────┘

Output layer (last Dense, special styling):
┌─────────────────────────────────────────────────────┐
│ ≡  Dense(32)                                  ⚙ 🗑 │  ← Green left border
│    ReLU • Output Embedding                         │
└─────────────────────────────────────────────────────┘
```

### Add Layer Dropdown

```
┌──────────────────────────────────────┐
│ [+ Add Layer ▼]                      │
└──────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ ┌────────────────────────────────┐   │
│ │ Dense Layer                    │   │
│ │ Fully connected layer          │   │
│ │ with configurable units        │   │
│ └────────────────────────────────┘   │
│ ┌────────────────────────────────┐   │
│ │ Dropout                        │   │
│ │ Randomly drop units during     │   │
│ │ training (regularization)      │   │
│ └────────────────────────────────┘   │
│ ┌────────────────────────────────┐   │
│ │ Batch Normalization            │   │
│ │ Normalize layer activations    │   │
│ │ for faster training            │   │
│ └────────────────────────────────┘   │
└──────────────────────────────────────┘
```

### Layer Configuration Modal - Dense

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Configure Dense Layer                                                ✕  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Units (neurons)                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ [32]  [64]  [128]  [256]  [512]  [Custom: ____]                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                      ▲                                                   │
│  ⓘ Powers of 2 are recommended for GPU efficiency                       │
│                                                                          │
│  Activation Function                                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ ● ReLU        ○ LeakyReLU     ○ GELU        ○ None (Linear)       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ ReLU: Fast and effective for most cases. Outputs 0 for negative   │  │
│  │ inputs, passes positive inputs unchanged.                         │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  L2 Regularization                                                       │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ [0.0 ▼]                                                           │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  Options: 0 (none), 0.001, 0.01, 0.1                                     │
│  ⓘ Penalizes large weights to reduce overfitting. Start with 0,         │
│    try 0.001-0.01 if model overfits.                                     │
│                                                                          │
│                                               [Cancel]  [Apply]         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Layer Configuration Modal - Dropout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Configure Dropout Layer                                              ✕  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Dropout Rate                                                            │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ [0.1]  [0.2]  [0.3]  [0.5]  [Custom: ____]                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                 ▲                                                        │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Dropout randomly sets a fraction of inputs to 0 during training,  │  │
│  │ which helps prevent overfitting.                                  │  │
│  │                                                                    │  │
│  │ • 0.1-0.2: Light regularization                                   │  │
│  │ • 0.3-0.5: Strong regularization (use carefully)                  │  │
│  │                                                                    │  │
│  │ Note: Dropout is only applied during training, not inference.     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│                                               [Cancel]  [Apply]         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Wizard Step 3: Training Parameters

Step 3 uses a **card-based layout** matching Step 2's design, with two panels:
- **Optimizer Panel** (purple) - Select optimizer with auto-suggested learning rate
- **Hyperparameters Panel** (amber) - Configure learning rate and batch size

**Note:** Epochs are NOT configured here - they are specified per experiment/training run for flexibility.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Model Configuration                                         Step 3 of 3 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│  │ ▓▓ OPTIMIZER ▓▓                 │  │ ▒▒ HYPERPARAMETERS ▒▒           │
│  │ (purple border/background)      │  │ (amber border/background)       │
│  │                                 │  │                                 │
│  │ ┌─────────────┐ ┌─────────────┐ │  │ Learning Rate                   │
│  │ │ ● Adagrad   │ │ ○ Adam      │ │  │ ┌─────────────────────────────┐ │
│  │ │ Best for    │ │ Popular     │ │  │ │ [0.1________________]       │ │
│  │ │ sparse      │ │ general     │ │  │ └─────────────────────────────┘ │
│  │ │ embeddings  │ │ purpose     │ │  │                                 │
│  │ └─────────────┘ └─────────────┘ │  │ [0.001] [0.01] [0.05] [0.1]     │
│  │                                 │  │  (preset buttons, centered)     │
│  │ ┌─────────────┐ ┌─────────────┐ │  │                                 │
│  │ │ ○ SGD       │ │ ○ RMSprop   │ │  │ Batch Size                      │
│  │ │ Simple,     │ │ Good for    │ │  │ ┌─────────────────────────────┐ │
│  │ │ requires    │ │ non-        │ │  │ │ [4096_______________] ▼     │ │
│  │ │ tuning      │ │ stationary  │ │  │ └─────────────────────────────┘ │
│  │ └─────────────┘ └─────────────┘ │  │                                 │
│  │                                 │  │ ⓘ Larger batches train faster   │
│  │ ┌─────────────┐ ┌─────────────┐ │  │   but use more memory.          │
│  │ │ ○ AdamW     │ │ ○ FTRL      │ │  │                                 │
│  │ │ Adam with   │ │ Best for    │ │  └─────────────────────────────────┘
│  │ │ weight      │ │ very large  │ │
│  │ │ decay       │ │ sparse data │ │
│  │ └─────────────┘ └─────────────┘ │
│  │                                 │
│  └─────────────────────────────────┘
│                                                                          │
│                                         [Cancel]  [← Back]  [Save]       │
└─────────────────────────────────────────────────────────────────────────┘
```

**Auto-Suggest Learning Rate:**
When selecting an optimizer, the learning rate is automatically set to a recommended value:

| Optimizer | Auto-Suggested LR | Use Case |
|-----------|-------------------|----------|
| Adagrad | 0.1 | Sparse embeddings (default for recommenders) |
| Adam | 0.001 | General purpose, stable convergence |
| SGD | 0.01 | Simple, requires careful tuning |
| RMSprop | 0.001 | Non-stationary problems |
| AdamW | 0.001 | Adam with better weight decay regularization |
| FTRL | 0.1 | Very large sparse datasets |

**UI Features:**
- **Radio button cards** for optimizer selection with visual selection state
- **Preset buttons** for learning rate (0.001, 0.01, 0.05, 0.1) - centered below input
- **All buttons uniform size** (min-height ensures consistent appearance)
- **Button text: "Save"** (not "Create" to match edit mode)

### Step 3 Extension: Ranking/Multitask (Phase 2-3)

For Ranking and Multitask models, Step 3 includes additional sections:

```
│  ════════════════════════════════════════════════════════════════════   │
│  RATING HEAD ARCHITECTURE (Ranking/Multitask only)                       │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  After concatenating Buyer + Product embeddings (64D total):             │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                                                                    │  │
│  │ ┌─────────────────────────────────────────────────────────────┐   │  │
│  │ │ ≡ Dense(256)                                           ⚙ 🗑 │   │  │
│  │ │   ReLU                                                      │   │  │
│  │ └─────────────────────────────────────────────────────────────┘   │  │
│  │                            │                                      │  │
│  │                            ▼                                      │  │
│  │ ┌─────────────────────────────────────────────────────────────┐   │  │
│  │ │ ≡ Dense(64)                                            ⚙ 🗑 │   │  │
│  │ │   ReLU                                                      │   │  │
│  │ └─────────────────────────────────────────────────────────────┘   │  │
│  │                            │                                      │  │
│  │                            ▼                                      │  │
│  │ ┌─────────────────────────────────────────────────────────────┐   │  │
│  │ │   Dense(1)                                                  │   │  │
│  │ │   Linear • Rating Output                                    │   │  │
│  │ └─────────────────────────────────────────────────────────────┘   │  │
│  │                                                                    │  │
│  │ [+ Add Layer]                                                     │  │
│  │                                                                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  LOSS WEIGHTS (Multitask only)                                           │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  Balance between retrieval and ranking objectives:                       │
│                                                                          │
│  Retrieval ●─────────────────────────────────────○ Ranking              │
│     1.0              0.5                        0.0                      │
│                       ▲                                                  │
│                                                                          │
│  Current weights: Retrieval = 0.5, Ranking = 0.5 (balanced)              │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ ⓘ Adjust based on your optimization priorities:                   │  │
│  │                                                                    │  │
│  │ • Higher retrieval weight → Better Recall@K metrics               │  │
│  │   Good when you care most about finding relevant items            │  │
│  │                                                                    │  │
│  │ • Higher ranking weight → Better RMSE on ratings                  │  │
│  │   Good when predicting exact ratings is important                 │  │
│  │                                                                    │  │
│  │ • Balanced (0.5/0.5) → Good starting point                        │  │
│  │   Benefits from transfer learning between tasks                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
```

### Updated Quick Test Section

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Chapter: Quick Test                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  STEP 1: Select Configurations                                           │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  ┌────────────────────────────────┐  ┌────────────────────────────────┐ │
│  │ Feature Config                 │  │ Model Config                   │ │
│  │ ┌────────────────────────────┐ │  │ ┌────────────────────────────┐ │ │
│  │ │ [Rich Features v2      ▼] │ │  │ │ [Standard Retrieval    ▼] │ │ │
│  │ └────────────────────────────┘ │  │ └────────────────────────────┘ │ │
│  │                                │  │                                │ │
│  │ Dataset: Q4 2024 Transactions  │  │ Type: Retrieval                │ │
│  │ Buyer Tensor:   104D           │  │ Buyer:   128→64→32             │ │
│  │ Product Tensor: 72D            │  │ Product: 128→64→32             │ │
│  │ Cross Features: 2              │  │ Output:  32D                   │ │
│  │                                │  │ Optimizer: Adagrad @ 0.1       │ │
│  │ Transform: ✓ Valid             │  │ Batch: 4096 • Epochs: 5        │ │
│  └────────────────────────────────┘  └────────────────────────────────┘ │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ ⚠️ For Ranking/Multitask models, select Rating Column:            │  │
│  │                                                                    │  │
│  │ Rating Column:  [user_rating ▼]                                   │  │
│  │                                                                    │  │
│  │ Column info: FLOAT64 • Range: 1.0 - 5.0 • Mean: 3.52              │  │
│  │ Available: user_rating, quantity, total_amount                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  (Rating column section only shown for ranking/multitask models)         │
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  STEP 2: Quick Test Settings                                             │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  Override model defaults for quick iteration:                            │
│                                                                          │
│  Epochs           Batch Size         Learning Rate                       │
│  ┌──────────────┐ ┌──────────────┐   ┌──────────────┐                   │
│  │ [2 ▼]        │ │ [4096 ▼]     │   │ [0.1 ▼]      │                   │
│  └──────────────┘ └──────────────┘   └──────────────┘                   │
│  (default: 5)     (default: 4096)    (default: 0.1)                      │
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  VALIDATION & ESTIMATE                                                   │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ ✓ Feature Config: Valid transform code                            │  │
│  │ ✓ Model Config: Valid architecture                                │  │
│  │ ✓ Compatibility: Configurations are compatible                    │  │
│  │                                                                    │  │
│  │ Estimated Duration: ~8 minutes                                    │  │
│  │ Estimated Cost:     ~$1.50                                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│                                               [▶ Start Quick Test]      │
│                                                                          │
│  ════════════════════════════════════════════════════════════════════   │
│  RECENT QUICK TESTS                                                      │
│  ════════════════════════════════════════════════════════════════════   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Rich Features v2 + Standard Retrieval         ✓ Completed  2h ago │  │
│  │ Recall@100: 47.3% • Loss: 0.38 • Duration: 8m 23s                 │  │
│  │                                                    [View Results] │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Rich Features v2 + Deep Asymmetric           ✓ Completed  1d ago │  │
│  │ Recall@100: 46.1% • Loss: 0.42 • Duration: 14m 52s                │  │
│  │                                                    [View Results] │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Code Generation

### TrainerModuleGenerator Updates

The existing `TrainerModuleGenerator` in `ml_platform/modeling/services.py` needs to be extended to:

1. Accept `ModelConfig` as input alongside `FeatureConfig`
2. Generate tower architecture from `ModelConfig.buyer_tower_layers` and `product_tower_layers`
3. Use training hyperparameters from `ModelConfig`
4. Support different model types (retrieval, ranking, multitask)

### Generated Code Structure

```python
# Auto-generated TFX Trainer Module
# FeatureConfig: "{feature_config.name}" (ID: {feature_config.id})
# ModelConfig: "{model_config.name}" (ID: {model_config.id})
# Model Type: {model_config.model_type}
# Generated at: {timestamp}

import tensorflow as tf
import tensorflow_transform as tft
import tensorflow_recommenders as tfrs
from typing import Dict, Text

# ═══════════════════════════════════════════════════════════════════════════
# BUYER MODEL (Query Tower)
# Input: {buyer_tensor_dim}D tensor from FeatureConfig
# Architecture: {buyer_tower_summary} from ModelConfig
# ═══════════════════════════════════════════════════════════════════════════

class BuyerModel(tf.keras.Model):
    """Query tower for buyer/user representation."""

    def __init__(self, tf_transform_output):
        super().__init__()

        # === FEATURE EMBEDDINGS (from FeatureConfig) ===
        {feature_embedding_code}

        # === DENSE TOWER (from ModelConfig) ===
        self.dense_layers = tf.keras.Sequential([
            {buyer_tower_layers_code}
        ])

    def call(self, features):
        embeddings = []
        {embedding_collection_code}
        concatenated = tf.concat(embeddings, axis=-1)
        return self.dense_layers(concatenated)


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT MODEL (Candidate Tower)
# Input: {product_tensor_dim}D tensor from FeatureConfig
# Architecture: {product_tower_summary} from ModelConfig
# ═══════════════════════════════════════════════════════════════════════════

class ProductModel(tf.keras.Model):
    """Candidate tower for product representation."""

    def __init__(self, tf_transform_output):
        super().__init__()

        # === FEATURE EMBEDDINGS (from FeatureConfig) ===
        {product_embedding_code}

        # === DENSE TOWER (from ModelConfig) ===
        self.dense_layers = tf.keras.Sequential([
            {product_tower_layers_code}
        ])

    def call(self, features):
        embeddings = []
        {product_embedding_collection_code}
        concatenated = tf.concat(embeddings, axis=-1)
        return self.dense_layers(concatenated)


# ═══════════════════════════════════════════════════════════════════════════
# RETRIEVAL MODEL (or RANKING MODEL or MULTITASK MODEL)
# ═══════════════════════════════════════════════════════════════════════════

{model_class_code}


# ═══════════════════════════════════════════════════════════════════════════
# TFX TRAINER ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def run_fn(fn_args):
    """TFX Trainer entry point."""

    tf_transform_output = tft.TFTransformOutput(fn_args.transform_output)

    # Load datasets
    train_dataset = _input_fn(
        fn_args.train_files,
        fn_args.data_accessor,
        tf_transform_output,
        batch_size={batch_size}
    )
    eval_dataset = _input_fn(
        fn_args.eval_files,
        fn_args.data_accessor,
        tf_transform_output,
        batch_size={batch_size}
    )

    # Build models
    buyer_model = BuyerModel(tf_transform_output)
    product_model = ProductModel(tf_transform_output)

    {model_construction_code}

    # Compile
    model.compile(optimizer=tf.keras.optimizers.{optimizer}(learning_rate={learning_rate}))

    # Train
    model.fit(
        train_dataset,
        epochs={epochs},
        validation_data=eval_dataset,
    )

    # Export
    {export_code}
```

### Layer Code Generation

```python
def generate_layer_code(layer_config: dict) -> str:
    """Generate Keras layer code from layer config."""

    layer_type = layer_config.get('type')

    if layer_type == 'dense':
        units = layer_config['units']
        activation = layer_config.get('activation', 'relu')
        l2_reg = layer_config.get('l2_reg', 0.0)

        if l2_reg > 0:
            return f"tf.keras.layers.Dense({units}, activation='{activation}', kernel_regularizer=tf.keras.regularizers.l2({l2_reg}))"
        else:
            activation_str = f"'{activation}'" if activation else "None"
            return f"tf.keras.layers.Dense({units}, activation={activation_str})"

    elif layer_type == 'dropout':
        rate = layer_config.get('rate', 0.2)
        return f"tf.keras.layers.Dropout({rate})"

    elif layer_type == 'batch_norm':
        return "tf.keras.layers.BatchNormalization()"

    else:
        raise ValueError(f"Unknown layer type: {layer_type}")
```

---

## Implementation Checklist

### Phase 1: Retrieval Model (Priority)

#### Backend Tasks

- [ ] **Create ModelConfig model**
  - [ ] Add to `ml_platform/models.py`
  - [ ] Include all fields from data model section
  - [ ] Implement helper methods (`get_preset`, `validate`, etc.)
  - [ ] Create database migration

- [ ] **Update QuickTest model**
  - [ ] Add `model_config` ForeignKey
  - [ ] Add `rating_column` field
  - [ ] Add override fields (`epochs_override`, etc.)
  - [ ] Create database migration
  - [ ] Update existing code to handle optional model_config

- [ ] **Create ModelConfig API**
  - [ ] Create `ml_platform/modeling/model_config_api.py`
  - [ ] Implement CRUD endpoints
  - [ ] Implement clone endpoint
  - [ ] Implement presets endpoint
  - [ ] Add URL routing

- [ ] **Create ModelConfig Serializer**
  - [ ] Create `ModelConfigSerializer`
  - [ ] Include validation logic
  - [ ] Handle layer config JSON validation

- [ ] **Update TrainerModuleGenerator**
  - [ ] Accept ModelConfig as parameter
  - [ ] Generate tower layers from config
  - [ ] Use optimizer/learning_rate from config
  - [ ] Support asymmetric towers

- [ ] **Create combined code generation endpoint**
  - [ ] `/api/generate-trainer-code/`
  - [ ] Accept feature_config_id + model_config_id
  - [ ] Return generated code with validation

- [ ] **Update QuickTest API**
  - [ ] Require model_config_id in create
  - [ ] Generate code at test start time
  - [ ] Pass model config params to pipeline

- [ ] **Update Pipeline Builder**
  - [ ] Accept model config parameters
  - [ ] Use correct optimizer and hyperparameters

#### Frontend Tasks

- [ ] **Add Model Structure chapter to modeling page**
  - [ ] Create chapter container with header
  - [ ] Add "+ New Model" button
  - [ ] Style to match existing chapters

- [ ] **Create ModelConfig card component**
  - [ ] Display model type badge
  - [ ] Show tower summaries
  - [ ] Show training params
  - [ ] Add View/Edit/Clone/Delete buttons

- [ ] **Create ModelConfig list**
  - [ ] Fetch and display model configs
  - [ ] Add scrolling container (max-height)
  - [ ] Handle empty state

- [ ] **Build 3-step wizard modal**
  - [ ] Step 1: Basic info + model type selection
  - [ ] Step 2: Tower architecture builder
  - [ ] Step 3: Training parameters
  - [ ] Navigation between steps
  - [ ] Save/Cancel functionality

- [ ] **Implement visual tower builder (Step 2)**
  - [ ] Preset selection buttons
  - [ ] Tower columns (Buyer / Product)
  - [ ] Layer blocks with drag handles
  - [ ] Add layer dropdown
  - [ ] Layer settings modal (⚙)
  - [ ] Layer delete button (🗑)
  - [ ] "Copy from Buyer" button
  - [ ] Output embedding dimension selector
  - [ ] Share weights checkbox
  - [ ] Parameter count estimation

- [ ] **Implement layer configuration modals**
  - [ ] Dense layer modal (units, activation, L2)
  - [ ] Dropout modal (rate)
  - [ ] Batch norm modal (no config needed)

- [ ] **Update Quick Test section**
  - [ ] Add Model Config dropdown
  - [ ] Show model config summary
  - [ ] Add override inputs
  - [ ] Update validation display
  - [ ] Update start test API call

- [ ] **Create View modal for ModelConfig**
  - [ ] Read-only architecture display
  - [ ] Training params display
  - [ ] Generated code preview (optional)

### Phase 2: Ranking Model

#### Backend Tasks

- [ ] Extend TrainerModuleGenerator for ranking
  - [ ] Generate rating head layers
  - [ ] Use `tfrs.tasks.Ranking` with MSE loss
  - [ ] Add RMSE/MAE metrics

- [ ] Add ranking metrics to QuickTest
  - [ ] `rmse` field
  - [ ] `mae` field

- [ ] Validate rating_column against Dataset columns

#### Frontend Tasks

- [ ] Enable "Ranking" option in model type selector
- [ ] Add rating head builder to Step 2
- [ ] Show rating column selector in Quick Test
- [ ] Display RMSE/MAE in results

### Phase 3: Multitask Model

#### Backend Tasks

- [ ] Extend TrainerModuleGenerator for multitask
  - [ ] Generate combined model with both tasks
  - [ ] Apply loss weights from config
  - [ ] Return both retrieval and ranking metrics

#### Frontend Tasks

- [ ] Enable "Multitask" option in model type selector
- [ ] Add loss weight slider to Step 3
- [ ] Show combined metrics in results

---

## Migration Strategy

### Database Migration

```python
# ml_platform/migrations/XXXX_add_model_config.py

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ml_platform', 'previous_migration'),
    ]

    operations = [
        # Create ModelConfig table
        migrations.CreateModel(
            name='ModelConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('model_type', models.CharField(choices=[('retrieval', 'Retrieval'), ('ranking', 'Ranking'), ('multitask', 'Multitask')], default='retrieval', max_length=20)),
                ('buyer_tower_layers', models.JSONField(default=list)),
                ('product_tower_layers', models.JSONField(default=list)),
                ('rating_head_layers', models.JSONField(default=list)),
                ('output_embedding_dim', models.IntegerField(default=32)),
                ('share_tower_weights', models.BooleanField(default=False)),
                ('optimizer', models.CharField(choices=[('adagrad', 'Adagrad'), ('adam', 'Adam'), ('sgd', 'SGD')], default='adagrad', max_length=20)),
                ('learning_rate', models.FloatField(default=0.1)),
                ('batch_size', models.IntegerField(default=4096)),
                ('epochs', models.IntegerField(default=5)),
                ('retrieval_weight', models.FloatField(default=1.0)),
                ('ranking_weight', models.FloatField(default=0.0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
            options={
                'ordering': ['-updated_at'],
                'verbose_name': 'Model Configuration',
                'verbose_name_plural': 'Model Configurations',
            },
        ),

        # Add model_config to QuickTest (nullable for backwards compatibility)
        migrations.AddField(
            model_name='quicktest',
            name='model_config',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='quick_tests', to='ml_platform.modelconfig'),
        ),

        # Add rating column and overrides to QuickTest
        migrations.AddField(
            model_name='quicktest',
            name='rating_column',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='epochs_override',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='batch_size_override',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='learning_rate_override',
            field=models.FloatField(blank=True, null=True),
        ),

        # Add ranking metrics to QuickTest
        migrations.AddField(
            model_name='quicktest',
            name='rmse',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quicktest',
            name='mae',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
```

### Backwards Compatibility

For existing QuickTests without a ModelConfig:
1. `model_config` is nullable initially
2. Quick Tests created before this feature use hardcoded default architecture
3. New Quick Tests require ModelConfig selection
4. Consider creating a "Legacy Default" ModelConfig for old tests

---

## Testing Strategy

### Unit Tests

```python
# ml_platform/tests/test_model_config.py

class ModelConfigTestCase(TestCase):

    def test_create_model_config(self):
        """Test creating a basic model config."""
        config = ModelConfig.objects.create(
            name="Test Config",
            model_type="retrieval",
            buyer_tower_layers=[
                {"type": "dense", "units": 128, "activation": "relu"},
                {"type": "dense", "units": 32, "activation": "relu"},
            ],
            product_tower_layers=[
                {"type": "dense", "units": 64, "activation": "relu"},
                {"type": "dense", "units": 32, "activation": "relu"},
            ],
        )
        self.assertEqual(config.get_buyer_tower_summary(), "128→32")
        self.assertEqual(config.get_product_tower_summary(), "64→32")

    def test_preset_loading(self):
        """Test loading architecture presets."""
        preset = ModelConfig.get_preset('standard')
        self.assertEqual(len(preset['buyer_tower_layers']), 3)

    def test_validation_weight_sharing(self):
        """Test validation fails when sharing weights with different architectures."""
        config = ModelConfig(
            name="Invalid",
            share_tower_weights=True,
            buyer_tower_layers=[{"type": "dense", "units": 128}],
            product_tower_layers=[{"type": "dense", "units": 64}],
        )
        errors = config.validate()
        self.assertIn("Weight sharing requires identical tower architectures", errors)

    def test_parameter_estimation(self):
        """Test parameter count estimation."""
        config = ModelConfig.objects.create(
            name="Test",
            buyer_tower_layers=[
                {"type": "dense", "units": 128, "activation": "relu"},
                {"type": "dense", "units": 32, "activation": "relu"},
            ],
            product_tower_layers=[
                {"type": "dense", "units": 64, "activation": "relu"},
                {"type": "dense", "units": 32, "activation": "relu"},
            ],
        )
        params = config.estimate_params(buyer_input_dim=100, product_input_dim=50)
        self.assertGreater(params, 0)
```

### API Tests

```python
# ml_platform/tests/test_model_config_api.py

class ModelConfigAPITestCase(APITestCase):

    def test_list_model_configs(self):
        """Test listing all model configs."""
        response = self.client.get('/api/model-configs/')
        self.assertEqual(response.status_code, 200)

    def test_create_model_config(self):
        """Test creating a model config via API."""
        data = {
            "name": "API Test Config",
            "model_type": "retrieval",
            "buyer_tower_layers": [
                {"type": "dense", "units": 128, "activation": "relu"}
            ],
            "product_tower_layers": [
                {"type": "dense", "units": 64, "activation": "relu"}
            ],
        }
        response = self.client.post('/api/model-configs/', data, format='json')
        self.assertEqual(response.status_code, 201)

    def test_get_presets(self):
        """Test getting architecture presets."""
        response = self.client.get('/api/model-configs/presets/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('standard', response.data)
```

---

## Related Documentation

- [Phase: Modeling Domain](phase_modeling.md) - Feature engineering and Quick Test
- [TFX Code Generation](tfx_code_generation.md) - Transform and Trainer code generation
- [TensorFlow Recommenders Documentation](https://www.tensorflow.org/recommenders)
- [TFRS Basic Retrieval Tutorial](https://www.tensorflow.org/recommenders/examples/basic_retrieval)
- [TFRS Ranking Tutorial](https://www.tensorflow.org/recommenders/examples/basic_ranking)
- [TFRS Multitask Tutorial](https://www.tensorflow.org/recommenders/examples/multitask)

---

## Appendix: Reference Notebooks Summary

### Retrieval Model (`past/recommenders.ipynb`)

Key architecture patterns:
```python
# Two-tower model
user_model = tf.keras.Sequential([
    tf.keras.layers.StringLookup(vocabulary=unique_user_ids),
    tf.keras.layers.Embedding(len(unique_user_ids) + 1, embedding_dimension)
])

movie_model = tf.keras.Sequential([
    tf.keras.layers.StringLookup(vocabulary=unique_movie_titles),
    tf.keras.layers.Embedding(len(unique_movie_titles) + 1, embedding_dimension)
])

# TFRS task
task = tfrs.tasks.Retrieval(
    metrics=tfrs.metrics.FactorizedTopK(
        candidates=movies.batch(128).map(movie_model)
    )
)
```

### Ranking Model (`past/ranking_tfx.ipynb`)

Key architecture patterns:
```python
# Rating prediction model
class RankingModel(tf.keras.Model):
    def __init__(self):
        # User and movie embeddings
        self.user_embeddings = ...
        self.movie_embeddings = ...

        # Rating prediction head
        self.ratings = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation='relu'),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dense(1)
        ])

    def call(self, inputs):
        user_embedding = self.user_embeddings(user_id)
        movie_embedding = self.movie_embeddings(movie_id)
        return self.ratings(tf.concat([user_embedding, movie_embedding], axis=2))

# TFRS task
task = tfrs.tasks.Ranking(
    loss=tf.keras.losses.MeanSquaredError(),
    metrics=[tf.keras.metrics.RootMeanSquaredError()]
)
```

### Multitask Model (`past/multitask.ipynb`)

Key architecture patterns:
```python
class MovielensModel(tfrs.models.Model):
    def __init__(self, rating_weight: float, retrieval_weight: float):
        # Shared embeddings
        self.movie_model = ...
        self.user_model = ...

        # Rating prediction head
        self.rating_model = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation="relu"),
            tf.keras.layers.Dense(128, activation="relu"),
            tf.keras.layers.Dense(1),
        ])

        # Both tasks
        self.rating_task = tfrs.tasks.Ranking(...)
        self.retrieval_task = tfrs.tasks.Retrieval(...)

        # Loss weights
        self.rating_weight = rating_weight
        self.retrieval_weight = retrieval_weight

    def compute_loss(self, features, training=False):
        # Compute both losses
        rating_loss = self.rating_task(labels, predictions)
        retrieval_loss = self.retrieval_task(user_embeddings, movie_embeddings)

        # Weighted combination
        return (self.rating_weight * rating_loss
                + self.retrieval_weight * retrieval_loss)
```
