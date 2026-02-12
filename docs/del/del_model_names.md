# Model Names: Problem Analysis

## Problem Symptoms

The "Models" KPI showed different numbers across three locations:

| Location | Count | Source |
|----------|-------|--------|
| Starting page — Assets card | **10** | `RegisteredModel.objects.count()` in `views.py:110` |
| Starting page — per-project card (test_v1) | **10** | `model.registered_models.all().count()` in `views.py:59` |
| Training page — Model Registry section | **8** | `TrainingRun` filtered by non-empty `vertex_model_resource_name`, deduplicated by `vertex_model_name` in `api.py:3996-3999` |
| Vertex AI Model Registry (gcloud) | **9** | Actual state in Google Cloud |

None of the four numbers matched.

---

## Data Audit (2026-02-08)

### Vertex AI Model Registry — 9 models

| Model | ID | Versions | Artifact Bucket | Verdict |
|-------|----|----------|-----------------|---------|
| chern_retriv_v2 | 5241525861236080640 | v1 | b2b-recs-training-artifacts | Legitimate |
| chern_retriv_v5 | 8920403806844354560 | v5 | b2b-recs-training-artifacts | Legitimate |
| chern_retriv_v6 | 7334503419312340992 | v1 | b2b-recs-training-artifacts | Legitimate |
| chern_rank_v3 | 2864962264123834368 | v1 | b2b-recs-training-artifacts | Legitimate |
| chern_rank_v4 | 3326581225929310208 | v4 | b2b-recs-training-artifacts | Legitimate |
| chern_hybrid_v1 | 174413330490851328 | v2 | b2b-recs-training-artifacts | Legitimate |
| chern_hybrid_v3 | 7115797362408161280 | v1 | b2b-recs-training-artifacts | Legitimate |
| trd-test-20260129-123106 | 252311530295525376 | v1 | b2b-recs-**quicktest**-artifacts | Test junk |
| trd-test-20260129-123928 | 4998894431311495168 | v1 | b2b-recs-**quicktest**-artifacts | Test junk |

### RegisteredModel DB table — 10 records

| ID | model_name | vertex_model_resource_name | Exists in Vertex? |
|----|------------|---------------------------|-------------------|
| 1 | chern_retriv_v2 | projects/…/models/5241525861236080640 | Yes |
| 2 | chern_retriv_v5 | projects/…/models/8920403806844354560 | Yes |
| 3 | **chern_rank_v1** | projects/…/models/6812719181234962432 | **No — NOT_FOUND** |
| 4 | chern_hybrid_v1 | projects/…/models/174413330490851328 | Yes |
| 5 | **chern_hybrid_v2** | *(empty)* | **Never registered** |
| 6 | chern_hybrid_v3 | projects/…/models/7115797362408161280 | Yes |
| 7 | **short-test-20260129** | *(empty)* | **Never registered** |
| 8 | chern_rank_v3 | projects/…/models/2864962264123834368 | Yes |
| 9 | chern_rank_v4 | projects/…/models/3326581225929310208 | Yes |
| 10 | chern_retriv_v6 | projects/…/models/7334503419312340992 | Yes |

### Discrepancies

**In RegisteredModel but not in Vertex AI (3 orphans):**
- `chern_rank_v1` — points to model ID `6812719181234962432` which returns NOT_FOUND from Vertex AI (deleted)
- `chern_hybrid_v2` — empty `vertex_model_resource_name` (training run failed, model never created)
- `short-test-20260129` — empty `vertex_model_resource_name` (test run, model never created)

**In Vertex AI but not in RegisteredModel (2 test models):**
- `trd-test-20260129-123106` — artifacts in quicktest bucket, no RegisteredModel record
- `trd-test-20260129-123928` — artifacts in quicktest bucket, no RegisteredModel record

---

## Data Cleanup Performed

1. Deleted 2 test models from Vertex AI:
   - `gcloud ai models delete 252311530295525376 --region=europe-central2`
   - `gcloud ai models delete 4998894431311495168 --region=europe-central2`

2. Deleted 3 orphan RegisteredModel records from DB:
   - `RegisteredModel.objects.filter(id__in=[3, 5, 7]).delete()`
   - This cascade-deleted 2 linked TrainingSchedule records

**Result:** 7 models in Vertex AI = 7 RegisteredModel records in DB.

---

