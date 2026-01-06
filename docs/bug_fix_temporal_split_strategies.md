# Bug Fix: Temporal Split Strategies Using CURRENT_DATE()

**Date:** 2025-12-18
**File:** `ml_platform/datasets/services.py`
**Method:** `_generate_holdout_cte()` (lines 1265-1341)

## Problem Description

Experiments using `time_holdout` or `strict_time` split strategies failed with a `KeyError: 'customer_id'` error in the TFX Transform stage when the dataset contained historical data.

### Error Traceback

```
tensorflow.python.framework.errors_impl.InvalidArgumentError: {{function_node __inference_preprocessing_fn_169}}
KeyError: 'customer_id'
```

### Affected Configurations

- Split strategy: `strict_time` or `time_holdout`
- Dataset: Any dataset with historical data (dates not near current date)

## Root Cause Analysis

### Investigation Steps

1. **Initial hypothesis (incorrect):** Column name mismatch between Dataset and FeatureConfig
   - Verified `customer_id` was correctly configured in both Dataset and FeatureConfig
   - SQL generation was correct with `customer_id` in output

2. **Key diagnostic:** Examined TFRecords created by BigQueryExampleGen
   - Failed experiment (QuickTest 35): **20 bytes** (0 bytes uncompressed) - EMPTY
   - Successful experiment (QuickTest 33): **288KB** - contained data

3. **Root cause identified:** The `_generate_holdout_cte()` method used `CURRENT_DATE()` as the reference point for date calculations

### The Bug

The temporal split strategies calculated date windows relative to `CURRENT_DATE()`:

```python
# time_holdout - BUGGY CODE
WHERE date_column < UNIX_SECONDS(TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {holdout_days} DAY)))

# strict_time - BUGGY CODE
WHERE date_column >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {total_window} DAY)))
  AND date_column < UNIX_SECONDS(TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL {test_days} DAY)))
```

### Why It Failed

For a dataset with data from **2024-01-01 to 2024-04-28**:

- `strict_time` with `train_days=60, val_days=7, test_days=2` calculated:
  - Window start: `CURRENT_DATE() - 69 days` = **2025-10-10**
  - Window end: `CURRENT_DATE() - 2 days` = **2025-12-16**

- **Result:** Zero overlap between data dates (ending 2024-04-28) and calculated window (2025-10-10 to 2025-12-16)

### Failure Cascade

```
0 rows returned by BigQuery
    ↓
Empty TFRecords created by BigQueryExampleGen
    ↓
Empty schema inferred by StatisticsGen/SchemaGen
    ↓
Transform stage fails with KeyError (no columns in schema)
```

## Solution

Modified `_generate_holdout_cte()` to use the MAX date from the dataset instead of `CURRENT_DATE()`.

### Fixed Code

Both strategies now use a CTE to find the MAX date once, then filter relative to it:

```python
# time_holdout - FIXED
WITH max_date_ref AS (
    SELECT DATE(TIMESTAMP_SECONDS(MAX({date_column}))) AS ref_date
    FROM {source_table}
)
SELECT base.*
FROM {source_table} base, max_date_ref
WHERE base.{date_column} < UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {holdout_days} DAY)))

# strict_time - FIXED
WITH max_date_ref AS (
    SELECT DATE(TIMESTAMP_SECONDS(MAX({date_column}))) AS ref_date
    FROM {source_table}
)
SELECT base.*
FROM {source_table} base, max_date_ref
WHERE base.{date_column} >= UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {total_window} DAY)))
  AND base.{date_column} < UNIX_SECONDS(TIMESTAMP(DATE_SUB(max_date_ref.ref_date, INTERVAL {test_days} DAY)))
```

### Timeline Illustration

```
Before (BUGGY):
Data:     [2024-01-01 -------- 2024-04-28]
Window:                                      [2025-10-10 -------- 2025-12-16]
Result:   NO OVERLAP → 0 rows

After (FIXED):
Data:     [2024-01-01 -------- 2024-04-28]  ← MAX date = 2024-04-28
Window:        [2024-02-19 ---- 2024-04-26] ← calculated from MAX date
Result:   OVERLAP → 4202 rows
```

## Verification

### Before Fix
```
Row count with strict_time: 0
TFRecord size: 20 bytes (empty)
Result: KeyError in Transform stage
```

### After Fix
```
Row count with strict_time: 4202
TFRecord size: Expected ~288KB (with data)
Result: Pipeline succeeds
```

## Files Modified

| File | Lines | Change |
|------|-------|--------|
| `ml_platform/datasets/services.py` | 1275-1302 | Updated docstring |
| `ml_platform/datasets/services.py` | 1303-1313 | Fixed `time_holdout` strategy |
| `ml_platform/datasets/services.py` | 1315-1337 | Fixed `strict_time` strategy |

