# B2B Recommendation System - SaaS Platform

A multi-tenant B2B SaaS platform for building, training, and deploying production-grade recommendation models.

## 📊 Project Stats

- **13** Database Models (including ETL models)
- **40+** Files Created
- **11** HTML Templates (with responsive UI)
- **20** View Functions (including ETL APIs)
- **17** URL Patterns
- **100%** Authentication Coverage
- **Status**: Frontend Skeleton + ETL Implementation ✅

## Project Status

**Current Phase**: ETL Implementation ✅ **COMPLETE**

**Date Completed**: November 11, 2025

The client-facing web application backbone is complete with fully functional ETL configuration and management system.

### ✅ Completed Components

**Backend:**
- ✅ Django project structure with proper settings
- ✅ 13 database models (ModelEndpoint, ETL, DataSource, DataSourceTable, Pipeline, Experiments, etc.)
- ✅ Complete URL routing structure (system + model-level pages)
- ✅ Functional views with authentication and authorization
- ✅ API endpoints for AJAX operations (training, ETL, deployment)
- ✅ Admin interface for all models (searchable, filterable)
- ✅ Database migrations created and applied
- ✅ **ETL System**: Multi-source configuration, connection testing, manual triggers

**Frontend:**
- ✅ Responsive UI using Tailwind CSS
- ✅ Base templates with navigation (system + model-specific)
- ✅ System Dashboard (landing page with stats and models list)
- ✅ Model/Endpoint creation flow
- ✅ Model Dashboard (status cards, recent runs, quick actions)
- ✅ Login/logout functionality
- ✅ **ETL Page**: Full-featured UI for data source management and monitoring

**Developer Experience:**
- ✅ User creation script (`create_user.py`)
- ✅ Comprehensive README documentation
- ✅ `.gitignore` configured for Django projects
- ✅ Requirements file with all dependencies

### Pages Structure

**System-Level:**
- System Dashboard - View all models/endpoints and summary stats
- Create Model/Endpoint - Initialize new recommendation systems

**Model-Level (per Model/Endpoint):**
- Dashboard - Model health, recent runs, performance
- Training Interface - Launch training jobs, view status
- Experiments Dashboard - View MLflow results, compare models
- Deployment Manager - Deploy models, manage versions
- Pipeline Configuration - Configure ML pipeline parameters
- Dataset Manager - Browse BigQuery data
- ETL - Configure data extraction
- Feature Engineering - Visual designer (placeholder)

## Quick Start

### 1. Clone and set up virtual environment

