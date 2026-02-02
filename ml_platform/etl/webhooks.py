"""
ETL Webhook Handlers

Handles Cloud Scheduler and external webhook callbacks for triggering ETL runs.
"""
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
import json
import os
import logging

from ml_platform.models import DataSource, ETLRun

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@csrf_exempt
def scheduler_webhook(request, data_source_id):
    """
    Webhook for Cloud Scheduler to trigger ETL runs.
    Accepts OIDC authenticated requests from Cloud Scheduler.
    No login required as this uses OIDC token authentication.
    """
    from django.utils import timezone
    from google.cloud import run_v2
    from django.conf import settings
    import os

    try:
        data_source = get_object_or_404(DataSource, id=data_source_id)
        model = data_source.etl_config.model_endpoint

        # Get GCP project ID
        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID'))
        if not project_id:
            return JsonResponse({
                'status': 'error',
                'message': 'GCP_PROJECT_ID not configured'
            }, status=500)

        # Count tables for this data source, default to 1 if none configured
        table_count = data_source.tables.filter(is_enabled=True).count()
        total_tables = table_count if table_count > 0 else 1

        # Create ETL run record (no user for scheduled runs)
        etl_run = ETLRun.objects.create(
            etl_config=data_source.etl_config,
            model_endpoint=model,
            data_source=data_source,  # Link run to specific data source
            status='pending',
            triggered_by=None,  # Scheduled runs have no user
            started_at=timezone.now(),
            total_sources=1,
            successful_sources=0,
            total_tables=total_tables,
            successful_tables=0,
        )

        # Trigger Cloud Run job
        try:
            client = run_v2.JobsClient()
            job_name = f'projects/{project_id}/locations/europe-central2/jobs/etl-runner'

            # Build execution request with arguments
            exec_request = run_v2.RunJobRequest(
                name=job_name,
                overrides=run_v2.RunJobRequest.Overrides(
                    container_overrides=[
                        run_v2.RunJobRequest.Overrides.ContainerOverride(
                            args=[
                                '--data_source_id', str(data_source_id),
                                '--etl_run_id', str(etl_run.id)
                            ]
                        )
                    ]
                )
            )

            # Execute the job
            operation = client.run_job(request=exec_request)

            # Extract operation name and execution name for logging/tracking
            operation_name = None
            execution_name = None

            if hasattr(operation, 'operation') and hasattr(operation.operation, 'name'):
                operation_name = operation.operation.name

            # Extract execution name from operation metadata
            try:
                if hasattr(operation, 'metadata') and operation.metadata:
                    metadata_name = getattr(operation.metadata, 'name', '')
                    if metadata_name and '/executions/' in metadata_name:
                        execution_name = metadata_name.split('/executions/')[-1]
                        logger.info(f"Scheduled ETL: extracted execution_name: {execution_name}")
            except Exception as meta_err:
                logger.warning(f"Could not extract execution_name from metadata: {meta_err}")

            # Update ETL run with execution details
            etl_run.cloud_run_execution_id = operation_name or 'triggered'
            etl_run.cloud_run_execution_name = execution_name or ''
            etl_run.status = 'running'
            etl_run.save()

            return JsonResponse({
                'status': 'success',
                'message': 'ETL job triggered successfully',
                'etl_run_id': etl_run.id,
                'execution_name': execution_name
            })

        except Exception as e:
            etl_run.status = 'failed'
            etl_run.error_message = str(e)
            etl_run.save()

            return JsonResponse({
                'status': 'error',
                'message': f'Failed to trigger Cloud Run job: {str(e)}',
                'etl_run_id': etl_run.id
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
