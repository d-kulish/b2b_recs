# Architecture Refactoring: views.py to Sub-Apps

## Problem Statement

### The Growing Monolith
The `ml_platform/views.py` file had grown to **4,627 lines** containing 84+ routes, mixing:
- Page views (HTML rendering)
- API endpoints (JSON responses)
- Webhook handlers (external callbacks)
- Business logic for multiple domains (ETL, Connections, Training, etc.)

### Why This Was Unsustainable

1. **Cognitive Overload**: Finding and modifying code required scrolling through thousands of lines
2. **Merge Conflicts**: Multiple developers working on different features would constantly conflict
3. **Testing Difficulty**: No clear boundaries made unit testing specific functionality hard
4. **Code Duplication**: Similar patterns repeated across unrelated sections
5. **Future Growth**: With 6 more major features planned (Datasets, Feature Engineering, Training, Experiments, Deployment, Model Serving), the file would have exceeded 10,000+ lines

### The Breaking Point
The platform needed to scale from 2 domains (ETL + Connections) to 8 domains. Without restructuring, each new feature would:
- Add 500-1000+ lines to views.py
- Increase complexity exponentially
- Make onboarding new developers nearly impossible

---

## Solution: Domain-Driven Sub-Apps Architecture

### Design Principles

1. **Single Responsibility**: Each sub-app owns one domain
2. **Separation of Concerns**: Views, APIs, and webhooks are separated within each sub-app
3. **Consistent Structure**: All sub-apps follow the same file organization
4. **Loose Coupling**: Sub-apps communicate through models, not direct imports
5. **URL Namespace Isolation**: Each sub-app manages its own routes

### New Directory Structure

```
ml_platform/
├── views.py              # 389 lines - Core views only
├── models.py             # Shared data models
├── urls.py               # Main router (includes sub-apps)
│
├── etl/                  # ETL Domain Sub-App
│   ├── __init__.py
│   ├── urls.py           # 27 routes
│   ├── views.py          # Page views (HTML)
│   ├── api.py            # API endpoints (JSON)
│   └── webhooks.py       # External callbacks
│
├── connections/          # Connection Management Sub-App
│   ├── __init__.py
│   ├── urls.py           # 17 routes
│   └── api.py            # API endpoints
│
└── tests/                # Test organization
    └── test_etl_baseline.py
```

### File Responsibilities

| File | Purpose | Returns |
|------|---------|---------|
| `views.py` | Page rendering, template context | `render()` HTML |
| `api.py` | REST endpoints, CRUD operations | `JsonResponse` |
| `webhooks.py` | External service callbacks (schedulers, etc.) | `JsonResponse` |
| `urls.py` | Route definitions for the sub-app | URL patterns |

---

## Changes Applied

### 1. Created Sub-App Structure

```bash
ml_platform/
├── etl/
│   ├── __init__.py
│   ├── urls.py
│   ├── views.py
│   ├── api.py
│   └── webhooks.py
└── connections/
    ├── __init__.py
    ├── urls.py
    └── api.py
```

### 2. Migrated Code

| Source | Destination | Lines |
|--------|-------------|-------|
| views.py ETL page view | etl/views.py | 277 |
| views.py ETL APIs | etl/api.py | 2,472 |
| views.py scheduler webhook | etl/webhooks.py | 101 |
| views.py connection APIs | connections/api.py | 1,551 |

### 3. Updated URL Configuration

**Main urls.py:**
```python
from django.urls import path, include

urlpatterns = [
    path('', include('ml_platform.etl.urls')),
    path('', include('ml_platform.connections.urls')),
    # ... core routes
]
```

**Sub-app urls.py (example: etl/urls.py):**
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

### 4. Fixed Import Paths

All migrated code updated from relative to absolute imports:
```python
# Before (in views.py)
from .utils.connection_manager import get_credentials_from_secret_manager
from .models import DataSource

# After (in sub-app)
from ml_platform.utils.connection_manager import get_credentials_from_secret_manager
from ml_platform.models import DataSource
```

