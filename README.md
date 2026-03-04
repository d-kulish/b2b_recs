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

### **ETL System (Standalone Page)** ✅
The ETL page (`/etl/`) is a system-wide standalone page for managing data ingestion pipelines. It provides a four-chapter interface:

**ETL Dashboard** - Operational overview
- 📊 **Header KPIs:** Failed/successful runs (last 24h), active connections, configured jobs
- 📈 **Dashboard KPIs:** Total runs, success rate, rows migrated, avg duration (last 30 days)
- 📅 **Scheduled Jobs Table:** All scheduled ETL jobs with next run time and Cloud Scheduler state
- 📉 **Diverging Chart:** D3.js visualization of success vs failure per job (last 30 days)

**ETL Runs** - Execution monitoring
- 🃏 **Run Cards:** Status, metrics (rows/bytes/tables), 4-stage progress bar (Init → Validate → Extract → Load)
- 🔍 **Rich Filtering:** Status, Connection, ETL Job, Destination Table, Load Type + search
- 📋 **Run Details Modal:** Full execution timeline, results, error classification, Cloud Run Job logs

**Connections** - Reusable data source credentials
- 📊 **Data Sources** (16 types):
  - **SQL Databases:** PostgreSQL, MySQL, MariaDB, Oracle, SQL Server, DB2, Redshift, BigQuery, Snowflake, Azure Synapse, Teradata
  - **NoSQL Databases:** MongoDB, Firestore 🔥, Cassandra, DynamoDB, Redis
  - **Cloud Storage:** GCS, S3, Azure Blob Storage
- 🔐 **Secret Manager Integration:** Credentials stored in Google Secret Manager, not in Django DB
- 🔌 **Connection Testing:** Individual and bulk connection validation with duplicate detection
- 🧙 **2-Step Wizard:** Select type → Configure credentials (type-specific forms)

**ETL Jobs** - Data extraction pipeline configuration
- 🧙 **5-Step Create Wizard:** Connection → Tables/Files → Load Strategy → BigQuery Setup → Schedule
- 📁 **File Formats:** CSV, Parquet, JSON/JSONL with auto-schema detection
- 🔄 **Load Strategies:** Transactional (incremental/append) or Catalog (full snapshot)
- ⚙️ **Processing Modes:** Standard (< 1M rows, Cloud Run) or Dataflow (≥ 1M rows, Apache Beam)
- 📅 **Scheduling:** Manual, Hourly, Daily, Weekly via Cloud Scheduler with OIDC authentication
- 🗄️ **BigQuery Table Management:** Create new or use existing tables with schema editor and compatibility validation

### **Datasets & Configs (Unified Page)** ✅
The Datasets & Configs page provides a four-chapter workflow for configuring ML training:

**Configs Dashboard** - Overview of all configs
- 📊 **KPI Summary Row:** 3 cards (Datasets, Features, Models) with total/active/unused counts and complexity scores
- 🗺️ **Coverage Matrix:** FeatureConfig × ModelConfig heatmap showing experiment counts and best metrics
- 🔗 **Configuration Flow:** Visual diagram showing Dataset → FeatureConfig → ModelConfig relationships
- 💡 **Suggestions:** Identifies untested but compatible combinations for experimentation gaps

**Chapter 1: Datasets** - Define WHAT data goes into training
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

**Chapter 2: Feature Engineering** - Define HOW to transform data
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

**Chapter 3: Model Structure** - Define neural network architecture
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

### **Experiments** ✅
The Experiments page (`model_experiments.html`) enables running Quick Tests to validate configurations and provides an analytics dashboard for comparing results.

**Chapter 1: Experiments Dashboard** - Analytics and insights
- 📈 **Model Type KPIs:** 3 clickable sections (Retrieval/Ranking/Hybrid) with 5 metric cards each, filtering all dashboard content
- 📉 **Metrics Trend:** Chart.js line chart showing best metrics over time by selected model type
- 🏆 **Top Configurations:** Table of top 5 best-performing experiment configs sorted by primary metric
- 🔬 **Hyperparameter Insights:** TPE-based analysis across 5 categories (Architecture, Features, Dataset, Training, Split) showing which values correlate with top 30% results
- 🗺️ **Training Heatmaps:** D3.js dual heatmaps — Epoch Loss (60%) + Final Metrics (40%), color-coded green-to-red
- 📊 **Dataset Performance:** Compare metrics across different datasets with model-type-specific columns
- 💡 **Suggested Experiments:** AI-powered recommendations (Feature Exploration + Hyperparameter Variation cards)

