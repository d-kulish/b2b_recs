# B2B Recommendation System - SaaS Platform

A multi-tenant B2B SaaS platform for building, training, and deploying production-grade recommendation models.

## 📊 Project Stats

- **10** Database Models
- **30+** Files Created
- **10** HTML Templates (with responsive UI)
- **13** View Functions
- **11** URL Patterns
- **100%** Authentication Coverage
- **Status**: Frontend Skeleton Complete ✅

## Project Status

**Current Phase**: Django Frontend Skeleton ✅ **COMPLETE**

**Date Completed**: November 11, 2025

This is the initial backbone of the client-facing web application. All foundational components are implemented and functional.

### ✅ Completed Components

**Backend:**
- ✅ Django project structure with proper settings
- ✅ 10 database models (ModelEndpoint, ETL, Pipeline, Experiments, Deployments, etc.)
- ✅ Complete URL routing structure (system + model-level pages)
- ✅ Functional views with authentication and authorization
- ✅ API endpoints for AJAX operations (training, ETL, deployment)
- ✅ Admin interface for all models (searchable, filterable)
- ✅ Database migrations created and applied

**Frontend:**
- ✅ Responsive UI using Tailwind CSS
- ✅ Base templates with navigation (system + model-specific)
- ✅ System Dashboard (landing page with stats and models list)
- ✅ Model/Endpoint creation flow
- ✅ Model Dashboard (status cards, recent runs, quick actions)
- ✅ Login/logout functionality
- ✅ Template placeholders for all 8 model-level pages

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

### ETLConfiguration & ETLRun
ETL configuration and execution history for data extraction from source systems.

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

## 🎯 Next Steps - Chapter-by-Chapter Implementation

The skeleton is complete! Now we can implement each feature "chapter-by-chapter":

### Priority 1 - Core ML Pipeline (Weeks 3-5)
1. **ETL Page** - BigQuery integration, data source connectors, schedule configuration
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
10. **Production Ready** - Dockerfile, CI/CD, monitoring, testing

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
