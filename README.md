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
- 🔧 **TFX Code Generation:** Auto-generate production-ready TFX code from feature configs
  - **Transform module:** `preprocessing_fn` with vocabularies, normalization, cyclical encoding, crosses
  - **Trainer module:** BuyerModel, ProductModel, RetrievalModel classes with TFRS integration
  - **Code Viewer UI:** Tabbed modal with syntax highlighting, copy/download, regenerate
  - **Code Validation:** Automatic syntax checking with error reporting (line numbers, error messages)
- 🧪 **Quick Test Pipeline:** Validate feature configs on Vertex AI before full training
  - **Note:** Quick Test moved to Experiments page (2025-12-13)
  - **Configurable params:** Epochs, batch size, learning rate, data sample %
  - **Hardware selection:** CPU tiers (Small/Medium/Large) with auto-recommendation
  - **Dataflow processing:** StatisticsGen and Transform use Dataflow for scalable data processing
  - **Real-time progress:** Stage tracking with animated progress bar
  - **Results display:** Loss, Recall@10/50/100, vocabulary statistics
  - **Pipeline stages:** ExampleGen → StatisticsGen → SchemaGen → Transform → Trainer

### **Model Structure** ✅
- 🏗️ **Architecture Configuration:** Define neural network architecture independent from features
- 🌐 **Global/Reusable:** ModelConfig is dataset-independent, can be used with any FeatureConfig
- 🗼 **Tower Builder:** Visual layer configuration for Buyer (Query) and Product (Candidate) towers
- 📊 **Layer Types:** Dense, Dropout, Batch Normalization, Layer Normalization with L1/L2/L1+L2 regularization
- 🎯 **5 Presets:** Minimal (64→32), Standard (128→64→32), Deep (256→128→64→32), Asymmetric, Regularized
- ⚙️ **Training Hyperparameters:** Optimizer (Adagrad/Adam/SGD/RMSprop/AdamW/FTRL), learning rate with auto-suggest, batch size
- 🔄 **Model Types:** Retrieval ✅, Ranking ✅, Multitask ✅ (all phases complete)
- 📋 **CRUD Operations:** Create, view, edit, clone, delete model configs
- 🔍 **Retrieval Algorithms:** Brute Force (default) or ScaNN for large catalogs (10K+ products)
- 📈 **Model Summary:** Keras-style parameter display (Total/Trainable/Non-trainable params)
- ↕️ **Layer Reordering:** Drag-drop layer reordering within towers (output layer locked)
- 🔧 **Runtime Code Generation:** Trainer code generated when combined with FeatureConfig for QuickTest
- 🎯 **Ranking Model Support:** Rating Head builder, loss function selection (MSE/BCE/Huber), drag-drop layer reordering
- 🔍 **Compare Modal:** Side-by-side model comparison with Rating Head support for Ranking models

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
**Architecture:** Multi-tenant SaaS (one GCP project per client)

### **Multi-Tenant Architecture**

Each client gets a fully isolated GCP project with their own Django app, databases, and ML pipelines. The only shared resource is the **TFX Compiler Image** hosted in a central platform project.

```
b2b-recs-platform (Central)          Client Projects (Isolated)
┌────────────────────────────┐      ┌─────────────┐ ┌─────────────┐
│ Artifact Registry          │      │ client-a    │ │ client-b    │
│ └── tfx-compiler:latest ◄──┼──────┤ Cloud Build │ │ Cloud Build │
│     (shared image)         │      │ Vertex AI   │ │ Vertex AI   │
└────────────────────────────┘      └─────────────┘ └─────────────┘
```

**TFX Compiler Image**: `europe-central2-docker.pkg.dev/b2b-recs-platform/tfx-builder/tfx-compiler:latest`
- Pre-built with TFX, KFP, and dependencies (Python 3.10)
- Reduces Quick Test compilation from 12-15 min to 1-2 min
- Built once, shared across all clients via IAM

See [`implementation.md`](implementation.md) for full architecture details.

### **Per-Client Components**

