# B2B Recommendation System - SaaS Platform

A production-ready multi-tenant SaaS platform for building, training, and deploying B2B recommendation models with automated ETL pipelines.

**Status:** Production Deployed ✅ | Cloud Scheduler Working ✅ | SQL/NoSQL/File ETL Active ✅ | Dataflow Ready ✅

**Live:** https://django-app-555035914949.europe-central2.run.app

---

## 🎯 What It Does

This platform enables businesses to:
- **Extract** data from SQL databases (PostgreSQL, MySQL, BigQuery), NoSQL databases (Firestore 🔥), and cloud storage (GCS, S3, Azure)
- **Transform** data with automatic schema detection, inference, and column sanitization
- **Load** data into BigQuery for analytics and ML model training
- **Automate** ETL pipelines with Cloud Scheduler (minute-level precision)
- **Scale** with Dataflow for large datasets (> 1M rows)
- **Build** recommendation models with TFRS (TensorFlow Recommenders)

---

## ✨ Key Features

### **ETL System**
- 📊 **Data Sources** (7 types):
  - **SQL Databases:** PostgreSQL, MySQL, BigQuery (cross-project + public datasets)
  - **NoSQL Databases:** Firestore 🔥 (with automatic schema inference)
  - **Cloud Storage:** GCS, S3, Azure Blob Storage
- 📁 **File Formats:** CSV, Parquet, JSON/JSONL
- 🔄 **Load Strategies:**
  - Transactional (incremental/append-only)
  - Catalog (daily snapshots)
- ⚙️ **Processing Modes:**
  - Standard (< 1M rows): Single Cloud Run instance
  - Dataflow (≥ 1M rows): Distributed processing with partitioning
- 🧠 **Smart Features:**
  - Automatic schema inference for NoSQL (samples 100 documents)
  - Nested data handling (JSON strings for complex objects)
  - Column name sanitization and type mapping
- ⏰ Automated scheduling with Cloud Scheduler
- 🔐 Secret Manager integration for credentials

### **Dataset Management** ✅
- 🎨 **Visual Schema Builder:** Power BI-style drag-and-drop interface with visual connection lines
- 🗃️ **Table Selection:** Browse and select from `raw_data.*` BigQuery tables
- 🔗 **Multi-Table Joins:** Auto-detect join keys with confidence scoring + manual override
- 📋 **Column Mapping:** Flexible column selection with ML role suggestions (user_id, product_id, revenue)
- 🔍 **Column Statistics:** Full table scan for accurate cardinality, min/max, nulls, uniqueness
- 🎯 **Advanced Data Filters:**
  - **Date Filtering:** Rolling window or fixed start date with timestamp column selection
  - **Product Filtering:** Top N% products by revenue with D3.js Pareto chart visualization
  - **Customer Filtering:** Top N% customers by revenue, min transactions, aggregation filters
  - **Column Filters:** Category (include/exclude), Numeric (range, greater than, less than, equals), Date filters
  - **Cross-sub-chapter column exclusion:** Prevents same column from being used in multiple filters
  - **Unified filter summary:** Numbered filters with delete buttons across all sub-chapters
- 📊 **Data Quality Metrics:** Automated scoring with issue detection (sparsity, cold start, engagement)
- 🔄 **TFX Integration:** Query generation ready for TFX ExampleGen component (split handled by Training domain)
- 👁️ **Live Preview:** See sample data from joined tables in real-time with seeded sampling
- 📦 **Dataset as Configuration:** Datasets store configuration only; no BigQuery copies created

### **Modeling (Feature Engineering)** ✅
- 🧠 **TFRS Two-Tower Architecture:** Configure BuyerModel (Query Tower) and ProductModel (Candidate Tower)
- 🎯 **Feature Configuration Wizard:** 2-step wizard for creating feature configs
  - Step 1: Basic info (name, dataset selection)
  - Step 2: Drag-and-drop column assignment to towers
- ⚙️ **Feature Processing Options:**
  - **String Features:** Embedding with configurable dimensions, vocabulary size, OOV buckets
  - **Numeric Features:** Normalization (z-score, min-max, log) or Bucketization with custom boundaries
  - **Timestamp Features:** Cyclical encoding (hour, day of week, month, day of month)
