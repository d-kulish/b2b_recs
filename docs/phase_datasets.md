# Phase: Datasets Domain

## Document Purpose
This document provides detailed specifications for implementing the **Datasets** domain in the ML Platform. The Datasets domain defines WHAT data goes into model training.

**Last Updated**: 2025-12-05 (v4 - Unified Filtering UI)

---

## Overview

### Purpose
The Datasets domain allows users to:
1. Select source tables from BigQuery (populated by ETL)
2. Connect tables and select columns using the visual Schema Builder
3. Define data filters (date range, revenue threshold, customer filters)
4. Configure train/eval split strategy

### Key Principle
**Datasets define WHAT data, not HOW to transform it.** Feature engineering (embeddings, buckets, crosses) is handled in the Engineering & Testing domain.

### Output
A Dataset definition (JSON stored in Django) that is used by:
- TFX ExampleGen to extract data from BigQuery
- Engineering & Testing domain to create Feature Configs

---

## User Interface

### Dataset List View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Datasets                                                    [+ New Dataset] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ Q4 2024 Training Data                                        Active ● │  │
│ │ Created: Nov 15, 2024 | Last used: Nov 28, 2024                       │  │
│ │ Tables: transactions, products | Rows: ~2.4M | Date: Jul-Dec 2024     │  │
│ │ [View] [Edit] [Clone] [Archive]                                       │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ Q3 2024 Baseline                                            Archived │  │
│ │ Created: Oct 1, 2024 | Last used: Oct 15, 2024                        │  │
│ │ Tables: transactions, products | Rows: ~1.8M | Date: Apr-Sep 2024     │  │
│ │ [View] [Restore]                                                      │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dataset Creation Wizard

#### Step 1: Name & Description

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create Dataset - Step 1 of 5: Basic Info                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Dataset Name *                                                               │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Q4 2024 Training Data                                                   │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Description (optional)                                                       │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Training data for Q4 2024 model, includes holiday season transactions  │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                                                    [Cancel]  [Next →]       │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Step 2: Select Source Tables

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create Dataset - Step 2 of 5: Source Tables                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Transactions Table * (required)                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ raw_data.transactions                                              [▼] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ ℹ️ 4,521,234 rows | Last updated: 2 hours ago                               │
│                                                                              │
│ Products Table (optional, for product metadata)                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ raw_data.products                                                  [▼] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ ℹ️ 45,123 rows | Last updated: 2 hours ago                                  │
│                                                                              │
│ Customers Table (optional, for customer metadata)                            │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ None selected                                                      [▼] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Available tables from ETL:                                                   │
│ • raw_data.transactions (4.5M rows)                                         │
│ • raw_data.products (45K rows)                                              │
│ • raw_data.customers (125K rows)                                            │
│                                                                              │
│                                         [← Back]  [Cancel]  [Next →]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Step 3: Visual Schema Builder

The Schema Builder provides a visual, drag-and-drop interface for connecting tables and selecting columns. It uses a dotted background pattern (similar to Vertex AI Pipelines) to create a canvas-like experience.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create Dataset - Step 3 of 5: Schema Builder                                │
│ Connect tables and select columns for your dataset.                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌·····································································────┐ │
│ │                                                                          │ │
│ │  ┌─────────────────┐         ┌─────────────────┐    ┌─────────────────┐  │ │
│ │  │ customers  SEC  │         │ transactions PRI│    │ products   SEC  │  │ │
│ │  ├─────────────────┤         ├─────────────────┤    ├─────────────────┤  │ │
│ │  │☑ customer_id ●──┼────────►│☑ customer_id  ●│    │☑ product_id  ○  │  │ │
│ │  │☑ first_name     │         │☑ product_id  ●─┼───►│☑ product_code ● │  │ │
│ │  │☑ last_name      │         │☑ timestamp      │    │☑ category       │  │ │
│ │  │☐ email       [+]│         │☑ amount         │    │☐ price       [+]│  │ │
│ │  │☐ created_at  [+]│         │☐ category       │    │☑ description    │  │ │
│ │  └─────────────────┘         └─────────────────┘    └─────────────────┘  │ │
│ │                                                                          │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Preview (5 rows):                                                            │
│ ┌────────────────────────────────────────────────────────────────────────┐  │
│ │ customer_id │ product_id │ timestamp  │ amount │ product_code │ ...   │  │
│ ├────────────────────────────────────────────────────────────────────────┤  │
│ │ C001        │ P123       │ 2024-11-01 │ 45.00  │ SKU-123      │ ...   │  │
│ │ C002        │ P456       │ 2024-11-02 │ 89.50  │ SKU-456      │ ...   │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│                                         [← Back]  [Cancel]  [Next →]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Features:**

1. **Draggable Table Cards**: Each table is represented as a draggable card with:
   - Table name and role badge (PRIMARY/SECONDARY)
   - Scrollable column list with checkboxes for selection
   - Column data types displayed (int, str, flo, tim, etc.)

