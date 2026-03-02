#!/usr/bin/env python3
"""
BigQueryExampleGen Isolated Test

Tests that BigQueryExampleGen correctly outputs TFRecords with aliased column names.
This is a minimal TFX pipeline with only the BigQueryExampleGen component.

Usage:
    # Submit via Cloud Build (recommended)
    python tests/test_bq_example_gen.py --submit

    # Just generate and print the SQL (dry run)
    python tests/test_bq_example_gen.py --dry-run
"""

import argparse
import base64
import json
import logging
import os
import sys
import tempfile
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = 'b2b-recs'
REGION = 'europe-central2'
STAGING_BUCKET = 'b2b-recs-pipeline-staging'
TFX_COMPILER_IMAGE = 'europe-central2-docker.pkg.dev/b2b-recs/tfx-builder/tfx-compiler:latest'


def get_test_query():
    """Generate the test SQL query using Django models."""
    # Add Django setup - ensure project root is in path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    import django
    django.setup()

    from ml_platform.models import Dataset, ModelEndpoint
    from ml_platform.datasets.services import BigQueryService

    # Dataset 14 = old_examples_chernigiv (has column aliases)
    ds = Dataset.objects.get(id=14)
    endpoint = ModelEndpoint.objects.first()

    bq_service = BigQueryService(endpoint, ds)
    sql = bq_service.generate_training_query(
        dataset=ds,
        split_strategy='random',
        holdout_days=1,
        date_column='date',
        sample_percent=10,  # Small sample for test
    )
    return sql


