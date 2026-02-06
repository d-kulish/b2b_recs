# Cross-Project Isolation: ModelConfig Scoping & Endpoint Name Prefixing

## Task

Prepare the platform for correct multi-project operation by fixing two architectural issues that would cause cross-project data leakage and resource naming collisions.

---

## Problem Analysis

### Problem 1: ModelConfig is globally shared

`ModelConfig` had no foreign key to `ModelEndpoint` (the project entity). Every project saw the same pool of model configs, which caused:

- **Data leakage** -- Project A's configs appeared in Project B's dropdowns, dashboards, and coverage matrices.
- **Name collisions** -- Creating a config named "standard" in Project A would block Project B from using the same name, since the name uniqueness check was global.
- **Incorrect dashboard stats** -- The coverage matrix (`_get_coverage_matrix`) and model config stats (`_get_model_config_stats`) in `ConfigDashboardStatsService` queried `ModelConfig.objects.all()`, mixing data across projects.
- **No ownership validation** -- Experiments, pipelines, and training runs accepted any `model_config_id` without verifying it belonged to the current project.

### Problem 2: DeployedEndpoint service names collide across projects

`deploy_to_cloud_run()` in `TrainingService` generated Cloud Run service names like `{model_name}-serving` with no project identifier. Two projects deploying a model with the same registered name (e.g., "churn-retrieval") would both attempt to create `churn-retrieval-serving`, causing a Cloud Run naming collision.

The frontend `generateServiceName()` in `deploy_wizard.js` had the same issue -- it generated names without any project context.

---

## Files Changed

| File | Change |
|------|--------|
| `ml_platform/models.py` | Added `model_endpoint` FK + `unique_together` on ModelConfig |
| `ml_platform/migrations/0056_modelconfig_model_endpoint.py` | 4-step migration (add nullable FK, data migration, make non-nullable, unique constraint) |
| `ml_platform/configs/urls.py` | Moved list/create/clone/check-name URLs under `api/models/<model_id>/model-configs/` |
| `ml_platform/configs/api.py` | Scoped all CRUD operations to `model_endpoint_id`; added `model_endpoint_id` to serializer |
| `ml_platform/configs/services.py` | Scoped dashboard stats and coverage matrix queries |
| `ml_platform/experiments/api.py` | Added project ownership validation for QuickTest creation; scoped suggestions query |
| `ml_platform/pipelines/api.py` | Added project ownership validation for pipeline QuickTests |
| `ml_platform/training/api.py` | Scoped ModelConfig validation in training run creation (2 locations) |
| `ml_platform/training/services.py` | Auto-prefix service names with project slug in `deploy_to_cloud_run()` |
| `ml_platform/admin.py` | Added `model_endpoint` to list_display, list_filter, fieldsets |
| `static/js/deploy_wizard.js` | Added `projectSlug` config; updated `generateServiceName()` to prefix |
| `static/js/training_wizard.js` | Updated `modelConfigs` endpoint template to project-scoped URL |
| `templates/ml_platform/model_configs.html` | Updated 4 fetch URLs to include `modelId` |
| `templates/ml_platform/model_experiments.html` | Updated model configs fetch URL to include `modelId` |
| `templates/ml_platform/model_training.html` | Generate `projectSlug` from model name and pass to DeployWizard |

---

## Fix 1: Scope ModelConfig to ModelEndpoint

### 1A. Model Change

Added a `ForeignKey` from `ModelConfig` to `ModelEndpoint` with `CASCADE` delete and a `unique_together` constraint on `(model_endpoint, name)`:

```python
class ModelConfig(models.Model):
    model_endpoint = models.ForeignKey(
        ModelEndpoint,
        on_delete=models.CASCADE,
        related_name='model_configs',
    )

    class Meta:
        unique_together = ['model_endpoint', 'name']
```

This means config names only need to be unique within a project -- two projects can each have a config called "standard".

### 1B. Migration Strategy

The migration (`0056`) uses a 4-step approach to avoid data loss:

