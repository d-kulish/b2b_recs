# Cross-Tab Project Data Leakage Bug

## Problem

Opening different ML Platform projects (ModelEndpoint) in separate browser tabs caused **data leakage between tabs** — one tab would show another tab's training runs, experiments, endpoints, and other project-specific data.

### Root Cause

All 74 API endpoints in the Training and Experiments domains resolve the "current project" from a single Django session value:

```python
def _get_model_endpoint(request):
    endpoint_id = request.session.get('model_endpoint_id')
    ...
```

Django sessions are shared across all tabs in the same browser. When a user navigates to Project B in Tab 2, the session value `model_endpoint_id` is overwritten — and Tab 1 (Project A) now silently fetches Project B's data on every subsequent API call.

### Additional Discovery

Only one of the four page views (`model_experiments`) actually set the session value. The other three views (`model_dashboard`, `model_training`, `model_deployment`) never wrote to the session at all, meaning the session value was stale and could point to whichever project was last visited via the Experiments page.

### Scope of Impact

- **74 API endpoints** across `ml_platform/training/api.py` and `ml_platform/experiments/api.py` use `_get_model_endpoint(request)` to determine the current project
- **99 frontend `fetch()` calls** across 12 JS modules and 4 HTML templates relied on the session for project scoping
- All four page views affected: Dashboard, Training, Experiments, Deployment

---

## Analysis

### Affected Backend Files
- `ml_platform/training/api.py` — `_get_model_endpoint()` helper used by ~40 training API endpoints
- `ml_platform/experiments/api.py` — `_get_model_endpoint()` helper used by ~34 experiment API endpoints
- `ml_platform/views.py` — Page views that should set session but 3 of 4 didn't

### Affected Frontend JS Modules (12 files)

| Module | fetch() calls | Had modelId? |
|--------|:---:|:---:|
| `training_cards.js` | 15 | Yes (via configure) |
| `exp_view_modal.js` | 27 | No |
| `training_wizard.js` | 8 | Yes (via configure) |
| `endpoints_table.js` | 6 | No |
| `schedule_modal.js` | 5 | No |
| `models_registry.js` | 4 | No |
| `deploy_wizard.js` | 3 | No |
| `integrate_modal.js` | 3 | No |
| `model_dashboard_experiments.js` | 3 | No |
| `model_dashboard_models.js` | 1 | No |
| `schedule_calendar.js` | 1 | No |
| `pipeline_dag.js` | 1 | No |

### Affected HTML Templates (4 files)

| Template | Inline fetch() calls |
|----------|:---:|
| `model_experiments.html` | 20 |
| `model_training.html` | 2 |
| `model_dashboard.html` | 0 (all in external JS) |
| `model_deployment.html` | 0 (all in external JS) |

### Modules Confirmed Correct (no changes needed)
- `model_dashboard_endpoints.js` — already received modelId via init()
- `model_dashboard_etl.js` — extracts modelId from URL path
- `model_dashboard_configs.js` — extracts modelId from URL path
- `endpoints_dashboard.js` — uses URL-embedded modelId (`/api/models/${id}/metrics/`)

---

## Solution

### Design Decisions

**Primary mechanism**: Pass `model_endpoint_id` as a **query parameter** on every API call from JavaScript. The backend reads the query parameter first, with session as fallback.

**Parameter name**: `model_endpoint_id` (not `model_id`) to avoid collision with `api/models/<int:model_id>/` URL paths where `model_id` refers to a RegisteredModel/TrainingRun, not the project.

**Backward compatibility**: Session fallback is preserved so existing bookmarks, external integrations, and the Cloud Scheduler webhook continue to work.

### Backend Changes

#### 1. Modified `_get_model_endpoint()` in both API modules

Query parameter takes priority over session:

```python
def _get_model_endpoint(request):
    """Get model endpoint from query param (preferred) or session (fallback)."""
    from ml_platform.models import ModelEndpoint
    endpoint_id = request.GET.get('model_endpoint_id') or request.session.get('model_endpoint_id')
    if not endpoint_id:
        return None
    try:
        return ModelEndpoint.objects.get(id=endpoint_id)
    except (ModelEndpoint.DoesNotExist, ValueError):
        return None
```

This single change makes all 74 endpoints automatically support the query parameter with zero per-endpoint modifications.

#### 2. Added session-setting to all page views

Added `request.session['model_endpoint_id'] = model_id` to `model_dashboard`, `model_training`, and `model_deployment` views (matching what `model_experiments` already did). This serves as a safety net for any code paths that don't yet send the query parameter.