2. **Column Connection System**:
   - **Recommended columns** (pattern-matched like `*_id`, `*_key`, `*_code`): Show empty dots (○) as visual hints
   - **Connected columns**: Show colored dots (●) matching the connection line color
   - **Any column**: Show "+" on hover to enable connection

3. **Connection Creation**:
   - Click a dot or "+" to enter connect mode
   - A floating popover appears showing:
     - Column name
     - Data type (INTEGER, STRING, FLOAT, etc.)
     - Sample values (3-5 examples from loaded data)
   - Hover over target column to see its info + compatibility status
   - Click target to create connection
   - Press Escape or click outside to cancel

4. **Type Compatibility**:
   - Compatible types show green "✓ Compatible" indicator
   - Mismatched types show warning "⚠ Type mismatch: INTEGER ↔ STRING"
   - Connections are allowed regardless (warning only, not blocking)

5. **Connection Lines**:
   - Curved SVG paths connecting column rows (not table borders)
   - Different colors for different connections (blue, green, red, purple, etc.)
   - Lines update in real-time when dragging cards or scrolling columns
   - Arrow indicators (▲/▼) when connected column is scrolled out of view

6. **Live Preview**:
   - Sample data preview updates when columns are selected/deselected
   - Shows joined result based on current connections
   - Stats display (row count, columns)

**Column Info Popover:**

```
┌─────────────────────────────┐
│ customer_id                 │
│ Type: INTEGER               │
│ Samples: 1001, 1002, 1543,  │
│          2089, 3421         │
│                             │
│ Click a column in another   │
│ table to connect            │
└─────────────────────────────┘
```

**Target Column Popover (compatible):**

```
┌─────────────────────────────┐
│ user_id                     │
│ Type: INTEGER               │
│ Samples: 1001, 1002, 1543   │
│                             │
│ ✓ Compatible                │
└─────────────────────────────┘
```

**Target Column Popover (incompatible):**

```
┌─────────────────────────────┐
│ user_name                   │
│ Type: STRING                │
│ Samples: "john", "mary"     │
│                             │
│ ⚠ Type mismatch             │
│   INTEGER ↔ STRING          │
└─────────────────────────────┘
```

#### Step 4: Filtering

Step 4 contains three collapsible sub-chapters for filtering data (all collapsed by default).
Each sub-chapter has a tablet-style header with black border that expands/collapses content.

**Unified Notification System (All Sub-chapters)**

All filtering sub-chapters use a consistent notification system:

1. **Summary Line** (below filter buttons):
   - Shows details of pending/selected filters in a yellow/amber background
   - Displays filter configuration (e.g., "Column: transaction_date • 30 days rolling window")
   - Updates immediately when filter values change
   - Shows "No filters selected" when empty

2. **Tablet Badge** (in sub-chapter header):
   - Shows "X filters applied" only AFTER clicking "Refresh Dataset"
   - Badge is cleared when filter values are changed (requires re-clicking Refresh)
   - Provides visual confirmation that filters have been committed

3. **Refresh Dataset Button**:
   - Disabled (grey) until filters are configured
   - Enabled (black with white text) when filters are ready to apply
   - Commits pending changes and updates Dataset Summary when clicked

**Sub-chapter 1: Dates**

Filter dataset by date range using one of two methods:

- **Timestamp Column** (required): Select the date/timestamp column to use for filtering
- **Rolling Window**: Set number of days from the latest available date (default: 30 days)
- **Start Date**: Select a fixed start date via calendar picker
- **Refresh Dataset**: Apply the selected date filter and update Dataset Summary

UI Components:
- Four equal-width buttons in a row with helper labels above each button
- Helper labels: "Select timestamp column", "Set number of days", "Select start date"
- Refresh Dataset button has no label (uses &nbsp; for alignment)
- Rolling Window and Start Date buttons are disabled until Timestamp Column is selected
- Each button opens a popup dropdown for selection
- Popups auto-close when value is selected (Apply button for Rolling Window)
- Summary line below buttons shows pending filter details
- Tablet header shows "1 filter applied" badge after clicking Refresh Dataset

**Sub-chapter 2: Customers**

Filter customers based on transaction history:

- **Minimum transactions per customer** (optional checkbox): Exclude customers with fewer than N transactions
- Helps filter out customers who don't provide enough signal for recommendations

**Sub-chapter 3: Products**

Filter products using multiple filter types. All filters are combined with **AND logic** (products must pass ALL enabled filters).

The Products sub-chapter uses a **pending/committed state** model:
- Filter changes are "pending" until committed
- **Refresh Dataset**: Commits pending changes and updates Dataset Summary

Products sub-chapter uses a **minimalist 3-button navigation** design with modal-based configuration:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Products                                            [2 filters applied]  ▼  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Filter by revenue        Filter by columns                                  │
│  [ Top Products ]         [ Filter Columns ]        [ Refresh Dataset ]      │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Top 80% products • category                              (summary)   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Navigation Buttons:**

