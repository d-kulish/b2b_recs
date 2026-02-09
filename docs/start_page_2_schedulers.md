# Starting Page: Scheduled Jobs Failure Analysis (2026-02-08)

## Context

The Starting Page relies on two Cloud Scheduler jobs that run daily:

| Job | Schedule (UTC) | Endpoint | Purpose |
|-----|---------------|----------|---------|
| `collect-resource-metrics` | `0 2 * * *` | `/api/system/collect-metrics-webhook/` | Collects KPIs for System Details chapter |
| `cleanup-gcs-artifacts` | `0 3 * * *` | `/api/system/cleanup-artifacts-webhook/` | Cleans up old GCS training artifacts |

Both jobs failed on their first scheduled execution (2026-02-08).

## Error Discovery

Cloud Scheduler dashboard showed both jobs as **Failed** with HTTP 500 responses:

```
collect-resource-metrics  Failed  8 Feb 2026, 04:00:17  (latency: 15s)
cleanup-gcs-artifacts     Failed  8 Feb 2026, 05:00:08  (latency: 6.9s)
```

## Log Analysis

### Step 1: Confirm HTTP 500s

Query: `resource.type="cloud_run_revision" AND severity>=ERROR`

Both webhooks returned **HTTP 500** from Cloud Run revision `django-app-00096-dhj`.

### Step 2: Extract Error Messages

Query: `logName=~"stderr" AND timestamp` around each failure window.

**collect-metrics-webhook (02:00 UTC):**
```
ERROR 2026-02-08 02:00:17,178 views Scheduled metrics collection failed:
  Invalid field name(s) for model ResourceMetrics: 'project_metrics_count'.
```

**cleanup-artifacts-webhook (03:00 UTC):**
```
ERROR 2026-02-08 03:00:08,282 views Scheduled artifact cleanup failed:
  'dict' object has no attribute 'endswith'
```

### Step 3: Root Cause Analysis

---

## Bug 1: collect-resource-metrics

**Error:** `Invalid field name(s) for model ResourceMetrics: 'project_metrics_count'`

**File:** `ml_platform/management/commands/collect_resource_metrics.py`

**Root cause:** The `_collect_project_metrics()` method adds a bookkeeping counter
to the shared `data` dictionary:

- Line 306: `data['project_metrics_count'] = 0` (early return path)
- Line 425: `data['project_metrics_count'] = count` (normal path)

Later, all keys from `data` are passed to `ResourceMetrics.objects.update_or_create()`:

```python
# Line 124-126
obj, created = ResourceMetrics.objects.update_or_create(
    date=target_date,
    defaults={k: v for k, v in data.items() if k != 'date'}
)
```

Django rejects `project_metrics_count` because the `ResourceMetrics` model
(defined in `ml_platform/models.py:940-987`) has no such field.

**Fix:** Remove `project_metrics_count` from the `data` dict. Use a local variable
or exclude it from the `defaults` comprehension.

---

## Bug 2: cleanup-gcs-artifacts

**Error:** `'dict' object has no attribute 'endswith'`

**File:** `ml_platform/management/commands/cleanup_gcs_artifacts.py`

**Root cause:** The `handle()` method returns a **dict** (lines 163-168):

```python
return {
    'deleted': deleted_count,
    'preserved': preserved_count,
    'bytes_freed': total_bytes_freed,
    'errors': errors,
}
```

Django's `BaseCommand.execute()` (`django/core/management/base.py:458-467`)
checks `if output:` on the return value. A non-empty dict is truthy, so Django
calls `self.stdout.write(output)`. Inside `OutputWrapper.write()`, line 177
calls `msg.endswith(ending)` on the dict, causing the `AttributeError`.

This was non-obvious because:
- The `.endswith()` call is inside Django's internals, not in project code
- The webhook view catches bare `Exception` without logging the traceback
- The error message gives no file/line context

**Fix:** Don't return a dict from `handle()`. Either return `None` or a string summary.

---

## Additional Issue: Poor Error Logging in Webhook Views

Both webhook views (`ml_platform/views.py:836-911`) catch `Exception` and log only
`str(e)` without the traceback:

```python
except Exception as e:
    logger.error(f'Scheduled artifact cleanup failed: {e}')
```

This made the cleanup bug especially hard to diagnose. The fix is to include
`exc_info=True` in the logger call to capture the full traceback.

## Fixes Applied

1. **collect_resource_metrics.py**: Removed `data['project_metrics_count']` from both
   code paths (lines 306, 425). `_collect_project_metrics()` now returns the count,
   captured via a local variable in `handle()` for the dry-run log.
