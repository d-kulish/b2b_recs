
# Phase: Configs Domain

## Document Purpose
This document provides detailed specifications for implementing the **Configs** domain in the ML Platform. This domain defines HOW data is transformed for training (Feature Configs) and the neural network architecture (Model Configs).

**Last Updated**: 2026-01-05

---

## Recent Updates (December 2025 - January 2026)

### Column Alias Validation Fix (2026-01-05)

**Bug Fix:** Fixed `_validate_column_names()` in experiments/services.py to use `display_name` when validating column names.

#### The Problem

Experiments that previously worked (14 successful runs from Dec 30 - Jan 2) started failing with:
```
FeatureConfig column names don't match BigQuery output.
Missing columns: ['division_desc', 'mge_cat_desc']
Available columns: ['category', 'city', 'cust_value', 'customer_id', 'date', 'product_id', 'sales', 'sub_category']

Suggestions:
  - 'division_desc' -> try 'category' (column was renamed in Dataset)
  - 'mge_cat_desc' -> try 'sub_category' (column was renamed in Dataset)
```

#### Timeline of Events

| Date | Event |
|------|-------|
| Dec 28, 2025 | Column renaming feature added (`fdcd6cf`) |
| Dec 29, 2025 | Display name preservation fixes (v15, v16) |
| Dec 30 - Jan 2 | 14 experiments completed successfully with `cherng_v1` FeatureConfig |
| Jan 3, 2026 | `_validate_column_names()` added to catch column mismatches (`da745c8`) |
| Jan 5, 2026 | Experiment failed - validation rejected previously-working config |

#### Root Cause Analysis

The Jan 3 validation addition (`da745c8`) introduced a regression. It checked `feature['column']` but the transform code generator uses `feature.get('display_name') or feature.get('column')`.

**FeatureConfig Data Model:**
```json
{
  "column": "division_desc",      // Original BigQuery column name
  "display_name": "category",     // Aliased name (matches BQ output)
  "type": "text",
  "transforms": { "embedding": { "enabled": true, "embedding_dim": 8 } }
}
```

**Data Flow:**
```
Dataset.column_aliases: {"products_division_desc": "category"}
                                    ↓
BigQuery SQL: SELECT division_desc AS category  →  Output column: "category"
                                    ↓
Transform code: inputs['category']  ←  Uses display_name ✅
                                    ↓
Validation: feature['column'] = "division_desc"  ←  Wrong field! ❌
```

#### Wrong Approach (Attempted & Reverted)

Initially attempted to fix by modifying `SmartDefaultsService._get_all_columns_with_info()` to apply aliases to the `name` field. This was **wrong** because:

1. The data model is correct - storing both `column` (original) and `display_name` (alias) is intentional
2. The transform code generator already handles this correctly
3. The fix would have broken existing FeatureConfigs that store original names in `column`

**Reverted changes:**
- `SmartDefaultsService._get_all_columns_with_info()` alias application
- New `_validate_column_names_against_dataset()` function
- Incorrect documentation

#### The Correct Fix

The validation should use the same pattern as the transform code generator:

**File:** `ml_platform/experiments/services.py`

```python
# Before (wrong - only checked 'column'):
for feature in (feature_config.buyer_model_features or []):
    if 'column' in feature:
        feature_columns.add(feature['column'])

# After (correct - uses display_name if present):
for feature in (feature_config.buyer_model_features or []):
    col = feature.get('display_name') or feature.get('column')
    if col:
        feature_columns.add(col)
```

#### Key Insight: Consistent Column Name Resolution

Throughout the codebase, column names should be resolved using:
```python
col = feature.get('display_name') or feature.get('column')
```

This pattern appears 30+ times in `configs/services.py` (transform/trainer code generators). The validation was the only place that didn't follow this pattern.

#### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/experiments/services.py` | Fixed `_validate_column_names()` to use `display_name or column` pattern |

#### Lessons Learned

1. **Check existing patterns** before implementing fixes - the codebase already had the correct approach
2. **Trace actual data** through the system before assuming what's broken
3. **Test with real data** - the FeatureConfig had both `column` and `display_name` fields
4. **Validation should match runtime behavior** - if transform uses `display_name`, validation must too

---

### Embedding Recommendations & OOV Info for All Features (2025-12-29)

**Feature Added:** Extended cardinality-based embedding recommendations and OOV information to all feature types (Primary IDs and Context Features).

**Changes Made:**

#### 1. Display Name (Alias) Preservation Fix

**Problem:** When columns with renamed aliases (from Dataset Config) were dragged to Context Features, the original BigQuery column names appeared instead of the user-friendly aliases.

**Root Cause:** The `createDefaultFeature()` and `dropPrimaryId()` functions were not preserving the `display_name` field from the column object.

**Fix:** Added `display_name` preservation throughout the feature creation pipeline:
- `createDefaultFeature()` - Now includes `display_name: col.display_name || col.name`
- `dropPrimaryId()` - Now includes `display_name` for primary ID features
- Cross-feature modal - Now shows aliases in selection list and preview
- `addCrossFeature()` - Now preserves `display_name` in cross feature config

#### 2. Cardinality-Based Recommendations for Context Features

**Problem:** Text features in Context Features had no guidance on embedding dimension selection, unlike Primary IDs which showed cardinality and recommendations.

**Implementation:**

**A. Feature Card Display** (`createAssignedFeatureElement()`):
After embedding is configured, shows cardinality info:
```
category
STRING → Text • Embed: 8D
📊 ~15 unique → ✓ 8D recommended     (green if matches)
```

**B. Settings Modal** (`renderFeatureConfigForm()`):
- Cardinality banner with recommendation status (green/amber)
- Visual indicator (★ and green ring) on recommended dimension button
- Auto-selects recommended dimension when first opening unconfigured feature

#### 3. OOV + Vocabulary Info for Primary IDs

**Problem:** Primary ID modals didn't show OOV (Out-of-Vocabulary) handling information, leaving users unaware of cold start handling.

**Implementation** (`renderPrimaryIdConfigForm()`):
- Added cardinality banner with recommendation (same as Context Features)
- Added vocabulary info section:
  ```
  🗄️ Vocabulary: Auto-detected from training data
  ➕ +1 OOV: New customers not in training data will use a learned "cold start" embedding
  ```
- Contextual messaging: "customers" for Customer ID, "products" for Product ID

**Files Modified:**
- `templates/ml_platform/model_configs.html`:
  - `createDefaultFeature()` - Added display_name preservation
  - `dropPrimaryId()` - Added display_name preservation
  - `createAssignedFeatureElement()` - Added cardinality info for text features
  - `renderFeatureConfigForm()` - Added cardinality banner and highlighted button for text features
  - `renderPrimaryIdConfigForm()` - Added cardinality banner, OOV info, highlighted button
  - Cross-feature modal functions - Added display_name support throughout

**Consistency Achieved:**

| Feature | Context Features | Primary IDs |
|---------|-----------------|-------------|
| Cardinality display | ✅ | ✅ |
| Recommended dimension | ✅ | ✅ |
| Highlighted button (★) | ✅ | ✅ |
| Auto-select recommended | ✅ | ✅ |
| Vocabulary info | ✅ | ✅ |
| +1 OOV info | ✅ | ✅ |

---

### Dynamic Embedding Dimensions for Primary IDs (2025-12-29)

**Feature Added:** Automatic embedding dimension assignment based on column cardinality for primary ID columns (customer_id, product_id).

**Problem Solved:**
Previously, when users dragged columns to the Customer ID or Product ID zones, the embedding dimension defaulted to 32D regardless of the column's cardinality. This was suboptimal because:
- A column with 1M+ unique values needs larger embeddings (128D+) to capture diversity
- A column with only 1K unique values wastes parameters with 128D embeddings

**Implementation:**

1. **Cardinality-Based Dimension Heuristic** (`model_configs.html`):
   ```javascript
   function getRecommendedEmbedDim(cardinality) {
       if (cardinality < 100) return 8;
       if (cardinality < 1000) return 16;
       if (cardinality < 10000) return 32;
       if (cardinality < 100000) return 64;
       if (cardinality < 1000000) return 128;
       return 256;  // 1M+ unique values
   }
   ```

2. **Auto-Apply on Drop**: When a column is dropped into the primary ID zone, the recommended embedding dimension is automatically applied based on the column's cardinality from stats.

3. **Cardinality Display**: The primary ID zone now shows:
   - Formatted cardinality (e.g., "~287K unique")
   - Recommendation status (green checkmark if using recommended, amber if custom)

4. **Backend Support** (`ml_platform/datasets/services.py`, `ml_platform/configs/api.py`):
   - Added `COUNT(DISTINCT)` for INTEGER columns in stats computation
   - Added on-the-fly cardinality computation for existing datasets with stale stats

**Files Modified:**
- `templates/ml_platform/model_configs.html` - Auto-apply logic, cardinality display, `getRecommendedEmbedDim()`, `formatCardinality()`
- `ml_platform/datasets/services.py` - Added cardinality computation for INTEGER columns
- `ml_platform/configs/api.py` - Added on-the-fly cardinality computation fallback