- 🔗 **Cross Features:** Hash bucket configuration for feature interactions
- 📊 **Tensor Dimension Preview:** Real-time calculation of input dimensions for both towers
- 📝 **Version Control:** Track configuration changes with version history
- 🎨 **Smart Defaults:** Auto-configure features based on column types and statistics

### **Platform Features**
- 🎨 ETL Wizard UI (5-step data source configuration)
- 📅 Advanced scheduling (cron with timezone support)
- 🔍 Connection testing and validation
- 📈 BigQuery integration with auto-table creation
- 🚀 Cloud Run deployment (auto-scaling)
- 🔒 User authentication and authorization

---

## 🏗️ Infrastructure

**Platform:** Google Cloud Platform
**Region:** europe-central2 (Warsaw, Poland)
**Project:** b2b-recs (555035914949)

### **Components**

| Component | Type | Resources | Purpose |
|-----------|------|-----------|---------|
| **Django App** | Cloud Run Service | 2Gi RAM, 2 CPU | Web UI + API |
| **ETL Runner** | Cloud Run Job | 8Gi RAM, 4 CPU | ETL execution (< 1M rows) |
| **Dataflow** | Dataflow Jobs | Auto-scaling | Large-scale ETL (≥ 1M rows) |
| **Database** | Cloud SQL PostgreSQL 15 | Standard | Application data |
| **Data Warehouse** | BigQuery | `raw_data` dataset | Analytics storage |
| **Scheduler** | Cloud Scheduler | - | Automated triggers |
| **Secrets** | Secret Manager | - | Credentials storage |

### **Architecture**

```
┌─────────────────┐
│   User (Web)    │
└────────┬────────┘
         │
         ↓
┌─────────────────┐      ┌──────────────────┐
│  Django App     │─────→│  Cloud SQL       │
│  (Cloud Run)    │      │  PostgreSQL      │
└────────┬────────┘      └──────────────────┘
         │
         │ Webhook
         ↓
┌─────────────────┐
│  ETL Runner     │─┐
│  (Cloud Run Job)│ │
└────────┬────────┘ │
         │          │
         │          ↓
         │    ┌──────────────────┐
         │    │  Source Databases│
         │    │  Cloud Storage   │
         │    └──────────────────┘
         ↓
┌─────────────────┐
│    BigQuery     │
│  (Data Warehouse)│
└─────────────────┘
         ↑
         │
┌─────────────────┐
│ Cloud Scheduler │
│ (Automated Runs)│
└─────────────────┘
```

---

## 🚀 Quick Start

### **Prerequisites**
- Google Cloud Project with billing enabled
- `gcloud` CLI installed and authenticated
- Python 3.10+

### **1. Clone Repository**
```bash
git clone https://github.com/d-kulish/b2b_recs.git
cd b2b_recs
```

### **2. Deploy to Google Cloud**

**Django App:**
```bash
# Build and deploy
gcloud builds submit --tag gcr.io/b2b-recs/django-app
gcloud run deploy django-app \
  --image gcr.io/b2b-recs/django-app:latest \
  --region europe-central2 \
  --platform managed
```

**ETL Runner:**
```bash
cd etl_runner
gcloud builds submit --tag gcr.io/b2b-recs/etl-runner
gcloud run jobs create etl-runner \
  --image gcr.io/b2b-recs/etl-runner:latest \
  --region europe-central2 \
  --memory 8Gi \
  --cpu 4
```

