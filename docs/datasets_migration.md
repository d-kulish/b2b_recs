# Dataset Manager Migration Plan

## Document Purpose

This document describes the plan to migrate the Dataset Manager functionality from `model_dataset.html` into `model_configs.html` as a new "Datasets" chapter. This consolidates all configuration work (data, features, models) into a single unified page.

**Created**: 2026-01-12
**Status**: MIGRATION COMPLETE (All 7 Phases Done) + Post-Migration Enhancements
**Last Updated**: 2026-01-13

---

## Background

### The Problem

The current page split between Dataset Manager (`model_dataset.html`) and Configs (`model_configs.html`) is artificial:
- Users need to switch pages frequently when configuring features (Dataset → back → Configs)
- Dataset Manager page appears sparse compared to the Configs page
- Logical workflow suggests these belong together

### The Solution

Move the Dataset Manager UI into the Configs page as the **first of three chapters**:

```
model_configs.html (unified page)
├── Chapter 1: Datasets          ← NEW (moved from model_dataset.html)
│   ├── Header: "Datasets" with [New Dataset] button
│   ├── Dataset list (scrollable cards)
│   └── Full wizard + modals (create, edit, view, delete, SQL preview)
│
├── Chapter 2: Features          (existing, unchanged)
│   ├── Header: "Features" with [New Feature Config] button
│   └── Feature config list + wizard
│
└── Chapter 3: Model Structure   (existing, unchanged)
    ├── Header: "Model Structure" with [New Model Config] button
    └── Model config list + wizard
```

---

## Architecture Analysis

### Dataset Manager Page (`model_dataset.html`)

| Aspect | Details |
|--------|---------|
| **File Size** | ~418KB |
| **Primary Purpose** | Define WHAT data goes into training |
| **Main Components** | Dataset list, 4-step wizard, filter modals |
| **JavaScript State** | `wizardData`, `schemaBuilderState`, `productFiltersState`, `customerFiltersState` |
| **API Endpoints** | ~20+ endpoints in `/datasets/` sub-app |
| **Key Features** | Visual schema builder (SVG), BigQuery table selection, D3.js Pareto charts, session-based preview |

### Configs Page (`model_configs.html`)

| Aspect | Details |
|--------|---------|
| **File Size** | ~462KB |
| **Primary Purpose** | Define HOW to transform data + model architecture |
| **Main Components** | Features chapter (list + 2-step wizard), Model Structure chapter (list + 3-step wizard) |
| **JavaScript State** | `configState`, `mcState`, `allConfigs`, `allModelConfigs`, `allDatasets` |
| **API Endpoints** | ~26+ endpoints in `/configs/` sub-app |
| **Key Features** | Drag-drop column assignment, tensor preview, tower builder, presets |

### Data Model Dependencies

```
Dataset (what data)
    ↓ selected by
FeatureConfig (how to transform)
    ↓ used with
ModelConfig (architecture)
    ↓ combined for
Experiment (training run)
```

---

## What Stays the Same

- **Backend APIs**: No changes to `/datasets/` or `/configs/` sub-apps
- **Dataset Wizard**: Full 4-step wizard functionality (Schema Builder, Filters, etc.)
- **Feature Config Wizard**: Dataset dropdown selection unchanged
- **Old Page**: `model_dataset.html` preserved as rollback option
- **URL Patterns**: Both pages remain accessible during transition

---

## Implementation Phases

### Phase 0: Preparation (Foundation) ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 0.1 | Add namespace prefixes to Dataset Manager JS | Prefix conflicting functions with `ds_` | ✅ Done |
| 0.2 | Add namespace prefixes to Configs page JS | Prefix feature config functions with `fc_` | ✅ Done |
| 0.3 | Identify shared utilities | Listed below | ✅ Done |
| 0.4 | Extract shared CSS classes | Both pages use same CSS files | ✅ Done |

#### Phase 0 Details

**Functions renamed in `model_dataset.html` (ds_ prefix):**
- `ds_loadDatasets()` - Load datasets list
- `ds_openWizard()` - Open dataset wizard
- `ds_closeWizard()` - Close dataset wizard
- `ds_nextStep()` - Wizard next step
- `ds_prevStep()` - Wizard previous step
- `ds_debounceSearch()` - Search debounce
- `ds_escapeHtml()` - HTML escape utility
- `ds_formatNumber()` - Number formatting utility

**Functions renamed in `model_configs.html` (fc_ prefix):**
- `fc_loadDatasets()` - Load datasets for dropdown
- `fc_openWizard()` - Open feature config wizard
- `fc_closeWizard()` - Close feature config wizard
- `fc_nextStep()` - Wizard next step
- `fc_prevStep()` - Wizard previous step
- `fc_debounceSearch()` - Search debounce

**Shared Utilities (to consolidate during merge):**
- `getCookie()` - CSRF token helper (currently only in configs page)
- `escapeHtml()` - HTML escape (exists in both, keep single copy)
- `formatNumber()` - Number formatting (exists in both, keep single copy)
- `showNotification()` / `showToast()` - Notification system (different in each page)

**Shared CSS:**
- Both pages include `css/cards.css` and `css/modals.css`
- No extraction needed - already shared

### Phase 1: Chapter Structure Integration ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 1.1 | Create Datasets chapter container | Added as first chapter in `model_configs.html` | ✅ Done |
| 1.2 | Add chapter header | Title "Datasets" with database icon, filter bar, Refresh/New buttons | ✅ Done |
| 1.3 | Add datasets list container | `#datasetsList` - scrollable container with loading/empty states | ✅ Done |
| 1.4 | Migrate dataset card rendering | `ds_renderDatasetsList()` with card layout showing name, tables, stats | ✅ Done |
| 1.5 | Initialize datasets on page load | `ds_loadDatasets()` called in `DOMContentLoaded` | ✅ Done |