**Chapter 2: Quick Test** - Create and manage experiments
- 🧪 **2-Step Wizard:** Step 1: Select configs (Model Type + Feature Config with preview + Model Config with preview) → Step 2: Training params (Sampling, Split Strategy, Epochs/Batch/LR, Hardware)
- 🎯 **Model Type Selection:** Retrieval, Ranking, or Multitask/Hybrid
- 🔀 **Split Strategy:** Random (80/15/5), Time Holdout (date column + holdout days), Strict Temporal (rolling window)
- ⚙️ **Configurable Parameters:** Sample % (5/10/25/100%), epochs (5-500), batch size (128-65536), learning rate (0.0001-1.0)
- 🖥️ **Hardware Tiers:** Small/Medium/Large CPU + GPU T4 (n1-standard-4 + NVIDIA T4) with auto-recommendation. GPU V100 locked
- 📊 **Experiment Cards:** 4-column layout with status, configs, metrics, actions + 6-stage progress bar
- 🔍 **Filter & Search:** 6 filters (Status, Model Type, Dataset, Features, Model, Search) — debounced search supports experiment number (e.g., "#62")
- ⚖️ **Compare Modal:** Side-by-side comparison of 2 experiments with 6 accordion sections (Results, Dataset, Features, Model, Training, Sampling)
- 👁️ **View Modal:** Reusable `ExpViewModal` module with 4 tabs (Overview, Pipeline DAG, Data Insights, Training charts)
- 📐 **AUC-ROC Metrics:** Auto-detected for binary-label ranking models, shown alongside RMSE/MAE

**Execution Pipeline:**
```
Cloud Build (1-2 min)              Vertex AI Pipeline (5-15 min)
┌─────────────────────┐           ┌────────────────────────────────────┐
│ Generate TFX code   │           │ ExampleGen → StatisticsGen →       │
│ Submit to Vertex AI │ ────────► │ SchemaGen → Transform → Trainer    │
└─────────────────────┘           │              │                     │
                                  │              ▼                     │
                                  │     training_metrics.json (GCS)    │
                                  └────────────────────────────────────┘
```

**Model Types & Metrics:**
| Model Type | Purpose | Primary Metrics |
|------------|---------|-----------------|
| **Retrieval** | Find candidate items | Recall@5, Recall@10, Recall@50, Recall@100 |
| **Ranking** | Score/rank candidates | RMSE, MAE, Test RMSE, Test MAE |
| **Multitask** | Combined objectives | All 8 metrics (retrieval + ranking) |

### **Training** ✅
The Training page (`model_training.html`) manages production model training, deployment, and the model registry. It provides a three-chapter interface with ~60 API endpoints:

**Chapter 1: Models Registry** - Production model management
- 📊 **KPI Summary Row:** Total models, Blessed, Deployed, Idle counts, Latest registration
- 📅 **Training Activity Calendar:** GitHub-style heatmap showing past 10 weeks + next 30 weeks of scheduled training
- 🔍 **Filter Bar:** Type (All/Retrieval/Ranking/Multitask), Status (All/Blessed/Deployed/Idle), Sort, Search
- 📋 **Registered Models Table:** Model name, type, version, metrics, status badge, actions dropdown
- 📅 **Schedules Section:** Schedule cards with Run/Pause/Resume/Edit/Delete actions
- 👁️ **Model View Modal:** 4 tabs (Overview, Versions with Chart.js grouped bar chart, Artifacts, Deployment)

**Chapter 2: Best Experiments** - Top-performing experiment configurations
- 🏆 **3 Model Type KPI Rows:** Retrieval (R@5/10/50/100), Ranking (RMSE/MAE/Test RMSE/Test MAE), Hybrid (R@50/R@100/RMSE/Test RMSE) — clickable, updates table
- 📋 **Top Configurations Table:** Best 10 experiments per model type (5 visible with scroll)

**Chapter 3: Training Runs** - Launch and monitor training jobs
- 🧪 **3-Step Wizard:** Step 1: Select experiment (model name, type, base experiment) → Step 2: Configuration (inherited configs, epochs/batch/LR, early stopping) → Step 3: GPU & Deploy (T4/L4/V100/A100, deployment presets, auto-deploy toggle)
- 🃏 **Training Run Cards:** 4-column layout (Info, Config, Metrics, Actions) with 8-stage pipeline progress bar (Compile→Examples→Stats→Schema→Transform→Train→Evaluator→Register) + optional Deploy stage
- 🔍 **Filter & Search:** Status, Model Type, Dataset, Features, Model, Search filters
- 👁️ **View Modal:** Reusable `ExpViewModal` in training_run mode with 4 tabs (Overview with Registry & Deployment sections, Pipeline DAG, Data Insights, Training charts)
- 🔄 **Rerun/Edit/Schedule:** Rerun from terminal state, edit training params, schedule recurring training

