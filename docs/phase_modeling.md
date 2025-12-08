
# Phase: Modeling Domain

## Document Purpose
This document provides detailed specifications for implementing the **Modeling** domain in the ML Platform. This domain defines HOW data is transformed for training and enables rapid experimentation via Quick Tests.

**Last Updated**: 2025-12-08

---

## Overview

### Purpose
The Modeling domain allows users to:
1. Configure feature preprocessing (embeddings, buckets, crosses, cyclical features)
2. Define **BuyerModel** (Query Tower) and **ProductModel** (Candidate Tower) features for TFRS two-tower models
3. Visually assign columns to either model via drag-and-drop
4. Preview tensor dimensions in real-time
5. Run Quick Tests on Vertex AI Pipelines (future scope)
6. Compare results via MLflow heatmaps (future scope)
7. Iterate until finding the best configuration

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

### Supported Transformations

| Data Type | Transform | Output | Description |
|-----------|-----------|--------|-------------|
| **STRING** | Vocabulary Embedding | `embedding_dim` D | Lookup table → learned embedding vectors |
| **INTEGER** | Normalize | 1D | Scale to [-1, 1] or [0, 1] |
| **INTEGER** | Bucketize + Embed | `embedding_dim` D | Quantile buckets → embedding |
| **FLOAT** | Normalize | 1D | Scale to [-1, 1] or [0, 1] |
| **FLOAT** | Bucketize + Embed | `embedding_dim` D | Quantile buckets → embedding |
| **FLOAT** | Log Transform | 1D | log(1 + x) for skewed distributions |
| **TIMESTAMP** | Normalize | 1D | UTC seconds scaled to [-1, 1] |
| **TIMESTAMP** | Bucketize + Embed | `embedding_dim` D | Time buckets → embedding |
| **TIMESTAMP** | Cyclical (each) | 2D per cycle | Sin/cos encoding for patterns |
| **CROSS** | Hash + Embed | `embedding_dim` D | Feature interaction via hashing |

### Cyclical Features for Timestamps

Cyclical features encode temporal patterns using sin/cos pairs, ensuring smooth transitions (e.g., hour 23 is close to hour 0):