### **3. Access Application**
Navigate to your Cloud Run URL and create a superuser:
```bash
gcloud run jobs execute django-migrate-and-createsuperuser --region europe-central2
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [`next_steps.md`](next_steps.md) | Current status, priorities, and roadmap |
| [`etl_runner/etl_runner.md`](etl_runner/etl_runner.md) | ETL Runner technical documentation |
| [`ml_platform/datasets/datasets.md`](ml_platform/datasets/datasets.md) | Dataset Manager documentation |
| [`docs/phase_datasets.md`](docs/phase_datasets.md) | Dataset domain specification |
| [`docs/phase_modeling.md`](docs/phase_modeling.md) | Modeling (Feature Engineering) specification |
| This file | Project overview and quick start |

---

## 🔒 Security

- **Authentication:** Django user authentication with session management
- **Credentials:** All sensitive data stored in Secret Manager
- **HTTPS:** Enforced via Cloud Run (SECURE_PROXY_SSL_HEADER)
- **CSRF:** Protection enabled for all forms
- **IAM:** Service accounts with least-privilege access
- **OIDC:** Cloud Scheduler authentication via OIDC tokens

---

## 🛠️ Tech Stack

**Backend:**
- Django 4.2
- PostgreSQL 15
- Python 3.10

**Cloud Services:**
- Google Cloud Run (Services + Jobs)
- Cloud SQL
- BigQuery
- Cloud Scheduler
- Secret Manager
- Cloud Build

**ETL:**
- Custom Python ETL runner
- Apache libraries (PyArrow for Parquet)
- Pandas for data processing
- Google Cloud client libraries

---

## 📊 Current Status

### **✅ Working**
- Multi-source ETL (databases + cloud storage files + NoSQL)
- **Firestore ETL** - Load NoSQL documents to BigQuery with automatic schema inference
- Automated scheduling via Cloud Scheduler
- BigQuery integration with auto-schema
- Connection management with Secret Manager
- ETL Wizard UI (5-step configuration)
- File validation and processing
- Incremental and snapshot loading
- Dataflow for large datasets (> 1M rows)
- **Dataset Management** - Full UI with 4-step wizard and Visual Schema Builder (27 endpoints)
- **Modeling (Feature Engineering)** - Feature config wizard with drag-drop UI, tensor dimension preview (11 endpoints)

### **🔮 Next Up**
1. Training Pipeline - TFX integration with ExampleGen, model training jobs
2. Real-time streaming ETL (Pub/Sub)
3. Data quality validation rules

See [`next_steps.md`](next_steps.md) for detailed roadmap.

---

## 🎯 Use Cases

**Retail/E-commerce:**
- Product catalog synchronization
- Sales transaction aggregation
- Customer behavior analytics

**B2B SaaS:**
- Usage metrics collection
- Customer data consolidation
- Cross-system reporting

**Analytics:**
- Multi-source data warehousing
- Scheduled data refreshes
- Historical data archival

---

## 🔧 Key Configurations

### **Service Accounts**

| Account | Purpose | Key Roles |
|---------|---------|-----------|
| `django-app@b2b-recs.iam.gserviceaccount.com` | Django App | Cloud SQL Client, Secret Manager Accessor |
| `etl-runner@b2b-recs.iam.gserviceaccount.com` | ETL Runner | BigQuery Data Editor, Storage Object Viewer |

### **Environment Variables**

**Django App:**
```bash
DATABASE_URL=postgresql://user:pass@/cloudsql/...
GCP_PROJECT_ID=b2b-recs
SECRET_MANAGER_PROJECT=b2b-recs
```

**ETL Runner:**
```bash
DJANGO_API_URL=https://django-app-555035914949.europe-central2.run.app
GCP_PROJECT_ID=b2b-recs
BIGQUERY_DATASET=raw_data
```

---

## 🐛 Troubleshooting

### **Cloud Scheduler 401 Error**
**Fix:** Grant OIDC token creation permission
```bash
gcloud iam service-accounts add-iam-policy-binding etl-runner@b2b-recs.iam.gserviceaccount.com \
  --member="serviceAccount:service-555035914949@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### **ETL Job Fails with "Cannot determine path"**
**Fix:** Configure GCS bucket in connection
```sql
UPDATE ml_platform_connection
SET source_host='your-bucket-name'
WHERE source_type='gcs';
```

### **Database Connection Issues**
**Fix:** Check Cloud SQL proxy settings and Secret Manager credentials

---

## 📝 Recent Updates

