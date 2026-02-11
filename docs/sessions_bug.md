# Cross-Tab Project Data Leakage Bug

**Date**: 2026-02-11
**Commit**: `ae59c13`
**Scope**: 19 files changed, +507 / -109 lines

---

## 1. The Problem

Users reported that **opening different ML Platform projects in separate browser tabs showed wrong data**. For example: open `test_v1` in Tab 1, open `Lviv_test` in Tab 2, switch back to Tab 1 — and Tab 1 now displays `Lviv_test`'s training runs, experiments, endpoints, and metrics. Every user action in Tab 1 (cancel a run, deploy a model, create a schedule) would silently operate on the wrong project.

This affected all four pages of the platform: Dashboard, Training, Experiments, and Deployment.

---

## 2. Analysis

### 2.1. How the Backend Resolves "Current Project"

The platform has two main API domains — Training (`ml_platform/training/api.py`, 63 view functions) and Experiments (`ml_platform/experiments/api.py`, 25 view functions). Almost every API endpoint needs to know which project (ModelEndpoint) the user is working with. This is resolved by a shared helper function, `_get_model_endpoint()`, duplicated identically in both files:

```python
# BEFORE (both training/api.py and experiments/api.py)
def _get_model_endpoint(request):
    """Get model endpoint from session."""
    from ml_platform.models import ModelEndpoint
    endpoint_id = request.session.get('model_endpoint_id')
    if not endpoint_id:
        return None
    try:
        return ModelEndpoint.objects.get(id=endpoint_id)
    except ModelEndpoint.DoesNotExist:
        return None
```

The function reads `model_endpoint_id` exclusively from `request.session` — Django's server-side session store. This is the single point where every API endpoint resolves which project to query.

The function is called 53 times in `training/api.py` and 24 times in `experiments/api.py` — a total of **77 call sites** across the two files, covering all endpoints that list training runs, experiments, registered models, deployed endpoints, schedules, metrics, comparisons, etc.

### 2.2. The Session Is Shared Across All Tabs

Django sessions are identified by a cookie (`sessionid`). All browser tabs for the same domain share the same cookie jar, and therefore the same session. This means `request.session['model_endpoint_id']` is a **single global value** that gets overwritten every time any tab navigates to a new project.

**Scenario reproducing the bug:**
1. User opens `http://platform/models/5/training/` in Tab 1 (Project A)
2. User opens `http://platform/models/8/experiments/` in Tab 2 (Project B)
3. The `model_experiments` view sets `request.session['model_endpoint_id'] = 8`
4. Tab 1 makes an AJAX call to `/api/training-runs/` — the backend reads session, finds `model_endpoint_id = 8`, and **returns Project B's training runs to Tab 1**

### 2.3. Only One View Set the Session

Investigation of `ml_platform/views.py` revealed that of the four page-level views, **only `model_experiments` wrote to the session**:

```python
# model_experiments (line 276) — the ONLY view that set the session
@login_required
def model_experiments(request, model_id):
    model = get_object_or_404(ModelEndpoint, id=model_id)
    request.session['model_endpoint_id'] = model_id   # <-- only here
    ...

# model_dashboard — DID NOT set session
@login_required
def model_dashboard(request, model_id):
    model = get_object_or_404(ModelEndpoint, id=model_id)
    # (no session write)
    ...

# model_training — DID NOT set session
@login_required
def model_training(request, model_id):
    model = get_object_or_404(ModelEndpoint, id=model_id)
    # (no session write)
    ...

# model_deployment — DID NOT set session
@login_required
def model_deployment(request, model_id):
    model = get_object_or_404(ModelEndpoint, id=model_id)
    # (no session write)
    ...
```

This meant the session value was **stale from the last Experiments page visit**. If a user navigated directly to Training or Dashboard without visiting Experiments first, the session could contain a completely unrelated project ID from a previous browsing session — or no ID at all.

### 2.4. Frontend Audit: 99 Blind Fetch Calls

The frontend consists of 16 JavaScript modules (each an IIFE/module pattern) and 4 Django HTML templates with inline `<script>` blocks. Every module makes `fetch()` calls to the API endpoints, and **none of them passed any project identifier** — they relied entirely on the backend session to scope the data.

An exhaustive audit of every `fetch()` call across the codebase found:

**JS Modules — 77 fetch() calls across 12 files:**

