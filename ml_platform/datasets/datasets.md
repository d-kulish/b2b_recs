# Dataset Manager

**Last Updated:** December 8, 2025
**Status:** Production Ready ✅ | Visual Schema Builder ✅ | TFX Query Generation ✅ | Edit-time Versioning ✅ | Product Metrics ✅ | View SQL ✅

Django-based dataset configuration system for defining ML training data from BigQuery tables. Part of the B2B Recommendations Platform.

---

## Overview

The Dataset Manager enables users to:
- **Select** source tables from BigQuery (`raw_data.*` dataset populated by ETL)
- **Join** multiple tables with auto-detected or manual join configuration
- **Map** columns to ML concepts (user_id, product_id, revenue)
- **Filter** data (top N% products by revenue, minimum transactions per customer)
- **Split** data for training/evaluation (random hash-based splitting)
- **Generate** SQL queries ready for TFX ExampleGen component

**Architecture:**
```
Dataset Manager UI (Django Template)
    ↓
REST API (27 endpoints)
    ├── Dataset CRUD operations
    ├── BigQuery metadata (tables, schemas, statistics)
    ├── Visual Schema Builder (preview service)
    └── Query generation (full, split, TFX)
    ↓
BigQuery (raw_data.* tables)
```

---

## Key Features

### **1. Visual Schema Builder (Power BI-style)**

Interactive drag-and-drop interface for configuring table joins:

- **Draggable Table Cards**: Each table appears as a movable card with columns listed
- **Connection Lines**: Visual curved lines show join relationships between tables
- **Color-coded Joins**: Each join has a unique color for clarity
- **Live Preview**: See sample data from the joined result in real-time
- **Click-to-Connect**: Click on a column in one table, then another to create joins
- **Auto-detect Joins**: System suggests joins based on column naming patterns

**Seeded Sampling:**
- Primary table sampled randomly (100 rows)
- Secondary tables filtered by foreign key values from primary
- Ensures preview shows actual joinable data, not random mismatches

### **2. ML Column Mapping**

Map any columns to ML concepts:
- `user_id` - Customer/user identifier
- `product_id` - Product/item identifier
- `revenue` - Transaction value/amount

**Auto-suggestions** based on column name patterns:
- `customer_id`, `user_id`, `client_id` → user_id
- `product_id`, `item_id`, `sku` → product_id
- `revenue`, `amount`, `total`, `price` → revenue

### **3. Data Filters**

**Date Filters:**
- Rolling window (last N days from MAX date in dataset)
- Fixed start date (all data from a specific date)
- Uses TIMESTAMP_SUB for rolling windows

**Top N% Products by Revenue:**
- Uses CTE with window functions for running totals
- Filters to products representing top N% of total revenue
- Example: Top 20% products = ~80% of revenue (Pareto principle)

**Product Metrics Filters:**
- Transaction Count Filter: Products with COUNT(*) > N transactions
- Revenue Filter: Products with SUM(amount) > N total revenue
- Both use GROUP BY product_id with HAVING clause

**Top N% Customers by Revenue:**
- Same Pareto-based filtering as products
- Filters to customers representing top N% of total revenue

**Customer Metrics Filters:**
- Transaction Count Filter: Customers with COUNT(*) > N transactions
- Spending Filter: Customers with SUM(amount) > N total spending
- Both use GROUP BY customer_id with HAVING clause

**Category/Numeric/Date Column Filters:**
- Category: Include/exclude specific values (IN / NOT IN)
- Numeric: Range, greater than, less than, equals
- Date: Relative (last N days) or fixed date range

### **4. Train/Eval Split**

**Random Split (FARM_FINGERPRINT):**
- Deterministic hash-based splitting
- Configurable split ratio (default 80/20)
- Reproducible across runs

**Split Query Generation:**
```sql
-- Training data (80%)
WHERE MOD(ABS(FARM_FINGERPRINT(CAST(user_id AS STRING))), 100) < 80

-- Evaluation data (20%)
WHERE MOD(ABS(FARM_FINGERPRINT(CAST(user_id AS STRING))), 100) >= 80
```

### **5. Data Quality Metrics**

Automated analysis with issue detection:
- Low user engagement (avg < 3 items/user)
- Sparse product coverage (< 20% products have interactions)
- Cold start issues (< 100 unique users or products)
- Extreme data sparsity (< 0.01% density)

---

## 4-Step Wizard Flow

### **Step 1: Basic Information**
- Dataset name (with real-time availability check)
- Description (optional)

### **Step 2: Source Tables**
- Select primary table from `raw_data.*`
- Add secondary tables for joins
- Configure join types (INNER, LEFT, RIGHT, FULL)
- Auto-detect or manually configure join keys

### **Step 3: Visual Schema Builder**
- Drag tables to arrange layout
- Visual connection lines between joined tables
- Column checkboxes for selection
- Live preview of resulting dataset
- ML column mapping (user_id, product_id, revenue)

