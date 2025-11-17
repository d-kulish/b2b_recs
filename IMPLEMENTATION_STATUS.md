# ETL Wizard Step 3 & 4 Implementation Status

## ✅ COMPLETED (Backend)

1. **Data Model** ✓
   - Added new fields to DataSourceTable model:
     - `load_type` (transactional | catalog)
     - `timestamp_column`
     - `historical_start_date`
     - `selected_columns` (JSON array)
     - `schedule_type`, `schedule_time`, `schedule_day_of_week`, `schedule_day_of_month`, `schedule_cron`
   - Migration created and applied: `0011_add_load_strategy_fields.py`

2. **Connection Manager** ✓
   - Added `fetch_table_metadata()` - Routes to specific DB implementations
   - Added `fetch_table_metadata_postgresql()` - Fetches column metadata + sample data
   - Added `fetch_table_metadata_mysql()` - MySQL implementation
   - Added `fetch_table_metadata_bigquery()` - BigQuery implementation
   - Auto-detects: timestamp columns, primary keys, data types, nullability

3. **API Endpoints** ✓
   - Added `api_connection_fetch_table_preview()` in views.py
   - URL route added: `/api/connections/<id>/fetch-table-preview/`
   - Returns: columns, total_rows, recommended timestamp & PK

## ✅ COMPLETED (Frontend - Partial)

4. **HTML Structure** ✓
   - Updated progress bar: 3 steps → 4 steps
   - Added Step 3: Configure Load Strategy (full HTML)
     - Table preview container
     - Load type selection (Transactional vs Catalog)
     - Transactional config (timestamp column, historical backfill)
     - Catalog config (snapshot explanation)
   - Renamed old Step 3 → Step 4
   - Updated `updateProgress()` function to handle 4 steps

## ⚠️ IN PROGRESS (Frontend - JavaScript)

5. **JavaScript Functions - PARTIALLY COMPLETE**
   - Need to add/update:
     - `proceedToStep3()` - Fetch table preview and show Step 3
     - `fetchTablePreview()` - Call API to get table metadata
     - `renderTablePreview()` - Render columns with checkboxes
     - `onLoadTypeChange()` - Show/hide transactional vs catalog config
     - `onHistoricalRangeChange()` - Show custom date picker
     - Update `nextStep()` to handle Step 2→3 and Step 3→4 transitions
     - Update `showStep()` to handle step4
     - Update `createETLJob()` to include new fields

## ❌ NOT STARTED

6. **API Update for ETL Creation**
   - Update `api_etl_create_job()` in views.py to handle:
     - `load_type`
     - `timestamp_column`
     - `historical_start_date`
     - `selected_columns`
     - `schedule` fields

7. **Testing**
   - End-to-end wizard flow
   - Table preview rendering
   - Column selection
   - Historical backfill date calculation
   - ETL job creation with new fields

## 📋 NEXT STEPS (Priority Order)

1. Add JavaScript functions for Step 3 interactivity (30 min)
2. Update `nextStep()` navigation logic for 4 steps (10 min)
3. Update `createETLJob()` payload to include new fields (10 min)
4. Update `api_etl_create_job()` backend to save new fields (10 min)
5. Test complete flow (15 min)

**Total Estimated Time Remaining: ~75 minutes**

## 🔧 Quick Reference

**Key Files Modified:**
- `ml_platform/models.py` - DataSourceTable model
- `ml_platform/utils/connection_manager.py` - Table metadata functions
- `ml_platform/views.py` - API endpoints
- `ml_platform/urls.py` - URL routes
- `templates/ml_platform/model_etl.html` - HTML + JavaScript

**Migration:**
```bash
python manage.py migrate ml_platform
```

**New API Endpoint:**
```
POST /api/connections/<id>/fetch-table-preview/
Body: {"schema_name": "public", "table_name": "transactions"}
```
