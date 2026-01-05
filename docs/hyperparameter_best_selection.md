# Hyperparameter Best Selection Analysis

**Last Updated**: 2026-01-05
**Status**: Implemented

---

## Goal

Define a reliable method to identify the **best hyperparameter values** based on historical experiment data. The system should help users understand which parameter combinations are most likely to produce optimal model performance (measured by Recall@100).

---

## Problem Statement

### Previous Implementation Issues

The old "Hyperparameter Insights" section analyzed completed experiments by:
1. Grouping experiments by each hyperparameter value
2. Calculating average Recall@100 for each group
3. Sorting by average recall (descending)
4. Displaying the top value as "best" for each parameter

**Problems identified:**

| Issue | Example | Impact |
|-------|---------|--------|
| Low sample size dominance | Batch size 1024 with 1 experiment (0.070) beats 2048 with 9 experiments (0.032) | Misleading recommendations |
| No uncertainty consideration | System treats 1 experiment same as 15 | False confidence |
| Limited parameter scope | Only 5 parameters analyzed (LR, batch, epochs, split, sample%) | Missing architecture insights |
| Outlier sensitivity | Single lucky result skews average | Unreliable rankings |

### User Requirements (2026-01-04)

The user requested tracking of 20+ parameters across 4 categories:

**1. Dataset:**
- Date filters applied
- Customer filters applied
- Product filters applied
- Row count

**2. Features:**
- Buyer tensor size & used columns with vector sizes
- Product tensor size & used columns with vector sizes
- Cross features for both towers

**3. Model Architecture:**
- Buyer/Product tower layer structure (e.g., `128→64→32`)
- Total params per tower
- L1/L2 regularization values
- Activation functions (relu, leaky_relu, etc.)

**4. Training Parameters:**
- Optimizer (adam, adagrad, sgd, etc.)
- Learning rate
- Batch size
- Output embedding dimension
- Retrieval algorithm (brute_force, scann)
- Top-K
- Epochs
- Split strategy

---

## Implemented Solution: TPE-Inspired Probability Ratio

### Algorithm Choice

After analysis of 5 options (Bayesian Averaging, LCB, Minimum Threshold, TPE, Combination Analysis), **Option 4: TPE-Inspired Probability Ratio** was selected because:

1. **Handles small samples** via Laplace smoothing
2. **Proven methodology** from Optuna/Hyperopt
3. **Robust to outliers** - uses binary good/bad classification
4. **Provides confidence indicators** naturally through sample counts

### TPE Scoring Formula

```python
# Define "good" as top 30% by Recall@100
good_threshold = percentile(all_recalls, 70)  # 70th percentile = top 30%

# For each parameter value:
n_good = count(experiments where recall >= good_threshold)
n_bad = count(experiments where recall < good_threshold)
n_total = n_good + n_bad

# Laplace smoothing (α=1, β=1)
p_good = (n_good + 1) / (n_total + 2)
p_bad = (n_bad + 1) / (n_total + 2)

# TPE Score
tpe_score = p_good / p_bad
```

**Interpretation:**
- `tpe_score > 1.0` → Parameter value associated with good outcomes
- `tpe_score < 1.0` → Parameter value associated with bad outcomes
- `tpe_score ≈ 1.0` → No clear association (or insufficient data)

### Confidence Levels

| Sample Count | Confidence | Visual |
|--------------|------------|--------|
| ≥ 5 experiments | High | Full opacity |
| 3-4 experiments | Medium | Full opacity |
| < 3 experiments | Low | Faded with • prefix |

---

## Implementation Details

### Files Created

| File | Purpose |
|------|---------|
| `ml_platform/migrations/0043_add_hyperparameter_analysis_fields.py` | Database migration adding 22 denormalized fields |
| `ml_platform/experiments/hyperparameter_analyzer.py` | TPE analysis service |
| `ml_platform/management/commands/backfill_hyperparameter_fields.py` | Backfill command for existing experiments |

### Files Modified

| File | Changes |
|------|---------|
| `ml_platform/models.py` | Added 22 denormalized fields to QuickTest (lines 1656-1804) |
| `ml_platform/experiments/services.py` | Added `_populate_denormalized_fields()` method |
| `ml_platform/experiments/api.py` | Updated `hyperparameter_analysis()` endpoint |
| `templates/ml_platform/model_experiments.html` | New CSS and JavaScript for categorized UI |

### Denormalized Fields Added to QuickTest

**From ModelConfig - Training:**
```python
optimizer = CharField(max_length=20)           # 'adam', 'adagrad', 'sgd', etc.
output_embedding_dim = IntegerField()          # 32, 64, 128
retrieval_algorithm = CharField(max_length=20) # 'brute_force', 'scann'
top_k = IntegerField()                         # 10, 50, 100
```

