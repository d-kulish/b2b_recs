# Next Steps: B2B Recommendations Platform

**Last Updated:** November 21, 2025
**Status:** Phase 7 Complete ✅ | BigQuery Source Operational ✅ | ETL Wizard Scheduler Fixed ✅ | Production Ready ✅

---

## 📊 Current Platform Status

### ✅ Functionality Built

#### **1. Core Platform**
- Multi-tenant SaaS platform with Django + Cloud Run
- User authentication and authorization
- PostgreSQL database (Cloud SQL)
- Production deployment in GCP (europe-central2)

#### **2. ETL System** ✅ **Fully Operational**
- **Database Sources**: PostgreSQL, MySQL, **BigQuery** (cross-project + public datasets)
- **File Sources**: GCS, S3, Azure Blob Storage (CSV, Parquet, JSON)
- **Load Strategies**:
  - Transactional (incremental/append-only)
  - Catalog (daily snapshots)
- **ETL Runner**: Cloud Run Job (8Gi RAM, 4 CPU)
- **Features**:
  - Source-type aware validation
  - Automatic credential handling
  - Column name sanitization and mapping
  - Schema filtering and type conversion
  - Incremental file processing with metadata tracking
- **API**: Django REST endpoints for configuration

#### **3. Cloud Scheduler Integration** (Phase 6-7 - Nov 21, 2025)
- ✅ Automated ETL job scheduling
- ✅ OIDC authentication configured (with audience parameter)
- ✅ Webhook pattern: `Cloud Scheduler → Django Webhook → Cloud Run Job`
- ✅ IAM permissions properly configured
- ✅ ETL Wizard creates schedulers correctly (dynamic webhook URL)
- ✅ Working end-to-end

#### **4. Connection Management**
- Centralized connection storage
- Secret Manager integration for credentials
- Connection testing and validation
- Support for multiple connection types

#### **5. ETL Wizard UI**
- Step-by-step data source configuration
- File/database selection
- Column mapping
- Schedule configuration (cron with timezone support)

#### **6. BigQuery Integration**
- Automatic table creation
- Schema management
- Incremental loading
- Column name sanitization
- **BigQuery as Source**: Cross-project ETL, public dataset access
- Row count estimation for processing mode selection

---

## 📈 Phase 7 Completion Summary (November 21, 2025)

### **BigQuery Source Implementation**

**Objective:** Enable ETL from BigQuery public datasets and cross-project data movement for testing and validation.

**Use Case:** Access Stack Overflow public dataset (`bigquery-public-data.stackoverflow.posts_questions`) to test ETL system with real-world, large-scale data.

### **Implementation Details:**

#### **1. BigQuery Extractor** (`etl_runner/extractors/bigquery.py`)
- Created new extractor supporting BigQuery as a source
- Features:
  - Service account authentication
  - Incremental extraction with timestamp filters
  - Row count estimation using `COUNT(*)` queries
  - Batch processing for memory efficiency
  - Support for cross-project access

#### **2. ETL Wizard Integration**
- Added BigQuery connection handling in `api_etl_job_config()`
- Parameter mapping:
  - `source_database` → `bigquery_project`
  - `schema_name` → `bigquery_dataset`
- Credentials passed from Secret Manager

#### **3. Testing with Public Datasets**
Successfully tested with Stack Overflow public dataset:
- **Dataset:** `bigquery-public-data.stackoverflow.posts_questions`
- **Schema:** 14 columns detected
- **Test Results:**
  - ✅ Connection successful
  - ✅ Schema detection working
  - ✅ Row count estimation functional
  - ✅ Incremental extraction with timestamp filters
  - ✅ End-to-end ETL completed successfully

### **Issues Discovered & Fixed:**

#### **Issue 1: ETL Wizard Scheduler Creation Bug**
**Problem:** Wizard-created Cloud Scheduler jobs had null httpTarget fields.

**Root Causes:**
1. Used Cloud Run Jobs API URL (complex auth, unreliable)
2. Missing OIDC `audience` parameter
3. Static configuration instead of dynamic URL building

**Solution:**
- Changed to webhook pattern with dynamic URL: `{request.scheme}://{request.get_host()}/api/etl/sources/{id}/scheduler-webhook/`
- Added OIDC audience extraction in `cloud_scheduler.py`
- Works in both local and Cloud Run environments

**Files Changed:**
- `ml_platform/views.py` - Dynamic webhook URL building
- `ml_platform/utils/cloud_scheduler.py` - OIDC audience parameter

#### **Issue 2: ETL Runner API Authentication (403 Forbidden)**
**Problem:** ETL Runner couldn't POST status updates to Django API.

**Root Cause:** Missing `@csrf_exempt` decorator on service-to-service API endpoints.

**Solution:** Added `@csrf_exempt` to:
- `/api/etl/runs/<id>/update/` - Status updates
- `/api/etl/job-config/<id>/` - Job configuration

**Files Changed:** `ml_platform/views.py`

#### **Issue 3: BigQuery Testing Bugs**
Multiple bugs discovered during Stack Overflow dataset testing:

1. **Schema Validation Error**
   - JavaScript used wrong CSS selectors
   - Fixed: Updated `syncBigQuerySchemaFromUI()` selectors

2. **Column Names with Emojis**
   - Column names extracted from textContent included emoji HTML
   - Fixed: Added `data-column-name` attribute to table rows

3. **Missing GCP_PROJECT_ID**
   - Environment variable not configured
   - Fixed: Added to `.env` and Cloud Run environment

4. **Missing google-cloud-scheduler Package**
   - Package not installed in requirements
   - Fixed: `pip install google-cloud-scheduler==2.17.0`

### **Architecture Improvements:**