#### Phase 1 Details

**HTML Structure Added:**
- Datasets chapter container with purple gradient icon
- Filter bar: Status dropdown (`#dsStatusFilter`) + Search input (`#dsSearchInput`)
- Action buttons: Refresh, New Dataset
- Scrollable list container with pagination support

**JavaScript Functions Added:**
- `ds_loadDatasets(page)` - Fetch datasets from API with pagination
- `ds_renderDatasetsList(datasets)` - Render dataset cards
- `ds_renderPagination(pagination)` - Render pagination controls
- `ds_refreshDatasets()` - Refresh current page
- `ds_filterDatasets()` - Apply status filter
- `ds_debounceSearch()` - Debounced search (300ms)
- `ds_escapeHtml()`, `ds_formatNumber()` - Utility functions

**Placeholder Functions (for Phase 2-4):**
- `ds_openWizard()` - Dataset creation wizard
- `ds_viewDataset()` - View dataset details
- `ds_editDataset()` - Edit dataset
- `ds_deleteDataset()` - Delete dataset confirmation

### Phase 2: Dataset Wizard Migration ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 2.1 | Add Dataset Wizard modal HTML | 4-step wizard with progress pills | ✅ Done |
| 2.2 | Migrate Step 1 (Basic Info) | Name validation, description | ✅ Done |
| 2.3 | Migrate Step 2 (Source Tables) | Primary/secondary table selection | ✅ Done |
| 2.4 | Migrate Step 3 (Schema Builder) | Column selection with preview | ✅ Done |
| 2.5 | Migrate Step 4 (Filtering) | Date filters, placeholder for Phase 3 modals | ✅ Done |
| 2.6 | Migrate wizard state management | `ds_wizardData`, `ds_schemaBuilderState` | ✅ Done |
| 2.7 | Migrate wizard navigation | Open/close/next/prev/save functions | ✅ Done |

#### Phase 2 Details

**HTML Modals Added:**
- `#dsWizardModal` - Main 4-step dataset wizard
- `#dsNotificationModal` - Auto-closing notifications
- `#dsDeleteModal` - Delete confirmation
- `#dsDetailModal` - View dataset details
- `#dsQueryModal` - View generated SQL

**JavaScript Functions Added (~800 lines):**
- Wizard lifecycle: `ds_openWizard()`, `ds_closeWizard()`, `ds_resetWizard()`
- Navigation: `ds_showStep()`, `ds_nextStep()`, `ds_prevStep()`, `ds_validateCurrentStep()`
- Step 1: `ds_validateDatasetName()` with async name check
- Step 2: `ds_loadBqTables()`, `ds_renderPrimaryTableList()`, `ds_renderSecondaryTableList()`
- Step 3: `ds_loadSchemaBuilder()`, `ds_renderTableCards()`, `ds_onColumnToggle()`
- Step 4: `ds_toggleSubchapter()`, `ds_toggleFilterPopup()`, date filter functions
- Actions: `ds_saveDataset()`, `ds_viewDataset()`, `ds_editDataset()`, `ds_deleteDataset()`
- Query: `ds_viewGeneratedQuery()`, `ds_copyQuery()`
- Notifications: `ds_showNotification()`, `ds_closeNotification()`

**Placeholder Functions (for Phase 3):**
- `ds_openTopProductsModal()` - Top Products filter
- `ds_openTopCustomersModal()` - Top Customers filter
- `ds_openProductMetricsModal()` - Product metrics
- `ds_openCustomerMetricsModal()` - Customer metrics
- `ds_openFilterColumnsModal()` - Column filters
- `ds_openCustomerFilterColumnsModal()` - Customer column filters

### Phase 3: Filter Modals Migration ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 3.1 | Migrate Top Products modal | Revenue column selection, D3.js Pareto chart, threshold slider | ✅ Done |
| 3.2 | Migrate Top Customers modal | Same structure as Top Products for customer filtering | ✅ Done |
| 3.3 | Migrate Product Metrics modal | Transaction count, revenue aggregation filters | ✅ Done |
| 3.4 | Migrate Customer Metrics modal | Transaction count, spending aggregation filters | ✅ Done |
| 3.5 | Migrate Filter Columns modals | Category filters, numeric filters, date filters | ✅ Done |
| 3.6 | Include D3.js dependency | Add script tag if not already present | ✅ Done |

**What was added:**
- D3.js v7 CDN script tag for chart rendering
- 5 filter modals with ds_ prefixed IDs:
  - `dsTopProductsModal` - Pareto chart for top products by revenue
  - `dsTopCustomersModal` - Pareto chart for top customers by revenue
  - `dsProductMetricsModal` - Transaction count and revenue filters
  - `dsCustomerMetricsModal` - Transaction count and spending filters
  - `dsFilterColumnsModal` - Category, numeric, and date filters
- ~1700 lines of filter modal JavaScript including:
  - Filter state management (`ds_productFiltersState`, `ds_customerFiltersState`)
  - D3.js chart functions (`ds_drawRevenueDistributionChart`, `ds_renderCustomerRevenueChart`)
  - Modal open/close/apply functions for all 5 modals
  - API integration for revenue analysis endpoints