| Cycle | Range | Use Case |
|-------|-------|----------|
| **Annual** | Quarter of year (1-4) | Seasonal patterns (Q1 promotions, holiday seasons) |
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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Feature Config: Q4 2024 - Rich Features v2                   Step 2 of 2    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ AVAILABLE COLUMNS                              [Apply Smart Defaults]   │ │
│ │ Drag columns to BuyerModel or ProductModel                              │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │                                                                          │ │
│ │ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐         │ │
│ │ │ ≡ customer_id    │ │ ≡ product_id     │ │ ≡ trans_date     │         │ │
│ │ │   STRING         │ │   INTEGER        │ │   TIMESTAMP      │         │ │
│ │ │   125K unique    │ │   45K unique     │ │                  │         │ │
│ │ └──────────────────┘ └──────────────────┘ └──────────────────┘         │ │
│ │                                                                          │ │
│ │ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐         │ │
│ │ │ ≡ city           │ │ ≡ category       │ │ ≡ subcategory    │         │ │
│ │ │   STRING         │ │   STRING         │ │   STRING         │         │ │
│ │ │   28 unique      │ │   12 unique      │ │   156 unique     │         │ │
│ │ └──────────────────┘ └──────────────────┘ └──────────────────┘         │ │
│ │                                                                          │ │
│ │ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐         │ │
│ │ │ ≡ revenue        │ │ ≡ product_name   │ │ ≡ quantity       │         │ │
│ │ │   FLOAT          │ │   STRING         │ │   INTEGER        │         │ │
│ │ │   range: 0-50K   │ │   43K unique     │ │   range: 1-999   │         │ │
│ │ └──────────────────┘ └──────────────────┘ └──────────────────┘         │ │
│ │                                                                          │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────┐    ┌─────────────────────────────────────┐ │
│ │ BUYER MODEL                 │    │ PRODUCT MODEL                       │ │
│ │ Drop features here          │    │ Drop features here                  │ │
│ ├─────────────────────────────┤    ├─────────────────────────────────────┤ │
│ │                             │    │                                     │ │
│ │ ┌─────────────────────────┐ │    │ ┌─────────────────────────────────┐ │ │
│ │ │ customer_id      ✕ ⚙️   │ │    │ │ product_id             ✕ ⚙️    │ │ │
│ │ │ Embedding: 64D          │ │    │ │ Embedding: 32D                  │ │ │
│ │ └─────────────────────────┘ │    │ └─────────────────────────────────┘ │ │
│ │                             │    │                                     │ │
│ │ ┌─────────────────────────┐ │    │ ┌─────────────────────────────────┐ │ │
│ │ │ city             ✕ ⚙️   │ │    │ │ category               ✕ ⚙️    │ │ │
│ │ │ Embedding: 16D          │ │    │ │ Embedding: 16D                  │ │ │
│ │ │ ⚠️ Also in ProductModel │ │    │ └─────────────────────────────────┘ │ │
│ │ └─────────────────────────┘ │    │                                     │ │
│ │                             │    │ ┌─────────────────────────────────┐ │ │
│ │ ┌─────────────────────────┐ │    │ │ subcategory            ✕ ⚙️    │ │ │
│ │ │ revenue          ✕ ⚙️   │ │    │ │ Embedding: 24D                  │ │ │
│ │ │ Buckets: 100 → 32D      │ │    │ └─────────────────────────────────┘ │ │
│ │ │ + Normalized: 1D        │ │    │                                     │ │
│ │ └─────────────────────────┘ │    │ ┌─────────────────────────────────┐ │ │
│ │                             │    │ │ product_name           ✕ ⚙️    │ │ │
│ │ ┌─────────────────────────┐ │    │ │ Embedding: 32D                  │ │ │
│ │ │ trans_date       ✕ ⚙️   │ │    │ └─────────────────────────────────┘ │ │
│ │ │ Normalized: 1D          │ │    │                                     │ │
│ │ │ Cyclical: quarterly,    │ │    │                                     │ │
│ │ │ monthly, weekly (6D)    │ │    │                                     │ │
│ │ └─────────────────────────┘ │    │                                     │ │
│ │                             │    │                                     │ │
│ │ [+ Add Cross Feature]       │    │ [+ Add Cross Feature]               │ │
│ │                             │    │                                     │ │
│ │ ┌─────────────────────────┐ │    │                                     │ │
│ │ │ ✕ customer_id × city    │ │    │                                     │ │
│ │ │ Hash: 5000 → 16D        │ │    │                                     │ │
│ │ └─────────────────────────┘ │    │                                     │ │
│ │                             │    │                                     │ │
│ └─────────────────────────────┘    └─────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ TENSOR PREVIEW                                                 [↻ Refresh]  │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────────────────┐    ┌─────────────────────────────────────┐ │
│ │ BUYER TENSOR                │    │ PRODUCT TENSOR                      │ │
│ │ Total: 136D                 │    │ Total: 104D                         │ │
│ ├─────────────────────────────┤    ├─────────────────────────────────────┤ │
│ │ customer_id      64D  ████  │    │ product_id       32D  ███           │ │
│ │ city             16D  ██    │    │ category         16D  ██            │ │
│ │ revenue_bucket   32D  ███   │    │ subcategory      24D  ██            │ │
│ │ revenue_norm      1D  ░     │    │ product_name     32D  ███           │ │
│ │ date_norm         1D  ░     │    │                                     │ │
│ │ cyclical          6D  █     │    │                                     │ │
│ │ customer×city    16D  ██    │    │                                     │ │
│ ├─────────────────────────────┤    ├─────────────────────────────────────┤ │
│ │ Sample (customer_12345):    │    │ Sample (product_67890):             │ │
│ │ [0.23, -0.15, 0.87, ...]   │    │ [0.45, 0.12, -0.33, ...]            │ │
│ └─────────────────────────────┘    └─────────────────────────────────────┘ │
│                                                                              │
│                                    [Cancel]  [← Back]  [Save Config]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key UI Elements:**

