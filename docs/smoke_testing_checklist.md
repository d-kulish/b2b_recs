# Smoke Testing Checklist - Views Refactoring

**Date:** November 30, 2025
**Purpose:** Verify all functionality works after migrating to sub-apps architecture

---

## Pre-Testing Setup

- [ ] Start development server: `python manage.py runserver`
- [ ] Ensure database is running and migrated
- [ ] Login to the application with a test user

---

## 1. System Dashboard

| Test | URL | Expected | Status |
|------|-----|----------|--------|
| Dashboard loads | `/` | Shows list of models, stats | ☐ |
| Create model button works | `/models/create/` | Form renders | ☐ |
| Model cards display correctly | `/` | Each model shows name, status | ☐ |

---

## 2. ETL Page (Sub-App)

### 2.1 Page Load
| Test | URL | Expected | Status |
|------|-----|----------|--------|
| ETL page loads | `/models/<id>/etl/` | Page renders without errors | ☐ |
| ETL jobs list displays | `/models/<id>/etl/` | Shows configured jobs | ☐ |
| Ridge chart renders | `/models/<id>/etl/` | 3D duration chart visible (if data) | ☐ |
| Recent runs table | `/models/<id>/etl/` | Paginated runs list | ☐ |
| Empty state | `/models/<id>/etl/` | "No ETL jobs" message if none | ☐ |

### 2.2 ETL Job CRUD
| Test | Action | Expected | Status |
|------|--------|----------|--------|
| Create job wizard opens | Click "Create ETL Job" | Modal/wizard appears | ☐ |
| Step 1: Select connection | Choose existing connection | Connection selected | ☐ |
| Step 2: Select table/schema | Pick source table | Table schema loads | ☐ |
| Step 3: Configure columns | Select columns | Columns preview | ☐ |
| Step 4: Destination settings | Set BigQuery destination | Settings saved | ☐ |
| Step 5: Schedule | Set schedule type | Schedule configured | ☐ |
| Job created successfully | Submit wizard | Job appears in list | ☐ |
| Edit job | Click edit icon | Edit modal opens | ☐ |
| Delete job | Click delete, confirm | Job removed | ☐ |

### 2.3 ETL Job Operations
| Test | Action | Expected | Status |
|------|--------|----------|--------|
| Run job manually | Click "Run Now" | Job starts, status updates | ☐ |
| Pause scheduled job | Click pause icon | Job paused, scheduler updated | ☐ |
| Resume paused job | Click resume | Job resumed | ☐ |
| View job details | Click job row | Details modal/panel opens | ☐ |
| View run details | Click run row | Run details with logs | ☐ |

### 2.4 ETL APIs (Developer Console)
| Test | Endpoint | Method | Expected | Status |
|------|----------|--------|----------|--------|
| Check job name | `/api/models/<id>/etl/check-name/` | POST | Returns exists: true/false | ☐ |
| Get source details | `/api/etl/sources/<id>/` | GET | Returns source JSON | ☐ |
| Run status | `/api/etl/runs/<id>/status/` | GET | Returns run status | ☐ |
| Toggle enabled | `/api/models/<id>/etl/toggle/` | POST | Toggles ETL enabled | ☐ |

---

## 3. Connection Management (Sub-App)

### 3.1 Connection List
| Test | Action | Expected | Status |
|------|--------|----------|--------|
| List connections | Open ETL wizard Step 1 | Shows saved connections | ☐ |
| Empty state | No connections | "Create connection" prompt | ☐ |

### 3.2 Connection CRUD
| Test | Action | Expected | Status |
|------|--------|----------|--------|
| Create PostgreSQL connection | Fill form, test, save | Connection saved | ☐ |
| Create MySQL connection | Fill form, test, save | Connection saved | ☐ |
| Create BigQuery connection | Upload SA JSON, test | Connection saved | ☐ |
| Create GCS connection | Configure bucket, test | Connection saved | ☐ |
| Edit connection | Click edit | Form pre-populated | ☐ |
| Delete connection | Click delete, confirm | Connection removed | ☐ |
| Test connection | Click "Test Connection" | Success/failure message | ☐ |

