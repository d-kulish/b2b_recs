# Datasets Domain Implementation Plan

**Created**: 2025-12-01
**Phase**: Datasets (Phase 2 of ML Platform)
**Reference**: `docs/phase_datasets.md`
**Last Updated**: 2025-12-01

---

## Current Status: Phases 1-5 Complete ✅

Backend implementation is complete. Ready for Phase 6 (User Interface).

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Foundation (Models, Sub-App Structure) |
| Phase 2 | ✅ Complete | Basic CRUD Operations |
| Phase 3 | ✅ Complete | BigQuery Integration |
| Phase 4 | ✅ Complete | Dataset Analysis |
| Phase 5 | ✅ Complete | Query Generation |
| Phase 6 | 🔲 Next | User Interface |
| Phase 7 | 🔲 Pending | Navigation Integration (mostly done) |
| Phase 8 | 🔲 Pending | Testing |

---

## Overview

The Datasets domain defines **WHAT data** goes into model training:
- Select source tables from BigQuery (populated by ETL)
- Map columns to ML concepts (user_id, product_id, timestamp, etc.)
- Define data filters (date range, revenue threshold, customer filters)
- Configure train/eval split strategy

**Key Output**: A Dataset definition (JSON stored in Django) used by TFX ExampleGen.

---

## Confirmed Design Decisions

Based on clarification with stakeholder (2025-12-01):

| Decision | Choice | Notes |
|----------|--------|-------|
| **Table Source** | `raw_data.*` only | Limit to ETL output dataset |
| **Column Mapping** | Flexible/Custom | Users can select ANY columns they need |
| **Multi-Table Joins** | Auto + Manual | Auto-detect FK joins + manual override option |
| **Status Workflow** | Draft → Active | Simple 2-state workflow for now |
| **Statistics Cost** | Full table scan | Accurate stats, higher BQ cost acceptable |
| **Navigation** | Existing page | Use `model_dataset.html` (already in sidebar) |

---

## Implementation Results

### Phase 1: Foundation ✅

**Files Created:**
- `ml_platform/datasets/__init__.py` - Sub-app initialization
- `ml_platform/datasets/urls.py` - All dataset routes
- `ml_platform/datasets/views.py` - Page view (model_dataset)
- `ml_platform/datasets/api.py` - REST API endpoints
- `ml_platform/datasets/services.py` - BigQuery integration service

**Models Added to `ml_platform/models.py`:**
- `Dataset` - Main dataset configuration model
- `DatasetVersion` - For reproducibility tracking

**Database Migration:** Applied successfully

### Phase 2: Basic CRUD ✅

**Implemented APIs:**
- `GET /api/models/{model_id}/datasets/` - List with pagination, search, status filter
- `POST /api/models/{model_id}/datasets/create/` - Create with validation
- `POST /api/models/{model_id}/datasets/check-name/` - Real-time name availability check
- `GET /api/datasets/{dataset_id}/` - Get with version history
- `POST /api/datasets/{dataset_id}/update/` - Update with validation, cache clearing
- `POST /api/datasets/{dataset_id}/delete/` - Delete with version protection
- `POST /api/datasets/{dataset_id}/clone/` - Clone dataset
- `POST /api/datasets/{dataset_id}/activate/` - Change status to active

**Helper Functions:**
- `serialize_dataset()` - Consistent JSON serialization
- `validate_dataset_config()` - Configuration validation

### Phase 3: BigQuery Integration ✅

**Service Methods:**
- `list_tables()` - List raw_data.* tables with metadata (row_count, size_mb, column_count)
- `get_table_schema()` - Schema with ML role suggestions and join key detection
- `get_column_stats()` - Full table scan statistics (cardinality, min/max/mean/stddev, uniqueness, range_days)
- `get_sample_values()` - Sample distinct values for columns
- `detect_join_keys()` - Auto-detect joins with scoring and confidence levels
- `suggest_columns()` - ML concept column suggestions
- `validate_query()` - Dry-run query validation with cost estimate

**Constants Added:**
- `ML_COLUMN_PATTERNS` - Regex patterns for user_id, product_id, timestamp, revenue detection
- `JOIN_KEY_PATTERNS` - Patterns for identifying potential join keys
- `HIGH_VALUE_JOIN_COLS` - Common join column names

