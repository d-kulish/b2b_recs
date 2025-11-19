# Next Steps: ETL & Connection Management System

**Last Updated:** November 19, 2025

---

## 🚀 Latest Update: Flat File ETL Wizard Complete! (Nov 19, 2025)

### **✅ Completed Today:**

#### **Phase 1: Bug Fixes - Field Mapping Issues**
- **Fixed GCS bucket path bug** in file listing and schema detection APIs
  - Changed `connection.source_host` → `connection.bucket_path` (2 locations)
  - Added validation for empty/invalid bucket paths
  - Fixed connection auto-test to include `bucket_path` parameter

#### **Phase 2: Missing Dependencies**
- **Installed pandas ecosystem** for file processing
  - `pandas>=2.3.0` (Python 3.13 compatible)
  - `pyarrow>=22.0.0` (Parquet support)
  - `pandas-gbq>=0.31.0` (BigQuery integration)
- **Fixed JSON serialization** bug (numpy.bool_ → Python bool)
- **Suppressed pandas warnings** for cleaner logs

#### **Phase 3: Wizard Navigation Fix** ⭐ **MAJOR FIX**
- **Corrected wizard flow** for file sources
  - **Before:** Step 2 → Step 4 (skipped Step 3) ❌
  - **After:** Step 2 → Step 3 → Step 4 ✅
- **Created `populateFilePreviewInStep3()` function**
  - Shows file configuration summary
  - Displays detected schema in table format
  - Shows column types and sample values
- **Updated Step 3 → Step 4 navigation**
  - Transfers schema data correctly
  - Validates at least 1 column selected
  - Populates BigQuery schema editor

#### **Phase 4: Column Selection Feature** 🎉 **NEW FEATURE**
- **Implemented column selection for flat files**
  - Checkboxes for each detected column
  - "Select All" / "Deselect All" styled buttons with icons
  - Real-time selection counter ("X of Y selected")
  - Default: All columns selected
  - Validation: Requires at least 1 column
- **Upgraded database column selection** for consistency
  - Replaced text links with styled buttons
  - Added selection counter
  - Added FontAwesome icons
  - Unified UX across database and file sources

### **📊 Implementation Summary:**

**Files Modified:**
- `ml_platform/views.py` - 8 bug fixes + schema detection improvements
- `templates/ml_platform/model_etl.html` - Wizard navigation + column selection UI
- `requirements.txt` - Added pandas ecosystem dependencies

**New Functions Created:**
- `populateFilePreviewInStep3()` - File schema preview in Step 3
- `selectAllFileColumns()` / `deselectAllFileColumns()` - File column selection
- `updateFileColumnCount()` - Real-time counter for files
- `selectAllColumns()` / `deselectAllColumns()` - Database column selection
- `updateColumnCount()` - Real-time counter for databases
- `syncBigQuerySchemaFromUI()` - Sync schema from UI to validation

**Total Changes:** ~500 lines of code across backend and frontend

### **🎯 Current Status:**

✅ **Flat File ETL - Phase 1 Complete:**
- GCS connection management ✅
- File listing and pattern matching ✅
- Schema auto-detection ✅
- Column selection (NEW!) ✅
- Wizard navigation fixed ✅
- BigQuery table configuration ✅

❌ **Flat File ETL - Phase 2 Pending:**
- ETL Runner implementation for files
- File loading to BigQuery
- ProcessedFile tracking

### **📝 Next Steps (Priority Order):**

1. **Implement ETL Runner for Files** (Phase 2) - HIGH PRIORITY
   - Create file extractor for GCS/S3/Azure
   - Load files with pandas based on configuration
   - Track processed files in ProcessedFile table
   - Validate schema fingerprint on each run
   - Insert to BigQuery using pandas-gbq
   - Handle latest-only vs all-files strategy
   - **Estimated effort:** 4-6 hours

2. **End-to-End Testing** - HIGH PRIORITY
   - Test complete file ETL workflow
   - Verify column selection works correctly
   - Test with CSV, Parquet, JSON files
   - Validate BigQuery data integrity
   - **Estimated effort:** 2 hours

3. **Fix API Authentication** (Minor)
   - ETL runner getting 403 on status update endpoint
   - Currently cosmetic issue
   - **Estimated effort:** 1 hour

4. **Implement Cloud Scheduler** (Phase 3)
   - Test automated ETL job scheduling
   - **Estimated effort:** 2-3 hours

5. **Production Database Security**
   - Replace `0.0.0.0/0` with specific IP ranges or Cloud NAT
   - **Estimated effort:** 1-2 hours

---

## 🚀 Previous Update: ETL End-to-End Success! (Nov 18, 2025)

### **✅ Completed Today:**
- **FIRST SUCCESSFUL ETL RUN** 🎉
  - Connected to external Cloud SQL database (memo2 project)
  - Extracted 264 rows from PostgreSQL table
  - Loaded data to BigQuery successfully
  - Full ETL pipeline working end-to-end!

- **ETL Runner Fixes:**
  - Fixed Django API URL configuration (removed localhost default)
  - Added `pyarrow==14.0.1` dependency for BigQuery loading
  - Fixed BigQuery permissions (added `roles/bigquery.user` and `roles/bigquery.dataEditor`)
  - Updated deployment script with correct environment variables

- **Cross-Project Database Access:**
  - Configured memo2 Cloud SQL for external access (0.0.0.0/0 for testing)
  - Documented external database connection process in etl_runner.md
  - Tested connection from Cloud Run to Cloud SQL in different project

- **Previous Deployment (Earlier Today):**
  - Django deployed to Cloud Run: `https://django-app-3dmqemfmxq-lm.a.run.app`
  - New Cloud SQL Database in b2b-recs project
  - Fixed static files, Cloud SQL connection, Tailwind CDN
  - Database migrations and superuser created

### **📝 Latest Milestone: Cloud Storage Flat File Ingestion (Nov 19, 2024)**

**Status:** ✅ Phase 1 Complete - Wizard & Configuration System

- **Flat File Support Added:**
  - CSV, Parquet, JSON file ingestion from cloud storage
  - GCS support fully implemented (S3 and Azure placeholders ready)
  - Auto-schema detection from file samples using pandas
  - 1GB file size limit (pandas-based processing)
  - Glob pattern matching for file selection
  - Recursive folder scanning support

- **ETL Wizard Enhanced:**
  - Branching UI: Database vs Cloud Storage workflows
  - Step 2 file selection for cloud sources:
    - Folder path prefix (optional)
    - File pattern matching (e.g., `*.csv`, `transactions_*.parquet`)
    - Format selector with CSV options (delimiter, encoding, header)
    - Preview matching files from bucket
    - Load strategy (latest file vs all files)
    - Schema detection & preview
  - Smart navigation: Skips Step 3 for file sources (jumps 2→4)

- **Database Updates:**
  - Added 7 new fields to DataSourceTable model for file configuration
  - Created ProcessedFile model to track loaded files
  - Migration 0013 applied successfully

- **API Endpoints:**
  - `/api/connections/{id}/list-files/` - List files from bucket with pattern matching
  - `/api/connections/{id}/detect-file-schema/` - Auto-detect schema from file sample
  - Updated `/api/models/{id}/etl/create-job/` - Handle file-based configurations

- **Total Implementation:** ~1000 lines of new code across backend and frontend

**Documentation Created:**
- `docs/flat_file_etl_implementation.md` - Complete 850-line technical specification

### **📝 Next Steps:**
1. **Implement ETL Runner for Files** (Phase 2):
   - Load files with pandas based on configuration
   - Track processed files in ProcessedFile table
   - Validate schema on each run using fingerprint
   - Insert to BigQuery using pandas-gbq
   - Handle latest-only vs all-files strategy

2. **Fix API Authentication** (Minor):
   - ETL runner getting 403 on status update endpoint
   - Currently cosmetic issue - ETL works but can't report status back to Django

3. **Implement Cloud Scheduler** (Phase 3):
   - Test automated ETL job scheduling
   - Validate cron expressions and timing

4. **Production Database Security**:
   - Replace `0.0.0.0/0` with specific IP ranges or Cloud NAT
   - Current setup allows access from anywhere (testing only)

5. **Real-Time Monitoring UI** (Phase 4):
   - Show ETL run progress in real-time
   - Error alerts and notifications

