# B2B Recommendation System - SaaS Implementation Plan

## Document Purpose
This document outlines the agreed-upon architecture and implementation strategy for transforming a client-specific TFRS (Two-Tower Retrieval System) implementation into a multi-tenant B2B SaaS platform.

**Last Updated**: 2025-11-18

---

## Executive Summary

### Vision
Build a SaaS platform where business users can build, train, and deploy production-grade recommendation models without technical expertise or direct GCP interaction.

### Core Principles
1. **Complete Isolation**: Each client gets their own GCP project - zero resource sharing
2. **Simplicity First**: Business users should be able to operate the system without coding
3. **Cost Efficiency**: Pay-per-use model, no expensive always-on infrastructure
4. **Template-Based**: Standardized components, deployed per client
5. **Iterate Fast**: Build working product first, automate infrastructure later

---

## System Architecture

### Three-Layer Model

```
┌─────────────────────────────────────────────────────────┐
│         LAYER 1: MASTER CONTROL PLANE                   │
│         (Your Company's GCP Management)                 │
│                                                          │
│  - Client Portal (subscription, provisioning)           │
│  - Billing Aggregation Dashboard                        │
│  - Cross-Project Monitoring                             │
│  - Template Version Management                          │
└─────────────────────────────────────────────────────────┘
                          ↓ (provisions)
┌─────────────────────────────────────────────────────────┐
│         LAYER 2: CLIENT PROJECT (PER CLIENT)            │
│         (Fully Isolated GCP Project)                    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Django Web Application (Cloud Run)               │   │
│  │  - Pipeline Configuration UI                     │   │
│  │  - Experiment Dashboard                          │   │
│  │  - Feature Engineering Designer                  │   │
│  │  - Model Deployment Manager                      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ETL Infrastructure (Cloud Run + Scheduler)       │   │
│  │  - Containerized ETL Jobs                        │   │
│  │  - Scheduled Data Extraction                     │   │
│  │  - Source DB Connectors                          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ML Pipeline (Vertex AI Custom Jobs)              │   │
│  │  - Data Extractor                                │   │
│  │  - Vocab Builder                                 │   │
│  │  - Trainer (Multi-GPU)                           │   │
│  │  - Orchestrated via Celery                       │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ MLflow Server (Cloud Run)                        │   │
│  │  - Experiment Tracking                           │   │
│  │  - Model Registry                                │   │
│  │  - Artifact Storage (GCS)                        │   │
│  │  - Metadata Storage (Cloud SQL)                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Model Serving (Cloud Run)                        │   │
│  │  - FastAPI Service                               │   │
│  │  - Batch Predictions                             │   │
│  │  - Version Management                            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Data Infrastructure                              │   │
│  │  - BigQuery (datasets, tables, views)            │   │
│  │  - GCS Buckets (models, artifacts, data)         │   │
│  │  - Secret Manager (credentials, API keys)        │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Key Architecture Decisions

#### 1. Separate GCP Project Per Client
**Rationale:**
- **Zero Cross-Tenant Risk**: Impossible for data to leak between clients
- **Simple Billing**: Each project has isolated costs, easy to track
- **Independent Scaling**: Client A's workload doesn't affect Client B
- **Client Portability**: Client can take ownership of their project if needed
- **No Quota Conflicts**: Each project has independent GPU/resource quotas
- **Regulatory Compliance**: Perfect for GDPR, data residency requirements

**Implementation:**
- All client resources live in their dedicated GCP project
- Projects created under your GCP Organization
- You maintain organization-level admin access
- Client never touches GCP console directly

#### 2. ETL Per Client (Not Shared)
**Rationale:**
- **Cost Efficiency**: Cloud Run + Scheduler = $10-20/month vs Cloud Composer $120/month base
- **True Isolation**: ETL failures don't cascade across clients
- **Simplicity**: All resources in one project, no cross-project permissions
- **Flexibility**: Each client can have custom ETL schedules and logic

**Implementation:**
- ETL packaged as Docker container
- Deployed to Cloud Run in client project
- Triggered by Cloud Scheduler (configurable frequency)
- Reads from client source databases
- Writes to BigQuery in same project
- Same image template, different instances per client

#### 3. No Shared Infrastructure Layer
**Decision**: Original architecture had "Layer 3: Shared ETL Infrastructure" - **REMOVED**

**Why:**
- Contradicts isolation principle
- Adds cost and complexity
- Cloud Composer unnecessary for simple scheduled jobs
- Cross-project permissions complicate security

**What's Actually Shared:**
- Docker image templates (same images deployed per client)
- Terraform modules (when we get there)
- Configuration patterns and best practices
- Your operational knowledge and support

#### 4. Django as the Control Interface
**Rationale:**
- Mature framework with excellent admin interface
- Strong multi-tenancy support
- Rich ecosystem for common patterns
- You have experience building Django apps
- Easy to build user-friendly frontends

**Client-Facing Django App (Per Project):**
- Simplified UI for business users
- No code required for standard operations
- Configuration over customization
- Guided workflows with smart defaults

**Master Django Portal (Control Plane):**
- Your internal management system
- Client provisioning and billing
- Cross-project monitoring
- Support tools

#### 5. Network Architecture & Static IPs
**Challenge:**
- Cloud Run services (Django, ETL) have dynamic outbound IPs by default
- Client databases often require IP whitelisting for security
- Each client needs predictable, stable IP address for firewall rules

**Solution: Cloud NAT + Reserved Static IP per Client Project**

**Architecture:**
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
Client's Database (PostgreSQL, MySQL, MongoDB, etc.)
    ├── Firewall: Allow 34.120.45.67 (client's static IP)
    └── Behind corporate VPN/firewall
```

**Implementation Per Client Project:**
1. **Reserve Static IP**: One dedicated external IP address per project
2. **Create Cloud Router**: Routes traffic within the VPC
3. **Configure Cloud NAT**: NAT gateway using the reserved static IP
4. **Result**: All outbound connections from Cloud Run use the static IP

**Cost Impact:**
- Static IP reservation: ~$7/month
- Cloud NAT usage: ~$32/month
- **Total: ~$40/month per client** for stable networking

**Client Benefits:**
- Client whitelists ONE IP address in their database firewall
- IP never changes - connection remains stable
- No VPN or complex networking required from client side
- Works with on-premise databases behind corporate firewalls

**Alternative Approaches (Not Recommended):**
- **VPN/Interconnect**: Complex, expensive, not scalable for multi-tenant SaaS
- **Agent/Connector**: Requires client to install software, adds support burden
- **Cloud Databases Only**: Limits client flexibility, many enterprises have on-prem databases