### **Step 4: Filters**
Three collapsible sub-chapters:

**Dates Sub-chapter:**
- Select timestamp column
- Rolling window (last N days) OR fixed start date
- Refresh Dataset button to apply

**Customers Sub-chapter:**
- Top Customers: Filter by cumulative revenue (Pareto)
- Customer Metrics: Transaction count filter, Spending filter
- Filter Columns: Category, numeric, date filters
- Refresh Dataset button to apply

**Products Sub-chapter:**
- Top Products: Filter by cumulative revenue (Pareto)
- Product Metrics: Transaction count filter, Revenue filter
- Filter Columns: Category, numeric, date filters
- Refresh Dataset button to apply

**Dataset Summary Panel:**
- Shows total rows with applied filters
- Column statistics (min/max/avg/unique)
- Updates on each Refresh Dataset click

---

## API Endpoints (27 Total)

### **Dataset CRUD**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{id}/datasets/` | List datasets with pagination |
| POST | `/api/models/{id}/datasets/create/` | Create new dataset |
| POST | `/api/models/{id}/datasets/check-name/` | Check name availability |
| GET | `/api/datasets/{id}/` | Get dataset details |
| POST | `/api/datasets/{id}/update/` | Update dataset |
| POST | `/api/datasets/{id}/delete/` | Delete dataset |
| POST | `/api/datasets/{id}/clone/` | Clone dataset |

### **BigQuery Integration**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/{id}/bq-tables/` | List BigQuery tables |
| GET | `/api/models/{id}/bq-tables/{table}/schema/` | Get table schema |
| GET | `/api/models/{id}/bq-tables/{table}/stats/` | Get column statistics |
| GET | `/api/models/{id}/bq-tables/{table}/columns/{col}/samples/` | Get sample values |
| POST | `/api/models/{id}/detect-joins/` | Auto-detect join keys |
| POST | `/api/models/{id}/suggest-columns/` | Suggest ML columns |

### **Dataset Preview & Summary**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/datasets/{id}/preview/` | Preview sample data |
| GET | `/api/datasets/{id}/summary/` | Get cached summary |
| POST | `/api/models/{id}/datasets/compare/` | Compare 2-5 datasets |

### **Query Generation**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/datasets/{id}/query/` | Get generated SQL |
| GET | `/api/datasets/{id}/query/split/` | Get train/eval queries |
| GET | `/api/datasets/{id}/query/tfx/` | Get TFX-formatted queries |
| POST | `/api/datasets/{id}/validate-query/` | Validate query (dry run) |

### **Visual Schema Builder**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/models/{id}/datasets/load-samples/` | Load table samples |
| POST | `/api/models/{id}/datasets/preview/` | Generate join preview |
| POST | `/api/models/{id}/datasets/detect-joins-preview/` | Auto-detect joins for preview |
| POST | `/api/models/{id}/datasets/cleanup-session/` | Cleanup cached session |

---

## File Structure

```
ml_platform/datasets/
├── __init__.py           # Sub-app initialization
├── urls.py               # URL routing (27 endpoints)
├── views.py              # Page view (model_dataset)
├── api.py                # REST API endpoints
├── services.py           # BigQuery integration service
├── preview_service.py    # Visual Schema Builder backend
└── datasets.md           # This documentation

templates/ml_platform/
└── model_dataset.html    # Full UI with 5-step wizard
```

---

## Data Model

### **Dataset Model**
```python
class Dataset(models.Model):
    model = ForeignKey(Model)          # Parent model
    name = CharField(max_length=200)   # Unique per model
    description = TextField(blank=True)

    # Source tables
    primary_table = CharField()
    secondary_tables = JSONField()     # List of additional tables
    join_config = JSONField()          # Join configuration
    selected_columns = JSONField()     # Columns per table
    column_mapping = JSONField()       # ML concept mappings
    filters = JSONField()              # Date/customer/product filters

    # Cached analysis (metadata - not versioned)
    row_count_estimate = BigIntegerField(null=True)
    unique_users_estimate = IntegerField(null=True)
    unique_products_estimate = IntegerField(null=True)
    summary_snapshot = JSONField()     # Step 4 summary for View modal

    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

### **DatasetVersion Model**

Automatic versioning is implemented to track configuration changes:
- **Version 1** is created when a dataset is first saved
- **New versions** are created each time the dataset configuration is edited
- Only **configuration fields** are versioned (not metadata/statistics)

```python
class DatasetVersion(models.Model):
    dataset = ForeignKey(Dataset)
    version_number = IntegerField()       # Auto-incremented (starts at 1)
    config_snapshot = JSONField()         # Full config at this version
    actual_row_count = BigIntegerField()  # Row count at time of version
    actual_unique_users = IntegerField()  # Unique users at time of version
    actual_unique_products = IntegerField() # Unique products at time of version
    generated_query = TextField()         # Generated SQL query
    created_at = DateTimeField()