### **🏗️ Infrastructure:**
- **Project**: b2b-recs (555035914949)
- **Region**: europe-central2 (Warsaw, Poland)
- **Django**: Cloud Run Service
- **Database**: Cloud SQL PostgreSQL (b2b-recs:europe-central2:b2b-recs-db)
- **ETL Runner**: Cloud Run Job
- **Secrets**: Secret Manager (django-db-password, django-secret-key)
- **Data Warehouse**: BigQuery (raw_data dataset)

---

## Current Status (Pre-Cloud Run)

- ✅ **Advanced 5-Step ETL Wizard** - Enhanced with BigQuery table setup, load strategy configuration, table preview, and column selection
- ✅ **Schema Selection** - Support for multi-schema databases (PostgreSQL, Oracle, SQL Server)
- ✅ **Load Type Differentiation** - Transactional (append-only) vs Catalog (daily snapshot)
- ✅ **Historical Backfill** - Load last 30/60/90 days on first sync, then incremental
- ✅ **Table Preview & Column Selection** - View table structure, select columns to sync
- ✅ **Smart Auto-Detection** - Automatically recommends timestamp columns and primary keys
- ✅ **Standalone Connection Management** - 2-step wizard with category tabs for independent connection creation
- ✅ **Complete Separation** - Connections managed independently from ETL jobs
- ✅ **22 Data Source Types** - Relational DBs (12), Cloud Storage (3), NoSQL (5)
- ✅ **Cloud Storage Integration** - GCS, S3, Azure Blob with storage-first architecture
- ✅ Real database connection testing (PostgreSQL, MySQL, BigQuery)
- ✅ Secure credential storage in GCP Secret Manager
- ✅ **Connection Reuse** - Select from existing connections, one connection serves multiple schemas
- ✅ **Test-First Pattern** - Connection test before save (no premature Secret Manager writes)
- ✅ **Smart Button States** - Grey→White reactive navigation, disabled states prevent errors
- ✅ **Beautiful Error Notifications** - User-friendly messages with proper formatting
- ✅ **Duplicate Detection** - Name and credential uniqueness with helpful error messages
- ✅ **Field Change Detection** - Save disabled if credentials edited after successful test
- ✅ **Atomic ETL Creation** - No draft saves until final step
- ✅ **Live Status Indicators** - Green/red/yellow dots with intelligent error handling
- ✅ **Category-Based UI** - Relational DB/Cloud Storage/NoSQL tabs with tile-based selection
- ✅ **Clean Data Model** - Removed deprecated fields from DataSource
- ✅ **Connection Tracking** - last_used_at field tracks ETL job usage
- ✅ **Professional UX** - Smooth animations, hover effects, consistent modal sizing
- ✅ **Standardized Buttons** - Consistent styling using buttons.css across all UI elements
- ✅ **Debug Logging** - Comprehensive console logs for troubleshooting connection issues
- ✅ **Manual Refresh** - Refresh button to re-test connections on demand
- ✅ **Status Timestamps** - "Tested 5m ago" display on connection cards
- ✅ **Modern Connection Cards** - Minimalistic 3-column design with optimized space usage
- ✅ **Reusable Card System** - cards.css for consistent tablet/card design across platform
- ✅ **Full Edit Functionality** - Edit connections with pre-populated fields and proper update flow
- ✅ **Multi-Machine Development** - Shared Cloud SQL database across desktop and laptop

---

## Solution Overview

**What we've built:**
1. **Standalone Connection Management** - 2-step wizard for creating connections independently
2. **Simplified ETL Wizard** - 3-step wizard to create ETL jobs (40% faster than before)
3. **Real Database Testing** - Connect to PostgreSQL, MySQL, BigQuery
4. **Secure Credentials** - Store passwords in GCP Secret Manager
5. **Atomic Creation** - No drafts, clean job creation at final step

**Standalone Connection Creation Flow:**
```
Click "+ Connection" →
Step 1: Select category (Relational DB/Files/NoSQL) + tile-based database type selection →
Step 2: Enter connection details (host, port, database, username, password, connection name) →
        Test connection (validates credentials, NO Secret Manager save yet) →
        "Save Connection" button appears after successful test →
        Click Save → Credentials saved to Secret Manager →
        Modal auto-closes, connections list reloads
```

**ETL Job Creation Flow (4 Steps):**
```
Click "+ ETL Job" →
Step 1: Select existing connection (with live status indicator) + Enter job name →
Step 2: Select schema (auto-fetched) + Select table from schema →
Step 3: Configure load strategy:
        • View table preview (columns, types, sample data)
        • Select columns to sync (with checkboxes)
        • Choose load type (Transactional vs Catalog)
        • Configure timestamp column (if transactional)
        • Set historical backfill range (30/60/90 days or custom) →
Step 4: Configure schedule (Manual/Hourly/Daily/Weekly/Monthly) + Review summary →
        Click "Create ETL Job" → Atomic creation (no drafts) →
        Connection.last_used_at updated →
        Modal closes, jobs list reloads
```

**Connection Reuse Benefits:**
```
User creates connection "Production PostgreSQL" once →
Connection saved with encrypted credentials in Secret Manager →
Next ETL job: User selects "Production PostgreSQL" at Step 1 →
Tables auto-fetched in background (no credential re-entry) →
Proceeds to Step 2 with table list ready →
Faster job creation, centralized credential management
```

---

## Milestones

### 🎯 Milestone 1: GCP Setup ✅ COMPLETE
- [x] Enable Secret Manager API ✓
- [x] GCP Project: **b2b-recs** (ID: b2b-recs, Number: 555035914949) ✓
- [x] Create service account: `django-app@b2b-recs.iam.gserviceaccount.com` ✓
- [x] Download service account JSON key to `.gcp/django-service-account.json` ✓
- [x] Set `GOOGLE_APPLICATION_CREDENTIALS` environment variable ✓
- [x] Test PostgreSQL connection details retrieved (from memo2 project) ✓
  - **Connection details saved in:** `.gcp/test-postgres-connection.md`

### 🎯 Milestone 2: PostgreSQL Connection Testing ✅ COMPLETE
- [x] Create `ml_platform/utils/connection_manager.py` ✓
- [x] Implement PostgreSQL connection test function ✓
- [x] Implement MySQL connection test function ✓
- [x] Implement BigQuery connection test function ✓
- [x] Implement Secret Manager save/retrieve functions ✓
- [x] Create wizard API endpoint: `api_etl_test_connection_wizard()` ✓
- [x] Update wizard JavaScript to call real API ✓
- [x] Populate Step 3 with real tables from database ✓
- [x] Tested with real PostgreSQL database via Cloud SQL Proxy ✓

### 🎯 Milestone 3: Draft-Save & Credential Management ✅ COMPLETE
- [x] Fetch table names, row counts, and last updated timestamps ✓
- [x] Update wizard Step 3 to show real tables (not hardcoded) ✓
- [x] Add error handling (timeouts, invalid credentials, connection failures) ✓
- [x] Implement draft-save flow (credentials saved after successful test) ✓
- [x] Create `api_etl_save_draft_source()` endpoint ✓
- [x] Update wizard to call save-draft when moving from Step 2 to Step 3 ✓
- [x] Modify createDataSource() to update existing draft ✓
- [x] Test full wizard flow end-to-end ✓
- [x] Replace popup alerts with inline messages ✓

### 🎯 Milestone 4: Connection Management System ✅ COMPLETE
- [x] Create Connection model with ForeignKey from DataSource ✓
- [x] Migrate database schema ✓
- [x] Update views to create/retrieve Connection objects ✓
- [x] Add Connection Name field to wizard (obligatory, unique) ✓
- [x] Auto-suggest connection name based on source type + database name ✓
- [x] Validate connection name uniqueness ✓
- [x] Show saved connections at Step 1 (select to reuse) ✓
- [x] Auto-populate connection details when reusing saved connection ✓
- [x] Auto-test saved connection to fetch tables ✓
- [x] ETL job name validation (check duplicates at Step 1) ✓
- [x] Draft ETL job creation at Step 2 (not Step 5) ✓
- [x] Fix nextStep() to handle all wizard steps ✓