**From ModelConfig - Architecture:**
```python
buyer_tower_structure = CharField(max_length=100)   # '128→64→32'
product_tower_structure = CharField(max_length=100)
buyer_activation = CharField(max_length=20)         # 'relu', 'leaky_relu'
product_activation = CharField(max_length=20)
buyer_l2_category = CharField(max_length=20)        # 'none', 'light', 'medium', 'heavy'
product_l2_category = CharField(max_length=20)
buyer_total_params = IntegerField()                 # Computed estimate
product_total_params = IntegerField()
```

**From FeatureConfig:**
```python
buyer_tensor_dim = IntegerField()      # Total tensor dimensions (renamed to "Vector Size" in UI)
product_tensor_dim = IntegerField()
buyer_feature_count = IntegerField()   # Number of columns
product_feature_count = IntegerField()
buyer_cross_count = IntegerField()     # Number of cross features
product_cross_count = IntegerField()
```

**Feature Details (Added 2026-01-05):**
```python
buyer_feature_details = JSONField()    # [{"name": "customer_id", "dim": 32}, ...]
product_feature_details = JSONField()
buyer_cross_details = JSONField()      # [{"name": "customer_id × date", "dim": 16}, ...]
product_cross_details = JSONField()
```

**From Dataset:**
```python
dataset_row_count = IntegerField()
dataset_date_range_days = IntegerField()
dataset_unique_users = IntegerField()
dataset_unique_products = IntegerField()
```

### L2 Regularization Categories

| Category | Value Range |
|----------|-------------|
| `none` | 0 |
| `light` | 0.0001 - 0.001 |
| `medium` | 0.001 - 0.01 |
| `heavy` | > 0.01 |

### API Response Structure

**GET `/api/experiments/hyperparameter-analysis/`**

```json
{
  "success": true,
  "analysis": {
    "training": [
      {
        "param": "Learning Rate",
        "field": "learning_rate",
        "values": [
          {
            "value": "0.005",
            "tpe_score": 2.3,
            "avg_recall": 0.085,
            "best_recall": 0.092,
            "count": 5,
            "good_count": 4,
            "confidence": "high"
          }
        ]
      }
    ],
    "model": [...],
    "features": [...],
    "dataset": [...],
    "feature_details": {
      "buyer": [{"value": "customer_id 64D", "tpe_score": 2.1, "count": 12, ...}],
      "product": [{"value": "product_id 32D", "tpe_score": 2.0, "count": 15, ...}],
      "buyer_crosses": [],
      "product_crosses": []
    },
    "good_threshold": 0.072,
    "total_experiments": 15,
    "good_experiments": 5
  }
}
```

### UI Layout (Updated 2026-01-05)

**Model Architecture** and **Features** sections now use a 2-row layout to enable easy Buyer/Product comparison. Activation cards were removed (activation varies per layer).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HYPERPARAMETER INSIGHTS                                                      │
│ TPE-based analysis • Higher score = better association with top 30% results │
├─────────────────────────────────────────────────────────────────────────────┤
│ Experiments: 15  │  Good threshold: 7.2%  │  Good experiments: 5             │
├─────────────────────────────────────────────────────────────────────────────┤
│ ▀ TRAINING (blue border) ───────────────────────────────────────────────────│
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             │
│ │Learning Rate│ │ Batch Size  │ │  Optimizer  │ │   Epochs    │             │
│ │0.005  2.3(5)│ │4096   1.8(4)│ │adam   2.1(6)│ │50     1.9(8)│             │
│ │0.01   1.5(4)│ │2048   1.2(6)│ │adagrad  1.4 │ │25     1.2(5)│             │
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘             │
├─────────────────────────────────────────────────────────────────────────────┤
│ ▀ MODEL ARCHITECTURE (purple border) - 2-row Buyer/Product layout ──────────│
│ ┌───────────────────────┐ ┌─────────────┐ ┌─────────────┐  ← Buyer row      │
│ │ BUYER TOWER (2x wide) │ │ BUYER L2 REG│ │ BUYER PARAMS│                   │
│ │ 128→64→32       2.0(4)│ │ light  2.0  │ │ 19,424  3.0 │                   │
│ │ 256→128→64→32   0.3(3)│ │ medium 0.7  │ │ 55,200  2.0 │                   │
│ └───────────────────────┘ └─────────────┘ └─────────────┘                   │
│ ┌───────────────────────┐ ┌─────────────┐ ┌─────────────┐  ← Product row    │
│ │ PRODUCT TOWER (2x)    │ │PRODUCT L2   │ │PRODUCT PARAMS│                  │
│ │ 128→64→32       0.6(11)│ │ light  2.0  │ │ 63,488  0.3 │                   │
│ │ 256→128→64→32   0.5(1)│ │ medium 0.7  │ │             │                   │
│ └───────────────────────┘ └─────────────┘ └─────────────┘                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ ▀ FEATURES (green border) - 2-row Buyer/Product layout ─────────────────────│
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  ← Buyer summary row        │
│ │BUYER VECTOR │ │BUYER FEATURES│ │BUYER CROSSES│                            │
│ │ SIZE        │ │ (count)     │ │ (count)     │                             │
│ │ 175    1.0  │ │ 5      1.0  │ │ 0      0.4  │                             │
│ └─────────────┘ └─────────────┘ └─────────────┘                             │
│ ┌───────────────────────────────┐ ┌─────────────────────┐ ← Buyer details   │
│ │ BUYER FEATURE DETAILS         │ │ BUYER CROSS DETAILS │                   │
│ │ customer_id 64D       2.1(12) │ │ No data available   │                   │
│ │ segment 8D            1.8(10) │ │                     │                   │
│ │ date 4D               1.5(8)  │ │                     │                   │
│ └───────────────────────────────┘ └─────────────────────┘                   │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  ← Product summary row      │
│ │PRODUCT VECT.│ │PRODUCT FEATS│ │PRODUCT CROSS│                             │
│ │ SIZE        │ │ (count)     │ │ (count)     │                             │
│ │ 72     1.0  │ │ 3      0.4  │ │ 0      0.4  │                             │
│ └─────────────┘ └─────────────┘ └─────────────┘                             │
│ ┌───────────────────────────────┐ ┌─────────────────────┐ ← Product details │
│ │ PRODUCT FEATURE DETAILS       │ │ PRODUCT CROSS DET.  │                   │
│ │ product_id 32D        2.0(15) │ │ No data available   │                   │
│ │ category 8D           1.7(12) │ │                     │                   │
│ └───────────────────────────────┘ └─────────────────────┘                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ ▀ DATASET (orange border) ──────────────────────────────────────────────────│
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             │
│ │  Row Count  │ │ Date Range  │ │Unique Users │ │Unique Prods │             │
│ │500K    1.9  │ │90 days  1.7 │ │25K     1.6  │ │2K      1.5  │             │
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Legend: [2.3] = TPE Score  (5) = count  •faded = low confidence (<3)        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Deployment