```

**Versioned Fields (config_snapshot):**
- `name`, `description`
- `primary_table`, `secondary_tables`
- `join_config`, `selected_columns`
- `column_mapping`, `filters`

**NOT Versioned (metadata - can be regenerated):**
- `summary_snapshot`, `row_count_estimate`
- `unique_users_estimate`, `unique_products_estimate`
- `column_stats`

---

## Query Generation

### **View SQL Feature**

The View modal includes a "View SQL" button that generates a production-ready SQL query from the saved dataset configuration:

- **Generates complete SQL** with all filters applied (date, products, customers)
- **Uses CTEs** (Common Table Expressions) for complex filter logic
- **Filter execution order**: Date filter first, then product/customer filters
- **Rolling windows** use MAX(date) from dataset for reproducibility
- **Copy to clipboard** for easy use in BigQuery console

### **Basic Query Structure**
```sql
WITH top_products AS (
    SELECT product_id
    FROM (
        SELECT product_id,
               SUM(revenue) as total_revenue,
               SUM(SUM(revenue)) OVER (ORDER BY SUM(revenue) DESC) as running_total,
               SUM(SUM(revenue)) OVER () as grand_total
        FROM `project.raw_data.transactions`
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.2  -- Top 20%
),
active_users AS (
    SELECT user_id
    FROM `project.raw_data.transactions`
    GROUP BY user_id
    HAVING COUNT(*) >= 3  -- Min 3 transactions
)
SELECT
    t.user_id,
    t.product_id,
    t.revenue
FROM `project.raw_data.transactions` t
INNER JOIN `project.raw_data.products` p ON t.product_id = p.id
WHERE t.product_id IN (SELECT product_id FROM top_products)
  AND t.user_id IN (SELECT user_id FROM active_users)
```

### **TFX Query Format**
```json
{
    "query": "SELECT user_id, product_id, revenue FROM ...",
    "train_query": "SELECT ... WHERE MOD(ABS(FARM_FINGERPRINT(...)), 100) < 80",
    "eval_query": "SELECT ... WHERE MOD(ABS(FARM_FINGERPRINT(...)), 100) >= 80",
    "split_column": "user_id",
    "split_ratio": 80
}
```

---

## Technical Details

### **Join Key Detection**

**Pattern Matching:**
- Column names ending in `_id`, `_key`, `_code`
- Column names starting with `id_`, `key_`
- Common names: `id`, `customer_id`, `product_id`, `user_id`

**Scoring Algorithm:**
```python
score = 0
if exact_name_match: score += 100
if same_type: score += 50
if both_unique: score += 30
if naming_pattern_match: score += 20
```

**Confidence Levels:**
- High (≥100): Exact column name match
- Medium (50-99): Type match + naming pattern
- Low (<50): Partial pattern match

### **Column Statistics**

Full table scan for accurate statistics:
- `cardinality`: COUNT(DISTINCT column)
- `null_count`: COUNTIF(column IS NULL)
- `min_value`, `max_value`: MIN/MAX
- `mean`, `stddev`: AVG/STDDEV (numeric only)
- `uniqueness`: cardinality / total_rows

### **Preview Service (Seeded Sampling)**

**Problem:** Random samples from separate tables don't join.

**Solution:**
1. Sample primary table randomly (100 rows)
2. Extract foreign key values from sample
3. Filter secondary table queries: `WHERE key IN (extracted_values)`
4. Join in pandas for preview

**Example:**
```python
# Primary: transactions (100 random rows)
# Extract: [123, 456, 789] product_ids

# Secondary: products filtered
SELECT * FROM products WHERE product_id IN (123, 456, 789)
```

---

## UI Components

### **Dataset Card**
- Name, description, status badge
- Table count, column count, row estimate
- Action buttons: View, Edit, Clone, Delete, Activate

### **Wizard Modal**
- 5-step progress bar
- Previous/Next navigation with validation
- Cancel with confirmation

### **Visual Schema Builder**
- Draggable cards with position persistence
- SVG connection lines (curved, color-coded)
- Join popover (edit/delete joins)
- Live preview table with pagination

### **Query Preview Modal**
- Full query, train query, eval query tabs
- Copy to clipboard button
- Validation status and estimated cost

---

## Status Workflow

```
Draft → Active
  │        │
  │        └── Used for training
  │
  └── Editable, not used for training
```

**Draft:** Editable configuration, not used for model training
**Active:** Locked configuration, used by TFX pipeline

---

## Integration with TFX

The Dataset Manager generates queries compatible with TFX ExampleGen:

```python
# In TFX pipeline
from tfx.components import BigQueryExampleGen

example_gen = BigQueryExampleGen(
    query=dataset.get_tfx_query()  # Generated by Dataset Manager
)
```

---

## Future Enhancements

1. **Feature Store Integration** - Connect to Vertex AI Feature Store
2. **Data Versioning** - DVC integration for dataset snapshots
3. **Streaming Datasets** - Real-time data for online inference
4. **Data Validation** - TFDV integration for schema validation