def get_compile_script():
    """Return the TFX compile and submit script for BigQueryExampleGen only."""
    return '''
import argparse
import base64
import json
import logging
import os
import tempfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_bq_example_gen_pipeline(
    pipeline_name: str,
    pipeline_root: str,
    bigquery_query: str,
    project_id: str,
    region: str = 'europe-central2',
):
    """Create minimal TFX pipeline with only BigQueryExampleGen."""
    from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
    from tfx.proto import example_gen_pb2
    from tfx.orchestration import pipeline as tfx_pipeline

    logger.info(f"Creating minimal pipeline: {pipeline_name}")
    logger.info(f"Query length: {len(bigquery_query)} chars")

    # Random split (80/20) - no partition_feature_name needed
    output_config = example_gen_pb2.Output(
        split_config=example_gen_pb2.SplitConfig(
            splits=[
                example_gen_pb2.SplitConfig.Split(name="train", hash_buckets=8),
                example_gen_pb2.SplitConfig.Split(name="eval", hash_buckets=2),
            ]
        )
    )

    example_gen = BigQueryExampleGen(
        query=bigquery_query,
        output_config=output_config,
        custom_config={"project": project_id}
    )

    # Configure Dataflow for BigQueryExampleGen (same as real experiments)
    staging_bucket = f'{project_id}-pipeline-staging'
    beam_pipeline_args = [
        '--runner=DataflowRunner',
        f'--project={project_id}',
        f'--region={region}',
        f'--zone={region}-b',  # Explicitly set zone to avoid exhausted zones (a and c are exhausted)
        f'--temp_location=gs://{staging_bucket}/dataflow_temp',
        f'--staging_location=gs://{staging_bucket}/dataflow_staging',
        '--machine_type=e2-standard-4',
        '--disk_size_gb=50',
        '--experiments=use_runner_v2',
        '--max_num_workers=10',
        '--autoscaling_algorithm=THROUGHPUT_BASED',
    ]
    logger.info(f"Dataflow configured: project={project_id}, region={region}")

    pipeline = tfx_pipeline.Pipeline(
        pipeline_name=pipeline_name,
        pipeline_root=pipeline_root,
        components=[example_gen],
        enable_cache=False,
        beam_pipeline_args=beam_pipeline_args,
    )

    logger.info("Pipeline created with BigQueryExampleGen only (using DataflowRunner)")
    return pipeline


def compile_pipeline(pipeline, output_file: str, project_id: str):
    """Compile pipeline to Vertex AI format."""
    from tfx.orchestration.kubeflow.v2 import kubeflow_v2_dag_runner

    logger.info(f"Compiling pipeline to: {output_file}")

    # Use custom TFX image (same as real experiments)
    custom_image = f'europe-central2-docker.pkg.dev/{project_id}/tfx-builder/tfx-trainer:latest'
    logger.info(f"Using custom TFX image: {custom_image}")

    runner = kubeflow_v2_dag_runner.KubeflowV2DagRunner(
        config=kubeflow_v2_dag_runner.KubeflowV2DagRunnerConfig(
            default_image=custom_image
        ),
        output_filename=output_file
    )
    runner.run(pipeline)
    logger.info("Pipeline compiled successfully")
    return output_file


def submit_to_vertex_ai(template_path: str, display_name: str, project_id: str, region: str):
    """Submit pipeline to Vertex AI."""
    from google.cloud import aiplatform

    logger.info(f"Initializing Vertex AI: project={project_id}, region={region}")
    aiplatform.init(project=project_id, location=region)

    logger.info(f"Creating pipeline job: {display_name}")
    pipeline_job = aiplatform.PipelineJob(
        display_name=display_name[:128],
        template_path=template_path,
        enable_caching=False,
    )

    logger.info("Submitting pipeline job...")
    pipeline_job.submit()
    resource_name = pipeline_job.resource_name
    logger.info(f"Pipeline submitted: {resource_name}")
    return resource_name


def write_result_to_gcs(bucket_name: str, blob_path: str, result: dict):
    """Write result JSON to GCS."""
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    content = json.dumps(result, indent=2)
    blob.upload_from_string(content, content_type="application/json")
    logger.info(f"Result written to gs://{bucket_name}/{blob_path}")


def main():
    parser = argparse.ArgumentParser(description="Compile and submit BigQueryExampleGen test pipeline")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--staging-bucket", required=True)
    parser.add_argument("--bigquery-query-b64", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", default="europe-central2")
    args = parser.parse_args()

    # Decode query
    bigquery_query = base64.b64decode(args.bigquery_query_b64).decode("utf-8")
    logger.info(f"Decoded query ({len(bigquery_query)} chars)")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_file = os.path.join(temp_dir, f"pipeline_{args.run_id}.json")

            pipeline = create_bq_example_gen_pipeline(
                pipeline_name=f"test-bq-examplegen-{args.run_id}",
                pipeline_root=f"gs://{args.staging_bucket}/test_bq_example_gen/{args.run_id}",
                bigquery_query=bigquery_query,
                project_id=args.project_id,
            )

            compile_pipeline(pipeline, pipeline_file, args.project_id)

            display_name = f"test-bq-examplegen-{args.run_id}"
            resource_name = submit_to_vertex_ai(
                pipeline_file, display_name, args.project_id, args.region
            )

            result = {
                "success": True,
                "run_id": args.run_id,
                "vertex_pipeline_job_name": resource_name,
                "display_name": display_name,
                "pipeline_root": f"gs://{args.staging_bucket}/test_bq_example_gen/{args.run_id}"
            }
            write_result_to_gcs(args.staging_bucket, f"test_results/{args.run_id}.json", result)

            logger.info("Test pipeline submitted successfully")
            print(f"PIPELINE_JOB_NAME={resource_name}")

    except Exception as e:
        logger.error(f"Pipeline submission failed: {e}")
        error_result = {"success": False, "run_id": args.run_id, "error": str(e)}
        try:
            write_result_to_gcs(args.staging_bucket, f"test_results/{args.run_id}.json", error_result)
        except Exception as gcs_error:
            logger.error(f"Failed to write error to GCS: {gcs_error}")
        raise


if __name__ == "__main__":
    main()
'''