1. **Top Products** - Opens modal for revenue-based product filtering
   - Helper label above: "Filter by revenue"
2. **Filter Columns** - Opens modal to manage column filters (STRING, INTEGER, FLOAT, DATE types)
   - Helper label above: "Filter by columns"
3. **Refresh Dataset** - Commits all pending changes and updates Dataset Summary
   - Black background with white text when enabled
   - Grey/disabled until at least one filter is configured
   - No helper label (empty space for alignment)

**Summary Line:**
- Shows pending filter details: "Top 80% products • category • price"
- Yellow/amber background when filters are pending
- Updates dynamically when filters are added/removed
- Shows "No filters selected" when empty

**Tablet Badge:**
- Shows "X filters applied" only after clicking Refresh Dataset
- Cleared when filter configuration changes

---

**Top Products Modal**

Modal dialog for filtering top-performing products by revenue contribution:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Top Products by Revenue                                                 [×] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Product ID Column      Revenue Column           [Analyze]                   │
│  [product_id      ▼]    [amount         ▼]                                  │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │         Cumulative Revenue Distribution (D3.js Pareto Chart)            │ │
│ │  100% ┤ ························○                                       │ │
│ │       │                    ○····                                        │ │
│ │   80% ├──────────────○·········  ← Threshold                            │ │
│ │       │          ○···                                                   │ │
│ │   60% ┤      ○···                                                       │ │
│ │       │   ○··                                                           │ │
│ │   40% ┤ ○··                                                             │ │
│ │       │○·                                                               │ │
│ │   20% ┤·                                                                │ │
│ │    0% ├─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────      │ │
│ │       0%   10%   20%   30%   40%   50%   60%   70%   80%   90% 100%     │ │
│ │                        % of Products                                    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Revenue Threshold: [80%] ──●──────────────                                  │
│ Selected: 4,521 products (9.4%) covering 80% of revenue                     │
│                                                                              │
│                                                    [Cancel]     [Apply]      │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Single Row Layout**: Product ID Column, Revenue Column, and Analyze button in one row
- **Product ID Column**: Dropdown for product identifier column
- **Revenue Column**: Dropdown for revenue/amount column
- **Analyze Button**: Triggers BigQuery analysis for revenue distribution
- **D3.js Pareto Chart**: Visual cumulative revenue distribution (appears after analysis)
- **Threshold Input**: Set percentage of cumulative revenue (default: 80%)
- **Analysis Results**: Shows total/selected products and revenue coverage
- Opening the modal auto-enables the filter (no separate checkbox needed)
- Product list computed dynamically at training time (rules stored, not product lists)

---

**Filter Columns Modal**

Modal dialog with **smart behavior**:
- If no filters exist → Shows "Add Filter" section directly
- If filters exist → Shows list of existing filters with "Add Filter" button

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Filter Columns                                                          [×] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Existing Filters:                                                           │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ category (STRING)           Include: Electronics, Clothing    [Edit][×] │ │
│ │ price (FLOAT)               Range: 10 - 500                   [Edit][×] │ │
│ │ active_since (DATE)         Last 90 days                      [Edit][×] │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                              [+ Add Filter]                                  │
│                                                                              │
│ ─────────────────────────────────────────────────────────────────────────── │
│                                                                              │
│ Add New Filter:                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Select column...                                                     ▼ │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [Inline filter configuration appears here based on column type]        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                                                    [Cancel]     [Done]       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Column Dropdown Rules:**
- Shows only columns from Step 3 Schema Builder selection
- **Excludes** columns already used in Dates sub-chapter (timestamp column)
- **Excludes** columns already used in Customers sub-chapter
- **Excludes** columns already added as filters
- Shows column type badge next to each option

**Inline Filter Configuration by Data Type:**

After selecting a column, the appropriate filter UI appears inline:

1. **STRING Columns** - Category Filter:
   ```
   ┌─────────────────────────────────────────────────────────────────────┐
   │ category (STRING) - 4 unique values                                 │
   │ ○ Include selected   ● Exclude selected                             │
   │ ┌─────────────────────────────────────────────────────────────────┐ │
   │ │ [Search values...]                                              │ │
   │ │ ☑ Electronics     (1,234)                                       │ │
   │ │ ☑ Clothing        (892)                                         │ │
   │ │ ☐ Home & Garden   (456)                                         │ │
   │ │ ☐ Sports          (234)                                         │ │
   │ └─────────────────────────────────────────────────────────────────┘ │
   │                                              [Add Filter]           │
   └─────────────────────────────────────────────────────────────────────┘
   ```
   - Mode toggle: Include OR Exclude selected values
   - List mode (≤100 unique values): Checkbox list with search
   - Autocomplete mode (>100 unique values): Search input with dropdown
   - API call to search matching values: `POST /api/models/{id}/datasets/search-category-values/`