**December 8, 2025 - Modeling (Feature Engineering) Domain Complete**
- ✅ New `ml_platform/modeling/` sub-app with services, API, views
- ✅ `FeatureConfig` and `FeatureConfigVersion` models for tracking feature engineering configurations
- ✅ 2-step wizard: Basic Info → Feature Assignment (drag-and-drop)
- ✅ Feature processing: String embeddings, Numeric normalization/bucketization, Timestamp cyclical encoding
- ✅ Cross feature configuration with hash buckets
- ✅ Real-time tensor dimension preview for BuyerModel and ProductModel towers
- ✅ Smart defaults service for auto-configuring features based on column types
- ✅ Version history tracking for configuration changes
- ✅ 11 REST API endpoints for feature config CRUD, smart defaults, dimension calculation

**December 6, 2025 - Dataset Wizard Finalized (4 Steps)**
- ✅ Removed Step 5 (Train/Eval Split) - now handled by Training domain
- ✅ Dataset is now "configuration only" - no BigQuery objects created
- ✅ 4-step wizard: Info → Tables → Schema → Filters
- ✅ Train/eval split moves to TFX ExampleGen in Training domain
- ✅ Dataset versioning at training time for reproducibility
- ✅ Simplified Query Preview modal (shows base query only)
- ✅ Updated documentation (implementation.md, phase_datasets.md)

**December 5, 2025 - Enhanced Filtering System**
- ✅ Cross-sub-chapter column exclusion - columns used in one filter are unavailable in others
- ✅ Unified filter summary UI - consistent "Filter #N" format with delete buttons across all sub-chapters
- ✅ Greater than / Less than numeric filter options added
- ✅ Top Products filter now shows product count from analysis (e.g., "Top 80% revenue (4 products)")
- ✅ Delete buttons (trash icon) for all filter types including Dates sub-chapter
- ✅ Committed/pending state management for filter lifecycle

**December 2, 2025 - Dataset Management UI Complete**
- ✅ Visual Schema Builder - Power BI-style drag-and-drop interface
- ✅ Draggable table cards with column checkboxes
- ✅ Color-coded curved connection lines for joins
- ✅ Live preview with seeded sampling (ensures joins work in preview)
- ✅ 4-step wizard (Basic Info → Source Tables → Visual Schema → Filters)
- ✅ 27 REST API endpoints (4 new for Visual Schema Builder)

**December 1, 2025 - Dataset Management Backend Complete**
- ✅ Dataset domain sub-app architecture (following ETL pattern)
- ✅ 23 REST API endpoints for dataset CRUD, BigQuery integration, analysis, and query generation
- ✅ Auto-detect join keys between tables with confidence scoring
- ✅ ML column role suggestions (user_id, product_id, revenue)
- ✅ Full table scan statistics with cardinality, uniqueness
- ✅ Data quality metrics with automated issue detection
- ✅ CTE-based complex filters (top N% products/customers, min transactions)
- ✅ TFX ExampleGen query generation (split handled by Training domain)

**November 25, 2025 - Firestore ETL Fix**
- ✅ Fixed Firestore timestamp conversion (DatetimeWithNanoseconds → strftime)
- ✅ Schema-aware BigQuery loader with column filtering
- ✅ NULL handling for REQUIRED fields in NoSQL data
- ✅ Successfully loaded 558 Firestore documents to BigQuery

**November 21-24, 2025 - Phase 6-8 Complete**
- ✅ Fixed Cloud Scheduler authentication (401 → webhook pattern)
- ✅ Fixed file ETL validation (GCS/S3/Azure now supported)
- ✅ Dataflow integration for large datasets (> 1M rows)
- ✅ BigQuery Storage Write API with schema conversion
- ✅ Complete Firestore/NoSQL ETL support

**November 20, 2025 - Phase 5 Complete**
- ✅ Professional scheduling system (minute-level, timezone support)
- ✅ File ETL runner implementation
- ✅ Column name sanitization for BigQuery

See git commit history for full changelog.

---

## 🤝 Contributing

This is a private project. For questions or issues, contact the repository owner.

---

## 📄 License

Private/Proprietary

---

**Project Stats:** 20 models • 60+ files • 135 URL patterns • ~8,000 LOC • 100% auth coverage

**Deployed:** November 2025 | **Region:** EU (Warsaw) | **Status:** Production Ready ✅