**Setup Steps:**
```bash
# Reserve static IP
gcloud compute addresses create client-static-ip \
    --region=us-central1 \
    --project=client-{name}-prod

# Create Cloud Router
gcloud compute routers create nat-router \
    --network=default \
    --region=us-central1 \
    --project=client-{name}-prod

# Create Cloud NAT with static IP
gcloud compute routers nats create nat-config \
    --router=nat-router \
    --region=us-central1 \
    --nat-external-ip-pool=client-static-ip \
    --nat-all-subnet-ip-ranges \
    --project=client-{name}-prod
```

**Client Onboarding:**
- Provide client with their dedicated static IP: `34.120.45.67`
- Client adds IP to database whitelist/firewall rules
- Enable SSL/TLS for encrypted connections
- Test connection from Django UI

**Rationale:**
- **Essential for enterprise clients**: Most have on-premise databases with strict security
- **Professional**: Shows proper enterprise architecture, builds trust
- **Cost-effective**: $40/month is minimal compared to alternative solutions
- **Scalable**: Terraform-automated, works for unlimited clients

---

## GCP Organization Structure

### Recommended Hierarchy

```
Your Company GCP Organization
│
├── Folder: Management
│   └── Project: control-plane-prod
│       - Master client portal
│       - Billing aggregation (BigQuery billing export)
│       - Cross-project monitoring
│       - Terraform state (when implemented)
│       - Admin tools
│
├── Folder: Clients
│   ├── Project: client-acme-prod
│   │   - Complete isolated stack
│   │
│   ├── Project: client-beta-prod
│   │   - Complete isolated stack
│   │
│   └── Project: client-{name}-prod
│       - Complete isolated stack per client
│
└── Folder: Development
    ├── Project: template-dev
    │   - Development and testing
    │   - Template validation
    │
    └── Project: your-sandbox
        - Experimentation
        - Feature development
```

### Naming Conventions

**Projects:**
- Control plane: `control-plane-prod`
- Client projects: `client-{sanitized-company-name}-{env}`
- Examples: `client-acmecorp-prod`, `client-retailco-prod`

**Resources (within client projects):**
- BigQuery datasets: `{purpose}` (e.g., `raw_data`, `features`, `predictions`)
- GCS buckets: `{project-id}-{purpose}` (e.g., `client-acmecorp-prod-ml-artifacts`)
- Cloud Run services: `{service-name}` (e.g., `django-app`, `model-serving`, `etl-runner`)

**Labels (all resources):**
- `client_id`: Unique identifier
- `template_version`: Which version of the stack
- `environment`: prod/staging/dev
- `cost_center`: For billing attribution
- `created_date`: Provisioning timestamp

---

## Per-Client Project Components

### Detailed Component Breakdown

#### 1. Django Application (User Interface)

**Purpose**: Business-user-friendly interface for all ML operations

**Key Features:**
- **Dashboard**: Pipeline status, recent runs, model performance
- **Pipeline Wizard**: Step-by-step configuration with defaults
- **Dataset Manager**: Browse BigQuery tables, preview data, create views
- **Feature Engineering**: Visual designer for creating features (no SQL required)
- **Training Interface**: Configure and launch training jobs
- **Experiment Dashboard**: View MLflow experiments, compare models
- **Deployment Manager**: One-click deployment, version switching
- **Monitoring**: Track predictions, costs, performance

**Technology:**
- Django 4.2+ with Django Rest Framework
- Celery for async task orchestration
- Redis for Celery broker
- PostgreSQL for Django metadata
- Vue.js for reactive UI components
- Tailwind CSS for styling

**Deployment:**
- Containerized Django app
- Deployed to Cloud Run
- Auto-scaling based on traffic
- Custom domain: `{clientname}.yoursaas.com`
- Environment variables for project-specific config

#### 2. ETL Infrastructure

**Purpose**: Automated data extraction from source systems to BigQuery

**Architecture:**
```
Source Database (Client's systems)
       ↓
Cloud Scheduler (triggers on schedule)
       ↓
Cloud Run Job (ETL container)
       ↓
BigQuery Dataset (client project)
```

**Components:**
- **ETL Container**: Python-based Apache Beam pipeline or custom ETL
- **Connectors**: PostgreSQL, MySQL, SQL Server (priority order)
- **Cloud Scheduler**: Configurable schedule (daily, weekly, monthly)
- **Secret Manager**: Database credentials stored securely
- **Monitoring**: Cloud Logging for ETL job logs

**Workflow:**
1. Cloud Scheduler triggers Cloud Run job at scheduled time
2. ETL container starts, pulls credentials from Secret Manager
3. Connects to source database(s)
4. Extracts data based on configuration
5. Transforms and validates
6. Loads to BigQuery tables in client project
7. Logs completion status
8. Django app polls for completion and updates dashboard

**Cost Model:**
- Cloud Run: Pay only when ETL job running (~5-30 min/day)
- Cloud Scheduler: $0.10/job/month
- Estimated: $10-20/month per client

#### 3. ML Pipeline Components

**Purpose**: Four-stage pipeline for building recommendation models

**Stage 1: Data Extractor (Vertex AI Custom Job)**
- Reads from BigQuery
- Extracts 90-day transaction history
- Includes product metadata (names, categories, subcategories)
- Filters top 80% revenue products
- Outputs compressed TFRecord files to GCS
- Machine type: n1-standard-4
- Runtime: ~30-60 minutes

**Stage 2: Vocab Builder (Vertex AI Custom Job)**
- Reads TFRecord files from Stage 1
- Builds vocabularies for all features
- Creates revenue/timestamp buckets
- Outputs vocabularies.json to GCS
- Machine type: n1-standard-4
- Runtime: ~3-5 minutes

**Stage 3: Trainer (Vertex AI Custom Job with GPUs)**
- Two-tower retrieval architecture
- 8 features: customer_id, product_id, revenue, city, timestamp, art_name, category, subcategory
- Multi-GPU training (4x T4/V100/L4)
- Early stopping and adaptive learning rate
- MLflow logging for experiments
- Outputs: saved_model, query_model, candidate_model
- Machine type: n1-standard-32 with 4x GPUs
- Runtime: 2-6 hours depending on dataset size
- Target performance: 45-47% Recall@100

**Stage 4: Deployment (Automated)**
- Updates Cloud Run model serving service
- Switches to new model version
- Health check validation
- Rollback capability via Cloud Run revisions

**Orchestration:**
- Django triggers Stage 1 via Celery task
- Celery task polls Vertex AI job status
- On completion, triggers Stage 2
- Chain continues through all stages
- Django UI shows real-time progress
- Email notifications on completion/failure

#### 4. MLflow Server

**Purpose**: Experiment tracking and model registry

**Architecture:**
- MLflow server as Cloud Run service
- Backend: GCS for artifacts (models, plots, files)
- Database: Cloud SQL PostgreSQL for metadata
- Accessed via Django UI (iframe or API integration)

**What Gets Tracked:**
- Training hyperparameters (epochs, batch size, learning rate)
- Model architecture configuration
- Training metrics (loss, recall@5/10/50/100)
- Dataset metadata (size, date range, cities)
- Model artifacts (saved models)
- Training duration and costs
- Hardware configuration used