## Underlying Bugs

### Bug 1: RegisteredModel is created before a model exists

**Location:** `ml_platform/training/services.py:236-243`

```python
def create_training_run(self, ...):
    # Get or create RegisteredModel for this training run
    if not registered_model:
        reg_model_service = RegisteredModelService(self.ml_model)
        registered_model = reg_model_service.get_or_create_for_training(
            model_name=name,
            model_type=model_type,
            ...
        )

    # Create training run
    training_run = TrainingRun.objects.create(
        ...
        registered_model=registered_model,
    )
```

`RegisteredModelService.get_or_create_for_training()` (`registered_model_service.py:65-86`) does a `RegisteredModel.objects.get_or_create()` at training run creation time. The TFX pipeline hasn't started yet. If the pipeline fails, the RegisteredModel record stays in the database permanently.

The same pattern exists in two more API endpoints:
- `api.py:2471-2502` — `create_training_schedule()` creates RegisteredModel when creating a schedule
- `api.py:3255-3307` — `create_training_schedule_from_run()` creates RegisteredModel from a source run

**Effect:** Failed training runs and test runs leave orphan RegisteredModel records. The starting page counts them via `RegisteredModel.objects.count()` (`views.py:110`), inflating the "Models" KPI.

### Bug 2: Delete clears TrainingRun but never touches RegisteredModel

**Location:** `ml_platform/training/api.py:4429-4506`

```python
def model_delete(request, model_id):
    # 1. Delete from Vertex AI — works correctly
    service.delete_model_from_registry(training_run)

    # 2. Clear TrainingRun fields — works correctly
    training_run.vertex_model_resource_name = ''
    training_run.vertex_model_name = ''
    training_run.vertex_model_version = ''
    training_run.registered_at = None
    training_run.save(update_fields=[...])

    # 3. RegisteredModel — NEVER TOUCHED
```

When a user deletes a model through the Model Registry UI:
1. The model is deleted from Vertex AI via `service.delete_model_from_registry()` (`services.py:1725-1763`) — this works
2. The TrainingRun's registration fields are cleared — this works
3. The RegisteredModel record is left untouched — it remains in the DB with a stale `vertex_model_resource_name` pointing to a model that no longer exists

**Effect:** After deleting a model from Vertex AI through the UI, the RegisteredModel record persists. The starting page continues counting it. This is exactly what happened with `chern_rank_v1` — the model was deleted from Vertex AI but RegisteredModel id=3 still pointed to the deleted model ID `6812719181234962432`.

### Why the Training Page Shows the Correct Number

The Model Registry section on the training page (`api.py:3996-3999`) counts models differently:

```python
all_models = TrainingRun.objects.filter(**base_filter).exclude(vertex_model_resource_name='')
total_unique = all_models.values('vertex_model_name').distinct().count()
```

It queries `TrainingRun` (not `RegisteredModel`), filters by non-empty `vertex_model_resource_name`, and deduplicates by `vertex_model_name`. After the delete operation clears the TrainingRun fields (Bug 2, step 2), the deleted model no longer appears in this query. So the training page self-corrects, but the starting page does not.

### Query Comparison

| Page | Table | Filter | Result |
|------|-------|--------|--------|
| Starting page (Assets) | `RegisteredModel` | None | Counts orphans + deleted models |
| Starting page (per-project) | `RegisteredModel` via `model.registered_models.all()` | None | Same problem, per project |
| Training page (Model Registry) | `TrainingRun` | `vertex_model_resource_name` not null/empty, distinct on `vertex_model_name` | Correct — only models with active Vertex registration |

---

## Bug 3: Deploy does not verify the model exists in Vertex AI

**Location:** `ml_platform/training/services.py:1515-1655` and `ml_platform/training/api.py:4256-4335`

### Current deploy flow

The `model_deploy` API endpoint (`api.py:4256`) performs these checks before deploying:

1. TrainingRun exists and has `vertex_model_resource_name` not null (`api.py:4273-4276`)
2. Model is blessed / passed evaluation (`api.py:4285-4289`)
3. Model is not already deployed (`api.py:4293-4297`)

Then `TrainingService.deploy_model()` (`services.py:1515`) does:

1. Validates training run status is `COMPLETED` (`services.py:1529`)
2. Validates `is_blessed` (`services.py:1535`)
3. Searches Vertex AI for a model matching the display name (`services.py:1566-1569`)
4. **If model is NOT found in Vertex AI** — instead of failing, it **uploads the model from GCS** (`services.py:1596-1607`):

```python
if not models:
    # Try to find by pushed_model path
    pushed_model_path = f"{training_run.gcs_artifacts_path}/pushed_model"
    ...
    model = aiplatform.Model.upload(
        display_name=model_display_name,
        artifact_uri=pushed_model_path,
        serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-12:latest",
        ...
        parent_model=parent_model_resource_name,
    )
```

### The problem

The deploy flow never verifies that the model referenced by `training_run.vertex_model_resource_name` actually exists in the Vertex AI Model Registry. The only check is `vertex_model_resource_name__isnull=False` (`api.py:4276`), which only checks that the DB field is populated — not that the model exists in Vertex AI.

Worse, when the model is not found in Vertex AI, the deploy silently re-uploads it from GCS artifacts instead of reporting an error. This means:

- A model that was intentionally deleted from Vertex AI (via the Model Registry delete button) could be silently re-registered and deployed if its GCS artifacts still exist
- The DB field `vertex_model_resource_name` is trusted as proof that the model exists, but as shown in the data audit, this field can point to models that no longer exist (e.g., `chern_rank_v1` pointing to `6812719181234962432` which returns NOT_FOUND)

### What should happen

Before deploying, the service should verify the model exists in the Vertex AI Model Registry by checking the actual `vertex_model_resource_name` (not just the display name). If the model does not exist:

- Return a clear error: "Model not found in Vertex AI Model Registry. It may have been deleted."
- Do NOT silently re-upload from GCS
- Clean up the stale DB fields (`vertex_model_resource_name`, etc.) on the TrainingRun and RegisteredModel

---

## Bug 4: `model_delete` checks wrong deployment layer

**Location:** `ml_platform/training/api.py:4461-4470` (before fix)

```python
# BROKEN — queries Vertex AI Endpoints (unused deployment path)
service = TrainingService(model_endpoint)
endpoint_info = service.get_deployed_model_resource_names()
deployed_models = endpoint_info['deployed_models']

if training_run.vertex_model_resource_name in deployed_models:
    return JsonResponse({'error': 'Cannot delete a deployed model.'}, status=400)
```

`get_deployed_model_resource_names()` queries Vertex AI Endpoints — the deployment path that is not used. All actual deployments go through Cloud Run via `DeployedEndpoint` records. This means a user could delete a model that has an active Cloud Run deployment, causing the deployment to fail on next restart.

---

## Fixes Applied (2026-02-08)

### Fix 1: Deployment Integrity Verification

**Files:** `ml_platform/training/services.py`, `ml_platform/training/api.py`

Added three verification helpers to `TrainingService`:

| Method | Purpose |
|--------|---------|
| `verify_model_in_vertex_ai(resource_name)` | Checks model exists by fetching `display_name` via API |
| `verify_gcs_artifacts_exist(gcs_path)` | Lightweight check for `pushed_model/` blobs (max_results=1) |
| `batch_verify_models_in_vertex_ai()` | Lists all models in one API call, returns set of resource names |

`deploy_to_cloud_run()` now verifies both Vertex AI model existence and GCS artifacts before proceeding. Since this is the shared low-level deploy method, both the first-deploy path (`training_run_deploy_cloud_run`) and the redeploy path (`redeploy_endpoint()`) benefit.

### Fix 2: `model_delete` Complete Cleanup

**File:** `ml_platform/training/api.py`, function `model_delete`

| Before | After |
|--------|-------|
| Checked Vertex AI Endpoints (dead code path) | Checks `DeployedEndpoint.objects.filter(is_active=True)` |
| No GCS cleanup | Calls `_delete_gcs_artifacts()` to remove training artifacts |
| No endpoint marking | Sets `model_deleted=True` on inactive `DeployedEndpoint` records |
| No version cache sync | Calls `RegisteredModelService.sync_version_cache()` |

### Fix 3: `model_deleted` Field on DeployedEndpoint

**File:** `ml_platform/training/models.py`

Added `model_deleted = BooleanField(default=False)` to `DeployedEndpoint`. This is orthogonal to `is_active`:

| `is_active` | `model_deleted` | Meaning |
|-------------|-----------------|---------|
| True | False | Normal active deployment |
| False | False | Stopped but restorable |
| False | True | Stopped, model deleted — cannot restore |

Both `redeploy_endpoint()` (services.py) and `endpoint_deploy` (api.py) now fast-fail with a clear error when `model_deleted=True`.

Migration: `0012_add_model_deleted_to_deployed_endpoint.py`

### Fix 4: Proactive Registry Verification on Model List

**File:** `ml_platform/training/api.py`, function `models_list`

The `models_list` API now calls `batch_verify_models_in_vertex_ai()` and includes:
- `registry_verified` per model (`true`/`false`/`null` if check unavailable)
- `registry_check_available` flag in response

### Fix 5: Frontend Safeguards

**Endpoints Table** (`static/js/endpoints_table.js`, `static/css/endpoints_table.css`):
- "Model Deleted" amber badge when `model_deleted=true`
- Deploy button disabled with tooltip when model deleted
- `confirmDeploy()` returns early with error toast

**Models Registry** (`static/js/models_registry.js`, `static/css/models_registry.css`):
- "Not in Registry" red warning badge when `registry_verified === false`
- Deploy button disabled when model missing from Vertex AI

---

## Verification Performed

### Automated
- `python manage.py makemigrations --check` — no pending migrations (migration matches model)
- `python manage.py migrate training` — migration applied successfully
- `python manage.py check` — system check identified no issues
- Python import verification — all new methods accessible on `TrainingService`, `api.py` imports cleanly

### Files Modified

| File | Change Type |
|------|-------------|
| `ml_platform/training/models.py` | Added `model_deleted` field |
| `ml_platform/training/migrations/0012_...py` | New migration |
| `ml_platform/training/services.py` | 3 verification helpers + deploy checks + redeploy guard |
| `ml_platform/training/api.py` | Fixed `model_delete`, added registry verification to `models_list`, endpoint serializer, `endpoint_deploy` guard |
| `static/js/endpoints_table.js` | Model Deleted badge + disabled Deploy |
| `static/js/models_registry.js` | Not in Registry badge + disabled Deploy |
| `static/css/endpoints_table.css` | `.model-deleted` badge style |
| `static/css/models_registry.css` | `.registry-missing` badge style |

### Manual Testing Checklist

- [ ] Deploy with deleted Vertex AI model → expect clear error message
- [ ] Reactivate endpoint after model deleted → "Model Deleted" badge, Deploy disabled
- [ ] Model Registry list → "Not in Registry" badge for missing models
- [ ] `model_delete` full cleanup → GCS artifacts gone, inactive endpoints marked, version cache synced
- [ ] `model_delete` blocks active deployments → "Cannot delete a deployed model" error

---

## Fixes Applied (2026-02-08) — Bug 1: Early Model Naming

### Problem

`RegisteredModel` records were created eagerly at training run creation time (`services.py:236-243`), before the TFX pipeline starts. If the pipeline fails, the record persists as an orphan with empty `vertex_model_resource_name`, inflating the "Models" KPI on the dashboard.

Three code paths created RegisteredModel early:
1. Manual training runs (`create_training_run()`)
2. Schedule creation (`api.py:2471-2502`)
3. Schedule-from-run creation (`api.py:3255-3307`)

### Fix 6: Deferred Registration for Manual Training Runs

**File:** `ml_platform/training/services.py`

Moved `RegisteredModel` creation from `create_training_run()` to `_register_to_model_registry()` — the method called after a successful Vertex AI model upload. Manual training runs now start with `registered_model=None` and only get a `RegisteredModel` record after the pipeline succeeds and the model is actually registered.

Scheduled runs are unchanged — they pass `registered_model` from the schedule, which represents an intentional, named model lineage.

**Why this is safe for parallel runs:** The parent model lookup in `_register_to_model_registry()` (lines 1095-1103) queries the `TrainingRun` table directly (not `RegisteredModel`), so versioning works regardless. The `get_or_create()` with `unique_together` constraint handles name collision atomically.

### Fix 7: Dashboard KPI Queries Exclude Orphans

**File:** `ml_platform/views.py`

| Location | Before | After |
|----------|--------|-------|
| Global Assets KPI (line 110) | `RegisteredModel.objects.count()` | `.exclude(vertex_model_resource_name='').exclude(vertex_model_resource_name__isnull=True).count()` |
| Per-project KPI (lines 58-59) | `model.registered_models.all()` | `model.registered_models.exclude(vertex_model_resource_name='').exclude(vertex_model_resource_name__isnull=True)` |

