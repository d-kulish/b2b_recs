# Phase: Datasets Domain

## Document Purpose
This document provides detailed specifications for implementing the **Datasets** domain in the ML Platform. The Datasets domain defines WHAT data goes into model training.

**Last Updated**: 2026-01-12 (v17 - UI merged into Configs page)

---

## UI Location Update (2026-01-12)

**Important:** The Dataset Manager UI has been merged into the **Configs page** as the first of three chapters:

```
model_configs.html (unified page)
├── Chapter 1: Datasets          ← Dataset Manager UI now lives here
│   ├── Header: "Datasets" with [New Dataset] button
│   ├── Dataset list (scrollable cards)
│   └── Full wizard + modals (create, edit, view, delete, SQL preview)
│
├── Chapter 2: Features          (existing)
│   └── Feature config list + wizard
│
└── Chapter 3: Model Structure   (existing)
    └── Model config list + wizard
```

**Key Changes:**
- **Navigation:** Single "Datasets & Configs" link in sidebar
- **URL Redirect:** `/models/<id>/dataset/` now redirects to `/models/<id>/configs/`
- **Legacy Page:** Original `model_dataset.html` preserved for rollback
- **Backend APIs:** No changes - all `/datasets/` API endpoints work unchanged

See [datasets_migration.md](datasets_migration.md) for the full migration plan and implementation details.

---

## Overview

### Purpose
The Datasets domain allows users to:
1. Select source tables from BigQuery (populated by ETL)
2. Connect tables and select columns using the visual Schema Builder
3. Define data filters (date range, revenue threshold, customer filters)

### Key Principles

1. **Datasets define WHAT data, not HOW to transform it.** Feature engineering (embeddings, buckets, crosses) is handled in the Modeling domain.

2. **Dataset is Configuration Only.** No BigQuery views, tables, or data copies are created. The dataset stores configuration (JSON) that is used to generate SQL queries at training time.

3. **No Train/Eval Split in Dataset.** The train/eval split is handled by the Training domain (TFX ExampleGen), not Datasets. This aligns with TFX architecture where ExampleGen handles data splitting.

4. **Dynamic Rolling Windows.** Date filters like "last 90 days" are resolved at training execution time, ensuring fresh data is always used.

5. **Edit-time Versioning.** Version 1 is created when a dataset is first saved. A new version is created each time the dataset configuration is edited, enabling rollback to previous configurations.

### Output
A Dataset definition (JSON stored in Django) that is used by:
- TFX ExampleGen to extract data from BigQuery (via generated SQL query)
- Modeling domain to create Feature Configs

### What Gets Stored

```
Dataset (Django Model)
├── Metadata: name, description
├── Tables: primary_table, secondary_tables
├── Schema: selected_columns, join_config, column_mapping, column_aliases
├── Filters: date_filter, customer_filter, product_filter
├── BigQuery: bq_location (region where BQ dataset exists, e.g., 'US', 'EU')
├── Cached: row_count_estimate, summary_snapshot (not versioned)
└── NO split_config (handled by Training domain)

DatasetVersion (Django Model) - Created on each save
├── version_number: Auto-incremented (starts at 1)
├── config_snapshot: Full configuration at time of save
├── actual_row_count, actual_unique_users, actual_unique_products
└── created_at: Timestamp
```

### SQL Generation Flow

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Dataset Config  │ --> │  SQL Generator   │ --> │  BigQuery SQL    │
│  (JSON in Django)│     │  (on demand)     │     │  (for ExampleGen)│
└──────────────────┘     └──────────────────┘     └──────────────────┘
         │
         │ On each save (create/edit):
         ▼