2. **INTEGER/FLOAT Columns** - Numeric Filter:
   ```
   ┌─────────────────────────────────────────────────────────────────────┐
   │ price (FLOAT) - Range: 0.50 - 12,450 | Nulls: 0.5%                  │
   │ Filter Type: ○ Range  ○ Equals  ○ Not Equals                        │
   │                                                                     │
   │ Min: [10        ]    Max: [500       ]                              │
   │ ☑ Include NULL values                                               │
   │                                              [Add Filter]           │
   └─────────────────────────────────────────────────────────────────────┘
   ```
   - Shows column statistics (min, max, null percentage)
   - Filter types: Range, Equals, Not Equals
   - Min/Max inputs for range, single value for equals
   - NULL handling checkbox

3. **DATE/TIMESTAMP Columns** - Date Filter:
   ```
   ┌─────────────────────────────────────────────────────────────────────┐
   │ active_since (DATE) - Range: 2020-01-01 - 2024-12-01                │
   │ Filter Type: ● Relative  ○ Date Range                               │
   │                                                                     │
   │ ┌─────────────────────────────────────────────────────────────────┐ │
   │ │ Last 90 days                                                  ▼ │ │
   │ └─────────────────────────────────────────────────────────────────┘ │
   │   Options: Last 7 days, Last 30 days, Last 90 days,                │
   │            This month, This quarter, This year, Custom              │
   │                                                                     │
   │ — OR (when Date Range selected) —                                   │
   │                                                                     │
   │ Start: [2024-01-01  📅]    End: [2024-12-01  📅]                    │
   │ ☑ Include NULL values                                               │
   │                                              [Add Filter]           │
   └─────────────────────────────────────────────────────────────────────┘
   ```
   - Shows column date range from sample data
   - **Relative options**: Last 7/30/90 days, This month/quarter/year
   - **Date range**: Calendar pickers for start and end dates
   - Toggle between relative and absolute date range
   - NULL handling checkbox

**Column Analysis Service**
`ColumnAnalysisService` class in `ml_platform/datasets/services.py` analyzes columns from Step 3 pandas sample data:

- **API endpoint**: `POST /api/models/{model_id}/datasets/analyze-columns/`
- **Input**: Selected columns from Step 3 Schema Builder (stored in session)
- **Output**: Column metadata including:
  - `type`: STRING, INTEGER, FLOAT, DATE, TIMESTAMP, etc.
  - `filter_type`: Determines which filter UI to show:
    - `'category'` for STRING columns
    - `'numeric'` for INTEGER/FLOAT columns
    - `'date'` for DATE/TIMESTAMP columns
  - For STRING: `unique_values`, `value_counts`, `display_mode` (list or autocomplete)
  - For numeric: `min`, `max`, `mean`, `null_count`, `null_percent`
  - For DATE/TIMESTAMP: `min_date`, `max_date`, `null_count`, `null_percent`
- **Autocomplete threshold**: 100 unique values (configurable via `AUTOCOMPLETE_THRESHOLD`)

**Category Value Search API**
For autocomplete mode when columns have >100 unique values:

- **API endpoint**: `POST /api/models/{model_id}/datasets/search-category-values/`
- **Input**: `column_name`, `search_term`, `limit` (default: 20)
- **Output**: Matching values with counts, sorted by count descending

**Dataset Summary Panel**

Always-visible panel at the bottom of Step 4 showing dataset statistics:

- **Header**: "Dataset Summary" with total rows count badge (e.g., "100,000 rows")
- **Filter Badges**: Three badges showing applied filters status
  - Dates: "All dates" or "Last 30 days" or "From 2025-01-01"
  - Customers: "All customers" or "Min 2 transactions"
  - Products: Shows count and types of active filters:
    - "All products" (no filters)
    - "Top 80% revenue" (only revenue filter)
    - "3 filters" (multiple filters - hover shows details)
  - Active filters shown with blue highlight
- **Column Statistics Table**: Two-column table showing stats for each selected column
  - Column name
  - Data Type (STRING, INTEGER, FLOAT, TIMESTAMP, etc.)
  - Statistics based on type:
    - STRING: Unique count
    - INTEGER/FLOAT: Min · Max · Avg
    - DATE/TIMESTAMP: Min · Max · Unique count
    - BOOL: True count · False count
  - Null counts shown if any nulls present

