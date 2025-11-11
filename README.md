# B2B Recommendation System - SaaS Platform

A multi-tenant B2B SaaS platform for building, training, and deploying production-grade recommendation models.

## Project Status

**Current Phase**: Django Frontend Skeleton ✅

This is the initial backbone of the client-facing web application. The following components are implemented:

### Completed
- ✅ Django project structure
- ✅ Database models (ModelEndpoint, ETL, Pipeline, Experiments, Deployments)
- ✅ URL routing for all pages
- ✅ Basic views for all functionality
- ✅ System Dashboard (landing page)
- ✅ Model/Endpoint creation flow
- ✅ Model-specific navigation and layout
- ✅ Admin interface for all models

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

### 1. Set up virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run migrations

```bash
python manage.py migrate
```

### 3. Create a superuser

```bash
python manage.py createsuperuser
```

### 4. Run the development server

```bash
python manage.py runserver
```

### 5. Access the application

- Web App: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

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

## Next Steps

The following features need to be implemented:

1. **ETL Integration** - Connect to BigQuery, implement data extraction
2. **Pipeline Orchestration** - Celery tasks for Vertex AI jobs
3. **MLflow Integration** - Connect to MLflow server, display experiments
4. **Deployment Automation** - Cloud Run deployment integration
5. **Real-time Status Updates** - WebSocket or polling for job status
6. **Monitoring Dashboard** - Cost tracking, prediction volume, performance metrics
7. **Feature Engineering UI** - Visual designer for creating features
8. **API Authentication** - Token-based auth for API endpoints
9. **Testing** - Unit tests, integration tests
10. **Production Deployment** - Dockerfile, Cloud Run configuration

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
