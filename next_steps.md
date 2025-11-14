# Next Steps: ETL & Connection Management System

**Last Updated:** November 14, 2025

---

## Current Status

- ✅ UI wizard is complete and functional
- ✅ Real database connection testing (PostgreSQL, MySQL, BigQuery)
- ✅ Secure credential storage in GCP Secret Manager
- ✅ **Connection Management System** - reusable named connections across ETL jobs
- ✅ **Connection Naming** - obligatory unique names with validation
- ✅ **ETL Job Naming** - duplicate job name validation at Step 1
- ✅ **Draft ETL Jobs** - saved at Step 2 (after connection test)
- ✅ Step 3 shows real tables from database with metadata
- ✅ Connection reuse - auto-populate and fetch tables for saved connections
- ✅ **Edit/Restore ETL Jobs** - resume wizard from last completed step
- ✅ **Loading States** - visual feedback with disabled navigation during async operations
- ✅ **Wizard Step Tracking** - wizard_last_step and wizard_completed_steps in DataSource model

---

## Solution Overview

**What we've built:**
1. **Connection Management** - Named, reusable database connections
2. **Real Database Testing** - Connect to PostgreSQL, MySQL, BigQuery
3. **Secure Credentials** - Store passwords in GCP Secret Manager
4. **ETL Job Wizard** - 5-step wizard to create ETL jobs
5. **Draft System** - Save job drafts at Step 2, finalize at Step 5

**ETL Wizard Flow:**
```
Step 1: Select source type + Job name (validate uniqueness) →
        Option: Reuse saved connection OR create new connection →
Step 2: Enter/view connection details + Connection name →
        Test connection → Auto-save draft ETL job →
Step 3: Select table from real database →
Step 4: Configure sync mode (replace/incremental/append) →
Step 5: Review and create (finalize ETL job)
```

**Connection Reuse Flow:**
```
User creates connection "Production PostgreSQL" →
Connection saved with encrypted credentials in Secret Manager →
Next ETL job: User selects "Production PostgreSQL" at Step 1 →
Step 2 auto-populates connection details (read-only) →
Auto-tests connection in background to fetch tables →
Proceeds to Step 3 with table list ready
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

### 🎯 Milestone 6: Advanced Connection Management (Next Phase)
- [ ] Add Edit button to saved connection cards
- [ ] Create Edit Connection modal with pre-filled form
- [ ] Add backend endpoint for updating connection credentials
- [ ] Show affected jobs count when editing connection
- [ ] Require connection re-test before saving edits
- [ ] Add Delete connection functionality (with cascade warnings)
- [ ] Add connection usage analytics (last used, job count)

### 🎯 Milestone 7: Production Readiness (Future)
- [ ] Test with MySQL database connection
- [ ] Test with BigQuery dataset
- [ ] Add SQL Server support if needed
- [ ] Build ETL container (etl_runner.py) for actual data extraction
- [ ] Create Dockerfile for Cloud Run deployment
- [ ] Set up Cloud Scheduler for automated runs
- [ ] Add comprehensive logging and error tracking

---

## What We Accomplished

**Milestones 1-5 Complete!**

✅ Real database connection testing (PostgreSQL, MySQL, BigQuery)
✅ Secure credential storage in GCP Secret Manager
✅ **Connection Management System** - reusable named connections
✅ **Connection Naming** - obligatory unique names with auto-suggestion
✅ **ETL Job Naming** - duplicate validation at Step 1 prevents UNIQUE constraint errors
✅ **Draft ETL Jobs** - correctly saved at Step 2 after connection test
✅ Connection reuse - select saved connection at Step 1, auto-populate details
✅ Auto-test saved connections to fetch table list in background
✅ Real table metadata displayed in wizard (names, row counts, last updated)
✅ Inline error messages with proper UX
✅ Cloud SQL Proxy integration for secure database access
✅ Fixed wizard step navigation (nextStep() handles all steps)
✅ **Edit/Restore ETL Jobs** - click Edit to resume wizard at last step + 1
✅ **Loading State Management** - animated spinner + disabled navigation during async operations
✅ **Proper CREATE vs EDIT separation** - no duplicate UNIQUE errors in edit mode
✅ **Auto-fetch tables in edit mode** - uses stored credentials from Secret Manager

**Next Steps:** Milestone 6 - Advanced connection editing and management features

---

## Key Files Modified

```
ml_platform/utils/connection_manager.py    ✅ NEW - connection testing for PostgreSQL, MySQL, BigQuery
ml_platform/views.py                       ✅ UPDATED - Connection CRUD, ETL wizard, edit endpoints, loading states
ml_platform/models.py                      ✅ UPDATED - Connection model, wizard step tracking fields
ml_platform/urls.py                        ✅ UPDATED - Connection management, test-and-fetch-tables endpoint
templates/ml_platform/model_etl.html       ✅ UPDATED - edit/resume, loading states, CREATE vs EDIT separation
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