| Module | fetch() calls | Role | Had modelId before fix? |
|--------|:---:|------|:---:|
| `exp_view_modal.js` | 27 | Experiment/model/endpoint detail modal | No |
| `training_cards.js` | 15 | Training runs list + actions (9 in main IIFE, 6 in TrainingSchedules sub-IIFE) | Partially (main IIFE only) |
| `training_wizard.js` | 8 | New training run wizard | Yes, but unused for API scoping |
| `endpoints_table.js` | 6 | Deployed endpoints list + actions | No |
| `schedule_modal.js` | 5 | Training schedule create/edit | No |
| `models_registry.js` | 4 | Registered models list | No |
| `deploy_wizard.js` | 3 | Cloud Run deployment wizard | No |
| `integrate_modal.js` | 3 | Endpoint integration testing | No |
| `model_dashboard_experiments.js` | 3 | Dashboard experiments summary | No |
| `model_dashboard_models.js` | 1 | Dashboard models summary | No |
| `schedule_calendar.js` | 1 | GitHub-style training calendar | No |
| `pipeline_dag.js` | 1 | Pipeline DAG component logs | No |

**HTML Templates — 22 inline fetch() calls across 2 files:**

| Template | fetch() calls | Examples |
|----------|:---:|---------|
| `model_experiments.html` | 20 | `loadInitialData()` (feature-configs, model-configs, quick-tests), `submitExperiment()`, `cancelExpFromCard()`, `deleteExpFromCard()`, `rerunExpFromCard()`, `loadExperimentsDashboard()`, `loadTrainingHeatmaps()`, `loadMetricsTrend()`, etc. |
| `model_training.html` | 2 | `loadBestExperiments()` (dashboard-stats), `loadBestExpConfigurations()` (top-configurations) |

**Modules that were already correct (no changes needed):**
- `model_dashboard_endpoints.js` — already received `modelId` via `init()` and used it properly
- `model_dashboard_etl.js` — extracts modelId from the URL path (`/models/5/etl/...`)
- `model_dashboard_configs.js` — extracts modelId from the URL path
- `endpoints_dashboard.js` — embeds modelId in the URL path (`/api/models/${id}/metrics/`)

### 2.5. Cross-Module Forwarding Gap

Several JS modules open other modules as sub-actions. For example:
- `TrainingCards` opens `ScheduleModal` when user clicks "Schedule" on a training run
- `ExpViewModal` opens `ScheduleModal` when user clicks "Create Schedule" inside a run's detail view
- `ModelsRegistry` opens `ScheduleModal` when user clicks "Schedule" on a registered model
- `TrainingWizard` opens `ScheduleModal` in the final step of the wizard
- `EndpointsTable` opens `IntegrateModal` when user clicks "Integrate" on an endpoint

Each of these call sites configures the child module with an `onSuccess` callback, but **none passed the project context**. This meant even if the parent module knew the correct project, the child module would fall back to the stale session.

---

## 3. Solution Design

### 3.1. Requirements

1. **Tab isolation**: Each browser tab must independently scope its API calls to the correct project
2. **Backward compatibility**: The Cloud Scheduler webhook, direct URL bookmarks, and any non-browser clients must continue to work
3. **Minimal per-endpoint changes**: With 77 backend call sites, modifying each endpoint individually is not feasible
4. **No global state**: JavaScript modules use the IIFE pattern to avoid global namespace pollution; the fix must respect this

### 3.2. Chosen Approach: Query Parameter with Session Fallback

**Primary mechanism**: Every frontend `fetch()` call appends `?model_endpoint_id=<id>` as a query parameter. The backend reads this first, falling back to the session if absent.

**Why query parameter instead of other approaches:**

- **Custom HTTP header** (`X-Model-Endpoint-Id`): Would work, but requires modifying every `fetch()` call's headers object anyway — same effort as a query param, but less visible in DevTools network tab for debugging
- **URL path rewrite** (`/api/projects/5/training-runs/` instead of `/api/training-runs/`): Would require changing all URL patterns in `urls.py`, all JavaScript endpoint configurations, and all backend view signatures — massive scope
- **LocalStorage/per-tab token**: Complex, requires synchronization, doesn't work across page navigations within the same tab
- **Query parameter**: Simplest, most debuggable (visible in network tab), requires only wrapping existing `fetch()` URLs, and the backend change is a single line per file

**Parameter name choice**: `model_endpoint_id` (not `model_id`) because the URL pattern `api/models/<int:model_id>/` already uses `model_id` to mean a RegisteredModel or TrainingRun ID — a completely different entity. Using the same name would create ambiguity.

### 3.3. Backend Change

A one-line change to both `_get_model_endpoint()` functions makes all 77 downstream endpoints automatically support the query parameter:

```python
# AFTER
def _get_model_endpoint(request):
    """Get model endpoint from query param (preferred) or session (fallback)."""
    from ml_platform.models import ModelEndpoint
    endpoint_id = request.GET.get('model_endpoint_id') or request.session.get('model_endpoint_id')
    #              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  NEW: query param first
    if not endpoint_id:
        return None
    try:
        return ModelEndpoint.objects.get(id=endpoint_id)
    except (ModelEndpoint.DoesNotExist, ValueError):
    #                                   ^^^^^^^^^^  NEW: handle non-integer query param
        return None
```

Additionally, all four page views now set the session (safety net for any code path that doesn't send the query param):

```python
# Added to model_dashboard, model_training, model_deployment
# (model_experiments already had this)
request.session['model_endpoint_id'] = model_id
```

### 3.4. Frontend Pattern

Each JS module received a private helper function placed inside its IIFE scope:

```javascript
function appendModelEndpointId(url) {
    if (!config.modelId) return url;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}model_endpoint_id=${config.modelId}`;
}
```

Every `fetch()` call in the module was then wrapped:

```javascript
// BEFORE
const response = await fetch(`/api/training-runs/${runId}/push/`, { method: 'POST', ... });

// AFTER
const response = await fetch(appendModelEndpointId(`/api/training-runs/${runId}/push/`), { method: 'POST', ... });
```

The helper is a no-op when `config.modelId` is null (safe for incremental rollout), and correctly handles URLs that already contain query parameters by checking for `?` and using `&` when appropriate.

**Special case — `pipeline_dag.js`**: This is the only module that uses global functions instead of the IIFE pattern. It required a different approach with a global variable and setter:

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

Called from the template:
```javascript
// model_training.html
if (typeof setPipelineDagModelEndpointId === 'function') {
    setPipelineDagModelEndpointId({{ model.id }});
}
```

### 3.5. modelId Propagation Chain

The `modelId` originates from Django's `{{ model.id }}` template tag, which is available on every page because every view loads the `ModelEndpoint` object. The propagation works in three layers:

**Layer 1: Template -> Top-level modules** (via `init()` or `configure()` calls in the page's `<script>` block):

```javascript
// model_training.html
TrainingCards.configure({ modelId: {{ model.id }} });
TrainingSchedules.configure({ modelId: {{ model.id }} });
ExpViewModal.configure({ modelId: {{ model.id }} });
DeployWizard.configure({ modelId: {{ model.id }} });
ModelsRegistry.init({ modelId: {{ model.id }}, ... });
```

**Layer 2: Parent modules -> Child modules** (at each call site where one module opens another):

```javascript
// training_cards.js — when user clicks "Schedule" on a training run
ScheduleModal.configure({
    modelId: config.modelId,        // forwarded from TrainingCards' own config
    onSuccess: function(schedule) { ... }
});
ScheduleModal.openForTrainingRun(runId);
```

This forwarding was added to all 5 sites where ScheduleModal is configured (training_cards.js x2, training_wizard.js, models_registry.js, exp_view_modal.js) and both sites where ScheduleCalendar is initialized (model_dashboard_models.js, models_registry.js).

**Layer 3: Inline template code** uses a local `appendModelEndpointId()` function defined at the top of the `<script>` block:

```javascript
// model_experiments.html — reuses existing modelId variable
const modelId = {{ model.id }};
function appendModelEndpointId(url) {
    if (!modelId) return url;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}model_endpoint_id=${modelId}`;
}
```

---

## 4. Implementation

### 4.1. Phase 1: Backend (3 files)

| File | Change |
|------|--------|
| `ml_platform/training/api.py` | Modified `_get_model_endpoint()`: `request.GET.get('model_endpoint_id') or request.session.get(...)`, added `ValueError` to except |
| `ml_platform/experiments/api.py` | Identical change to its own `_get_model_endpoint()` |
| `ml_platform/views.py` | Added `request.session['model_endpoint_id'] = model_id` to `model_dashboard` (line 218), `model_training` (line 261), `model_deployment` (line 302) |

### 4.2. Phase 2: JS Modules (12 files, 77 fetch calls)

Each module received:
1. `modelId: null` added to its `config` object (if not already present)
2. `appendModelEndpointId(url)` helper function
3. `modelId` acceptance in `init()` or `configure()` (e.g., `if (options.modelId) config.modelId = options.modelId;`)
4. Every `fetch(url, ...)` call wrapped as `fetch(appendModelEndpointId(url), ...)`

**`training_cards.js`** was the most complex: it contains two separate IIFEs (`TrainingCards` and `TrainingSchedules`) that each needed their own helper, config property, and wrapped fetch calls. `TrainingSchedules` also needed a new `configure()` function (it previously had none) to receive `modelId` from the template. Plus, both call sites where `TrainingCards` opens `ScheduleModal` needed `modelId: config.modelId` forwarding.

