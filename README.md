# B2B Recommendation System - SaaS Platform

A production-ready multi-tenant SaaS platform for building, training, and deploying B2B recommendation models with automated ETL pipelines.

**Status:** Production Deployed ✅ | Cloud Scheduler Working ✅ | Multi-Source ETL Active ✅

**Live:** https://django-app-555035914949.europe-central2.run.app

---

## 🎯 What It Does

This platform enables businesses to:
- **Extract** data from databases (PostgreSQL, MySQL, BigQuery) and cloud storage (GCS, S3, Azure)
- **Transform** data with automatic schema detection and column sanitization
- **Load** data into BigQuery for analytics and ML model training
- **Automate** ETL pipelines with Cloud Scheduler (minute-level precision)
- **Build** recommendation models (future phase)

---

## ✨ Key Features

### **ETL System**
- 📊 Multiple data sources (6 types: PostgreSQL, MySQL, BigQuery, GCS, S3, Azure Blob)
- 📁 File formats: CSV, Parquet, JSON/JSONL
- 🔄 Load strategies: Transactional (incremental) and Catalog (snapshot)
- ⏰ Automated scheduling with Cloud Scheduler
- 🎯 Column mapping and schema management
- 🔐 Secret Manager integration for credentials

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
| **ETL Runner** | Cloud Run Job | 8Gi RAM, 4 CPU | ETL execution |
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
| [`etl_runner.md`](etl_runner.md) | ETL Runner technical documentation |
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
- Multi-source ETL (databases + cloud storage files)
- Automated scheduling via Cloud Scheduler
- BigQuery integration with auto-schema
- Connection management with Secret Manager
- ETL Wizard UI (5-step configuration)
- File validation and processing
- Incremental and snapshot loading

### **⚠️ In Progress**
- GCS bucket configuration for DataSource #5
- End-to-end file ETL testing

### **🔮 Next Up**
1. Complete GCS bucket setup and testing
2. Integrate Dataflow for big data volumes (> 1M rows)
3. ML model training pipeline integration

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

**November 21, 2025 - Phase 6 Complete**
- ✅ Fixed Cloud Scheduler authentication (401 → webhook pattern)
- ✅ Fixed file ETL validation (GCS/S3/Azure now supported)
- ✅ Updated validation logic for file vs database sources
- ✅ Dynamic API configuration based on source type

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

**Project Stats:** 14 models • 45+ files • 74 URL patterns • ~3,850 LOC • 100% auth coverage

**Deployed:** November 2025 | **Region:** EU (Warsaw) | **Status:** Production Ready ✅