### 3.3 Schema/Table Fetching
| Test | Action | Expected | Status |
|------|--------|----------|--------|
| Fetch schemas | Select connection | Schema list loads | ☐ |
| Fetch tables for schema | Select schema | Table list loads | ☐ |
| Table preview | Select table | Sample rows display | ☐ |

### 3.4 File Operations (Cloud Storage)
| Test | Action | Expected | Status |
|------|--------|----------|--------|
| List files in bucket | Enter prefix/pattern | Files listed | ☐ |
| Detect file schema | Select CSV/Parquet | Columns detected | ☐ |

### 3.5 Connection APIs (Developer Console)
| Test | Endpoint | Method | Expected | Status |
|------|----------|--------|----------|--------|
| List connections | `/api/models/<id>/connections/` | GET | Returns connections array | ☐ |
| Get connection | `/api/connections/<id>/` | GET | Returns connection details | ☐ |
| Test connection | `/api/connections/<id>/test/` | POST | Returns success/failure | ☐ |
| Fetch schemas | `/api/connections/<id>/fetch-schemas/` | GET | Returns schemas array | ☐ |

---

## 4. Other Model Pages (Unchanged)

| Test | URL | Expected | Status |
|------|-----|----------|--------|
| Model Dashboard | `/models/<id>/` | Dashboard loads | ☐ |
| Dataset page | `/models/<id>/dataset/` | Page loads | ☐ |
| Pipeline Config | `/models/<id>/pipeline-config/` | Form renders | ☐ |
| Feature Engineering | `/models/<id>/feature-engineering/` | Page loads | ☐ |
| Training | `/models/<id>/training/` | Page loads | ☐ |
| Experiments | `/models/<id>/experiments/` | Page loads | ☐ |
| Deployment | `/models/<id>/deployment/` | Page loads | ☐ |

---

## 5. Cloud Scheduler Integration

| Test | Action | Expected | Status |
|------|--------|----------|--------|
| Create scheduled job | Create ETL with schedule | Scheduler job created in GCP | ☐ |
| Modify schedule | Edit job schedule | Scheduler updated | ☐ |
| Delete scheduled job | Delete ETL job | Scheduler job deleted | ☐ |
| Webhook receives calls | Wait for schedule | ETL run triggered | ☐ |

---

## 6. Error Handling

| Test | Action | Expected | Status |
|------|--------|----------|--------|
| Invalid model ID | `/models/99999/etl/` | 404 page | ☐ |
| Invalid source ID | `/api/etl/sources/99999/` | Error JSON response | ☐ |
| Unauthenticated access | Logout, access ETL | Redirect to login | ☐ |
| Invalid connection test | Wrong credentials | Clear error message | ☐ |

---

## Test Summary

| Category | Total | Passed | Failed |
|----------|-------|--------|--------|
| System Dashboard | 3 | ☐ | ☐ |
| ETL Page | 5 | ☐ | ☐ |
| ETL Job CRUD | 9 | ☐ | ☐ |
| ETL Job Operations | 5 | ☐ | ☐ |
| ETL APIs | 4 | ☐ | ☐ |
| Connection List | 2 | ☐ | ☐ |
| Connection CRUD | 7 | ☐ | ☐ |
| Schema/Table Fetching | 3 | ☐ | ☐ |
| File Operations | 2 | ☐ | ☐ |
| Connection APIs | 4 | ☐ | ☐ |
| Other Model Pages | 7 | ☐ | ☐ |
| Cloud Scheduler | 4 | ☐ | ☐ |
| Error Handling | 4 | ☐ | ☐ |
| **TOTAL** | **59** | ☐ | ☐ |

---

## Sign-Off

- [ ] All critical paths tested
- [ ] No blocking issues found
- [ ] Ready for production deployment

**Tested By:** ________________
**Date:** ________________
**Notes:** ________________