**`exp_view_modal.js`** had the most fetch calls (27), spread across experiment details, model details, endpoint details, push/register/deploy/undeploy actions, version loading, lineage loading, training history, statistics, schema, component logs, and polling intervals.

### 4.3. Phase 3: HTML Templates (4 files, 22 fetch calls)

**`model_experiments.html`** — the largest template with 20 inline fetch calls. Added `appendModelEndpointId()` helper after the existing `const modelId = {{ model.id }}` declaration. Wrapped all 20 calls spanning: initial data load (feature-configs, model-configs, quick-tests in a `Promise.all`), experiment CRUD (submit, cancel, delete, rerun), experiment comparison (selectable list, compare POST), and analytics dashboard (stats, heatmaps, metrics-trend, top-configurations, hyperparameter-analysis, suggestions, dataset-comparison). Added `modelId: modelId` to `ExpViewModal.configure()`.

**`model_training.html`** — Added a new `appendModelEndpointId()` helper using `const modelEndpointId = {{ model.id }}`. Wrapped 2 inline fetch calls (`loadBestExperiments`, `loadBestExpConfigurations`). Added `modelId` to `ExpViewModal.configure()`, `DeployWizard.configure()`, `ModelsRegistry.init()`, `TrainingSchedules.configure()`. Added `setPipelineDagModelEndpointId()` call for the pipeline DAG module.

**`model_dashboard.html`** — No inline fetch calls. Added `modelId: {{ model.id }}` to `ExpViewModal.configure()`, `ModelDashboardModels.init()`, `ModelDashboardExperiments.init()`.

**`model_deployment.html`** — No inline fetch calls. Added `ExpViewModal.configure({ modelId })`, `IntegrateModal.configure({ modelId })`, `modelId` to `DeployWizard.configure()`, `modelId` to `EndpointsTable.init()`.

### 4.4. Audit

After implementation, an exhaustive audit verified:
- **77/77** fetch calls in JS modules are wrapped with `appendModelEndpointId` (or `appendPipelineDagModelEndpointId`)
- **22/22** inline fetch calls in HTML templates are wrapped
- **0 unwrapped fetch calls** remain across the entire codebase

---

## 5. Files Changed Summary

```
 ml_platform/experiments/api.py               |  6 +--
 ml_platform/training/api.py                  |  6 +--
 ml_platform/views.py                         |  7 +++
 static/js/deploy_wizard.js                   | 14 ++++--
 static/js/endpoints_table.js                 | 20 ++++++---
 static/js/exp_view_modal.js                  | 65 ++++++++++++++++------------
 static/js/integrate_modal.js                 | 18 ++++++--
 static/js/model_dashboard_experiments.js     | 13 ++++--
 static/js/model_dashboard_models.js          | 11 ++++-
 static/js/models_registry.js                 | 18 ++++++--
 static/js/pipeline_dag.js                    | 13 +++++-
 static/js/schedule_calendar.js               | 10 ++++-
 static/js/schedule_modal.js                  | 18 +++++---
 static/js/training_cards.js                  | 55 ++++++++++++++++-------
 static/js/training_wizard.js                 | 23 ++++++----
 templates/ml_platform/model_dashboard.html   |  5 ++-
 templates/ml_platform/model_deployment.html  | 10 +++++
 templates/ml_platform/model_experiments.html | 47 +++++++++++---------
 templates/ml_platform/model_training.html    | 25 ++++++++++-
 19 files changed, 275 insertions(+), 109 deletions(-)
```

---

## 6. Verification Checklist

### Two-Tab Test
1. Open `test_v1` in Tab 1, `Lviv_test` in Tab 2
2. Navigate to Training, Dashboard, Experiments, and Deployment in each tab
3. Verify each tab shows only its own project's data
4. Switch back and forth — data must remain stable per tab

### Network Tab Audit
1. Open DevTools -> Network tab, filter by `/api/`
2. Verify every request includes `model_endpoint_id=` in the query string
3. Check that the value matches the project open in that tab

### Fresh Session Test
1. Clear all cookies for the site
2. Open a Training page directly via URL (e.g., `/models/5/training/`)
3. API calls should work correctly — `model_endpoint_id` comes from JS, not the (empty) session

### Action Isolation Test
1. In Tab 1 (Project A), cancel a training run — verify it cancels Project A's run
2. In Tab 2 (Project B), deploy a model — verify it deploys to Project B
3. In Tab 1, create a schedule — verify it's for Project A
4. Verify Tab 2's data is unchanged after Tab 1's actions

### Regression: Non-Browser Clients
1. Cloud Scheduler webhook should continue to work (it doesn't go through `_get_model_endpoint`)
2. Direct API calls without the query param should fall back to session (backward compatible)
