# Hybrid Model Dashboard Implementation

This document details the changes implemented to support hybrid (multitask) experiments in the Model Experiments dashboard.

## Overview

Hybrid models combine retrieval and ranking in a single TFRS multitask model. They have:
- **Retrieval metrics**: R@5, R@10, R@50, R@100 (higher is better)
- **Ranking metrics**: RMSE, Test RMSE, MAE, Test MAE (lower is better)
- **Primary metric for sorting/display**: R@100 (Option A approach)

## Model Type Detection

The source of truth for model type is `ModelConfig.model_type`:
- `'retrieval'` - Pure retrieval model
- `'ranking'` - Pure ranking model
- `'multitask'` - Hybrid model (combines retrieval + ranking)

**Important**: `FeatureConfig.config_type` only has `'retrieval'` or `'ranking'` (derived from target_column presence). A ranking FeatureConfig can be used with BOTH ranking ModelConfig AND multitask ModelConfig.

### Filtering Pattern

All API endpoints use this pattern:

```python
if model_type == 'ranking':
    queryset = queryset.filter(
        feature_config__config_type='ranking'
    ).exclude(model_config__model_type='multitask')
elif model_type == 'hybrid':
    queryset = queryset.filter(model_config__model_type='multitask')
else:  # retrieval
    queryset = queryset.filter(
        Q(feature_config__config_type='retrieval') |
        Q(feature_config__config_type__isnull=True) |
        Q(feature_config__config_type='')
    ).exclude(model_config__model_type='multitask')
```

## Backend Changes

### 1. API Endpoints (`ml_platform/experiments/api.py`)

#### `_get_experiment_metrics()` (line ~43)
- Added hybrid branch to collect both retrieval and ranking metrics

#### `experiment_dashboard_stats()` (line ~2227)
- Added hybrid filtering using `model_config__model_type='multitask'`

#### `quick_test_list()` (line ~360)
- Added hybrid filtering

#### `metrics_trend()` (line ~2700+)
- Added hybrid chart data with dual metrics

#### `top_configurations()` (line ~3026)
- Added hybrid branch that:
  - Collects both R@100, R@50, R@10 and Test RMSE, Test MAE
  - Sorts by R@100 descending (higher is better)
  - Returns fields: `recall_at_100`, `recall_at_50`, `recall_at_10`, `test_rmse`, `test_mae`

#### `training_heatmaps()` (line ~2083)
- Added hybrid metric collection (all 8 metrics)
- Uses R@100 as sort key (descending)
- Final metrics dict includes both retrieval (as %) and ranking (as decimals)

#### `dataset_comparison()` (line ~3461)
- Added hybrid metric collection
- Stats include: `best_recall`, `avg_recall`, `best_rmse`, `avg_rmse`
- Sorted by `best_recall` descending

#### `hyperparameter_analysis()` (line ~2928)
- Added hybrid filtering
- Passes `model_type='hybrid'` to analyzer

### 2. Hyperparameter Analyzer (`ml_platform/experiments/hyperparameter_analyzer.py`)

#### Model Architecture Getters

Added fallback getters that extract data from `ModelConfig` when `QuickTest` fields are NULL (common for hybrid experiments):

| Field | Getter | Source |
|-------|--------|--------|
| `buyer_tower_structure` | `_get_buyer_tower_structure()` | `model_config.buyer_tower_layers` |
| `product_tower_structure` | `_get_product_tower_structure()` | `model_config.product_tower_layers` |
| `buyer_activation` | `_get_buyer_activation()` | First activation in buyer_tower_layers |
| `product_activation` | `_get_product_activation()` | First activation in product_tower_layers |
| `buyer_l2_category` | `_get_buyer_l2_category()` | Max l2_reg from buyer_tower_layers |
| `product_l2_category` | `_get_product_l2_category()` | Max l2_reg from product_tower_layers |
| `buyer_total_params` | `_get_buyer_total_params()` | Computed from layers + feature_config.buyer_tensor_dim |
| `product_total_params` | `_get_product_total_params()` | Computed from layers + feature_config.product_tensor_dim |

#### Ranking Tower Fields for Hybrid

Updated `ranking_only` check to include hybrid:

```python
# Skip ranking_only fields when not analyzing ranking or hybrid models
if param_def.get('ranking_only') and model_type not in ('ranking', 'hybrid'):
    continue
```

This ensures Ranking Tower and Ranking Params are displayed for hybrid experiments.

## Frontend Changes (`templates/ml_platform/model_experiments.html`)

### 1. Metrics Trend Chart (line ~10922)
- Added hybrid chart with dual Y-axis (Recall left, RMSE right)
- Both metrics shown as area charts

### 2. Top Configurations (line ~11069)

#### Header
```javascript
thead.innerHTML = `
    <tr>
        <th>#</th>
        <th>Experiment</th>
        <th>Dataset</th>
        <th>Feature</th>
        <th>Model</th>
        <th>LR</th>
        <th>R@100</th>
        <th>R@50</th>
        <th>Test RMSE</th>
        <th>Test MAE</th>
    </tr>
`;
```

#### Rendering
- Uses `recall_at_100` (not `recall_100`) to match backend field names
- Highlights best R@100 with `metric-best` class

### 3. Training Heatmaps (line ~10434)

#### Section Header
- Subtitle: "Top 10 experiments by R@100 (highest)"
- Metrics title: "Final Metrics (Retrieval + Ranking)"

#### Final Metrics Heatmap
- Displays all 8 metrics: R@5, R@10, R@50, R@100, RMSE, Test RMSE, MAE, Test MAE
- Per-metric color direction:
  - Retrieval metrics (R@*): Red (low) → Green (high)
  - Ranking metrics (RMSE/MAE): Green (low) → Red (high)
- Smaller font (7px) and narrower cells (50px) to fit 8 columns

### 4. Dataset Performance (line ~11723)

#### Header (6 columns for hybrid)
```javascript
thead.innerHTML = `
    <tr>
        <th>Dataset</th>
        <th>Experiments</th>
        <th>Best R@100</th>
        <th>Avg R@100</th>
        <th>Best RMSE</th>
        <th>Avg RMSE</th>
    </tr>
`;
```

### 5. Hyperparameter Insights (line ~11293)

- Removed "coming soon" placeholder
- Updated subtitle: "TPE-based analysis • Higher score = better association with top 30% results (by R@100)"
- Uses R@100 as primary metric (same as retrieval)

## Testing

To verify hybrid experiments are working:

1. **Dashboard KPIs**: Hybrid column should show experiment count and metrics
2. **Metrics Trend**: Should show chart if 2+ experiments exist
3. **Top Configurations**: Should show both R@100/R@50 and Test RMSE/MAE
4. **Training Heatmaps**: Should show all 8 metrics in final metrics heatmap
5. **Dataset Performance**: Should show best/avg for both recall and RMSE
6. **Hyperparameter Insights**: Should show Model Architecture with all tower info including Ranking Tower

## Files Modified

- `ml_platform/experiments/api.py` - 7 API endpoint updates
- `ml_platform/experiments/hyperparameter_analyzer.py` - Getter methods and ranking_only check
- `templates/ml_platform/model_experiments.html` - All dashboard components