1. **Add nullable FK** -- existing rows get `NULL` temporarily
2. **Data migration** -- assign all existing ModelConfigs to `ModelEndpoint.objects.first()`
3. **Alter to non-nullable** -- enforce the FK constraint going forward
4. **Add unique_together** -- enforce `(model_endpoint, name)` uniqueness

### 1C. URL Restructuring

Routes that need project context moved under `api/models/<model_id>/model-configs/`:

| Endpoint | Before | After |
|----------|--------|-------|
| List | `api/model-configs/` | `api/models/<model_id>/model-configs/` |
| Create | `api/model-configs/create/` | `api/models/<model_id>/model-configs/create/` |
| Clone | `api/model-configs/<id>/clone/` | `api/models/<model_id>/model-configs/<id>/clone/` |
| Check name | `api/model-configs/check-name/` | `api/models/<model_id>/model-configs/check-name/` |

ID-based routes (get, update, delete) remain unchanged since IDs are globally unique.

Global/stateless routes also remain unchanged: presets, validate, rating-head-presets, loss-functions.

### 1D. API Changes

- **list_model_configs** -- filters by `model_endpoint_id=model_id`
- **create_model_config** -- sets `model_endpoint_id=model_id`; name check scoped to project
- **clone_model_config** -- accepts `model_id` to set on the new record
- **check_model_config_name** -- filters by `model_endpoint_id=model_id`
- **update_model_config** -- name uniqueness check scoped to `mc.model_endpoint`
- **serialize_model_config** -- now includes `model_endpoint_id` in output

### 1E. Cross-Domain Validation

Added ownership checks wherever a `model_config_id` is accepted:

- **experiments/api.py** -- validates `model_config.model_endpoint == model_endpoint` before creating QuickTest
- **pipelines/api.py** -- validates config belongs to same project as the FeatureConfig
- **training/api.py** -- uses `ModelConfig.objects.get(id=..., model_endpoint=model_endpoint)` in both training run creation paths

### 1F. Dashboard Scoping

- `_get_model_config_stats()` -- changed from `ModelConfig.objects.all()` to `.filter(model_endpoint=self.model)`
- `_get_coverage_matrix()` -- same change; coverage heatmap now only shows current project's configs

---

## Fix 2: Auto-prefix Endpoint Names with Project Slug

### 2A. Backend (`training/services.py`)

`deploy_to_cloud_run()` now generates a project slug from `self.ml_model.name`:

```python
project_slug = self.ml_model.name.lower().replace('_', '-').replace(' ', '-')
project_slug = ''.join(c if c.isalnum() or c == '-' else '' for c in project_slug).strip('-')[:20]
```

All service names are prefixed: `{project_slug}-{model_name}-serving`. User-provided names also get the prefix if it's missing.

### 2B. Frontend (`deploy_wizard.js`)

- Added `config.projectSlug` to the DeployWizard configuration object
- `generateServiceName()` prepends the project slug: `prefix + name + '-serving'`
- Names are still truncated to 63 characters (Cloud Run limit)

### 2C. Template (`model_training.html`)

The project slug is derived from the Django template variable:

```javascript
const projectSlug = '{{ model.name|lower }}'
    .replace(/_/g, '-').replace(/ /g, '-')
    .replace(/[^a-z0-9-]/g, '').replace(/--+/g, '-')
    .replace(/^-|-$/g, '').substring(0, 20);
```

### 2D. Backward Compatibility

Existing `DeployedEndpoint` records keep their current `service_name` -- no live Cloud Run services are renamed. Only new deployments get the project-prefixed name.

---

## Verification Checklist

- [ ] **Config isolation**: Configs page for Project A shows only Project A's configs
- [ ] **Name uniqueness**: Two projects can each have a config named "standard"
- [ ] **Experiments scoping**: Model config dropdown in experiments page shows only current project's configs
- [ ] **Dashboard scoping**: Coverage matrix only shows current project's model configs
- [ ] **Endpoint naming**: Deploy from project "test_v1" produces `test-v1-{model}-serving`
- [ ] **No collision**: Deploy same model name from "test_v2" produces `test-v2-{model}-serving`
- [ ] **Existing data**: Existing ModelConfigs assigned to first project via migration
- [ ] **Existing endpoints**: Keep their current service names unchanged