### 🎯 Milestone 5: ETL Job Editing & Wizard Resume ✅ COMPLETE
- [x] Add wizard step tracking to DataSource model ✓
- [x] Fix api_etl_get_source to handle both old and new architecture ✓
- [x] Implement wizard resume at last completed step + 1 ✓
- [x] Skip draft-save in edit mode (prevent duplicate UNIQUE errors) ✓
- [x] Auto-fetch tables in edit mode using stored credentials ✓
- [x] Create api_connection_test_and_fetch_tables endpoint ✓
- [x] Add loading spinner with disabled navigation buttons ✓
- [x] Implement proper CREATE vs EDIT flow separation ✓
- [x] Skip name validation in edit mode (Step 1) ✓
- [x] Add visual feedback during async table loading ✓

### 🎯 Milestone 6: Standalone Connections Management UI ✅ COMPLETE
- [x] Split ETL Jobs page into 2-column layout (50/50) ✓
- [x] Add Connections section (LEFT) with "+ Connection" button ✓
- [x] Move "+ ETL Job" button into ETL Jobs section (RIGHT) ✓
- [x] Create loadConnections() to fetch and display all connections ✓
- [x] Create renderConnectionCard() with status indicators ✓
- [x] Add connection status dots (green=working, red=failed) ✓
- [x] Auto-test connections on page load in background ✓
- [x] Create openCreateConnectionModal() for standalone creation ✓
- [x] Create openEditConnectionModal() with pre-filled data ✓
- [x] Add wizardStandaloneMode flag (no step progression) ✓
- [x] Create api_connection_create_standalone endpoint ✓
- [x] Wire Create Connection to call standalone endpoint ✓
- [x] Wire Edit Connection to update endpoint ✓
- [x] Show affected jobs count when editing connection ✓
- [x] Require connection re-test before saving edits ✓
- [x] Implement deleteConnection() with usage check ✓
- [x] Block deletion if ETL jobs depend on connection ✓
- [x] Add empty states for both sections ✓
- [x] Hide Back/Next navigation in standalone mode ✓
- [x] Auto-close modal and reload connections after create/edit ✓

### 🎯 Milestone 7: Simplified ETL Wizard Architecture ✅ COMPLETE
**Date Completed:** November 14, 2025

**Objective:** Complete separation of connection management from ETL job creation, simplify wizard flow from 5 steps to 3 steps.

**Backend Changes:**
- [x] Remove deprecated connection fields from DataSource model ✓
- [x] Add last_used_at field to Connection model ✓
- [x] Create api_etl_get_connections endpoint (Step 1) ✓
- [x] Create api_etl_test_connection_in_wizard endpoint ✓
- [x] Create api_etl_create_job endpoint (atomic creation at final step) ✓
- [x] Update Connection.last_used_at when creating ETL job ✓
- [x] Database migration: simplify_datasource_model ✓

**Frontend - ETL Wizard (3 Steps):**
- [x] Step 1: Select existing connection + Enter job name ✓
- [x] Step 2: Select table from database (auto-fetched) ✓
- [x] Step 3: Configure sync mode + Schedule + Review summary ✓
- [x] Progress bar updated from 5 steps to 3 steps ✓
- [x] Removed old Step 2 (connection configuration) ✓
- [x] Updated nextStep() for 3-step flow validation ✓
- [x] Created updateSummary() to populate Step 3 review ✓
- [x] Created createETLJob() - atomic creation (no drafts) ✓
- [x] loadSavedConnections() with status indicators ✓
- [x] fetchTablesForConnection() for table loading ✓

**Frontend - Connection Modal (2 Steps):**
- [x] Recreated 2-step wizard matching old design ✓
- [x] Step 1: Category tabs (Relational DB/Files/NoSQL) + tile-based selection ✓
- [x] Step 2: Connection form with test button ✓
- [x] "Save Connection" button only appears after successful test ✓
- [x] Connection testing does NOT save to Secret Manager (test first, save later) ✓
- [x] Progress bar for 2-step flow ✓
- [x] Navigation buttons (Back/Next) with proper state management ✓
- [x] Modal functions: openCreateConnectionModal, switchConnTab, connNextStep, etc. ✓
- [x] Event listener to enable Next button on type selection ✓
- [x] Fixed duplicate function definitions ✓
- [x] Added debug logging for troubleshooting ✓

**Key Improvements:**
- ✅ Clear separation: Connections are created/managed independently
- ✅ Simplified ETL flow: 3 steps instead of 5 (40% reduction)
- ✅ Better UX: Category tabs with tile-based database selection
- ✅ Test-first pattern: Connection test before save (no premature Secret Manager writes)
- ✅ Atomic ETL creation: No draft saves until final step
- ✅ Connection reuse: Select from existing connections at Step 1
- ✅ Status tracking: Connection.last_used_at updated on ETL job creation

**Testing Requirements:**
- [x] Test full ETL job creation flow (all 3 steps) ✓
- [x] Test connection creation flow (both steps) ✓
- [x] Test connection reuse from Step 1 ✓
- [x] Test table loading and selection (Step 2) ✓
- [x] Test with PostgreSQL database connection ✓
- [x] Test error handling (invalid credentials, network failures) ✓
- [x] Verify Secret Manager integration works correctly ✓

### 🎯 Milestone 7.5: Connection Wizard UX Enhancements ✅ COMPLETE
**Date Completed:** November 15, 2025

**Objective:** Improve connection wizard user experience, add all data source types, enhance error handling, and refine button states.

**Data Source Type Coverage:**
- [x] Added all 22 data source types (from 9 to 22) ✓
  - **Relational DBs (12):** PostgreSQL, MySQL, MariaDB, Oracle, SQL Server, IBM DB2, Redshift, BigQuery, Snowflake, Azure Synapse, Teradata
  - **NoSQL (5):** MongoDB, Cassandra, Redis, Firestore, DynamoDB
  - **Files (6):** CSV, JSON, Parquet, Avro, Excel, Text
- [x] Fixed NoSQL tab capitalization bug (connTabNosql) ✓
- [x] Added default ports for all relational databases ✓
- [x] Created separate forms for each category (Relational, BigQuery, NoSQL, Files) ✓

**Button State Management:**
- [x] Created centralized updateConnectionModalButtons() function ✓
- [x] Step 1: Hidden Back button (no Step 0), reactive Next button ✓
- [x] Next button: Grey (disabled) → White (enabled) on tile selection ✓
- [x] Step 2: Back button visible, Save button appears after successful test ✓
- [x] Save button: Disabled until successful connection test ✓
- [x] Cancel button: Always visible and active ✓
- [x] Removed alert messages (button states prevent invalid actions) ✓

**Test Connection Behavior:**
- [x] Test only validates connection (no Secret Manager save) ✓
- [x] Success: Green background message with checkmark ✓
- [x] Failure: Red background message with error icon ✓
- [x] Test button stays active for re-testing ✓
- [x] Field edits after successful test disable Save (requires re-test) ✓
- [x] Yellow warning shown on field changes ✓

**Save Connection Flow:**
- [x] Save button enabled only after successful test ✓
- [x] Success notification with green checkmark (2-second display) ✓
- [x] Auto-close modal and reload page after save ✓
- [x] Removed icon from Save button (text only) ✓

**Error Handling & Validation:**
- [x] Backend: Catch IntegrityError for duplicate credentials ✓
- [x] Frontend: Beautiful error notification with proper formatting ✓
- [x] Error window: Wide layout, left-aligned text, highlighted message box ✓
- [x] User-friendly messages for duplicate name and duplicate credentials ✓
- [x] Error details: Shows existing connection name, host, database, username ✓
- [x] Close button required (no accidental dismissal) ✓
- [x] ESC key support for error notifications ✓

**Visual Polish:**
- [x] Fixed modal height (450px) to prevent size jumps between steps ✓
- [x] Smooth transitions for button state changes (0.3s) ✓
- [x] Hover effects on enabled buttons (lift + shadow) ✓
- [x] Disabled state styling (opacity 0.5, cursor not-allowed) ✓
- [x] Pulse animation when selecting connection tiles ✓
- [x] Color transitions for Next button (grey → white) ✓

**Bug Fixes:**
- [x] Fixed missing pymysql dependency ✓
- [x] Updated requirements.txt with all missing packages ✓
- [x] Fixed NoSQL tab ID mismatch (capital SQL vs lowercase) ✓
- [x] Improved duplicate credential error messages (user-friendly) ✓