### Migration Applied
```bash
python manage.py migrate ml_platform 0043_add_hyperparameter_analysis_fields
# Result: OK - 22 fields added
```

### Backfill Completed
```bash
python manage.py backfill_hyperparameter_fields
# Result: 25 experiments populated, 0 errors
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Good threshold | Top 30% | Balance between selectivity and sample size |
| Laplace smoothing | α=1, β=1 | Conservative smoothing for small samples |
| Confidence threshold | <3 = low | Matches statistical intuition |
| L2 as category | 4 buckets | Easier to analyze than continuous values |
| Exact values (no binning) | Yes | User preference - datasets <100K are useless anyway |
| Denormalize fields | Yes | Fast queries without joins for dashboard |

---

## Next Steps

### Immediate (Before Production Deploy)
1. ✅ Migration applied locally
2. ✅ Backfill completed locally
3. [ ] Deploy to Cloud Run
4. [ ] Run migration on production DB
5. [ ] Run backfill on production experiments

### Short-term Enhancements
1. **Add to Suggestions Engine** - Use TPE scores to generate smarter experiment suggestions
2. **Parameter Importance** - Rank which parameters have most impact on Recall@100
3. **Export Analysis** - Allow downloading hyperparameter analysis as CSV/JSON

### Medium-term
1. **Pairwise Interactions** - Analyze LR × batch_size, epochs × sample% combinations
2. **Time-based Trends** - Show how best parameters change as more experiments run
3. **Auto-tuning** - Suggest optimal values for new experiments based on TPE scores

### Long-term
1. **Optuna Integration** - Use actual TPE sampler for automated hyperparameter search
2. **Bayesian Optimization** - Full BO with GP surrogate for expensive evaluations
3. **Multi-objective** - Optimize for both Recall@100 and training time

---

## Files Reference

### Core Implementation
- **Analyzer**: `ml_platform/experiments/hyperparameter_analyzer.py`
- **API**: `ml_platform/experiments/api.py` (function `hyperparameter_analysis`)
- **Model fields**: `ml_platform/models.py` (QuickTest class, lines 1656-1804)
- **Field population**: `ml_platform/experiments/services.py` (function `_populate_denormalized_fields`)

### UI
- **Template**: `templates/ml_platform/model_experiments.html`
- **CSS**: Lines 2986-3137 (`.hyperparam-*` classes)
- **JavaScript**: Function `loadHyperparameterAnalysis()` around line 9475

### Management Commands
- **Backfill**: `ml_platform/management/commands/backfill_hyperparameter_fields.py`

---

## References

- [TPE - Tree-structured Parzen Estimator](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html)
- [Laplace Smoothing](https://en.wikipedia.org/wiki/Additive_smoothing)
- [Multi-armed Bandit / UCB](https://en.wikipedia.org/wiki/Multi-armed_bandit)