1. **Data Leakage Warning**: When a column is assigned to BOTH models, show `⚠️ Also in [other model]` badge
2. **Drag Handle**: `≡` icon indicates draggable columns
3. **Settings Button**: `⚙️` opens configuration modal for that feature
4. **Remove Button**: `✕` removes feature from model
5. **Live Tensor Preview**: Updates when features are added/removed/configured

### Feature Configuration Modals

#### String Feature Modal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Configure Feature: product_name                                        ✕    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Source Column: product_name                                                  │
│ Data Type: STRING                                                            │
│ Unique Values: 43,521                                                        │
│ Sample Values: "Organic Coffee Beans 500g", "Premium Olive Oil 1L", ...     │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ TRANSFORMATION                                                               │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Transform Type: Vocabulary Embedding (learned)                               │
│                                                                              │
│ Embedding Dimension                                                          │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [32 ▼]    Recommended: 32-64 for 43K unique values                     │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Vocabulary Settings                                                          │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Max vocabulary size: [50000 ▼]                                         │ │
│ │ OOV (out-of-vocab) buckets: [10 ▼]                                     │ │
│ │ Min frequency threshold: [5 ▼]                                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│ Total Feature Dimensions: 32D                                                │
│                                                                              │
│                                                    [Cancel]  [Apply]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Numeric Feature Modal (INTEGER / FLOAT)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Configure Feature: revenue                                             ✕    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Source Column: revenue                                                       │
│ Data Type: FLOAT                                                             │
│ Range: 0.00 - 48,523.00                                                      │
│ Mean: 245.67 | Median: 89.00 | Std: 512.34                                  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ TRANSFORMATION OPTIONS (select multiple)                                     │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ Normalize                                                     +1D    │ │
│ │   Range: ( ) [0, 1]  (●) [-1, 1]                                       │ │
│ │   Outputs single normalized value                                       │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ Bucketize + Embed                                                    │ │
│ │   Number of buckets: [100 ▼]  (default: 100)                           │ │
│ │   Embedding dimension: [32 ▼]                                   +32D   │ │
│ │   ⓘ Buckets created using quantiles (equal frequency)                  │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☐ Log Transform (before other transforms)                               │ │
│ │   Applies log(1 + x) for skewed distributions                          │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│ Total Feature Dimensions: 33D (1D norm + 32D bucket embedding)              │
│                                                                              │
│                                                    [Cancel]  [Apply]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Timestamp Feature Modal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Configure Feature: trans_date                                         ✕     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Source Column: trans_date                                                    │
│ Data Type: TIMESTAMP                                                         │
│ Sample Values: 2024-10-15 14:23:00, 2024-10-16 09:45:00, ...                │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ BASIC TRANSFORMS                                                             │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ Normalize to [-1, 1]                                         +1D     │ │
│ │   Converts timestamp to UTC seconds, normalizes to range                │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☐ Bucketize                                                             │ │
│ │   Number of buckets: [100 ▼]                                            │ │
│ │   Embedding dimension: [32 ▼]                                   +32D    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ CYCLICAL FEATURES (select multiple - stackable)                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☐ Annual (quarter of year 1-4)                         sin/cos  +2D    │ │
│ │   Captures yearly seasonality (Q1 promotions, holidays)                 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ Quarterly (month of quarter 1-3)                     sin/cos  +2D    │ │
│ │   Captures end-of-quarter patterns                                      │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ Monthly (day of month 1-31)                          sin/cos  +2D    │ │
│ │   Captures monthly patterns (paydays, billing cycles)                   │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ Weekly (day of week 0-6)                             sin/cos  +2D    │ │
│ │   Captures weekly patterns (weekday vs weekend)                         │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ ☐ Daily (hour of day 0-23)                             sin/cos  +2D    │ │
│ │   Captures intra-day patterns (morning, lunch, evening)                 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│ Total Feature Dimensions: 7D (1D norm + 6D cyclical)                        │
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