**Integration:**
- Trainer component auto-logs to MLflow
- Minimal code changes: `mlflow.tensorflow.autolog()`
- Django displays experiments in user-friendly format
- Compare models side-by-side
- Tag best models for deployment

**Deployment:**
- Single Cloud Run service per client project
- Always-on with min instances: 1
- Low cost: ~$20-30/month per client

#### 5. Model Serving

**Purpose**: Production API for getting recommendations

**Existing Implementation** (from `past/recs/cloud_run_service/`):
- FastAPI-based REST API
- Batch processing (up to 1000 customers per request)
- ~2ms inference time per customer
- Health checks and monitoring

**Endpoints:**
- `GET /health`: Service health status
- `POST /recommend`: Single customer recommendations
- `POST /recommend-batch`: Batch recommendations
- `GET /model-info`: Model metadata and metrics

**Deployment:**
- Cloud Run service
- Auto-scaling: 1-10 instances
- Machine: 4Gi memory, 2 CPU
- Traffic splitting for A/B testing (future)
- Multiple revisions for version management

**Workflow:**
1. Django deployment process updates service
2. Sets environment variables (MODEL_BASE_PATH, VOCAB_PATH)
3. Cloud Run pulls new model from GCS
4. Health check validates model loaded correctly
5. Traffic switches to new revision
6. Old revision kept for rollback

#### 6. Data Infrastructure

**BigQuery Structure:**
```
Project: client-acme-prod
├── Dataset: raw_data
│   ├── transactions (from ETL)
│   ├── products (from ETL)
│   └── customers (from ETL)
│
├── Dataset: features
│   ├── customer_features (views/tables)
│   ├── product_features (views/tables)
│   └── transaction_features (views/tables)
│
├── Dataset: ml_datasets
│   └── training_metadata (pipeline runs, stats)
│
└── Dataset: predictions
    ├── recommendation_history
    └── prediction_logs
```

**GCS Bucket Structure:**
```
gs://client-acme-prod-ml-platform/
├── datasets/
│   └── {run_id}/
│       ├── raw_data/*.tfrecord.gz
│       ├── vocabularies/vocabularies.json
│       └── metadata.json
│
├── models/
│   └── {version}/
│       ├── saved_model/
│       ├── query_model/
│       └── candidate_model/
│
├── experiments/
│   └── mlflow-artifacts/
│       └── {experiment_id}/
│
├── etl/
│   ├── configs/
│   └── logs/
│
└── backups/
    └── {date}/
```

**Secret Manager:**
- `source-db-credentials`: Connection string for client source database
- `api-keys`: External service API keys
- `service-account-keys`: For cross-service authentication

---

## Client Lifecycle

### 1. Client Onboarding

**Step 1: Initial Setup (Your Side)**
- Client signs contract and provides requirements
- You create GCP project manually (later: Terraform)
- Set up billing link to your organization
- Configure project IAM (service accounts, roles)

**Step 2: Infrastructure Provisioning**
- Create BigQuery datasets
- Create GCS buckets
- Deploy Django application to Cloud Run
- Deploy MLflow server
- Set up Secret Manager
- Configure Cloud Scheduler for ETL

**Step 3: Data Onboarding**
- Client provides source database credentials
- You store credentials in Secret Manager
- Configure ETL container with connection details
- Test ETL run and validate data extraction
- Set up ETL schedule

**Step 4: Initial Model Training**
- Configure first pipeline run through Django UI
- Run full pipeline: data extraction → vocab → training → deployment
- Validate model performance
- Deploy to production

**Step 5: Handoff to Client**
- Provide client with Django UI URL and credentials
- Walk through interface and key features
- Train client on basic operations
- Set up monitoring and alerts

**Timeline**: 2-4 hours manual (future: 30 minutes automated)

### 2. Day-to-Day Operations (Client)

**Typical Client Workflow:**
1. Log into Django UI (`{clientname}.yoursaas.com`)
2. View dashboard with data freshness, model performance
3. Optionally: adjust pipeline parameters or create new feature engineering
4. Click "Train New Model" button
5. Select configuration (or use defaults)
6. Submit training job
7. Monitor progress in UI (real-time status updates)
8. Receive email when training completes
9. Review experiment results and metrics
10. Compare with previous models in MLflow dashboard
11. If better: click "Deploy to Production"
12. Model automatically deployed, endpoint URL provided
13. Integration code updated to use new endpoint (if needed)

**Time Investment**: 5-10 minutes active work, 2-6 hours training time

### 3. Automated Processes

**Scheduled ETL:**
- Runs daily/weekly/monthly (client configurable)
- Updates BigQuery with fresh data
- Notifications on success/failure

**Model Retraining:**
- Optional: automatic retraining on schedule
- Triggered when new data available
- Auto-deploy if metrics improve

**Monitoring:**
- Prediction volume tracking
- Model performance metrics
- Cost tracking and alerts
- Anomaly detection

**Backups:**
- Daily BigQuery table snapshots
- Model versioning in GCS
- Configuration backup

### 4. Your Operations (Control Plane)

**Daily:**
- Monitor all client project health via aggregated dashboard
- Review cost anomalies and budget alerts
- Respond to support tickets
- Check pipeline success rates

**Weekly:**
- Review performance metrics across all clients
- Identify common issues or feature requests
- Plan improvements and bug fixes

**Monthly:**
- Pull billing data from all client projects
- Calculate costs per client
- Generate invoices (manual initially)
- Review resource utilization
- Plan capacity and quotas

**Quarterly:**
- Release new template version with improvements
- Plan rollout to client projects
- Review overall platform health
- Optimize costs and performance

---

## Implementation Strategy

### Guiding Principles

1. **Manual First, Automate Later**
   - First 1-2 clients: completely manual to learn the process
   - Document every step meticulously
   - Identify pain points and automation opportunities
   - Only then invest in automation

2. **One Working System Before Many**
   - Get a single client project fully functional
   - Validate all components work end-to-end
   - Prove the business model
   - Then replicate to more clients

3. **Infrastructure Comes After Product**
   - Don't start with Terraform
   - Build the Django app and get ML pipeline working first
   - Learn what infrastructure you actually need
   - Then codify it with Terraform for client #2+

4. **Simple Tech Stack**
   - Use managed services (Cloud Run, Vertex AI, Cloud SQL)
   - Avoid complex orchestration (no Kubernetes, no multi-machine setups)
   - Leverage existing working components from `past/` folder
   - Add complexity only when absolutely necessary

---

## Phase 1: Build Single Working System (Weeks 1-6)

### Goal
Create one complete, functional client project with all components working end-to-end.

### Week 1-2: Project Setup & Django Foundation

**Activities:**
- **GCP Setup**:
  - Create GCP Organization (if not exists)
  - Create control-plane project
  - Create first client project manually: `template-dev`
  - Set up billing export to BigQuery
  - Configure IAM and service accounts