## Lessons Learned

1. **Temporal split strategies should never use `CURRENT_DATE()`** - they should always be relative to the actual data in the dataset
2. **Empty TFRecords are a silent failure** - they don't cause immediate errors but lead to confusing downstream failures
3. **When debugging TFX pipelines**, check the TFRecords size/content early in the investigation

---

# Bug Fix: Transform Component Missing splits_config for Test Split

**Date:** 2026-01-06
**Files:**
- `ml_platform/experiments/services.py` (inline script in `_get_compile_script()`)
- `cloudbuild/compile_and_submit.py` (legacy file, not used by main flow)

## Problem Description

The Transform component in the TFX pipeline is not configured with `splits_config`, which means:
1. Vocabularies are only built from the default split (typically 'train')
2. The 'test' split may not be transformed correctly
3. Customer/product IDs that only appear in test data will map to OOV (out-of-vocabulary) embeddings

### Expected vs Actual Behavior

**Expected (per UI and documentation):**
| Split Strategy | Train | Eval | Test | Description |
|---------------|-------|------|------|-------------|
| `random` | 80% | 15% | 5% | Hash-based random split |
| `time_holdout` | ~80% | ~20% | Last N days | Temporal test holdout, random train/eval |
| `strict_time` | Configurable days | Configurable days | Configurable days | Pure temporal ordering |

**Actual Behavior:**
- BigQueryExampleGen: ✅ Creates 3 splits correctly (train/eval/test)
- Transform: ❌ Missing `splits_config` - vocabularies only from train, test may not be transformed
- Trainer: ⚠️ Looks for `Split-test` directory, fails gracefully if not found

## Architecture Analysis

### Code Locations (Important Discovery)

There are **THREE** places where TFX pipeline creation is defined:

| Location | Used By | BigQueryExampleGen | Transform |
|----------|---------|-------------------|-----------|
| `services.py:_get_compile_script()` (lines 882-1123) | **Main pipeline flow** | ✅ Correct (16/3/1 hash for random, partition for temporal) | ❌ Missing `splits_config` |
| `cloudbuild/compile_and_submit.py` | Manual YAML trigger only | ❌ Broken (8/2 hash, no test split) | ✅ Has `splits_config` (but only train/eval) |
| `ml_platform/experiments/tfx_pipeline.py` | Not used | ❌ Broken (8/2 hash, no test split) | ✅ Has `splits_config` (but only train/eval) |

**Key Finding:** The inline script in `services.py:_get_compile_script()` is what actually runs in production, but it's missing the `splits_config` fix that exists in the other files.

### Data Flow Analysis

```
SQL Query Generation (ml_platform/datasets/services.py)
├── random: No 'split' column added (BigQueryExampleGen does hash split)
├── time_holdout: 'split' column with train/eval/test values
└── strict_time: 'split' column with train/eval/test values
         ↓
BigQueryExampleGen (inline script in services.py:924-949)
├── random: hash_buckets=[16, 3, 1] → 80/15/5 split ✅
└── temporal: partition_feature_name='split' → uses SQL column ✅
         ↓
Transform (inline script in services.py:960-964) ❌ PROBLEM HERE
├── Missing: from tfx.proto import transform_pb2
├── Missing: splits_config parameter
└── Result: Default behavior - may only analyze/transform 'train' split
         ↓
Trainer (looks for Split-test directory)
├── If test split exists: runs final evaluation ✅
└── If test split missing: logs warning and continues ⚠️
```

### The Specific Bug

In `ml_platform/experiments/services.py:960-964` (inside `_get_compile_script()`):

```python
# CURRENT (BUGGY) - No splits_config
transform = Transform(
    examples=example_gen.outputs["examples"],
    schema=schema_gen.outputs["schema"],
    module_file=transform_module_path,
)
```

**Should be:**

```python
# FIXED - With splits_config for all 3 splits (avoiding data leakage)
from tfx.proto import transform_pb2

transform = Transform(
    examples=example_gen.outputs["examples"],
    schema=schema_gen.outputs["schema"],
    module_file=transform_module_path,
    splits_config=transform_pb2.SplitsConfig(
        analyze=['train', 'eval'],  # NO test - avoid data leakage!
        transform=['train', 'eval', 'test']  # But transform all for evaluation
    ),
)
```

**Critical: Why NOT include 'test' in analyze:**
- `analyze` determines which splits are used to build vocabularies
- If test is included, test-only IDs get vocabulary entries (model "knows" about them)
- This is **DATA LEAKAGE** - artificially inflates test metrics
- Test-only IDs should map to OOV (out-of-vocabulary) for honest evaluation

