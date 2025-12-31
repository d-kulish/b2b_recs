# Custom Job Testing for Vertex AI

This document describes how to run standalone Custom Jobs in Vertex AI for testing specific pipeline components (e.g., Trainer) without running the full TFX pipeline.

## Overview

Running the full TFX pipeline takes ~1 hour. For rapid iteration on specific components like the Trainer, we can:

1. Use **existing artifacts** from a completed pipeline run (Transform output, Schema, etc.)
2. Generate the component code (e.g., `trainer_module.py`) using `services.py`
3. Submit a **standalone Custom Job** that runs only that component

This reduces test iteration time from ~1 hour to ~5 minutes.

## Prerequisites

- Google Cloud SDK configured (`gcloud auth login`)
- Python virtual environment activated
- Django project configured

## Scripts

### 1. `scripts/test_services_trainer.py`

Tests the **actual code generation** from `services.py` by:
1. Loading FeatureConfig and ModelConfig from the database
2. Generating `trainer_module.py` using `TrainerModuleGenerator`
3. Validating the generated code syntax
4. Submitting a Custom Job that runs the trainer

**Usage:**
```bash
# Default: uses FeatureConfig ID 5, ModelConfig ID 6, 2 epochs
./venv/bin/python scripts/test_services_trainer.py

# Custom configs and epochs
./venv/bin/python scripts/test_services_trainer.py \
    --feature-config-id 5 \
    --model-config-id 6 \
    --source-exp qt-62-20251231-154907 \
    --epochs 2

# Dry run (generate code but don't submit job)
./venv/bin/python scripts/test_services_trainer.py --dry-run
```

**Arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `--feature-config-id` | 5 | FeatureConfig database ID |
| `--model-config-id` | 6 | ModelConfig database ID |
| `--source-exp` | qt-62-20251231-154907 | Source experiment for Transform artifacts |
| `--epochs` | 2 | Number of training epochs |
| `--dry-run` | false | Generate code without submitting job |

### 2. `scripts/run_trainer_only.py`

Tests trainer code with **regex patching** on existing trainer artifacts. Useful for testing specific fixes without regenerating the entire trainer module.

**Usage:**
```bash
./venv/bin/python scripts/run_trainer_only.py \
    --source qt-62-20251231-154907 \
    --epochs 5
```

**Note:** This script applies regex patches to an existing `trainer_module.py` from GCS. It does NOT test the actual code generation path in `services.py`.

## Monitoring Jobs

### Check Job Status
```bash
gcloud ai custom-jobs describe JOB_ID --region=europe-central2 --format='value(state)'
```

### View Logs
```bash
# All logs
gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="JOB_ID"' \
    --project=b2b-recs --limit=100 --format='value(textPayload)'

# Filter for errors
gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="JOB_ID" AND "ERROR"' \
    --project=b2b-recs --limit=50 --format='value(textPayload)'

# Filter for specific patterns
gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="JOB_ID" AND "grad"' \
    --project=b2b-recs --limit=20 --format='value(textPayload)'
```

### View Generated Code
```bash
gsutil cat gs://b2b-recs-quicktest-artifacts/services-test-TIMESTAMP/trainer_module.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    test_services_trainer.py                      │
├─────────────────────────────────────────────────────────────────┤
│ 1. Load configs from Django DB                                   │
│ 2. TrainerModuleGenerator.generate() → trainer_module.py         │
│ 3. validate_python_code() → syntax check                         │
│ 4. Upload to GCS: gs://b2b-recs-quicktest-artifacts/...         │
│ 5. Create runner.py (wraps trainer execution)                    │
│ 6. Submit Vertex AI CustomJob                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Vertex AI CustomJob                          │
├─────────────────────────────────────────────────────────────────┤
│ Container: europe-central2-docker.pkg.dev/b2b-recs/             │
│            tfx-builder/tfx-trainer:latest                        │
│                                                                  │
│ 1. Download trainer_module.py from GCS                           │
│ 2. Download Transform artifacts (transform_graph, schema)        │
│ 3. Set MLFLOW_TRACKING_URI environment                           │
│ 4. Import and execute trainer.run_fn(fn_args)                    │
│ 5. Upload model to GCS                                           │
└─────────────────────────────────────────────────────────────────┘
```

## GCS Buckets

| Bucket | Purpose |
|--------|---------|
| `b2b-recs-pipeline-staging` | Pipeline artifacts (Transform, Schema, etc.) |
| `b2b-recs-quicktest-artifacts` | Test artifacts and generated trainer code |

## Finding Source Artifacts

To find artifacts from a completed experiment:

```bash
# List available experiments
gsutil ls gs://b2b-recs-pipeline-staging/pipeline_root/ | grep qt-

# List artifacts for a specific experiment
gsutil ls gs://b2b-recs-pipeline-staging/pipeline_root/qt-62-20251231-154907/
```

Required artifacts for trainer testing:
- `Transform_*/transform_graph/` - Transform model
- `Transform_*/transformed_examples/Split-train/` - Training data
- `Transform_*/transformed_examples/Split-eval/` - Evaluation data
- `SchemaGen_*/schema/schema.pbtxt` - Data schema

## Troubleshooting

### Job Fails Immediately
- Check container image exists: `gcloud artifacts docker images list europe-central2-docker.pkg.dev/b2b-recs/tfx-builder`
- Check IAM permissions for the service account

### Import Errors
- Verify Transform artifacts are compatible with the trainer code
- Check that feature names in FeatureConfig match the Transform output

### MLflow Errors
- HTTP 400: Usually invalid metric names (e.g., containing `{` or `}`)
- Connection errors: Check MLflow server is running

### Graph Mode Errors
- `SymbolicTensor has no attribute 'numpy'`: Code calling `.numpy()` inside `train_step`
- Solution: Use `tf.Variable` accumulators and pure TF ops in `train_step`