**APIs:**
- `GET /api/models/{model_id}/bq-tables/` - List BigQuery tables
- `GET /api/models/{model_id}/bq-tables/{table}/schema/` - Get table schema
- `GET /api/models/{model_id}/bq-tables/{table}/stats/` - Get column statistics
- `GET /api/models/{model_id}/bq-tables/{table}/columns/{column}/samples/` - Get sample values
- `POST /api/models/{model_id}/detect-joins/` - Auto-detect join keys
- `POST /api/models/{model_id}/suggest-columns/` - Get ML column suggestions

### Phase 4: Dataset Analysis ✅

**Service Methods:**
- `analyze_dataset()` - Full dataset analysis with row/user/product counts, date range
- `preview_dataset()` - Sample data preview with ML role annotations

**API Helper Functions:**
- `calculate_split_estimates()` - Estimate train/eval split sizes for time-based and random strategies
- `calculate_quality_metrics()` - Data quality scoring with issue detection

**Quality Metrics Detected:**
- Low user engagement
- Sparse product coverage
- Cold start issues (few users/products)
- Extreme data sparsity
- Short date range

**APIs:**
- `POST /api/datasets/{dataset_id}/analyze/` - Analyze with split estimates and quality metrics
- `GET /api/datasets/{dataset_id}/preview/` - Preview sample data
- `GET /api/datasets/{dataset_id}/summary/` - Get cached summary (no BQ query)
- `POST /api/models/{model_id}/datasets/compare/` - Compare 2-5 datasets side-by-side

### Phase 5: Query Generation ✅

**Service Methods:**
- `generate_query()` - Main query generation with optional split parameter
- `_generate_split_clause()` - Train/eval split WHERE clause
  - Time-based: `DATE_SUB(CURRENT_DATE(), INTERVAL N DAY)`
  - Random: `FARM_FINGERPRINT` for reproducible hash-based splitting
- `_generate_top_products_cte()` - CTE for top N% products by revenue using window functions
- `_generate_active_users_cte()` - CTE for users with minimum transactions
- `generate_train_query()` - Convenience method for training data
- `generate_eval_query()` - Convenience method for evaluation data
- `generate_tfx_queries()` - TFX ExampleGen-ready query configuration

**APIs:**
- `GET /api/datasets/{dataset_id}/query/` - Get generated SQL with optional split parameter
- `GET /api/datasets/{dataset_id}/query/split/` - Get both train and eval queries
- `GET /api/datasets/{dataset_id}/query/tfx/` - Get TFX-formatted queries
- `POST /api/datasets/{dataset_id}/validate-query/` - Validate query (dry run)

**Query Features:**
- Rolling or fixed date range filters
- Top N% products by revenue (CTE with running total)
- Minimum transactions per customer (CTE with HAVING clause)
- Time-based or random train/eval split
- Multi-table JOINs with configurable join types
- Column aliasing for ML concept names

---

## API Endpoints Summary (All Implemented)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| GET | `/models/{id}/dataset/` | Page view | ✅ |
| GET | `/api/models/{id}/datasets/` | List datasets | ✅ |
| POST | `/api/models/{id}/datasets/create/` | Create dataset | ✅ |
| POST | `/api/models/{id}/datasets/check-name/` | Check name availability | ✅ |
| GET | `/api/datasets/{id}/` | Get dataset | ✅ |
| POST | `/api/datasets/{id}/update/` | Update dataset | ✅ |
| POST | `/api/datasets/{id}/delete/` | Delete dataset | ✅ |
| POST | `/api/datasets/{id}/clone/` | Clone dataset | ✅ |
| POST | `/api/datasets/{id}/activate/` | Activate dataset | ✅ |
| GET | `/api/models/{id}/bq-tables/` | List BigQuery tables | ✅ |
| GET | `/api/models/{id}/bq-tables/{table}/schema/` | Get table schema | ✅ |
| GET | `/api/models/{id}/bq-tables/{table}/stats/` | Get column statistics | ✅ |
| GET | `/api/models/{id}/bq-tables/{table}/columns/{col}/samples/` | Get sample values | ✅ |
| POST | `/api/models/{id}/detect-joins/` | Detect join keys | ✅ |
| POST | `/api/models/{id}/suggest-columns/` | Suggest ML columns | ✅ |
| POST | `/api/datasets/{id}/analyze/` | Analyze dataset | ✅ |
| GET | `/api/datasets/{id}/preview/` | Preview data | ✅ |
| GET | `/api/datasets/{id}/summary/` | Get cached summary | ✅ |
| GET | `/api/datasets/{id}/query/` | Get generated SQL | ✅ |
| GET | `/api/datasets/{id}/query/split/` | Get train/eval queries | ✅ |
| GET | `/api/datasets/{id}/query/tfx/` | Get TFX queries | ✅ |
| POST | `/api/datasets/{id}/validate-query/` | Validate query | ✅ |
| POST | `/api/models/{id}/datasets/compare/` | Compare datasets | ✅ |