**Example:**
| Column | Cardinality | Old Default | New Auto |
|--------|-------------|-------------|----------|
| customer_id | ~287K | 32D | 64D |
| product_id | ~4.5K | 32D | 32D |

---

### Multitask Model Config Support (2025-12-14)

**Phase 3 Complete:** Multitask model configuration is now fully implemented.

**What is a Multitask Model?**
Multitask models combine both Retrieval and Ranking objectives in a single model. They share the same Buyer and Product towers but train with a weighted combination of both loss functions. This enables transfer learning between tasks - knowledge from abundant implicit feedback (clicks) can help predict sparse explicit feedback (ratings).

**Key Components Added:**

1. **Loss Weight Sliders** (Step 3 UI)
   - Retrieval Weight slider (0.0-1.0, blue gradient thumb)
   - Ranking Weight slider (0.0-1.0, amber gradient thumb)
   - Independent weights (not normalized to sum to 1.0)
   - Real-time validation: At least one weight must be > 0
   - Default: 1.0 / 1.0 (balanced start)

2. **Multitask Architecture Diagram** (Step 2 UI)
   - Visual representation showing both task paths
   - Displays: Towers → Embeddings → Split into Retrieval (dot-product) and Ranking (Rating Head)
   - Combined loss formula at bottom
   - Updates dynamically based on tower/weight configuration

3. **UI Behavior for Multitask**
   - Step 1: Multitask button enabled (no longer grayed out)
   - Step 2: Shows both Retrieval Algorithm AND Rating Head sections
   - Step 3: Shows both Loss Function AND Loss Weighting panels
   - Model cards: Pink "Multitask" badge + weights display

4. **State Management**
   - `mcState.retrievalWeight` and `mcState.rankingWeight` added
   - Save/Load/Edit/Clone/Reset all handle multitask weights
   - Validation prevents saving with both weights = 0

**Files Modified:**
- `templates/ml_platform/model_modeling.html` - All wizard and display updates

**Next Steps (Pending):**
- TrainerModuleGenerator for Multitask models (code generation)
- Multitask model serving signature

See [Phase: Model Structure](phase_model_structure.md) for full specifications.

### Ranking Model Config Support (2025-12-13)

**Phase 2 Complete:** Ranking model configuration is now fully implemented.

**What is a Ranking Model?**
While Retrieval models output embeddings for similarity matching (finding candidates), Ranking models predict a scalar rating. They concatenate buyer and product embeddings and pass them through a "Rating Head" (additional dense layers) to output a single rating value.

**Key Components Added:**

1. **Rating Head Builder** (Step 2 UI)
   - Visual layer builder similar to tower builders
   - Three presets: Minimal (64→1), Standard (256→64→1), Deep (512→256→64→1)
   - Final layer always Dense(1) for scalar output
   - Purple/pink color theme to distinguish from tower builders
   - **Drag-and-drop layer reordering** (output layer locked at bottom)

2. **Layer Types** (All 3 towers: Buyer, Product, Rating Head)
   - **Dense** - Fully connected layer with units, activation, L2 regularization
   - **Dropout** - Regularization layer with configurable rate
   - **BatchNormalization** - Normalizes activations (no parameters)
   - **LayerNormalization** - Normalizes across features with configurable epsilon (added 2025-12-13)

3. **Loss Function Selector** (Step 3 UI)
   - MSE (Mean Squared Error): For continuous ratings (1.0-5.0 scale)
   - Binary Crossentropy: For binary feedback (click/no-click)
   - Huber: Robust to outliers, good for noisy rating data

4. **Rating Column Selection** (QuickTest Dialog)
   - Rating column selected at test time, NOT stored in ModelConfig
   - Keeps ModelConfig dataset-independent (can be reused across datasets)
   - Only numeric columns from dataset are shown as options

5. **Compare Modal Enhancement** (2025-12-13)
   - Rating Head comparison section (purple theme) for Ranking models
   - Side-by-side layer comparison with aligned rows
   - Loss Function comparison in Training Settings
   - Mixed model comparison (Ranking vs Retrieval) shows "N/A" for non-applicable settings

**Database Changes:**
- `ModelConfig.loss_function` - CharField with choices (mse, binary_crossentropy, huber)
- `ModelConfig.rating_head_layers` - JSONField for Rating Head architecture
- `QuickTest.rating_column` - CharField for rating column name

**Migrations:**
- `0031_add_loss_function_to_modelconfig.py`
- `0032_add_rating_column_to_quicktest.py`

**API Endpoints Added:**
- `GET /api/model-configs/rating-head-presets/` - Returns preset configurations
- `GET /api/model-configs/loss-functions/` - Returns loss function options with descriptions

**UI Updates:**
- Step 1: Ranking button enabled (no longer grayed out)
- Step 2: Rating Head section appears for Ranking models
- Step 3: Loss Function dropdown with help text
- Model cards: Show all 3 models (Buyer, Product, Rating Head) + loss badge
- View modal: Rating Head section with layer visualization
- Compare modal: Rating Head comparison section for Ranking models
- QuickTest dialog: Rating column selector (only for Ranking models)

**Next Steps (Pending):**
- TrainerModuleGenerator for Ranking models (code generation)
- Ranking model serving signature

See [Phase: Model Structure](phase_model_structure.md) for full specifications.

### Code Generation Architecture Refactored (2025-12-12)

**Major Change:** Split code generation between Transform (stored) and Trainer (runtime).

**Why This Change:**
- **Transform code** only depends on FeatureConfig (feature definitions)
- **Trainer code** depends on BOTH FeatureConfig AND ModelConfig (architecture)
- Storing trainer code would become stale when ModelConfig changes

**New Architecture:**

| Code Type | Generated From | Storage | When Generated |
|-----------|----------------|---------|----------------|
| **Transform** | FeatureConfig only | `FeatureConfig.generated_transform_code` | On create/update/clone |
| **Trainer** | FeatureConfig + ModelConfig | NOT stored (runtime) | On QuickTest start or preview request |

**Key Changes:**
- `generated_trainer_code` field **removed** from FeatureConfig model
- `TrainerModuleGenerator` now **requires both** FeatureConfig and ModelConfig
- **New API endpoint**: `POST /api/modeling/generate-trainer-code/` accepts both config IDs
- **QuickTest now requires** `model_config_id` in request body
- **Code button removed** from Model Structure chapter (nothing to show without FeatureConfig)
- **ModelConfig is global** - reusable across any dataset/FeatureConfig

**Trainer Code Features:**
- Configurable tower layers from ModelConfig (Dense, Dropout, BatchNorm)
- **L1, L2, and L1+L2 (elastic net)** regularization support
- **6 optimizers**: Adagrad, Adam, SGD, RMSprop, AdamW, FTRL
- **Retrieval algorithms**: Brute Force or ScaNN
- Output embedding dimension from ModelConfig

**UI Changes:**
- QuickTest dialog now has **ModelConfig selector dropdown** (required)
- Training params pre-filled from selected ModelConfig
- Features chapter "Code" button shows transform only
- Model Structure chapter has no "Code" button

See [TFX Code Generation](tfx_code_generation.md) for full technical details.

### Model Structure Chapter - Enhanced (2025-12-11)

**New Features:**
Added complete Model Structure chapter for configuring neural network architecture independently from feature engineering. This enables flexible experimentation with different model architectures using the same feature set.

**Key Components:**
- **ModelConfig entity** - Stores tower architecture, training hyperparameters (optimizer, learning rate, batch size)
- **3-step wizard** - Basic Info → Architecture → Training
- **Visual tower builder** - Layer list with add/remove, supports Dense/Dropout/BatchNorm layers
- **5 presets** - Minimal, Standard, Deep, Asymmetric, Regularized
- **Full CRUD** - View/Edit/Clone/Delete model configs

**Step 3 Training UI (2025-12-11):**
- **Card-based layout** - Two-panel design (Optimizer + Hyperparameters) matching Step 2
- **6 optimizers** - Adagrad, Adam, SGD, RMSprop, AdamW, FTRL
- **Auto-suggest learning rate** - Selecting optimizer sets recommended LR (e.g., Adagrad → 0.1)
- **LR preset buttons** - Quick-select (0.001, 0.01, 0.05, 0.1) centered below input
- **Epochs removed** - Set per experiment/training run for flexibility

**Step 2 Enhancements (2025-12-11):**
- **Retrieval Algorithm Selection** - Brute Force (default) or ScaNN for large catalogs (10K+ products)
  - Top-K configuration (default: 100)
  - ScaNN parameters: num_leaves, leaves_to_search
- **Layer Drag-Drop Reordering** - Layers can be reordered within towers (except output layer)
- **Keras-style Model Summary** - Each tower displays Total params, Trainable params, Non-trainable params
- **Unified Layer Edit Modals** - Consistent UI with dimension button selectors (32, 64, 128, 256, 512 + custom)
- **Output Layer Alignment** - Output layers and param summaries always align between towers