2. **cleanup_gcs_artifacts.py**: Removed `return {...}` from `handle()`. The webhook
   view already handles `None` gracefully (`result if isinstance(result, dict) else {}`).
3. **views.py**: Added `exc_info=True` to `logger.error()` in both webhook views
   for full tracebacks on future failures.

## Verification

### Local dry-run tests (2026-02-08)

**collect_resource_metrics --dry-run** — completed without field errors:
```
Collecting resource metrics for 2026-02-08...
  BQ: 8 tables, 18,090,867,981 bytes
  BQ jobs: 7 completed, 0 failed
  Cloud Run: 2 services, 2 active
  DB: 13,620,015 bytes, 20 tables
  GCS: 8 buckets, 18,460,206,211 bytes
  ETL: 4 completed, 0 failed
  Cloud Run requests: 4 across 1 serving endpoints
  Project metrics: 1 projects updated
  GPU: 1.4h, 1 completed, 0 failed, 0 running
DRY RUN - no changes saved.
  Project metrics rows: 1
```

**cleanup_gcs_artifacts --dry-run** — completed without AttributeError:
```
GCS Artifact Cleanup (cutoff: 2026-02-01, 7 days)
DRY RUN - no files will be deleted.
Found 17 terminal training run(s) older than 7 days.
  PRESERVE: TR-41 #30 (completed) - registered model
  ...
Would delete artifacts for 4 run(s), preserved 13 registered model(s), freed ~9.9 MB
```

### Production Cloud Scheduler runs (2026-02-08, post-deploy)

Both jobs triggered manually via `gcloud scheduler jobs run` after redeployment:

| Job | Triggered | Status |
|-----|-----------|--------|
| `collect-resource-metrics` | 2026-02-08 ~15:05 UTC | **Success** (confirmed via scheduler dashboard) |
| `cleanup-gcs-artifacts` | 2026-02-08 ~15:10 UTC | **Success** (`status: {}`, no error code) |

---

## Bug 3: Stale GPU Counts — Scheduler Timing (2026-02-09)

**Symptom:** The "Training Jobs (30d)" chart on the starting page under-reported failed
training jobs for Feb 6, Feb 8, and Feb 9.

### Data Comparison (ResourceMetrics vs TrainingRun ground truth)

| Date | Chart completed | Chart failed | Real completed | Real failed | Status |
|------|:-:|:-:|:-:|:-:|--------|
| Feb 6 | 0 | **1** | 0 | **2** | WRONG — missing 1 failed |
| Feb 8 | 1 | **0** | 1 | **3** | WRONG — missing 3 failed |
| Feb 9 | 0 | **0** | 0 | **1** | WRONG — missing 1 failed |

### Root Cause

The webhook (`views.py:854`) called `collect_resource_metrics` without a `--date` argument,
so the command defaulted to `target_date = timezone.now().date()` (today). The scheduler
runs at **02:00 UTC** — at that hour the day has barely started, so training runs completing
later in the day are permanently missed.

The data is **never retroactively updated** because the next day's scheduler run uses the
next day's date. This affected every collection point:

| Collection | Ran at (UTC) | target_date | Missed runs |
|------------|-------------|-------------|-------------|
| Backfill | Feb 6 10:46 | Feb 6 | TR-51 (failed 15:24) |
| Manual re-run | Feb 8 15:05 | Feb 8 | TR-56 (17:09), TR-57 (19:26), TR-58 (21:27) |
| First scheduled | Feb 9 02:00 | Feb 9 | TR-59 (failed 09:58) |

### Fix Applied

**File:** `ml_platform/views.py` — `scheduler_collect_metrics_webhook()`

The webhook now passes `--date` with **yesterday's date** to the command. At 02:00 UTC,
the previous day is fully complete so all training runs have their final `completed_at`
timestamps:

```python
yesterday = (timezone.now() - timedelta(days=1)).date()
call_command('collect_resource_metrics', '--date', yesterday.isoformat(), stdout=output)
```

The management command default (`timezone.now().date()`) is unchanged for manual usage.

### Data Repair

Re-collected the 3 stale dates manually via `collect_resource_metrics --date`:

```
$ python manage.py collect_resource_metrics --date 2026-02-06
  GPU: 0.2h, 0 completed, 2 failed, 0 running     # was: 0c/1f

$ python manage.py collect_resource_metrics --date 2026-02-08
  GPU: 3.0h, 1 completed, 3 failed, 0 running      # was: 1c/0f

$ python manage.py collect_resource_metrics --date 2026-02-09
  GPU: 0.6h, 0 completed, 1 failed, 0 running      # was: 0c/0f
```

All 13 active days in the 30-day window now match ground truth.