| Component | Type | Resources | Purpose |
|-----------|------|-----------|---------|
| **Django App** | Cloud Run Service | 2Gi RAM, 2 CPU | Web UI + API |
| **ETL Runner** | Cloud Run Job | 8Gi RAM, 4 CPU | ETL execution (< 1M rows) |
| **Dataflow** | Dataflow Jobs | Auto-scaling | Large-scale ETL (≥ 1M rows) |
| **Database** | Cloud SQL PostgreSQL 15 | Standard | Application data |
| **Data Warehouse** | BigQuery | `raw_data` dataset | Analytics storage |
| **Scheduler** | Cloud Scheduler | - | Automated triggers |
| **Secrets** | Secret Manager | - | Credentials storage |
| **ML Pipelines** | Vertex AI Pipelines | - | TFX pipeline execution |

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
| [`implementation.md`](implementation.md) | **SaaS architecture, multi-tenant design, shared infrastructure** |
| [`next_steps.md`](next_steps.md) | Current status, priorities, and roadmap |
| [`etl_runner/etl_runner.md`](etl_runner/etl_runner.md) | ETL Runner technical documentation |
| [`ml_platform/datasets/datasets.md`](ml_platform/datasets/datasets.md) | Dataset Manager documentation |
| [`docs/phase_datasets.md`](docs/phase_datasets.md) | Dataset domain specification |
| [`docs/phase_configs.md`](docs/phase_configs.md) | Feature + Model Config specification |
| [`docs/phase_model_structure.md`](docs/phase_model_structure.md) | Model Structure (Architecture) specification |
| [`docs/phase_experiments.md`](docs/phase_experiments.md) | Experiments (Quick Test + MLflow) specification |
| [`docs/phase_experiments_implementation.md`](docs/phase_experiments_implementation.md) | **Experiments implementation guide (TFX, Cloud Build)** |
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
- **Quick Test Pipeline** - ✅ **Fully working!** TFX pipeline on Vertex AI with TFRS model training and SavedModel export
- **Model Structure** - Tower architecture builder with presets, layer configuration, training params (9 endpoints)

### **🔮 Next Up**
1. **Metrics Display** - Per-epoch training charts, comparison tables
2. **MLflow Integration** - Experiment tracking, heatmaps, model comparison
3. Full Training Pipeline - Extended training with checkpointing
4. Model Deployment - Candidate index building, serving endpoints

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