### Phase 4: Dataset Actions Migration ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 4.1 | Migrate View modal | Dataset detail display with tables, joins, filters, statistics | ✅ Done |
| 4.2 | Migrate Edit functionality | Opens wizard in edit mode with pre-populated data | ✅ Done |
| 4.3 | Migrate Delete confirmation modal | Warning if dataset has version history | ✅ Done |
| 4.4 | Migrate View SQL modal | Generated query display with copy functionality | ✅ Done |
| 4.5 | Migrate Clone functionality | Creates copy of dataset with new name | ✅ Done |
| 4.6 | Migrate Notification system | Auto-closing success/error/warning notifications | ✅ Done |

**What was added/enhanced:**
- Enhanced `ds_renderDatasetDetail()` with comprehensive display:
  - Tables & Joins section with join keys and types
  - Detailed filters display (dates, customers, products)
  - Column statistics table with type badges
  - Snapshot information and timestamps
- Added Clone functionality:
  - Clone modal (`dsCloneModal`) with name input
  - Clone button on dataset cards
  - Clone button in Detail modal footer
  - `ds_cloneDataset()`, `ds_confirmClone()`, `ds_cloneDatasetFromDetail()` functions
- Existing functionality (already from Phase 2):
  - View/Edit/Delete modals and functions
  - SQL Query preview modal
  - Auto-closing notification system

### Phase 5: Integration & Testing ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 5.1 | Ensure state isolation | Verify opening Dataset wizard doesn't affect Feature/Model wizards | ✅ Done |
| 5.2 | Test schema builder | Verify schema builder functionality | ✅ Done |
| 5.3 | Test filter interactions | Verify D3 charts, filter states, column exclusion | ✅ Done |
| 5.4 | Test create/edit/delete flows | Full CRUD operations for datasets | ✅ Done |
| 5.5 | Test feature config interaction | Verify dataset dropdown loads from shared state | ✅ Done |
| 5.6 | Performance check | Page initialization loads all 3 chapters in parallel | ✅ Done |
| 5.7 | Error handling | Added D3 availability checks, null guards | ✅ Done |

**Integration fixes applied:**
- State isolation verified: Each wizard uses properly prefixed state variables (`ds_`, `fc_`, `mc_`)
- Dataset CRUD now refreshes Feature Config dropdown:
  - `ds_saveDataset()` calls `fc_loadDatasets()` on success
  - `ds_confirmDelete()` calls `fc_loadDatasets()` on success
  - `ds_confirmClone()` calls `fc_loadDatasets()` on success
- Fixed `ds_cloneDatasetFromDetail()` to use `ds_allDatasets` instead of `allDatasets`
- Added D3.js availability checks in chart functions:
  - `ds_drawRevenueDistributionChart()` - checks for D3 and container
  - `ds_renderCustomerRevenueChart()` - checks for D3 and container
  - `ds_updateCustomerRevenueChart()` - checks for D3 availability
- Page initialization loads all chapters in parallel via `DOMContentLoaded`:
  - `ds_loadDatasets()` - Dataset chapter
  - `fc_loadDatasets()` - Feature Config dropdown
  - `loadConfigs()` - Feature Configs
  - `loadModelConfigs()` - Model Configs

### Phase 6: Navigation & URL Updates ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 6.1 | Update sidebar navigation | Merged "Dataset Manager" and "Configs" into "Datasets & Configs" | ✅ Done |
| 6.2 | Add URL redirect | `/models/<id>/dataset/` redirects to `/models/<id>/configs/` | ✅ Done |
| 6.3 | Update breadcrumbs | Page title shows "Datasets & Configs" for both URL names | ✅ Done |

**What was changed:**

1. **Sidebar Navigation (`templates/base_model.html`):**
   - Merged "Dataset Manager" and "Configs" into single "Datasets & Configs" link
   - Link highlights when either `model_configs` or `model_dataset` URL is active
   - Updated breadcrumb/page title in model info tablet to show "Datasets & Configs"

2. **URL Redirect (`ml_platform/datasets/urls.py` + `views.py`):**
   - Added `redirect_to_configs()` view function that redirects to `model_configs`
   - Old `model_dataset` view preserved as `model_dataset_legacy()` for rollback
   - Users visiting `/models/<id>/dataset/` are automatically redirected to `/models/<id>/configs/`

### Phase 7: Documentation & Cleanup ✅ COMPLETED

| # | Task | Details | Status |
|---|------|---------|--------|
| 7.1 | Update README | Documented three-chapter structure, added recent update entry | ✅ Done |
| 7.2 | Update docs/phase_datasets.md | Added "UI Location Update" section noting migration | ✅ Done |
| 7.3 | Update docs/phase_configs.md | Added "Three-Chapter Page Structure" section | ✅ Done |
| 7.4 | Keep model_dataset.html | Added legacy comment block with rollback instructions | ✅ Done |

**Documentation Updated:**
- `README.md` - Updated "Datasets & Configs (Unified Page)" section with chapter descriptions
- `docs/phase_datasets.md` - Added v17 update with UI location change note
- `docs/phase_configs.md` - Added comprehensive three-chapter structure documentation
- `templates/ml_platform/model_dataset.html` - Added legacy comment block at top of file

---

## Critical Implementation Details

### 1. Namespace Prefixes

To prevent JavaScript naming collisions when merging:

```javascript
// Dataset functions (prefix: ds_)
ds_loadDatasets()
ds_renderDatasetsList()
ds_openWizard()
ds_closeWizard()
ds_showStep()
ds_saveDataset()
ds_viewDataset()
ds_editDataset()
ds_deleteDataset()
// ... all dataset-related functions

// Feature Config functions (prefix: fc_)
fc_loadConfigs()
fc_renderConfigs()
fc_openWizard()
fc_saveConfig()
// ... all feature config functions

// Model Config functions (prefix: mc_)
mc_loadModelConfigs()
mc_renderModelConfigs()
mc_openModelConfigWizard()
mc_createModelConfig()
// ... all model config functions
```

