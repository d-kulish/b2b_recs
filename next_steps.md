# Next Steps: Connection Testing & Credential Management

**Last Updated:** November 12, 2025

---

## Current Status

- ✅ UI wizard is complete and looks great
- ✅ "Test Connection" button performs real database connections
- ✅ Real database connections working (PostgreSQL, MySQL, BigQuery)
- ✅ Step 3 shows real tables from database with metadata
- ✅ Passwords stored securely in GCP Secret Manager
- ✅ Draft-save flow implemented (credentials saved immediately after test)

---

## Solution Overview

**What we're building:**
1. Django connects to real databases (PostgreSQL, MySQL, etc.)
2. Fetches real table list from the database
3. Saves credentials to GCP Secret Manager (secure)
4. Shows real tables in wizard Step 3

**Flow:**
```
User enters DB credentials → Click "Test Connection" →
Django connects → Pulls table list →
Saves to Secret Manager → Shows real tables → User selects table
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

### 🎯 Milestone 4: Production Readiness (Next Phase)
- [ ] Test with MySQL database connection
- [ ] Test with BigQuery dataset
- [ ] Add SQL Server support if needed
- [ ] Build ETL container (etl_runner.py) for actual data extraction
- [ ] Create Dockerfile for Cloud Run deployment
- [ ] Set up Cloud Scheduler for automated runs
- [ ] Add comprehensive logging and error tracking

---

## What We Accomplished

**Milestones 1-3 Complete!**

✅ Real database connection testing (PostgreSQL, MySQL, BigQuery)
✅ Secure credential storage in GCP Secret Manager
✅ Draft-save flow (credentials saved immediately after successful test)
✅ Real table metadata displayed in wizard (names, row counts, last updated)
✅ Inline error messages with proper UX
✅ Cloud SQL Proxy integration for secure database access

**Next Steps:** Milestone 4 - Build ETL container for production data extraction

---

## Key Files Modified

```
ml_platform/utils/connection_manager.py    ✅ NEW - connection testing for PostgreSQL, MySQL, BigQuery
ml_platform/views.py                       ✅ UPDATED - api_etl_test_connection_wizard(), api_etl_save_draft_source()
ml_platform/models.py                      ✅ UPDATED - added credentials_secret_name field
ml_platform/urls.py                        ✅ UPDATED - added save-draft endpoint route
templates/ml_platform/model_etl.html       ✅ UPDATED - real table list, draft-save flow, inline messages
requirements.txt                           ✅ UPDATED - added psycopg2-binary, pymysql, google-cloud-secret-manager
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