**DatasetStatsService** (Backend):
- New service in `ml_platform/datasets/services.py`
- API endpoint: `POST /api/models/{model_id}/datasets/stats/`
- Calculates statistics with optional filters (dates, customers, products)
- Returns: total_rows, filters_applied, column_stats
- Stats are recalculated when "Refresh Dataset" is clicked with current filter settings

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create Dataset - Step 4 of 5: Filtering                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Dates                                         [30 days rolling window]  │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│   [Timestamp Column] [Rolling Window] [Start Date] [Refresh Dataset]        │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Customers                                                           ▶   │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Products                                                            ▶   │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Dataset Summary                                           [85,000 rows] │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ [Last 30 days] [All customers] [All products]                           │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ Column                    │ Data Type │ Statistics                      │ │
│ │ transactions.amount       │ FLOAT     │ Min: 8.27 · Max: 896 · Avg: 248 │ │
│ │ transactions.quantity     │ INTEGER   │ Min: 1 · Max: 9 · Avg: 5.01     │ │
│ │ transactions.trans_date   │ TIMESTAMP │ Min: 2024-03-04 · Max: 2024-04  │ │
│ │ transactions.category     │ STRING    │ Unique: 4                       │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│                                              [← Back]  [Cancel]  [Next →]   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Validation Requirements for Step 4:**
- Timestamp column must be selected
- Product ID column must be selected
- Revenue column must be selected
- Product analysis must be run successfully (click "Analyze Revenue Distribution" button)
- If analysis fails or returns 0 products, user cannot proceed to next step
- Save button only appears on final step (Step 5)

#### Step 5: Train/Eval Split

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create Dataset - Step 5 of 5: Train/Eval Split                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ SPLIT STRATEGY                                                               │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ ● Time-based split (recommended for temporal data)                          │
│   Last [14 ▼] days for evaluation                                           │
│   ℹ️ Mimics real-world: train on past, predict future                       │
│                                                                              │
│ ○ Random split                                                              │
│   [80 ▼] % train / [20 ▼] % eval                                            │
│                                                                              │
│ ═══════════════════════════════════════════════════════════════════════════ │
│ PREVIEW                                                                      │
│ ═══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│ Estimated dataset size after filters:                                        │
│ • Total transactions: ~2,450,000                                            │
│ • Unique customers: ~98,000                                                 │
│ • Unique products: ~36,000                                                  │
│ • Train set: ~2,100,000 (86%)                                               │
│ • Eval set: ~350,000 (14%)                                                  │
│                                                                              │
│                                     [← Back]  [Cancel]  [Create Dataset]    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technical Implementation Details

### Product Revenue Analysis (Step 4)

The "Analyze Revenue Distribution" button triggers a BigQuery analysis via the `ProductRevenueAnalysisService`:

**API Endpoint:** `POST /api/models/{model_id}/datasets/analyze-product-revenue/`

**Request:**
```json
{
  "primary_table": "raw_data.transactions",
  "product_column": "transactions.product_id",
  "revenue_column": "transactions.total_amount",
  "timestamp_column": "transactions.transaction_date",
  "rolling_days": 30
}
```

**Response:**
```json
{
  "status": "success",
  "total_products": 48234,
  "total_revenue": 15500000.0,
  "date_range": {"start": "2024-11-03", "end": "2024-12-03"},
  "distribution": [
    {"percent_products": 1.0, "cumulative_revenue_percent": 15.2},
    {"percent_products": 5.0, "cumulative_revenue_percent": 42.1},
    {"percent_products": 10.0, "cumulative_revenue_percent": 58.7},
    ...
  ],
  "thresholds": {
    "70": {"products": 2891, "percent": 6.0},
    "80": {"products": 4521, "percent": 9.4},
    "90": {"products": 8234, "percent": 17.1},
    "95": {"products": 15234, "percent": 31.6}
  }
}
```

**Key Implementation Notes:**
1. The service uses CTEs to compute cumulative revenue distribution
2. Window functions (`LAG`) must be computed in separate CTEs before aggregation (BigQuery limitation)
3. Distribution curve is sampled to ~50 points for efficient charting
4. Pre-computed thresholds for 70%, 80%, 90%, 95% are returned for quick UI updates
5. Date filtering applies before revenue analysis if timestamp_column and rolling_days are provided

### D3.js Chart Integration

The cumulative revenue chart uses D3.js v7 loaded from CDN:
- `<script src="https://d3js.org/d3.v7.min.js"></script>`
- Chart renders in SVG with responsive width
- Includes threshold line, shaded area, and axis labels
- Updates dynamically when threshold slider changes

---

## Data Model

### Django Models