### 2. State Variables

```javascript
// Dataset state (prefix: ds_)
let ds_wizardData = {
    name: '',
    description: '',
    primaryTable: null,
    secondaryTables: [],
    joinConfig: {},
    selectedColumns: {},
    columnAliases: {},
    filters: {}
};

let ds_schemaBuilderState = {
    sessionId: null,
    tables: {},
    selectedColumns: {},
    columnAliases: {},
    joins: [],
    connectMode: null,
    previewData: null,
    selectedJoinIndex: null
};

let ds_productFiltersState = { pending: {...}, committed: {...} };
let ds_customerFiltersState = { pending: {...}, committed: {...} };

// Feature config state (prefix: fc_)
let fc_configState = {
    name, description, datasetId, startFrom, cloneFromId,
    customerIdFeature, productIdFeature,
    buyerFeatures, productFeatures,
    buyerCrosses, productCrosses,
    availableColumns, sampleRows, columnOrder,
    targetColumn
};

// Model config state (prefix: mc_)
let mc_state = {
    modelType, name, description, selectedPreset,
    buyerTowerLayers, productTowerLayers,
    retrievalAlgorithm, topK, scannParams,
    ratingHeadLayers, ratingHeadPreset,
    lossFunction, retrievalWeight, rankingWeight,
    outputEmbeddingDim, optimizer, learningRate, batchSize
};
```

### 3. Schema Builder SVG Integration

The Schema Builder (Step 3) is the most complex component:
- SVG overlay for connection lines must position correctly within the modal
- Window resize events must trigger `ds_updateConnectionLines()`
- Column scroll within table cards must update line positions
- Container element IDs must be unique (prefixed)

### 4. D3.js Chart Integration

The Pareto/cumulative revenue charts require:
- D3.js loaded before chart functions are called
- Charts destroyed/recreated when modals close/reopen to prevent memory leaks
- Container element IDs unique (prefix with `ds_`)

### 5. Session-Based Preview Caching

The Schema Builder uses session-based caching:
- `ds_loadSamples()` caches BigQuery data in backend memory
- `ds_generatePreview()` performs pandas joins on cached data
- `ds_cleanupSession()` must be called when wizard closes

### 6. Initialization

```javascript
document.addEventListener('DOMContentLoaded', function() {
    // Load all data in parallel
    Promise.all([
        ds_loadDatasets(),      // Datasets chapter
        fc_loadConfigs(),       // Features chapter
        mc_loadModelConfigs()   // Model Structure chapter
    ]).then(() => {
        console.log('All chapters loaded');
    });
});
```

---

## Estimated Complexity

| Component | Complexity | Lines of Code (approx) |
|-----------|------------|------------------------|
| Datasets chapter container | Low | ~100 lines HTML |
| Dataset list & cards | Medium | ~200 lines JS |
| 4-step Dataset wizard | High | ~3,000 lines JS |
| Schema Builder (Step 3) | Very High | ~1,500 lines JS |
| Filter modals (Step 4) | High | ~2,000 lines JS |
| D3.js Pareto charts | Medium | ~300 lines JS |
| View/Edit/Delete actions | Medium | ~500 lines JS |
| **Total migration** | **High** | **~7,500 lines** |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Large template (~880KB) | Users have modern browsers; caching helps |
| JS namespace collisions | Strict `ds_`/`fc_`/`mc_` prefixes |
| Schema Builder complexity | Careful migration, thorough testing |
| Regression bugs | Keep `model_dataset.html` as rollback |
| Memory pressure | Clear session caches aggressively; dispose D3 charts |
| Browser compatibility | Test on Chrome, Firefox, Safari |

---

## Rollback Plan

If migration fails or causes issues:

1. **Old page preserved**: `model_dataset.html` remains functional
2. **Revert configs page**: Git revert changes to `model_configs.html`
3. **Restore navigation**: Re-enable Dataset Manager link in sidebar
4. **No backend changes**: APIs remain unchanged throughout

---

## Success Criteria

- [x] All three chapters render correctly on page load
- [x] Dataset CRUD operations work (create, view, edit, delete)
- [x] Schema Builder works with SVG connections
- [x] Filter modals work with D3 Pareto charts
- [x] Feature Config wizard can select datasets from new chapter
- [ ] Page load time < 3 seconds (to be verified in production)
- [ ] No JavaScript console errors (to be verified in production)
- [ ] Works on Chrome, Firefox, Safari (to be verified in production)

---

## Post-Migration Enhancements (2026-01-13)

After the initial migration was complete, several enhancements were made to the Schema Builder (Step 3) to fully replicate the original functionality:

### Enhancement 1: Table Card Positioning & Dragging ✅

**Problem**: Table cards in the Schema Builder were stacking on top of each other instead of being positioned side by side.

**Solution**: Added positioning and drag functionality:
- `ds_cardPositions` - Tracks card positions
- `ds_dragState` - Manages drag state (isDragging, table, coordinates)
- `ds_positionCardsInitially()` - Positions cards horizontally with spacing
- `ds_setupDragHandlers()` - Sets up mouse event listeners
- `ds_startDrag()`, `ds_onDragMove()`, `ds_onDragEnd()` - Drag handlers
- Cards are absolutely positioned within a relative container

### Enhancement 2: Table Connection System ✅

**Problem**: No functionality to connect columns between tables for joins.

**Solution**: Implemented full connection system with SVG lines:

**Connection Mode Functions:**
- `ds_onConnectionDotClick()` - Handles clicks on connection dots/plus icons
- `ds_highlightConnectModeElements()` - Highlights valid connection targets
- `ds_handleTargetColumnHover()` - Shows column info on hover during connect mode
- `ds_exitConnectMode()` - Cancels connection mode

**Join Management:**
- `ds_createJoin()` - Creates a join between two columns (ensures primary is always left)
- `ds_removeJoin()` - Removes a join by index
- `ds_setJoinType()` - Changes join type (left/inner/right)
- `ds_showJoinPopover()` - Shows popover for join configuration
- `ds_hideJoinPopover()` - Hides join popover

**SVG Line Drawing:**
- `ds_updateConnectionLines()` - Redraws all connection lines
- `ds_getConnectionSides()` - Determines which side of cards to connect
- `ds_getColumnAnchorPoint()` - Gets exact anchor point for a column
- `ds_drawConnectionLine()` - Draws a single curved connection line
- `ds_createCurvedPath()` - Creates SVG path with bezier curves

**Column Rendering:**
- `ds_renderColumnItem()` - Renders column with connection dot/plus, checkbox, type badge
- Connection dots show: connected (colored), recommended (empty), or plus on hover

### Enhancement 3: Select All Functionality ✅

**Problem**: No way to select/deselect all columns in a table at once.

**Solution**: Added "Select All" row to table cards:
- `ds_toggleAllColumns()` - Toggles all columns in a table
- Select All row appears at top of column list with column count badge
- CSS classes: `.schema-select-all-row`, `.schema-select-all-label`, `.schema-column-count`
- Fixed column list height (200px) for consistent card sizing

### Enhancement 4: Join Type Switching ✅

**Problem**: Join type options (left/inner/right) in popover weren't switchable.

**Solution**:
- Made join type options clickable with `ds_setJoinType()` handler
- Added CSS for checkmark visibility (hidden by default, visible when `.active`)
- Clicking a join type updates the join and refreshes preview

### Enhancement 5: Preview Table ✅

**Problem**: Preview table wasn't showing sample data after joins.

**Solution**: Implemented full preview functionality:
- `ds_debouncedRefreshPreview()` - Debounced wrapper (500ms) to prevent API spam
- `ds_refreshPreview()` - Makes POST request to `/api/models/${modelId}/datasets/preview/`
- `ds_renderPreview()` - Renders preview table with headers and rows
- `ds_renderPreviewEmpty()` - Shows empty state when no data
- `ds_renderPreviewError()` - Shows error state

**Preview displays:**
- Row count and column count stats
- Warnings (null counts, join issues)
- Scrollable data table with column headers
- Updates automatically when columns selected or joins changed

### Enhancement 6: Debug Logging (Development) 🔧

Added comprehensive logging to diagnose join issues:

**Frontend (Browser Console):**
```javascript
console.log('[DS Join] Creating join - Input:', {...});
console.log('[DS Preview] Session ID:', ...);
console.log('[DS Preview] Joins:', ...);
console.log('[DS Preview] Response:', ...);
```

**Backend (Server Logs):**
```python
logger.info(f"[Preview] Session {session_id}: Tables in cache: {tables}")
logger.info(f"[Preview Join] left_join_col: {col}, right_join_col: {col}")
logger.info(f"[Preview Join] Sample left values: {values}")
logger.info(f"[Preview Join] Merge completed: {before} rows -> {after} rows")
```

### CSS Updates (modals.css)

New classes added for Schema Builder enhancements:
- `.schema-select-all-row` - Select All row styling
- `.schema-select-all-label` - Label styling
- `.schema-column-count` - Column count badge
- `.schema-column-list` - Fixed 200px height, overflow-y scroll
- `.join-popover-option i.fa-check` - Hidden by default
- `.join-popover-option.active i.fa-check` - Visible when active

### Files Modified

| File | Changes |
|------|---------|
| `templates/ml_platform/model_configs.html` | +500 lines: positioning, connections, SVG, preview |
| `static/css/modals.css` | +50 lines: Select All, join popover styles |
| `ml_platform/datasets/preview_service.py` | +20 lines: debug logging |

---

## Bug Fixes (2026-01-13)

After testing the migration, several bugs were identified and fixed:

### Fix 1: Excessive Logging in Preview Service ✅

**Problem**: The Schema Builder preview was generating huge JSON outputs in server logs with column names and sample values.

**Solution**: Removed debug logging statements from `ml_platform/datasets/preview_service.py`:
- Removed `[Preview]` prefix logs (session info, tables, joins)
- Removed `[Preview Join]` prefix logs (column names, sample values, merge stats)
- Kept error logging for actual failures

### Fix 2: 400 Error on Dataset Save ✅

**Problem**: Saving a dataset at Step 4 (Filter) returned a 400 Bad Request error.

**Root Cause**: The frontend was sending `join_config` as an array format, but the backend validation expected a dictionary format.

**Solution**: Added `ds_convertJoinsToConfig()` function to convert the array format to dict format:
```javascript
// From: [{leftTable, rightTable, leftCol, rightCol, type}, ...]
// To: {rightTable: {join_key, primary_column, secondary_column, join_type}, ...}
```

### Fix 3: Schema Builder State Not Resetting on New Wizard ✅

**Problem**: When creating a second dataset after the first, the wizard showed stale table selections and threw errors.

**Root Cause**: Two issues:
1. `dsSchemaLoading` element was inside `dsSchemaCardsContainer` and got destroyed when innerHTML was replaced
2. `ds_renderSecondaryTableList()` wasn't called when loading BQ tables

**Solution**:
- Moved `dsSchemaLoading` element outside `dsSchemaCardsContainer` (sibling instead of child)
- Added `ds_renderSecondaryTableList()` call to `ds_loadBqTables()` to clear stale checkboxes