**Key Improvements:**
- ✅ 22 data source types supported (comprehensive coverage)
- ✅ Smart button states prevent user errors
- ✅ Test-first pattern enforced (can't save without successful test)
- ✅ Beautiful error notifications (no more ugly alerts)
- ✅ Field change detection (Save disabled if credentials edited)
- ✅ Professional visual design with smooth animations
- ✅ Fixed modal height prevents jarring size changes
- ✅ Duplicate detection with helpful guidance

### 🎯 Milestone 8: Connection Testing & UX Polish ✅ COMPLETE
**Date Completed:** November 15, 2025

**Objective:** Fix connection status indicators, improve error handling, and standardize button styling across the platform.

**Connection Status Bug Fixes:**
- [x] Fixed frontend status indicator system ✓
  - Added 4 status types: success (green), failed (red), error (yellow), unknown (gray)
  - Implemented proper error handling to distinguish connection failures vs system errors
  - Network errors no longer mark connections as "failed"
  - Fallback to previous status when test system unavailable
- [x] Fixed backend api_connection_test endpoint ✓
  - Now retrieves credentials from Secret Manager (was trying to parse empty request body)
  - Added proper error handling and logging
  - Returns correct status codes matching frontend expectations
  - Added detailed stack trace logging for debugging
- [x] Added comprehensive debug logging ✓
  - Console logs for connection testing with emoji indicators
  - Shows HTTP response status, test results, and error messages
  - Helps troubleshoot connection issues in real-time
- [x] Added manual refresh button ✓
  - Refresh icon button next to "+ Connection"
  - Spinning animation during refresh
  - Re-tests all connections on demand
- [x] Added timestamp display on connection cards ✓
  - Shows "Tested 5m ago" or "Failed 2m ago"
  - Helps users know if status is fresh or stale
  - Updates in real-time
- [x] Added loading state during auto-test ✓
  - Pulsing blue dot with "Testing..." text
  - Shows before test completes
  - Better user feedback

**Button Styling Standardization:**
- [x] Standardized all buttons using buttons.css ✓
  - Refresh button: Added `btn-icon` class for icon-only styling
  - +Connection button: Removed unnecessary `mr-1` class
  - +ETL Job button: Removed unnecessary `mr-1` class
  - Changed button container to use `.btn-group` class
  - All buttons now have consistent size, shape, and formatting
- [x] Fixed icon spacing ✓
  - Uses `gap: 10px` from .btn class
  - No manual margin classes needed
  - Consistent spacing across all buttons

**Key Improvements:**
- ✅ Working connections no longer show red dots incorrectly
- ✅ System errors (yellow) distinguished from connection failures (red)
- ✅ Comprehensive debugging via browser console
- ✅ Manual refresh capability for connection testing
- ✅ Visual feedback with timestamps
- ✅ Professional, consistent button styling
- ✅ Better UX with loading states and animations

**Files Modified:**
- `templates/ml_platform/model_etl.html` - Frontend status handling, debug logging, button styling
- `ml_platform/views.py` - Backend api_connection_test endpoint fix
- `static/css/buttons.css` - Already existed, now properly utilized

### 🎯 Milestone 9: UI/UX Polish & Design System ✅ COMPLETE
**Date Completed:** November 16, 2025

**Objective:** Enhance UI consistency, improve visual design, and create reusable component systems.

**Button Standardization:**
- [x] Fixed button sizing inconsistency ✓
  - All 3 buttons (Refresh, + Connection, + ETL Job) now same width (110px)
  - Created `.btn-fixed` CSS class for uniform button sizing
  - Override aspect-ratio for icon buttons with fixed width
- [x] Unified navigation arrows ✓
  - Changed all `fa-arrow-left/right` to `fa-chevron-left/right`
  - Consistent with sidebar collapse/expand button style
  - Applies to ETL wizard, connection modal, and all navigation buttons

**Background Design System:**
- [x] Created backgrounds.css file ✓
  - Dotted pattern background (like Vertex AI Pipelines)
  - 3 variants: normal, subtle, dense
  - Reusable across application
- [x] Applied dotted background to main pages ✓
  - Replaced grey background with professional dotted pattern
  - Cards (white) now float elegantly on dotted background
  - Consistent visual hierarchy

**Modal System:**
- [x] Created modals.css for reusable modals ✓
  - Professional modal styling with smooth animations
  - 4 modal types: danger, warning, info, success
  - Colored header icons and buttons
  - Modal sizes: sm, default, lg, xl
- [x] Built custom confirmation modal ✓
  - Replaced browser `confirm()` dialogs with styled modals
  - Customizable title, message, buttons, type
  - Auto-hides Cancel button for error/info messages
  - Keyboard support (ESC to close)
- [x] Updated deleteConnection() to use custom modal ✓
  - Beautiful warning modal for dependent jobs
  - Professional delete confirmation
  - User-friendly error messages with HTML formatting

**Connection Management UX:**
- [x] Fixed delete connection functionality ✓
  - Removed duplicate deleteConnection() function
  - Proper usage checking before deletion
  - Shows list of dependent jobs if deletion blocked
- [x] Fixed connection modal sizing ✓
  - Changed from `h-36` (144px) to `max-h-80` (320px)
  - Database tiles now fill available space
  - Scrollbar only appears if needed (not by default)
  - Eliminates wasted whitespace

**Empty State Messages:**
- [x] Modernized empty state text ✓
  - Removed database/briefcase icons
  - Professional copy: "No database connections configured"
  - Action-oriented subtext: "Create your first connection to get started with data ingestion"
  - Better typography with proper spacing

**Key Improvements:**
- ✅ Consistent button sizing across all UI elements
- ✅ Unified navigation icons (chevrons everywhere)
- ✅ Professional dotted background pattern
- ✅ Reusable modal system for confirmations
- ✅ Better space utilization in connection modal
- ✅ Modern, professional empty states
- ✅ Improved delete flow with usage checking

**Files Created:**
- `static/css/backgrounds.css` - Dotted background patterns
- `static/css/modals.css` - Reusable modal system

**Files Modified:**
- `templates/base.html` - Include new CSS files
- `templates/base_model.html` - Apply dotted background
- `templates/ml_platform/model_etl.html` - All UX improvements
- `static/css/buttons.css` - Added btn-fixed class

### 🎯 Milestone 10: Connection Card Redesign & UI Optimization ✅ COMPLETE
**Date Completed:** November 16, 2025

**Objective:** Create a modern, minimalistic connection card design with optimized space usage and reusable card system.

**Connection Card Redesign:**
- [x] Created cards.css for reusable card/tablet design ✓
- [x] Redesigned connection cards from 4 rows to 2 rows ✓
- [x] Implemented 3-column layout (60% + 30% + 10%) ✓
  - Column 1: Status dot + Connection name + Database name
  - Column 2: "Used by: X jobs" + "Tested: timestamp"
  - Column 3: Edit and Delete buttons stacked vertically
- [x] Removed redundant information (data type, host name) ✓
- [x] Added database name display (db name: xyz) ✓
- [x] Changed text from "X job(s) using" to "Used by: X jobs" ✓
- [x] Changed text from "Tested just now" to "Tested: just now" ✓
- [x] Stacked action buttons vertically (edit on top, delete on bottom) ✓
- [x] Fixed grid overflow issues with proper CSS Grid configuration ✓
- [x] Added text truncation with ellipsis for long names ✓
- [x] Increased font sizes for better readability (connection: 16px, db name: 13px) ✓

**Design System:**
- [x] Created reusable card CSS classes ✓
  - `.card` - Base card styling
  - `.card-container` - 3-column grid layout
  - `.card-header` - Status dot + title
  - `.card-body` - Information display
  - `.card-meta-column` - Meta information
  - `.card-actions` - Action buttons
  - `.status-dot` with variants (green/red/gray/blue)
  - `.card-action-btn` - Icon-only action buttons
- [x] Modern, minimalistic aesthetic ✓
- [x] Efficient space usage with no wasted whitespace ✓
- [x] Simple and informative layout ✓

**Key Improvements:**
- ✅ Reduced from 4 rows to 2 rows (50% more compact)
- ✅ Better horizontal space utilization (3-column grid)
- ✅ No horizontal scrollbars (proper overflow handling)
- ✅ Text truncation prevents overlapping
- ✅ Larger, more readable fonts
- ✅ Reusable card system for future components
- ✅ Professional, clean design

**Files Created:**
- `static/css/cards.css` - Reusable card/tablet design system

**Files Modified:**
- `templates/ml_platform/model_etl.html` - Card rendering and layout

### 🎯 Milestone 10.5: Cloud Storage Integration & Storage-First Architecture ✅ COMPLETE
**Date Completed:** November 17, 2025

**Objective:** Implement comprehensive cloud storage support (GCS, S3, Azure Blob) with a storage-first approach where connections represent bucket/container access rather than file types.

**Architecture Decision:**
- Replaced file-type-first (CSV, Parquet, JSON) with storage-first approach
- One connection = one bucket/container (regardless of file formats inside)
- File type selection deferred to ETL job creation (not connection setup)
- Matches industry best practices and provides better flexibility

**Backend Changes:**
- [x] Updated Connection model SOURCE_TYPE_CHOICES ✓
  - Removed: csv, json, parquet, avro, excel, txt (6 file types)
  - Added: gcs, s3, azure_blob (3 storage providers)
- [x] Added cloud storage authentication fields to Connection model ✓
  - GCS: bucket_path, service_account_json
  - S3: aws_access_key_id, aws_secret_access_key_secret, aws_region
  - Azure: azure_storage_account, azure_account_key_secret, azure_sas_token_secret
- [x] Applied database migration (0009_connection_aws_access_key_id...) ✓
- [x] Implemented connection test functions in connection_manager.py ✓
  - test_gcs(): Google Cloud Storage with service account authentication
  - test_s3(): AWS S3 with access key/secret key authentication
  - test_azure_blob(): Azure Blob Storage with account key or SAS token
- [x] Updated view functions to handle storage parameters ✓
  - api_connection_test_wizard: Extract bucket_path, AWS credentials, Azure credentials
  - api_connection_create_standalone: Save storage connection fields

**Frontend Changes:**
- [x] Renamed "Flat Files" tab to "Cloud Storage" ✓
- [x] Created three comprehensive connection forms ✓
  - **GCS Form**: Bucket path + Service Account JSON (with file upload button)
  - **S3 Form**: Bucket path + Access Key ID + Secret Access Key + Region selector (12 regions)
  - **Azure Blob Form**: Storage account + Container path + Auth method toggle (Account Key or SAS Token)
- [x] Updated JavaScript routing logic ✓
  - switchConnTab(): Handle 'storage' tab instead of 'files'
  - connShowForm(): Route to correct storage form (gcs, s3, azure_blob)
  - testConnectionStandalone(): Collect storage credentials
  - saveConnectionStandalone(): Save storage connections
- [x] Added file upload handler for GCS service account JSON ✓
- [x] Added toggleAzureAuthFields() for Azure authentication switching ✓

**Dependencies Installed:**
- [x] google-cloud-storage==2.19.0 ✓
- [x] boto3==1.35.94 (AWS SDK) ✓
- [x] azure-storage-blob==12.25.0 ✓

**Connection Test Features:**
- **GCS**: Validates service account JSON, connects to bucket, lists up to 100 files
- **S3**: Validates AWS credentials, connects to bucket, lists up to 100 objects
- **Azure Blob**: Supports both Account Key and SAS Token authentication, lists up to 100 blobs
- All test functions return file metadata: name, size, last_modified

**Security:**
- Service account JSON stored directly in Connection model (encrypted at rest)
- AWS Secret Access Key stored in GCP Secret Manager (never in Django DB)
- Azure Account Key/SAS Token stored in GCP Secret Manager (never in Django DB)
- Only non-sensitive fields (bucket_path, aws_access_key_id, azure_storage_account) in Django DB

**Key Improvements:**
- ✅ Storage-first architecture (connection = bucket access, not file type)
- ✅ Support for 3 major cloud storage providers (GCS, S3, Azure)
- ✅ Comprehensive authentication methods (service account, access keys, SAS tokens)
- ✅ File upload UX for service account JSON files
- ✅ Dual authentication options for Azure (Account Key or SAS Token)
- ✅ Real-time file listing during connection test (up to 100 files shown)
- ✅ Better flexibility - one connection can access multiple file formats

**Files Modified:**
- `ml_platform/models.py` - Updated SOURCE_TYPE_CHOICES, added storage fields
- `ml_platform/migrations/0009_*.py` - Database migration for storage fields
- `templates/ml_platform/model_etl.html` - New storage forms, updated JavaScript
- `ml_platform/utils/connection_manager.py` - Three new test functions (test_gcs, test_s3, test_azure_blob)
- `ml_platform/views.py` - Updated to handle storage parameters
- `requirements.txt` - Added cloud storage client libraries

**Testing Notes:**
- GCS connection tested successfully with memo2 project bucket
- Required IAM role: **Storage Object Viewer** (for read access)
- Service account: `firestore-etl-test@memo2-456215.iam.gserviceaccount.com`

### 🎯 Milestone 10.6: Schema Selection in ETL Wizard ✅ COMPLETE
**Date Completed:** November 17, 2025

**Objective:** Add schema selection capability to ETL Wizard Step 2, enabling users to select specific database schemas (for PostgreSQL, SQL Server, Oracle) before choosing tables.

**Problem Addressed:**
- Many databases have multiple schemas (e.g., `public`, `analytics`, `staging` in PostgreSQL)
- Previous implementation only fetched tables from a single hardcoded schema
- Users couldn't access tables from different schemas

**Architecture Decision:**
- **Schema at ETL Job Level** (not connection level)
- One connection can serve multiple ETL jobs, each pulling from different schemas
- More flexible and scalable - don't need N connections for N schemas

**Backend Changes:**
- [x] Added `fetch_schemas()` routing function to connection_manager.py ✓
- [x] Added `fetch_schemas_postgresql()` - fetches all user schemas (excludes system schemas) ✓
- [x] Added `fetch_schemas_mysql()` - returns database name as single schema ✓
- [x] Added `fetch_schemas_bigquery()` - fetches all datasets (act as schemas) ✓
- [x] Added `fetch_tables_for_schema()` - routing function with schema parameter ✓
- [x] Added schema-aware table fetching for PostgreSQL, MySQL, BigQuery ✓
- [x] Created API endpoint: `api_connection_fetch_schemas()` ✓
- [x] Created API endpoint: `api_connection_fetch_tables_for_schema()` ✓
- [x] Added `schema_name` field to DataSourceTable model ✓
- [x] Applied migration: `0010_add_schema_name_to_datasourcetable.py` ✓
- [x] Updated `api_etl_create_job()` to store schema_name ✓

**Frontend Changes:**
- [x] Updated Step 2 UI to add schema dropdown ✓
- [x] Added schema selection before table selection ✓
- [x] Created `fetchSchemasForConnection()` JavaScript function ✓
- [x] Created `onSchemaChange()` handler to load tables when schema selected ✓
- [x] Updated `fetchTablesForSchema()` to accept schema parameter ✓
- [x] Auto-select for MySQL (only 1 schema), disable dropdown ✓
- [x] Updated validation to check both schema and table selection ✓
- [x] Updated summary to show `schema.table_name` format ✓
- [x] Updated payload to include schema_name ✓

**User Flow:**
```
Step 2: Select Schema & Table
  ↓
[Schema Dropdown] (auto-populated with available schemas)
  ↓
User selects schema (e.g., "public")
  ↓
[Tables List] (auto-fetched for selected schema)
  ↓
User selects table → Next Step
```

**Database-Specific Behavior:**
- **PostgreSQL:** Shows all user schemas, excludes system schemas
- **MySQL:** Auto-selects database as schema, hides dropdown
- **BigQuery:** Shows all datasets as schemas
- **Others:** Graceful fallback with default schema

**Key Improvements:**
- ✅ One connection can access multiple schemas
- ✅ Eliminates connection proliferation (don't need separate connections per schema)
- ✅ Better for Oracle/PostgreSQL with many schemas
- ✅ Smart auto-detection for single-schema databases (MySQL)
- ✅ Full history of which schema each ETL job uses

**Files Modified:**
- `ml_platform/utils/connection_manager.py` - Schema fetching functions (~350 lines added)
- `ml_platform/views.py` - 2 new API endpoints
- `ml_platform/models.py` - schema_name field
- `ml_platform/urls.py` - 2 new routes
- `templates/ml_platform/model_etl.html` - UI and JavaScript updates

### 🎯 Milestone 11: Advanced ETL Wizard - 4-Step Flow with Load Strategy ✅ COMPLETE
**Date Completed:** November 17, 2025

**Objective:** Enhance ETL wizard from 3 steps to 4 steps with sophisticated load strategy configuration, table preview, column selection, and historical backfill capabilities.

**Problem Addressed:**
- Need to differentiate between transactional (append-only) and catalog (snapshot) tables
- Users want historical backfill (e.g., load last 90 days, then daily increments)
- Need column-level control (exclude heavy BLOB/TEXT fields)
- Lack of visibility into table structure before configuring load

**Architecture:**
- **2 Load Types:** Transactional (append-only) vs Catalog (daily snapshot)
- **Historical Backfill:** Last 30/60/90 days or custom date for first sync
- **Column Selection:** Deselect specific columns to optimize performance
- **Smart Auto-Detection:** Automatically recommends timestamp columns

**Backend Changes:**
- [x] Added 9 new fields to DataSourceTable model ✓
  - `load_type` (transactional | catalog)
  - `timestamp_column` (for incremental tracking)
  - `historical_start_date` (backfill start date)
  - `selected_columns` (JSON array)
  - `schedule_type`, `schedule_time`, `schedule_day_of_week`, `schedule_day_of_month`, `schedule_cron`
- [x] Applied migration: `0011_add_load_strategy_fields.py` ✓
- [x] Added `fetch_table_metadata()` to connection_manager.py ✓
  - Fetches column names, types, nullability, constraints
  - Fetches sample data (5 rows per column)
  - Auto-detects timestamp columns (prefers created_at, updated_at)
  - Auto-detects primary keys
- [x] Implemented for PostgreSQL, MySQL, BigQuery ✓
- [x] Created API endpoint: `api_connection_fetch_table_preview()` ✓
- [x] Updated `api_etl_create_job()` to handle all new fields ✓

**Frontend Changes:**
- [x] Updated wizard from 3 steps to 4 steps ✓
- [x] Updated progress bar (4 segments instead of 3) ✓
- [x] Created **new Step 3: Configure Load Strategy** ✓
  - Table preview with column metadata
  - Column checkboxes (Select All / Deselect All)
  - Load type selection (Transactional vs Catalog)
  - Timestamp column dropdown (auto-populated with recommendations)
  - Historical backfill options (30/60/90 days or custom date)
- [x] Renamed old Step 3 to **Step 4: Schedule & Review** ✓
- [x] Added JavaScript functions for Step 3 ✓
  - `proceedToStep3()` - Transitions and fetches table preview
  - `fetchTablePreview()` - Calls API for metadata
  - `renderTablePreview()` - Renders columns with visual indicators
  - `toggleAllColumns()` - Bulk column selection
  - `populateTimestampColumns()` - Populates dropdown with auto-detection
  - `onLoadTypeChange()` - Shows/hides config sections
- [x] Updated navigation logic for 4 steps ✓
- [x] Updated `createETLJob()` to collect and send all new fields ✓

**New 4-Step Wizard Flow:**
```
Step 1: Connection & Job Name
  ↓
Step 2: Schema & Table Selection
  ↓
Step 3: Configure Load Strategy ⭐ NEW
  ├─ View table preview (columns, types, samples)
  ├─ Select columns to sync (checkboxes)
  ├─ Choose load type:
  │   • Transactional (append-only, incremental by timestamp)
  │   • Catalog (daily snapshot, full replace)
  ├─ Configure timestamp column (if transactional)
  └─ Set historical backfill range (30/60/90 days or custom)
  ↓
Step 4: Schedule & Review
  ├─ Set schedule (Manual, Hourly, Daily, Weekly, Monthly)
  └─ Review summary → Create ETL Job
```

**Visual Indicators:**
- 🔑 Primary key columns
- 🕐 Timestamp columns
- Sample values for each column
- Row count display
- Column type information

**Load Type Behavior:**

**Transactional (Append-Only):**
- For: Transactions, logs, events, orders
- Uses timestamp column for incremental tracking
- First sync: Loads records from historical_start_date to now
- Subsequent syncs: Loads only new records (WHERE timestamp > last_sync_value)
- Never updates existing records

**Catalog (Daily Snapshot):**
- For: Products, customers, inventory
- Full table replacement on each sync
- No incremental tracking needed
- No history kept (overwrites previous data)

**Historical Backfill Example:**
```
User selects: "Last 90 days"
Today: 2025-11-17
Calculated start date: 2025-08-19

First sync SQL:
  WHERE created_at >= '2025-08-19'

Subsequent sync SQL:
  WHERE created_at > '2025-11-17 10:23:45' (last sync timestamp)
```

**Key Features:**
- ✅ Table preview with column metadata and sample data
- ✅ Smart auto-detection of timestamp columns and primary keys
- ✅ Column-level control (deselect heavy fields)
- ✅ Two distinct load strategies (transactional vs catalog)
- ✅ Historical backfill with flexible date ranges
- ✅ Visual indicators (icons for PK and timestamp columns)
- ✅ All configuration stored in database for execution
- ✅ Monthly schedule option added

**Payload Example:**
```json
{
  "name": "Daily Transactions",
  "connection_id": 5,
  "schema_name": "public",
  "load_type": "transactional",
  "timestamp_column": "created_at",
  "historical_start_date": "2025-08-19",
  "selected_columns": ["id", "created_at", "amount", "customer_id"],
  "schedule_type": "daily",
  "tables": [{
    "source_table_name": "transactions",
    "dest_table_name": "transactions",
    "sync_mode": "incremental",
    "incremental_column": "created_at"
  }]
}
```

**Files Modified:**
- `ml_platform/models.py` - 9 new fields added
- `ml_platform/migrations/0011_*.py` - Migration for new fields
- `ml_platform/utils/connection_manager.py` - Table metadata functions (~400 lines)
- `ml_platform/views.py` - New API endpoint + updated ETL creation
- `ml_platform/urls.py` - New route
- `templates/ml_platform/model_etl.html` - Complete Step 3 HTML + JavaScript (~200 lines)

**Documentation Created:**
- `IMPLEMENTATION_STATUS.md` - Progress tracking
- `IMPLEMENTATION_COMPLETE.md` - Comprehensive reference guide

### 🎯 Milestone 11.5: BigQuery Table Setup & Schema Management ✅ COMPLETE
**Date Completed:** November 18, 2025

**Objective:** Add intelligent BigQuery table schema configuration with auto-type detection, user customization, and upfront table creation.

**Architecture Decision:**
- **Schema-First Approach:** BigQuery tables created during ETL wizard (before any data is loaded)
- **Immutable Schemas:** Tables cannot be modified after creation (must create new job for schema changes)
- **Smart Type Mapping:** Intelligent mapping from source DB types to BigQuery types with confidence scoring

**Backend Implementation:**
- [x] Created `ml_platform/utils/schema_mapper.py` (368 lines) ✓
  - PostgreSQL → BigQuery type mapping (40+ types)
  - MySQL → BigQuery type mapping (30+ types)
  - Smart type detection (dates in VARCHAR, integers in strings, boolean patterns)
  - Confidence scoring (high/medium/low)
  - Warning system for problematic fields
- [x] Created `ml_platform/utils/bigquery_manager.py` (219 lines) ✓
  - `ensure_dataset_exists()` - Creates raw_data dataset
  - `create_table_from_schema()` - Creates tables with partitioning/clustering
  - `validate_table_schema()` - Schema validation for evolution
  - Automatic DAY partitioning for transactional loads
  - Automatic clustering on timestamp column
- [x] Enhanced `ml_platform/utils/connection_manager.py` ✓
  - `fetch_table_metadata()` now returns BigQuery type mappings
  - Each column includes: bigquery_type, bigquery_mode, confidence, warnings
- [x] Updated `ml_platform/views.py` (api_etl_create_job) ✓
  - Creates BigQuery dataset (if needed)
  - Creates BigQuery table with custom schema
  - Validates table name and schema
  - Returns full table path in response
  - Rollback on table creation failure

**Frontend Implementation (5-Step Wizard):**
- [x] Updated wizard from 4 steps to 5 steps ✓
- [x] Added **new Step 4: BigQuery Table Setup** ✓
  - Table name input (default: `bq_{source_table}`, editable)
  - Interactive schema editor table
  - Editable BigQuery type dropdown (13 types)
  - Editable mode dropdown (NULLABLE/REQUIRED)
  - Confidence indicators (🟢 high, 🟡 medium, 🔴 low)
  - Warning panel for schema issues
  - Performance optimization info (partitioning/clustering)
  - Summary panel with full table path
  - Reset to Defaults button
- [x] Renamed old Step 4 → **Step 5: Schedule & Review** ✓
- [x] Added JavaScript functions for Step 4 ✓
  - `proceedToStep4()` - Transition and setup
  - `renderBigQuerySchemaEditor()` - Render editable schema
  - `getBigQueryTypeOptions()` - Type dropdown options
  - `onBqTypeChange()` / `onBqModeChange()` - Handle user edits
  - `resetSchemaToDefaults()` - Reset to auto-detected
  - `updateSchemaWarnings()` - Validate schema
- [x] Updated navigation logic (progress bar, showStep, nextStep) ✓
- [x] Updated `createETLJob()` payload with BigQuery schema ✓

**New 5-Step Wizard Flow:**
```
Step 1: Connection & Job Name
  ↓
Step 2: Schema & Table Selection
  ↓
Step 3: Configure Load Strategy
  • View table preview (columns, types, samples)
  • Select columns to sync
  • Choose load type (Transactional vs Catalog)
  • Configure timestamp column
  • Set historical backfill range
  ↓
Step 4: BigQuery Table Setup ⭐ NEW
  • Review source → BigQuery type mappings
  • Customize table name (default: bq_{source_table})
  • Edit BigQuery types if needed
  • Edit modes (NULLABLE/REQUIRED)
  • View warnings for schema issues
  • See performance optimizations (partitioning/clustering)
  ↓
Step 5: Schedule & Review
  • Set schedule (Manual, Hourly, Daily, Weekly, Monthly)
  • Review complete summary
  • Create ETL Job → BigQuery table created immediately
```

**Type Mapping Examples:**
- PostgreSQL `integer` → BigQuery `INT64` (high confidence)
- PostgreSQL `timestamp without time zone` → BigQuery `TIMESTAMP` (high confidence)
- PostgreSQL `varchar(50)` → BigQuery `STRING` (high confidence)
- MySQL `tinyint(1)` → BigQuery `BOOL` (high confidence, special case)
- VARCHAR containing dates → BigQuery `DATE` (medium confidence, auto-detected)
- TEXT fields → BigQuery `STRING` with warning about performance

**Key Features:**
- ✅ Intelligent type mapping with 40+ PostgreSQL and 30+ MySQL types
- ✅ Smart pattern detection (dates, timestamps, booleans in strings)
- ✅ User customization - edit any type or mode
- ✅ Confidence scoring - visual indicators for mapping quality
- ✅ Warning system - alerts for large TEXT fields, type mismatches
- ✅ Schema immutability - clear messaging that schemas can't change
- ✅ Performance optimization - automatic partitioning/clustering for transactional loads
- ✅ Table name customization - default prefix `bq_` but editable
- ✅ Upfront creation - tables created during wizard (not at runtime)

**Configuration Required:**
```python
# settings.py or .env
GCP_PROJECT_ID = 'your-gcp-project-id'
```

**GCP Permissions Needed:**
- `bigquery.datasets.create`
- `bigquery.tables.create`
- `bigquery.tables.get`
- `bigquery.tables.list`

**Files Created:**
- `ml_platform/utils/schema_mapper.py` (368 lines)
- `ml_platform/utils/bigquery_manager.py` (219 lines)
- `BQ_TABLE_SETUP.md` (comprehensive documentation)

**Files Modified:**
- `ml_platform/utils/connection_manager.py` (enhanced fetch_table_metadata)
- `ml_platform/views.py` (enhanced api_etl_create_job)
- `templates/ml_platform/model_etl.html` (added Step 4, ~300 lines)

**Total Lines of Code Added:** ~1,100 lines

**Documentation:**
- `BQ_TABLE_SETUP.md` - Complete implementation guide with detailed next steps for ETL Runner and Cloud Scheduler

### 🎯 Milestone 12: ETL Runner & Cloud Scheduler Integration ✅ COMPLETE
**Date Completed:** November 18, 2025
**Status:** Phase 1 & Phase 2 COMPLETE | Ready for Data Loading

**Phase 1: ETL Runner Implementation (Week 1-2)** ✅
- [x] Built complete ETL runner codebase (~2,600 lines of Python) ✓
- [x] Implemented PostgreSQLExtractor with server-side cursors ✓
- [x] Implemented MySQLExtractor with SSCursor streaming ✓
- [x] Built BigQueryLoader with batch processing ✓
- [x] Created configuration management module ✓
- [x] Implemented logging and error handling utilities ✓
- [x] Created main.py orchestrator with job execution flow ✓
- [x] Created Dockerfile for Cloud Run deployment ✓
- [x] Deployed to Cloud Run Jobs (europe-central2) ✓
- [x] Configured service accounts and IAM permissions ✓

**Phase 2: Django Integration & Cloud Scheduler (Week 2-3)** ✅
- [x] Created CloudSchedulerManager utility module ✓
- [x] Updated ETLRun model with progress tracking fields ✓
- [x] Added schedule fields to DataSource model ✓
- [x] Created API endpoint: `api_etl_job_config` (runner fetches config) ✓
- [x] Created API endpoint: `api_etl_run_update` (runner reports progress) ✓
- [x] Created API endpoint: `api_etl_trigger_now` (manual execution) ✓
- [x] Updated `api_etl_create_job` to integrate Cloud Scheduler ✓
- [x] Updated frontend "Run Now" button to trigger Cloud Run jobs ✓
- [x] Configured IAM permissions for all service accounts ✓
- [x] Set region to europe-central2 (Warsaw, Poland) ✓
- [x] Database migrations created and applied ✓

**What's Ready:**
- ✅ ETL jobs create BigQuery tables during wizard
- ✅ Manual "Run Now" triggers Cloud Run ETL jobs
- ✅ Cloud Scheduler utility ready for automated scheduling
- ✅ Progress tracking API endpoints implemented
- ✅ All IAM permissions configured
- ✅ Docker image deployed to Cloud Run

**Next Steps (Testing & Phase 3):**
- [ ] Test end-to-end data loading (click "Run Now", verify data in BigQuery)
- [ ] Test Cloud Scheduler job creation for scheduled jobs
- [ ] Validate progress tracking and status updates
- [ ] Implement Phase 3: Real-time status monitoring UI
- [ ] Build ETL history page with run metrics

---

## What We Accomplished

**Milestones 1-11 Complete!**

✅ **Advanced 4-Step ETL Wizard** - Enhanced with load strategy, table preview, column selection
✅ **Schema Selection** - Support for multi-schema databases (PostgreSQL, Oracle, SQL Server)
✅ **Load Type Differentiation** - Transactional (append-only) vs Catalog (daily snapshot)
✅ **Historical Backfill** - Load last 30/60/90 days on first sync, then daily increments
✅ **Table Preview** - View column metadata, data types, sample values before configuring
✅ **Column Selection** - Deselect specific columns (e.g., heavy BLOB/TEXT fields)
✅ **Smart Auto-Detection** - Recommends timestamp columns and detects primary keys
✅ **Cloud Storage Integration** - GCS, S3, Azure Blob with storage-first architecture
✅ Real database connection testing (PostgreSQL, MySQL, BigQuery)
✅ Secure credential storage in GCP Secret Manager
✅ **Standalone Connection Management** - 2-step wizard with category tabs
✅ **Complete Architecture Separation** - Connections and ETL jobs managed independently
✅ **Connection Reuse Pattern** - One connection serves multiple schemas and ETL jobs
✅ **Test-First Pattern** - Connection test before Secret Manager save (no premature writes)
✅ **Atomic ETL Creation** - No draft saves until final step (cleaner flow)
✅ **Clean Data Model** - Added 9 new fields for load strategy configuration
✅ **Connection Tracking** - last_used_at field updated on ETL job creation
✅ Auto-test saved connections to fetch table list in background
✅ Real table metadata displayed in wizard (names, row counts, last updated)
✅ Inline error messages with proper UX
✅ Cloud SQL Proxy integration for secure database access
✅ **Edit/Restore ETL Jobs** - click Edit to resume wizard at last step + 1
✅ **Loading State Management** - animated spinner + disabled navigation during async operations
✅ **Standalone Connections Management UI** - 2-column layout with dedicated connections section
✅ **Connection CRUD** - Create, Edit, Delete connections independently from ETL jobs
✅ **Live Connection Status** - Auto-tested green/red/yellow indicators
✅ **Protected Deletion** - Blocks deletion of connections with dependent jobs
✅ **Category-Based Selection** - Relational DB/Cloud Storage/NoSQL tabs with tile-based picking
✅ **Fixed Connection Status Bug** - Proper status indicators with intelligent error handling
✅ **Standardized Button Styling** - Consistent buttons using buttons.css system
✅ **Manual Refresh** - Re-test connections on demand with spinning animation
✅ **Status Timestamps** - "Tested 5m ago" display for freshness awareness
✅ **Comprehensive Debug Logging** - Console logs with emoji indicators for troubleshooting
✅ **Modern Connection Cards** - Minimalistic 3-column design (60% + 30% + 10%)
✅ **Reusable Card System** - cards.css for consistent design across platform
✅ **Optimized Space Usage** - 2-row layout, no wasted whitespace
✅ **Text Truncation** - Ellipsis for long names, prevents overflow
✅ **22 Data Source Types** - 12 relational DBs, 3 cloud storage providers, 5 NoSQL databases

**Next Steps:** Testing and validation, then Milestone 12 - Production readiness and deployment

---

## Standalone Connections Management UI Architecture

**Overview:**
The ETL Jobs page now features a 2-column layout that separates connection management from ETL job management, allowing users to manage database connections independently.

**Layout Structure:**
```
┌─────────────────────────────────────────────────────────────┐
│                         ETL Jobs                            │
├──────────────────────────────┬──────────────────────────────┤
│    Connections (LEFT 50%)    │   ETL Jobs (RIGHT 50%)       │
├──────────────────────────────┼──────────────────────────────┤
│  Connections                 │  Jobs                        │
│  [+ Connection]              │  [+ ETL Job]                 │
│                              │                              │
│  ┌────────────────────────┐  │  ┌────────────────────────┐  │
│  │ ● PostgreSQL - prod    │  │  │ 📊 daily_users         │  │
│  │ PostgreSQL             │  │  │ PostgreSQL • prod      │  │
│  │ 10.0.1.5              │  │  │ [Run] [Edit] [Delete]  │  │
│  │ 3 job(s) using         │  │  └────────────────────────┘  │
│  │ [Edit] [Delete]        │  │                              │
│  └────────────────────────┘  │  ┌────────────────────────┐  │
│                              │  │ 📊 products_sync       │  │
│  ┌────────────────────────┐  │  │ MySQL • analytics      │  │
│  │ ● MySQL - analytics    │  │  │ [Run] [Edit] [Delete]  │  │
│  │ MySQL                  │  │  └────────────────────────┘  │
│  │ analytics.db.com      │  │                              │
│  │ 1 job(s) using         │  │  (scroll for more...)        │
│  │ [Edit] [Delete]        │  │                              │
│  └────────────────────────┘  │                              │
│                              │                              │
│  (scroll for more...)        │                              │
│                              │                              │
└──────────────────────────────┴──────────────────────────────┘
```

**Connections Section (LEFT):**
- **Header:** "Connections" with "+ Connection" button
- **Display:** Connection cards showing:
  - Status indicator (🟢 green = working, 🔴 red = failed)
  - Connection name
  - Data source type (PostgreSQL, MySQL, BigQuery, etc.)
  - Host/server address or project ID
  - Number of ETL jobs using this connection
  - Edit & Delete action buttons
- **Behavior:**
  - Max 4 cards visible with vertical scroll
  - Auto-loads on page load
  - Auto-tests each connection in background to update status dots
  - Empty state: "No connections yet" message

**ETL Jobs Section (RIGHT):**
- **Header:** "Jobs" with "+ ETL Job" button (moved from previous top-right position)
- **Display:** Existing ETL job cards (unchanged)
- **Behavior:**
  - Max 4 cards visible with vertical scroll
  - Empty state: "No ETL jobs yet" message

**Standalone Connection Modal:**
When "+ Connection" is clicked:
1. Opens wizard in **Standalone Mode** at Step 2 (connection details)
2. Hides Back/Next navigation buttons (no step progression)
3. Shows "Create Connection" or "Edit Connection" title
4. User fills connection details and clicks "Test Connection"
5. If test succeeds, connection is created/updated automatically
6. Modal shows success message and auto-closes after 1.5 seconds
7. Connections list reloads to show new/updated connection

**Connection Status Indicators:**
- 🟢 **Green dot** - Connection tested successfully
- 🔴 **Red dot** - Connection test failed
- Status updated via background API calls when page loads

**Protected Deletion:**
- Clicking Delete checks for dependent ETL jobs
- If jobs exist: Shows error with job names, blocks deletion
- If no dependencies: Confirms and deletes connection

**Key Difference from ETL Job Wizard:**
- **ETL Job Flow:** Step 1 → Step 2 → Step 3 → Step 4 → Step 5 (full wizard)
- **Standalone Connection:** Only Step 2 (connection details), no progression

---

## Key Files Modified

```
ml_platform/utils/connection_manager.py    ✅ NEW - connection testing for PostgreSQL, MySQL, BigQuery
ml_platform/views.py                       ✅ UPDATED - Connection CRUD, standalone endpoint, ETL wizard, loading states
ml_platform/models.py                      ✅ UPDATED - Connection model, wizard step tracking fields
ml_platform/urls.py                        ✅ UPDATED - Connection management, standalone creation endpoint
templates/ml_platform/model_etl.html       ✅ UPDATED - 2-column layout, standalone connection UI, wizard modes
ml_platform/migrations/0005_*.py           ✅ NEW - Connection model migration
ml_platform/migrations/0006_*.py           ✅ NEW - DataSource unique constraint (etl_config, name)
ml_platform/migrations/0007_*.py           ✅ NEW - wizard_last_step and wizard_completed_steps fields
requirements.txt                           ✅ UPDATED - psycopg2-binary, pymysql, google-cloud-secret-manager
start_dev.sh                               ✅ NEW - development environment startup script
```

---

## Dependencies Installed

```bash
✅ psycopg2-binary              # PostgreSQL connections
✅ pymysql                      # MySQL connections
✅ google-cloud-secret-manager  # Secure credential storage
✅ google-cloud-bigquery        # BigQuery connections
```

All dependencies are in `requirements.txt` and installed.

---

## Security Note

**Never store passwords in Django database.**

✅ Store in Secret Manager: `model-{id}-source-{id}-credentials`
✅ Store secret name in Django: `credentials_secret_name = "model-5-source-12..."`
❌ Don't store actual password in Django DB

---

## Service Account Creation

**Simple way - Run the setup script:**

```bash
bash setup_service_account.sh
```

This will:
- Create service account: `django-app@b2b-recs.iam.gserviceaccount.com`
- Grant Secret Manager permissions
- Download key to `django-service-account.json` (already in .gitignore ✓)
- Show you the export command to add to your shell profile

**After running, add this to your `~/.zshrc` or `~/.bash_profile`:**

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/Users/dkulish/Projects/b2b_recs/django-service-account.json"
```

Then reload: `source ~/.zshrc`

---

## Running the Application

**Start Django server with GCP credentials:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/Users/dkulish/Projects/b2b_recs/.gcp/django-service-account.json"
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

**Start Cloud SQL Proxy (for PostgreSQL access):**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/Users/dkulish/Projects/b2b_recs/.gcp/django-service-account.json"
./cloud-sql-proxy memo2-456215:europe-central2:memo2-db --port 5433
```

**Access the application:**
- Web UI: http://127.0.0.1:8000/
- ETL Wizard: http://127.0.0.1:8000/models/1/etl/