┌──────────────────┐
│ DatasetVersion   │
│ (frozen snapshot)│
│ - version_number │  (v1, v2, v3...)
│ - config_snapshot│  (full config JSON)
│ - created_at     │
└──────────────────┘
```

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

### Dataset View Modal

The View modal displays a saved dataset's configuration and summary snapshot. This modal opens when clicking the "View" button on a dataset card.

**Key Principle**: The View modal displays data saved in `summary_snapshot` field - no BigQuery queries are executed. This makes the View instant even for large datasets (15-20M rows).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Q4 2024 Training Data                                    [View SQL] [Edit] [×]│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ [Draft]  Created 12/07/2024                              [8,233 rows]       │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 🗄️ Tables & Joins                                                       │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ Primary:    transactions                                                │ │
│ │ Secondary:  customers                                                   │ │
│ │                                                                         │ │
│ │ Join Keys:                                                              │ │
│ │ transactions.customer_id  ↔  customers.customer_id  [LEFT]              │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 🔍 Filters Applied                                                       │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ │ 📅 Date Filter                                                        │ │
│ │ │   Column: transactions.trans_date                                     │ │
│ │ │   Range: Last 30 days (rolling window)                               │ │
│ │                                                                         │ │
│ │ │ 👥 Customer Filters (1)                                               │ │
│ │ │   • Top 80% customers by revenue                                      │ │
│ │ │     Customer: customers.customer_id, Revenue: transactions.amount     │ │
│ │                                                                         │ │
│ │ │ 📦 Product Filters (1)                                                │ │
│ │ │   • Top 75% products by revenue                                       │ │
│ │ │     Product: transactions.product_id, Revenue: transactions.amount    │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 📊 Column Statistics                                                     │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ Column                    │ Type      │ Statistics                      │ │
│ │ customers.customer_id     │ INTEGER   │ Min: 59 · Max: 999.9K · Avg: 503K│ │
│ │ transactions.category     │ STRING    │ Unique: 4                       │ │
│ │ transactions.quantity     │ INTEGER   │ Min: 1 · Max: 9 · Avg: 6.35     │ │
│ │ transactions.product_id   │ STRING    │ Unique: 3                       │ │
│ │ transactions.unit_price   │ FLOAT     │ Min: 10.07 · Max: 99.99 · Avg: 67│ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ Snapshot from 12/7/2024, 2:30:45 PM                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**View Modal Sections:**

1. **Header Row**:
   - Dataset name (title)
   - Status badge (Draft/Active/Archived)
   - Created date
   - Total rows badge (from snapshot)

2. **Tables & Joins Section**:
   - Primary table name
   - Secondary table names
   - Join keys with visual arrow (↔) showing column relationships
   - Join type badge (LEFT, INNER, etc.)

3. **Filters Applied Section**:
   - **Date Filter**: Column name + range type (rolling days or fixed start date)
   - **Customer Filters**: List of applied filters with column details
     - Top revenue: shows percent + customer column + revenue column
     - Transaction count: shows filter type and value
     - Spending: shows filter type and value
     - Category/Numeric filters: shows column and criteria
   - **Product Filters**: Same structure as customer filters
   - Color-coded left borders (blue for dates, green for customers, purple for products)

4. **Column Statistics Section**:
   - Table with Column, Type, Statistics columns
   - Statistics vary by type:
     - STRING: Unique count
     - INTEGER/FLOAT: Min · Max · Avg
     - DATE/TIMESTAMP: Min · Max · Unique
     - BOOL: True count · False count
   - Snapshot timestamp at bottom

**Data Storage - summary_snapshot Field:**

The `summary_snapshot` JSONField stores the Dataset Summary from wizard Step 4:

```json
{
  "total_rows": 8233,
  "filters_applied": {
    "dates": {
      "type": "rolling",
      "days": 30,
      "column": "transactions.trans_date"
    },
    "customers": {
      "type": "multiple",
      "count": 1,
      "filters": [
        {
          "type": "top_revenue",
          "percent": 80,
          "customer_column": "customers.customer_id",
          "revenue_column": "transactions.amount"
        }
      ]
    },
    "products": {
      "type": "multiple",
      "count": 1,
      "filters": [
        {
          "type": "top_revenue",
          "percent": 75,
          "product_column": "transactions.product_id",
          "revenue_column": "transactions.amount"
        }
      ]
    }
  },
  "column_stats": {
    "customers.customer_id": {"type": "INTEGER", "min": 59, "max": 999900, "avg": 503600},
    "transactions.category": {"type": "STRING", "unique_count": 4},
    "transactions.quantity": {"type": "INTEGER", "min": 1, "max": 9, "avg": 6.35}
  },
  "snapshot_at": "2024-12-07T14:30:45.123Z"
}
```

**When summary_snapshot is Saved:**
- On **Create**: When clicking "Save" in Step 4, current `datasetStatsData` is saved
- On **Edit**: When saving after edit, new summary from Step 4 replaces old snapshot
- The snapshot captures whatever statistics are displayed at save time (filtered or unfiltered)

**API Endpoint:**
- `GET /api/datasets/{dataset_id}/summary/` - Returns dataset configuration + summary_snapshot

### View SQL Functionality

The "View SQL" button in the View modal generates a production-ready SQL query from the saved dataset configuration. This query can be copied and run directly in BigQuery.

**Key Features:**
- Generates complete SQL with all filters applied (date, products, customers)
- Uses CTEs (Common Table Expressions) for complex filters
- Rolling window date filters use `MAX(date)` from the dataset (not current date) for reproducibility
- All filter logic is applied in the correct order: date filter first, then product/customer filters

**SQL Generation Order:**
1. **filtered_data CTE**: Apply date filter first (if configured)
2. **Product filter CTEs**: top_products, filtered_products_N (from filtered_data)
3. **Customer filter CTEs**: top_customers, filtered_customers_N (from filtered_data)
4. **Final SELECT**: From filtered_data with WHERE clauses for product/customer filters

**Example Generated SQL:**
```sql
WITH filtered_data AS (
    SELECT customer_id, product_id, category, amount, transaction_date
    FROM `project.raw_data.transactions` AS transactions
    WHERE transaction_date >= TIMESTAMP_SUB(
        (SELECT MAX(transaction_date) FROM `project.raw_data.transactions`),
        INTERVAL 30 DAY
    )
),
filtered_products_0 AS (
    SELECT product_id
    FROM filtered_data
    GROUP BY product_id
    HAVING COUNT(*) > 3
),
top_customers AS (
    SELECT customer_id
    FROM (
        SELECT customer_id, SUM(amount) as total_revenue,
               SUM(SUM(amount)) OVER () as grand_total,
               SUM(SUM(amount)) OVER (ORDER BY SUM(amount) DESC) as running_total
        FROM filtered_data
        GROUP BY customer_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
)
SELECT customer_id, product_id, category, amount, transaction_date
FROM filtered_data
WHERE product_id IN (SELECT product_id FROM filtered_products_0)
  AND category IN ('Electronics', 'Home Decor')
  AND customer_id IN (SELECT customer_id FROM top_customers)
```

**API Endpoint:**
- `GET /api/datasets/{dataset_id}/query/` - Returns generated SQL query

**Backend Service:**
- `BigQueryService.generate_query()` in `ml_platform/datasets/services.py`
- Uses `_generate_date_filter()`, `_generate_product_filter_clauses_v2()`, `_generate_customer_filter_clauses_v2()`

### Dataset Edit Functionality

The Edit button on dataset cards opens the same 4-step wizard in "edit mode", pre-populated with the saved dataset configuration. Users can modify any aspect of the dataset and save changes.

**Edit Flow:**

1. User clicks "Edit" on a dataset card
2. `openWizard(datasetId)` is called with the dataset ID, setting `wizardEditMode = true`
3. Tables are loaded from BigQuery (`loadBqTables()`)
4. After tables load, `loadDatasetForEdit(datasetId)` fetches and populates saved configuration
5. User navigates through steps, with each step restoring saved data

**Data Restoration by Step:**

**Step 1 - Basic Info:**
- Dataset name and description are populated from saved values
- Form fields are set directly from `wizardData.name` and `wizardData.description`

**Step 2 - Source Tables:**
- Primary table selection is restored from `wizardData.primaryTable`
- Secondary tables are restored from `wizardData.secondaryTables`
- Table radio buttons and checkboxes are programmatically selected

**Step 3 - Schema Builder:**
- Tables are loaded with sample data via `loadSchemaBuilder()`
- **Joins are restored** from `wizardData.joinConfig`:
  - Each join entry is converted to `schemaBuilderState.joins` format
  - `updateConnectionLines()` draws the restored connections
  - Joins remain fully editable (add/modify/delete)
- **Selected columns are restored** from `wizardData.selectedColumns`:
  - Column checkboxes are programmatically checked
  - Preview is refreshed to show selected columns

**Step 4 - Filtering:**
- `fetchColumnAnalysis()` loads column type information
- `populateFilterColumnDropdowns()` builds filter dropdowns
- `restoreFiltersFromSavedData()` restores all filter states:

  **Dates Filter Restoration:**
  - Timestamp column dropdown is set to saved value
  - Rolling days or start date is populated
  - `datesFilterState.committed` is initialized from saved data
  - `dateFiltersApplied` flag is set to `true`
  - Summary line shows restored filter details

  **Products Filter Restoration:**
  - Top revenue settings are restored (product column, revenue column, threshold)
  - Category filters are restored with column/mode/values
  - Numeric filters are restored with column/type/values
  - `productFiltersState.committed` is initialized
  - `productFiltersApplied` flag is set to `true`

  **Customers Filter Restoration:**
  - Top revenue settings are restored (customer column, revenue column, percent)
  - Aggregation filters are restored (transaction count, spending)
  - Category and numeric filters are restored
  - `customerFiltersState.committed` is initialized
  - `customerFiltersApplied` flag is set to `true`

- `fetchDatasetStats(true)` fetches statistics WITH filters applied
- Dataset Summary panel shows filtered row count and statistics

**Filter Persistence:**

Each sub-chapter's "Refresh Dataset" button saves filters to `wizardData.filters`:

```javascript
// Dates - saved in refreshDatasetHistory()
wizardData.filters.history = {
    timestamp_column: "transactions.trans_date",
    rolling_days: 30,
    start_date: null
};

// Products - saved in refreshProductFilters()
wizardData.filters.product_filter = {
    top_revenue: { enabled: true, product_column: "...", revenue_column: "...", threshold_percent: 80 },
    category_filters: [...],
    numeric_filters: [...]
};

// Customers - saved in refreshCustomerFilters()
wizardData.filters.customer_filter = {
    top_revenue: { enabled: true, customer_column: "...", revenue_column: "...", percent: 80 },
    aggregation_filters: [...],
    category_filters: [...],
    numeric_filters: [...]
};
```

**State Management in Edit Mode:**

```javascript
// Global edit mode flags
let wizardEditMode = false;           // True when editing existing dataset
let wizardEditDatasetId = null;       // ID of dataset being edited

// Filter state model (pending/committed)
// In edit mode:
// 1. committed state is restored from saved filters
// 2. pending state is set equal to committed (no unapplied changes)
// 3. Refresh buttons are disabled until user makes changes
// 4. When user changes a filter, pending differs from committed
// 5. Refresh button enables, allowing user to commit changes
```

**API Endpoints for Edit:**
- `GET /api/datasets/{dataset_id}/` - Fetch dataset configuration for editing
- `POST /api/datasets/{dataset_id}/update/` - Save updated dataset configuration

**Key Implementation Notes:**

1. **Race Condition Prevention**: `loadBqTables()` returns a Promise, and `loadDatasetForEdit()` is only called after tables are fully loaded. This ensures secondary tables display correctly.

2. **Column Name Matching**: Filter restoration uses flexible matching to handle column name format differences (with/without table prefix).

3. **Pending = Committed**: On restore, pending state equals committed state, so Refresh buttons start disabled. This is correct behavior - buttons enable when user makes changes.

4. **Statistics Refresh**: `fetchDatasetStats(true)` is called after filter restoration to show filtered statistics, not raw table statistics.

### Dataset Creation Wizard

#### Step 1: Name & Description

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create Dataset - Step 1 of 4: Basic Info                                    │
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
│ Create Dataset - Step 2 of 4: Source Tables                                 │
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
│ Create Dataset - Step 3 of 4: Schema Builder                                │
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

7. **Column Renaming (Aliases)**:
   - Double-click any column header in the preview table to rename it
   - An inline input field appears with the current name selected
   - Press Enter or click outside to save the alias
   - Press Escape to cancel
   - Aliases are displayed throughout the wizard (preview, filter dropdowns, summary)
   - Generated SQL uses aliases via AS clauses
   - Aliases are persisted with the dataset and restored when editing

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
- **Timestamp Column**: Direct dropdown with clock icon (no popup - simplified from v5)
- **Rolling Window** and **Start Date**: Buttons that open popup dropdowns
- Refresh Dataset button has no label (uses &nbsp; for alignment)
- Rolling Window and Start Date buttons are disabled until Timestamp Column is selected
- Popups auto-close when value is selected (Apply button for Rolling Window)
- **Pending/Committed State**: Like Products/Customers, Dates now uses pending/committed model for proper "Refresh Dataset" button state management
- **Summary line** below buttons uses the same structure as Products sub-chapter:
  - Shows "Filter #1: {column_name}: {details}" format
  - Includes delete button (trash icon) to clear the filter
  - Yellow/amber background when filter is configured
  - Shows "No filters selected" when empty
- Tablet header shows "1 filter applied" badge after clicking Refresh Dataset
- **Cross-sub-chapter exclusion**: After Refresh Dataset, the timestamp column is excluded from selection in Customers and Products sub-chapter dropdowns

**Sub-chapter 2: Customers**

Filter customers using multiple filter types. All filters are combined with **AND logic** (customers must pass ALL enabled filters).

The Customers sub-chapter uses the same **pending/committed state** model as Products:
- Filter changes are "pending" until committed
- **Refresh Dataset**: Commits pending changes and updates Dataset Summary

Customers sub-chapter uses a **4-button navigation** design with modal-based configuration:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Customers                                           [2 filters applied]  ▼ │
├─────────────────────────────────────────────────────────────────────────────┤
│  Filter by revenue      Filter by metrics      Filter by columns            │
│  [ Top Customers ]      [ Customer Metrics ]   [ Filter Columns ]           │
│                                                                              │
│                                                 [ Refresh Dataset ]          │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Filter #1: Top 80% customers • Filter #2: transactions > 5   [trash] │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Top Customers Button** (opens modal):
- Select Customer ID column (grouping column - NOT excluded from other filters)
- Select Revenue column (aggregation column - excluded after use)
- Click "Analyze" to see cumulative revenue distribution (Pareto chart)
- **Analysis runs directly in BigQuery** (not on sampled data) for accurate results with millions of rows
- Set revenue threshold (e.g., "Include customers covering 80% of revenue")
- Shows analysis summary: total customers, selected customers, revenue coverage
- Apply/Cancel buttons for consistent modal behavior

**Customer Metrics Button** (opens modal):
Two separate filter sections with Apply/Cancel buttons:

1. **Transaction Count Filter**:
   - Select Customer ID column (grouping column)
   - Select filter type: Greater than / Less than / Range
   - Enter value(s)
   - Filters customers by their total number of transactions (COUNT of rows per customer)

2. **Spending Filter**:
   - Select Customer ID column (grouping column)
   - Select Amount column (aggregation column - excluded after use)
   - Select filter type: Greater than / Less than / Range
   - Enter value(s)
   - Filters customers by their total spending (SUM of amount)

**Filter Columns Button** (opens modal):
Same functionality as Products Filter Columns:
- Category filters (STRING columns): Include/exclude specific values
- Numeric filters (INTEGER/FLOAT): Range, greater than, less than, equals
- Date filters: Relative (last N days) or fixed date range

**Column Exclusion Rules**:
- **Grouping columns** (customer_id in Top Customers / Customer Metrics): NOT excluded - can be reused across multiple aggregations
- **Aggregation columns** (revenue, amount in SUM): EXCLUDED after first use - prevents conflicting filter logic
- **Filter columns** (category, numeric, date): EXCLUDED after first use

**State Management**:
```javascript
let customerFiltersState = {
    pending: {
        topRevenue: { enabled, customerColumn, revenueColumn, thresholdPercent },
        aggregationFilters: [{ type, customerColumn, amountColumn?, filterType, value, min?, max? }],
        categoryFilters: [...],
        numericFilters: [...],
        dateFilters: [...]
    },
    committed: { /* same structure */ },
    columnAnalysis: {},
    selectedFilterColumn: null
};
```

**API Endpoints**:
- `POST /api/models/{id}/datasets/analyze-customer-revenue/` - Pareto analysis for Top Customers
- `POST /api/models/{id}/datasets/analyze-customer-aggregations/` - Transaction count / spending analysis

**Cross-sub-chapter Exclusion**:
- After Refresh Dataset, all committed aggregation columns (revenue, amount) are excluded from Dates and Products sub-chapter dropdowns
- Grouping columns (customer_id) are NOT excluded - can be reused

**Sub-chapter 3: Products**

Filter products using multiple filter types. All filters are combined with **AND logic** (products must pass ALL enabled filters).

The Products sub-chapter uses a **pending/committed state** model:
- Filter changes are "pending" until committed
- **Refresh Dataset**: Commits pending changes and updates Dataset Summary

Products sub-chapter uses a **4-button navigation** design with modal-based configuration:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Products                                            [3 filters applied]  ▼  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Filter by revenue      Filter by metrics      Filter by columns            │
│  [ Top Products ]       [ Product Metrics ]    [ Filter Columns ]           │
│                                                                              │
│                                                 [ Refresh Dataset ]          │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Filter #1: Top 80% revenue • Filter #2: transactions > 5  [trash]    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Navigation Buttons:**

1. **Top Products** - Opens modal for revenue-based product filtering
   - Helper label above: "Filter by revenue"
2. **Product Metrics** - Opens modal for aggregation-based product filtering
   - Helper label above: "Filter by metrics"
3. **Filter Columns** - Opens modal to manage column filters (STRING, INTEGER, FLOAT, DATE types)
   - Helper label above: "Filter by columns"
4. **Refresh Dataset** - Commits all pending changes and updates Dataset Summary
   - Black background with white text when enabled
   - Grey/disabled until at least one filter is configured
   - No helper label (empty space for alignment)

**Product Metrics Button** (opens modal):
Two separate filter sections with Apply/Cancel buttons:

1. **Transaction Count Filter**:
   - Select Product ID column (grouping column)
   - Select filter type: Greater than / Less than / Range
   - Enter value(s)
   - Filters products by their total number of transactions (COUNT of rows per product)

2. **Revenue Filter**:
   - Select Product ID column (grouping column)
   - Select Amount column (aggregation column - excluded after use)
   - Select filter type: Greater than / Less than / Range
   - Enter value(s)
   - Filters products by their total revenue (SUM of amount)

**Summary Line:**
- Shows numbered filters with delete buttons: "Filter #1: Top 80% revenue (X products)", "Filter #2: unit_price: < 20"
- Each filter shows as a separate item with trash icon for deletion
- Top Products filter displays both threshold percentage AND product count from analysis
- Yellow/amber background when filters are pending
- Updates dynamically when filters are added/removed
- Shows "No filters selected" when empty
- **Cross-sub-chapter exclusion**: After Refresh Dataset, all committed aggregation columns are excluded from Dates and Customers sub-chapter dropdowns (grouping columns like `product_id` are NOT excluded)

**Tablet Badge:**
- Shows "X filters applied" only after clicking Refresh Dataset
- Cleared when filter configuration changes

---

**State Management for Products**:
```javascript
let productFiltersState = {
    pending: {
        topRevenue: { enabled, productColumn, revenueColumn, thresholdPercent },
        aggregationFilters: [{ type, productColumn, amountColumn?, filterType, value, min?, max? }],
        categoryFilters: [...],
        numericFilters: [...],
        dateFilters: [...]
    },
    committed: { /* same structure */ },
    columnAnalysis: {},
    selectedFilterColumn: null
};
```

---

**Cross-Sub-chapter Column Exclusion**

To prevent the same column from being used in multiple filters across different sub-chapters, the system implements centralized column tracking:

1. **Committed State Tracking**: Each sub-chapter tracks which columns have been "committed" (applied via Refresh Dataset)
   - Dates: `committedDatesFilter.timestampColumn`
   - Products: `productFiltersState.committed` (topRevenue columns, aggregation columns, category/numeric/date filter columns)
   - Customers: `customerFiltersState.committed` (topRevenue columns, aggregation columns, category/numeric/date filter columns)

2. **Column Availability Rules**:
   - Columns committed in Dates sub-chapter are excluded from Products and Customers dropdowns
   - Columns committed in Products sub-chapter are excluded from Dates and Customers dropdowns
   - Columns committed in Customers sub-chapter are excluded from Dates and Products dropdowns
   - Within Products, columns used in pending filters are excluded from the Filter Columns dropdown

3. **State Lifecycle**:
   - Column becomes "committed" when user clicks Refresh Dataset
   - Committed state is cleared when user changes the selection (before re-committing)
   - All committed states reset when wizard is closed or reset

4. **Implementation Functions**:
   - `isColumnCommittedInAnyFilter(columnName)`: Checks all committed states across Dates, Customers, and Products sub-chapters
   - `isColumnUsedInFilters(columnName)`: Checks pending state within Products sub-chapter
   - `isColumnUsedInCustomerFilters(columnName)`: Checks pending state within Customers sub-chapter
   - `getAvailableFilterColumns()`: Filters out both committed and pending columns (for Products)
   - `getAvailableCustomerFilterColumns()`: Filters out both committed and pending columns (for Customers)

5. **Column Type Distinction**:
   - **Grouping columns** (e.g., `customer_id`, `product_id`): Used for GROUP BY - NOT excluded from other filters
   - **Aggregation columns** (e.g., `amount` in SUM, `revenue` in revenue threshold): EXCLUDED after first use
   - **Filter columns** (category equals, numeric range, date range): EXCLUDED after first use

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
   │ Filter Type: ○ Range  ○ Greater than  ○ Less than  ○ Equals  ○ Not Equals │
   │                                                                     │
   │ Min: [10        ]    Max: [500       ]                              │
   │ ☑ Include NULL values                                               │
   │                                              [Apply]  [Cancel]      │
   └─────────────────────────────────────────────────────────────────────┘
   ```
   - Shows column statistics (min, max, null percentage)
   - Filter types: Range, Greater than, Less than, Equals, Not Equals
   - Min/Max inputs for range, single value for greater_than/less_than/equals
   - NULL handling checkbox
   - Apply button adds the filter and closes modal

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
│ Create Dataset - Step 4 of 4: Filtering                                      │
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
│                                     [← Back]  [Cancel]  [Save Dataset]      │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Validation Requirements for Step 4 (Final Step):**
- At least one filter must be configured (date, customer, or product)
- If date filter is used, timestamp column must be selected
- If product top revenue filter is used, product and revenue columns must be selected and analysis must run successfully
- If customer top revenue filter is used, customer and revenue columns must be selected and analysis must run successfully
- **Save button appears on Step 4** (this is now the final step)

**Note on Train/Eval Split:**
Train/eval split configuration has been moved to the **Training domain**. This aligns with TFX architecture where BigQueryExampleGen handles data splitting. When launching a training run, users will configure:
- Split strategy (time-based or random)
- Split parameters (eval days or train percentage)

The dataset only defines WHAT data to use, not HOW to split it for training.

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

    # BigQuery location
    # IMPORTANT: BigQuery datasets are region-locked. Queries must be executed
    # in the same region where the data resides. This field stores the region
    # detected when the dataset is first created, ensuring all subsequent
    # queries use the correct location.
    bq_location = models.CharField(
        max_length=50,
        default='US',
        help_text="BigQuery region where the dataset exists (e.g., 'US', 'EU', 'europe-central2')"
    )

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
    #   "date_filter": {"column": "trans_date", "type": "rolling", "days": 90},
    #   "product_filter": {"top_revenue": {...}, "category_filters": [...], ...},
    #   "customer_filter": {"top_revenue": {...}, "aggregation_filters": [...], ...}
    # }

    # NOTE: split_config has been REMOVED
    # Train/eval split is now handled by the Training domain (TFX ExampleGen)
    # This aligns with TFX architecture where data splitting is an execution-time concern

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

    # Summary snapshot from wizard Step 4 (for View modal)
    summary_snapshot = models.JSONField(default=dict)
    # Saved when dataset is created/updated, displayed in View modal
    # Example:
    # {
    #   "total_rows": 8233,
    #   "filters_applied": {
    #       "dates": {"type": "rolling", "days": 30, "column": "trans_date"},
    #       "customers": {"type": "multiple", "count": 1, "filters": [...]},
    #       "products": {"type": "multiple", "count": 1, "filters": [...]}
    #   },
    #   "column_stats": {
    #       "customers.customer_id": {"type": "INTEGER", "min": 59, "max": 999900},
    #       ...
    #   },
    #   "snapshot_at": "2024-12-07T10:30:00Z"
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
    Immutable snapshot of a dataset configuration.
    Created when a dataset is used in a training run.
    Ensures full reproducibility of training data.
    """
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()  # Auto-incremented

    # Snapshot of configuration at time of use
    config_snapshot = models.JSONField()  # Full copy of dataset config (frozen)

    # Generated SQL query with resolved dynamic values
    generated_query = models.TextField()  # The actual SQL used for this training run
    # Example: "SELECT ... WHERE trans_date >= '2024-09-07'" (dates resolved)

    # Execution context
    execution_date = models.DateTimeField()  # When this version was created

    # Stats at time of snapshot
    actual_row_count = models.BigIntegerField(null=True)
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
              "filter_type": {"enum": ["range", "greater_than", "less_than", "equals", "not_equals"]},
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
| GET | `/api/datasets/{dataset_id}/summary/` | Get dataset summary + snapshot for View modal |

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
        (Used by Modeling domain)
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
- **Modeling Domain**: Uses Dataset to create Feature Configs
- **Training Domain**: Uses Dataset definition for ExampleGen

---

## Related Documentation

- [Implementation Overview](../implementation.md)
- [Modeling Phase](phase_modeling.md)
- [Training Phase](phase_training.md)

---

## Changelog

### v16 (2025-12-29) - Feature Config Wizard Column Aliases Fix

**Bug Fixed:** Column aliases were not displaying in the Feature Config wizard's "Available Columns" panel.

**Problem Description:**
While v15 fixed column aliases display in the Dataset View modal and other UI locations, the Feature Config wizard (Step 2 - "Available Columns") was still showing original BigQuery column names instead of user-defined aliases.

**Example:**
- Dataset View modal (correct): Shows `sub_category`, `category`
- Feature Config wizard (broken): Shows `division_desc`, `mge_cat_desc`

**Root Cause:**
The `get_schema_with_sample()` API endpoint in `ml_platform/configs/api.py` was not updated in v15. It was missing:
1. `column_aliases` retrieval from the dataset
2. `display_name` field for each column
3. The suffix-matching fallback logic to handle key format mismatches

**Files Modified:**

1. **Backend API** (`ml_platform/configs/api.py`):
   - Added `column_aliases = dataset.column_aliases or {}` to retrieve aliases
   - Added `get_display_name()` helper function with suffix-matching fallback
   - Added `display_name` field to each column in the response
   - Added `column_aliases` to the response data

**Technical Details:**

The key fix was adding the suffix-matching fallback that searches through all `column_aliases` keys:

```python
def get_display_name(col_name):
    """Get display name from column_aliases, trying multiple key formats."""
    if not column_aliases:
        return col_name
    # Try direct match
    if column_aliases.get(col_name):
        return column_aliases[col_name]
    # Try with table prefix formats (dot and underscore)
    for table in (dataset.selected_columns or {}).keys():
        full_key = f"{table}.{col_name}"
        underscore_key = full_key.replace('.', '_')
        if column_aliases.get(full_key):
            return column_aliases[full_key]
        if column_aliases.get(underscore_key):
            return column_aliases[underscore_key]
    # Fallback: search all aliases for keys ending with the column name
    for key, alias in column_aliases.items():
        if key.endswith(col_name) or key.endswith(f'.{col_name}') or key.endswith(f'_{col_name}'):
            return alias
    return col_name
```

The suffix-matching fallback is critical because:
- Column names from BigQuery result are plain names: `division_desc`
- But `column_aliases` keys may have table prefixes: `raw_data.tablename.division_desc` or `raw_data_tablename_division_desc`

**Verification:**
After fix, the Feature Config wizard "Available Columns" panel correctly shows aliased names like `sub_category` and `category` instead of original BQ names.

---

### v15 (2025-12-29) - Column Aliases Display Fix

**Bug Fixed:** Column aliases (renamed columns) were not displaying correctly throughout the system.

**Problem Description:**
Users could rename verbose column names (e.g., `tfrs_training_examples.customer_id` → `customer_id`) in the Schema Builder (Step 3), but the aliases would not appear in:
1. The View modal showing saved dataset configuration
2. Various other UI locations across the system

**Root Causes Identified:**

1. **View Modal API Gap**: The `get_dataset_summary` API endpoint was not returning `column_aliases` field. The frontend expected `summary.column_aliases` but the API never sent it.

2. **Key Format Mismatch**: Even after adding `column_aliases` to the API, the View modal's `getDisplayName()` function did a simple direct lookup, but there was a format mismatch:
   - `column_stats` keys used dot notation: `tfrs_training_examples.date`
   - `column_aliases` keys used underscore notation: `tfrs_training_examples_date`

3. **State Reset Bug (already fixed in Phase 1)**: The `loadSchemaBuilder()` function was resetting `schemaBuilderState` without preserving `columnAliases` when editing existing datasets.

**Files Modified:**

1. **Backend API** (`ml_platform/datasets/api.py`):
   - Added `column_aliases` to `get_dataset_summary()` response (line 1060)
   - Added `column_aliases` to `clone_dataset()` to preserve aliases when cloning
   - Added `columns_with_display_names` to `serialize_dataset()` for convenience
   - Updated `get_dataset_columns()` in configs API to return `display_name` field

2. **Backend Services** (`ml_platform/datasets/services.py`):
   - Added `apply_column_aliases()` helper function for consistent alias application

3. **Frontend Dataset Wizard** (`templates/ml_platform/model_dataset.html`):
   - Fixed `loadSchemaBuilder()` to preserve `columnAliases` in edit mode
   - Updated View modal's `getDisplayName()` to try multiple key formats (dot and underscore)
   - Updated filter dropdowns and displays to use `getColumnDisplayName()`

4. **Frontend Configs Page** (`templates/ml_platform/model_configs.html`):
   - Updated column cards, feature cards, and modals to use `display_name`

5. **Frontend Experiments Page** (`templates/ml_platform/model_experiments.html`):
   - Updated tensor breakdown functions to use `display_name`
   - Updated date/rating column dropdowns to use `display_name`

**Technical Details:**

The View modal fix required updating the `getDisplayName` helper to handle key format differences:

```javascript
// Before (broken - simple lookup):
const getDisplayName = (colName) => columnAliases[colName] || colName;

// After (fixed - tries multiple formats):
const getDisplayName = (colName) => {
    if (!columnAliases || Object.keys(columnAliases).length === 0) return colName;
    if (columnAliases[colName]) return columnAliases[colName];
    // Try underscore format (dot → underscore)
    const underscoreFormat = colName.replace(/\./g, '_');
    if (columnAliases[underscoreFormat]) return columnAliases[underscoreFormat];
    // Try dot format (underscore → dot)
    const dotFormat = colName.replace(/_/g, '.');
    if (columnAliases[dotFormat]) return columnAliases[dotFormat];
    return colName;
};
```

**Verification:**
After fix, column aliases are correctly displayed in:
- View modal column statistics table
- Schema Builder preview table (edit mode)
- Filter dropdowns in Step 4
- Model Configs page feature cards
- Experiments page tensor displays

---

### v14 (2025-12-28) - Query Generator Cross-Filter Fix

**Bug Fixed:** Generated SQL query was calculating top products/customers globally instead of respecting cross-sub-chapter filters.

**Problem Description:**
While v13 fixed the UI analysis (Pareto chart), the final generated SQL query used for training still had a bug: the `filtered_data` CTE only included the date filter, not category/numeric filters from other sub-chapters. This meant top products/customers were calculated from all data, not the filtered subset.

**Example:**
1. User applies 60-day rolling window in Dates sub-chapter
2. User filters by city = 'CHERNIGIV' in Customers sub-chapter
3. User enables Top 80% products by revenue in Products sub-chapter
4. User saves the dataset
5. **Before fix:** Top 80% products calculated from ALL cities (4,554 products), then city filter applied → 87% revenue coverage
6. **After fix:** Top 80% products calculated from CHERNIGIV only (1,054 products) → 80% revenue coverage (as expected)

**Impact:**
| Metric | Before (Bug) | After (Fixed) |
|--------|--------------|---------------|
| Products in top 80% | 4,554 (global) | 1,054 (CHERNIGIV) |
| Total rows | 107,692 | 88,082 |
| Revenue coverage | 86.98% | 80.01% |

**Root Cause:**
In `BigQueryService.generate_query()`, the `filtered_data` CTE was only applying the date filter:
```python
# Before (buggy):
filtered_data_cte = f"... WHERE {date_filter_clause}"
```

The category/numeric filters from `customer_filter` and `product_filter` were only applied in the final WHERE clause, AFTER the top products/customers CTEs were calculated.

**Files Modified:**

1. **Backend Services** (`ml_platform/datasets/services.py`):
   - Added `_build_cross_filter_where_clauses()` helper method (lines 884-1031)
   - Modified `filtered_data` CTE construction to include all cross-sub-chapter filters (lines 1193-1213)
   - Updated `_generate_product_filter_clauses_v2()` with `skip_row_filters` parameter
   - Updated `_generate_customer_filter_clauses_v2()` with `skip_row_filters` parameter

**Technical Details:**

Before fix - Generated query structure:
```sql
WITH filtered_data AS (
    SELECT ... WHERE date >= ...  -- Only date filter!
),
top_products AS (
    ... FROM filtered_data ...    -- Calculated from ALL cities
)
SELECT ... WHERE product_id IN (...) AND city IN ('CHERNIGIV')  -- Too late!
```

After fix - Generated query structure:
```sql
WITH filtered_data AS (
    SELECT ... WHERE date >= ... AND city IN ('CHERNIGIV')  -- All filters applied
),
top_products AS (
    ... FROM filtered_data ...    -- Correctly scoped to CHERNIGIV
)
SELECT ... WHERE product_id IN (...)  -- No duplicate filter
```

**Verification:**
Test query in `sql/chernigiv_verification.sql` confirms the fix works correctly.

---

### v13 (2025-12-28) - Cross-Sub-Chapter Filter Fix

**Bug Fixed:** Top Products/Customers analysis was ignoring filters from other sub-chapters.

**Problem Description:**
When users applied filters in one sub-chapter (e.g., city = 'VINNYTSYA' in Customers) and then ran "Top Products" analysis, the analysis would run against the full dataset instead of the filtered subset.

**Example:**
1. User applies 30-day rolling window in Dates sub-chapter
2. User filters by city = 'VINNYTSYA' in Customers sub-chapter
3. User clicks "Refresh Dataset" to commit the customer filter
4. User opens "Top Products" modal and clicks "Analyze"
5. **Before fix:** Analysis shows total products from entire dataset (ignoring city filter)
6. **After fix:** Analysis shows only products sold in VINNYTSYA within the date range

**Root Cause:**
The `analyzeProductRevenue()` and `analyzeCustomerRevenue()` frontend functions were not passing committed filters from other sub-chapters to the backend API. The backend services only applied the date filter, ignoring customer/product category filters.

**Files Modified:**

1. **Frontend** (`templates/ml_platform/model_dataset.html`):
   - Added `getCommittedFiltersForAnalysis()` helper function to collect all committed filters
   - Updated `analyzeProductRevenue()` to pass committed date and customer filters
   - Updated `analyzeCustomerRevenue()` to pass committed date and product filters

2. **Backend API** (`ml_platform/datasets/api.py`):
   - Updated `analyze_product_revenue` endpoint to accept `filters` parameter
   - Updated `analyze_customer_revenue` endpoint to accept `filters` parameter

3. **Backend Services** (`ml_platform/datasets/services.py`):
   - Updated `ProductRevenueAnalysisService.analyze_distribution()` to apply customer category/numeric filters
   - Updated `ProductRevenueAnalysisService._get_distribution_curve()` to apply same filters
   - Updated `CustomerRevenueAnalysisService.analyze_distribution()` to apply product and customer filters
   - Fixed distribution curve sampling to guarantee inclusion of 70%, 80%, 90%, 95%, 100% threshold points

**Additional Bug Fixed:**
The distribution curve query was using `ORDER BY rank LIMIT 100` which cut off data before reaching the 80% revenue threshold. Fixed by using a `threshold_points` CTE to explicitly find and include threshold crossing points.

**Technical Details:**

Filter flow after fix:
```
Frontend: getCommittedFiltersForAnalysis()
    ↓
Collects: datesFilterState.committed + customerFiltersState.committed + productFiltersState.committed
    ↓
API: analyze-product-revenue/ receives filters parameter
    ↓
Service: ProductRevenueAnalysisService.analyze_distribution(filters=filters)
    ↓
SQL: WHERE clause includes date filter AND customer category filters
```

Example generated WHERE clause:
```sql
WHERE `tfrs_training_examples`.`date` >= DATE_SUB(
        (SELECT MAX(`date`) FROM `b2b-recs.raw_data.tfrs_training_examples`),
        INTERVAL 30 DAY
    )
  AND `tfrs_training_examples`.`city` IN ('VINNYTSYA')
```
