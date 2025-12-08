# Modeling: Feature Config Implementation

## Objective

Implement the Feature Config Wizard that allows users to:
1. Create named feature configurations based on a dataset
2. Assign columns to BuyerModel or ProductModel via drag-and-drop
3. Configure transformations for each feature (embeddings, normalization, bucketization, cyclical)
4. Define cross features within each model
5. Preview tensor dimensions in real-time
6. Save and version feature configurations

---

## Scope

**In Scope:**
- Feature Config CRUD (create, read, update, delete, clone)
- Wizard UI (2 steps)
- Drag-and-drop feature assignment
- Feature transformation configuration modals
- Tensor dimension preview
- Smart defaults generation
- Versioning

**Out of Scope:**
- Quick Test / model training
- TFX pipeline integration
- MLflow integration
- Vertex AI deployment

---

## Implementation Tasks

### 1. Backend: Django Models

**File:** `ml_platform/modeling/models.py`

Create `FeatureConfig` model:

```python
class FeatureConfig(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE,
                                related_name='feature_configs')

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    version = models.PositiveIntegerField(default=1)

    # Feature configurations (JSON)
    buyer_model_features = models.JSONField(default=list)
    product_model_features = models.JSONField(default=list)
    buyer_model_crosses = models.JSONField(default=list)
    product_model_crosses = models.JSONField(default=list)

    # Cached dimensions
    buyer_tensor_dim = models.PositiveIntegerField(null=True, blank=True)
    product_tensor_dim = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Create `FeatureConfigVersion` model for audit trail:

```python
class FeatureConfigVersion(models.Model):
    feature_config = models.ForeignKey(FeatureConfig, on_delete=models.CASCADE,
                                        related_name='versions')
    version = models.PositiveIntegerField()

    # Snapshot
    buyer_model_features = models.JSONField()
    product_model_features = models.JSONField()
    buyer_model_crosses = models.JSONField()
    product_model_crosses = models.JSONField()
    buyer_tensor_dim = models.PositiveIntegerField()
    product_tensor_dim = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
```

**Tasks:**
- [ ] Create `modeling` Django app
- [ ] Define `FeatureConfig` model
- [ ] Define `FeatureConfigVersion` model
- [ ] Create and run migrations
- [ ] Register models in admin

---

### 2. Backend: Services

**File:** `ml_platform/modeling/services.py`

#### SmartDefaultsService

Generates default feature configuration based on dataset column mapping and statistics.

```python
class SmartDefaultsService:
    CARDINALITY_TO_DIM = [
        (0, 50, 8),
        (50, 500, 16),
        (500, 5000, 32),
        (5000, 50000, 64),
        (50000, 500000, 96),
        (500000, float('inf'), 128),
    ]

    def generate(self, dataset) -> dict:
        """
        Returns:
        {
            'buyer_model_features': [...],
            'product_model_features': [...],
            'buyer_model_crosses': [...],
            'product_model_crosses': [...]
        }
        """
```

Logic:
- `customer_id` → BuyerModel, string_embedding
- `product_id` → ProductModel, string_embedding
- Columns starting with `customer_*` → BuyerModel
- Columns starting with `product_*` → ProductModel
- `category`, `subcategory` → ProductModel
- `transaction_date`, `revenue`, `quantity` → BuyerModel (context features)
- Embedding dim based on cardinality
- Default cyclical: quarterly + monthly + weekly for timestamps
- Default crosses: `customer_id × city`, `category × subcategory`

#### TensorDimensionCalculator

Calculates tensor dimensions for preview.

```python
class TensorDimensionCalculator:
    def calculate(self, features: list, crosses: list) -> dict:
        """
        Returns:
        {
            'total': 136,
            'breakdown': [
                {'name': 'customer_id', 'dim': 64},
                {'name': 'city', 'dim': 16},
                {'name': 'revenue_norm', 'dim': 1},
                {'name': 'revenue_bucket', 'dim': 32},
                ...
            ]
        }
        """
```

**Tasks:**
- [ ] Implement `SmartDefaultsService`
- [ ] Implement `TensorDimensionCalculator`
- [ ] Add unit tests for both services

---

### 3. Backend: API Endpoints

**File:** `ml_platform/modeling/views.py`, `ml_platform/modeling/serializers.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/feature-configs/` | List all feature configs (filterable by dataset) |
| POST | `/api/feature-configs/` | Create new feature config |
| GET | `/api/feature-configs/{id}/` | Get feature config details |
| PUT | `/api/feature-configs/{id}/` | Update feature config |
| DELETE | `/api/feature-configs/{id}/` | Delete feature config |
| POST | `/api/feature-configs/{id}/clone/` | Clone feature config |
| GET | `/api/feature-configs/{id}/versions/` | List versions |
| POST | `/api/feature-configs/smart-defaults/` | Generate smart defaults for a dataset |
| POST | `/api/feature-configs/calculate-dims/` | Calculate tensor dimensions |

#### Serializers

```python
class FeatureConfigSerializer(serializers.ModelSerializer):
    buyer_tensor_dim = serializers.IntegerField(read_only=True)
    product_tensor_dim = serializers.IntegerField(read_only=True)
    columns_in_both_models = serializers.ListField(read_only=True)