- **Django Application**:
  - Initialize Django project structure
  - Set up models: Pipeline, PipelineRun, Dataset, MLModel, Deployment
  - Create basic admin interface
  - Implement user authentication
  - Deploy to Cloud Run (simple version)

- **Local Development Environment**:
  - Docker Compose for local development
  - PostgreSQL for Django database
  - Redis for Celery
  - Mock GCP services for testing

**Deliverables:**
- Running Django app on Cloud Run
- Admin interface accessible
- Basic authentication working
- Local dev environment functional

### Week 3: Port ML Pipeline Components

**Activities:**
- **Container Setup**:
  - Review existing components in `past/` folder
  - Create Dockerfiles for each component
  - Build and test containers locally
  - Push to Artifact Registry

- **Component Integration**:
  - Data Extractor: parameterize for different configs
  - Vocab Builder: ensure it works with new data paths
  - Trainer: validate GPU training works in Vertex AI
  - Serving: deploy existing FastAPI service

- **Testing**:
  - Manual end-to-end pipeline run
  - Data extraction → vocab building → training → deployment
  - Validate outputs at each stage
  - Document any issues or adjustments needed

**Deliverables:**
- All 4 components containerized
- Images in Artifact Registry
- Manual pipeline run successful
- Model deployed and serving predictions

### Week 4: Django Integration with ML Pipeline

**Activities:**
- **Celery Setup**:
  - Configure Celery with Redis
  - Create tasks for each pipeline stage
  - Implement job status polling
  - Error handling and retry logic

- **Django UI Development**:
  - Pipeline configuration form
  - Trigger pipeline button
  - Real-time status updates
  - Log viewer
  - Simple dashboard

- **Vertex AI Integration**:
  - Python client for creating custom jobs
  - Job status monitoring
  - Resource cleanup on failure

**Deliverables:**
- Pipeline triggerable from Django UI
- Real-time status visible
- Logs accessible in UI
- Error handling working

### Week 5: MLflow Integration

**Activities:**
- **MLflow Server Setup**:
  - Deploy MLflow as Cloud Run service
  - Configure Cloud SQL backend
  - Set up GCS artifact storage
  - Test basic logging

- **Trainer Integration**:
  - Add MLflow logging to trainer component
  - Log hyperparameters, metrics, artifacts
  - Validate experiments appear in MLflow UI

- **Django Display**:
  - Embed MLflow UI in Django (iframe or API)
  - Create experiment comparison view
  - Model registry integration
  - Tag models for deployment

**Deliverables:**
- MLflow server running
- Experiments tracked automatically
- Visible in Django UI
- Model comparison functional

### Week 6: ETL Setup & End-to-End Testing

**Activities:**
- **ETL Development**:
  - Create ETL container (use Apache Beam or custom)
  - Add database connectors (PostgreSQL priority)
  - Configure Cloud Scheduler
  - Store credentials in Secret Manager

- **ETL Testing**:
  - Test with sample source database
  - Validate data extraction
  - Confirm BigQuery loading
  - Schedule daily runs

- **Complete Integration Testing**:
  - ETL runs → data in BigQuery
  - Trigger pipeline from Django
  - Full pipeline executes successfully
  - Model deployed and serving
  - MLflow shows experiment
  - All monitoring working

- **Documentation**:
  - Document every GCP resource created
  - List all configurations and settings
  - Screenshot every step
  - Note costs incurred

**Deliverables:**
- Working ETL pipeline
- Complete end-to-end system functional
- All components integrated
- Comprehensive documentation of setup
- Cost analysis for one full pipeline run

### Success Criteria for Phase 1
- [ ] Single client project fully operational
- [ ] Django UI deployed and accessible
- [ ] ETL running on schedule
- [ ] ML pipeline executable from UI
- [ ] MLflow tracking experiments
- [ ] Model deployed and serving predictions
- [ ] All costs tracked and documented
- [ ] Complete setup documentation

---

## Phase 2: Learn & Document (Weeks 7-8)

### Goal
Understand costs, requirements, and prepare for replication.

### Week 7: Cost Analysis & Optimization

**Activities:**
- **Cost Breakdown**:
  - Analyze billing data from Phase 1
  - Break down costs by service (Vertex AI, BigQuery, Cloud Run, etc.)
  - Calculate cost per pipeline run
  - Calculate cost per 100K predictions
  - Identify cost optimization opportunities

- **Performance Analysis**:
  - Measure pipeline execution times
  - Identify bottlenecks
  - Test different machine types and configurations
  - Optimize for cost/performance balance

- **Resource Right-Sizing**:
  - Are we over-provisioned anywhere?
  - Can we use preemptible GPUs?
  - Are Cloud Run instances sized correctly?
  - BigQuery cost optimization (partitioning, clustering)

**Deliverables:**
- Complete cost breakdown spreadsheet
- Cost per pipeline run documented
- Cost per prediction documented
- Optimization recommendations
- Updated configurations for cost efficiency

### Week 8: Documentation & Requirements

**Activities:**
- **Architecture Documentation**:
  - Complete list of all GCP resources used
  - Architecture diagrams
  - Data flow diagrams
  - Security and IAM documentation

- **Setup Documentation**:
  - Step-by-step guide to recreate the system
  - All GCP console clicks documented
  - All configuration files saved
  - Environment variables documented

- **User Experience Review**:
  - What worked well in Django UI?
  - What was confusing?
  - What features are missing?
  - How can we simplify further?

- **Requirements Refinement**:
  - What needs to be configurable per client?
  - What can be standardized?
  - What features are essential vs nice-to-have?
  - What pain points need solving?

**Deliverables:**
- Complete architecture documentation
- Detailed setup runbook
- UX improvement list
- Requirements document
- Lessons learned document

---

## Phase 3: Templatize & Automate (Weeks 9-12)

### Goal
Convert manual setup into automated, repeatable process.

### Week 9-10: Terraform Development

**Activities:**
- **Terraform Module Structure**:
  ```
  terraform/
  ├── modules/
  │   ├── client-project/
  │   │   ├── main.tf (project, IAM)
  │   │   ├── bigquery.tf
  │   │   ├── storage.tf
  │   │   ├── cloud-run.tf
  │   │   └── variables.tf
  │   ├── django-app/
  │   ├── mlflow-server/
  │   └── etl-pipeline/
  └── environments/
      ├── template-dev/
      └── client-{name}/
  ```

- **Infrastructure as Code**:
  - Convert Phase 1 manual steps to Terraform
  - Parameterize for different clients
  - Test by creating second project
  - Validate all resources created correctly

- **Configuration Management**:
  - Environment variables template
  - Secrets template
  - Django settings per environment
  - BigQuery schema definitions

**Deliverables:**
- Terraform modules for all infrastructure
- Tested with 2-3 test projects
- Documentation on using Terraform
- Variable definitions and examples