### Fix 4: Tables Not Updating When Returning to Step 3 ✅

**Problem**: When going back to Step 2 to add/remove tables, then returning to Step 3, the Schema Builder didn't show the updated tables.

**Root Cause**: `ds_schemaBuilderState.sessionId` was only cleared on wizard reset, not when tables changed.

**Solution**: Added `ds_schemaBuilderState.sessionId = null;` to:
- `ds_onPrimaryTableSelect()` - when primary table changes
- `ds_onSecondaryTableToggle()` - when secondary tables are added/removed

This forces the Schema Builder to reload when returning to Step 3 after table changes.

### Fix 5: Dataset Summary Not Loading at Step 4 ✅

**Problem**: The Dataset Summary panel at Step 4 showed "Apply filters and refresh" but never loaded statistics.

**Root Cause**: Missing Step 4 initialization - no code to fetch column analysis or call the stats API.

**Solution**:
1. Added `ds_fetchColumnAnalysis()` - fetches column types from `/api/models/${modelId}/datasets/analyze-columns/`
2. Added `ds_loadDatasetStats()` - fetches stats from `/api/models/${modelId}/datasets/stats/`
3. Added `ds_renderDatasetStats()` - renders stats matching original design (filter badges + column table)
4. Updated `ds_nextStep()` to call these functions when entering Step 4

### Fix 6: Dataset Summary Wrong Design ✅

**Problem**: The Dataset Summary was showing custom cards (Total Rows, Unique Customers, Unique Products) instead of the original design.

**Solution**: Updated to match original `model_dataset.html` design:
- Header with total rows badge
- Filter badges (Dates, Customers, Products) with active state
- Column stats table with Column, Data Type, Statistics columns
- Added `ds_formatColumnStats()` helper for type-aware formatting

### Fix 7: Timestamp Column Dropdown Empty ✅

**Problem**: The "Select timestamp column" dropdown was empty - no date columns shown.

**Root Cause**: Missing column analysis step that fetches column types to filter for DATE/TIMESTAMP columns.

**Solution**:
1. Added `ds_fetchColumnAnalysis()` - fetches column type info via API
2. Added `ds_populateFilterColumnDropdowns()` - populates timestamp dropdown with only DATE/DATETIME/TIMESTAMP/TIME columns
3. Added `ds_populateProductFilterDropdowns()` - populates product/revenue dropdowns
4. Updated `ds_nextStep()` to call `ds_fetchColumnAnalysis().then(() => ds_populateFilterColumnDropdowns())` when entering Step 4

### Fix 8: Rolling Window and Start Date Popups Not Working ✅

**Problem**: Clicking "Rolling Window" or "Start Date" buttons did nothing.

**Root Cause**:
1. `ds_toggleFilterPopup()` was using `classList.toggle('hidden')` instead of `classList.toggle('show')`
2. CSS uses `.filter-popup.show { display: block; }` not `.hidden` removal
3. Missing popup positioning logic

**Solution**:
1. Rewrote `ds_toggleFilterPopup()` to use `.show` class and fixed positioning
2. Rewrote `ds_closeFilterPopup()` to use `.show` class
3. Added click-outside handler to close popups
4. Added `ds_historyFilterMode` state tracking ('rolling' or 'startDate')
5. Added `ds_datesFilterState` for pending/committed state management
6. Added `ds_updateDatesRefreshButtonState()` to enable/disable Refresh button
7. Added `ds_updateDatesFilterSummary()` to show filter summary text

### Fix 9: Dates Refresh Dataset Button Not Deactivating ✅

**Problem**: After clicking "Refresh Dataset" in the Dates filter, the button remained active instead of becoming disabled.

**Root Cause**:
1. `ds_updateDatesRefreshButtonState()` only checked if timestamp was selected, not if there were changes
2. `ds_refreshDatasetHistory()` didn't commit pending state or call button state update

**Solution**:
1. Updated `ds_updateDatesRefreshButtonState()` to compare `pending` vs `committed` state:
   ```javascript
   const pendingJson = JSON.stringify(pendingState);
   const committedJson = JSON.stringify(ds_datesFilterState.committed);
   const hasChanges = pendingJson !== committedJson;
   const shouldEnable = hasTimestamp && hasChanges;
   ```
2. Updated `ds_refreshDatasetHistory()` to commit state and update button
3. Added `ds_restoreDatesFilterState()` for edit mode restoration
4. Added filter state reset in `ds_resetWizard()`

### Fix 10: Products/Customers Refresh Buttons Not Working ✅

**Problem**: The "Refresh Dataset" buttons in Products and Customers sub-chapters never activated when filters were applied.

**Root Cause**:
1. Missing `ds_updateProductsRefreshButtonState()` and `ds_updateCustomersRefreshButtonState()` functions
2. `ds_refreshProductFilters()` and `ds_refreshCustomerFilters()` were stubs that only showed notifications
3. Summary update functions didn't call button state updates

**Solution**:
1. Added `ds_updateProductsRefreshButtonState()` - compares pending vs committed state
2. Added `ds_updateCustomersRefreshButtonState()` - compares pending vs committed state
3. Rewrote `ds_refreshProductFilters()` - commits state, saves to wizardData, updates summary
4. Rewrote `ds_refreshCustomerFilters()` - commits state, saves to wizardData, updates summary
5. Added helper functions: `ds_buildProductFilterConfig()`, `ds_buildCustomerFilterConfig()`
6. Added status functions: `ds_updateProductsFilterStatus()`, `ds_updateCustomersFilterStatus()`
7. Updated `ds_resetWizard()` to reset `ds_productFiltersState` and `ds_customerFiltersState`