**Model Types (All Implemented):**
| Phase | Type | Status |
|-------|------|--------|
| 1 | Retrieval (Two-Tower) | ✅ Implemented |
| 2 | Ranking | ✅ Implemented (2025-12-13) |
| 3 | Multitask | ✅ Implemented (2025-12-14) |

**API Endpoints:**
- `GET /api/model-configs/` - List all configs
- `POST /api/model-configs/create/` - Create new config
- `GET/PUT/DELETE /api/model-configs/{id}/` - CRUD operations
- `POST /api/model-configs/{id}/clone/` - Clone config
- `GET /api/model-configs/presets/` - Get preset configurations
- `GET /api/model-configs/rating-head-presets/` - Get Rating Head presets (Ranking models)
- `GET /api/model-configs/loss-functions/` - Get loss function options (Ranking models)

**Database Fields Added:**
- `retrieval_algorithm` - 'brute_force' (default) or 'scann'
- `top_k` - Number of candidates to retrieve (default: 100)
- `scann_num_leaves` - ScaNN partitions (default: 100)
- `scann_leaves_to_search` - Partitions to search (default: 10)
- `loss_function` - 'mse' (default), 'binary_crossentropy', or 'huber' (for Ranking models)
- `rating_head_layers` - JSONField for Rating Head architecture (Ranking models)

**Files Modified:**
- `ml_platform/models.py` - Added `ModelConfig` model with retrieval algorithm fields
- `ml_platform/modeling/api.py` - Added ModelConfig API endpoints
- `ml_platform/modeling/urls.py` - Added URL routing
- `ml_platform/admin.py` - Admin registration
- `templates/ml_platform/model_modeling.html` - UI chapter + wizard with enhanced Step 2

**See Also:** [Phase: Model Structure](phase_model_structure.md) for full specifications.

### Feature Set View Modal Enhancement (2025-12-10)

**Dataset Information Section:**
- Added Dataset Source section above tensor visualizations showing:
  - BigQuery tables (primary + secondary)
  - Join configuration (formatted as "table1.col ↔ table2.col (JOIN_TYPE)")
  - Filters summary (dates, customers, products)
  - Estimated row count badge
- Removed version number and "Created X ago by Y" timestamp from View modal
- Increased modal width from 700px to 880px for better readability

**Backend Changes:**
- Extended `serialize_feature_config()` to include `dataset_info` object
- Added helper functions for formatting dataset info:
  - `_format_joins_summary()` - formats joins as readable text
  - `_format_date_filter_summary()` - "Last 30 days" or "From 2024-01-01"
  - `_format_customer_filter_summary()` - "Top 80% customers" or "2 customer filters"
  - `_format_product_filter_summary()` - "Top 75% products" or "3 product filters"
  - `_count_selected_columns()` - counts total columns across tables
  - `get_dataset_info_for_view()` - main function building dataset info dict

### Compare Feature Sets (2025-12-10)

**New Feature:**
- Added "Compare" button (replacing "Refresh") in the Features chapter header
- Opens a side-by-side comparison modal for any two feature sets
- Supports cross-dataset comparison (different datasets can be compared)

**Compare Modal Features:**
- Two dropdown selects to choose Left and Right feature sets
- Table-based layout ensuring aligned rows for easy comparison:
  - Header row: Feature set name + dataset name
  - Source row: Tables, filters, row count (aligned horizontally)
  - Buyer Tensor row: Tensor bar + features list (aligned horizontally)
  - Product Tensor row: Tensor bar + features list (aligned horizontally)
- White background for clean appearance
- Cross features displayed in italic
- Tensor dimension bars for visual comparison

**JavaScript Functions:**
- `openCompareModal()` - Opens modal, populates dropdowns
- `closeCompareModal()` - Closes modal, resets state
- `onCompareSelectChange(side)` - Handles dropdown selection, fetches data
- `renderCompareColumn(config, side)` - Renders feature set into table cells
- `buildCompareSourceHtml(info)` - Builds compact source section HTML
- `updateCompareRowVisibility()` - Shows/hides data rows based on selection

### Clone Modal Enhancement (2025-12-10)

- Replaced browser's native `prompt()` dialog with modern modal
- Clean input field with label "New config name"
- Pre-filled with suggested name (original name + " (Copy)")
- Auto-focus and select text for immediate editing
- Buttons: Clone (green) + Cancel (red)

### Feature Set List Scrolling (2025-12-10)

- Feature configs list now shows approximately 2 cards with scroll for more
- Added `max-height: 420px` and `overflow-y: auto` to configs container
- Prevents the Features chapter from becoming too tall with many feature sets

### UI Improvements (2025-12-10)

**Feature Set Tablets:**
- Limited description display to 80 characters on card view
- Reorganized layout: version and updated info moved to dataset row
- Added View/Edit/Delete buttons to top-right corner of each card
- Tensor visualization bars now span full width
- Replaced detailed tensor breakdown tags with summary ("N features, M crosses")
- Detailed tensor breakdown moved to View modal
- Clone and Code buttons styled consistently (150px width, btn-sm)

**Code Viewer Modal:**
- Close button styled with red background (btn-neu-cancel) matching Cancel buttons elsewhere

**Base Template:**
- Fixed header/content alignment by removing extra padding-right from header

**Status Field Removal:**
- Completely removed `status` field from FeatureConfig model
- Removed from API endpoints, serializer, admin, and all UI components
- Created migration `0027_remove_feature_config_status.py`

### Quick Test Moved to Experiments Domain (2025-12-13)

**Note:** Quick Test functionality has been moved from Modeling to the **Experiments** domain.

See [Phase: Experiments](phase_experiments.md) for:
- Quick Test pipeline integration with Vertex AI
- Quick Test UI (dialog, progress, results modals)
- Quick Test API endpoints
- MLflow experiment tracking

### TFX Code Generation (2025-12-10, Updated 2025-12-12)
- **Transform code generation** - Feature Configs automatically generate TFX Transform `preprocessing_fn` code
  - Stored in `FeatureConfig.generated_transform_code` field
  - Auto-generated on create, update (if features changed), and clone
- **Trainer code generation** - Generated at **runtime** combining FeatureConfig + ModelConfig:
  - BuyerModel (Query Tower) and ProductModel (Candidate Tower) classes
  - RetrievalModel with configurable tower layers from ModelConfig
  - Support for Dense, Dropout, BatchNorm layers with L1/L2/L1+L2 regularization
  - 6 optimizers: Adagrad, Adam, SGD, RMSprop, AdamW, FTRL
  - `run_fn()` TFX entry point with configured optimizer
  - Serving signature for raw input → recommendations
- **Database storage** - Only Transform code stored; Trainer code generated at runtime
- **API endpoints** for viewing and generating code:
  - `GET /api/feature-configs/{id}/generated-code/?type=transform` - Get stored transform code
  - `POST /api/feature-configs/{id}/regenerate-code/` - Regenerate transform code only
  - `POST /api/modeling/generate-trainer-code/` - **NEW** Generate trainer code with both config IDs
- **Code Viewer UI** - "Code" button on Feature Config cards shows transform code only
  - Python syntax highlighting
  - Copy to clipboard and download functionality
  - Regenerate button
- **Code Validation** - Generated code is automatically validated:
  - `validate_python_code()` function using Python's `compile()` for syntax checking
  - Validation badges in code viewer (green "Valid" / red "Error" / yellow "Checking")
  - Error banner displays syntax error message and line number
- See [TFX Code Generation](tfx_code_generation.md) for full details

### CSRF Bug Fix (2025-12-10)
- Fixed missing CSRF token in Feature Config save/clone/delete operations
- Added `getCookie()` helper and `X-CSRFToken` header to all POST/PUT/DELETE fetch calls

### Primary ID Requirement
- **Customer ID** and **Product ID** are now **required** fields that must be assigned before adding other features
- Primary ID zones are visually distinct with key icon and "Required" badge
- Each model (BuyerModel/ProductModel) unlocks independently when its primary ID is assigned
- Removing a primary ID locks the model and clears all associated features

### Primary ID Configuration
- Any column can be used as Customer ID or Product ID (user defines based on domain knowledge)
- Primary ID columns are **automatically converted to Text type** regardless of original BigQuery type
- Default embedding dimension: 32D
- Embedding dimension options: Preset buttons (8D, 16D, 32D, 64D, 128D, 256D) + Custom input (4-1024)
- Configuration is limited to embedding dimension only (no other transforms)