### Frontend Changes

#### Pattern: `appendModelEndpointId(url)` helper

Every JS module received a private helper function:

```javascript
function appendModelEndpointId(url) {
    if (!config.modelId) return url;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}model_endpoint_id=${config.modelId}`;
}
```

- **No-op when modelId is null** — safe to deploy incrementally
- **Handles existing query params** — uses `&` when URL already contains `?`
- **Per-module scoping** — each IIFE has its own copy, avoiding global namespace pollution

The one exception is `pipeline_dag.js`, which uses global functions (not an IIFE). For this module, a global variable and setter function were used:

```javascript
let pipelineDagModelEndpointId = null;

function setPipelineDagModelEndpointId(modelId) {
    pipelineDagModelEndpointId = modelId;
}

function appendPipelineDagModelEndpointId(url) {
    if (!pipelineDagModelEndpointId) return url;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}model_endpoint_id=${pipelineDagModelEndpointId}`;
}
```

#### Module Configuration

Each JS module was updated to accept `modelId` through its existing configuration pattern (`configure()`, `init()`, or direct config). The modelId flows from Django templates via `{{ model.id }}`.

#### Cross-Module Forwarding

Some modules open other modules (e.g., TrainingCards opens ScheduleModal). In these cases, `modelId` is forwarded at the call site:

```javascript
ScheduleModal.configure({
    modelId: config.modelId,
    onSuccess: function(schedule) { ... }
});
```

This ensures the child module always has the correct project context regardless of which tab triggered the action.

#### Template-Level Initialization

Each page template passes `modelId: {{ model.id }}` to all JS modules it initializes:

```javascript
// model_deployment.html
ExpViewModal.configure({ modelId: {{ model.id }} });
IntegrateModal.configure({ modelId: {{ model.id }} });
DeployWizard.configure({ modelId: {{ model.id }}, ... });
EndpointsTable.init({ modelId: {{ model.id }}, ... });
```

Templates with inline fetch calls also define a local `appendModelEndpointId()` helper using the template-provided model ID.

---

## Implementation Plan

The work was organized into phases to manage the scope (19 files, 99 fetch calls):

| Phase | Scope | Files | Fetch Sites |
|-------|-------|:---:|:---:|
| 1 | Backend helpers + views | 3 | 0 (enables all) |
| 2 | JS modules | 12 | 77 |
| 3 | HTML templates | 4 | 22 |

### Files Modified

**Backend (3 files):**
- `ml_platform/training/api.py`
- `ml_platform/experiments/api.py`
- `ml_platform/views.py`

**JS Modules (12 files):**
- `static/js/training_cards.js` (15 fetch calls)
- `static/js/exp_view_modal.js` (27 fetch calls)
- `static/js/training_wizard.js` (8 fetch calls)
- `static/js/endpoints_table.js` (6 fetch calls)
- `static/js/schedule_modal.js` (5 fetch calls)
- `static/js/models_registry.js` (4 fetch calls)
- `static/js/deploy_wizard.js` (3 fetch calls)
- `static/js/integrate_modal.js` (3 fetch calls)
- `static/js/model_dashboard_experiments.js` (3 fetch calls)
- `static/js/model_dashboard_models.js` (1 fetch call)
- `static/js/schedule_calendar.js` (1 fetch call)
- `static/js/pipeline_dag.js` (1 fetch call)

**HTML Templates (4 files):**
- `templates/ml_platform/model_training.html` (2 inline fetch calls + module init)
- `templates/ml_platform/model_experiments.html` (20 inline fetch calls + module init)
- `templates/ml_platform/model_dashboard.html` (module init only)
- `templates/ml_platform/model_deployment.html` (module init only)

**Total: 19 files, +275 / -109 lines, 99 fetch() calls wrapped**

---

## Verification

### Two-Tab Test
1. Open Project A in Tab 1, Project B in Tab 2
2. Navigate to Training, Dashboard, Experiments, and Deployment in each tab
3. Verify each tab shows only its own project's data

### Network Tab Audit
1. Open DevTools, filter by `/api/`
2. Verify every request includes `model_endpoint_id=` in the query string

### Fresh Session Test
1. Clear cookies, open a Training page directly via URL
2. API calls should work (modelId from JS query param, no session needed)

### Action Isolation Test
1. In Tab 1, create/cancel/delete a training run
2. Verify it operates on Tab 1's project, not Tab 2's