**Deployment & Serving:**
- ☁️ **Cloud Run Deployment:** TF Serving containers (native for brute-force, Python/Flask for ScaNN models)
- 📦 **Deploy Wizard:** Endpoint selection, 3 presets (Development/Production/High Traffic), advanced options
- 🔗 **Integration API:** Input schema, sample code, and live endpoint testing
- 🔄 **Auto-Deployment:** Optional automatic Cloud Run deployment after successful training and registration

**Scheduling:**
- 📅 **5 Schedule Types:** Once, Hourly, Daily, Weekly, Monthly via Cloud Scheduler with OIDC authentication
- 🔄 **Schedule Modal:** Reusable across Training Cards, View Modal, and Training Wizard
- ✏️ **Edit Schedules:** Modify timing (not training config which stays frozen from source)

**Execution Pipeline:**
```
Training Wizard                   Vertex AI Pipeline (GPU)              Cloud Run
┌─────────────────────┐          ┌──────────────────────────────────┐  ┌──────────────┐
│ Select experiment   │          │ Compile → ExampleGen → StatsGen →│  │ TF Serving   │
│ Configure params    │ ───────► │ SchemaGen → Transform → Trainer →│─►│ or Flask+    │
│ GPU & Deploy        │          │ Evaluator → Register             │  │ ScaNN        │
└─────────────────────┘          └──────────────────────────────────┘  └──────────────┘
```

See [`docs/phase_training.md`](docs/phase_training.md) for full training domain specification. See [`docs/models_registry.md`](docs/models_registry.md) for models registry details.

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

### **Per-Client Components**

| Component | Type | Resources | Purpose |
|-----------|------|-----------|---------|
| **Django App** | Cloud Run Service | 2Gi RAM, 2 CPU | Web UI + API |
| **ETL Runner** | Cloud Run Job | 8Gi RAM, 4 CPU | ETL execution (< 1M rows) |
| **TFDV Parser** | Cloud Run Service | 2Gi RAM, 2 CPU | Parse TFX artifacts (Python 3.10 with TFDV) |
| **Dataflow** | Dataflow Jobs | Auto-scaling | Large-scale ETL (≥ 1M rows) |
| **Database** | Cloud SQL PostgreSQL 15 | Standard | Application data |
| **Data Warehouse** | BigQuery | `raw_data` dataset | Analytics storage |
| **Scheduler** | Cloud Scheduler | - | Automated triggers |
| **Secrets** | Secret Manager | - | Credentials storage |
| **ML Pipelines** | Vertex AI Pipelines | - | TFX pipeline execution |

### **GCS Storage Management**

Four GCS buckets with automated lifecycle policies:

| Bucket | Lifecycle | Contents |
|--------|-----------|----------|
| `b2b-recs-quicktest-artifacts` | 7-day auto-delete | Experiment artifacts |
| `b2b-recs-training-artifacts` | No lifecycle (selective cleanup) | Training run artifacts, registered models |
| `b2b-recs-pipeline-staging` | 7-day auto-delete | TFX intermediate artifacts (TFRecords, Transform, Statistics) |
| `b2b-recs-dataflow` | 3-day auto-delete | ETL Dataflow temp files |

The training-artifacts bucket has no GCS lifecycle policy because registered models must be preserved indefinitely. Instead, a daily cleanup command (`cleanup_gcs_artifacts`) selectively deletes artifacts for old non-registered runs while preserving `pushed_model/` directories for models in the Vertex AI Model Registry.

**Automated cleanup** runs daily at 03:00 UTC via Cloud Scheduler (1 hour after metrics collection).

**Setup for new projects:**