```python
# ml_platform/models.py

class Dataset(models.Model):
    """
    Defines what data goes into training.
    Does NOT define how to transform features - that's FeatureConfig.
    """
    # Basic info
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    ml_model = models.ForeignKey('MLModel', on_delete=models.CASCADE, related_name='datasets')

    # Status
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Source tables
    transactions_table = models.CharField(max_length=255)  # e.g., "raw_data.transactions"
    products_table = models.CharField(max_length=255, blank=True)
    customers_table = models.CharField(max_length=255, blank=True)

    # Filters (JSON)
    filters = models.JSONField(default=dict)
    # Example:
    # {
    #   "date_range": {"type": "rolling", "months": 6},
    #   "product_filter": {"type": "top_revenue_percent", "value": 80},
    #   "customer_filter": {"type": "min_transactions", "value": 2}
    # }

    # Split configuration (JSON)
    split_config = models.JSONField(default=dict)
    # Example:
    # {
    #   "strategy": "time_based",
    #   "eval_days": 14
    # }
    # OR:
    # {
    #   "strategy": "random",
    #   "train_percent": 80
    # }

    # Metadata (populated after analysis)
    row_count_estimate = models.IntegerField(null=True, blank=True)
    unique_users_estimate = models.IntegerField(null=True, blank=True)
    unique_products_estimate = models.IntegerField(null=True, blank=True)
    date_range_start = models.DateField(null=True, blank=True)
    date_range_end = models.DateField(null=True, blank=True)

    # Column statistics (JSON, populated by analysis)
    column_stats = models.JSONField(default=dict)
    # Example:
    # {
    #   "user_id": {"cardinality": 125234, "null_percent": 0.1},
    #   "product_id": {"cardinality": 45123, "null_percent": 0},
    #   "revenue": {"min": 0.5, "max": 12450, "mean": 45.67},
    #   ...
    # }

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.status})"

    def get_bigquery_query(self):
        """
        Generate the BigQuery SQL query based on this dataset definition.
        Used by TFX ExampleGen.
        """
        # Implementation in services.py
        pass


class DatasetVersion(models.Model):
    """
    Tracks versions of a dataset (for reproducibility).
    Created when a dataset is used in training.
    """
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()

    # Snapshot of configuration at time of use
    config_snapshot = models.JSONField()  # Full copy of dataset config

    # Stats at time of snapshot
    actual_row_count = models.IntegerField(null=True)
    actual_unique_users = models.IntegerField(null=True)
    actual_unique_products = models.IntegerField(null=True)

    # Links to training runs that used this version
    # (via TrainingRun.dataset_version FK)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['dataset', 'version_number']
        ordering = ['-version_number']
```

### JSON Schema: filters

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "date_range": {
      "type": "object",
      "oneOf": [
        {
          "properties": {
            "type": {"const": "rolling"},
            "days": {"type": "integer", "minimum": 1, "maximum": 730}
          },
          "required": ["type", "days"]
        },
        {
          "properties": {
            "type": {"const": "fixed"},
            "start_date": {"type": "string", "format": "date"},
            "end_date": {"type": "string", "format": "date"}
          },
          "required": ["type", "start_date", "end_date"]
        }
      ]
    },
    "product_filter": {
      "type": "object",
      "description": "Combined product filters (AND logic)",
      "properties": {
        "top_revenue": {
          "type": "object",
          "description": "Optional revenue-based filter",
          "properties": {
            "enabled": {"type": "boolean"},
            "product_column": {"type": "string"},
            "revenue_column": {"type": "string"},
            "threshold": {"type": "integer", "minimum": 1, "maximum": 100}
          }
        },
        "category_filters": {
          "type": "array",
          "description": "Optional category-based filters",
          "items": {
            "type": "object",
            "properties": {
              "column": {"type": "string"},
              "mode": {"enum": ["include", "exclude"]},
              "values": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["column", "mode", "values"]
          }
        },
        "numeric_filters": {
          "type": "array",
          "description": "Optional numeric-based filters",
          "items": {
            "type": "object",
            "properties": {
              "column": {"type": "string"},
              "filter_type": {"enum": ["range", "equals", "not_equals"]},
              "min": {"type": ["number", "null"]},
              "max": {"type": ["number", "null"]},
              "value": {"type": ["number", "null"]},
              "include_nulls": {"type": "boolean"}
            },
            "required": ["column", "filter_type", "include_nulls"]
          }
        }
      }
    },
    "customer_filter": {
      "type": "object",
      "properties": {
        "type": {"enum": ["min_transactions", "none"]},
        "value": {"type": "integer", "minimum": 1}
      }
    }
  }
}
```

**Example product_filter with multiple filters:**
```json
{
  "product_filter": {
    "top_revenue": {
      "enabled": true,
      "product_column": "transactions.product_id",
      "revenue_column": "transactions.amount",
      "threshold": 80
    },
    "category_filters": [
      {
        "column": "products.category",
        "mode": "exclude",
        "values": ["Electronics", "Clothing"]
      },
      {
        "column": "products.brand",
        "mode": "include",
        "values": ["Nike", "Adidas"]
      }
    ],
    "numeric_filters": [
      {
        "column": "products.price",
        "filter_type": "range",
        "min": 10,
        "max": 500,
        "include_nulls": false
      }
    ]
  }
}
```

---

## API Endpoints

### Dataset CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{model_id}/datasets/` | List datasets for a model |
| POST | `/api/models/{model_id}/datasets/` | Create new dataset |
| GET | `/api/datasets/{dataset_id}/` | Get dataset details |
| PUT | `/api/datasets/{dataset_id}/` | Update dataset |
| DELETE | `/api/datasets/{dataset_id}/` | Delete dataset |
| POST | `/api/datasets/{dataset_id}/clone/` | Clone dataset |
| POST | `/api/datasets/{dataset_id}/archive/` | Archive dataset |