The deployed models count (`kpi_models_deployed`) uses the same `registered` queryset, so the filter propagates automatically.

### Fix 8: Periodic Orphan Cleanup (Scheduled Job)

Added a scheduled job to clean up any remaining orphans — from schedules deleted before a successful run, or historical data.

**New management command:** `cleanup_orphan_models`

```
python manage.py cleanup_orphan_models --dry-run   # Preview
python manage.py cleanup_orphan_models              # Delete orphans older than 7 days
python manage.py cleanup_orphan_models --days 14    # Custom age threshold
```

Cleanup logic:
1. Finds `RegisteredModel` records where `vertex_model_resource_name` is empty/null and `created_at` is older than N days (default: 7)
2. Skips records with linked `TrainingRun` in non-terminal state (pending, scheduled, submitting, running, deploying)
3. Deletes orphans and logs details for audit trail

**Scheduler setup:** Cloud Scheduler job `cleanup-orphan-models` runs daily at 04:00 UTC (after the 03:00 GCS cleanup).

| Component | File |
|-----------|------|
| Management command | `ml_platform/management/commands/cleanup_orphan_models.py` |
| Scheduler setup command | `ml_platform/management/commands/setup_orphan_cleanup_scheduler.py` |
| Webhook endpoint | `ml_platform/views.py` → `scheduler_cleanup_orphan_models_webhook()` |
| Scheduler setup API | `ml_platform/views.py` → `api_setup_orphan_cleanup_scheduler()` |
| URL paths | `ml_platform/urls.py` (2 new paths) |

### Expected Outcome

| Metric | Before | After |
|--------|--------|-------|
| Dashboard "Models" KPI | Counts all RegisteredModel records (including orphans from failed pipelines) | Only counts models actually registered in Vertex AI |
| Manual training run failure | Leaves orphan RegisteredModel record permanently | No RegisteredModel created — nothing to clean up |
| Schedule with no successful runs | Orphan RegisteredModel accumulates | Cleaned up after 7 days by scheduled job |
| Historical orphans | Persist indefinitely | Cleaned up by first scheduled job run |

### Files Modified

| File | Change |
|------|--------|
| `ml_platform/training/services.py` | Removed early RegisteredModel creation in `create_training_run()`, added deferred creation in `_register_to_model_registry()` |
| `ml_platform/views.py` | KPI queries exclude orphans, added webhook + scheduler setup endpoints |
| `ml_platform/urls.py` | 2 new URL paths for orphan cleanup |
| `ml_platform/management/commands/cleanup_orphan_models.py` | **NEW** — management command |
| `ml_platform/management/commands/setup_orphan_cleanup_scheduler.py` | **NEW** — scheduler management command |

### Verification

- `python manage.py check` — no issues
- No migrations needed (`TrainingRun.registered_model` FK is already `null=True`)
- Existing test failures are pre-existing (`Dataset()` got unexpected keyword arg `bq_dataset` — unrelated)

### Deployed (2026-02-08)

Cloud Scheduler job created and tested:

```
$ curl -s -X POST .../api/system/setup-orphan-cleanup-scheduler/
{"status": "success", "action": "created", "job_name": "projects/b2b-recs/locations/europe-central2/jobs/cleanup-orphan-models", "schedule": "0 4 * * *"}

$ curl -s -X POST .../api/system/cleanup-orphan-models-webhook/
{"status": "success", "message": "Orphan model cleanup completed", "output": "...Found 0 orphaned RegisteredModel(s) older than 7 days.\n\nDeleted 0 orphaned RegisteredModel(s), skipped 0 with active training runs\n"}
```

All three system cleanup/metrics jobs now active:

| Job | Schedule (UTC) | Purpose |
|-----|----------------|---------|
| `collect-resource-metrics` | 02:00 | Collect CPU/memory/request metrics from Cloud Run |
| `cleanup-gcs-artifacts` | 03:00 | Delete old GCS training artifacts |
| `cleanup-orphan-models` | 04:00 | Delete orphan RegisteredModel records (never registered to Vertex AI) |

First run found 0 orphans — expected since the 3 historical orphans were manually cleaned during the data audit.