```bash
# 1. Create buckets (done by setup_vertex_ai.sh, or manually):
gsutil mb -p $PROJECT_ID -l $REGION gs://$PROJECT_ID-quicktest-artifacts/
gsutil mb -p $PROJECT_ID -l $REGION gs://$PROJECT_ID-training-artifacts/
gsutil mb -p $PROJECT_ID -l $REGION gs://$PROJECT_ID-pipeline-staging/
gsutil mb -p $PROJECT_ID -l $REGION gs://$PROJECT_ID-dataflow/

# 2. Apply lifecycle policies:
gsutil lifecycle set /dev/stdin gs://$PROJECT_ID-quicktest-artifacts/ <<< \
  '{"rule":[{"action":{"type":"Delete"},"condition":{"age":7}}]}'

gsutil lifecycle set /dev/stdin gs://$PROJECT_ID-training-artifacts/ <<< \
  '{"rule":[]}'

gsutil lifecycle set /dev/stdin gs://$PROJECT_ID-pipeline-staging/ <<< \
  '{"rule":[{"action":{"type":"Delete"},"condition":{"age":7}}]}'

gsutil lifecycle set /dev/stdin gs://$PROJECT_ID-dataflow/ <<< \
  '{"rule":[{"action":{"type":"Delete"},"condition":{"age":3}}]}'

# 3. Deploy the app, then create the cleanup scheduler from the deployed app:
curl -X POST https://<your-cloud-run-url>/api/system/setup-cleanup-scheduler/ \
  -H "Content-Type: application/json"

# 4. Verify:
gsutil lifecycle get gs://$PROJECT_ID-training-artifacts/
gsutil lifecycle get gs://$PROJECT_ID-pipeline-staging/
gsutil lifecycle get gs://$PROJECT_ID-dataflow/
gcloud scheduler jobs list --location=$REGION
```

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

### **Network Architecture & Static IPs**

Enterprise clients typically have on-premise databases behind firewalls that require IP whitelisting. Each client project gets a **Cloud NAT + Reserved Static IP** so all outbound traffic from Cloud Run uses a predictable, stable IP address.

```
Client GCP Project
├── Cloud Run Services (Django, ETL, Model Serving)
│   └── Outbound connections
│           ↓
├── Cloud NAT Gateway
│   └── Maps all outbound traffic to static IP
│           ↓
├── Reserved Static External IP
│   └── Whitelisted in client's source database
│           ↓
Client's Database (PostgreSQL, MySQL, etc.)
    └── Firewall: Allow <client-static-ip>
```

**Setup per client project:**
```bash
# Reserve static IP
gcloud compute addresses create client-static-ip \
    --region=$REGION --project=$CLIENT_PROJECT

# Create Cloud Router
gcloud compute routers create nat-router \
    --network=default --region=$REGION --project=$CLIENT_PROJECT

# Create Cloud NAT with static IP
gcloud compute routers nats create nat-config \
    --router=nat-router --region=$REGION \
    --nat-external-ip-pool=client-static-ip \
    --nat-all-subnet-ip-ranges --project=$CLIENT_PROJECT
```

**Cost:** ~$40/month per client (Static IP ~$7 + Cloud NAT ~$32).

### **GCP Organization Structure**

```
Your Company GCP Organization
│
├── Folder: Management
│   ├── Project: control-plane-prod        ← Master portal, billing, monitoring
│   └── Project: b2b-recs-platform         ← Shared TFX compiler image (Artifact Registry)
│
├── Folder: Clients
│   ├── Project: client-acme-prod          ← Fully isolated stack
│   ├── Project: client-beta-prod          ← Fully isolated stack
│   └── Project: client-{name}-prod
│
└── Folder: Development
    ├── Project: template-dev              ← Development and testing
    └── Project: your-sandbox              ← Experimentation
```

### **Required GCP APIs**

Enable these APIs per client project:
```bash
gcloud services enable \
  bigquery.googleapis.com \
  cloudscheduler.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  aiplatform.googleapis.com \
  dataflow.googleapis.com \
  artifactregistry.googleapis.com
```

### **Region Selection Policy**

> **CRITICAL**: ALL GCP resources within a client project MUST be in the same region. Mixed regions cause query failures, increased latency, and potential GDPR violations.

| Region | Location | GPU Training | Use Case |
|--------|----------|--------------|----------|
| `europe-central2` | Warsaw, Poland | No | Default for EU clients (data + infra) |
| `europe-west4` | Netherlands | Yes (T4) | GPU training jobs |
| `us-central1` | Iowa, USA | Yes | US clients, largest GPU capacity |

**Common mistake:** BigQuery defaults to `US` multi-region when no location is specified. Always set location explicitly:
```bash
bq mk --location=$REGION --dataset $PROJECT_ID:dataset_name
```

### **Cost Estimates Per Client**

**Fixed monthly (~$140-200):**
| Component | Cost |
|-----------|------|
| Cloud Run (Django) | ~$30-50 |
| Cloud SQL (PostgreSQL) | ~$25-40 |
| Cloud NAT + Static IP | ~$40 |
| Cloud Scheduler | ~$0.10 |