### Week 11: Control Plane Development

**Activities:**
- **Master Portal (control-plane-prod)**:
  - Client management interface
  - Project provisioning wizard
  - Billing dashboard (pull from BigQuery billing export)
  - Cross-project monitoring dashboard

- **Automation Scripts**:
  - Project creation orchestration
  - Terraform execution automation
  - DNS and SSL setup
  - Health check validation

- **Monitoring Setup**:
  - Organization-level Cloud Monitoring
  - Aggregate metrics across projects
  - Alerting for failures
  - Cost anomaly detection

**Deliverables:**
- Control plane Django app deployed
- Provisioning wizard functional
- Billing dashboard showing costs
- Monitoring dashboard operational

### Week 12: Template Validation & Polish

**Activities:**
- **Create Test Clients**:
  - Provision 3 test client projects using automation
  - Validate all components work
  - Test different configurations
  - Identify and fix issues

- **User Experience Polish**:
  - Implement UX improvements from Week 8
  - Add helpful tooltips and documentation
  - Create onboarding wizard
  - Improve error messages

- **Documentation**:
  - User guide for Django UI
  - Admin guide for your operations
  - Troubleshooting guide
  - API documentation

- **Security Review**:
  - Audit IAM permissions
  - Review Secret Manager usage
  - Check data isolation
  - Validate no cross-tenant access possible

**Deliverables:**
- 3 test projects provisioned automatically
- Polished Django UI
- Complete documentation
- Security audit passed
- Ready for first real client

---

## Phase 4: First Real Client (Weeks 13-14)

### Goal
Onboard first paying customer, validate everything works.

### Week 13: Client Onboarding

**Activities:**
- **Pre-Onboarding**:
  - Contract signed
  - Requirements gathering
  - Source database access provided

- **Provisioning**:
  - Use Terraform to create client project
  - Deploy Django app
  - Configure DNS and SSL
  - Set up ETL with client credentials

- **Initial Data Load**:
  - Run ETL to extract historical data
  - Validate data quality
  - Create initial BigQuery views
  - Prepare for first training run

- **Client Training**:
  - Walk through Django UI
  - Explain pipeline configuration
  - Show how to trigger training
  - Review model deployment process

**Deliverables:**
- Client project provisioned
- ETL running successfully
- Client trained on system
- Initial data loaded

### Week 14: First Production Run & Support

**Activities:**
- **First Training Run**:
  - Client triggers pipeline (or you do with them)
  - Monitor closely for any issues
  - Validate model training succeeds
  - Deploy model to production

- **Integration Support**:
  - Help client integrate prediction API
  - Test predictions in their system
  - Validate accuracy and performance

- **Feedback Collection**:
  - What worked well?
  - What was confusing?
  - What features are missing?
  - Any bugs or issues?

- **Iteration**:
  - Quick fixes for any critical issues
  - Plan improvements based on feedback

**Deliverables:**
- Client's first model in production
- Predictions serving in their system
- Feedback documented
- Support process validated

---

## Phase 5: Scale & Iterate (Week 15+)

### Goal
Onboard additional clients, iterate on product.

### Ongoing Activities

**Client Acquisition**:
- Onboard 2-3 clients per month initially
- Each client validates the template
- Identify unique requirements
- Decide what to productize vs custom work

**Product Development**:
- Prioritize features based on client feedback
- Release new template versions
- Roll out updates to existing clients
- A/B test UI improvements

**Operations**:
- Monitor all client projects
- Respond to support requests
- Optimize costs across all deployments
- Track metrics (uptime, success rate, costs)

**Business Development**:
- Track costs per client vs revenue
- Understand unit economics
- Refine pricing model
- Plan for profitability

---

## Technology Stack

### Per-Client Project Stack

**Frontend:**
- Vue.js 3 for reactive components
- Tailwind CSS for styling
- Chart.js for metrics visualization
- Django templates for base layout

**Backend:**
- Django 4.2+ (LTS version)
- Django Rest Framework for API
- Celery 5.3+ for async tasks
- Redis for Celery broker and caching
- PostgreSQL 15+ for Django database

**ML Pipeline:**
- TensorFlow 2.15+ (existing code)
- Apache Beam for data extraction
- Python 3.10+
- Docker for containerization

**GCP Services:**
- Cloud Run (Django, MLflow, model serving, ETL)
- Vertex AI (custom training jobs with GPUs)
- BigQuery (data warehouse)
- Cloud Storage (artifacts, models, data)
- Cloud SQL PostgreSQL (Django DB, MLflow DB)
- Secret Manager (credentials)
- Cloud Scheduler (ETL triggers)
- Artifact Registry (Docker images)
- Cloud Logging (centralized logs)
- Cloud Monitoring (metrics and alerts)

**ML Operations:**
- MLflow 2.9+ for experiment tracking
- Docker for reproducibility
- GCS for model artifacts
- Cloud SQL for MLflow metadata

### Control Plane Stack

**Infrastructure:**
- Terraform 1.5+ for infrastructure as code
- Cloud Build for CI/CD
- GitHub for version control

**Monitoring:**
- Cloud Monitoring (aggregate view)
- Cloud Logging (centralized logs)
- Custom dashboards (all clients)

**Automation:**
- Python scripts for orchestration
- Terraform for provisioning
- Django admin for management

---

## Security & Compliance

### Project Isolation

**Guarantees:**
- Each client in separate GCP project
- No shared compute or storage resources
- Separate IAM policies per project
- Independent network configurations

**Client Access:**
- Clients never access GCP console
- All interactions via Django UI only
- API access authenticated with tokens
- No direct database access

**Your Access:**
- Organization-level admin for all projects
- Service accounts for automation
- Audit logging for all actions
- Break-glass procedures for emergencies

### Data Security

**At Rest:**
- All GCP data encrypted by default
- Customer-managed encryption keys (optional for sensitive clients)
- Secrets in Secret Manager (never in code)
- Database backups encrypted

**In Transit:**
- HTTPS/TLS for all communication
- gRPC with TLS for internal services
- VPC peering for private connectivity (if needed)

**Access Control:**
- Principle of least privilege
- Service accounts per service
- Time-limited credentials
- No long-lived keys

### IAM Requirements & Setup

**Region Configuration:**
- Primary Region: `europe-central2` (Warsaw, Poland)
- Matches existing infrastructure location
- Ensures data residency compliance for Ukraine

**Required GCP APIs** (must be enabled):
```bash
# Core ETL Platform APIs
bigquery.googleapis.com              # BigQuery for data warehousing
cloudscheduler.googleapis.com        # Cloud Scheduler for ETL automation
run.googleapis.com                   # Cloud Run for containerized services
cloudbuild.googleapis.com            # Cloud Build for Docker image builds
secretmanager.googleapis.com         # Secret Manager for credentials
sqladmin.googleapis.com              # Cloud SQL for Django/MLflow databases
```

