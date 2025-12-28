# Bug Fix Plan: Cross-Sub-Chapter Filter Application

**Date**: 2024-12-28
**Bug Summary**: Top Products/Customers calculations in query generator don't respect filters from other sub-chapters
**Affected Dataset**: `old_examples_chernigiv` (ID: 14)

---

## Problem Statement

When a user configures:
- Date filter: Last 60 days
- Customer filter: `city = 'CHERNIGIV'` (category filter)
- Product filter: Top 80% products by revenue

**Expected Behavior**: Top 80% products should be calculated from CHERNIGIV data only.

**Actual Behavior**: Top 80% products are calculated from ALL cities (globally), then city filter is applied at the end.

---

## Root Cause Analysis

### Component Status

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| UI Analysis (Products) | `model_dataset.html:8878` | ✅ Fixed in v13 | Calls `getCommittedFiltersForAnalysis()` |
| UI Analysis (Customers) | `model_dataset.html:4296` | ✅ Fixed in v13 | Calls `getCommittedFiltersForAnalysis()` |
| Backend Analysis (Products) | `services.py:2340` | ✅ Fixed in v13 | `ProductRevenueAnalysisService.analyze_distribution()` |
| Backend Analysis (Customers) | `services.py:2941` | ✅ Fixed in v13 | `CustomerRevenueAnalysisService.analyze_distribution()` |
| **Query Generator** | `services.py:884` | ❌ **BUG** | `BigQueryService.generate_query()` |

### The Bug Location

**File**: `ml_platform/datasets/services.py`
**Method**: `BigQueryService.generate_query()`
**Lines**: 996-1050

```python
# Current buggy code (simplified):
if has_date_filter:
    filtered_data_cte = f"""
        SELECT ...
        FROM `{primary_table}` AS {primary_alias}
        WHERE {date_filter_clause}"""  # ← Only date filter!
    ctes.append(('filtered_data', filtered_data_cte))

# Then top_products is calculated from filtered_data (which has ALL cities)
```

---

## Implementation Plan

### Phase 1: Fix Query Generator

**File**: `ml_platform/datasets/services.py`
**Method**: `BigQueryService.generate_query()`

#### Step 1.1: Create helper method for building WHERE clauses

Add a new helper method `_build_cross_filter_where_clauses()` that collects WHERE clauses from:
- `customer_filter.category_filters`
- `customer_filter.numeric_filters`
- `product_filter.category_filters`
- `product_filter.numeric_filters`

```python
def _build_cross_filter_where_clauses(self, filters, primary_alias, exclude_filter=None):
    """
    Build WHERE clauses from cross-sub-chapter filters.

    Args:
        filters: Full filters dict from dataset config
        primary_alias: Table alias for column references
        exclude_filter: 'customer' or 'product' - skip this filter type
                       (used when calculating top for that entity)

    Returns:
        List of WHERE clause strings
    """
```

#### Step 1.2: Modify `filtered_data` CTE construction (lines 996-1050)

Current:
```python
filtered_data_cte = f"""
    SELECT ...
    WHERE {date_filter_clause}"""
```

Change to:
```python
# Build all applicable WHERE clauses
where_clauses = []
if date_filter_clause:
    where_clauses.append(date_filter_clause)

# Add customer category/numeric filters (for top_products calculation)
customer_filter = filters.get('customer_filter', {})
where_clauses.extend(
    self._build_category_filter_clauses(customer_filter.get('category_filters', []), primary_alias)
)
where_clauses.extend(
    self._build_numeric_filter_clauses(customer_filter.get('numeric_filters', []), primary_alias)
)

# Add product category/numeric filters (for top_customers calculation)
product_filter = filters.get('product_filter', {})
where_clauses.extend(
    self._build_category_filter_clauses(product_filter.get('category_filters', []), primary_alias)
)
where_clauses.extend(
    self._build_numeric_filter_clauses(product_filter.get('numeric_filters', []), primary_alias)
)

where_clause_str = ' AND '.join(where_clauses) if where_clauses else '1=1'

filtered_data_cte = f"""
    SELECT ...
    WHERE {where_clause_str}"""
```

#### Step 1.3: Update final WHERE clause generation

