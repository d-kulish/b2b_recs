# Next Steps: ETL & Connection Management System

**Last Updated:** November 16, 2025

---

## Current Status

- ✅ **Simplified 3-Step ETL Wizard** - streamlined from 5 steps to 3 steps (40% reduction)
- ✅ **Standalone Connection Management** - 2-step wizard with category tabs for independent connection creation
- ✅ **Complete Separation** - Connections managed independently from ETL jobs
- ✅ **22 Data Source Types** - PostgreSQL, MySQL, Oracle, SQL Server, MongoDB, BigQuery, Snowflake, and more
- ✅ Real database connection testing (PostgreSQL, MySQL, BigQuery)
- ✅ Secure credential storage in GCP Secret Manager
- ✅ **Connection Reuse** - Select from existing connections at Step 1
- ✅ **Test-First Pattern** - Connection test before save (no premature Secret Manager writes)
- ✅ **Smart Button States** - Grey→White reactive navigation, disabled states prevent errors
- ✅ **Beautiful Error Notifications** - User-friendly messages with proper formatting
- ✅ **Duplicate Detection** - Name and credential uniqueness with helpful error messages
- ✅ **Field Change Detection** - Save disabled if credentials edited after successful test
- ✅ **Atomic ETL Creation** - No draft saves until final step
- ✅ **Live Status Indicators** - Green/red/yellow dots with intelligent error handling
- ✅ **Category-Based UI** - Relational DB/Files/NoSQL tabs with tile-based selection
- ✅ **Clean Data Model** - Removed deprecated fields from DataSource
- ✅ **Connection Tracking** - last_used_at field tracks ETL job usage
- ✅ **Professional UX** - Smooth animations, hover effects, consistent modal sizing
- ✅ **Standardized Buttons** - Consistent styling using buttons.css across all UI elements
- ✅ **Debug Logging** - Comprehensive console logs for troubleshooting connection issues
- ✅ **Manual Refresh** - Refresh button to re-test connections on demand
- ✅ **Status Timestamps** - "Tested 5m ago" display on connection cards
- ✅ **Modern Connection Cards** - Minimalistic 3-column design with optimized space usage
- ✅ **Reusable Card System** - cards.css for consistent tablet/card design across platform

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

**ETL Job Creation Flow (3 Steps):**
```
Click "+ ETL Job" →
Step 1: Select existing connection (with live status indicator) + Enter job name →
Step 2: Select table from database (auto-fetched from selected connection) →
Step 3: Configure sync mode (replace/incremental/append) + Schedule + Review summary →
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

### 🎯 Milestone 11: Production Readiness (Future)
- [ ] Test with MySQL database connection
- [ ] Test with BigQuery dataset
- [ ] Add SQL Server support if needed
- [ ] Build ETL container (etl_runner.py) for actual data extraction
- [ ] Create Dockerfile for Cloud Run deployment
- [ ] Set up Cloud Scheduler for automated runs
- [ ] Add comprehensive logging and error tracking

---

## What We Accomplished

**Milestones 1-10 Complete!**

✅ Real database connection testing (PostgreSQL, MySQL, BigQuery)
✅ Secure credential storage in GCP Secret Manager
✅ **Simplified 3-Step ETL Wizard** - streamlined from 5 steps to 3 (40% faster)
✅ **Standalone Connection Management** - 2-step wizard with category tabs
✅ **Complete Architecture Separation** - Connections and ETL jobs managed independently
✅ **Connection Reuse Pattern** - Select from existing connections, no credential re-entry
✅ **Test-First Pattern** - Connection test before Secret Manager save (no premature writes)
✅ **Atomic ETL Creation** - No draft saves until final step (cleaner flow)
✅ **Clean Data Model** - Removed deprecated DataSource fields (simplified schema)
✅ **Connection Tracking** - last_used_at field updated on ETL job creation
✅ Auto-test saved connections to fetch table list in background
✅ Real table metadata displayed in wizard (names, row counts, last updated)
✅ Inline error messages with proper UX
✅ Cloud SQL Proxy integration for secure database access
✅ **Edit/Restore ETL Jobs** - click Edit to resume wizard at last step + 1
✅ **Loading State Management** - animated spinner + disabled navigation during async operations
✅ **Standalone Connections Management UI** - 2-column layout with dedicated connections section
✅ **Connection CRUD** - Create, Edit, Delete connections independently from ETL jobs
✅ **Live Connection Status** - Auto-tested green/red status indicators
✅ **Protected Deletion** - Blocks deletion of connections with dependent jobs
✅ **Category-Based Selection** - Relational DB/Files/NoSQL tabs with tile-based database picking
✅ **Fixed Connection Status Bug** - Proper green/red/yellow indicators with intelligent error handling
✅ **Standardized Button Styling** - Consistent buttons using buttons.css system
✅ **Manual Refresh** - Re-test connections on demand with spinning animation
✅ **Status Timestamps** - "Tested 5m ago" display for freshness awareness
✅ **Comprehensive Debug Logging** - Console logs with emoji indicators for troubleshooting
✅ **Modern Connection Cards** - Minimalistic 3-column design (60% + 30% + 10%)
✅ **Reusable Card System** - cards.css for consistent design across platform
✅ **Optimized Space Usage** - 2-row layout, no wasted whitespace
✅ **Text Truncation** - Ellipsis for long names, prevents overflow

**Next Steps:** Testing and validation, then Milestone 11 - Production readiness and deployment

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