**Variable (usage-based):**
| Operation | Cost |
|-----------|------|
| ETL run (Cloud Run + Dataflow) | ~$5-20/run |
| Quick Test (Vertex AI CPU) | ~$2-5/run |
| Full Training (Vertex AI GPU) | ~$10-50/run |
| BigQuery queries | ~$5-50/month |

**Typical total:** $190-440/month depending on training frequency.

### **Client Onboarding**

1. Create isolated GCP project under organization
2. Enable required APIs and configure IAM service accounts
3. Deploy Django app, ETL runner, and TFDV parser to Cloud Run
4. Set up Cloud NAT + Static IP for database connectivity
5. Grant client's Cloud Build access to shared TFX compiler image
6. Store client database credentials in Secret Manager
7. Run initial ETL and validate data in BigQuery
8. Provide client with Django UI URL and credentials

**Timeline:** 2-4 hours manual. **Future:** Automated via Terraform in ~30 minutes.

### **Future: Terraform Automation**

Infrastructure provisioning is currently manual. For scaling beyond the first few clients, the setup will be codified with Terraform:

```
terraform/
├── modules/
│   ├── client-project/     # GCP project, IAM, networking
│   ├── cloud-run/          # Django, ETL, TFDV services
│   ├── data-infra/         # BigQuery, GCS, Secret Manager
│   └── ml-pipeline/        # Vertex AI, Cloud Build
└── environments/
    └── client-{name}/      # Per-client tfvars
```

This will enable one-command client provisioning: `terraform apply -var="client_name=acme"`.

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
| [`docs/phase_etl.md`](docs/phase_etl.md) | **ETL page specification** (Connections + ETL Jobs + Dashboard + Runs) |
| [`etl_runner/etl_runner.md`](etl_runner/etl_runner.md) | ETL Runner technical documentation |
| [`docs/phase_configs.md`](docs/phase_configs.md) | **Datasets & Configs page specification** (Datasets + Features + Model Structure) |
| [`docs/phase_experiments.md`](docs/phase_experiments.md) | **Experiments page specification** (Quick Test + Dashboard) |
| [`docs/phase_experiments_implementation.md`](docs/phase_experiments_implementation.md) | **Experiments implementation guide (TFX, Cloud Build)** |
| [`docs/phase_experiments_changelog.md`](docs/phase_experiments_changelog.md) | Experiments detailed changelog history |
| [`docs/phase_training.md`](docs/phase_training.md) | **Training domain specification** (3-chapter page, 60+ APIs, GPU config, deployment, scheduling) |
| [`docs/models_registry.md`](docs/models_registry.md) | **Models Registry specification** (registered models, version tracking, deployment) |
| [`docs/training_full.md`](docs/training_full.md) | **Full training implementation guide** (GPU container, validation) |
| [`docs/del_datasets_migration.md`](docs/del_datasets_migration.md) | Migration plan: Dataset Manager → Configs page (reference) |
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
- **ETL System (Standalone Page)** - System-wide ETL with 4-chapter interface (~40 API endpoints):
  - ETL Dashboard (header KPIs, dashboard KPIs, scheduled jobs table, diverging chart)
  - ETL Runs (run cards with 4-stage progress bars, filtering, Cloud Run logs viewer)
  - Connections (16 source types, Secret Manager, 2-step wizard, bulk testing)
  - ETL Jobs (5-step wizard, file/database sources, schema editor, Cloud Scheduler)
- Multi-source ETL (databases + cloud storage files + NoSQL)
- **Firestore ETL** - Load NoSQL documents to BigQuery with automatic schema inference
- Automated scheduling via Cloud Scheduler
- BigQuery integration with auto-schema and compatibility validation
- Dataflow for large datasets (> 1M rows)
- **Datasets & Configs (Unified Page)** - Four-chapter workflow with ~60 API endpoints:
  - Configs Dashboard (KPI summary, coverage matrix, configuration flow)
  - Chapter 1: Dataset Management (4-step wizard, Visual Schema Builder, D3.js Pareto charts)
  - Chapter 2: Feature Engineering (drag-drop UI, tensor preview, TFX code generation)
  - Chapter 3: Model Structure (tower builder, presets, Retrieval/Ranking/Multitask models)
- **Experiments Page** - ✅ **Fully working!** Two-chapter workflow with ~25 API endpoints:
  - Chapter 1: Experiments Dashboard (3 clickable KPI sections, metrics trend, top configs, hyperparameter insights, D3.js heatmaps, dataset comparison, suggestions)
  - Chapter 2: Quick Test (2-step wizard with config previews, experiment cards with 6-stage progress, 6-filter bar, compare modal, reusable view modal)
