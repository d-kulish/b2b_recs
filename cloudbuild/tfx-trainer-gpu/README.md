# TFX Trainer GPU Container

GPU-enabled TFX trainer container for full-scale TFRS model training on Vertex AI.

## Overview

This container extends the CPU-based `tfx-trainer` with GPU support for production model training:

| Feature | tfx-trainer (CPU) | tfx-trainer-gpu |
|---------|-------------------|-----------------|
| Base Image | `gcr.io/tfx-oss-public/tfx:1.15.0` | `tensorflow/tensorflow:2.15.0-gpu` |
| TensorFlow | 2.15.x (CPU) | 2.15.0 (GPU with CUDA 12.2) |
| Multi-GPU | N/A | MirroredStrategy + NCCL |
| Use Case | Quick Tests (5-25% data) | Full Training (100% data) |

## Building the Container

### Prerequisites

1. Google Cloud SDK installed and configured
2. Docker (for local testing only)
3. Access to `b2b-recs` project with Artifact Registry permissions

### Build with Cloud Build

```bash
cd cloudbuild/tfx-trainer-gpu
gcloud builds submit --config=cloudbuild.yaml --project=b2b-recs
```

This takes approximately 15-20 minutes due to the large TensorFlow GPU base image.

### Verify Build

Check the image in Artifact Registry:
```bash
gcloud artifacts docker images list \
  europe-central2-docker.pkg.dev/b2b-recs/tfx-builder \
  --filter="package=tfx-trainer-gpu"
```

## Testing the Container

### Submit GPU Test Job

The test script validates all GPU functionality:

```bash
# Test with 1x T4 GPU (most available)
python submit_test_job.py --gpu-type NVIDIA_TESLA_T4 --gpu-count 1

# Test with 2x L4 GPUs (recommended for training)
python submit_test_job.py --gpu-type NVIDIA_L4 --gpu-count 2

# Test with spot VMs (cheaper, may be interrupted)
python submit_test_job.py --gpu-type NVIDIA_L4 --gpu-count 2 --spot
```

### Monitor Test Job

```bash
# List recent jobs
gcloud ai custom-jobs list --project=b2b-recs --region=europe-central2 --limit=5

# Describe specific job
gcloud ai custom-jobs describe JOB_ID --project=b2b-recs --region=europe-central2

# Stream logs
gcloud ai custom-jobs stream-logs JOB_ID --project=b2b-recs --region=europe-central2
```

### Expected Test Output

A successful test shows:
```
TEST SUMMARY
  ✅ TensorFlow GPU: PASSED
  ✅ MirroredStrategy: PASSED
  ✅ TFRS Import: PASSED
  ✅ ScaNN: PASSED
  ✅ TFRS Model Training: PASSED
  ✅ TFX Components: PASSED

ALL TESTS PASSED - GPU container is ready for training!
```

## GPU Configurations

| GPU Type | Machine Type | GPU Memory | Best For |
|----------|--------------|------------|----------|
| T4 | n1-standard-8 | 16GB | Testing, small models |
| L4 | g2-standard-12+ | 24GB | **Recommended** for training |
| V100 | n1-standard-8 | 16GB | High performance |
| A100 | a2-highgpu-1g | 40GB | Very large models |

### Multi-GPU Configurations

| GPUs | L4 Machine | T4/V100 Machine |
|------|------------|-----------------|
| 1 | g2-standard-12 | n1-standard-8 |
| 2 | g2-standard-24 | n1-standard-16 |
| 4 | g2-standard-48 | n1-standard-32 |
| 8 | g2-standard-96 | n1-standard-64 |

## Container Contents

- **TensorFlow 2.15.0** with CUDA 12.2 and cuDNN 8.9
- **TFX 1.15.0** for pipeline orchestration
- **TensorFlow Recommenders 0.7.3+** for TFRS models
- **ScaNN 1.3.0** for approximate nearest neighbor search
- **NCCL** for multi-GPU communication
- **KFP 2.0+** for Kubeflow pipeline compilation

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NCCL_DEBUG` | `INFO` | NCCL debugging level |
| `TF_FORCE_GPU_ALLOW_GROWTH` | `true` | Dynamic GPU memory allocation |

## Troubleshooting

### GPU Not Detected

If GPUs are not detected:
1. Verify the VM has GPU quota in the region
2. Check CUDA driver compatibility
3. Review container logs for CUDA errors

```bash
# Check GPU quota
gcloud compute regions describe europe-central2 --project=b2b-recs \
  --format="table(quotas.filter(metric~GPU))"
```

### Out of Memory (OOM)

If training fails with OOM:
1. Reduce batch size
2. Use a GPU with more memory (L4 or A100)
3. Enable mixed precision training

### Build Failures

If the container build fails:
1. Check Artifact Registry permissions
2. Verify network access to Docker Hub and PyPI
3. Review Cloud Build logs

## Related Files

- `Dockerfile` - Container definition
- `cloudbuild.yaml` - Cloud Build configuration
- `test_gpu.py` - GPU validation script
- `submit_test_job.py` - Test job submission script

## References

- [Vertex AI GPU Configuration](https://cloud.google.com/vertex-ai/docs/training/configure-compute)
- [TensorFlow GPU Support](https://www.tensorflow.org/install/gpu)
- [NVIDIA CUDA Containers](https://hub.docker.com/r/nvidia/cuda)
- [TFX on Vertex AI](https://www.tensorflow.org/tfx/tutorials/tfx/gcp/vertex_pipelines_vertex_training)
