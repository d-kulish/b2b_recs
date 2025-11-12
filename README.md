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
- **Per-Table ETL Jobs**: Each data source extracts exactly one table with independent scheduling
- **4-Step Wizard Modal**: Guided job creation (Connection → Table → Sync → Schedule)
- **Full CRUD Operations**: Add, edit, delete ETL jobs with complete configuration
- **Multiple Data Source Types**: PostgreSQL, MySQL, SQL Server, BigQuery, CSV, Parquet
- **Connection Testing**: Validate database connections before saving
- **Sync Modes**: Full Refresh (replace), Append, Incremental (timestamp-based)
- **Per-Job Run Trigger**: "Run Now" button on each individual job
- **Schedule Configuration**: Manual, hourly, daily, weekly, monthly options
- **ETL Run History**: View past executions with detailed results and row counts

**API Endpoints**:
- `POST /api/models/{id}/etl/add-source/` - Create new data source/job
- `GET /api/etl/sources/{id}/` - Get source details for editing
- `POST /api/etl/sources/{id}/update/` - Update existing data source
- `POST /api/etl/sources/{id}/test/` - Test database connection
- `POST /api/etl/sources/{id}/run/` - Run ETL for single source
- `POST /api/etl/sources/{id}/delete/` - Delete data source
- `POST /api/models/{id}/etl/toggle/` - Enable/disable ETL scheduling
- `POST /api/models/{id}/etl/run/` - Trigger full ETL run (all sources)
- `GET /api/etl/runs/{id}/status/` - Poll ETL run status

**Database Models**:
- **ETLConfiguration**: Schedule settings and Cloud Run service configuration
- **DataSource**: Individual source connections (one table per source)
- **DataSourceTable**: Table-level extraction config (sync mode, incremental column, row limits)
- **ETLRun**: Execution history with per-source and per-table success tracking

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

1. **Per-Table Job Architecture**: One DataSource = One Table = One Independent Schedule
   - Maximum flexibility for different update frequencies per table
   - Granular control over sync modes and incremental logic
   - Independent failure handling (one table failure doesn't block others)
2. **Configuration-Driven**: All extraction logic driven by Django database configuration
3. **Wizard-Based UX**: 4-step guided process for non-technical users
4. **No Airflow**: Uses Cloud Run + Cloud Scheduler for simplicity and cost ($10-20/month vs $120/month)
5. **Per-Client Isolation**: Each client gets their own Cloud Scheduler + Cloud Run deployment
6. **Same Container Image**: One Docker image deployed to all clients with different env vars

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
- Custom Button CSS System (see below)

**Future:**
- Vue.js for reactive components
- Celery for async tasks
- Redis for caching
- Google Cloud Platform services

## UI Components - Button Styling System

A unified button styling system has been implemented for consistent UI across all pages.

### Button CSS File
**Location**: `static/css/buttons.css`

All buttons follow a standardized design:
- **White background** with thin black border (1px)
- **Light green hover effect** (`#f0fdf4`)
- Subtle shadow for depth
- Proper icon spacing (10px gap)
- Short and wide proportions for better visibility

### Base Button Classes

**Primary button** (main actions):
```html
<button class="btn btn-primary">
    <i class="fas fa-plus"></i><span>Add Item</span>
</button>
```

**Button variants**:
- `.btn-success` - Light green (create, confirm actions)
- `.btn-danger` - Light red (delete, remove actions)
- `.btn-secondary` - Neutral (less emphasis)
- `.btn-warning` - Light yellow (caution actions)

**Size modifiers**:
- `.btn-sm` - Small buttons
- `.btn-lg` - Large buttons
- `.btn-wide` - Extra wide buttons (200px min-width)
- `.btn-block` - Full width

### Usage Guidelines

1. **Always wrap text in `<span>` tags** when using icons for proper spacing
2. **Use consistent color coding**: success (green), danger (red), primary (neutral)
3. **Icons are optional** but provide good visual cues
4. **Disabled state** is handled automatically via CSS `:disabled` pseudo-class

### Examples

**With icon:**
```html
<button class="btn btn-success">
    <i class="fas fa-check"></i><span>Save</span>
</button>
```

**Text only:**
```html
<button class="btn btn-primary">
    <span>Test Connection</span>
</button>
```

**Wide button:**
```html
<button class="btn btn-primary btn-wide">
    <i class="fas fa-plus"></i><span>ETL Job</span>
</button>
```

### Connection Test Containers

Connection test sections use dynamic background colors:
- **White** (default) - Before testing
- **Light green** (`bg-green-50`) - Success
- **Light red** (`bg-red-50`) - Failure

The "Next" navigation button remains disabled until connection test succeeds.

## Contributing

This is an internal project. See `implementation.md` for the complete roadmap and implementation phases.

## License

Proprietary - All rights reserved