**Service Accounts:**

1. **ETL Runner Service Account**
   - Name: `etl-runner@{project-id}.iam.gserviceaccount.com`
   - Purpose: Executes Cloud Run ETL jobs
   - Required Roles:
     - `roles/bigquery.dataEditor` - Create tables, load data
     - `roles/bigquery.jobUser` - Run BigQuery jobs
     - `roles/secretmanager.secretAccessor` - Read database credentials
     - `roles/run.invoker` - Invoke Cloud Run jobs

2. **Django App Service Account** (App Engine Default)
   - Name: `{project-id}@appspot.gserviceaccount.com`
   - Purpose: Django application backend operations
   - Required Roles:
     - `roles/cloudscheduler.admin` - Create/manage Cloud Scheduler jobs
     - `roles/bigquery.admin` - Manage BigQuery datasets/tables
     - `roles/secretmanager.admin` - Manage connection credentials
     - `roles/run.admin` - Trigger ETL jobs

**User Permissions** (for development/operations):
- Primary User: `kulish.dmytro@gmail.com`
  - `roles/owner` - Full project access (already assigned)
  - `roles/bigquery.admin` - BigQuery operations
  - `roles/cloudscheduler.admin` - Scheduler management

**Setup Commands:**
```bash
# Set project
gcloud config set project b2b-recs

# Enable required APIs
gcloud services enable bigquery.googleapis.com \
  cloudscheduler.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com

# Create ETL Runner service account
gcloud iam service-accounts create etl-runner \
  --display-name="ETL Runner Service Account"

# Grant permissions to ETL Runner
gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:etl-runner@b2b-recs.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:etl-runner@b2b-recs.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:etl-runner@b2b-recs.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:etl-runner@b2b-recs.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Grant permissions to Django App (App Engine default SA)
gcloud projects add-iam-policy-binding b2b-recs \
  --member="serviceAccount:b2b-recs@appspot.gserviceaccount.com" \
  --role="roles/cloudscheduler.admin"

# Setup application default credentials (for local development)
gcloud auth application-default login
```

**Security Best Practices:**
- ✅ No service account keys stored locally
- ✅ All credentials in Secret Manager
- ✅ Least privilege access (scoped to specific services)
- ✅ Service accounts per component (ETL, Django, ML)
- ✅ Regular IAM policy audits
- ⚠️ Never commit credentials to Git
- ⚠️ Rotate service account keys if generated

### Compliance

**Data Residency:**
- Projects can be region-specific
- EU clients → europe-west4
- US clients → us-central1
- Data never leaves specified region

**Audit Trail:**
- Cloud Audit Logs for all GCP actions
- Django logs all user actions
- Immutable log storage
- Retention: 1 year minimum

**GDPR Considerations:**
- Data deletion on request
- Export functionality
- Data processing agreements
- Privacy by design

---

## Cost Management

### Cost Structure Per Client

**Fixed Monthly Costs** (always running):
- Cloud Run (Django app): ~$30-50
- Cloud Run (MLflow): ~$20-30
- Cloud SQL (Django DB): ~$25-40
- Cloud SQL (MLflow DB): ~$25-40
- Cloud NAT + Static IP: ~$40
- Cloud Scheduler (ETL): ~$0.10
- **Total Fixed**: ~$140-200/month

**Variable Costs** (usage-based):
- ETL runs (Cloud Run + Dataflow): ~$5-20 per run
- Training runs (Vertex AI GPUs): ~$10-50 per run
- BigQuery queries: ~$5-50/month depending on data size
- Model serving predictions: ~$0.001-0.01 per 1000 predictions
- GCS storage: ~$1-10/month depending on data volume

**Typical Monthly Total Per Client**:
- Light usage (1-2 trainings): ~$190-240
- Medium usage (4-8 trainings): ~$290-440
- Heavy usage (daily trainings): ~$540-840

### Cost Optimization Strategies