### Table Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{model_id}/tables/` | List available BigQuery tables |
| GET | `/api/tables/{table_name}/schema/` | Get table schema |
| GET | `/api/tables/{table_name}/stats/` | Get column statistics |
| POST | `/api/datasets/{dataset_id}/analyze/` | Analyze dataset (compute stats) |
| GET | `/api/datasets/{dataset_id}/preview/` | Preview sample data |

### Product Filtering

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/models/{model_id}/datasets/analyze-product-revenue/` | Analyze product revenue distribution |
| POST | `/api/models/{model_id}/datasets/analyze-columns/` | Analyze columns for filter options |
| POST | `/api/models/{model_id}/datasets/search-category-values/` | Search category values (autocomplete) |

### API Response Examples

**GET /api/models/{model_id}/tables/**
```json
{
  "status": "success",
  "data": {
    "tables": [
      {
        "name": "raw_data.transactions",
        "row_count": 4521234,
        "last_modified": "2024-11-28T10:30:00Z",
        "columns": ["customer_code", "article_id", "trans_date", "net_amount", "city"]
      },
      {
        "name": "raw_data.products",
        "row_count": 45123,
        "last_modified": "2024-11-28T10:30:00Z",
        "columns": ["article_id", "article_name", "category", "subcategory"]
      }
    ]
  }
}
```

**GET /api/tables/{table_name}/stats/**
```json
{
  "status": "success",
  "data": {
    "table": "raw_data.transactions",
    "columns": {
      "customer_code": {
        "type": "STRING",
        "cardinality": 125234,
        "null_percent": 0.1,
        "sample_values": ["C001234", "C005678", "C009012"]
      },
      "net_amount": {
        "type": "FLOAT64",
        "min": 0.5,
        "max": 12450.0,
        "mean": 45.67,
        "median": 28.50,
        "null_percent": 0
      },
      "trans_date": {
        "type": "DATE",
        "min": "2024-05-01",
        "max": "2024-11-28",
        "null_percent": 0
      }
    }
  }
}
```

**POST /api/datasets/{dataset_id}/analyze/**
```json
{
  "status": "success",
  "data": {
    "row_count_estimate": 2450000,
    "unique_users_estimate": 98000,
    "unique_products_estimate": 36000,
    "train_rows": 2100000,
    "eval_rows": 350000,
    "date_range": {
      "start": "2024-06-01",
      "end": "2024-11-28"
    },
    "column_stats": {
      "user_id": {"cardinality": 98000},
      "product_id": {"cardinality": 36000},
      "revenue": {"min": 0.5, "max": 8500, "mean": 52.3}
    }
  }
}
```

---

## Services

### BigQuery Analysis Service

```python
# ml_platform/datasets/services.py

from google.cloud import bigquery
from typing import Dict, List, Any

class DatasetAnalysisService:
    """
    Analyzes BigQuery tables and datasets for column statistics,
    cardinality, and data quality metrics.
    """

    def __init__(self, project_id: str):
        self.client = bigquery.Client(project=project_id)
        self.project_id = project_id

    def list_tables(self, dataset_id: str = "raw_data") -> List[Dict]:
        """List all tables in a dataset with basic metadata."""
        pass

    def get_table_schema(self, table_name: str) -> Dict:
        """Get schema for a specific table."""
        pass

    def get_column_stats(self, table_name: str) -> Dict:
        """
        Compute statistics for all columns in a table.
        - Cardinality for string columns
        - Min/max/mean for numeric columns
        - Date range for date columns
        - Null percentage for all columns
        """
        pass

    def analyze_dataset(self, dataset: 'Dataset') -> Dict:
        """
        Analyze a dataset definition to compute:
        - Estimated row count after filters
        - Unique users/products after filters
        - Train/eval split sizes
        """
        pass

    def generate_bigquery_query(self, dataset: 'Dataset') -> str:
        """
        Generate the BigQuery SQL query for a dataset definition.
        This query will be used by TFX BigQueryExampleGen.
        """
        pass

    def preview_data(self, dataset: 'Dataset', limit: int = 100) -> List[Dict]:
        """Return sample rows from the dataset."""
        pass


class SmartDefaultsService:
    """
    Provides smart defaults and recommendations for dataset configuration
    based on data analysis.
    """

    def suggest_filters(self, column_stats: Dict) -> Dict:
        """
        Suggest filter settings based on data distribution.
        - If >1M products, suggest top 80% filter
        - If many single-transaction customers, suggest min 2
        """
        pass

    def get_embedding_recommendations(self, column_stats: Dict) -> Dict:
        """
        Recommend embedding dimensions based on cardinality.
        (Used by Engineering & Testing domain)
        """
        cardinality_to_dim = {
            (0, 50): 8,
            (50, 1000): 16,
            (1000, 10000): 32,
            (10000, 100000): 64,
            (100000, 1000000): 96,
            (1000000, float('inf')): 128
        }
        # Implementation
        pass