### Text Feature Improvements
- **Embedding is always applied** for text features (no checkbox needed)
- **Vocabulary is auto-detected** from training data (removed manual "Max Vocab" input)
- **+1 OOV dimension** is automatically reserved for new/unknown values (handled by TensorFlow's StringLookup)
- Same dimension selector style as primary IDs: presets + custom input

### UI/UX Improvements
- Renamed "Additional Features" to **"Context Features"** for clarity
- Feature card buttons now arranged **vertically** (settings + delete)
- Delete button uses **trash bin icon** instead of X
- Improved tooltips and informational messages
- **"Required" badge** now uses transparent background (matches model container colors)
- **Data type dropdown removed** from feature card surface (only configurable via settings modal)
- **BQ type transformation display** shows original type with arrow: `STRING → Text • Embed: 32D`
- **Context Features containers** now have same gradient background styling as Primary ID zones (blue for Buyer, green for Product)
- **Unconfigured features** have light orange background instead of orange left border, turns white when transforms are applied
- **Tensor Preview** now calculates dimensions client-side in real-time (no API call needed)

### Temporal Feature Improvements
- **Cyclical Features section** no longer has a parent toggle checkbox - individual options are directly selectable
- **Added "Yearly" (month of year)** cyclical option (+2D) for annual seasonality patterns
- Cyclical options now include: Yearly, Quarterly, Monthly, Weekly, Daily

### Cross Feature Improvements
- **Feature type badges** in cross feature modal (ID, Numeric, Temporal, Text)
- **Bucketization options** for numeric/temporal features when crossing
  - Numeric and temporal features need to be discretized before crossing
  - Separate "crossing buckets" parameter (coarse granularity, e.g., 5-20 buckets)
  - This is independent from the main tensor's bucketization
- **New data structure** for cross features includes per-feature bucket configuration
- **Display shows bucket details** for crossed numeric/temporal features

---

## Overview

### Purpose
The Modeling domain allows users to:
1. Configure feature preprocessing (embeddings, buckets, crosses, cyclical features)
2. Define **BuyerModel** (Query Tower) and **ProductModel** (Candidate Tower) features for TFRS two-tower models
3. Visually assign columns to either model via drag-and-drop
4. Preview tensor dimensions in real-time
5. Generate TFX Transform code automatically
6. Iterate configurations before running experiments

**Note:** Quick Tests and experiment comparison have moved to the **Experiments** domain. See [Phase: Experiments](phase_experiments.md).

### Key Principle
**This is the experimentation sandbox.** Users can create multiple Feature Configs per Dataset, configure different feature engineering approaches, and compare results without committing to expensive full training runs.

### Terminology

| Term | Definition |
|------|------------|
| **BuyerModel** | Query Tower - represents the user/customer making a query |
| **ProductModel** | Candidate Tower - represents products/items being recommended |
| **Feature Config** | A complete specification of how columns are transformed and assigned to models |
| **Cross Feature** | A hashed combination of two or more features (e.g., customer_id × city) |
| **Cyclical Feature** | Sin/cos encoding of temporal patterns (e.g., day of week, hour of day) |

### Output
A Feature Config (JSON stored in Django) that:
- Defines which columns go to BuyerModel vs ProductModel
- Specifies transformation logic for each column (embeddings, buckets, cyclical)
- Defines cross features within each model
- Generates the TFX Transform `preprocessing_fn`
- Is used by both Quick Tests and Full Training
- Captures all feature engineering decisions for reproducibility

---

## Feature Transformation Types

### Data Type System

The UI uses a simplified 3-type system that maps from BigQuery types:

| UI Data Type | BigQuery Types | Available Transforms |
|--------------|---------------|---------------------|
| **Numeric** | INTEGER, INT64, FLOAT, FLOAT64, NUMERIC, BIGNUMERIC | Normalize, Bucketize + Embed |
| **Text** | STRING, BYTES | Embedding (vocabulary lookup) |
| **Temporal** | TIMESTAMP, DATETIME, DATE, TIME | Normalize, Cyclical, Bucketize + Embed |

### Supported Transformations

| Data Type | Transform | Output | Description |
|-----------|-----------|--------|-------------|
| **Text** | Embedding | `embedding_dim` D | Vocabulary lookup → learned embedding vectors |
| **Numeric** | Normalize | 1D | Scale to [-1, 1] range |
| **Numeric** | Bucketize + Embed | `embedding_dim` D | Quantile buckets → embedding |
| **Temporal** | Normalize | 1D | UTC seconds scaled to [-1, 1] |
| **Temporal** | Bucketize + Embed | `embedding_dim` D | Time buckets → embedding |
| **Temporal** | Cyclical (each) | 2D per cycle | Sin/cos encoding for patterns |
| **CROSS** | Hash + Embed | `embedding_dim` D | Feature interaction via hashing |

### Cyclical Features for Timestamps

Cyclical features encode temporal patterns using sin/cos pairs, ensuring smooth transitions (e.g., hour 23 is close to hour 0):

| Cycle | Range | Use Case |
|-------|-------|----------|
| **Yearly** | Month of year (1-12) | Annual seasonality (holiday seasons, summer/winter patterns) |
| **Quarterly** | Month of quarter (1-3) | End-of-quarter patterns |
| **Monthly** | Day of month (1-31) | Payday patterns, billing cycles |
| **Weekly** | Day of week (0-6) | Weekday vs weekend behavior |
| **Daily** | Hour of day (0-23) | Intra-day patterns (morning, lunch, evening) |

Each cyclical feature produces **2 dimensions** (sin + cos). Users can **stack multiple cycles** on the same timestamp column.

### TFX Compatibility

All transformations are compatible with TFX Transform component:

```python
# Vocabulary embedding (from recommenders.ipynb)
tft.compute_and_apply_vocabulary(
    inputs['customer_id'],
    num_oov_buckets=NUM_OOV_BUCKETS,
    vocab_filename='customer_id_vocab'
)

# Bucketization
tft.bucketize(inputs['revenue'], num_buckets=100)

# Normalization
tft.scale_to_z_score(inputs['amount'])
```

The Trainer then loads vocabularies from Transform artifacts to create embeddings:
```python
unique_ids = tf_transform_output.vocabulary_by_name('customer_id_vocab')
vocab_str = [b.decode() for b in unique_ids]
embedding = tf.keras.Sequential([
    tf.keras.layers.StringLookup(vocabulary=vocab_str, mask_token=None),
    tf.keras.layers.Embedding(len(vocab_str) + 1, embedding_dim)
])
```

---

## User Interface

### Feature Config List View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Modeling                                                 [+ New Config]     │
│ Dataset: Q4 2024 Training Data                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Filter: [All ▼]  Sort: [Best Recall@100 ▼]                                  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ ★ config-042: Large embeddings                            Best 47.3%  │  │
│ │ BuyerModel: 120D | ProductModel: 104D | Crosses: 2                    │  │
│ │ Quick Tests: 3 | Last: 2 hours ago | Status: Tested ✓                 │  │
│ │ [View] [Edit] [Clone] [▶ Run Quick Test] [▶ Full Training]            │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-038: With cross features                                 46.1% │  │
│ │ BuyerModel: 96D | ProductModel: 72D | Crosses: 1                      │  │
│ │ Quick Tests: 2 | Last: 1 day ago | Status: Tested ✓                   │  │
│ │ [View] [Edit] [Clone] [▶ Run Quick Test]                              │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-035: Baseline (minimal)                                  42.0% │  │
│ │ BuyerModel: 64D | ProductModel: 32D | Crosses: 0                      │  │
│ │ Quick Tests: 1 | Last: 3 days ago | Status: Tested ✓                  │  │
│ │ [View] [Clone]                                                        │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ config-044: Testing 128d embeddings                              Draft │  │
│ │ BuyerModel: 180D | ProductModel: 128D | Crosses: 3                    │  │
│ │ Quick Tests: 0 | Status: Not tested                                   │  │
│ │ [View] [Edit] [Delete]                                                │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ [Compare Selected] [View Heatmap]                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Feature Config Wizard

The wizard has **2 steps**:
1. **Basic Info**: Name, description, dataset selection, starting point
2. **Feature Assignment**: Drag-and-drop columns, configure transforms, preview tensors

#### Step 1: Basic Info

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create Feature Config                                        Step 1 of 2    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Config Name *                                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Q4 2024 - Rich Features v2                                              │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Description                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Testing larger embeddings with quarterly cyclical features              │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Base Dataset *                                                               │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Q4 2024 Transactions (v3)                                           ▼  │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│   Dataset columns: 14 | Rows: ~2.4M | Last updated: 2 hours ago            │
│                                                                              │
│ Start From                                                                   │
│ ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐     │
│ │ ○ Blank            │  │ ● Smart Defaults   │  │ ○ Clone Existing   │     │
│ │   Empty config     │  │   Auto-configure   │  │   Copy from...     │     │
│ │   (manual setup)   │  │   based on data    │  │   [Select ▼]       │     │
│ └────────────────────┘  └────────────────────┘  └────────────────────┘     │
│                                                                              │
│                                              [Cancel]  [Continue →]         │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Step 2: Feature Assignment (Drag & Drop Builder)

The Step 2 interface includes:
- **Dataset Sample tablet** (collapsible): Shows 10 sample rows with color-coded columns
- **Available Columns tablet** (collapsible): Compact column cards showing BQ type
- **Model drop zones**: BuyerModel and ProductModel with assigned features
- **Tensor Preview panel**: Real-time dimension calculation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Feature Config: Q4 2024 - Rich Features v2                   Step 2 of 2    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ▼ DATASET SAMPLE                                          [10 rows]    │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ ┌─────────────────────────────────────────────────────────────────────┐ │ │
│ │ │ customer_id │ product_id │ trans_date      │ city    │ revenue    │ │ │
│ │ │ (blue)      │ (green)    │                 │ (purple)│ (blue)     │ │ │
│ │ ├─────────────┼────────────┼─────────────────┼─────────┼────────────┤ │ │
│ │ │ C12345      │ P67890     │ 2024-10-15 14:23│ NYC     │ 245.00     │ │ │
│ │ │ C12346      │ P67891     │ 2024-10-16 09:45│ LA      │ 89.50      │ │ │
│ │ │ ...         │ ...        │ ...             │ ...     │ ...        │ │ │
│ │ └─────────────────────────────────────────────────────────────────────┘ │ │
│ │ Legend: 🔵 BuyerModel  🟢 ProductModel  🟣 Both Models                  │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ▼ AVAILABLE COLUMNS                                                     │ │
│ │ Drag columns to BuyerModel or ProductModel                              │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │                                                                          │ │
│ │ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐            │ │
│ │ │ ≡ customer_id   │ │ ≡ product_id    │ │ ≡ trans_date    │            │ │
│ │ │   STRING        │ │   INT64         │ │   TIMESTAMP     │            │ │
│ │ └─────────────────┘ └─────────────────┘ └─────────────────┘            │ │
│ │                                                                          │ │
│ │ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐            │ │
│ │ │ ≡ city          │ │ ≡ category      │ │ ≡ revenue       │            │ │
│ │ │   STRING        │ │   STRING        │ │   FLOAT64       │            │ │
│ │ └─────────────────┘ └─────────────────┘ └─────────────────┘            │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────┐    ┌─────────────────────────────────────┐ │
│ │ BUYER MODEL                 │    │ PRODUCT MODEL                       │ │
│ │ Drop features here          │    │ Drop features here                  │ │
│ ├─────────────────────────────┤    ├─────────────────────────────────────┤ │
│ │                             │    │                                     │ │
│ │ ┌─────────────────────────┐ │    │ ┌─────────────────────────────────┐ │ │
│ │ │ customer_id             │ │    │ │ product_id                      │ │ │
│ │ │ Text • Embed: 64D       │ │    │ │ Text • Embed: 32D               │ │ │
│ │ │ [Text ▼]          ⚙️ ✕  │ │    │ │ [Text ▼]                  ⚙️ ✕ │ │ │
│ │ └─────────────────────────┘ │    │ └─────────────────────────────────┘ │ │
│ │                             │    │                                     │ │
│ │ ┌─────────────────────────┐ │    │ ┌─────────────────────────────────┐ │ │
│ │ │ revenue                 │ │    │ │ category                        │ │ │
│ │ │ Numeric • Norm: 1D +    │ │    │ │ Text • No transform selected    │ │ │
│ │ │ Bucket: 32D             │ │    │ │ [Text ▼]               ⚙️🔸 ✕  │ │ │
│ │ │ [Numeric ▼]       ⚙️ ✕  │ │    │ └─────────────────────────────────┘ │ │
│ │ └─────────────────────────┘ │    │                                     │ │
│ │                             │    │                                     │ │
│ │ ┌─────────────────────────┐ │    │                                     │ │
│ │ │ trans_date              │ │    │                                     │ │
│ │ │ Temporal • Norm: 1D +   │ │    │                                     │ │
│ │ │ Cyclical: 6D            │ │    │                                     │ │
│ │ │ [Temporal ▼]      ⚙️ ✕  │ │    │                                     │ │
│ │ └─────────────────────────┘ │    │                                     │ │
│ │                             │    │                                     │ │
│ │ [+ Add Cross Feature]       │    │ [+ Add Cross Feature]               │ │
│ │                             │    │                                     │ │
│ └─────────────────────────────┘    └─────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ TENSOR PREVIEW                                                 [↻ Refresh]  │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────────────────┐    ┌─────────────────────────────────────┐ │
│ │ BUYER TENSOR                │    │ PRODUCT TENSOR                      │ │
│ │ Total: 104D                 │    │ Total: 32D                          │ │
│ ├─────────────────────────────┤    ├─────────────────────────────────────┤ │
│ │ customer_id      64D  ████  │    │ product_id       32D  ███           │ │
│ │ revenue_bucket   32D  ███   │    │                                     │ │
│ │ revenue_norm      1D  ░     │    │                                     │ │
│ │ date_norm         1D  ░     │    │                                     │ │
│ │ cyclical          6D  █     │    │                                     │ │
│ └─────────────────────────────┘    └─────────────────────────────────────┘ │
│                                                                              │
│                                    [Cancel]  [← Back]  [Save Config]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key UI Elements:**

1. **Dataset Sample Table**: 10 rows fetched from BigQuery with color-coded columns:
   - 🔵 Blue: assigned to BuyerModel
   - 🟢 Green: assigned to ProductModel
   - 🟣 Purple: assigned to both models (data leakage warning)

2. **Available Columns**: Compact cards showing column name and BQ type (e.g., `STRING`, `INT64`)

3. **Assigned Features**: Each feature card shows:
   - Column name
   - Data type + transform summary (e.g., "Numeric • Norm: 1D + Bucket: 32D")
   - Data type dropdown (`[Numeric ▼]`) to override inferred type
   - Settings button `⚙️` opens configuration modal
   - Remove button `✕`
   - Warning indicator `🔸` (pulsing) when no transforms selected

4. **No Auto-Apply Transforms**: Features are added without pre-configured transforms. User must click `⚙️` to configure. Features without transforms show "No transform selected" warning.

5. **Live Tensor Preview**: Updates when features are added/removed/configured

### Feature Configuration Modals

The feature configuration modal is a unified interface that adapts based on the selected data type. The modal includes:
1. **Data Type selector** at the top (allows overriding inferred type)
2. **Transform options** that change based on selected data type
3. **Dimension indicators** showing output dimensions for each transform

#### Unified Feature Modal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Configure: column_name                                                  ✕    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Data Type                                                                    │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [Numeric ▼]                                                             │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ Original BQ type: FLOAT64                                                    │
│                                                                              │
│ Transformations                                                              │
│ Select at least one transformation to include this feature in the model     │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☐ Normalize                                                        +1D │ │
│ │   Scale values to [-1, 1] range                                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☐ Bucketize + Embed                                               +32D │ │
│ │   Discretize into buckets with learned embedding                       │ │
│ │     Buckets: [100 ▼]    Dim: [32 ▼]                                    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                                                    [Cancel]  [Apply]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Transforms by Data Type

**Numeric:**
- Normalize (+1D): Scale to [-1, 1] range
- Bucketize + Embed (+configurable D): Quantile buckets → embedding

**Text:**
- Embedding (+configurable D): Vocabulary lookup → learned vectors
  - Dimension: 8/16/32/64/128/256 (presets) or custom 4-1024
  - Vocabulary: Auto-detected from training data (no manual limit)
  - +1 OOV: Automatically reserved for unknown values

**Temporal:**
- Normalize (+1D): Scale timestamp to [-1, 1]
- Cyclical Features (varies): Sin/cos encoding for periodic patterns (no parent toggle - select individual options directly)
  - Yearly: month of year (+2D)
  - Quarterly: month of quarter (+2D)
  - Monthly: day of month (+2D)
  - Weekly: day of week (+2D)
  - Daily: hour of day (+2D)
- Bucketize + Embed (+configurable D): Time buckets → embedding

#### Temporal Feature Modal Example

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Configure: trans_date                                                   ✕    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Data Type                                                                    │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [Temporal ▼]                                                            │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ Original BQ type: TIMESTAMP                                                  │
│                                                                              │
│ Transformations                                                              │
│ Select at least one transformation to include this feature in the model     │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ Normalize                                                        +1D │ │
│ │   Scale timestamp to [-1, 1] range                                     │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Cyclical Features                                                varies │ │
│ │   Extract periodic patterns using sin/cos encoding                      │ │
│ │     ☐ Yearly (month of year)                                       +2D │ │
│ │     ☐ Quarterly (month of quarter)                                 +2D │ │
│ │     ☑ Monthly (day of month)                                       +2D │ │
│ │     ☑ Weekly (day of week)                                         +2D │ │
│ │     ☐ Daily (hour of day)                                          +2D │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☐ Bucketize + Embed                                               +32D │ │
│ │   Discretize into time buckets with learned embedding                  │ │
│ │     Buckets: [100 ▼]    Dim: [32 ▼]                                    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                                                    [Cancel]  [Apply]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Cross Feature Modal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Add Cross Feature to BuyerModel                                        ✕    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Cross features capture interactions between columns.                         │
│ Only features already in this model can be crossed.                         │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ SELECT FEATURES TO CROSS (2-3 features)                                      │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Available in BuyerModel:                                                     │
│ ┌──────────────────────────────────────────────────────────────────────┐   │
│ │ ☑ customer_id                                                        │   │
│ │ ☑ city                                                               │   │
│ │ ☐ revenue_bucket                                                     │   │
│ │ ☐ trans_date_bucket                                                  │   │
│ └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ Selected: customer_id × city                                                 │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ CROSS FEATURE SETTINGS                                                       │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Hash Bucket Size                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [5000 ▼]   Recommended: 5000 (125K × 28 combinations → hashed)        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Embedding Dimension                                                          │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [16 ▼]     Recommended: 16 for cross features                          │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│ Total Feature Dimensions: +16D                                               │
│                                                                              │
│                                                    [Cancel]  [Add Cross]    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Note:** Quick Test UI mockups (Dialog, Progress, Results) and MLflow Heatmap views have been moved to [Phase: Experiments](phase_experiments.md).

---

## Data Model

### Django Models

```python
# ml_platform/models.py

class FeatureConfig(models.Model):
    """
    Defines how to transform features for BuyerModel and ProductModel.
    Many configs can exist per Dataset. Versioned via FeatureConfigVersion.
    """
    # Basic info
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dataset = models.ForeignKey('Dataset', on_delete=models.CASCADE,
                                related_name='feature_configs')

    # Version tracking
    version = models.PositiveIntegerField(default=1)

    # BuyerModel features (JSON) - see schema below
    buyer_model_features = models.JSONField(default=list)

    # ProductModel features (JSON) - see schema below
    product_model_features = models.JSONField(default=list)

    # Cross features for BuyerModel (JSON)
    buyer_model_crosses = models.JSONField(default=list)

    # Cross features for ProductModel (JSON)
    product_model_crosses = models.JSONField(default=list)

    # Computed tensor dimensions (cached for display)
    buyer_tensor_dim = models.PositiveIntegerField(null=True, blank=True)
    product_tensor_dim = models.PositiveIntegerField(null=True, blank=True)

    # Best metrics from quick tests
    best_recall_at_100 = models.FloatField(null=True, blank=True)
    best_recall_at_50 = models.FloatField(null=True, blank=True)
    best_recall_at_10 = models.FloatField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-best_recall_at_100', '-updated_at']

    def __str__(self):
        return f"{self.name} v{self.version} ({self.status})"

    def calculate_tensor_dims(self):
        """Calculate and cache tensor dimensions for both models."""
        self.buyer_tensor_dim = self._calc_model_dim(
            self.buyer_model_features, self.buyer_model_crosses
        )
        self.product_tensor_dim = self._calc_model_dim(
            self.product_model_features, self.product_model_crosses
        )

    def _calc_model_dim(self, features, crosses):
        """Calculate total dimension for a model."""
        total = 0
        for f in features:
            total += self._calc_feature_dim(f)
        for c in crosses:
            total += c.get('embedding_dim', 16)
        return total

    def _calc_feature_dim(self, feature):
        """Calculate dimension for a single feature."""
        dim = 0
        transforms = feature.get('transforms', {})

        # String embedding
        if feature.get('type') == 'string_embedding':
            dim += feature.get('embedding_dim', 32)

        # Numeric transforms
        if transforms.get('normalize', {}).get('enabled'):
            dim += 1
        if transforms.get('bucketize', {}).get('enabled'):
            dim += transforms['bucketize'].get('embedding_dim', 32)
        if transforms.get('log_transform'):
            pass  # Log doesn't add dimensions, just transforms

        # Cyclical features (2D each for sin/cos)
        cyclical = transforms.get('cyclical', {})
        for cycle in ['annual', 'quarterly', 'monthly', 'weekly', 'daily']:
            if cyclical.get(cycle):
                dim += 2

        return dim

    def get_config_hash(self):
        """Generate hash of configuration for duplicate detection."""
        import hashlib
        import json
        config = {
            'buyer_model_features': self.buyer_model_features,
            'product_model_features': self.product_model_features,
            'buyer_model_crosses': self.buyer_model_crosses,
            'product_model_crosses': self.product_model_crosses,
        }
        return hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()

    def get_columns_in_both_models(self):
        """Return columns that appear in both models (data leakage warning)."""
        buyer_cols = {f['column'] for f in self.buyer_model_features}
        product_cols = {f['column'] for f in self.product_model_features}
        return buyer_cols & product_cols


class FeatureConfigVersion(models.Model):
    """
    Stores historical versions of a FeatureConfig for audit trail.
    Created automatically when FeatureConfig is updated.
    """
    feature_config = models.ForeignKey(FeatureConfig, on_delete=models.CASCADE,
                                        related_name='versions')
    version = models.PositiveIntegerField()

    # Snapshot of config at this version
    buyer_model_features = models.JSONField()
    product_model_features = models.JSONField()
    buyer_model_crosses = models.JSONField()
    product_model_crosses = models.JSONField()
    buyer_tensor_dim = models.PositiveIntegerField()
    product_tensor_dim = models.PositiveIntegerField()

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)

    class Meta:
        unique_together = ['feature_config', 'version']
        ordering = ['-version']


class QuickTest(models.Model):
    """
    Tracks quick test runs for a feature config.
    """
    feature_config = models.ForeignKey(FeatureConfig, on_delete=models.CASCADE, related_name='quick_tests')

    # Test settings
    data_sample_percent = models.IntegerField(default=10)  # 5, 10, 25
    epochs = models.IntegerField(default=2)  # 1, 2, 3
    batch_size = models.IntegerField(default=4096)

    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Pipeline tracking
    vertex_pipeline_id = models.CharField(max_length=255, blank=True)
    current_stage = models.CharField(max_length=100, blank=True)

    # Results
    loss = models.FloatField(null=True, blank=True)
    recall_at_10 = models.FloatField(null=True, blank=True)
    recall_at_50 = models.FloatField(null=True, blank=True)
    recall_at_100 = models.FloatField(null=True, blank=True)

    # Vocabulary stats (JSON)
    vocabulary_stats = models.JSONField(default=dict)
    # Example:
    # {
    #   "user_id": {"vocab_size": 9823, "oov_rate": 0.012},
    #   "product_id": {"vocab_size": 3612, "oov_rate": 0.008},
    #   ...
    # }

    # Warnings (JSON list)
    warnings = models.JSONField(default=list)

    # Cost and duration
    duration_seconds = models.IntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # MLflow tracking
    mlflow_run_id = models.CharField(max_length=255, blank=True)

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
```

### JSON Schema: buyer_model_features / product_model_features

The system supports two formats for backward compatibility:

#### New Format (data_type based)

Each feature specifies a column, data type, and transforms:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["column", "data_type"],
    "properties": {
      "column": {
        "type": "string",
        "description": "Column name from Dataset"
      },
      "bq_type": {
        "type": "string",
        "description": "Original BigQuery type (STRING, INT64, FLOAT64, TIMESTAMP, etc.)"
      },
      "data_type": {
        "enum": ["numeric", "text", "temporal"],
        "description": "UI data type that determines available transforms"
      },
      "transforms": {
        "type": "object",
        "description": "Enabled transforms based on data_type",
        "properties": {
          "normalize": {
            "type": "object",
            "description": "For numeric/temporal",
            "properties": {
              "enabled": {"type": "boolean"},
              "range": {"enum": [[-1, 1], [0, 1]]}
            }
          },
          "bucketize": {
            "type": "object",
            "description": "For numeric/temporal",
            "properties": {
              "enabled": {"type": "boolean"},
              "buckets": {"type": "integer", "default": 100},
              "embedding_dim": {"type": "integer", "default": 32}
            }
          },
          "embedding": {
            "type": "object",
            "description": "For text type (always enabled, vocab auto-detected)",
            "properties": {
              "enabled": {"type": "boolean", "default": true},
              "embedding_dim": {"type": "integer", "default": 32, "minimum": 4, "maximum": 1024}
            }
          },
          "cyclical": {
            "type": "object",
            "description": "For temporal type",
            "properties": {
              "enabled": {"type": "boolean"},
              "yearly": {"type": "boolean", "description": "Month of year (1-12)"},
              "quarterly": {"type": "boolean", "description": "Month of quarter (1-3)"},
              "monthly": {"type": "boolean", "description": "Day of month (1-31)"},
              "weekly": {"type": "boolean", "description": "Day of week (0-6)"},
              "daily": {"type": "boolean", "description": "Hour of day (0-23)"}
            }
          }
        }
      }
    }
  }
}
```

**Example: buyer_model_features (new format)**

```json
[
  {
    "column": "customer_id",
    "bq_type": "STRING",
    "data_type": "text",
    "is_primary_id": true,
    "transforms": {
      "embedding": {"enabled": true, "embedding_dim": 64}
    }
  },
  {
    "column": "city",
    "bq_type": "STRING",
    "data_type": "text",
    "transforms": {
      "embedding": {"enabled": true, "embedding_dim": 16}
    }
  },
  {
    "column": "revenue",
    "bq_type": "FLOAT64",
    "data_type": "numeric",
    "transforms": {
      "normalize": {"enabled": true, "range": [-1, 1]},
      "bucketize": {"enabled": true, "buckets": 100, "embedding_dim": 32}
    }
  },
  {
    "column": "trans_date",
    "bq_type": "TIMESTAMP",
    "data_type": "temporal",
    "transforms": {
      "normalize": {"enabled": true, "range": [-1, 1]},
      "cyclical": {
        "enabled": true,
        "yearly": false,
        "quarterly": true,
        "monthly": true,
        "weekly": true,
        "daily": false
      }
    }
  }
]
```

#### Legacy Format (type based)

For backward compatibility, the system also supports the legacy format with `type` field:

```json
[
  {
    "column": "customer_id",
    "type": "string_embedding",
    "embedding_dim": 64,
    "vocab_settings": {"max_size": 100000, "oov_buckets": 10, "min_frequency": 5}
  },
  {
    "column": "revenue",
    "type": "numeric",
    "transforms": {
      "normalize": {"enabled": true, "range": [-1, 1]},
      "bucketize": {"enabled": true, "buckets": 100, "embedding_dim": 32}
    }
  },
  {
    "column": "trans_date",
    "type": "timestamp",
    "transforms": {
      "normalize": {"enabled": true, "range": [-1, 1]},
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

### JSON Schema: buyer_model_crosses / product_model_crosses

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["features", "hash_bucket_size", "embedding_dim"],
    "properties": {
      "features": {
        "type": "array",
        "minItems": 2,
        "maxItems": 3,
        "description": "Features to cross (array of feature config objects)",
        "items": {
          "type": "object",
          "required": ["column", "type"],
          "properties": {
            "column": {
              "type": "string",
              "description": "Column name"
            },
            "type": {
              "enum": ["text", "numeric", "temporal"],
              "description": "Data type of the feature"
            },
            "crossing_buckets": {
              "type": "integer",
              "minimum": 5,
              "maximum": 100,
              "description": "Number of buckets for crossing (only for numeric/temporal)"
            }
          }
        }
      },
      "hash_bucket_size": {
        "type": "integer",
        "minimum": 100,
        "maximum": 100000,
        "description": "Hash bucket size for the cross"
      },
      "embedding_dim": {
        "type": "integer",
        "minimum": 4,
        "maximum": 64,
        "default": 16,
        "description": "Embedding dimension for crossed feature"
      }
    }
  }
}
```

**Example: buyer_model_crosses**

```json
[
  {
    "features": [
      {"column": "customer_id", "type": "text"},
      {"column": "city", "type": "text"}
    ],
    "hash_bucket_size": 5000,
    "embedding_dim": 16
  },
  {
    "features": [
      {"column": "revenue", "type": "numeric", "crossing_buckets": 10},
      {"column": "trans_date", "type": "temporal", "crossing_buckets": 20}
    ],
    "hash_bucket_size": 3000,
    "embedding_dim": 12
  }
]
```

**Note:** Numeric and temporal features require `crossing_buckets` to discretize them before crossing. This is separate from the bucketization used in the main tensor - typically coarser (5-20 buckets) for effective crossing.

---

## API Endpoints

### Feature Config CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/datasets/{dataset_id}/feature-configs/` | List feature configs for a dataset |
| POST | `/api/datasets/{dataset_id}/feature-configs/` | Create new feature config |
| GET | `/api/feature-configs/{config_id}/` | Get feature config details |
| PUT | `/api/feature-configs/{config_id}/` | Update feature config |
| DELETE | `/api/feature-configs/{config_id}/` | Delete feature config |
| POST | `/api/feature-configs/{config_id}/clone/` | Clone feature config |

### Quick Test

**Note:** Quick Test API endpoints are documented in [Phase: Experiments](phase_experiments.md).

### Recommendations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/datasets/{dataset_id}/embedding-recommendations/` | Get embedding dim recommendations |
| GET | `/api/feature-configs/templates/` | Get available templates |

---

## Services

### preprocessing_fn Generator

The Feature Config generates a TFX Transform `preprocessing_fn`:

```python
# ml_platform/engineering/services.py

class PreprocessingFnGenerator:
    """
    Generates TFX Transform preprocessing_fn from FeatureConfig.
    """

    def __init__(self, feature_config: 'FeatureConfig', dataset: 'Dataset'):
        self.config = feature_config
        self.dataset = dataset

    def generate(self) -> str:
        """
        Generate the preprocessing_fn as a Python string.
        This is compiled and used by TFX Transform.
        """
        pass

    def _generate_vocabulary_calls(self) -> List[str]:
        """Generate tft.compute_and_apply_vocabulary calls."""
        pass

    def _generate_bucketization(self) -> List[str]:
        """Generate tft.bucketize calls for numeric features."""
        pass

    def _generate_crosses(self) -> List[str]:
        """Generate cross feature computation."""
        pass
```

### Example Generated preprocessing_fn

```python
# Auto-generated from FeatureConfig: config-042

import tensorflow as tf
import tensorflow_transform as tft

def preprocessing_fn(inputs):
    outputs = {}

    # ═══════════════════════════════════════════════════════════════
    # QUERY TOWER FEATURES
    # ═══════════════════════════════════════════════════════════════

    # user_id vocabulary
    outputs['user_id'] = tft.compute_and_apply_vocabulary(
        inputs['user_id'],
        top_k=100000,
        num_oov_buckets=10,
        vocab_filename='user_id_vocab'
    )

    # city vocabulary
    outputs['city'] = tft.compute_and_apply_vocabulary(
        inputs['city'],
        top_k=1000,
        num_oov_buckets=5,
        vocab_filename='city_vocab'
    )

    # ═══════════════════════════════════════════════════════════════
    # CANDIDATE TOWER FEATURES
    # ═══════════════════════════════════════════════════════════════

    # product_id vocabulary
    outputs['product_id'] = tft.compute_and_apply_vocabulary(
        inputs['product_id'],
        top_k=100000,
        num_oov_buckets=10,
        vocab_filename='product_id_vocab'
    )

    # product_name vocabulary
    outputs['product_name'] = tft.compute_and_apply_vocabulary(
        inputs['product_name'],
        top_k=100000,
        num_oov_buckets=10,
        vocab_filename='product_name_vocab'
    )

    # category vocabulary
    outputs['category'] = tft.compute_and_apply_vocabulary(
        inputs['category'],
        top_k=1000,
        num_oov_buckets=5,
        vocab_filename='category_vocab'
    )

    # subcategory vocabulary
    outputs['subcategory'] = tft.compute_and_apply_vocabulary(
        inputs['subcategory'],
        top_k=1000,
        num_oov_buckets=5,
        vocab_filename='subcategory_vocab'
    )

    # ═══════════════════════════════════════════════════════════════
    # NUMERIC FEATURES
    # ═══════════════════════════════════════════════════════════════

    # revenue bucketization
    outputs['revenue_bucket'] = tft.bucketize(
        inputs['revenue'],
        num_buckets=10
    )

    # timestamp hour extraction
    outputs['hour_of_day'] = tf.cast(
        tf.strings.to_number(
            tf.strings.substr(inputs['timestamp'], 11, 2)
        ),
        tf.int64
    )

    # ═══════════════════════════════════════════════════════════════
    # CROSS FEATURES
    # ═══════════════════════════════════════════════════════════════

    # category x subcategory cross
    outputs['category_x_subcategory'] = tf.sparse.cross_hashed(
        [inputs['category'], inputs['subcategory']],
        hash_bucket_size=1000,
        hash_key=42
    )

    # user_id x city cross
    outputs['user_id_x_city'] = tf.sparse.cross_hashed(
        [inputs['user_id'], inputs['city']],
        hash_bucket_size=5000,
        hash_key=42
    )

    return outputs
```

### Smart Defaults Service

```python
# ml_platform/modeling/services.py

class SmartDefaultsService:
    """
    Auto-configures features based on column statistics and mapping.
    """

    CARDINALITY_TO_DIM = [
        (0, 50, 8),
        (50, 500, 16),
        (500, 5000, 32),
        (5000, 50000, 64),
        (50000, 500000, 96),
        (500000, float('inf'), 128),
    ]

    def get_embedding_recommendation(self, cardinality: int) -> int:
        """Get recommended embedding dimension for a given cardinality."""
        for min_card, max_card, dim in self.CARDINALITY_TO_DIM:
            if min_card <= cardinality < max_card:
                return dim
        return 128

    def generate_smart_defaults(self, dataset: 'Dataset') -> dict:
        """
        Generate smart defaults based on dataset columns and their mapping.
        Uses column statistics to determine appropriate transforms.
        """
        buyer_features = []
        product_features = []

        for col in dataset.selected_columns:
            col_name = col['name']
            col_type = col['type']
            mapping = dataset.column_mapping.get(col_name)
            stats = col.get('statistics', {})

            # Determine target model based on column mapping
            if mapping in ['customer_id']:
                target = buyer_features
                feature = self._create_id_feature(col_name, stats, is_primary=True)
            elif mapping in ['product_id']:
                target = product_features
                feature = self._create_id_feature(col_name, stats, is_primary=True)
            elif mapping and mapping.startswith('customer_'):
                target = buyer_features
                feature = self._create_feature(col_name, col_type, stats)
            elif mapping and mapping.startswith('product_'):
                target = product_features
                feature = self._create_feature(col_name, col_type, stats)
            elif mapping in ['category', 'subcategory']:
                target = product_features
                feature = self._create_feature(col_name, col_type, stats)
            elif mapping in ['transaction_date', 'revenue', 'quantity']:
                target = buyer_features  # Context features go to query tower
                feature = self._create_feature(col_name, col_type, stats)
            else:
                continue  # Skip unmapped columns

            if feature:
                target.append(feature)

        # Add default cross features
        buyer_crosses = self._generate_default_crosses(buyer_features)
        product_crosses = self._generate_default_crosses(product_features)

        return {
            'buyer_model_features': buyer_features,
            'product_model_features': product_features,
            'buyer_model_crosses': buyer_crosses,
            'product_model_crosses': product_crosses,
        }

    def _create_id_feature(self, col_name: str, stats: dict, is_primary: bool) -> dict:
        """Create feature config for ID columns."""
        cardinality = stats.get('unique_count', 10000)
        return {
            'column': col_name,
            'type': 'string_embedding',
            'embedding_dim': self.get_embedding_recommendation(cardinality),
            'vocab_settings': {
                'max_size': min(cardinality * 2, 500000),
                'oov_buckets': 10,
                'min_frequency': 5 if is_primary else 1
            }
        }

    def _create_feature(self, col_name: str, col_type: str, stats: dict) -> dict:
        """Create feature config based on column type."""
        if col_type == 'STRING':
            cardinality = stats.get('unique_count', 1000)
            return {
                'column': col_name,
                'type': 'string_embedding',
                'embedding_dim': self.get_embedding_recommendation(cardinality),
                'vocab_settings': {
                    'max_size': min(cardinality * 2, 100000),
                    'oov_buckets': 10,
                    'min_frequency': 5
                }
            }
        elif col_type in ['INTEGER', 'FLOAT']:
            return {
                'column': col_name,
                'type': 'numeric',
                'transforms': {
                    'normalize': {'enabled': True, 'range': [-1, 1]},
                    'bucketize': {'enabled': True, 'buckets': 100, 'embedding_dim': 32},
                    'log_transform': stats.get('skewness', 0) > 2
                }
            }
        elif col_type == 'TIMESTAMP':
            return {
                'column': col_name,
                'type': 'timestamp',
                'transforms': {
                    'normalize': {'enabled': True, 'range': [-1, 1]},
                    'bucketize': {'enabled': False},
                    'cyclical': {
                        'annual': False,
                        'quarterly': True,
                        'monthly': True,
                        'weekly': True,
                        'daily': False
                    }
                }
            }
        return None

    def _generate_default_crosses(self, features: list) -> list:
        """Generate sensible default cross features."""
        crosses = []
        feature_names = [f['column'] for f in features]

        # Common cross patterns
        if 'customer_id' in feature_names and 'city' in feature_names:
            crosses.append({
                'features': ['customer_id', 'city'],
                'hash_bucket_size': 5000,
                'embedding_dim': 16
            })

        if 'category' in feature_names and 'subcategory' in feature_names:
            crosses.append({
                'features': ['category', 'subcategory'],
                'hash_bucket_size': 1000,
                'embedding_dim': 16
            })

        return crosses


class TensorDimensionCalculator:
    """
    Calculates tensor dimensions for preview display.
    """

    def calculate(self, features: list, crosses: list) -> dict:
        """
        Calculate total dimensions and breakdown by feature.
        Returns dict with 'total' and 'breakdown' keys.
        """
        breakdown = []
        total = 0

        for feature in features:
            dims = self._feature_dims(feature)
            for name, dim in dims.items():
                breakdown.append({'name': name, 'dim': dim})
                total += dim

        for cross in crosses:
            name = ' × '.join(cross['features'])
            dim = cross.get('embedding_dim', 16)
            breakdown.append({'name': name, 'dim': dim})
            total += dim

        return {'total': total, 'breakdown': breakdown}

    def _feature_dims(self, feature: dict) -> dict:
        """Get dimension breakdown for a single feature."""
        result = {}
        col = feature['column']
        transforms = feature.get('transforms', {})

        if feature.get('type') == 'string_embedding':
            result[col] = feature.get('embedding_dim', 32)
        else:
            if transforms.get('normalize', {}).get('enabled'):
                result[f'{col}_norm'] = 1
            if transforms.get('bucketize', {}).get('enabled'):
                result[f'{col}_bucket'] = transforms['bucketize'].get('embedding_dim', 32)

            cyclical = transforms.get('cyclical', {})
            cyclical_dims = sum(2 for c in ['annual', 'quarterly', 'monthly', 'weekly', 'daily']
                               if cyclical.get(c))
            if cyclical_dims > 0:
                result[f'{col}_cyclical'] = cyclical_dims

        return result
```

---

## Implementation Checklist

### Phase 1: Data Model & Backend ✅
- [x] Create `FeatureConfig` Django model with JSON fields
- [x] Create `FeatureConfigVersion` model for versioning
- [x] Create database migrations
- [x] Implement `SmartDefaultsService` (auto-configure based on column stats)
- [x] Implement `TensorDimensionCalculator` service
- [x] Create CRUD API endpoints (`/api/feature-configs/`)
- [x] Add column statistics endpoint from Dataset

### Phase 2: Wizard UI - Step 1 ✅
- [x] Create Feature Config list page (with tensor dimension summary)
- [x] Build Step 1 form (name, description, dataset selector)
- [x] Implement "Start From" options (Blank / Smart Defaults / Clone)
- [x] Connect Step 1 to backend API
- [x] Add dataset info display (columns, rows, last updated)

### Phase 3: Wizard UI - Step 2 (Drag & Drop) ✅
- [x] Build Available Columns panel (draggable cards with stats)
- [x] Build BuyerModel / ProductModel drop zones
- [x] Implement drag & drop with native HTML5 API
- [x] Create feature card component (shows transform summary)
- [x] Add data leakage warning badge for features in both models
- [x] Implement "Apply Smart Defaults" button

### Phase 4: Feature Configuration Modals ✅
- [x] String feature modal (embedding dim, vocab auto-detected)
- [x] Numeric feature modal (normalize, bucketize)
- [x] Timestamp feature modal (normalize, bucketize, cyclical options)
- [x] Cross feature modal (feature selection, hash bucket size, embedding dim, crossing buckets)
- [x] Live dimension counter in each modal

### Phase 5: Tensor Preview Panel ✅
- [x] Build tensor preview component (side-by-side Buyer/Product)
- [x] Implement real-time dimension calculation (client-side)
- [x] Add dimension breakdown bars (visual proportion)
- [ ] Add sample row preview (mock/computed data)
- [x] Implement refresh button functionality

### Phase 6: TFX Code Generation ✅
- [x] Implement `PreprocessingFnGenerator` service
- [x] Generate `preprocessing_fn` code from FeatureConfig JSON
- [x] Handle text features → `tft.compute_and_apply_vocabulary()`
- [x] Handle numeric features → `tft.scale_to_z_score()` + `tft.bucketize()`
- [x] Handle temporal features → normalize + cyclical (sin/cos) + bucketize
- [x] Handle cross features → `tft.hash_strings()` (dense output for Trainer compatibility)
- [x] Add database fields for generated code storage
- [x] Add API endpoints for viewing/regenerating code
- [x] Implement `TrainerModuleGenerator` service
- [x] Generate Trainer module code (BuyerModel, ProductModel, RetrievalModel, run_fn, serving signature)
- [x] Add "Code" button on Feature Config cards
- [x] Implement code viewer modal with tabs, syntax highlighting, copy/download
- [x] Add `validate_python_code()` function for syntax validation
- [x] Display validation badges (Valid/Error/Checking) in code viewer
- [x] Show error banner with message and line number for syntax errors

### Phase 7: Quick Test Integration ✅ (Moved to Experiments Domain)

**Note:** Quick Test has been implemented and moved to the Experiments domain.

See [Phase: Experiments](phase_experiments.md) for:
- Quick Test model and API
- Vertex AI Pipelines integration
- Quick Test UI (dialog, progress, results)
- MLflow experiment tracking (future)

---

## Dependencies on Other Domains

### Depends On
- **Datasets Domain**: Uses Dataset definition and column statistics
- **ETL Domain**: Data must exist in BigQuery

### Depended On By
- **Training Domain**: Uses Feature Config for full training
- **Experiments Domain**: Quick Test results feed into comparison

---

## Related Documentation

- [TFX Code Generation](tfx_code_generation.md) - Auto-generated Transform/Trainer code
- [Implementation Overview](../implementation.md)
- [Datasets Phase](phase_datasets.md)
- [Training Phase](phase_training.md)
- [Experiments Phase](phase_experiments.md)