### 5. Renamed Functions

Removed redundant prefixes since context is now provided by module:
```python
# Before
def api_etl_add_source(request, model_id): ...
def api_connection_create(request, model_id): ...

# After
def add_source(request, model_id): ...  # in etl/api.py
def create(request, model_id): ...      # in connections/api.py
```

---

## Results

### Line Count Comparison

| File | Before | After | Change |
|------|--------|-------|--------|
| ml_platform/views.py | 4,627 | 389 | -91.6% |
| ml_platform/etl/api.py | - | 2,472 | New |
| ml_platform/etl/views.py | - | 277 | New |
| ml_platform/etl/webhooks.py | - | 101 | New |
| ml_platform/connections/api.py | - | 1,551 | New |

### Test Results

```
Ran 26 tests in 26.059s
OK
```

All baseline tests pass:
- ETL page views (5 tests)
- ETL API endpoints (9 tests)
- ETL URL resolution (3 tests)
- Connection API (5 tests)
- ETL Run model (3 tests)

### URL Verification

- Total URL patterns: **159**
- ETL routes: **27**
- Connection routes: **17**
- Core routes: **13** (in main views.py)

---

## Guidelines for Future Sub-Apps

### When to Create a New Sub-App

Create a new sub-app when:
1. The domain has 5+ related API endpoints
2. The domain has its own page views
3. The domain has distinct business logic
4. The domain could theoretically be a separate service

### Sub-App Template

```
ml_platform/{domain}/
├── __init__.py           # Empty or exports
├── urls.py               # All routes for this domain
├── views.py              # Page views (if any)
├── api.py                # REST API endpoints
├── webhooks.py           # External callbacks (if any)
└── services.py           # Complex business logic (if needed)
```

### File Size Guidelines

| File Type | Target Lines | Max Lines | Action if Exceeded |
|-----------|--------------|-----------|-------------------|
| views.py | <300 | 500 | Split by page group |
| api.py | <500 | 1000 | Split by resource type |
| services.py | <300 | 500 | Extract to utils/ |
| urls.py | <100 | 150 | N/A (rarely grows) |

### Naming Conventions

```python
# urls.py - Use descriptive names with domain prefix
name='api_etl_add_source'
name='api_connection_create'

# api.py - Short function names (context from module)
def add_source(request, model_id): ...
def get_source(request, source_id): ...
def update_source(request, source_id): ...
def delete_source(request, source_id): ...

# views.py - Page-oriented names
def model_etl(request, model_id): ...
def model_dataset(request, model_id): ...
```

### Import Patterns

```python
# In sub-app files, always use absolute imports
from ml_platform.models import DataSource, ETLRun
from ml_platform.utils.connection_manager import test_connection

# In urls.py, use relative imports for same sub-app
from . import views, api, webhooks
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

---

## Planned Sub-Apps

| Domain | Sub-App | Status | Est. Routes |
|--------|---------|--------|-------------|
| ETL | ml_platform/etl/ | Complete | 27 |
| Connections | ml_platform/connections/ | Complete | 17 |
| Datasets | ml_platform/datasets/ | Planned | ~15 |
| Features | ml_platform/features/ | Planned | ~20 |
| Training | ml_platform/training/ | Planned | ~25 |
| Experiments | ml_platform/experiments/ | Planned | ~15 |
| Deployment | ml_platform/deployment/ | Planned | ~20 |
| Serving | ml_platform/serving/ | Planned | ~15 |

---

## Migration Checklist for New Sub-Apps

- [ ] Create sub-app directory with `__init__.py`
- [ ] Create `urls.py` with route definitions
- [ ] Create `api.py` with API endpoints
- [ ] Create `views.py` if page views needed
- [ ] Create `webhooks.py` if external callbacks needed
- [ ] Update main `urls.py` to include sub-app
- [ ] Update imports to use absolute paths
- [ ] Remove migrated code from old location
- [ ] Run `python manage.py check`
- [ ] Run tests to verify functionality
- [ ] Update documentation
