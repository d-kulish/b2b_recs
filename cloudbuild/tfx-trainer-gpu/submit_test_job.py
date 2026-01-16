#!/usr/bin/env python3
"""
Submit GPU Test Job to Vertex AI

This script submits a Vertex AI Custom Job to test the GPU container.
It uploads the test script to GCS and runs it on a GPU VM.

Usage:
    python submit_test_job.py [--gpu-type GPU_TYPE] [--gpu-count GPU_COUNT]

Examples:
    python submit_test_job.py --gpu-type NVIDIA_TESLA_T4 --gpu-count 1
    python submit_test_job.py --gpu-type NVIDIA_L4 --gpu-count 2
    python submit_test_job.py --gpu-type NVIDIA_TESLA_V100 --gpu-count 1

Environment variables:
    GCP_PROJECT_ID: GCP project ID (default: b2b-recs)
    GCP_REGION: GCP region (default: europe-central2)
"""

import argparse
import os
import sys
from datetime import datetime

from google.cloud import aiplatform
from google.cloud import storage


# Configuration
PROJECT_ID = os.environ.get('GCP_PROJECT_ID', 'b2b-recs')
REGION = os.environ.get('GCP_REGION', 'europe-central2')
STAGING_BUCKET = f'gs://{PROJECT_ID}-pipeline-staging'
IMAGE_URI = f'{REGION}-docker.pkg.dev/{PROJECT_ID}/tfx-builder/tfx-trainer-gpu:latest'

# GPU configurations
GPU_CONFIGS = {
    'NVIDIA_TESLA_T4': {
        'machine_type': 'n1-standard-8',
        'accelerator_count': 1,
    },
    'NVIDIA_L4': {
        'machine_type': 'g2-standard-12',
        'accelerator_count': 1,
    },
    'NVIDIA_TESLA_V100': {
        'machine_type': 'n1-standard-8',
        'accelerator_count': 1,
    },
    'NVIDIA_TESLA_A100': {
        'machine_type': 'a2-highgpu-1g',
        'accelerator_count': 1,
    },
}


def upload_test_script(bucket_name: str, destination_path: str) -> str:
    """Upload test_gpu.py to GCS."""
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_path)

    # Read the test script
    script_path = os.path.join(os.path.dirname(__file__), 'test_gpu.py')
    with open(script_path, 'r') as f:
        script_content = f.read()

    blob.upload_from_string(script_content, content_type='text/x-python')
    return f'gs://{bucket_name}/{destination_path}'