- **Training Page** - ✅ **Fully working!** Three-chapter workflow with ~60 API endpoints:
  - Chapter 1: Models Registry (KPI summary, training activity calendar, filter bar, registered models table, schedules section, model view modal with 4 tabs)
  - Chapter 2: Best Experiments (3 model type KPI rows, top configurations table)
  - Chapter 3: Training Runs (3-step wizard, run cards with 8-stage pipeline progress, filter bar, reusable view modal in training_run mode)
  - Deployment: Cloud Run with TF Serving (native + ScaNN), Deploy Wizard with 3 presets, auto-deployment, integration API
  - Scheduling: 5 schedule types via Cloud Scheduler, reusable Schedule Modal, edit/pause/resume
  - 9-stage pipeline: Compile → ExampleGen → StatsGen → SchemaGen → Transform → Trainer → Evaluator → Register → Deploy

### **🔮 Next Up**
See [`next_steps.md`](next_steps.md) for detailed roadmap.

---

## GPU Training Configuration

### GPU Quota Status (as of 2026-01-18)

| GPU Type | Region | Quota | Status |
|----------|--------|-------|--------|
| T4 | europe-west4 | 2 | ✅ Approved & Validated |

### Regional Limitations

> ⚠️ **Important**: Vertex AI custom training does NOT support GPUs in all regions!

| Region | GPU Training | Notes |
|--------|--------------|-------|
| `europe-west4` (Netherlands) | ✅ Supported | **Use for training jobs** |
| `europe-central2` (Warsaw) | ❌ Not supported | Data/infrastructure only |
| `us-central1` (Iowa) | ✅ Supported | Largest GPU capacity |

Data can remain in `europe-central2` while training runs in `europe-west4` - cross-region access works seamlessly.

### Running GPU Training

**1. Request GPU Quota** (if not already done):
- Go to: https://console.cloud.google.com/iam-admin/quotas?project=YOUR_PROJECT
- Filter: Service = "Vertex AI API", search "nvidia_t4"
- Select region: `europe-west4` (NOT europe-central2!)
- Request: 2-4 GPUs

**2. Test GPU Access**:
```bash
gcloud ai custom-jobs create \
  --project=YOUR_PROJECT \
  --region=europe-west4 \
  --display-name="gpu-test" \
  --worker-pool-spec="replica-count=1,machine-type=n1-standard-16,accelerator-type=NVIDIA_TESLA_T4,accelerator-count=2,container-image-uri=europe-central2-docker.pkg.dev/YOUR_PROJECT/tfx-builder/tfx-trainer-gpu:latest" \
  --args="python","-c","import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

**3. Expected Output**:
```
[PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU'),
 PhysicalDevice(name='/physical_device:GPU:1', device_type='GPU')]
```

### GPU Container

Pre-built GPU container: `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer-gpu:latest`

| Component | Version |
|-----------|---------|
| TensorFlow | 2.15.1 |
| CUDA | 12.2 |
| TFX | 1.15.0 |
| TFRS | 0.7.6 |
| ScaNN | 1.3.0 |

See [`docs/training_full.md`](docs/training_full.md) for complete GPU configuration details.

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
| `tfdv-parser@b2b-recs.iam.gserviceaccount.com` | TFDV Parser | Storage Object Viewer |

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

### **Cloud Scheduler 401 Error (ETL)**
**Fix:** Grant OIDC token creation permission for ETL scheduler
```bash
gcloud iam service-accounts add-iam-policy-binding etl-runner@b2b-recs.iam.gserviceaccount.com \
  --member="serviceAccount:service-555035914949@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### **Training Schedule Not Executing (401 Error)**
**Cause:** The `training-scheduler` service account doesn't exist or lacks permissions.