**Immediate Savings:**
- Use preemptible GPUs for training (70% cheaper)
- Right-size Cloud Run instances (don't over-provision)
- Set min-instances=0 for low-traffic services
- Use BigQuery partitioning and clustering
- Archive old models to Nearline/Coldline storage

**Scale Optimizations:**
- Committed use discounts for steady state
- Negotiated pricing with Google at volume
- Shared Artifact Registry across all projects
- Optimized Docker images (smaller = faster)

**Client Controls:**
- Budget alerts per project
- Usage quotas (max trainings per month)
- Approval required for expensive operations
- Cost visibility in Django UI

### Billing Model

**What You Pay Google:**
- Single bill for entire organization
- All client project costs included
- BigQuery billing export for attribution

**What Clients Pay You:**
- TBD based on economics (to be determined after Phase 2)
- Must cover GCP costs + margin
- Options: fixed subscription, usage-based, or hybrid

**Cost Tracking:**
- Daily: Pull billing data to control plane BigQuery
- Attribute costs to each client project via labels
- Django dashboard shows per-client costs
- Monthly invoice generation (manual initially)

---

## Monitoring & Operations

### Health Monitoring

**Per-Client Metrics:**
- Django app uptime
- Pipeline success rate
- Training job failures
- ETL job status
- Model serving latency
- Prediction volume
- Error rates

**Aggregate Metrics:**
- Total active clients
- Total pipeline runs today/week/month
- Average success rate across clients
- Total predictions served
- Average costs per client
- Support ticket volume

**Alerting:**
- Pipeline failures → email/Slack
- Cost anomalies → email
- Service downtime → PagerDuty
- Model performance degradation → client notification

### Operational Runbooks

**Daily Tasks:**
- Review aggregate health dashboard
- Check for failed pipelines (investigate)
- Monitor cost anomalies
- Respond to support tickets

**Weekly Tasks:**
- Review success rates across all clients
- Identify common issues
- Plan bug fixes and improvements
- Update documentation

**Monthly Tasks:**
- Generate billing data
- Review per-client costs and profitability
- Platform health review
- Capacity planning
- Release planning

**Incident Response:**
- Pipeline failure: check logs, rerun if transient
- Service downtime: check Cloud Run logs, scale up if needed
- Data quality issues: validate ETL, check source
- Model performance drop: compare with previous versions
- Cost spike: identify cause, alert client if their usage

---

## Template Versioning & Updates

### Version Strategy

**Semantic Versioning:**
- v1.0.0: Initial production release
- v1.1.0: Minor features, backward compatible
- v1.0.1: Bug fixes, patches
- v2.0.0: Breaking changes (rare)

**What Gets Versioned:**
- Django application code
- ML pipeline component Docker images
- Terraform modules
- Configuration schemas
- Database migrations

### Rolling Out Updates

**Development Process:**
1. Develop in `template-dev` project
2. Test thoroughly
3. Create release candidate: `v1.2.0-rc1`
4. Deploy to 1 test client
5. Monitor for 48 hours
6. If stable, promote to `v1.2.0`

**Deployment Process:**
1. Tag release in Git
2. Build and push Docker images
3. Deploy to 10% of clients (canary)
4. Monitor for 1 week
5. If no issues, deploy to remaining 90%
6. Update control plane to show new version available

**Rollback Process:**
- Keep previous 3 versions available
- One-click rollback per client in control plane
- Automatic rollback on health check failure
- Client can request rollback via support

**Communication:**
- Release notes for each version
- Email notification before major updates
- In-app notification of new features
- Changelog visible in Django UI

---

## Risks & Mitigation

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| GPU quota limits | Training delays | High | Request quota increases proactively, use multiple regions |
| GCP service outage | Client operations halted | Low | Multi-region deployments (future), SLA monitoring |
| Template bug affects many clients | Mass issues | Medium | Staged rollouts, canary deployments, rapid rollback |
| Cost overruns | Profit loss | Medium | Per-client budgets, cost alerts, usage caps |
| Data loss | Client trust broken | Low | Automated backups, versioned storage, disaster recovery plan |
| Security breach | Data exposure | Low | Project isolation, audit logging, security reviews |
| Client project sprawl | Management complexity | High | Automation, monitoring, centralized control plane |

### Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Support burden too high | Can't scale | High | Self-service features, documentation, automated troubleshooting |
| Manual provisioning bottleneck | Slow growth | Medium | Terraform automation priority, self-service signup (future) |
| Client customization requests | Template divergence | High | Strict policies, charge premium for custom work, or decline |
| Debugging across projects | Slow issue resolution | Medium | Centralized logging, cross-project monitoring, good tooling |

### Business Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Underpricing (costs exceed revenue) | Unsustainable | High | Complete cost analysis in Phase 2, conservative pricing |
| Low client retention | Revenue instability | Medium | Focus on UX, proactive support, deliver value |
| Slow client acquisition | Growth stalls | Medium | Marketing, word-of-mouth, free tier/trial (future) |
| Client demands features you can't build | Expectation mismatch | Medium | Clear scope, roadmap transparency, feature voting |

---

## Success Metrics

### Phase 1 Success (Single Working System)
- [ ] End-to-end pipeline completes successfully
- [ ] Django UI deployed and functional
- [ ] MLflow tracking experiments
- [ ] ETL running on schedule
- [ ] Model serving predictions
- [ ] Full cost breakdown documented

### Phase 2 Success (Learn & Document)
- [ ] Complete setup documentation exists
- [ ] Cost per pipeline run known
- [ ] UX pain points identified
- [ ] Requirements refined
- [ ] Ready to replicate to client #2

### Phase 3 Success (Templatize & Automate)
- [ ] Terraform can create new client project in 30 minutes
- [ ] Control plane dashboard operational
- [ ] 3 test projects provisioned successfully
- [ ] Template versioning working
- [ ] Security audit passed

### Phase 4 Success (First Real Client)
- [ ] Client project provisioned
- [ ] Client trained on system
- [ ] First model in production
- [ ] Client satisfied with product
- [ ] Feedback collected and documented

### Phase 5 Success (Scale)
- [ ] 5+ clients operational
- [ ] All clients profitable (revenue > costs)
- [ ] Support burden manageable
- [ ] Template updates rolling out smoothly
- [ ] Product-market fit validated

---

## Open Questions & Future Considerations

### To Be Determined

**Pricing Model:**
- Fixed monthly subscription vs usage-based vs hybrid?
- What's the right markup on GCP costs?
- Free trial or always paid?
- Annual vs monthly contracts?

**Feature Scope:**
- How much feature engineering customization to allow?
- Support for other model types beyond TFRS?
- A/B testing infrastructure needed when?
- Multi-model deployment per client?

**Self-Service:**
- When to allow self-service signup?
- Credit card payments or manual invoicing?
- Trial period automation?

### Future Enhancements (Not in Initial Scope)

**Advanced ML Features:**
- AutoML / hyperparameter tuning automation
- Model architecture search
- Multi-armed bandit for A/B testing
- Real-time model updates

**Data Features:**
- More data source connectors (Snowflake, Redshift)
- Real-time data streaming
- Data quality monitoring
- Feature store

**Platform Features:**
- White-label deployments (client's domain, branding)
- Multi-user access with roles
- API for external integrations
- Jupyter notebook integration
- CLI tool for power users

**Enterprise Features:**
- SSO integration
- VPC peering for private connectivity
- Custom SLAs
- Dedicated support
- On-premise deployment option

---

## Code Organization & Architecture Guidelines

### Problem: Monolithic File Growth

As the platform grows, individual files can become unmanageably large. Without architectural discipline, a single `views.py` can grow to 5,000+ lines, making the codebase:
- Hard to navigate and understand
- Prone to merge conflicts
- Difficult to test in isolation
- Challenging for new developers to onboard

**Example**: The initial `ml_platform/views.py` grew to 4,627 lines mixing ETL, Connections, and core views—an unsustainable pattern.

### Solution: Domain-Driven Sub-Apps

Organize code by **domain** (business capability), not by **layer** (views, models, utils).

#### Directory Structure

```
ml_platform/
├── views.py              # Core views only (dashboard, model pages)
├── models.py             # All Django models (shared across domains)
├── urls.py               # Main router - includes sub-app URLs
│
├── etl/                  # ETL Domain
│   ├── __init__.py
│   ├── urls.py           # ETL routes
│   ├── views.py          # Page rendering (HTML)
│   ├── api.py            # REST endpoints (JSON)
│   ├── webhooks.py       # External callbacks
│   └── services.py       # Complex business logic (if needed)
│
├── connections/          # Connection Management Domain
│   ├── __init__.py
│   ├── urls.py
│   └── api.py
│
├── datasets/             # Dataset Management Domain (planned)
│   ├── __init__.py
│   ├── urls.py
│   ├── views.py
│   └── api.py
│
├── features/             # Feature Engineering Domain (planned)
│   └── ...
│
├── training/             # Training Domain (planned)
│   └── ...
│
├── experiments/          # Experiments Domain (planned)
│   └── ...
│
├── deployment/           # Deployment Domain (planned)
│   └── ...
│
├── serving/              # Model Serving Domain (planned)
│   └── ...
│
└── utils/                # Shared utilities
    ├── connection_manager.py
    ├── bigquery_manager.py
    └── scheduler_manager.py
```

### File Responsibility Guidelines

| File | Purpose | Returns | Max Lines |
|------|---------|---------|-----------|
| `views.py` | Page rendering, template context | `render()` HTML | 500 |
| `api.py` | REST endpoints, CRUD operations | `JsonResponse` | 1000 |
| `webhooks.py` | External service callbacks | `JsonResponse` | 200 |
| `services.py` | Complex business logic | Python objects | 500 |
| `urls.py` | Route definitions | URL patterns | 150 |

### When to Create a New Sub-App

Create a new sub-app when the domain:
1. Has **5+ related API endpoints**
2. Has its own **page views**
3. Has **distinct business logic**
4. Could theoretically be a **separate microservice**
5. Will be **developed independently** from other domains

### Sub-App Creation Checklist

```bash
# 1. Create sub-app directory
mkdir -p ml_platform/{domain}
touch ml_platform/{domain}/__init__.py

# 2. Create required files
touch ml_platform/{domain}/urls.py
touch ml_platform/{domain}/api.py

# 3. Optional files (if needed)
touch ml_platform/{domain}/views.py      # If page views exist
touch ml_platform/{domain}/webhooks.py   # If external callbacks exist
touch ml_platform/{domain}/services.py   # If complex business logic exists
```

### URL Configuration Pattern

**Main urls.py (ml_platform/urls.py):**
```python
from django.urls import path, include
from . import views

urlpatterns = [
    # Include sub-app URLs
    path('', include('ml_platform.etl.urls')),
    path('', include('ml_platform.connections.urls')),
    path('', include('ml_platform.datasets.urls')),

    # Core routes (not part of any sub-app)
    path('', views.system_dashboard, name='system_dashboard'),
    path('models/<int:model_id>/', views.model_dashboard, name='model_dashboard'),
]
```

**Sub-app urls.py (ml_platform/etl/urls.py):**
```python
from django.urls import path
from . import views, api, webhooks

urlpatterns = [
    # Page views
    path('models/<int:model_id>/etl/', views.model_etl, name='model_etl'),

    # API endpoints
    path('api/models/<int:model_id>/etl/add-source/', api.add_source, name='api_etl_add_source'),
    path('api/etl/sources/<int:source_id>/', api.get_source, name='api_etl_get_source'),

    # Webhooks
    path('api/etl/sources/<int:data_source_id>/scheduler-webhook/',
         webhooks.scheduler_webhook, name='api_etl_scheduler_webhook'),
]
```

### Import Conventions

```python
# In sub-app files: Always use ABSOLUTE imports
from ml_platform.models import DataSource, ETLRun
from ml_platform.utils.connection_manager import test_connection

# In urls.py: Use RELATIVE imports for same sub-app
from . import views, api, webhooks
```

### Naming Conventions

**URL Names:**
```python
# Pattern: api_{domain}_{action}
name='api_etl_add_source'
name='api_etl_get_source'
name='api_connection_create'
name='api_connection_test'
```

**Function Names (in api.py):**
```python
# Short names - context provided by module
def add_source(request, model_id): ...    # etl/api.py
def get_source(request, source_id): ...   # etl/api.py
def create(request, model_id): ...        # connections/api.py
def test(request, connection_id): ...     # connections/api.py
```

### API Response Standards

```python
# Success response
return JsonResponse({
    'status': 'success',
    'message': 'Human-readable message',
    'data': {...}  # Optional payload
})

# Error response
return JsonResponse({
    'status': 'error',
    'message': 'Human-readable error description'
}, status=400)  # or 404, 500
```

### File Size Triggers

When files exceed these thresholds, consider splitting:

| File | Warning | Action Required |
|------|---------|-----------------|
| views.py | 300 lines | 500 lines → split by page group |
| api.py | 500 lines | 1000 lines → split by resource type |
| services.py | 300 lines | 500 lines → extract to utils/ |
| Single function | 100 lines | 150 lines → extract helper functions |

### Testing Structure

```
ml_platform/tests/
├── test_etl_baseline.py      # ETL domain tests
├── test_connections.py       # Connection domain tests
├── test_datasets.py          # Dataset domain tests
├── conftest.py               # Shared fixtures
└── factories.py              # Test data factories
```

### Migration Procedure

When moving code from a monolithic file to a sub-app:

1. **Create sub-app structure** (directories, __init__.py)
2. **Copy functions** to appropriate files (views.py, api.py, webhooks.py)
3. **Fix imports** (change relative to absolute)
4. **Rename functions** (remove redundant prefixes)
5. **Create urls.py** with all routes
6. **Update main urls.py** to include sub-app
7. **Remove original code** from monolithic file
8. **Run `python manage.py check`**
9. **Run tests** to verify functionality
10. **Document** the migration

### Reference Implementation

See `docs/architecture_refactoring.md` for the complete case study of migrating:
- ETL code from views.py → ml_platform/etl/
- Connection code from views.py → ml_platform/connections/

Results: 91.6% reduction in views.py (4,627 → 389 lines)

---

## Appendix: Reference Architecture from Past Project

### Existing Working Components

From `past/` folder, these components are production-tested and will be reused:

**1. Data Extractor** (`past/recs/data_extractor/`)
- Extracts 90-day transaction data from BigQuery
- Includes product metadata
- Filters top 80% revenue products
- Outputs TFRecord files
- Uses Apache Beam with DataflowRunner

**2. Vocab Builder** (`past/recs/vocab_builder/`)
- Processes TFRecords to extract vocabularies
- Creates mappings for 8 features
- Generates revenue and timestamp buckets
- Outputs vocabularies.json

**3. Trainer** (`past/recs/trainer/`)
- Two-tower retrieval model
- Multi-GPU training support
- Early stopping and adaptive learning rate
- Achieves 45-47% Recall@100
- Outputs saved_model, query_model, candidate_model

**4. Cloud Run Service** (`past/recs/cloud_run_service/`)
- FastAPI-based prediction API
- Batch processing support
- ~2ms per customer inference
- Health checks and monitoring

**5. Airflow DAG** (`past/dags/metro_recommender_production_v2.py`)
- Orchestrates all 4 components
- GPU fallback logic
- Error handling and validation
- Monthly scheduling

### Modifications Needed for SaaS

**Parameterization:**
- All hardcoded paths → environment variables
- Project ID, region, bucket names configurable
- City lists, date ranges, product filters configurable

**Multi-Tenant Support:**
- Add tenant_id to all operations
- Isolated data paths per tenant
- Separate credentials per tenant

**Django Integration:**
- Replace Airflow orchestration with Celery
- Add MLflow logging to trainer
- API endpoints for Django to trigger jobs
- Status polling for UI updates

**Cost Optimization:**
- Configurable machine types
- Optional preemptible GPU usage
- Idle resource cleanup
- Right-sizing based on dataset

---

## Document Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-11-09 | 1.0 | Initial document based on architecture discussions | - |
| 2025-11-17 | 1.1 | Added Network Architecture section (Cloud NAT + Static IPs), updated cost structure | Claude Code |
| 2025-11-30 | 1.2 | Added Code Organization & Architecture Guidelines section based on views.py refactoring | Claude Code |

---

## Next Steps

1. **Review this document** - Ensure alignment on approach
2. **Set up GCP Organization** - Create folder structure
3. **Create template-dev project** - First manual client project
4. **Start Phase 1, Week 1** - Begin Django foundation work

---

*This is a living document. Update as decisions are made and approach evolves.*