### Fix 11: Filters Not Applied to Dataset Summary ✅

**Problem**: Clicking "Refresh Dataset" deactivated the button but the Dataset Summary didn't reflect the filter changes.

**Root Cause**: `ds_buildFiltersPayload()` was using wrong structure:
- Was: `{ customer_filter: { type: 'top_revenue', customer_column: ... } }` (flat)
- Expected: `{ customer_filter: { top_revenue: { customer_column: ... } } }` (nested)

**Solution**: Rewrote `ds_buildFiltersPayload()` to:
1. Read from committed state instead of UI elements
2. Use nested structure for `top_revenue` objects
3. Support all filter types: aggregation, category, numeric filters
4. Match the original `model_dataset.html` API payload structure

### Fix 12: Filter Columns Modal Not Showing Values ✅

**Problem**: Selecting a column (e.g., "city") in the Filter Columns modal didn't show available values to select.

**Root Cause**:
1. `ds_onFilterColumnSelect()` wasn't async and didn't fetch column analysis
2. Used basic column type (STRING) instead of `filter_type` from analysis (category)
3. Missing functions to populate category values list

**Solution**:
1. Made `ds_onFilterColumnSelect()` async with `await ds_fetchColumnAnalysis()`
2. Added `ds_showFilterConfigForType()` - routes to appropriate config function
3. Added `ds_showCategoryFilterConfig()` - populates values with checkboxes or autocomplete
4. Added `ds_showNumericFilterConfig()` - shows range stats and inputs
5. Added `ds_showDateFilterConfig()` - shows date range stats
6. Added helper functions: `ds_filterCategoryValues()`, `ds_toggleCategoryValue()`, `ds_searchCategoryValues()`

### Fix 13: Filter Columns Apply Saving 0 Values ✅

**Problem**: After selecting values and clicking Apply, the filter showed "Include: 0 values".

**Root Cause**: `ds_applyFilterColumnsModal()` had `values: []` hardcoded instead of collecting selected values.

**Solution**: Updated to collect values from:
- Checkboxes (list mode): `#dsNewCategoryValuesList input[type="checkbox"]:checked`
- Tags (autocomplete mode): `#dsCategorySelectedTags .category-tag`

### Fix 14: Customer Filters Going to Wrong State ✅

**Problem**: Filters created in Customers sub-chapter were being added to Products state.

**Root Cause**: Single Filter Columns modal was always adding to `ds_productFiltersState` regardless of which sub-chapter opened it.

**Solution**:
1. Added `ds_filterColumnsContext` variable to track which sub-chapter opened the modal
2. Updated `ds_openFilterColumnsModal()` to set context to 'product'
3. Updated `ds_openCustomerFilterColumnsModal()` to set context to 'customer'
4. Updated `ds_renderExistingFilters()` to read from correct state based on context
5. Updated `ds_applyFilterColumnsModal()` to add filters to correct state and call correct summary function

### Fix 15: Dataset Snapshot Not Saved ✅

**Problem**: Newly created datasets showed "N/A" for Rows and Columns on the card, and "No summary snapshot available" when clicking View.

**Root Cause**: The migrated `ds_saveDataset()` function was missing the `summary_snapshot` field in the payload:
1. No `ds_datasetStatsData` variable to store fetched stats
2. No snapshot building code before save
3. Missing `summary_snapshot` field in the save payload

**Solution**:
1. Added `let ds_datasetStatsData = null;` global variable (line 7016)
2. Store stats when fetched: `ds_datasetStatsData = data;` in `ds_loadDatasetStats()` success handler (line 9187)
3. Build snapshot in `ds_saveDataset()`:
   ```javascript
   const summarySnapshot = ds_datasetStatsData ? {
       total_rows: ds_datasetStatsData.summary?.total_rows || 0,
       filters_applied: ds_datasetStatsData.filters_applied || {},
       column_stats: ds_datasetStatsData.column_stats || {},
       snapshot_at: new Date().toISOString()
   } : {};
   ```
4. Include `summary_snapshot: summarySnapshot` in payload
5. Reset variable in `ds_resetWizard()`: `ds_datasetStatsData = null;`

### Fix 16: Edit Mode Not Restoring Schema/Filters ✅

**Problem**: When editing an existing dataset, Step 3 (Schema Builder) showed no selected columns and Step 4 showed no restored filters.

**Root Cause**: `ds_loadDatasetForEdit()` was incomplete:
1. Missing: `joinConfig`, `selectedColumns`, `columnAliases` restoration to `ds_wizardData`
2. Missing: `selectedColumns`, `columnAliases`, `joins` restoration to `ds_schemaBuilderState`
3. Missing: Product and customer filter state restoration functions
4. `ds_collectStepData(4)` was overwriting all filters instead of merging

**Solution**:

**A. Fixed `ds_loadDatasetForEdit()` (lines 11976-12015):**
```javascript
// Added missing field restorations
ds_wizardData.joinConfig = ds.join_config || {};
ds_wizardData.selectedColumns = ds.selected_columns || {};
ds_wizardData.columnAliases = ds.column_aliases || {};

// Restore schema builder state
ds_schemaBuilderState.selectedColumns = {...ds_wizardData.selectedColumns};
ds_schemaBuilderState.columnAliases = {...ds_wizardData.columnAliases};
ds_schemaBuilderState.joins = ds_convertJoinConfigToArray(ds_wizardData.joinConfig, ds_wizardData.primaryTable);
```

**B. Added `ds_convertJoinConfigToArray()` helper (lines 12017-12039):**
Converts DB join_config dict format to schema builder joins array format.