**Fix:** Create and configure the training scheduler service account:
```bash
# 1. Create the service account
gcloud iam service-accounts create training-scheduler \
  --display-name="Training Scheduler Service Account" \
  --project=b2b-recs

# 2. Grant Cloud Scheduler agent permission to create OIDC tokens
gcloud iam service-accounts add-iam-policy-binding \
  training-scheduler@b2b-recs.iam.gserviceaccount.com \
  --member="serviceAccount:service-555035914949@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --project=b2b-recs

# 3. Grant the service account permission to invoke Cloud Run
gcloud run services add-iam-policy-binding django-app \
  --member="serviceAccount:training-scheduler@b2b-recs.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=europe-central2 \
  --project=b2b-recs
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

**January 26, 2026 - Training Scheduler IAM Fix**
- ✅ **Bug fix** - Training schedules not executing due to missing service account
- ✅ **Created `training-scheduler` service account** - Required for Cloud Scheduler OIDC authentication
- ✅ **IAM permissions configured** - `roles/iam.serviceAccountTokenCreator` and `roles/run.invoker`
- ✅ **Documentation updated** - Added troubleshooting section for training scheduler setup
- See Troubleshooting section below for setup commands

**January 18, 2026 - GPU Training Configuration & Quota**
- ✅ **GPU quota approved** - 2x T4 GPUs in `europe-west4` region
- ✅ **GPU validation passed** - TensorFlow successfully detects both GPUs
- ⚠️ **Regional limitation documented** - `europe-central2` does NOT support GPU training
- ✅ **Cross-region architecture** - Data in `europe-central2`, training in `europe-west4`
- ✅ **GPU container ready** - `tfx-trainer-gpu:latest` with TF 2.15.1 + CUDA 12.2
- See [Training Full docs](docs/training_full.md) for complete GPU configuration

**February 24, 2026 - System-Wide ETL Page**
- ✅ **Standalone ETL page** (`/etl/`) - ETL moved out of per-project scope to system-wide page
- ✅ **4-chapter interface** - ETL Dashboard → ETL Runs → Connections → ETL Jobs
- ✅ **5-step Create Wizard** - Connection → Tables/Files → Load Strategy → BigQuery Setup → Schedule
- ✅ **ETL Dashboard** - Header KPIs, dashboard KPIs, scheduled jobs table, diverging chart (D3.js)
- ✅ **ETL Run Cards** - 4-stage progress bar (Init → Validate → Extract → Load), Cloud Run Job logs viewer
- See [Phase: ETL docs](docs/phase_etl.md) for full ETL page specification

**February 3, 2026 - Configs Dashboard Chapter Added**
- ✅ **Configs Dashboard** - New first chapter on the Configs page with inventory and usage insights
- ✅ **KPI Summary Row** - 3 cards (Datasets, Features, Models) with total/active/unused counts and complexity bars
- ✅ **Coverage Matrix** - FeatureConfig × ModelConfig heatmap showing experiment counts per combination
- ✅ **Configuration Flow** - Visual diagram showing Dataset → FeatureConfig → ModelConfig relationships
- ✅ **Page now has 4 chapters** - Dashboard → Datasets → Feature Engineering → Model Structure
- See [Phase: Configs docs](docs/phase_configs.md) for Configs Dashboard details

**January 12, 2026 - Datasets & Configs Page Consolidation**
- ✅ **Unified page** - Dataset Manager merged into Configs page
- ✅ **Chapter structure** - Datasets → Feature Engineering → Model Structure (later extended with Dashboard)
- ✅ **Navigation update** - Single "Datasets & Configs" sidebar link
- ✅ **URL redirect** - Old `/models/<id>/dataset/` URL now redirects to `/models/<id>/configs/`
- ✅ **Legacy preservation** - Original `model_dataset.html` kept for rollback
- See [del_datasets_migration.md](docs/del_datasets_migration.md) for full migration details

**January 4, 2026 - Experiments Dashboard Enhanced**
- ✅ **8 analytical components** - Complete dashboard overhaul with metrics trend, top configs, hyperparameter insights
- ✅ **Metrics Trend Chart** - Line chart showing cumulative best Recall@100 improvement over time
- ✅ **Top Configurations Table** - Top 5 experiments ranked by R@100 with full hyperparameter details
- ✅ **Hyperparameter Insights** - Grid showing which LR, batch size, epochs values perform best
- ✅ **Dataset Performance** - Compare results across different datasets
- ✅ **Suggested Next Experiments** - AI-powered recommendations with "Run Experiment" buttons
- ✅ **Enhanced Summary Cards** - 8 KPIs: Total, Completed, Running, Failed, Best R@100, Avg R@100, Success Rate, Avg Duration
- ✅ **5 new API endpoints** - metrics-trend, hyperparameter-analysis, top-configurations, suggestions, dataset-comparison
- See [Phase: Experiments docs](docs/phase_experiments.md) for details

**December 22, 2025 - Enhanced Pipeline DAG Visualization (Phase 20)**
- ✅ **8-node TFX pipeline** - Pipeline Compile, Examples Gen, Stats Gen, Schema Gen, Transform, Trainer, Evaluator, Pusher
- ✅ **11 artifacts displayed** - Config, Examples, Statistics, Schema, Transform Graph, Transformed Examples, Model, ModelRun, Model Blessing, Evaluation, Model Endpoint
- ✅ **Bezier curve connections** - SVG curves with 4 types (left, right, down-left, down-right)
- ✅ **White background styling** - Clean background with subtle dot grid, 264px node width
- ✅ **Node renaming** - BigQueryExampleGen → Examples Gen, StatisticsGen → Stats Gen, SchemaGen → Schema Gen
- ✅ **New Evaluator/Pusher nodes** - Placeholder components for full-scale training pipeline
- See [Phase 20: Enhanced Pipeline DAG](docs/phase_experiments_implementation.md#phase-20-enhanced-pipeline-dag-visualization-december-2025) for details

**December 21, 2025 - Schema Fix & TFDV Hybrid Visualization (Phase 19)**
- ✅ **Schema field fix** - Updated `renderSchema()` to use correct field names (`feature_type`, `presence`)
- ✅ **Removed broken TFDV modal** - Deleted iframe-based modal that rendered incorrectly
- ✅ **Open in New Tab** - TFDV now opens as standalone page in new browser tab
- See [Phase 19: Schema Fix](docs/phase_experiments_implementation.md#phase-19-schema-fix-and-tfdv-hybrid-visualization-december-2025) for details

**December 20, 2025 - TFDV Parser Microservice (Phase 18)**
- ✅ **TFDV Parser Cloud Run Service** - Dedicated Python 3.10 service for parsing TFX artifacts
- ✅ **Data Insights now working** - Rich statistics display in experiment View modal
- ✅ **Statistics Parser** - Parse FeatureStats.pb with count, missing%, mean, std_dev, zeros%, min/median/max, histograms
- ✅ **Schema Parser** - Parse schema.pbtxt files from SchemaGen component
- ✅ **Mini visualizations** - Inline histograms for numeric features, bar charts for categorical top values
- ✅ **TFDV HTML visualization** - Full TFDV visualization available in modal
- ✅ **Service-to-service auth** - Identity token authentication from Django to Cloud Run
- ✅ **Local dev support** - Fallback to `gcloud auth print-identity-token` for development
- See [Phase 18: TFDV Parser Microservice](docs/phase_experiments_implementation.md#phase-18-tfdv-parser-microservice-december-2025) for details

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
- See [Phase: Configs docs](docs/phase_configs.md) for Model Structure details

**December 13, 2025 - Ranking Model Enhancements**
- ✅ **LayerNormalization** - Added as 4th layer type to all towers (Buyer, Product, Rating Head)
- ✅ **Rating Head drag-drop** - Layers now draggable/reorderable in Rating Head (output layer locked)
- ✅ **Compare Modal for Ranking** - Added Rating Head comparison section with purple theme
- ✅ **Mixed model comparison** - Shows "N/A" for non-applicable settings when comparing Ranking vs Retrieval
- ✅ **Loss Function comparison** - Added to Training Settings section in Compare modal
- See [Phase: Configs docs](docs/phase_configs.md) for Model Structure details

**December 13, 2025 - Quick Test Moved to Experiments Page**
- ✅ **Page split** - Quick Test functionality moved from Modeling to dedicated Experiments page
- ✅ **New Experiments page** (`model_experiments.html`) - 1,129 lines of new code
- ✅ **Modeling page reduced** - Removed ~714 lines, now focused on Feature + Model Config only
- ✅ **Clean separation** - Modeling = Configure, Experiments = Run and Compare
- ✅ **Documentation updated** - `phase_configs.md`, `phase_experiments.md`
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
- See [Phase: Configs docs](docs/phase_configs.md) for Model Structure details

**December 10, 2025 - Quick Test Pipeline Integration**
- ✅ **Vertex AI Pipeline** - Full KFP v2 pipeline for validating feature configs
- ✅ **QuickTest model** - Django model for tracking pipeline runs with status, progress, results
- ✅ **Pipeline Service** - Submit pipelines, poll status, extract metrics from GCS
- ✅ **UI Integration** - "Test" button, configuration dialog, progress modal, results display
- ✅ **GCS Buckets** - Created with lifecycle policies (see GCS Storage Management)
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
- ✅ Updated documentation (phase_configs.md)

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

**Project Stats:** 25+ models • 70+ files • 200+ URL patterns • ~15,000 LOC • 100% auth coverage

**Deployed:** November 2025 | **Region:** EU (Warsaw) | **Status:** Production Ready ✅