**December 17, 2025 - Hardware Configuration & Dataflow Integration**
- ✅ **Hardware selection UI** - Choose CPU tiers (Small/Medium/Large) for experiments
- ✅ **Auto-recommendation** - System suggests hardware based on dataset size and model complexity
- ✅ **Dataflow integration** - StatisticsGen and Transform always use Dataflow for scalable processing
- ✅ **Machine type persistence** - `machine_type` field added to QuickTest model
- ✅ **GPU options preview** - GPU cards shown as "coming soon" in the wizard
- See [Phase 11: Hardware Configuration](docs/phase_experiments_implementation.md#phase-11-hardware-configuration--dataflow-december-2025) for details

**December 16, 2025 - TFX Pipeline Fully Working! 🎉**
- ✅ **End-to-end pipeline execution** - BigQueryExampleGen → StatisticsGen → SchemaGen → Transform → Trainer → Model Saved
- ✅ **TFRS Two-Tower model training** - Retrieval model trains successfully on Vertex AI
- ✅ **SavedModel export** - Model saved with serving signature for inference
- ✅ **5 critical bug fixes in TrainerModuleGenerator**:
  - Fixed embedding flatten shape issue (static shapes preserved)
  - Fixed infinite dataset error (added `num_epochs=1`)
  - Removed redundant StringLookup (Transform provides vocab indices)
  - Removed FactorizedTopK (caused serialization issues)
  - Created ServingModel wrapper (tracks TFT resources properly)
- See [Phase: Experiments Implementation](docs/phase_experiments_implementation.md) for technical details

**December 14, 2025 - Multitask Model Support (Phase 3 Complete)**
- ✅ **Multitask model type** - Combined Retrieval + Ranking with configurable loss weights
- ✅ **Loss Weight sliders** - Retrieval Weight and Ranking Weight (0.0-1.0 each)
- ✅ **Independent weights** - Not normalized, allows flexible task emphasis
- ✅ **Multitask Architecture Diagram** - Visual representation in Step 2 showing both task paths
- ✅ **Validation** - At least one weight must be > 0
- ✅ **Balanced start default** - 1.0 / 1.0 for initial experiments
- ✅ **Model cards** - Pink "Multitask" badge with weights display
- ✅ **Full CRUD** - Save/Load/Edit/Clone/Reset all handle multitask configs
- See [Phase: Model Structure docs](docs/phase_model_structure.md) for details

**December 13, 2025 - Ranking Model Enhancements**
- ✅ **LayerNormalization** - Added as 4th layer type to all towers (Buyer, Product, Rating Head)
- ✅ **Rating Head drag-drop** - Layers now draggable/reorderable in Rating Head (output layer locked)
- ✅ **Compare Modal for Ranking** - Added Rating Head comparison section with purple theme
- ✅ **Mixed model comparison** - Shows "N/A" for non-applicable settings when comparing Ranking vs Retrieval
- ✅ **Loss Function comparison** - Added to Training Settings section in Compare modal
- See [Phase: Model Structure docs](docs/phase_model_structure.md) for details

**December 13, 2025 - Quick Test Moved to Experiments Page**
- ✅ **Page split** - Quick Test functionality moved from Modeling to dedicated Experiments page
- ✅ **New Experiments page** (`model_experiments.html`) - 1,129 lines of new code
- ✅ **Modeling page reduced** - Removed ~714 lines, now focused on Feature + Model Config only
- ✅ **Clean separation** - Modeling = Configure, Experiments = Run and Compare
- ✅ **Documentation updated** - `phase_modeling.md`, `phase_experiments.md`, `implementation.md`
- See [Phase: Experiments docs](docs/phase_experiments.md) for details

**December 12, 2025 - Code Generation Architecture Refactored**
- ✅ **Split code generation** - Transform code stored in FeatureConfig, Trainer code generated at runtime
- ✅ **TrainerModuleGenerator refactored** - Now requires both FeatureConfig AND ModelConfig
- ✅ **Trainer code features** - Configurable tower layers (Dense/Dropout/BatchNorm), L1/L2/L1+L2 regularization
- ✅ **6 optimizers supported** - Adagrad, Adam, SGD, RMSprop, AdamW, FTRL
- ✅ **ModelConfig is global** - Dataset-independent, reusable across any FeatureConfig
- ✅ **QuickTest updated** - Now requires model_config_id; generates trainer code at runtime
- ✅ **New API endpoint** - `POST /api/modeling/generate-trainer-code/` for combined code generation
- ✅ **UI updates** - ModelConfig selector in QuickTest dialog; Code button removed from Model Structure
- See [TFX Code Generation docs](docs/tfx_code_generation.md) for details

**December 11, 2025 - Model Structure Chapter Enhanced**
- ✅ **ModelConfig entity** - Separate model architecture from feature engineering
- ✅ **Tower Architecture Builder** - Visual layer configuration for Buyer/Product towers
- ✅ **5 Presets** - Minimal, Standard, Deep, Asymmetric, Regularized
- ✅ **3-step Wizard** - Basic Info → Architecture → Training
- ✅ **Layer Types** - Dense, Dropout, Batch Normalization
- ✅ **Training Params** - 6 optimizers (Adagrad/Adam/SGD/RMSprop/AdamW/FTRL), learning rate with auto-suggest, batch size
- ✅ **Step 3 Card-Based UI** - Two-panel layout (Optimizer + Hyperparameters) with LR preset buttons
- ✅ **Epochs Removed** - Now set per experiment/training run for flexibility
- ✅ **Retrieval Algorithms** - Brute Force (default) or ScaNN for 10K+ product catalogs
- ✅ **Layer Drag-Drop Reordering** - Layers movable within towers (output layer locked)
- ✅ **Keras-style Model Summary** - Total/Trainable/Non-trainable params per tower
- ✅ **Unified Layer Edit Modals** - Consistent UI with dimension button selectors
- ✅ **All 3 phases complete** - Retrieval, Ranking, and Multitask model types fully implemented
- ✅ API endpoints: `/api/model-configs/` (full CRUD + clone + presets)
- See [Phase: Model Structure docs](docs/phase_model_structure.md) for details

**December 10, 2025 - Quick Test Pipeline Integration**
- ✅ **Vertex AI Pipeline** - Full KFP v2 pipeline for validating feature configs
- ✅ **QuickTest model** - Django model for tracking pipeline runs with status, progress, results
- ✅ **Pipeline Service** - Submit pipelines, poll status, extract metrics from GCS
- ✅ **UI Integration** - "Test" button, configuration dialog, progress modal, results display
- ✅ **GCS Buckets** - Created with lifecycle policies (7/30/3 days)
- ✅ **IAM Setup** - Service account roles for Vertex AI, Storage, Service Account User
- ✅ API endpoints: `/api/feature-configs/{id}/quick-test/`, `/api/quick-tests/{id}/`
- See [TFX Code Generation docs](docs/tfx_code_generation.md) for details

**December 10, 2025 - TFX Code Generation & Validation**
- ✅ **Transform code generation** - Auto-generate TFX `preprocessing_fn` from Feature Configs
- ✅ **Trainer code generation** - Auto-generate TFX Trainer module with:
  - BuyerModel (Query Tower) and ProductModel (Candidate Tower) classes
  - RetrievalModel using TFRS with configurable dense layers (128→64→32)
  - `run_fn()` TFX entry point with serving signature
- ✅ **Code Viewer UI** - Modal with Transform/Trainer tabs, syntax highlighting, copy/download
- ✅ **Code Validation** - Automatic syntax checking with validation badges and error reporting
- ✅ API endpoints: `GET/POST /api/feature-configs/{id}/generated-code/` and `/regenerate-code/`
- See [TFX Code Generation docs](docs/tfx_code_generation.md) for details

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

**Project Stats:** 21 models • 70+ files • 139 URL patterns • ~10,000 LOC • 100% auth coverage

**Deployed:** November 2025 | **Region:** EU (Warsaw) | **Status:** Production Ready ✅