### Quick Test Dialog

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test: config-042                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Quick Test Settings                                                          │
│                                                                              │
│ Data sample:    [10% ▼]    (options: 5%, 10%, 25%)                          │
│ Epochs:         [2 ▼]      (options: 1, 2, 3)                               │
│ Batch size:     [4096 ▼]   (options: 2048, 4096, 8192)                      │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│                                                                              │
│ Estimated:                                                                   │
│   Duration: ~8 minutes                                                       │
│   Cost: ~$1.50                                                               │
│                                                                              │
│ What Quick Test validates:                                                   │
│   ✓ Transform compiles successfully                                         │
│   ✓ Features have valid vocabularies                                        │
│   ✓ Model trains without errors                                             │
│   ✓ Basic metrics computed (loss, recall@10/50/100)                         │
│                                                                              │
│ ⚠️ Quick Test metrics are indicative only. Run Full Training for            │
│    production-ready results.                                                 │
│                                                                              │
│                                              [Cancel]  [▶ Start Quick Test] │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test Progress

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test Running: config-042                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────┐    │
│ │ ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 45%       │    │
│ └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│ Current Stage: Transform (generating vocabularies)                           │
│                                                                              │
│ ✅ ExampleGen        - Completed (2 min)                                     │
│ ✅ StatisticsGen     - Completed (1 min)                                     │
│ ✅ SchemaGen         - Completed (10 sec)                                    │
│ 🔄 Transform         - Running... (3 min elapsed)                            │
│ ⏳ Trainer           - Pending                                               │
│                                                                              │
│ Elapsed: 6 min 10 sec                                                        │
│ Estimated remaining: ~5 min                                                  │
│                                                                              │
│                                                              [Cancel Test]   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Test Results

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Quick Test Results: config-042                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Status: ✅ Success                                                           │
│ Duration: 8 min 23 sec                                                       │
│ Cost: $1.42                                                                  │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ METRICS (indicative - 10% sample, 2 epochs)                                  │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────┬────────────┬────────────────────────────────────────┐    │
│ │ Metric         │ Value      │ vs Previous Best (config-038)          │    │
│ ├────────────────┼────────────┼────────────────────────────────────────┤    │
│ │ Loss           │ 0.38       │ ↓ 0.04 (was 0.42)                      │    │
│ │ Recall@10      │ 18.2%      │ ↑ 0.4% (was 17.8%)                     │    │
│ │ Recall@50      │ 38.5%      │ ↑ 1.2% (was 37.3%)                     │    │
│ │ Recall@100     │ 47.3%      │ ↑ 1.2% (was 46.1%)                     │    │
│ └────────────────┴────────────┴────────────────────────────────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ VOCABULARY STATS                                                             │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ┌────────────────┬────────────┬────────────┬───────────────────────────┐    │
│ │ Feature        │ Vocab Size │ OOV Rate   │ Status                    │    │
│ ├────────────────┼────────────┼────────────┼───────────────────────────┤    │
│ │ user_id        │ 9,823      │ 1.2%       │ ✅ Good                   │    │
│ │ product_id     │ 3,612      │ 0.8%       │ ✅ Good                   │    │
│ │ city           │ 28         │ 0%         │ ✅ Good                   │    │
│ │ product_name   │ 3,421      │ 2.1%       │ ✅ Good                   │    │
│ │ category       │ 12         │ 0%         │ ✅ Good                   │    │
│ │ subcategory    │ 142        │ 0.3%       │ ✅ Good                   │    │
│ └────────────────┴────────────┴────────────┴───────────────────────────┘    │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ WARNINGS                                                                     │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ (none)                                                                       │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ 🎉 This config shows improvement over previous best!                         │
│                                                                              │
│ [View in MLflow]  [Modify & Re-test]  [▶ Run Full Training]  [Close]        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MLflow Heatmap View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Experiment Heatmap: Q4 2024 Training Data                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Metric: [Recall@100 ▼]     Group by: [Embedding Dims ▼]                     │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Recall@100 by Configuration                                                  │
│                                                                              │
│                    │ user_id │ user_id │ user_id │ user_id │                │
│                    │ 32d     │ 64d     │ 64d     │ 128d    │                │
│                    │ prod 32d│ prod 32d│ prod 64d│ prod 64d│                │
│ ───────────────────┼─────────┼─────────┼─────────┼─────────┤                │
│ No crosses         │  38.2%  │  41.5%  │  44.1%  │  44.8%  │                │
│                    │  ██     │  ███    │  ████   │  ████   │                │
│ ───────────────────┼─────────┼─────────┼─────────┼─────────┤                │
│ cat × subcat       │  39.1%  │  42.8%  │  45.9%  │  46.2%  │                │
│                    │  ██     │  ███    │  █████  │  █████  │                │
│ ───────────────────┼─────────┼─────────┼─────────┼─────────┤                │
│ + user × city      │  38.5%  │  43.1%  │ ★47.3%  │  46.9%  │                │
│                    │  ██     │  ███    │  █████  │  █████  │                │
│                                                                              │
│ ★ = Best configuration                                                       │
│                                                                              │
│ Legend: █████ > 46%  ████ 44-46%  ███ 42-44%  ██ < 42%                       │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Best: config-042 (user 64d, prod 64d, cat×subcat + user×city) = 47.3%       │
│                                                                              │
│ [Export CSV]  [View Details]  [▶ Run Full Training with Best]               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

    # Status
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('tested', 'Tested'),
        ('promoted', 'Promoted'),  # Used in full training
        ('archived', 'Archived'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

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

Each feature in the array specifies a column and its transformation:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["column", "type"],
    "properties": {
      "column": {
        "type": "string",
        "description": "Column name from Dataset"
      },
      "type": {
        "enum": ["string_embedding", "numeric", "timestamp"],
        "description": "Feature type determines available transforms"
      },
      "embedding_dim": {
        "type": "integer",
        "minimum": 4,
        "maximum": 256,
        "description": "For string_embedding type"
      },
      "vocab_settings": {
        "type": "object",
        "properties": {
          "max_size": {"type": "integer", "default": 100000},
          "oov_buckets": {"type": "integer", "default": 10},
          "min_frequency": {"type": "integer", "default": 5}
        }
      },
      "transforms": {
        "type": "object",
        "description": "For numeric/timestamp types",
        "properties": {
          "normalize": {
            "type": "object",
            "properties": {
              "enabled": {"type": "boolean"},
              "range": {"enum": [[-1, 1], [0, 1]]}
            }
          },
          "bucketize": {
            "type": "object",
            "properties": {
              "enabled": {"type": "boolean"},
              "buckets": {"type": "integer", "default": 100},
              "embedding_dim": {"type": "integer", "default": 32}
            }
          },
          "log_transform": {"type": "boolean"},
          "cyclical": {
            "type": "object",
            "description": "For timestamp type only",
            "properties": {
              "annual": {"type": "boolean", "description": "Quarter of year (1-4)"},
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

**Example: buyer_model_features**

```json
[
  {
    "column": "customer_id",
    "type": "string_embedding",
    "embedding_dim": 64,
    "vocab_settings": {"max_size": 100000, "oov_buckets": 10, "min_frequency": 5}
  },
  {
    "column": "city",
    "type": "string_embedding",
    "embedding_dim": 16,
    "vocab_settings": {"max_size": 1000, "oov_buckets": 5, "min_frequency": 5}
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
        "items": {"type": "string"},
        "minItems": 2,
        "maxItems": 3,
        "description": "Column names to cross (must be in same model)"
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
    "features": ["customer_id", "city"],
    "hash_bucket_size": 5000,
    "embedding_dim": 16
  },
  {
    "features": ["revenue_bucket", "trans_date_bucket"],
    "hash_bucket_size": 3000,
    "embedding_dim": 12
  }
]
```

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

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/feature-configs/{config_id}/quick-test/` | Start quick test |
| GET | `/api/quick-tests/{test_id}/` | Get quick test status/results |
| POST | `/api/quick-tests/{test_id}/cancel/` | Cancel running quick test |
| GET | `/api/feature-configs/{config_id}/quick-tests/` | List all quick tests for a config |

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

## Quick Test Pipeline

Quick Test runs a mini TFX pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QUICK TEST PIPELINE                                  │
│                                                                              │
│   BigQuery     ExampleGen     Statistics    Schema      Transform           │
│   (10% sample) (TFRecords)    Gen          Gen         (vocabularies)       │
│       │            │             │            │             │               │
│       └────────────┴─────────────┴────────────┴─────────────┘               │
│                                        │                                     │
│                                        ↓                                     │
│                                    Trainer                                   │
│                               (2 epochs, no GPU)                             │
│                                        │                                     │
│                                        ↓                                     │
│                                   Metrics                                    │
│                              (Loss, Recall@k)                                │
│                                        │                                     │
│                                        ↓                                     │
│                                    MLflow                                    │
│                              (log experiment)                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Quick Test vs Full Training differences:**

| Aspect | Quick Test | Full Training |
|--------|------------|---------------|
| Data | 10% sample query | 100% data |
| ExampleGen | Sampled BigQuery | Full BigQuery |
| Transform | Full vocabulary | Full vocabulary |
| Trainer | CPU, 2 epochs | GPU, 10-50 epochs |
| Output | Temporary | Permanent artifacts |
| MLflow | Logged (tagged as quick test) | Logged (production) |

---

## Implementation Checklist

### Phase 1: Data Model & Backend
- [ ] Create `FeatureConfig` Django model with JSON fields
- [ ] Create `FeatureConfigVersion` model for versioning
- [ ] Create database migrations
- [ ] Implement `SmartDefaultsService` (auto-configure based on column stats)
- [ ] Implement `TensorDimensionCalculator` service
- [ ] Create CRUD API endpoints (`/api/feature-configs/`)
- [ ] Add column statistics endpoint from Dataset

### Phase 2: Wizard UI - Step 1
- [ ] Create Feature Config list page (with tensor dimension summary)
- [ ] Build Step 1 form (name, description, dataset selector)
- [ ] Implement "Start From" options (Blank / Smart Defaults / Clone)
- [ ] Connect Step 1 to backend API
- [ ] Add dataset info display (columns, rows, last updated)

### Phase 3: Wizard UI - Step 2 (Drag & Drop)
- [ ] Build Available Columns panel (draggable cards with stats)
- [ ] Build BuyerModel / ProductModel drop zones
- [ ] Implement drag & drop with Vue.js Draggable (or similar)
- [ ] Create feature card component (shows transform summary)
- [ ] Add data leakage warning badge for features in both models
- [ ] Implement "Apply Smart Defaults" button

### Phase 4: Feature Configuration Modals
- [ ] String feature modal (embedding dim, vocab settings)
- [ ] Numeric feature modal (normalize, bucketize, log transform)
- [ ] Timestamp feature modal (normalize, bucketize, cyclical options)
- [ ] Cross feature modal (feature selection, hash bucket size, embedding dim)
- [ ] Live dimension counter in each modal

### Phase 5: Tensor Preview Panel
- [ ] Build tensor preview component (side-by-side Buyer/Product)
- [ ] Implement real-time dimension calculation
- [ ] Add dimension breakdown bars (visual proportion)
- [ ] Add sample row preview (mock/computed data)
- [ ] Implement refresh button functionality

### Phase 6: TFX Integration (Future Scope)
- [ ] Implement `PreprocessingFnGenerator` service
- [ ] Generate `preprocessing_fn` code from FeatureConfig JSON
- [ ] Create Trainer module template using Transform output
- [ ] Handle cyclical feature generation in TFX Transform

### Phase 7: Quick Test Integration (Future Scope)
- [ ] Create Quick Test model and API
- [ ] Integrate with Vertex AI Pipelines trigger
- [ ] Show Quick Test progress in UI
- [ ] Display results and update best metrics
- [ ] MLflow integration for experiment tracking

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

- [Implementation Overview](../implementation.md)
- [Datasets Phase](phase_datasets.md)
- [Training Phase](phase_training.md)
- [Experiments Phase](phase_experiments.md)
