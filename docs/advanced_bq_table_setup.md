# Advanced BigQuery Table Setup

## Overview

This document describes a future enhancement to the ETL system that allows users to load data into existing BigQuery tables instead of always creating new ones.

## Current Behavior

Currently, the ETL Wizard (Step 3-4) always creates a **new BigQuery table** when setting up an ETL job:

```
ETL Wizard Flow:
Step 1: Select Connection
Step 2: Choose Source Table
Step 3: Preview & Select Columns
Step 4: Configure Load Strategy → Creates NEW BigQuery table
Step 5: Set Schedule
```

## The Problem

This creates issues in several real-world scenarios:

### Scenario A: Connection Credential Rotation
- User has `production_db` connection loading to `bq.transactions` (20M rows)
- Database credentials are rotated, user creates new `production_db_v2` connection
- User wants to continue loading to the same `bq.transactions` table
- **Currently impossible** - wizard forces new table creation

### Scenario B: Resume Failed Migration
- User started ETL, loaded 15M of 20M rows
- Something broke, job was deleted
- User wants to create new job pointing to same destination table
- **Currently impossible**

### Scenario C: Multiple Sources to One Table
- User has EU database and US database
- Both should load into single `bq.global_transactions` table
- **Currently impossible**

### Scenario D: Schema Evolution
- User adds new columns to source table
- Wants to add those columns to existing BigQuery table
- Current workaround: Edit job and add columns (implemented)
- But if job is deleted, cannot recreate pointing to same table

## Proposed Solution

### Option A: Add "Use Existing Table" Mode to ETL Wizard

Modify Step 3 or 4 of the wizard to offer a choice:

```
Step 3/4: Destination Table
  ○ Create new table (default)
  ○ Use existing BigQuery table ← NEW OPTION
    └── [Dropdown: Select from existing tables in dataset]
    └── [Validation: Schema compatibility check]
```

### Implementation Requirements

#### 1. Schema Validation Logic
When user selects an existing table, the system must validate:

- **Source columns must be mappable to destination columns**
  - Same name match
  - Compatible data types (e.g., INT → INT64, VARCHAR → STRING)

- **Handle missing columns gracefully**
  - Source columns not in destination: Show warning, can be added via ALTER TABLE
  - Destination columns not in source: Will be NULL for new rows

#### 2. UI Changes

**Wizard Step 3/4:**
```html
<div class="destination-mode-selector">
  <label>
    <input type="radio" name="destMode" value="new" checked>
    Create new BigQuery table
  </label>
  <label>
    <input type="radio" name="destMode" value="existing">
    Use existing BigQuery table
  </label>
</div>

<div id="existingTableSelector" class="hidden">
  <select id="existingTableDropdown">
    <!-- Populated via API -->
  </select>

  <div id="schemaCompatibilityReport">
    <!-- Shows compatibility analysis -->
  </div>
</div>
```

#### 3. New API Endpoints Required

```
GET /api/etl/datasets/<dataset>/tables/
    Returns list of existing tables in a BigQuery dataset

POST /api/etl/validate-schema-compatibility/
    Body: { source_columns: [...], destination_table: "..." }
    Returns: { compatible: true/false, warnings: [...], can_alter: [...] }
```

#### 4. Backend Changes

**In `api_etl_create_job` (views.py):**
```python
# Check if using existing table
if data.get('use_existing_table'):
    existing_table = data.get('existing_table_name')

    # Validate schema compatibility
    compatibility = validate_schema_compatibility(
        source_columns=selected_columns,
        dest_table=existing_table
    )

    if not compatibility['compatible']:
        return JsonResponse({
            'status': 'error',
            'message': 'Schema incompatible',
            'details': compatibility['errors']
        })

    # Don't create table, just configure ETL to use existing one
    dest_table_name = existing_table
else:
    # Current behavior - create new table
    dest_table_name = create_bigquery_table(...)
```

## Schema Compatibility Rules

| Source Type | BigQuery Type | Compatible |
|-------------|---------------|------------|
| INTEGER | INT64 | Yes |
| VARCHAR/TEXT | STRING | Yes |
| DECIMAL | NUMERIC/FLOAT64 | Yes |
| BOOLEAN | BOOL | Yes |
| TIMESTAMP | TIMESTAMP | Yes |
| DATE | DATE | Yes |
| JSON | STRING/JSON | Yes |
| ARRAY | REPEATED | Conditional |

### Incompatible Scenarios
- Narrowing types (STRING → INT64) - Requires data validation
- Removing NOT NULL constraint from destination
- Primary key mismatches

## Alternative: "Reconnect Job" Feature

Instead of modifying the wizard, add a separate action to existing jobs:

```
Job Actions: [Run Now] [Edit] [Reconnect] [Pause] [Delete]
```

**"Reconnect" Flow:**
1. Select new connection
2. Select source table
3. System validates schema compatibility with existing BigQuery table
4. Updates `DataSource.connection` without touching BigQuery table

### Pros/Cons

| Approach | Pros | Cons |
|----------|------|------|
| Wizard "Use Existing" | Single unified flow | More complex wizard UI |
| "Reconnect" action | Simpler, targeted | Another action to learn |

## Next Steps

1. **Phase 1: Design Review**
   - Finalize which approach (Wizard vs Reconnect)
   - Define exact schema compatibility rules
   - Design UI mockups

2. **Phase 2: Backend Implementation**
   - Add API endpoints for listing tables
   - Implement schema compatibility validation
   - Modify job creation logic

3. **Phase 3: Frontend Implementation**
   - Add UI for selecting existing tables
   - Show compatibility warnings
   - Handle edge cases

4. **Phase 4: Testing**
   - Test with various schema combinations
   - Test credential rotation scenario
   - Test multi-source to single table scenario

## Related Files

- `ml_platform/views.py` - API endpoints
- `ml_platform/utils/connection_manager.py` - Schema fetching
- `templates/ml_platform/model_etl.html` - Wizard UI
- `etl_runner.md` - ETL system documentation

## Priority

**Medium** - This is an enhancement for advanced use cases. The current Edit functionality (added in this release) addresses the most common need of modifying schedules and columns on existing jobs.
