# BigQueryExampleGen Column Aliases Test Results

**Date:** 2025-12-29
**Related Issue:** Exp #21 failed at BigQueryExampleGen due to column renaming issues
**Bug Fix Commit:** `fa102aa` - Nested WITH clause bug & column aliases consistency

---

## Objective

Verify that the column aliasing fix works correctly in the `BigQueryExampleGen` TFX component by running an isolated Vertex AI Pipeline test.

---

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Dataset | `old_examples_chernigiv` (ID: 14) |
| Feature Config | `cherng_v1` (ID: 5) |
| Split Strategy | `random` |
| Sample Percent | 10% |
| Pipeline | BigQueryExampleGen only (no Transform/Trainer) |

### Column Aliases Tested

| Original Column | Aliased Name |
|-----------------|--------------|
| `division_desc` | `category` |
| `mge_cat_desc` | `sub_category` |

---

## Test Execution

### Step 1: SQL Validation

**Command:**
```bash
bq query --dry_run --use_legacy_sql=false "$(cat /tmp/test_query.sql)"
```

**Result:** Query validated successfully (1.56 GB would be processed)

**Sample Output:**
```json
{
  "category": "DRY",
  "sub_category": "ЗЕЛЬТЕРСЬКА/ СОДОВА",
  "customer_id": "170052245701",
  "product_id": "276133001001",
  ...
}
```

Column aliases confirmed in BigQuery output.

---

### Step 2: Vertex AI Pipeline Submission

**Test Script:** `tests/test_bq_example_gen.py`

**First Attempt (failed):**
- Run ID: `20251229-202041`
- Cloud Build: `3f216d78-523c-42e2-a176-9dbd8b608a8e` ✓
- Vertex Pipeline: `PIPELINE_STATE_FAILED`
- **Cause:** Missing Dataflow configuration and custom TFX image

**Second Attempt (successful):**
- Run ID: `20251229-203623`
- Cloud Build: `729f71b0-4183-423e-b24b-e006aef70846` ✓
- Vertex Pipeline: `test-bq-examplegen-20251229-203623-20251229203806` ✓
- **Status:** `PIPELINE_STATE_SUCCEEDED`

**Fix Applied:**
1. Added `beam_pipeline_args` with DataflowRunner configuration
2. Added custom TFX image: `europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-trainer:latest`

---

### Step 3: TFRecords Verification

**TFRecords Location:**
```
gs://b2b-recs-pipeline-staging/test_bq_example_gen/20251229-203623/
  555035914949/test-bq-examplegen-20251229-203623-20251229203806/
    BigQueryExampleGen_7315307045802999808/examples/
      Split-train/data_tfrecord-00000-of-00001.gz
      Split-eval/data_tfrecord-00000-of-00001.gz
```

**Column Names Found in TFRecords:**

| Column | Status |
|--------|--------|
| `category` | ✓ Found (aliased from `division_desc`) |
| `sub_category` | ✓ Found (aliased from `mge_cat_desc`) |
| `customer_id` | ✓ Found |
| `product_id` | ✓ Found |
| `city` | ✓ Found |
| `sales` | ✓ Found |
| `cust_value` | ✓ Found |
| `date` | ✓ Found |

**Original Column Names (should NOT be present):**

| Column | Status |
|--------|--------|
| `division_desc` | ✓ Not found (correctly replaced) |
| `mge_cat_desc` | ✓ Not found (correctly replaced) |

---

## Conclusion

**TEST PASSED**

The bug fix in commit `fa102aa` successfully resolves the column aliasing issue:

1. **SQL Generation:** Column aliases are correctly applied via `AS` clauses
2. **BigQueryExampleGen:** Executes SQL and outputs TFRecords with aliased column names
3. **Data Consistency:** TFRecords contain `category` and `sub_category` (not original names)

The Transform and Trainer code that references `inputs['category']` and `inputs['sub_category']` will now work correctly.

---

## Test Script Usage

The test script can be reused to verify BigQueryExampleGen behavior:

```bash
# Dry run - just show the SQL query
./venv/bin/python tests/test_bq_example_gen.py --dry-run

# Submit test pipeline to Vertex AI
./venv/bin/python tests/test_bq_example_gen.py --submit
```

---

## Next Steps

1. Re-run Exp #21 (or create new experiment) to verify full pipeline works
2. Monitor that Transform stage correctly processes aliased columns
3. Verify Trainer code references aliased column names in embeddings

---

## References

- Bug Fix Documentation: `docs/bug_fix_nested_with_and_column_aliases.md`
- Test Script: `tests/test_bq_example_gen.py`
- Experiments Phase: `docs/phase_experiments.md`