**C. Fixed `ds_collectStepData()` case 4 (lines 7301-7328):**
- Changed from overwriting to merging filters
- Changed key from `dates` to `history` (matching DB format)
- Changed to snake_case property names (`timestamp_column`, `rolling_days`)
- Uses committed state from `ds_datesFilterState`

**D. Added filter restoration functions:**
- `ds_restoreProductFilterState()` (lines 8948-8990) - restores product filter state
- `ds_restoreCustomerFilterState()` (lines 8996-9038) - restores customer filter state
- Updated `ds_restoreDatesFilterState()` to also set pending state (line 8941)

**E. Updated Step 4 initialization (lines 7274-7276):**
```javascript
ds_restoreDatesFilterState();
ds_restoreProductFilterState();
ds_restoreCustomerFilterState();
```

### Files Modified for Bug Fixes

| File | Changes |
|------|---------|
| `ml_platform/datasets/preview_service.py` | Removed excessive debug logging |
| `templates/ml_platform/model_configs.html` | Fixed join_config format, Schema Builder state management, Dataset Summary, column dropdowns, filter popups, Refresh button states, filter payload structure, Filter Columns modal functionality, context-aware filtering, **snapshot save**, **edit mode restoration** |

---

## Known Issues - Pending Fix (2026-01-13)

### Issue 17: Filters Saved with Wrong Structure (Requires Browser Refresh)

**Problem**: Dataset 19 was saved with `filters.dates` (camelCase) instead of `filters.history` (snake_case), despite Fix 16 being deployed.

**Analysis**:

Comparing datasets:
```
Dataset 16 (correct):          Dataset 19 (wrong):
filters: {                     filters: {
  "history": {                   "dates": {
    "rolling_days": 90,            "rollingDays": 31,
    "timestamp_column": "..."      "timestampColumn": "..."
  }                              }
}                              }
```

**Root Cause Investigation**:

1. **Code Verification**: The fix IS in the codebase - `ds_collectStepData(4)` correctly sets `filters.history` with snake_case keys
2. **Database Evidence**: Dataset 19 has the OLD format (camelCase `dates` key) that was removed from the code
3. **Likely Cause**: Browser cached old JavaScript when dataset 19 was created

**Action Required**:
- Users must **hard refresh** the browser (Cmd+Shift+R / Ctrl+Shift+R) after deployment
- Server must be restarted to ensure templates are reloaded

### Issue 18: Dates Filter Not Saved Without "Refresh Dataset" Click

**Problem**: If user selects a timestamp column and rolling days but does NOT click "Refresh Dataset", the filter won't be saved.

**Root Cause**: Current `ds_collectStepData(4)` implementation:
```javascript
const datesCommitted = ds_datesFilterState.committed;
if (datesCommitted.timestampColumn) {  // Only runs if committed state exists
    ds_wizardData.filters.history = {...};
}
```

The code only reads from COMMITTED state, which is empty until user clicks "Refresh Dataset".

**Expected Behavior**: Filter should be saved based on UI selections even without explicit "Refresh Dataset" click.

**Fix Plan**:
1. In `ds_collectStepData(4)`, fall back to UI element values if committed state is empty:
```javascript
// Get from committed state first, fall back to UI elements
const timestampColumn = datesCommitted.timestampColumn ||
    document.getElementById('dsTimestampColumn')?.value;
const rollingDays = datesCommitted.rollingDays ||
    parseInt(document.getElementById('dsRollingDays')?.value) || 30;
const startDate = datesCommitted.startDate ||
    document.getElementById('dsStartDateInput')?.value;

if (timestampColumn) {
    ds_wizardData.filters.history = {
        timestamp_column: timestampColumn,
        rolling_days: rollingDays,
        start_date: startDate || null
    };
}
```

### Issue 19: column_aliases Saved as None

**Problem**: Dataset 19 has `column_aliases: None` instead of `{}` or actual aliases.

**Analysis**:
- Save payload code: `column_aliases: ds_schemaBuilderState.columnAliases || {}`
- This should save at least `{}` if no renaming was done
- `None` in Python means the field wasn't in the request OR was explicitly `null`

**Possible Causes**:
1. `ds_schemaBuilderState.columnAliases` is `null` (not `undefined`) - `null || {}` returns `null` in JavaScript!
2. JSON serialization of `null` becomes Python `None`

**Fix Plan**:
```javascript
// Current (buggy):
column_aliases: ds_schemaBuilderState.columnAliases || {},

// Fixed (handles null explicitly):
column_aliases: ds_schemaBuilderState.columnAliases ?? {},
// OR
column_aliases: ds_schemaBuilderState.columnAliases || ds_wizardData.columnAliases || {},
```

### Implementation Plan for Issues 17-19

| Step | Task | Priority |
|------|------|----------|
| 1 | Fix `ds_collectStepData(4)` to fall back to UI elements for dates filter | High |
| 2 | Fix `column_aliases` to use nullish coalescing (`??`) instead of OR (`||`) | High |
| 3 | Add deployment note: require browser hard refresh after deployment | Medium |
| 4 | Test: Create new dataset without clicking "Refresh Dataset" | High |
| 5 | Test: Verify column_aliases saves as `{}` not `None` | High |

---

## References

- `templates/ml_platform/model_dataset.html` - Source page (to migrate from)
- `templates/ml_platform/model_configs.html` - Target page (to migrate to)
- `ml_platform/datasets/api.py` - Dataset API endpoints
- `ml_platform/configs/api.py` - Configs API endpoints
- `docs/phase_datasets.md` - Dataset domain specification
- `docs/phase_configs.md` - Configs domain specification
