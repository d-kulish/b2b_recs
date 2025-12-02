# BigQuery US Region Migration Plan

**Created**: 2025-12-02
**Status**: Planning
**Priority**: Medium (before production rollout)

---

## Problem Statement

The current BigQuery dataset `b2b-recs:raw_data` was created in the **US multi-region** by default. This is inconsistent with our target infrastructure location of **europe-central2** (Warsaw, Poland).

### Current State
```
Dataset: b2b-recs:raw_data
Location: US (multi-region)
Tables: bq_csv (and potentially others)
```

### Target State
```
Dataset: b2b-recs:raw_data
Location: europe-central2 (Warsaw)
Tables: Same structure, same data
```

---

## Why Migration is Necessary

### 1. Data Residency Compliance
- **GDPR Requirements**: EU client data should remain in EU regions
- **Ukrainian Regulations**: Data should be in geographically appropriate locations
- **Client Contracts**: May require data to stay in specific regions

### 2. Operational Consistency
- All other GCP resources (Cloud Run, Cloud SQL, GCS) should be in europe-central2
- Mixed regions cause confusion and potential errors
- Consistent region simplifies troubleshooting

### 3. Cost Optimization
- Cross-region queries incur data transfer costs
- Co-located resources have lower latency
- Egress charges apply when data crosses regions

### 4. Performance
- Queries run faster when client and data are in same region
- Reduced network latency for data-intensive operations
- Better user experience for EU-based users

---

## Impact Assessment

### Low Risk (Current Development Stage)
- **Data Volume**: Small (development/test data only)
- **Dependencies**: Application code already updated to use configurable location
- **Users**: Only development team affected
- **Downtime**: Acceptable for development environment

### Considerations
- BigQuery dataset location **cannot be changed** after creation
- Must create new dataset and copy data
- All table references remain the same (same dataset name)

---

## Migration Steps

### Step 1: Verify Current State

```bash
# Check current dataset location
bq show --format=prettyjson b2b-recs:raw_data | grep location

# List all tables in the dataset
bq ls b2b-recs:raw_data

# Check table sizes
bq show --format=prettyjson b2b-recs:raw_data.bq_csv
```

### Step 2: Create New Dataset in europe-central2

```bash
# Create new dataset with correct location
bq mk \
  --location=europe-central2 \
  --dataset \
  --description="Raw data from ETL pipelines (migrated from US)" \
  b2b-recs:raw_data_eu

# Verify creation
bq show --format=prettyjson b2b-recs:raw_data_eu
```

### Step 3: Copy Tables

```bash
# Copy each table to new dataset
# For bq_csv table:
bq cp \
  --force \
  b2b-recs:raw_data.bq_csv \
  b2b-recs:raw_data_eu.bq_csv

# Repeat for any other tables in raw_data dataset
# bq cp b2b-recs:raw_data.other_table b2b-recs:raw_data_eu.other_table
```

### Step 4: Verify Data Integrity

```bash
# Compare row counts
bq query --use_legacy_sql=false \
  "SELECT 'US' as region, COUNT(*) as rows FROM \`b2b-recs.raw_data.bq_csv\`
   UNION ALL
   SELECT 'EU' as region, COUNT(*) as rows FROM \`b2b-recs.raw_data_eu.bq_csv\`"

# Compare schemas
bq show --schema --format=prettyjson b2b-recs:raw_data.bq_csv > us_schema.json
bq show --schema --format=prettyjson b2b-recs:raw_data_eu.bq_csv > eu_schema.json
diff us_schema.json eu_schema.json
```

### Step 5: Rename Datasets (Atomic Swap)

BigQuery doesn't support renaming datasets, so we need to:

```bash
# Option A: Update application to use new dataset name
# Change GCP_LOCATION and dataset references in application

# Option B: Delete old and recreate with same name (DESTRUCTIVE)
# Only do this after verifying data in new dataset

# 1. Delete old dataset (CAREFUL - data loss if not copied correctly)
bq rm -r -f b2b-recs:raw_data

# 2. Rename new dataset by copying again
bq mk --location=europe-central2 --dataset b2b-recs:raw_data
bq cp b2b-recs:raw_data_eu.bq_csv b2b-recs:raw_data.bq_csv

# 3. Delete temporary dataset
bq rm -r -f b2b-recs:raw_data_eu
```

### Step 6: Update Application Configuration

```python
# config/settings.py
GCP_LOCATION = os.environ.get('GCP_LOCATION', 'europe-central2')
```

### Step 7: Verify Application Works

```bash
# Run Django dev server
python manage.py runserver

# Test dataset analysis
# Click "Analyse dataset" in UI - should work without errors
```

### Step 8: Clean Up

```bash
# Remove old dataset if using Option B
# Already done in Step 5

# Remove temporary files
rm us_schema.json eu_schema.json
```

---

## Rollback Plan

If migration fails:

1. **Data still in US dataset**: No action needed, application can use US location
2. **Data copied but US deleted**: Restore from copy in raw_data_eu
3. **Application errors**: Revert `GCP_LOCATION` to `US` in settings

---

## Post-Migration Checklist

- [ ] Verify `raw_data` dataset location is europe-central2
- [ ] Verify all tables copied with correct row counts
- [ ] Verify application queries work (Analyse dataset button)
- [ ] Verify ETL jobs write to correct dataset
- [ ] Update any scheduled jobs or triggers
- [ ] Delete temporary datasets and backups
- [ ] Document migration completion date

---

## Timeline Recommendation

| Phase | Action | When |
|-------|--------|------|
| **Now** | Keep using US location for development | Current |
| **Before first client** | Perform migration to europe-central2 | Before production |
| **Client onboarding** | Create client datasets in correct region from start | Per client |

---

## Alternative: Keep US for Development

If migration is not urgent, you can:

1. Keep `raw_data` in US for development
2. Set `GCP_LOCATION=US` in development settings
3. When deploying to production/client projects, ensure new datasets are created in correct region from the start

This avoids migration complexity but requires careful attention during client onboarding.

---

## Commands Reference

```bash
# Check dataset location
bq show --format=prettyjson PROJECT:DATASET | grep location

# Create dataset with location
bq mk --location=REGION --dataset PROJECT:DATASET

# Copy table
bq cp SOURCE_TABLE DESTINATION_TABLE

# Delete dataset (with all tables)
bq rm -r -f PROJECT:DATASET

# List tables in dataset
bq ls PROJECT:DATASET

# Query to compare data
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM \`PROJECT.DATASET.TABLE\`"
```

---

## Notes

- BigQuery dataset location is immutable after creation
- Cross-region copies may incur data transfer costs
- Large datasets may take significant time to copy
- Consider using BigQuery Data Transfer Service for large migrations