def submit_gpu_test_job(
    gpu_type: str = 'NVIDIA_TESLA_T4',
    gpu_count: int = 1,
    use_spot: bool = False,
) -> str:
    """Submit a Vertex AI Custom Job to test the GPU container."""

    # Initialize Vertex AI
    aiplatform.init(project=PROJECT_ID, location=REGION)

    # Generate job ID
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    job_id = f'gpu-test-{gpu_type.lower().replace("_", "-")}-{timestamp}'

    print(f"Submitting GPU test job: {job_id}")
    print(f"  GPU Type: {gpu_type}")
    print(f"  GPU Count: {gpu_count}")
    print(f"  Use Spot: {use_spot}")
    print(f"  Image: {IMAGE_URI}")

    # Upload test script to GCS
    bucket_name = f'{PROJECT_ID}-pipeline-staging'
    script_gcs_path = f'gpu-test/{job_id}/test_gpu.py'
    script_uri = upload_test_script(bucket_name, script_gcs_path)
    print(f"  Test script: {script_uri}")

    # Get machine configuration
    if gpu_type not in GPU_CONFIGS:
        raise ValueError(f"Unknown GPU type: {gpu_type}. Available: {list(GPU_CONFIGS.keys())}")

    config = GPU_CONFIGS[gpu_type]
    machine_type = config['machine_type']

    # Adjust machine type for multiple GPUs
    if gpu_count > 1:
        if gpu_type == 'NVIDIA_L4':
            if gpu_count == 2:
                machine_type = 'g2-standard-24'
            elif gpu_count == 4:
                machine_type = 'g2-standard-48'
            elif gpu_count == 8:
                machine_type = 'g2-standard-96'
        elif gpu_type in ['NVIDIA_TESLA_T4', 'NVIDIA_TESLA_V100']:
            if gpu_count == 2:
                machine_type = 'n1-standard-16'
            elif gpu_count == 4:
                machine_type = 'n1-standard-32'

    print(f"  Machine Type: {machine_type}")

    # Create the custom job
    worker_pool_specs = [
        {
            'machine_spec': {
                'machine_type': machine_type,
                'accelerator_type': gpu_type,
                'accelerator_count': gpu_count,
            },
            'replica_count': 1,
            'container_spec': {
                'image_uri': IMAGE_URI,
                'command': ['python'],
                'args': ['/gcs_script/test_gpu.py'],
            },
            'disk_spec': {
                'boot_disk_type': 'pd-ssd',
                'boot_disk_size_gb': 100,
            },
        }
    ]

    # Add spot/preemptible scheduling if requested
    if use_spot:
        worker_pool_specs[0]['machine_spec']['spot'] = True

    # Create custom training job
    job = aiplatform.CustomJob(
        display_name=job_id,
        worker_pool_specs=worker_pool_specs,
        staging_bucket=STAGING_BUCKET,
    )

    # Submit with script
    print("\nStarting job...")
    job.run(
        service_account=f'{PROJECT_ID}@appspot.gserviceaccount.com',
        sync=False,  # Don't wait for completion
    )

    # Get job resource name
    job_resource = job.resource_name
    print(f"\nJob submitted successfully!")
    print(f"  Resource name: {job_resource}")
    print(f"\nTo monitor the job:")
    print(f"  gcloud ai custom-jobs describe {job_resource.split('/')[-1]} --project={PROJECT_ID} --region={REGION}")
    print(f"\nOr view in console:")
    print(f"  https://console.cloud.google.com/vertex-ai/training/custom-jobs?project={PROJECT_ID}")

    return job_resource


def check_gpu_availability(gpu_type: str, gpu_count: int) -> bool:
    """Check if the requested GPU configuration is available."""
    # This is a simplified check - actual availability requires querying quotas
    print(f"\nChecking GPU availability for {gpu_type} x {gpu_count}...")

    # Known limitations
    if gpu_type == 'NVIDIA_TESLA_A100' and gpu_count > 1:
        print("  Warning: A100 multi-GPU requires a2-megagpu machines")

    if gpu_type == 'NVIDIA_L4' and gpu_count > 8:
        print("  Warning: L4 supports max 8 GPUs per VM")

    print("  Note: Actual availability depends on quota and region capacity")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Submit GPU test job to Vertex AI'
    )
    parser.add_argument(
        '--gpu-type',
        type=str,
        default='NVIDIA_TESLA_T4',
        choices=list(GPU_CONFIGS.keys()),
        help='GPU type to use (default: NVIDIA_TESLA_T4)'
    )
    parser.add_argument(
        '--gpu-count',
        type=int,
        default=1,
        choices=[1, 2, 4, 8],
        help='Number of GPUs (default: 1)'
    )
    parser.add_argument(
        '--spot',
        action='store_true',
        help='Use spot/preemptible VMs (70%% cheaper but may be interrupted)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print configuration without submitting job'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("TFX TRAINER GPU - TEST JOB SUBMISSION")
    print("=" * 60)

    check_gpu_availability(args.gpu_type, args.gpu_count)

    if args.dry_run:
        print("\n[DRY RUN] Would submit job with:")
        print(f"  GPU Type: {args.gpu_type}")
        print(f"  GPU Count: {args.gpu_count}")
        print(f"  Spot: {args.spot}")
        print(f"  Image: {IMAGE_URI}")
        return 0

    try:
        job_resource = submit_gpu_test_job(
            gpu_type=args.gpu_type,
            gpu_count=args.gpu_count,
            use_spot=args.spot,
        )
        return 0
    except Exception as e:
        print(f"\nError submitting job: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