---

## Next Steps: Phase 6 (User Interface)

### 6.1 Update `model_dataset.html` Template

The template should include:

1. **Dataset List Section**
   - Cards showing existing datasets (name, status, table count, row estimate)
   - Status badges (Draft/Active)
   - Action buttons (View, Edit, Clone, Delete)
   - "New Dataset" button to open wizard

2. **4-Step Wizard Modal**
   - **Step 1: Basic Info**
     - Name input with real-time availability check
     - Description textarea
   - **Step 2: Source Tables**
     - List of `raw_data.*` tables from BigQuery
     - Primary table selection (required)
     - Secondary tables (optional, checkboxes)
     - Auto-detected joins with override option
   - **Step 3: Column Selection & Mapping**
     - Columns from all selected tables
     - Checkbox selection for each column
     - ML role mapping (user_id, product_id, timestamp, revenue)
     - Column statistics display (type, cardinality, nulls)
   - **Step 4: Filters & Split**
     - Date range: Rolling (months) or Fixed (start/end dates)
     - Product filter: Top N% by revenue (optional)
     - Customer filter: Minimum transactions (optional)
     - Split strategy: Time-based (eval_days) or Random (train_percent)

3. **Dataset Detail Panel**
   - Configuration summary
   - Cached analysis results
   - Generated SQL preview
   - Edit/Clone/Activate/Delete actions

### 6.2 JavaScript Requirements

Create `static/js/datasets.js` with:

```javascript
// Key functions needed:
- loadDatasets()           // Fetch and render dataset list
- openWizard(mode, datasetId)  // Open create/edit wizard
- loadBqTables()           // Fetch tables for Step 2
- loadTableSchema(table)   // Fetch schema for Step 3
- detectJoins(tables)      // Auto-detect joins
- suggestColumns(tables)   // Get ML suggestions
- validateStep(step)       // Validate current step
- saveDataset()            // Create/update dataset
- analyzeDataset(id)       // Run analysis
- previewQuery(id)         // Show generated SQL
```

### 6.3 CSS (Reuse Existing)

- `static/css/cards.css` - Dataset cards styling
- `static/css/modals.css` - Wizard modal styling

### 6.4 Reference Implementation

Follow the patterns from:
- `templates/ml_platform/model_etl.html` - ETL wizard structure
- `static/js/etl-wizard.js` - ETL wizard JavaScript

---

## Files Summary

### Created Files ✅
- `ml_platform/datasets/__init__.py`
- `ml_platform/datasets/urls.py`
- `ml_platform/datasets/views.py`
- `ml_platform/datasets/api.py`
- `ml_platform/datasets/services.py`

### Modified Files ✅
- `ml_platform/models.py` - Added Dataset, DatasetVersion models
- `ml_platform/urls.py` - Included datasets sub-app URLs
- `ml_platform/views.py` - Removed placeholder model_dataset view

### Pending Files (Phase 6)
- `templates/ml_platform/model_dataset.html` - Replace placeholder with full UI
- `static/js/datasets.js` - Create wizard JavaScript (optional, can be inline)

---

## Testing Results

All tests passing:
- Django system check: No issues
- URL routing: All 23 endpoints correctly configured
- Query generation: All 6 test cases passing
  - Basic query with CTEs
  - Time-based train/eval split
  - Random (hash-based) split with FARM_FINGERPRINT
  - Top products CTE structure
  - Active users CTE structure
  - TFX query format

---

## Notes

- Follow the exact patterns established in `ml_platform/etl/` sub-app
- Use the same CSS classes from `cards.css` and `modals.css`
- Use 4-step wizard (not 5) since Datasets is simpler than ETL
- Keep the wizard modal at fixed height (580px) like ETL wizard
- Column selection is FLEXIBLE - users can select ANY columns
- Auto-join detection should suggest joins but allow manual override
- Full table scans for statistics are acceptable for accuracy
- Only show tables from `raw_data.*` BigQuery dataset