**Before Phase 7:**
```
Cloud Scheduler → Cloud Run Jobs API (❌ Auth issues)
```

**After Phase 7:**
```
Cloud Scheduler → Django Webhook → Django triggers Cloud Run Job → ETL Runner ✅
                                                                        ↓
                                                                   BigQuery Source
                                                                        ↓
                                                                   Extract Data
                                                                        ↓
                                                                   BigQuery Destination
```

### **Testing Results:**
- ✅ Scheduler jobs created by wizard work on first try
- ✅ OIDC authentication functioning properly
- ✅ ETL Runner successfully updates job status
- ✅ BigQuery-to-BigQuery ETL operational
- ✅ Public dataset access working
- ✅ End-to-end flow validated

---

## 🚀 Next Steps

### **Priority 1: Integrate Dataflow for Big Data Volumes**

**Goal:** Add Dataflow as an execution option for large-scale ETL jobs (millions of rows).

**Current Architecture:**
```
Cloud Scheduler → Django API → Cloud Run Job (ETL Runner)
                                    ↓
                              BigQuery
```

**Proposed Architecture:**
```
Cloud Scheduler → Django API → Decision Logic
                                    ├── Small Data: Cloud Run Job (ETL Runner)
                                    │                    ↓
                                    │              BigQuery
                                    │
                                    └── Big Data: Dataflow
                                                   ↓
                                             BigQuery
```

**Implementation Plan:**

#### **Step 1: Add Dataflow Execution Mode (1-2 days)**
1. Create Dataflow template for ETL processing
   - Input: GCS staging bucket with extracted data
   - Transformations: Schema mapping, data cleaning
   - Output: BigQuery table
2. Add execution mode to DataSource model:
   ```python
   EXECUTION_MODE_CHOICES = [
       ('cloud_run', 'Cloud Run Job (< 1M rows)'),
       ('dataflow', 'Dataflow (> 1M rows)'),
       ('auto', 'Auto-select based on volume'),
   ]
   ```
3. Update ETL Runner to detect volume and choose execution method

#### **Step 2: Implement Dataflow Pipeline (2-3 days)**
1. Create Apache Beam pipeline:
   - Read from source (database/files)
   - Apply transformations
   - Write to BigQuery
2. Build Dataflow template
3. Deploy to GCP

#### **Step 3: Update Django API (1 day)**
1. Add Dataflow job launching logic to `api_etl_scheduler_webhook`
2. Monitor Dataflow job status
3. Update ETLRun record with progress

#### **Step 4: Testing (1 day)**
1. Test with small dataset (should use Cloud Run)
2. Test with large dataset (should use Dataflow)
3. Test auto-selection mode
4. Verify cost optimization

**Technologies:**
- Apache Beam (Python SDK)
- Dataflow Runner
- GCS for staging
- BigQuery for destination

**Benefits:**
- Handle millions/billions of rows efficiently
- Auto-scaling workers
- Better cost optimization for large jobs
- Parallel processing

**Estimated Time:** 5-7 days

---

## 📋 Technical Debt & Improvements (Future)

### **Minor Enhancements**
- [ ] Add retry logic for failed Cloud Scheduler jobs
- [ ] Implement email notifications for ETL failures
- [ ] Add ETL job metrics dashboard
- [ ] Optimize BigQuery table partitioning
- [ ] Add data quality checks

### **Security**
- [ ] Rotate service account keys regularly
- [ ] Add audit logging for data access
- [ ] Implement row-level security in BigQuery

### **Monitoring**
- [ ] Set up Cloud Monitoring dashboards
- [ ] Configure alerting policies
- [ ] Add performance metrics tracking

---

## 📚 Documentation Status

- ✅ `README.md` - Project overview and deployment
- ✅ `etl_runner.md` - ETL runner technical documentation
- ✅ This file - Next steps and roadmap
- ⚠️ API documentation needed (consider OpenAPI/Swagger)
- ⚠️ User guide needed (how to create data sources, schedule ETL jobs)

---

## 🎯 Success Metrics

**Achieved (Phase 6-7 - Nov 21, 2025):**
- ✅ Cloud Scheduler triggers working (100% success rate)
- ✅ ETL Wizard scheduler creation working (100% success rate)
- ✅ File validation working (100% pass rate)
- ✅ End-to-end file ETL working (GCS CSV files → BigQuery)
- ✅ BigQuery source ETL working (cross-project + public datasets)
- ✅ Automatic column mapping and type conversion
- ✅ File metadata tracking and incremental loading
- ✅ Successfully processed 200,000 rows in test run
- ✅ ETL Runner API authentication working (service-to-service)
- ✅ Tested with real-world public dataset (Stack Overflow)

**Next Targets:**
- [ ] Test with large dataset (> 1M rows) to trigger Dataflow mode
- [ ] Implement conditional Dataflow integration (auto-switch at 1M rows)
- [ ] Process > 10M rows per ETL job with Dataflow
- [ ] < 5 minute latency for scheduled jobs
- [ ] 99.9% ETL success rate
- [ ] Support 10+ concurrent data sources

---

## 💡 Future Enhancements (Phase 7+)

**ML Pipeline Integration:**
- Feature engineering automation
- Model training triggers after ETL completion
- Model deployment automation

**Advanced ETL:**
- CDC (Change Data Capture) support
- Real-time streaming (Pub/Sub → Dataflow → BigQuery)
- Data lineage tracking

**Platform Features:**
- Multi-project support
- Role-based access control (RBAC)
- Cost allocation by team/project
- Self-service data source registration

---

**Current Focus:** BigQuery Source Complete ✅ | ETL Wizard Fixed ✅ | Next: Dataflow Integration for Large-Scale Processing (> 1M rows)