def submit_via_cloud_build(query: str, run_id: str):
    """Submit the test pipeline via Cloud Build."""
    from google.cloud.devtools import cloudbuild_v1
    from google.cloud import storage

    logger.info(f"Submitting test pipeline via Cloud Build: {run_id}")

    # Upload compile script to GCS
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(STAGING_BUCKET)

    script_path = f"test_scripts/{run_id}/compile_bq_test.py"
    blob = bucket.blob(script_path)
    blob.upload_from_string(get_compile_script(), content_type='text/plain')
    logger.info(f"Uploaded compile script to gs://{STAGING_BUCKET}/{script_path}")

    # Base64 encode query
    query_b64 = base64.b64encode(query.encode()).decode()

    # Create Cloud Build job
    client = cloudbuild_v1.CloudBuildClient()

    build = cloudbuild_v1.Build(
        steps=[
            cloudbuild_v1.BuildStep(
                name=TFX_COMPILER_IMAGE,
                entrypoint='bash',
                args=[
                    '-c',
                    f'''
set -e
echo "TFX Compiler - BigQueryExampleGen Test"
python -c "import tfx; print(f'TFX version: {{tfx.__version__}}')"
python -c "from google.cloud import storage; storage.Client().bucket('{STAGING_BUCKET}').blob('{script_path}').download_to_filename('/tmp/compile_bq_test.py')"
python /tmp/compile_bq_test.py \\
    --run-id="{run_id}" \\
    --staging-bucket="{STAGING_BUCKET}" \\
    --bigquery-query-b64="{query_b64}" \\
    --project-id="{PROJECT_ID}" \\
    --region="{REGION}"
'''
                ],
            )
        ],
        timeout={'seconds': 600},
        options=cloudbuild_v1.BuildOptions(
            logging=cloudbuild_v1.BuildOptions.LoggingMode.CLOUD_LOGGING_ONLY,
            machine_type=cloudbuild_v1.BuildOptions.MachineType.E2_HIGHCPU_8,
        ),
    )

    operation = client.create_build(project_id=PROJECT_ID, build=build)
    build_id = operation.metadata.build.id

    logger.info(f"Cloud Build started: {build_id}")
    logger.info(f"Monitor at: https://console.cloud.google.com/cloud-build/builds/{build_id}?project={PROJECT_ID}")

    return build_id


def wait_for_result(run_id: str, timeout_seconds: int = 300):
    """Wait for the result JSON from GCS."""
    import time
    from google.cloud import storage

    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(STAGING_BUCKET)
    blob = bucket.blob(f"test_results/{run_id}.json")

    logger.info(f"Waiting for result: gs://{STAGING_BUCKET}/test_results/{run_id}.json")

    start_time = time.time()
    while (time.time() - start_time) < timeout_seconds:
        if blob.exists():
            content = blob.download_as_string().decode('utf-8')
            return json.loads(content)
        time.sleep(10)
        logger.info(f"  Still waiting... ({int(time.time() - start_time)}s)")

    return {"success": False, "error": f"Timeout after {timeout_seconds}s"}


def main():
    parser = argparse.ArgumentParser(description="Test BigQueryExampleGen with column aliases")
    parser.add_argument("--submit", action="store_true", help="Submit pipeline to Vertex AI")
    parser.add_argument("--dry-run", action="store_true", help="Just print the SQL query")
    parser.add_argument("--wait", action="store_true", help="Wait for Cloud Build result")
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 60)
        print("DRY RUN - SQL Query to be used:")
        print("=" * 60)
        query = get_test_query()
        print(query)
        print("=" * 60)
        print("\nColumn aliases in query:")
        if 'AS category' in query:
            print("  ✓ 'category' alias found")
        if 'AS sub_category' in query:
            print("  ✓ 'sub_category' alias found")
        return

    if args.submit:
        run_id = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        query = get_test_query()

        print("=" * 60)
        print(f"Submitting BigQueryExampleGen Test Pipeline")
        print(f"Run ID: {run_id}")
        print("=" * 60)

        build_id = submit_via_cloud_build(query, run_id)

        print(f"\nCloud Build ID: {build_id}")
        print(f"Run ID: {run_id}")
        print(f"\nMonitor Cloud Build:")
        print(f"  https://console.cloud.google.com/cloud-build/builds/{build_id}?project={PROJECT_ID}")
        print(f"\nAfter Cloud Build completes, monitor Vertex AI Pipeline:")
        print(f"  https://console.cloud.google.com/vertex-ai/pipelines/runs?project={PROJECT_ID}")
        print(f"\nResult will be at:")
        print(f"  gs://{STAGING_BUCKET}/test_results/{run_id}.json")
        print(f"\nTFRecords will be at:")
        print(f"  gs://{STAGING_BUCKET}/test_bq_example_gen/{run_id}/BigQueryExampleGen/examples/")

        if args.wait:
            print("\nWaiting for Cloud Build result...")
            result = wait_for_result(run_id, timeout_seconds=300)
            print(f"\nResult: {json.dumps(result, indent=2)}")

        return

    parser.print_help()


if __name__ == "__main__":
    main()