class FeatureConfigCreateSerializer(serializers.ModelSerializer):
    start_from = serializers.ChoiceField(
        choices=['blank', 'smart_defaults', 'clone'],
        write_only=True
    )
    clone_from_id = serializers.IntegerField(required=False, write_only=True)

class SmartDefaultsRequestSerializer(serializers.Serializer):
    dataset_id = serializers.IntegerField()

class CalculateDimsRequestSerializer(serializers.Serializer):
    features = serializers.ListField()
    crosses = serializers.ListField()
```

**Tasks:**
- [ ] Create serializers
- [ ] Create ViewSet for FeatureConfig
- [ ] Implement clone action
- [ ] Implement smart-defaults endpoint
- [ ] Implement calculate-dims endpoint
- [ ] Add URL routes
- [ ] Add API tests

---

### 4. Frontend: Feature Config List Page

**Route:** `/modeling/` or `/datasets/{id}/modeling/`

Display list of feature configs for a dataset:

```
┌────────────────────────────────────────────────────────────────────┐
│ Feature Configs                                   [+ New Config]   │
│ Dataset: Q4 2024 Transactions                                      │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ Rich Features v2                                        v3     │ │
│ │ BuyerModel: 136D | ProductModel: 104D                         │ │
│ │ Updated: 2 hours ago                                          │ │
│ │ [View] [Edit] [Clone] [Delete]                                │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ Minimal Baseline                                        v1     │ │
│ │ BuyerModel: 64D | ProductModel: 32D                           │ │
│ │ Updated: 3 days ago                                           │ │
│ │ [View] [Edit] [Clone] [Delete]                                │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Create list page component
- [ ] Display tensor dimensions in cards
- [ ] Implement clone functionality
- [ ] Implement delete with confirmation
- [ ] Add empty state

---

### 5. Frontend: Wizard Step 1 (Basic Info)

**Route:** `/modeling/new/` or `/modeling/{id}/edit/`

```
┌────────────────────────────────────────────────────────────────────┐
│ Create Feature Config                              Step 1 of 2     │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│ Config Name *                                                      │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │                                                                │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
│ Description                                                        │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │                                                                │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
│ Base Dataset *                                                     │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ Select dataset...                                          ▼  │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
│ Start From                                                         │
│ ○ Blank - Empty configuration                                      │
│ ● Smart Defaults - Auto-configure based on column mapping          │
│ ○ Clone Existing - Copy from another config                        │
│                                                                    │
│                                        [Cancel]  [Continue →]      │
└────────────────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Create Step 1 form component
- [ ] Dataset selector with info display
- [ ] "Start From" radio options
- [ ] Clone selector (conditional)
- [ ] Validation (name required, dataset required)
- [ ] Navigate to Step 2 with initial data

---

### 6. Frontend: Wizard Step 2 (Feature Assignment)

**Route:** `/modeling/new/features/` or `/modeling/{id}/edit/features/`

Three main areas:
1. **Available Columns** (top) - draggable cards
2. **BuyerModel / ProductModel** (middle) - drop zones side by side
3. **Tensor Preview** (bottom) - dimension breakdown

#### 6.1 Available Columns Panel

Show all columns from dataset that are not yet assigned:

```
┌─────────────────────────────────────────────────────────────────┐
│ AVAILABLE COLUMNS                        [Apply Smart Defaults] │
│ Drag columns to BuyerModel or ProductModel                      │
├─────────────────────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │
│ │ ≡ city       │ │ ≡ quantity   │ │ ≡ region     │              │
│ │   STRING     │ │   INTEGER    │ │   STRING     │              │
│ │   28 unique  │ │   1-999      │ │   5 unique   │              │
│ └──────────────┘ └──────────────┘ └──────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Create draggable column card component
- [ ] Show column type and statistics
- [ ] Filter out already-assigned columns
- [ ] Implement drag start/end handlers

#### 6.2 Model Drop Zones

Two side-by-side panels:

```
┌─────────────────────────┐    ┌─────────────────────────────────┐
│ BUYER MODEL             │    │ PRODUCT MODEL                   │
│ Drop features here      │    │ Drop features here              │
├─────────────────────────┤    ├─────────────────────────────────┤
│                         │    │                                 │
│ ┌─────────────────────┐ │    │ ┌─────────────────────────────┐ │
│ │ customer_id    ✕ ⚙️ │ │    │ │ product_id           ✕ ⚙️  │ │
│ │ Embedding: 64D      │ │    │ │ Embedding: 32D              │ │
│ └─────────────────────┘ │    │ └─────────────────────────────┘ │
│                         │    │                                 │
│ ┌─────────────────────┐ │    │ ┌─────────────────────────────┐ │
│ │ revenue        ✕ ⚙️ │ │    │ │ category             ✕ ⚙️  │ │
│ │ Norm: 1D + Buck: 32D│ │    │ │ Embedding: 16D              │ │
│ └─────────────────────┘ │    │ └─────────────────────────────┘ │
│                         │    │                                 │
│ [+ Add Cross Feature]   │    │ [+ Add Cross Feature]           │
│                         │    │                                 │
│ ┌─────────────────────┐ │    │                                 │
│ │ ✕ customer × city   │ │    │                                 │
│ │ Hash: 5000 → 16D    │ │    │                                 │
│ └─────────────────────┘ │    │                                 │
└─────────────────────────┘    └─────────────────────────────────┘
```

**Tasks:**
- [ ] Create drop zone component
- [ ] Create assigned feature card component
- [ ] Show transform summary on card
- [ ] ⚙️ button opens configuration modal
- [ ] ✕ button removes feature (returns to available)
- [ ] Show data leakage warning if column in both models
- [ ] Cross features section with add button
- [ ] Cross feature cards

#### 6.3 Tensor Preview Panel

```
┌─────────────────────────┐    ┌─────────────────────────────────┐
│ BUYER TENSOR            │    │ PRODUCT TENSOR                  │
│ Total: 136D             │    │ Total: 104D                     │
├─────────────────────────┤    ├─────────────────────────────────┤
│ customer_id    64D ████ │    │ product_id     32D ███          │
│ city           16D ██   │    │ category       16D ██           │
│ revenue_norm    1D ░    │    │ subcategory    24D ██           │
│ revenue_bucket 32D ███  │    │ product_name   32D ███          │
│ date_cyclical   6D █    │    │                                 │
│ customer×city  16D ██   │    │                                 │
└─────────────────────────┘    └─────────────────────────────────┘
```

**Tasks:**
- [ ] Create tensor preview component
- [ ] Call calculate-dims API on feature changes
- [ ] Show dimension bars (proportional width)
- [ ] Auto-refresh on any change

---

### 7. Frontend: Configuration Modals

#### 7.1 String Feature Modal

For STRING columns:

```
┌────────────────────────────────────────────────────────────────┐
│ Configure: product_name                                    ✕   │
├────────────────────────────────────────────────────────────────┤
│ Type: STRING | Unique: 43,521                                  │
│                                                                │
│ Embedding Dimension                                            │
│ [32 ▼]  Recommended: 32-64 for 43K unique                     │
│                                                                │
│ Vocabulary Settings                                            │
│ Max vocab size:    [50000 ▼]                                  │
│ OOV buckets:       [10 ▼]                                     │
│ Min frequency:     [5 ▼]                                      │
│                                                                │
│ ─────────────────────────────────────────────────────────────  │
│ Output: 32D                                                    │
│                                                                │
│                                       [Cancel]  [Apply]        │
└────────────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Create string feature modal component
- [ ] Embedding dimension dropdown
- [ ] Vocabulary settings fields
- [ ] Show recommended values based on cardinality
- [ ] Live dimension display

#### 7.2 Numeric Feature Modal

For INTEGER / FLOAT columns:

```
┌────────────────────────────────────────────────────────────────┐
│ Configure: revenue                                         ✕   │
├────────────────────────────────────────────────────────────────┤
│ Type: FLOAT | Range: 0 - 48,523                               │
│                                                                │
│ ☑ Normalize                                            +1D    │
│   Range: ( ) [0, 1]  (●) [-1, 1]                              │
│                                                                │
│ ☑ Bucketize + Embed                                   +32D    │
│   Buckets: [100 ▼]                                            │
│   Embedding dim: [32 ▼]                                       │
│                                                                │
│ ☐ Log Transform (before other transforms)                     │
│                                                                │
│ ─────────────────────────────────────────────────────────────  │
│ Output: 33D                                                    │
│                                                                │
│                                       [Cancel]  [Apply]        │
└────────────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Create numeric feature modal component
- [ ] Normalize checkbox + range radio
- [ ] Bucketize checkbox + settings
- [ ] Log transform checkbox
- [ ] Live dimension calculation