After applying all filters to `filtered_data`, the final SELECT should NOT re-apply category/numeric filters (they're already in filtered_data). Only aggregation-based filters (`top_products`, `top_customers`, `filtered_products_N`, `filtered_customers_N`) should be in the final WHERE.

Review lines 1052-1070 to ensure no duplicate filters.

---

### Phase 2: Verify UI Analysis is Consistent

The UI analysis (Pareto charts) was fixed in v13. Verify it works correctly:

#### Step 2.1: Verify `analyzeProductRevenue()` (model_dataset.html:8878)

- [x] Calls `getCommittedFiltersForAnalysis()` - **CONFIRMED**
- [x] Passes filters to backend - **CONFIRMED** (line 8912)
- [x] Removes `product_filter` before sending - **CONFIRMED** (line 8897)

#### Step 2.2: Verify `analyzeCustomerRevenue()` (model_dataset.html:4296)

- [x] Calls `getCommittedFiltersForAnalysis()` - **CONFIRMED**
- [x] Passes filters to backend - **CONFIRMED** (line 4331)
- [x] Removes `customer_filter.top_revenue` before sending - **CONFIRMED** (line 4314)

#### Step 2.3: Verify Backend Analysis Services

**ProductRevenueAnalysisService** (services.py:2340):
- [x] Accepts `filters` parameter - **CONFIRMED**
- [x] Applies `customer_filter.category_filters` - **CONFIRMED** (lines 2420-2441)
- [x] Applies `customer_filter.numeric_filters` - **CONFIRMED** (lines 2444-2483)

**CustomerRevenueAnalysisService** (services.py:2941):
- [x] Accepts `filters` parameter - **CONFIRMED**
- [x] Applies `product_filter.category_filters` - **CONFIRMED** (lines 3025-3044)
- [x] Applies `product_filter.numeric_filters` - **CONFIRMED** (lines 3047-3086)
- [x] Applies `customer_filter.category_filters` - **CONFIRMED** (lines 3088+)

---

### Phase 3: Handle Edge Cases

#### Step 3.1: Top Products with Customer Filters

When calculating `top_products`:
- INCLUDE: date filter, customer category filters, customer numeric filters
- EXCLUDE: product filters (we're calculating products)
- EXCLUDE: customer aggregation filters (like min transactions - these depend on final product set)
- EXCLUDE: customer top_revenue (same entity type)

#### Step 3.2: Top Customers with Product Filters

When calculating `top_customers`:
- INCLUDE: date filter, product category filters, product numeric filters
- EXCLUDE: customer filters (we're calculating customers)
- EXCLUDE: product aggregation filters
- EXCLUDE: product top_revenue

#### Step 3.3: Aggregation Filters

Filters like "customers with > 5 transactions" or "products with > 10 sales" should be calculated AFTER top filters are applied, using the fully-filtered dataset.

Current order should be:
1. `filtered_data` CTE: date + category + numeric filters
2. `top_products` CTE: FROM filtered_data
3. `top_customers` CTE: FROM filtered_data
4. `filtered_products_N` CTEs: aggregation filters FROM filtered_data
5. `filtered_customers_N` CTEs: aggregation filters FROM filtered_data
6. Final SELECT: FROM filtered_data WHERE all CTE conditions

---

### Phase 4: Update Generated Query Structure

#### Current Structure (Buggy):
```sql
WITH filtered_data AS (
    SELECT ... FROM table WHERE date_filter_only
),
top_products AS (
    SELECT product_id FROM (
        SELECT product_id, SUM(sales)...
        FROM filtered_data  -- All cities!
        GROUP BY product_id
    ) WHERE cumulative <= 80%
)
SELECT * FROM filtered_data
WHERE product_id IN (SELECT product_id FROM top_products)
  AND city IN ('CHERNIGIV')  -- Applied too late!
```

#### Fixed Structure:
```sql
WITH filtered_data AS (
    SELECT ... FROM table
    WHERE date >= ...              -- Date filter
      AND city IN ('CHERNIGIV')    -- Customer category filters
      -- product category filters would go here too
),
top_products AS (
    SELECT product_id FROM (
        SELECT product_id, SUM(sales)...
        FROM filtered_data  -- Now correctly scoped to CHERNIGIV!
        GROUP BY product_id
    ) WHERE cumulative <= 80%
)
SELECT * FROM filtered_data
WHERE product_id IN (SELECT product_id FROM top_products)
-- No city filter needed here, already in filtered_data
```

---

### Phase 5: Testing Plan

#### Test Case 1: CHERNIGIV Dataset (Existing)

**Config**:
- Date: 60 days rolling
- Customer: city = 'CHERNIGIV'
- Product: Top 80% by revenue

**Before Fix**:
- Total rows: 107,692
- Unique products: 1,693
- Revenue coverage: 87%

**After Fix** (Expected):
- Total rows: ~same or fewer (products scoped to CHERNIGIV)
- Unique products: Should be ≤ 1,054 (CHERNIGIV top 80%)
- Revenue coverage: ~80% of CHERNIGIV revenue

**Verification Query**:
```sql
-- This query should produce same results as generated query after fix
WITH filtered_data AS (
    SELECT * FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM ...), INTERVAL 60 DAY)
      AND city = 'CHERNIGIV'  -- Filter applied BEFORE top products
),
top_products AS (
    SELECT product_id FROM (
        SELECT product_id, SUM(sales) as total_revenue,
               SUM(SUM(sales)) OVER () as grand_total,
               SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
)
SELECT COUNT(*), COUNT(DISTINCT product_id), SUM(sales)
FROM filtered_data
WHERE product_id IN (SELECT product_id FROM top_products);
```

#### Test Case 2: Multiple Category Filters

**Config**:
- Date: 30 days
- Customer: city IN ('KYIV', 'LVIV')
- Product: category = 'FRESH'
- Product: Top 90% by revenue

Verify top products are calculated from KYIV+LVIV transactions in FRESH category only.

#### Test Case 3: Numeric Filters

**Config**:
- Date: 60 days
- Customer: cust_value > 1000
- Product: Top 80%

Verify top products are calculated only from high-value customer transactions.

#### Test Case 4: Top Customers with Product Filters

**Config**:
- Date: 30 days
- Product: division_desc = 'DRY'
- Customer: Top 80% by revenue

Verify top customers are calculated from DRY division transactions only.

---

### Phase 6: Files to Modify

| File | Changes |
|------|---------|
| `ml_platform/datasets/services.py` | Modify `generate_query()` method (lines 996-1070) |
| `ml_platform/datasets/services.py` | Add helper method `_build_cross_filter_where_clauses()` |
| `sql/chernigiv_verification.sql` | Update with post-fix expected results |

---

### Phase 7: Regression Testing

After fix, verify:
1. Existing datasets can still generate queries
2. UI analysis results match generated query results
3. No performance regression on large datasets
4. Edge cases: empty filters, single filter, all filter types combined

---

## Summary

The fix is localized to the `generate_query()` method in `BigQueryService`. The key change is:

**Before**: `filtered_data` CTE only includes date filter
**After**: `filtered_data` CTE includes date + all category/numeric filters from both customer_filter and product_filter

This ensures that `top_products` and `top_customers` CTEs operate on the correctly-filtered subset of data, matching what the UI analysis shows.