```

---

## BigQuery Query Generation

The Dataset definition generates a BigQuery query for TFX ExampleGen.

### Example Generated Query

For a dataset with:
- Rolling 6-month window
- Top 80% revenue products
- Min 2 transactions per customer
- Time-based split (14 days eval)

```sql
-- Generated query for Dataset: Q4 2024 Training Data
WITH
-- Filter date range (rolling 6 months)
date_filtered AS (
  SELECT *
  FROM `project.raw_data.transactions`
  WHERE trans_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH)
),

-- Calculate product revenue ranking
product_revenue AS (
  SELECT
    article_id,
    SUM(net_amount) as total_revenue,
    PERCENT_RANK() OVER (ORDER BY SUM(net_amount) DESC) as revenue_rank
  FROM date_filtered
  GROUP BY article_id
),

-- Filter top 80% revenue products
top_products AS (
  SELECT article_id
  FROM product_revenue
  WHERE revenue_rank <= 0.80
),

-- Filter customers with min 2 transactions
active_customers AS (
  SELECT customer_code
  FROM date_filtered
  WHERE article_id IN (SELECT article_id FROM top_products)
  GROUP BY customer_code
  HAVING COUNT(*) >= 2
),

-- Join with product metadata
enriched_transactions AS (
  SELECT
    t.customer_code AS user_id,
    t.article_id AS product_id,
    t.trans_date AS timestamp,
    t.net_amount AS revenue,
    t.city,
    p.article_name AS product_name,
    p.category,
    p.subcategory,
    -- Split indicator: 1 = eval, 0 = train
    CASE
      WHEN t.trans_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) THEN 1
      ELSE 0
    END AS split
  FROM date_filtered t
  INNER JOIN top_products tp ON t.article_id = tp.article_id
  INNER JOIN active_customers ac ON t.customer_code = ac.customer_code
  LEFT JOIN `project.raw_data.products` p ON t.article_id = p.article_id
)

SELECT * FROM enriched_transactions
```

---

## Implementation Checklist

### Phase 1: Basic Dataset CRUD
- [ ] Create Django models (Dataset, DatasetVersion)
- [ ] Create datasets sub-app structure
- [ ] Implement basic API endpoints (list, create, get, update, delete)
- [ ] Create dataset list page (HTML template)
- [ ] Create dataset creation wizard (4 steps)

### Phase 2: BigQuery Integration
- [ ] Implement DatasetAnalysisService
- [ ] List available tables from BigQuery
- [ ] Get table schema API
- [ ] Get column statistics API
- [ ] Smart column mapping suggestions

### Phase 3: Query Generation
- [ ] Implement BigQuery query generation
- [ ] Handle rolling vs fixed date ranges
- [ ] Handle product filters (top N%)
- [ ] Handle customer filters (min transactions)
- [ ] Handle train/eval split logic

### Phase 4: UI Polish
- [ ] Dataset preview (sample data)
- [ ] Column statistics display
- [ ] Estimate row counts after filters
- [ ] Clone and archive functionality
- [ ] Validation and error handling

---

## Testing

### Unit Tests

```python
# ml_platform/tests/test_datasets.py

class TestDatasetModel:
    def test_create_dataset(self):
        """Test basic dataset creation."""
        pass

    def test_filters_json_schema(self):
        """Test filter configuration validation."""
        pass


class TestDatasetAnalysisService:
    def test_list_tables(self):
        """Test listing BigQuery tables."""
        pass

    def test_column_stats_string(self):
        """Test cardinality calculation for string columns."""
        pass

    def test_column_stats_numeric(self):
        """Test min/max/mean for numeric columns."""
        pass


class TestQueryGeneration:
    def test_rolling_date_filter(self):
        """Test rolling date range in generated query."""
        pass

    def test_fixed_date_filter(self):
        """Test fixed date range in generated query."""
        pass

    def test_product_revenue_filter(self):
        """Test top N% product filter in generated query."""
        pass

    def test_time_based_split(self):
        """Test time-based train/eval split."""
        pass

    def test_random_split(self):
        """Test random train/eval split."""
        pass
```

---

## Dependencies on Other Domains

### Depends On
- **ETL Domain**: Tables in BigQuery must exist (populated by ETL)
- **Connections Domain**: For accessing BigQuery (uses same GCP project)

### Depended On By
- **Engineering & Testing Domain**: Uses Dataset to create Feature Configs
- **Training Domain**: Uses Dataset definition for ExampleGen

---

## Related Documentation

- [Implementation Overview](../implementation.md)
- [Engineering & Testing Phase](phase_engineering_testing.md)
- [Training Phase](phase_training.md)