```bash
git clone <your-repo-url>
cd b2b_recs
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run migrations

```bash
python manage.py migrate
```

### 3. Create a superuser (Option A - Automated)

```bash
python create_user.py
```

This creates a user with:
- Username: `dkulish`
- Password: `admin123`

**Or Option B - Manual:**

```bash
python manage.py createsuperuser
# Follow the prompts to create your own user
```

### 4. Run the development server

```bash
python manage.py runserver
```

### 5. Access the application

- **Web App**: http://127.0.0.1:8000/
- **Admin Panel**: http://127.0.0.1:8000/admin/

### 6. Login and create your first model

1. Log in with your credentials
2. Click "Create Model/Endpoint" on the System Dashboard
3. Fill in the name and description
4. Explore the model-specific pages (Dashboard, Training, ETL, etc.)

## Project Structure

```
b2b_recs/
├── config/                 # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── ml_platform/           # Main application
│   ├── models.py         # Database models
│   ├── views.py          # View functions
│   ├── urls.py           # URL routing
│   └── admin.py          # Admin configuration
├── templates/            # HTML templates
│   ├── base.html         # Base template with navigation
│   ├── base_model.html   # Model-specific base
│   ├── login.html        # Login page
│   └── ml_platform/      # App-specific templates
├── static/               # Static files (CSS, JS)
├── manage.py             # Django management script
└── requirements.txt      # Python dependencies
```

## Database Models

### ModelEndpoint
Represents a complete ML project/pipeline instance. Each ModelEndpoint is a separate recommendation system.

### ETL Models (Configuration-Driven Architecture)

**ETLConfiguration** - Parent configuration for scheduling and settings
- Schedule type (manual, daily, weekly, monthly)
- Cron expression for Cloud Scheduler
- Last run status and timestamps
- Cloud Run service URL reference

**DataSource** - Individual data source connections (supports multiple per client)
- Supported types: PostgreSQL, MySQL, SQL Server, BigQuery, CSV, Parquet
- Connection details (host, port, database, credentials)
- Connection testing status
- Enable/disable per source

**DataSourceTable** - Table-level extraction configuration
- Source → destination table mapping
- Sync modes: replace (full refresh), append, incremental (date-based)
- Row limits for testing
- Per-table enable/disable

**ETLRun** - Execution history with detailed results
- Tracks all sources and tables in a single run
- Per-source and per-table success/failure
- Total rows extracted
- JSON detailed results structure

### PipelineConfiguration & PipelineRun
ML pipeline parameters and execution tracking (4-stage pipeline: extraction → vocab → training → deployment).

### Experiment
MLflow experiment tracking with metrics and parameters.

### TrainedModel
Individual trained model versions with performance metrics.

### Deployment
Deployment history and active deployments to Cloud Run.

### PredictionLog & SystemMetrics
Aggregated prediction statistics and system-wide metrics.

## 🔄 ETL Implementation

### Architecture: Configuration-Driven Multi-Source ETL

The ETL system uses a **single Docker container template** deployed per client with configuration stored in Django.

```
┌─────────────────────────────────────────┐
│  Django (Client-facing UI)              │
│  - Configure data sources (PostgreSQL,  │
│    MySQL, BigQuery, CSV, Parquet)       │
│  - Set schedules                         │
│  - Test connections                      │
│  - Monitor runs                          │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  Cloud Scheduler (per client)            │
│  - Triggers on schedule (daily 2am, etc.)│
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  Cloud Run Job (ETL Container)           │
│  1. Fetch configuration from Django API │
│  2. For each enabled data source:       │
│     - Connect (PostgreSQL/MySQL/etc.)   │
│     - Extract configured tables         │
│     - Load to BigQuery                  │
│  3. Report results back to Django       │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│  BigQuery (Client's GCP Project)         │
│  Dataset: raw_data                       │
│    - transactions (from PostgreSQL)     │
│    - products (from MySQL)              │
│    - customers (from CSV upload)        │
└─────────────────────────────────────────┘
```

### ✅ Implemented Features

**Django Web UI** (`/models/{id}/etl/`):
- ETL status dashboard with metrics cards
- Add/edit/delete data sources
- Configure multiple sources per model (PostgreSQL, MySQL, BigQuery, CSV, Parquet)
- Test database connections
- Configure table-level sync settings
- Manual "Run ETL Now" trigger
- Enable/disable scheduled runs
- View ETL run history with detailed results

**API Endpoints**:
- `POST /api/models/{id}/etl/add-source/` - Create new data source
- `POST /api/etl/sources/{id}/test/` - Test connection
- `POST /api/etl/sources/{id}/delete/` - Remove data source
- `POST /api/models/{id}/etl/toggle/` - Enable/disable scheduling
- `POST /api/models/{id}/etl/run/` - Trigger manual ETL run
- `GET /api/etl/runs/{id}/status/` - Poll run status

**Database Models**:
- Full schema for multi-source ETL configuration
- Execution tracking with per-table granularity
- Connection testing state

### 🔨 Pending Components (For Production Deployment)

**ETL Container** (Not yet built - needed for actual data extraction):
- `etl_runner.py` - Python script with database connectors
- Database drivers: psycopg2 (PostgreSQL), PyMySQL (MySQL), pyodbc (SQL Server)
- BigQuery loading via `pandas-gbq`
- Reads Django configuration via REST API
- Dockerfile for Cloud Run deployment

**When Needed**:
- First client goes to production
- Actual database connections required
- For now, Django simulates ETL runs for testing

### Key Design Decisions

1. **Configuration-Driven**: All extraction logic driven by Django database configuration
2. **Multi-Source Support**: Single ETL run processes all configured data sources
3. **No Airflow**: Uses Cloud Run + Cloud Scheduler for simplicity and cost ($10-20/month vs $120/month)
4. **Per-Client Isolation**: Each client gets their own Cloud Scheduler + Cloud Run deployment
5. **Same Container Image**: One Docker image deployed to all clients with different env vars

## 🎯 Next Steps - Chapter-by-Chapter Implementation

ETL implementation is complete! Next features to build:

### Priority 1 - Core ML Pipeline (Weeks 3-5)
1. ✅ **ETL Page** - ✅ COMPLETE (Django UI, APIs, multi-source configuration)
2. **Training Interface** - Celery + Vertex AI integration, real-time status updates
3. **Pipeline Configuration** - Complete form validation, parameter presets
4. **Deployment Manager** - Cloud Run API integration, one-click deployment

### Priority 2 - Monitoring & Analytics (Week 5-6)
5. **MLflow Integration** - Connect to MLflow server, display experiments, model comparison
6. **Model Dashboard** - Real-time metrics, health checks, prediction volume
7. **Dataset Manager** - BigQuery table browser, data preview, quality checks

### Priority 3 - Advanced Features (Week 6+)
8. **Feature Engineering** - Visual designer for feature creation
9. **Control Plane** - Separate app for cross-customer management, billing dashboard
10. **Production Ready** - ETL Container + Dockerfile, CI/CD, monitoring, testing

### Quick Wins (Can be done anytime)
- Add pagination to tables
- Add search/filter to System Dashboard
- Add model status transitions (draft → active)
- Add confirmation modals for destructive actions
- Add loading indicators for AJAX calls

## Architecture Overview

See `implementation.md` for the complete architecture and implementation plan.

### Key Architecture Decisions
- Separate GCP project per client (complete isolation)
- Django for client-facing UI (no-code interface)
- Cloud Run for all services (Django, MLflow, ETL, model serving)
- Vertex AI for GPU training jobs
- BigQuery for data warehouse
- MLflow for experiment tracking

## Development

### Working Across Multiple Machines

The SQLite database (`db.sqlite3`) is **not synced** via Git (it's in `.gitignore`). This is intentional to avoid conflicts.

**On a new machine:**
```bash
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate       # Creates empty database
python create_user.py          # Creates user (same credentials)
python manage.py runserver
```

Your user account will be recreated, but any test data (models you created) won't transfer. This is normal for development.

**If you need to sync specific data between machines:**
```bash
# On Machine A (export data)
python manage.py dumpdata auth.User --indent 2 > fixtures/users.json

# Commit and push
git add fixtures/
git commit -m "Add user fixtures"
git push

# On Machine B (import data)
git pull
python manage.py loaddata fixtures/users.json
```

### Adding a new page

1. Create view in `ml_platform/views.py`
2. Add URL pattern in `ml_platform/urls.py`
3. Create template in `templates/ml_platform/`

### Updating models

```bash
python manage.py makemigrations
python manage.py migrate
```

### Accessing the admin interface

Navigate to http://127.0.0.1:8000/admin/ and log in with your superuser credentials.

### Change your password

```bash
python manage.py changepassword dkulish
# Or just run: python create_user.py (updates existing user)
```

## Technology Stack

**Backend:**
- Django 5.2
- SQLite (development) / PostgreSQL (production)

**Frontend:**
- Tailwind CSS (via CDN)
- Font Awesome icons
- Vanilla JavaScript (for now)

**Future:**
- Vue.js for reactive components
- Celery for async tasks
- Redis for caching
- Google Cloud Platform services

## Contributing

This is an internal project. See `implementation.md` for the complete roadmap and implementation phases.

## License

Proprietary - All rights reserved