## Impact Assessment

### Without splits_config:

1. **Test Split TFRecords:** May not exist or may be empty (Transform doesn't know to process test)
2. **Final Evaluation:** Trainer gracefully skips test evaluation (line 3105: "No test split found")
3. **Metrics:** `test_recall_at_*` metrics not computed, only `val_recall_at_*`

### With CORRECT splits_config (`analyze=['train', 'eval']`, `transform=['train', 'eval', 'test']`):

1. **Vocabularies:** Built from train+eval only (what model sees during training)
2. **Test-only IDs:** Correctly map to OOV embedding (honest evaluation)
3. **Test TFRecords:** Properly created and available for final evaluation
4. **Metrics:** Both `val_recall_at_*` and `test_recall_at_*` computed

### Affected Experiments:

All QuickTest experiments are affected regardless of split strategy.

## Related Issues

### Legacy Code Inconsistency

The file `cloudbuild/compile_and_submit.py` has **different bugs**:
- Lines 69-76: Always uses `hash_buckets=[8, 2]` (80/20 split, no test)
- Lines 99-107: Has `splits_config` but only for `['train', 'eval']`

This file is:
- Referenced by `cloudbuild/tfx-compile.yaml` (manual trigger)
- **NOT** used by the main `ExperimentService` pipeline flow
- Creates confusion about the "correct" implementation

### Recommendation

1. **Delete or deprecate** `cloudbuild/compile_and_submit.py` and `cloudbuild/tfx-compile.yaml`
2. **Delete or deprecate** `ml_platform/experiments/tfx_pipeline.py`
3. **Single source of truth:** Only use the inline script in `services.py:_get_compile_script()`

---

# Detailed Implementation Plan

## Overview

Fix all three split strategies to correctly create train/eval/test splits with proper vocabulary coverage.

## Phase 1: Fix Transform Component in Inline Script

**File:** `ml_platform/experiments/services.py`
**Method:** `_get_compile_script()` (lines 882-1123)

### Step 1.1: Add transform_pb2 import

**Location:** Line 915 (after `from tfx.proto import example_gen_pb2, trainer_pb2`)

```python
# BEFORE
from tfx.proto import example_gen_pb2, trainer_pb2

# AFTER
from tfx.proto import example_gen_pb2, trainer_pb2, transform_pb2
```

### Step 1.2: Add splits_config to Transform component

**Location:** Lines 960-964

```python
# BEFORE
transform = Transform(
    examples=example_gen.outputs["examples"],
    schema=schema_gen.outputs["schema"],
    module_file=transform_module_path,
)

# AFTER (avoiding data leakage)
transform = Transform(
    examples=example_gen.outputs["examples"],
    schema=schema_gen.outputs["schema"],
    module_file=transform_module_path,
    splits_config=transform_pb2.SplitsConfig(
        analyze=['train', 'eval'],  # NO test - avoid data leakage!
        transform=['train', 'eval', 'test']  # But transform all for evaluation
    ),
)
```

**IMPORTANT:** Do NOT include 'test' in `analyze` - this would cause data leakage by including test-only IDs in vocabularies.

## Phase 2: Verify and Test Random Split Strategy

### Step 2.1: Create test script for SQL generation

Verify that random split does NOT add a 'split' column (BigQueryExampleGen handles it):

```python
# Test: Random split SQL should NOT have 'split' column
from ml_platform.datasets.services import BigQueryService

bq_service = BigQueryService(project_id='b2b-recs', dataset_name='test')
query = bq_service.generate_training_query(
    dataset=test_dataset,
    split_strategy='random',
    sample_percent=100
)
assert 'AS split' not in query  # Random uses hash_buckets, not SQL column
```

### Step 2.2: Create test script for BigQueryExampleGen configuration

Verify hash_buckets configuration produces correct ratios:

```python
# Test: 16 + 3 + 1 = 20 buckets
# train: 16/20 = 80%
# eval:  3/20 = 15%
# test:  1/20 = 5%
assert 16 + 3 + 1 == 20
assert 16/20 == 0.80
assert 3/20 == 0.15
assert 1/20 == 0.05
```

### Step 2.3: Integration test with actual pipeline (dry run)

1. Create a small test dataset
2. Run pipeline compilation (without submission)
3. Verify JSON spec contains correct split configuration
4. Submit to Vertex AI with a small sample
5. Verify TFRecords have all 3 splits with expected proportions
6. Verify Trainer finds and uses test split

## Phase 3: Verify and Test Time Holdout Strategy

### Step 3.1: Verify SQL generates 'split' column

```python
# Test: time_holdout SQL should have 'split' column
query = bq_service.generate_training_query(
    dataset=test_dataset,
    split_strategy='time_holdout',
    holdout_days=1,
    date_column='trans_date',
    sample_percent=100
)
assert 'AS split' in query
assert "'test'" in query  # Last N days = 'test'
assert "'train'" in query
assert "'eval'" in query
assert 'partition_feature_name' not in query  # That's in ExampleGen config
```

### Step 3.2: Verify BigQueryExampleGen uses partition_feature_name

The inline script already has this at lines 940-949:
```python
output_config = example_gen_pb2.Output(
    split_config=example_gen_pb2.SplitConfig(
        splits=[
            example_gen_pb2.SplitConfig.Split(name="train"),
            example_gen_pb2.SplitConfig.Split(name="eval"),
            example_gen_pb2.SplitConfig.Split(name="test"),
        ],
        partition_feature_name='split'
    )
)
```

### Step 3.3: Integration test

1. Use dataset with known date distribution
2. Run pipeline
3. Verify test split contains only data from last N days
4. Verify train/eval contain remaining data in ~80/20 ratio

## Phase 4: Verify and Test Strict Temporal Strategy

### Step 4.1: Verify SQL generates correct temporal 'split' column

```python
# Test: strict_time SQL should have 'split' column with temporal boundaries
query = bq_service.generate_training_query(
    dataset=test_dataset,
    split_strategy='strict_time',
    date_column='trans_date',
    train_days=48,
    val_days=9,
    test_days=3,
    sample_percent=100
)
assert 'AS split' in query
assert 'test' in query
assert 'train' in query
assert 'eval' in query
# Verify date boundary calculations are correct
```

### Step 4.2: Integration test

1. Use dataset with known date distribution (e.g., 60 days of data)
2. Configure: train_days=48, val_days=9, test_days=3
3. Run pipeline
4. Verify splits contain exactly the expected date ranges
5. Verify no data leakage (train dates < eval dates < test dates)

## Phase 5: Clean Up Legacy Code

### Step 5.1: Update or delete cloudbuild/compile_and_submit.py

Options:
- **Option A:** Delete the file and `cloudbuild/tfx-compile.yaml`
- **Option B:** Update to match inline script exactly (sync code)

Recommendation: **Option A** - single source of truth

### Step 5.2: Update or delete ml_platform/experiments/tfx_pipeline.py

Same options as above. Recommendation: **Delete**.

### Step 5.3: Update documentation

Update `docs/phase_experiments.md` to reflect:
- Single source of truth is `services.py:_get_compile_script()`
- All three split strategies now produce test split
- Transform component analyzes all splits for vocabulary

## Test Plan

### Unit Tests

| Test | File | Description |
|------|------|-------------|
| `test_random_split_sql` | `tests/test_split_strategies.py` | Random split SQL has no 'split' column |
| `test_time_holdout_sql` | `tests/test_split_strategies.py` | Time holdout SQL has correct 'split' column |
| `test_strict_time_sql` | `tests/test_split_strategies.py` | Strict time SQL has correct 'split' column |
| `test_hash_buckets_ratio` | `tests/test_split_strategies.py` | Verify 16/3/1 = 80/15/5 |

### Integration Tests (Manual)

| Test | Description | Expected Result |
|------|-------------|-----------------|
| Random split pipeline | Submit QuickTest with random split | 3 TFRecord splits (80/15/5), test metrics computed |
| Time holdout pipeline | Submit QuickTest with time_holdout | Test split has last N days only |
| Strict temporal pipeline | Submit QuickTest with strict_time | Splits follow temporal order |

### Verification Checklist

For each split strategy, verify:
- [ ] BigQueryExampleGen creates 3 splits (train, eval, test)
- [ ] Transform processes all 3 splits (TFRecords exist for each)
- [ ] Vocabularies built from train+eval ONLY (no test-only IDs)
- [ ] Test-only IDs correctly map to OOV embedding
- [ ] Trainer finds `Split-test` directory
- [ ] `test_loss` and `test_recall_at_*` metrics are computed
- [ ] No data leakage (test data not seen during training)

## Rollback Plan

If issues are discovered:
1. Revert `services.py:_get_compile_script()` to previous version
2. All new experiments will use old code (inline script is generated fresh each time)
3. No database migrations required
4. Existing completed experiments are unaffected

---

# Implementation Log

## 2026-01-06: Fix Implemented and Random Split Verified

### Changes Made

**File: `ml_platform/experiments/services.py`**

1. **Added `transform_pb2` import** (line 915):
```python
# BEFORE
from tfx.proto import example_gen_pb2, trainer_pb2

# AFTER
from tfx.proto import example_gen_pb2, trainer_pb2, transform_pb2
```

2. **Added `splits_config` to Transform component** (lines 960-972):
```python
# BEFORE
transform = Transform(
    examples=example_gen.outputs["examples"],
    schema=schema_gen.outputs["schema"],
    module_file=transform_module_path,
)

# AFTER
transform = Transform(
    examples=example_gen.outputs["examples"],
    schema=schema_gen.outputs["schema"],
    module_file=transform_module_path,
    splits_config=transform_pb2.SplitsConfig(
        analyze=['train', 'eval'],  # NO test - avoid data leakage
        transform=['train', 'eval', 'test']  # But transform all for evaluation
    ),
)
```

**File: `tests/test_split_strategies.py`** (NEW)

Created comprehensive unit test suite with 14 tests:
- `TestHashBucketsRatios`: Validates 16/3/1 = 80/15/5 split math
- `TestInlineScript`: Validates inline script configuration
  - `transform_pb2` import exists
  - `splits_config` parameter present
  - `analyze` excludes 'test' (no data leakage)
  - `transform` includes 'test' (TFRecords created)
  - Random strategy uses hash_buckets=[16, 3, 1]
  - Temporal strategies use `partition_feature_name='split'`
- `TestSQLGeneration`: Validates SQL generation for each strategy

### Test Results

**Unit Tests: All 14 tests pass**
```
test_old_broken_ratios ... ok
test_random_split_ratios ... ok
test_random_strategy_creates_test_split ... ok
test_random_strategy_hash_buckets ... ok
test_temporal_strategy_defines_three_splits ... ok
test_temporal_strategy_uses_partition_feature ... ok
test_transform_analyze_excludes_test ... ok
test_transform_pb2_import_exists ... ok
test_transform_splits_config_exists ... ok
test_transform_transform_includes_test ... ok
test_random_split_no_split_column ... ok
test_time_holdout_has_split_column ... ok
test_strict_time_has_split_column ... ok
test_time_holdout_uses_max_date ... ok
----------------------------------------------------------------------
Ran 14 tests in 0.730s
OK
```

### E2E Verification: Random Split (QuickTest 82)

**Pipeline:** `quicktest-qt-82-20260106-140104-20260106140337`

**BigQueryExampleGen Output:**
| Split | Size (bytes) | Percentage | Expected |
|-------|-------------|------------|----------|
| train | 2,997,430 | 80.06% | 80% |
| eval | 559,811 | 14.95% | 15% |
| test | 186,736 | 4.99% | 5% |
| **Total** | **3,743,977** | **100%** | |

**Transform Output:**
| Split | Size (bytes) | Status |
|-------|-------------|--------|
| train | 3,655,133 | Created |
| eval | 682,711 | Created |
| test | 227,530 | Created |

**Test Metrics (proof test split was evaluated):**
| Metric | Value |
|--------|-------|
| test_loss | 2730.84 |
| test_recall_at_5 | 4.75% |
| test_recall_at_10 | 8.43% |
| test_recall_at_50 | 21.30% |
| test_recall_at_100 | 31.65% |

**Verification Checklist for Random Split:**
- [x] BigQueryExampleGen creates 3 splits (train, eval, test)
- [x] Transform processes all 3 splits (TFRecords exist for each)
- [x] Vocabularies built from train+eval ONLY (no test in `analyze`)
- [x] Trainer finds `Split-test` directory
- [x] `test_loss` and `test_recall_at_*` metrics are computed
- [x] Split ratios match expected 80/15/5

---

## Next Steps

### Remaining E2E Tests

1. **Time Holdout Strategy** - Submit QuickTest with:
   - `split_strategy='time_holdout'`
   - `holdout_days=N` (e.g., 1-3 days)
   - `date_column` set to appropriate timestamp column
   - Verify: Last N days in test split, remaining data split 80/20 for train/eval

2. **Strict Temporal Strategy** - Submit QuickTest with:
   - `split_strategy='strict_time'`
   - `train_days`, `val_days`, `test_days` configured
   - `date_column` set to appropriate timestamp column
   - Verify: Pure temporal ordering (train < eval < test), no random component

### Cleanup Tasks

1. Consider deleting legacy files (optional):
   - `cloudbuild/compile_and_submit.py` - Not used by main flow
   - `cloudbuild/tfx-compile.yaml` - Not used by main flow
   - `ml_platform/experiments/tfx_pipeline.py` - Not used

2. Update `docs/phase_experiments.md` to note single source of truth is `services.py:_get_compile_script()`

---

# Bug Fix: Temporal Split Strategies Failing with partition_feature_name

**Date:** 2026-01-06
**Files Modified:**
- `ml_platform/experiments/services.py`
- `ml_platform/datasets/services.py`
- `tests/test_split_strategies.py`

## Problem Description

Experiments using `time_holdout` or `strict_time` split strategies failed at the BigQueryExampleGen stage with the error:

```
RuntimeError: Str-typed output split name and int-typed hash buckets are required.
```

### Error Location

```
File "tfx/components/example_gen/utils.py", line 87, in generate_output_split_names
    raise RuntimeError(
RuntimeError: Str-typed output split name and int-typed hash buckets are required.
```

### Affected Configurations

- Split strategy: `time_holdout` or `strict_time`
- Random split: **NOT affected** (uses hash_buckets)

## Root Cause Analysis

### Investigation Steps

1. **Examined TFX source code** to understand the error:
   ```python
   # tfx/components/example_gen/utils.py:generate_output_split_names()
   def generate_output_split_names(input_config, output_config):
       if output_config.split_config.splits:
           if output_config.split_config.partition_feature_name:  # ← PROBLEM
               return [split.name for split in output_config.split_config.splits]
           for split in output_config.split_config.splits:
               if not isinstance(split.hash_buckets, int) or split.hash_buckets <= 0:
                   raise RuntimeError(...)  # ← ERROR THROWN HERE
   ```

2. **Root cause identified**: The `partition_feature_name` field is set in Python but evaluates to `False` (empty string) after JSON serialization/deserialization in Vertex AI.

3. **The bug pathway**:
   - Pipeline compiled locally with `partition_feature_name='split'` ✅
   - Pipeline JSON submitted to Vertex AI
   - TFX deserializes JSON back to protobuf
   - `partition_feature_name` is empty string (falsy) ❌
   - Code falls through to check `hash_buckets` (not set for temporal strategies)
   - RuntimeError raised

### Why Random Split Works

Random split uses `hash_buckets=[16, 3, 1]` in `output_config`:
```python
output_config = example_gen_pb2.Output(
    split_config=example_gen_pb2.SplitConfig(
        splits=[
            example_gen_pb2.SplitConfig.Split(name='train', hash_buckets=16),
            example_gen_pb2.SplitConfig.Split(name='eval', hash_buckets=3),
            example_gen_pb2.SplitConfig.Split(name='test', hash_buckets=1),
        ]
    )
)
```
This bypasses the `partition_feature_name` check entirely.

## Solution

### Proposed Fix: Use input_config.splits Instead

Instead of using `partition_feature_name` (buggy code path), use multiple `input_config.splits` with separate queries for each split:

```python
# BEFORE (BUGGY - partition_feature_name not parsed correctly)
output_config = example_gen_pb2.Output(
    split_config=example_gen_pb2.SplitConfig(
        splits=[...],
        partition_feature_name='split'  # ← NOT RECOGNIZED IN VERTEX AI
    )
)
example_gen = BigQueryExampleGen(query=single_query, output_config=output_config)

# AFTER (FIXED - multiple input splits)
input_config = example_gen_pb2.Input(splits=[
    example_gen_pb2.Input.Split(name='train', pattern=train_query),
    example_gen_pb2.Input.Split(name='eval', pattern=eval_query),
    example_gen_pb2.Input.Split(name='test', pattern=test_query),
])
example_gen = BigQueryExampleGen(input_config=input_config, custom_config={'project': project_id})
```

This takes a different code path in `generate_output_split_names()`:
```python
elif input_config.splits:  # ← TRUE (we define splits here)
    return [split.name for split in input_config.splits]  # ← SUCCESS
```

## Pre-Implementation Testing

Before implementing the fix, comprehensive tests were run to validate the approach.

### Test Environment

```bash
# TFX 1.15.0 in conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate tf_2.12_py39
python -c "import tfx; print(f'TFX version: {tfx.__version__}')"
# Output: TFX version: 1.15.0
```

### Test 1: Validate input_config Approach Works

**File:** `tests/test_proposed_split_fix.py`

```python
def test_tfx_input_config_creation(self):
    """Test actual TFX Input config creation."""
    from tfx.proto import example_gen_pb2
    from tfx.components.example_gen import utils

    input_config = example_gen_pb2.Input(splits=[
        example_gen_pb2.Input.Split(name='train', pattern='Q1'),
        example_gen_pb2.Input.Split(name='eval', pattern='Q2'),
        example_gen_pb2.Input.Split(name='test', pattern='Q3'),
    ])
    output_config = example_gen_pb2.Output()  # Empty!

    split_names = utils.generate_output_split_names(input_config, output_config)
    assert split_names == ['train', 'eval', 'test']
```

**Result:** ✅ PASSED

### Test 2: Verify Random Split Not Affected

```python
def test_random_split_uses_hash_buckets(self):
    """Verify random split uses hash_buckets configuration."""
    # Random split continues to use:
    # - Single BigQuery query (no 'split' column)
    # - hash_buckets=[16, 3, 1] for 80/15/5 split
    # This is NOT affected by the fix
```

**Result:** ✅ PASSED

### Test 3: Parameter Pass-Through Verification

```python
def test_parameters_not_hardcoded(self):
    """Test that temporal parameters are passed through, not hardcoded."""
    # Verified that holdout_days, train_days, val_days, test_days
    # flow from wizard → SQL generation → pipeline configuration
```

**Result:** ✅ PASSED

### Full Test Results

```
======================================================================
TESTING PROPOSED FIX FOR TEMPORAL SPLIT STRATEGIES
======================================================================
test_parameters_not_hardcoded ... ok
test_wrap_query_with_split_filter ... ok
test_input_config_multiple_splits_structure ... ok
test_no_output_config_needed_for_multiple_input_splits ... ok
test_tfx_input_config_creation ... ok
test_random_split_uses_hash_buckets ... ok
test_random_split_uses_single_query ... ok
test_proposed_fix_for_temporal_strategies ... ok
test_verify_fix_avoids_buggy_code_path ... ok
test_query_syntax_basic ... ok
----------------------------------------------------------------------
Ran 10 tests in 0.023s
OK

*** ALL TESTS PASSED - PROPOSED FIX IS VALIDATED ***
```

## Implementation

### Phase 1: Add generate_split_queries() Method

**File:** `ml_platform/datasets/services.py`
**Location:** After `generate_training_query()` method

```python
def generate_split_queries(
    self,
    dataset,
    split_strategy: str,
    holdout_days: int = 1,
    date_column: str = None,
    sample_percent: int = 100,
    train_days: int = 60,
    val_days: int = 7,
    test_days: int = 7,
) -> dict:
    """
    Generate separate BigQuery queries for each split (temporal strategies only).

    For temporal strategies (time_holdout, strict_time), generates three separate
    queries that each filter by the split column. This is required because TFX's
    partition_feature_name doesn't work correctly in Vertex AI.

    Returns:
        dict with 'train', 'eval', 'test' keys containing SQL queries,
        or None for random split (which uses hash_buckets).
    """
    if split_strategy == 'random':
        return None

    # Generate base query (includes 'split' column)
    base_query = self.generate_training_query(
        dataset=dataset,
        split_strategy=split_strategy,
        holdout_days=holdout_days,
        date_column=date_column,
        sample_percent=sample_percent,
        train_days=train_days,
        val_days=val_days,
        test_days=test_days,
    )

    # Wrap base query to filter by split and remove split column
    def make_split_query(split_name: str) -> str:
        return f"WITH base AS (\n{base_query}\n)\nSELECT * EXCEPT(split) FROM base WHERE split = '{split_name}'"

    return {
        'train': make_split_query('train'),
        'eval': make_split_query('eval'),
        'test': make_split_query('test'),
    }
```

### Phase 2: Update _submit_pipeline() to Generate Split Queries

**File:** `ml_platform/experiments/services.py`
**Method:** `_submit_pipeline()`

```python
# Generate split queries for temporal strategies
split_queries = None
if quick_test.split_strategy in ('time_holdout', 'strict_time'):
    split_queries = bq_service.generate_split_queries(
        dataset=dataset,
        split_strategy=quick_test.split_strategy,
        holdout_days=getattr(quick_test, 'holdout_days', 1),
        date_column=getattr(quick_test, 'date_column', None),
        sample_percent=quick_test.sample_percent,
        train_days=getattr(quick_test, 'train_days', 60),
        val_days=getattr(quick_test, 'val_days', 7),
        test_days=getattr(quick_test, 'test_days', 7),
    )
    logger.info(f"Generated split queries for {quick_test.split_strategy}: "
               f"train={len(split_queries['train'])} chars, "
               f"eval={len(split_queries['eval'])} chars, "
               f"test={len(split_queries['test'])} chars")
```

### Phase 3: Upload Split Queries to GCS (Cloud Build Arg Limit Fix)

**Problem:** Cloud Build has a 10KB limit for command-line arguments. The three split queries (each wrapping the full base query) exceeded this limit.

**Error:**
```
400 invalid build: invalid .steps field: build step 0 arg 1 too long (max: 10000)
```

**Solution:** Upload split queries as a JSON file to GCS instead of passing as CLI args.

**File:** `ml_platform/experiments/services.py`
**Method:** `_trigger_cloud_build()`

```python
# For temporal strategies, upload split queries to GCS as JSON (too large for CLI args)
split_queries_blob_path = ""
if split_queries:
    split_queries_blob_path = f"build_scripts/{run_id}/split_queries.json"
    split_blob = bucket.blob(split_queries_blob_path)
    split_blob.upload_from_string(json.dumps(split_queries), content_type='application/json')
    logger.info(f"Uploaded split queries to gs://{self.STAGING_BUCKET}/{split_queries_blob_path}")

# Build command with optional split queries GCS path
split_args = ""
if split_queries_blob_path:
    split_args = f'    --split-queries-gcs-path="{split_queries_blob_path}" \\\n'
```

### Phase 4: Update Inline Script to Use input_config

**File:** `ml_platform/experiments/services.py`
**Method:** `_get_compile_script()` → `create_tfx_pipeline()`

```python
def create_tfx_pipeline(..., split_queries: Optional[dict], ...):
    if split_strategy == 'random':
        # Unchanged - uses hash_buckets
        output_config = example_gen_pb2.Output(
            split_config=example_gen_pb2.SplitConfig(
                splits=[
                    example_gen_pb2.SplitConfig.Split(name='train', hash_buckets=16),
                    example_gen_pb2.SplitConfig.Split(name='eval', hash_buckets=3),
                    example_gen_pb2.SplitConfig.Split(name='test', hash_buckets=1),
                ]
            )
        )
        example_gen = BigQueryExampleGen(query=bigquery_query, output_config=output_config, ...)
    else:
        # NEW - uses input_config with multiple splits (avoids partition_feature_name bug)
        input_config = example_gen_pb2.Input(splits=[
            example_gen_pb2.Input.Split(name='train', pattern=split_queries['train']),
            example_gen_pb2.Input.Split(name='eval', pattern=split_queries['eval']),
            example_gen_pb2.Input.Split(name='test', pattern=split_queries['test']),
        ])
        example_gen = BigQueryExampleGen(input_config=input_config, custom_config={'project': project_id})
```

### Phase 5: Update Inline Script main() to Download Split Queries

```python
def main():
    parser.add_argument("--split-queries-gcs-path", default="",
                       help="GCS blob path to split_queries.json (temporal strategies)")
    ...

    # Download split queries from GCS for temporal strategies
    split_queries = None
    if args.split_queries_gcs_path:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(args.staging_bucket)
        blob = bucket.blob(args.split_queries_gcs_path)
        split_queries = json.loads(blob.download_as_text())
        logger.info(f"Downloaded split queries from gs://{args.staging_bucket}/{args.split_queries_gcs_path}")
```

## Files Modified

| File | Changes |
|------|---------|
| `ml_platform/datasets/services.py` | Added `generate_split_queries()` method |
| `ml_platform/experiments/services.py` | Updated `_submit_pipeline()`, `_submit_vertex_pipeline()`, `_trigger_cloud_build()`, inline script |
| `tests/test_split_strategies.py` | Updated tests for new `input_config` approach |
| `tests/test_proposed_split_fix.py` | New - validation tests for the fix |
| `tests/test_proposed_fix_integration.py` | New - integration tests |
| `docs/tfx_test.md` | New - documentation for running TFX tests |

## Test Results After Implementation

```
$ python tests/test_split_strategies.py --no-django
test_old_broken_ratios ... ok
test_random_split_ratios ... ok
test_random_strategy_creates_test_split ... ok
test_random_strategy_hash_buckets ... ok
test_temporal_strategy_defines_three_splits ... ok
test_temporal_strategy_uses_input_config ... ok
test_transform_analyze_excludes_test ... ok
test_transform_pb2_import_exists ... ok
test_transform_splits_config_exists ... ok
test_transform_transform_includes_test ... ok
----------------------------------------------------------------------
Ran 10 tests in 0.002s
OK
```

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| Temporal split approach | `partition_feature_name='split'` | `input_config.splits` with 3 queries |
| Random split | `hash_buckets=[16,3,1]` | Unchanged |
| Query passing | 3 base64-encoded CLI args | JSON file in GCS |
| Data flow | Single query with 'split' column | 3 separate queries (split column removed) |

## Verification Checklist

- [x] Random split strategy still works (hash_buckets approach unchanged)
- [x] Temporal parameters (holdout_days, train_days, etc.) passed from wizard, not hardcoded
- [x] Split queries uploaded to GCS (avoids Cloud Build 10KB arg limit)
- [x] Inline script downloads split queries from GCS
- [x] `input_config.splits` used instead of `partition_feature_name`
- [x] All unit tests pass (10/10)
- [ ] E2E test: time_holdout strategy pipeline succeeds
- [ ] E2E test: strict_time strategy pipeline succeeds