#### 7.3 Timestamp Feature Modal

For TIMESTAMP columns:

```
┌────────────────────────────────────────────────────────────────┐
│ Configure: trans_date                                      ✕   │
├────────────────────────────────────────────────────────────────┤
│ Type: TIMESTAMP                                                │
│                                                                │
│ BASIC TRANSFORMS                                               │
│ ☑ Normalize to [-1, 1]                                 +1D    │
│ ☐ Bucketize + Embed                                           │
│                                                                │
│ CYCLICAL FEATURES (stackable)                                  │
│ ☐ Annual (quarter 1-4)                                 +2D    │
│ ☑ Quarterly (month of quarter 1-3)                     +2D    │
│ ☑ Monthly (day 1-31)                                   +2D    │
│ ☑ Weekly (day 0-6)                                     +2D    │
│ ☐ Daily (hour 0-23)                                    +2D    │
│                                                                │
│ ─────────────────────────────────────────────────────────────  │
│ Output: 7D                                                     │
│                                                                │
│                                       [Cancel]  [Apply]        │
└────────────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Create timestamp feature modal component
- [ ] Normalize and bucketize options
- [ ] Cyclical feature checkboxes (stackable)
- [ ] Live dimension calculation

#### 7.4 Cross Feature Modal

```
┌────────────────────────────────────────────────────────────────┐
│ Add Cross Feature                                          ✕   │
├────────────────────────────────────────────────────────────────┤
│ Select 2-3 features from this model to cross:                  │
│                                                                │
│ ☑ customer_id                                                 │
│ ☑ city                                                        │
│ ☐ revenue_bucket                                              │
│                                                                │
│ Selected: customer_id × city                                   │
│                                                                │
│ Hash bucket size: [5000 ▼]                                    │
│ Embedding dim:    [16 ▼]                                      │
│                                                                │
│ ─────────────────────────────────────────────────────────────  │
│ Output: +16D                                                   │
│                                                                │
│                                     [Cancel]  [Add Cross]      │
└────────────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Create cross feature modal component
- [ ] Feature selection checkboxes (2-3 required)
- [ ] Hash bucket size dropdown
- [ ] Embedding dimension dropdown
- [ ] Validation (min 2, max 3 features)

---

### 8. Frontend: Save & Version

**Save Button Actions:**
1. Validate config (at least one feature in each model)
2. Calculate final tensor dimensions
3. POST/PUT to API
4. Create version snapshot
5. Navigate to list or stay on page

**Tasks:**
- [ ] Implement save handler
- [ ] Validation before save
- [ ] Version creation on save
- [ ] Success/error notifications
- [ ] Unsaved changes warning on navigation

---

## JSON Structure Reference

### buyer_model_features / product_model_features

```json
[
  {
    "column": "customer_id",
    "type": "string_embedding",
    "embedding_dim": 64,
    "vocab_settings": {
      "max_size": 100000,
      "oov_buckets": 10,
      "min_frequency": 5
    }
  },
  {
    "column": "revenue",
    "type": "numeric",
    "transforms": {
      "normalize": {"enabled": true, "range": [-1, 1]},
      "bucketize": {"enabled": true, "buckets": 100, "embedding_dim": 32},
      "log_transform": false
    }
  },
  {
    "column": "trans_date",
    "type": "timestamp",
    "transforms": {
      "normalize": {"enabled": true, "range": [-1, 1]},
      "bucketize": {"enabled": false},
      "cyclical": {
        "annual": false,
        "quarterly": true,
        "monthly": true,
        "weekly": true,
        "daily": false
      }
    }
  }
]
```

### buyer_model_crosses / product_model_crosses

```json
[
  {
    "features": ["customer_id", "city"],
    "hash_bucket_size": 5000,
    "embedding_dim": 16
  }
]
```

---

## Task Summary

| Area | Tasks |
|------|-------|
| **Backend Models** | 5 tasks |
| **Backend Services** | 3 tasks |
| **Backend API** | 7 tasks |
| **List Page** | 5 tasks |
| **Wizard Step 1** | 6 tasks |
| **Wizard Step 2** | 15 tasks |
| **Modals** | 16 tasks |
| **Save/Version** | 5 tasks |
| **Total** | ~62 tasks |

---

## Dependencies

**Requires from Datasets domain:**
- Dataset model with `selected_columns` JSON field
- Column statistics (unique count, min, max, type)
- Column mapping (customer_id, product_id, etc.)

**Provides to Training domain (future):**
- Feature Config JSON that defines all transformations
- Can be used to generate TFX `preprocessing_fn`
