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

---

## GPU-Based Testing (2026-01-22)

This section describes how to run Custom Job tests with GPU acceleration. GPU testing is critical for verifying that training pipelines will use hardware acceleration correctly.

### Why GPU Testing Matters

1. **Fail-Fast Behavior**: The trainer now raises `RuntimeError` if GPU was requested but not detected
2. **Region Constraints**: Not all GCP regions have GPU quota
3. **Container Requirements**: Must use CUDA-enabled container images
4. **Performance Validation**: Verify actual GPU utilization before full-scale runs

### GPU Region Configuration

**CRITICAL**: Not all regions support GPUs. Use regions with GPU quota.

| Region | GPU Support | Notes |
|--------|-------------|-------|
| `europe-west4` | ✅ Yes | **Recommended for EU** - T4, V100, A100 available |
| `europe-central2` | ❌ No | No GPU quota - will fail |
| `us-central1` | ✅ Yes | T4, V100, A100 available |
| `us-west1` | ✅ Yes | T4, V100 available |

### Staging Bucket Configuration

**CRITICAL**: The job staging bucket must be in the **same region** as the Custom Job.

```python
# In scripts/test_services_trainer.py

# Job runs in europe-west4
REGION = 'europe-west4'

# Staging bucket MUST be in europe-west4
JOB_STAGING_BUCKET = 'b2b-recs-gpu-staging'  # Created in europe-west4
```

**Create Staging Bucket (if needed):**
```bash
gsutil mb -l europe-west4 gs://b2b-recs-gpu-staging
```

### Container Image Requirements

For GPU training, use a container with CUDA drivers pre-installed:

| Image | Use Case |
|-------|----------|
| `tfx-trainer-gpu:latest` | GPU training with TensorFlow |
| `tfx-trainer:latest` | CPU-only training |

**Build GPU Container (if needed):**
```bash
# Dockerfile.gpu should extend TF GPU base image
gcloud builds submit --config=deploy/tfx_builder/cloudbuild-gpu.yaml .
```

### Worker Pool Specs for GPU

Configure the `worker_pool_specs` with GPU accelerators:

```python
worker_pool_specs = [{
    "machine_spec": {
        "machine_type": "n1-standard-8",       # 8 vCPUs, 30GB RAM
        "accelerator_type": "NVIDIA_TESLA_T4", # GPU type
        "accelerator_count": 1,                # Number of GPUs
    },
    "replica_count": 1,
    "container_spec": {
        "image_uri": f"{REGION}-docker.pkg.dev/{PROJECT_ID}/tfx-builder/tfx-trainer-gpu:latest",
        "command": ["python", "-c", "..."],
        "args": [],
        "env": [
            {"name": "GPU_ENABLED", "value": "true"},
            {"name": "GPU_COUNT", "value": "1"},
        ],
    },
}]
```

### Custom Config for GPU

The `custom_config` passed to the trainer must include GPU settings:

```python
custom_config = {
    # GPU configuration - REQUIRED for GPU training
    'gpu_enabled': True,
    'gpu_count': 1,

    # Other training parameters
    'epochs': 3,
    'batch_size': 1024,
    ...
}
```

**Important**: If `gpu_enabled=True` but no GPUs are detected, the trainer will raise:
```
RuntimeError: GPU training requested (gpu_count=1) but no GPUs detected.
Check: 1) GPU quota in region, 2) Container image has CUDA drivers,
3) Machine type supports GPUs. Will NOT fall back to CPU training.
```

### Available GPU Types

| GPU Type | Constant | Memory | Use Case |
|----------|----------|--------|----------|
| Tesla T4 | `NVIDIA_TESLA_T4` | 16 GB | Cost-effective training |
| Tesla V100 | `NVIDIA_TESLA_V100` | 16 GB | High-performance training |
| A100 40GB | `NVIDIA_TESLA_A100` | 40 GB | Large models |
| A100 80GB | `NVIDIA_A100_80GB` | 80 GB | Very large models |

### Running GPU Test

**Full Command:**
```bash
./venv/bin/python scripts/test_services_trainer.py \
    --feature-config-id 8 \
    --model-config-id 14 \
    --source-training-run 7 \
    --epochs 3
```

**Expected Output:**
```
============================================================
                    GPU TRAINING TEST RESULTS
============================================================

GPU Configuration:
  gpu_enabled: True
  gpu_count: 1

Physical GPUs detected: 1
  GPU 0: Tesla T4

Training completed successfully!
  Epochs: 3
  Test Recall@100: 0.1758
============================================================
```

### Verifying GPU Usage in Logs

Check that GPUs were actually used:

```bash
# View job logs
gcloud logging read 'resource.type="ml_job" AND resource.labels.job_id="JOB_ID"' \
    --project=b2b-recs --limit=100 --format='value(textPayload)' | grep -i gpu

# Expected output:
# Physical GPUs detected: 1
# GPU 0: Tesla T4
# Using single GPU (default strategy)
```

### GPU Troubleshooting

#### No GPUs Detected
```
RuntimeError: GPU training requested (gpu_count=1) but no GPUs detected.
```

**Solutions:**
1. Verify region has GPU quota: `gcloud compute accelerator-types list --filter="zone:europe-west4-*"`
2. Use GPU-enabled container: `tfx-trainer-gpu:latest`
3. Check `accelerator_type` and `accelerator_count` in `worker_pool_specs`

#### Cross-Region Bucket Error
```
Error: Staging bucket must be in same region as job
```

**Solution:**
Create bucket in job region:
```bash
gsutil mb -l europe-west4 gs://b2b-recs-gpu-staging
```

#### GPU Quota Exceeded
```
Error: Quota 'NVIDIA_T4_GPUS' exceeded
```

**Solutions:**
1. Request quota increase in GCP Console
2. Use a different GPU type
3. Use a different region

#### CUDA Driver Mismatch
```
Could not load dynamic library 'libcuda.so.1'
```

**Solution:**
Use GPU-enabled container with matching CUDA version:
```bash
# Rebuild container with correct CUDA
docker build -f Dockerfile.gpu -t tfx-trainer-gpu:latest .
```

### Test Artifacts Location

After a successful GPU test, artifacts are stored in:

```
gs://b2b-recs-quicktest-artifacts/services-test-TIMESTAMP/
├── trainer_module.py    # Generated trainer code
├── runner.py            # Job runner script
└── model/               # Trained model (if successful)
    └── pushed_model/
        ├── saved_model.pb
        └── variables/
```

### Quick Reference

| Parameter | Value | Notes |
|-----------|-------|-------|
| Region | `europe-west4` | GPU-enabled |
| Staging Bucket | `gs://b2b-recs-gpu-staging` | In europe-west4 |
| Container | `tfx-trainer-gpu:latest` | CUDA-enabled |
| Machine Type | `n1-standard-8` | 8 vCPUs, 30GB RAM |
| GPU Type | `NVIDIA_TESLA_T4` | Cost-effective |
| GPU Count | `1` | Single GPU |
| `gpu_enabled` | `True` | In custom_config |
| `gpu_count` | `1` | In custom_config |
