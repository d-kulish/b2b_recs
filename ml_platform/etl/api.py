"""
ETL REST API Endpoints

Handles all ETL-related API operations (JSON responses).
This module contains all ETL job management, run status, and Cloud Run integration APIs.
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
import json
import os
import logging

from ml_platform.models import (
    ModelEndpoint,
    ETLConfiguration,
    DataSource,
    DataSourceTable,
    ETLRun,
    Connection,
    ProcessedFile,
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def add_source(request, model_id):
    """
    API endpoint to add a new data source.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        etl_config = model.etl_config

        data = json.loads(request.body)

        print("=== ETL JOB CREATE DEBUG ===")
        print(f"Received data: {data}")
        print(f"Job name: {data.get('name')}")
        print(f"Connection ID: {data.get('connection_id')}")
        print(f"Tables: {data.get('tables')}")

        # Create data source
        # Check if using existing connection (new architecture)
        connection_id = data.get('connection_id')
        if connection_id:
            # Link to existing Connection
            from ml_platform.models import Connection
            connection = get_object_or_404(Connection, id=connection_id)

            source = DataSource.objects.create(
                etl_config=etl_config,
                connection=connection,  # NEW: Link to Connection
                name=data.get('name'),
                source_type=connection.source_type,
                is_enabled=data.get('is_enabled', True),
            )
        else:
            # Old architecture: store connection details directly
            source = DataSource.objects.create(
                etl_config=etl_config,
                name=data.get('name'),
                source_type=data.get('source_type'),
                source_host=data.get('source_host', ''),
                source_port=data.get('source_port'),
                source_database=data.get('source_database', ''),
                source_schema=data.get('source_schema', ''),
                bigquery_project=data.get('bigquery_project', ''),
                bigquery_dataset=data.get('bigquery_dataset', ''),
                file_path=data.get('file_path', ''),
                is_enabled=data.get('is_enabled', True),
            )

        # Create tables if provided
        tables_data = data.get('tables', [])
        for table_data in tables_data:
            DataSourceTable.objects.create(
                data_source=source,
                source_table_name=table_data.get('source_table_name'),
                dest_table_name=table_data.get('dest_table_name'),
                dest_dataset=table_data.get('dest_dataset', 'raw_data'),
                sync_mode=table_data.get('sync_mode', 'replace'),
                is_enabled=table_data.get('is_enabled', True),
            )

        return JsonResponse({
            'status': 'success',
            'message': 'Data source added successfully',
            'source_id': source.id,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["GET"])
def get_source(request, source_id):
    """
    API endpoint to get data source details for editing.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)

        # Get tables for this source with extended info for Edit modal
        tables = []
        for table in source.tables.all():
            tables.append({
                'id': table.id,
                'source_table_name': table.source_table_name,
                'dest_table_name': table.dest_table_name,
                'dest_dataset': table.dest_dataset,
                'sync_mode': table.sync_mode,
                'incremental_column': table.incremental_column or '',
                'row_limit': table.row_limit,
                'is_enabled': table.is_enabled,
                # Extended fields for Edit modal
                'load_type': table.load_type or 'transactional',
                'selected_columns': table.selected_columns or [],
                'timestamp_column': table.timestamp_column or '',
                'schema_name': table.schema_name or '',
            })

        # Get connection details (works for both old and new architecture)
        conn_details = source.get_connection_details()

        # Build response with connection details
        response_data = {
            'id': source.id,
            'name': source.name,
            'source_type': source.source_type,
            'source_host': conn_details.get('host') or '',
            'source_port': conn_details.get('port'),
            'source_database': conn_details.get('database') or '',
            'source_schema': conn_details.get('schema') or '',
            'bigquery_project': conn_details.get('bigquery_project') or '',
            'bigquery_dataset': conn_details.get('bigquery_dataset') or '',
            'file_path': conn_details.get('file_path') or '',
            'connection_string': conn_details.get('connection_string') or '',
            'is_enabled': source.is_enabled,
            'tables': tables,
            # Wizard fields (use getattr for backward compatibility)
            'wizard_last_step': getattr(source, 'wizard_last_step', 5),
            'wizard_completed_steps': getattr(source, 'wizard_completed_steps', None) or [],
            # Schedule info for Edit modal
            'schedule_type': getattr(source, 'schedule_type', 'manual') or 'manual',
            'cloud_scheduler_job_name': getattr(source, 'cloud_scheduler_job_name', '') or '',
        }

        # Add source_username and connection info if using Connection model
        if source.connection:
            response_data['source_username'] = source.connection.source_username or ''
            response_data['connection_id'] = source.connection.id
            response_data['connection_name'] = source.connection.name
            response_data['uses_saved_connection'] = True
        else:
            # Old architecture - no source_username field in DataSource
            response_data['source_username'] = ''
            response_data['uses_saved_connection'] = False

        return JsonResponse({
            'status': 'success',
            'source': response_data
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def update_source(request, source_id):
    """
    API endpoint to update an existing data source.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)
        data = json.loads(request.body)

        # Update source fields
        source.name = data.get('name', source.name)
        source.source_type = data.get('source_type', source.source_type)
        source.source_host = data.get('source_host', '')
        source.source_port = data.get('source_port')
        source.source_database = data.get('source_database', '')
        source.source_schema = data.get('source_schema', '')
        source.bigquery_project = data.get('bigquery_project', '')
        source.bigquery_dataset = data.get('bigquery_dataset', '')
        source.file_path = data.get('file_path', '')
        source.is_enabled = data.get('is_enabled', source.is_enabled)
        source.save()

        # Update tables if provided
        tables_data = data.get('tables', [])
        if tables_data:
            # Delete existing tables
            source.tables.all().delete()
            # Create new tables
            for table_data in tables_data:
                DataSourceTable.objects.create(
                    data_source=source,
                    source_table_name=table_data.get('source_table_name'),
                    dest_table_name=table_data.get('dest_table_name'),
                    dest_dataset=table_data.get('dest_dataset', 'raw_data'),
                    sync_mode=table_data.get('sync_mode', 'replace'),
                    incremental_column=table_data.get('incremental_column', ''),
                    row_limit=table_data.get('row_limit'),
                    is_enabled=table_data.get('is_enabled', True),
                )

            # Mark wizard as completed (all 5 steps done)
            source.wizard_last_step = 5
            source.wizard_completed_steps = [1, 2, 3, 4, 5]
            source.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Data source updated successfully',
            'source_id': source.id,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def test_connection_wizard(request):
    """
    API endpoint to test a data source connection during wizard (no saved source yet).
    """
    from ml_platform.utils.connection_manager import test_and_fetch_metadata

    try:
        data = json.loads(request.body)

        # Get connection parameters from request
        source_type = data.get('source_type')
        connection_params = {
            'host': data.get('host', ''),
            'port': data.get('port'),
            'database': data.get('database', ''),
            'username': data.get('username', ''),
            'password': data.get('password', ''),
            'project_id': data.get('project_id', ''),
            'dataset': data.get('dataset', ''),
            'service_account_json': data.get('service_account_json', ''),
            'connection_string': data.get('connection_string', ''),
        }

        # Test connection and get metadata
        result = test_and_fetch_metadata(source_type, connection_params)

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'tables': result['tables']
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Unexpected error: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def check_job_name(request, model_id):
    """
    Check if ETL job name already exists.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        etl_config = model.etl_config

        data = json.loads(request.body)
        job_name = data.get('name', '').strip()

        if not job_name:
            return JsonResponse({
                'status': 'error',
                'message': 'Job name is required',
            }, status=400)

        # Check if name exists
        exists = DataSource.objects.filter(etl_config=etl_config, name=job_name).exists()

        if exists:
            return JsonResponse({
                'status': 'error',
                'exists': True,
                'message': f'ETL job "{job_name}" already exists. Please choose a different name.',
            }, status=400)

        return JsonResponse({
            'status': 'success',
            'exists': False,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def save_draft_source(request, model_id):
    """
    API endpoint to save draft DataSource after successful connection test.
    Handles both saved connections and new connections.
    """
    from ml_platform.utils.connection_manager import save_credentials_to_secret_manager
    from ml_platform.models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        etl_config = model.etl_config

        data = json.loads(request.body)

        print("=== SAVE DRAFT DEBUG ===")
        print(f"Data received: {data}")

        # Extract job name
        source_name = data.get('name', 'Untitled Job')

        # Check if using saved connection or new connection
        connection_id = data.get('connection_id')

        if connection_id:
            # Using saved connection - link to it
            print(f"Using saved connection ID: {connection_id}")
            connection = get_object_or_404(Connection, id=connection_id)

            source = DataSource.objects.create(
                etl_config=etl_config,
                connection=connection,
                name=source_name,
                source_type=connection.source_type,
                is_enabled=False,  # Disabled until wizard is completed
                connection_tested=True,
                wizard_last_step=2,  # Draft saved at step 2
                wizard_completed_steps=[1, 2],  # Steps 1 and 2 completed
            )

            print(f"Draft created with ID: {source.id}")

            return JsonResponse({
                'status': 'success',
                'message': 'Draft ETL job saved',
                'source_id': source.id,
            })

        else:
            # New connection - use old flow
            print("Using new connection with params")
            connection_params = data.get('connection_params', {})
            source_type = data.get('source_type')

            # Prepare credentials for Secret Manager
            credentials_dict = {
                'host': connection_params.get('host', ''),
                'port': connection_params.get('port'),
                'database': connection_params.get('database', ''),
                'username': connection_params.get('username', ''),
                'password': connection_params.get('password', ''),
                'project_id': connection_params.get('project_id', ''),
                'dataset': connection_params.get('dataset', ''),
                'service_account_json': connection_params.get('service_account_json', ''),
                'connection_string': connection_params.get('connection_string', ''),
            }

            # Create draft DataSource
            source = DataSource.objects.create(
                etl_config=etl_config,
                name=source_name,
                source_type=source_type,
                source_host=credentials_dict['host'],
                source_port=credentials_dict['port'],
                source_database=credentials_dict['database'],
                source_schema=connection_params.get('schema', ''),
                bigquery_project=credentials_dict['project_id'],
                bigquery_dataset=credentials_dict['dataset'],
                connection_string=credentials_dict['connection_string'],
                is_enabled=False,  # Disabled until wizard is completed
                connection_tested=True,
                wizard_last_step=2,  # Draft saved at step 2
                wizard_completed_steps=[1, 2],  # Steps 1 and 2 completed
            )

        # Save credentials to Secret Manager
        try:
            secret_name = save_credentials_to_secret_manager(
                model_id=model_id,
                source_id=source.id,
                credentials_dict=credentials_dict
            )

            source.credentials_secret_name = secret_name
            source.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Connection saved as draft',
                'source_id': source.id,
            })

        except Exception as secret_error:
            # If Secret Manager fails, delete the DataSource
            source.delete()
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to save credentials: {str(secret_error)}',
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to save draft: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_connection(request, source_id):
    """
    API endpoint to test a data source connection.
    """
    from ml_platform.utils.connection_manager import test_and_fetch_metadata, save_credentials_to_secret_manager

    try:
        source = get_object_or_404(DataSource, id=source_id)
        data = json.loads(request.body)

        # Prepare connection parameters based on source type
        connection_params = {
            'host': source.source_host,
            'port': source.source_port,
            'database': source.source_database,
            'username': data.get('username', ''),
            'password': data.get('password', ''),
        }

        # Test connection and get metadata
        result = test_and_fetch_metadata(source.source_type, connection_params)

        if result['success']:
            # Save credentials to Secret Manager
            try:
                model_id = source.etl_config.model_endpoint.id
                secret_name = save_credentials_to_secret_manager(
                    model_id=model_id,
                    source_id=source.id,
                    credentials_dict=connection_params
                )

                # Update DataSource record
                source.connection_tested = True
                source.last_test_at = timezone.now()
                source.last_test_message = result['message']
                source.credentials_secret_name = secret_name
                source.save()

                return JsonResponse({
                    'status': 'success',
                    'message': result['message'],
                    'tables': result['tables']
                })

            except Exception as secret_error:
                # Connection worked but Secret Manager failed
                return JsonResponse({
                    'status': 'error',
                    'message': f'Connection successful, but failed to save credentials: {str(secret_error)}',
                }, status=500)

        else:
            # Connection failed
            source.connection_tested = False
            source.last_test_at = timezone.now()
            source.last_test_message = result['message']
            source.save()

            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Unexpected error: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_source(request, source_id):
    """
    API endpoint to delete a data source.
    Also deletes the associated Cloud Scheduler job if one exists.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)
        source_name = source.name

        # Delete Cloud Scheduler job if one exists
        if source.cloud_scheduler_job_name:
            from ml_platform.utils.cloud_scheduler import CloudSchedulerManager
            import os

            project_id = os.environ.get('GCP_PROJECT_ID', 'b2b-recs')
            region = os.environ.get('CLOUD_SCHEDULER_REGION', 'europe-central2')

            scheduler_manager = CloudSchedulerManager(
                project_id=project_id,
                region=region
            )

            delete_result = scheduler_manager.delete_etl_schedule(source.id)
            if not delete_result['success']:
                # Scheduler deletion failed - block DataSource deletion to prevent orphaned jobs
                return JsonResponse({
                    'status': 'error',
                    'message': f'Cannot delete ETL job: failed to delete scheduler. {delete_result["message"]}',
                }, status=500)

        source.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'Data source "{source_name}" deleted successfully',
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def toggle_pause(request, source_id):
    """
    API endpoint to pause/resume a data source's Cloud Scheduler job.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)

        # Check if source has a scheduler job
        if not source.cloud_scheduler_job_name:
            return JsonResponse({
                'status': 'error',
                'message': 'This ETL job does not have a scheduler configured. Only scheduled jobs can be paused.',
            }, status=400)

        # Import CloudSchedulerManager
        from ml_platform.utils.cloud_scheduler import CloudSchedulerManager
        import os

        project_id = os.environ.get('GCP_PROJECT_ID', 'b2b-recs')
        region = os.environ.get('CLOUD_SCHEDULER_REGION', 'europe-central2')

        scheduler_manager = CloudSchedulerManager(
            project_id=project_id,
            region=region
        )

        # Toggle based on current state
        if source.is_enabled:
            # Pause the scheduler
            result = scheduler_manager.pause_etl_schedule(source.id)
            if result['success']:
                source.is_enabled = False
                source.save()
                return JsonResponse({
                    'status': 'success',
                    'message': f'ETL job "{source.name}" paused successfully',
                    'is_enabled': False,
                    'action': 'paused'
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': result['message'],
                }, status=400)
        else:
            # Resume the scheduler
            result = scheduler_manager.resume_etl_schedule(source.id)
            if result['success']:
                source.is_enabled = True
                source.save()
                return JsonResponse({
                    'status': 'success',
                    'message': f'ETL job "{source.name}" resumed successfully',
                    'is_enabled': True,
                    'action': 'resumed'
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': result['message'],
                }, status=400)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def edit_source(request, source_id):
    """
    API endpoint to edit an ETL job (name, schedule, columns).
    Does not allow changing source connection, table, or destination.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)
        data = json.loads(request.body)

        # Get the first (and typically only) table for this source
        table = source.tables.first()
        if not table:
            return JsonResponse({
                'status': 'error',
                'message': 'No table configuration found for this ETL job',
            }, status=400)

        # Track what changed for response message
        changes = []

        # 1. Update job name if changed
        new_name = data.get('name', '').strip()
        if new_name and new_name != source.name:
            source.name = new_name
            changes.append('name')

        # 2. Update schedule if changed
        new_schedule_type = data.get('schedule_type', 'manual')
        old_schedule_type = source.schedule_type or 'manual'

        schedule_changed = new_schedule_type != old_schedule_type
        if schedule_changed:
            changes.append('schedule')

        # Handle schedule updates via Cloud Scheduler
        if schedule_changed or (new_schedule_type != 'manual' and 'schedule_time' in data):
            from ml_platform.utils.cloud_scheduler import CloudSchedulerManager
            import os

            project_id = os.environ.get('GCP_PROJECT_ID', 'b2b-recs')
            region = os.environ.get('CLOUD_SCHEDULER_REGION', 'europe-central2')

            scheduler_manager = CloudSchedulerManager(
                project_id=project_id,
                region=region
            )

            # Delete existing scheduler if changing from scheduled to manual
            if new_schedule_type == 'manual' and source.cloud_scheduler_job_name:
                delete_result = scheduler_manager.delete_etl_schedule(source.id)
                if not delete_result['success']:
                    # Log warning but continue (scheduler might not exist)
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to delete scheduler: {delete_result['message']}")
                source.cloud_scheduler_job_name = ''

            # Create/update scheduler for non-manual schedules
            elif new_schedule_type != 'manual':
                # Delete existing scheduler first
                if source.cloud_scheduler_job_name:
                    delete_result = scheduler_manager.delete_etl_schedule(source.id)
                    if not delete_result['success']:
                        return JsonResponse({
                            'status': 'error',
                            'message': f"Failed to update schedule: could not delete existing scheduler. {delete_result['message']}",
                        }, status=500)
                    # Clear the reference immediately after successful deletion
                    source.cloud_scheduler_job_name = ''

                # Build webhook URL
                django_base_url = f"{request.scheme}://{request.get_host()}"
                webhook_url = f"{django_base_url}/api/etl/sources/{source.id}/scheduler-webhook/"

                # Get service account
                service_account_email = os.environ.get(
                    'ETL_SERVICE_ACCOUNT',
                    f'etl-runner@{project_id}.iam.gserviceaccount.com'
                )

                # Create new scheduler
                create_result = scheduler_manager.create_etl_schedule(
                    data_source_id=source.id,
                    job_name=source.name,
                    schedule_type=new_schedule_type,
                    cloud_run_job_url=webhook_url,
                    service_account_email=service_account_email,
                    timezone='Europe/Kiev',
                    schedule_time=data.get('schedule_time', '09:00'),
                    schedule_minute=data.get('schedule_minute', 0),
                    schedule_day_of_week=data.get('schedule_day_of_week', 0),
                )

                if create_result['success']:
                    source.cloud_scheduler_job_name = create_result['job_name']
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f"Failed to create scheduler: {create_result['message']}",
                    }, status=400)

            source.schedule_type = new_schedule_type

        # 3. Update selected columns if changed
        new_columns = data.get('selected_columns', [])
        old_columns = table.selected_columns or []

        if set(new_columns) != set(old_columns):
            changes.append('columns')

            # Determine columns to add (new columns not in BigQuery)
            columns_to_add = [col for col in new_columns if col not in old_columns]

            # If there are new columns, we need to ALTER the BigQuery table
            if columns_to_add:
                try:
                    from google.cloud import bigquery

                    bq_client = bigquery.Client(project=os.environ.get('GCP_PROJECT_ID', 'b2b-recs'))
                    table_ref = f"{os.environ.get('GCP_PROJECT_ID', 'b2b-recs')}.{table.dest_dataset}.{table.dest_table_name}"

                    # Get current BigQuery table schema
                    bq_table = bq_client.get_table(table_ref)
                    existing_columns = {field.name for field in bq_table.schema}

                    # Add new columns that don't exist in BigQuery
                    new_schema = list(bq_table.schema)
                    for col_name in columns_to_add:
                        if col_name not in existing_columns:
                            # Default to STRING type - the actual type will be determined during ETL run
                            new_schema.append(bigquery.SchemaField(col_name, "STRING", mode="NULLABLE"))

                    if len(new_schema) > len(bq_table.schema):
                        bq_table.schema = new_schema
                        bq_client.update_table(bq_table, ["schema"])

                except Exception as bq_error:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to update BigQuery schema: {bq_error}")
                    # Continue anyway - the ETL run will handle schema updates

            # Update the selected columns in database
            table.selected_columns = new_columns
            table.save()

        # Save source changes
        source.save()

        # Build response message
        if changes:
            message = f"ETL job updated successfully. Changed: {', '.join(changes)}"
        else:
            message = "No changes detected"

        return JsonResponse({
            'status': 'success',
            'message': message,
            'changes': changes,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["GET"])
def available_columns(request, source_id):
    """
    API endpoint to fetch available columns from the source table.
    Used by the Edit modal to show columns that can be added/removed.
    Reuses the same connection_manager utility as the ETL wizard for consistency.
    """
    try:
        from ml_platform.utils.connection_manager import fetch_table_metadata, get_credentials_from_secret_manager

        source = get_object_or_404(DataSource, id=source_id)

        # Get the table configuration
        table = source.tables.first()
        if not table:
            return JsonResponse({
                'status': 'error',
                'message': 'No table configuration found',
            }, status=400)

        # Get currently selected columns
        currently_selected = table.selected_columns or []

        # Get connection
        connection = source.connection
        if not connection:
            return JsonResponse({
                'status': 'error',
                'message': 'No connection found for this ETL job',
            }, status=400)

        columns = []
        source_type = connection.source_type

        try:
            # Build connection params for fetch_table_metadata (same as wizard)
            connection_params = {}

            if source_type in ('postgresql', 'mysql', 'sqlserver', 'oracle', 'mariadb'):
                # Relational databases - get credentials from Secret Manager
                credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

                connection_params = {
                    'host': connection.source_host,
                    'port': connection.source_port,
                    'database': connection.source_database,
                    'username': connection.source_username,
                    'password': credentials.get('password', '') if credentials else '',
                }

                # Fetch columns using the wizard's utility
                result = fetch_table_metadata(
                    source_type=source_type,
                    schema_name=table.schema_name or 'public',
                    table_name=table.source_table_name,
                    connection_params=connection_params
                )

                if result['success']:
                    columns = [{'name': col['name'], 'type': col.get('bigquery_type', col.get('type', 'STRING'))} for col in result['columns']]
                else:
                    # Fallback to currently selected columns if fetch fails
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to fetch columns: {result.get('message', 'Unknown error')}")
                    columns = [{'name': col, 'type': 'STRING'} for col in currently_selected]

            elif source_type == 'bigquery':
                # BigQuery - get credentials from Secret Manager
                credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)
                service_account_json = json.dumps(credentials) if credentials else '{}'

                connection_params = {
                    'project_id': connection.bigquery_project,
                    'service_account_json': service_account_json,
                }

                result = fetch_table_metadata(
                    source_type='bigquery',
                    schema_name=connection.bigquery_dataset,  # For BQ, schema_name is dataset
                    table_name=table.source_table_name,
                    connection_params=connection_params
                )

                if result['success']:
                    columns = [{'name': col['name'], 'type': col.get('bigquery_type', col.get('type', 'STRING'))} for col in result['columns']]
                else:
                    columns = [{'name': col, 'type': 'STRING'} for col in currently_selected]

            elif source_type == 'firestore':
                # Firestore - get credentials from Secret Manager
                credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)
                service_account_json = json.dumps(credentials) if credentials else '{}'

                connection_params = {
                    'project_id': connection.bigquery_project,  # Firestore uses bigquery_project field for GCP project
                    'service_account_json': service_account_json,
                }

                result = fetch_table_metadata(
                    source_type='firestore',
                    schema_name='',  # Firestore doesn't use schema
                    table_name=table.source_table_name,  # Collection name
                    connection_params=connection_params
                )

                if result['success']:
                    columns = [{'name': col['name'], 'type': col.get('bigquery_type', col.get('type', 'STRING'))} for col in result['columns']]
                else:
                    columns = [{'name': col, 'type': 'STRING'} for col in currently_selected]

            elif source_type in ('gcs', 's3', 'azure_blob'):
                # For file-based sources, get columns from BigQuery destination table
                columns = _fetch_bq_destination_columns(table)

            else:
                # Fallback: return currently selected columns as available
                columns = [{'name': col, 'type': 'STRING'} for col in currently_selected]

        except Exception as fetch_error:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to fetch source columns: {fetch_error}")
            traceback.print_exc()
            # Fallback: return currently selected columns
            columns = [{'name': col, 'type': 'STRING'} for col in currently_selected]

        return JsonResponse({
            'status': 'success',
            'columns': columns,
            'currently_selected': currently_selected,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


def _fetch_bq_destination_columns(table):
    """Fetch columns from BigQuery destination table (for file-based sources)."""
    from google.cloud import bigquery
    import os

    client = bigquery.Client(project=os.environ.get('GCP_PROJECT_ID', 'b2b-recs'))
    table_ref = f"{os.environ.get('GCP_PROJECT_ID', 'b2b-recs')}.{table.dest_dataset}.{table.dest_table_name}"

    try:
        bq_table = client.get_table(table_ref)
        columns = []
        for field in bq_table.schema:
            columns.append({'name': field.name, 'type': field.field_type})
        return columns
    except Exception:
        return []


@login_required
@require_http_methods(["POST"])
def toggle_enabled(request, model_id):
    """
    API endpoint to enable/disable ETL scheduling.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        etl_config = model.etl_config

        data = json.loads(request.body)
        etl_config.is_enabled = data.get('enabled', not etl_config.is_enabled)
        etl_config.save()

        return JsonResponse({
            'status': 'success',
            'message': f'ETL {"enabled" if etl_config.is_enabled else "disabled"}',
            'is_enabled': etl_config.is_enabled,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def run_now(request, model_id):
    """
    API endpoint to trigger ETL run manually.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        etl_config = model.etl_config

        # Create ETL run record
        etl_run = ETLRun.objects.create(
            etl_config=etl_config,
            model_endpoint=model,
            status='pending',
            triggered_by=request.user,
            started_at=timezone.now(),
        )

        # TODO: Trigger actual Cloud Run ETL job
        # For now, simulate success
        etl_run.status = 'running'
        etl_run.save()

        return JsonResponse({
            'status': 'success',
            'message': 'ETL run started',
            'run_id': etl_run.id,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def run_source(request, source_id):
    """
    API endpoint to trigger ETL run for a single data source.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)
        etl_config = source.etl_config
        model = etl_config.model_endpoint

        # Create ETL run record for this specific source
        etl_run = ETLRun.objects.create(
            etl_config=etl_config,
            model_endpoint=model,
            data_source=source,  # Link run to specific data source
            status='pending',
            triggered_by=request.user,
            started_at=timezone.now(),
        )

        # TODO: Trigger actual Cloud Run ETL job for this specific source
        # For now, simulate success
        etl_run.status = 'running'
        etl_run.total_sources = 1
        etl_run.successful_sources = 0
        # Count tables, default to 1 if none configured (single-table ETL jobs)
        table_count = source.tables.filter(is_enabled=True).count()
        etl_run.total_tables = table_count if table_count > 0 else 1
        etl_run.successful_tables = 0
        etl_run.save()

        return JsonResponse({
            'status': 'success',
            'message': f'ETL run started for "{source.name}"',
            'run_id': etl_run.id,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
def run_status(request, run_id):
    """
    API endpoint to get ETL run status and details (for polling and View Details modal).
    """
    try:
        etl_run = get_object_or_404(ETLRun, id=run_id)

        # Build response with comprehensive run details
        response_data = {
            'run_id': etl_run.id,
            'status': etl_run.status,
            'started_at': etl_run.started_at.isoformat() if etl_run.started_at else None,
            'completed_at': etl_run.completed_at.isoformat() if etl_run.completed_at else None,
            'total_sources': etl_run.total_sources,
            'successful_sources': etl_run.successful_sources,
            'total_tables': etl_run.total_tables,
            'successful_tables': etl_run.successful_tables,
            'total_rows_extracted': etl_run.total_rows_extracted,
            'rows_loaded': etl_run.rows_loaded,
            'bytes_processed': etl_run.bytes_processed,
            'error_message': etl_run.error_message,
            'cloud_run_execution_id': etl_run.cloud_run_execution_id,
            'cloud_run_execution_name': etl_run.cloud_run_execution_name,
            'dataflow_job_id': etl_run.dataflow_job_id if etl_run.dataflow_job_id else None,
            'logs_url': etl_run.logs_url,
            # Timing breakdown
            'extraction_started_at': etl_run.extraction_started_at.isoformat() if etl_run.extraction_started_at else None,
            'extraction_completed_at': etl_run.extraction_completed_at.isoformat() if etl_run.extraction_completed_at else None,
            'loading_started_at': etl_run.loading_started_at.isoformat() if etl_run.loading_started_at else None,
            'loading_completed_at': etl_run.loading_completed_at.isoformat() if etl_run.loading_completed_at else None,
            'init_completed_at': etl_run.init_completed_at.isoformat() if etl_run.init_completed_at else None,
            'validation_completed_at': etl_run.validation_completed_at.isoformat() if etl_run.validation_completed_at else None,
            'error_type': etl_run.error_type or '',
            'duration_seconds': etl_run.get_duration_seconds(),
            # Detailed results if available
            'results_detail': etl_run.results_detail,
        }

        # Add data source info if available
        if etl_run.data_source:
            response_data['job_name'] = etl_run.data_source.name
            response_data['source_type'] = etl_run.data_source.source_type
            if etl_run.data_source.connection:
                response_data['connection_name'] = etl_run.data_source.connection.name
            else:
                response_data['connection_name'] = None
            # Get destination table name
            first_table = etl_run.data_source.tables.first()
            if first_table:
                response_data['destination_table'] = first_table.dest_table_name
                response_data['load_type'] = first_table.load_type
            else:
                response_data['destination_table'] = None
                response_data['load_type'] = None
        else:
            response_data['job_name'] = None
            response_data['source_type'] = None
            response_data['connection_name'] = None
            response_data['destination_table'] = None
            response_data['load_type'] = None

        # Add triggered by info
        if etl_run.triggered_by:
            response_data['triggered_by'] = etl_run.triggered_by.email or etl_run.triggered_by.username
        else:
            response_data['triggered_by'] = 'Scheduled'

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["GET"])
def run_logs(request, run_id):
    """
    Fetch Cloud Run Job logs for an ETL run.

    Returns logs from Cloud Logging, queried by execution_name if available,
    or by timestamp range as fallback.

    Query params:
        limit: Maximum number of log entries (default: 100)
    """
    from ml_platform.etl.etl_logs_service import EtlLogsService

    try:
        etl_run = get_object_or_404(ETLRun, id=run_id)

        # Get limit from query params
        limit = int(request.GET.get('limit', 100))

        # Fetch logs using the service
        service = EtlLogsService()
        result = service.get_logs(etl_run, limit=limit)

        return JsonResponse(result)

    except Exception as e:
        logger.exception(f"Error fetching logs for ETL run {run_id}: {e}")
        return JsonResponse({
            'available': False,
            'message': f"Failed to fetch logs: {str(e)}"
        }, status=500)


# ============================================================================
# Connection Management API Endpoints (New Architecture)
# ============================================================================
@login_required
@require_http_methods(["GET"])
def get_connections(request, model_id):
    """
    Get all connections for a model to populate ETL wizard Step 1.
    Returns connections with test status and usage count.
    """
    from ml_platform.models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)

        # Fetch all connections for this model
        connections = Connection.objects.filter(model_endpoint=model).order_by('name')

        # Build response data
        connections_data = []
        for conn in connections:
            connections_data.append({
                'id': conn.id,
                'name': conn.name,
                'source_type': conn.source_type,
                'source_type_display': conn.get_source_type_display(),
                'host': conn.source_host,
                'port': conn.source_port,
                'database': conn.source_database,
                'last_test_status': conn.last_test_status or 'untested',
                'last_test_at': conn.last_test_at.isoformat() if conn.last_test_at else None,
                'last_used_at': conn.last_used_at.isoformat() if conn.last_used_at else None,
                'jobs_count': conn.data_sources.count(),
                'is_enabled': conn.is_enabled,
            })

        return JsonResponse({
            'status': 'success',
            'connections': connections_data,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_connection_in_wizard(request, connection_id):
    """
    Test an existing connection from within ETL wizard.
    Does NOT create or modify anything, just tests and fetches tables.
    Updates connection last_test_at and last_test_status.
    """
    from ml_platform.models import Connection
    from ml_platform.utils.connection_manager import test_and_fetch_metadata
    from django.utils import timezone

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Build connection parameters from Connection object
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'schema': connection.source_schema,
            'username': connection.source_username,
            'credentials_secret_name': connection.credentials_secret_name,
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'connection_string': connection.connection_string,
            'service_account_json': connection.service_account_json,
        }

        # Test connection and get tables
        result = test_and_fetch_metadata(connection.source_type, connection_params)

        # Update connection test status
        connection.last_test_at = timezone.now()
        if result['success']:
            connection.last_test_status = 'success'
            connection.last_test_message = result.get('message', 'Connection successful')
        else:
            connection.last_test_status = 'failed'
            connection.last_test_message = result.get('message', 'Connection failed')
        connection.save()

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'tables': result.get('tables', []),
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Unexpected error: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def create_job(request, model_id):
    """
    Create complete ETL job with all configuration.
    Called at final wizard step only (no drafts).

    Payload:
    {
        "name": "daily_transactions",
        "connection_id": 5,
        "tables": [
            {
                "source_table_name": "transactions",
                "dest_table_name": "raw_transactions",
                "sync_mode": "incremental",
                "incremental_column": "updated_at"
            }
        ]
    }
    """
    from ml_platform.models import Connection, DataSourceTable
    from django.utils import timezone

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        etl_config = model.etl_config

        data = json.loads(request.body)

        # Extract and validate required fields
        job_name = data.get('name', '').strip()
        connection_id = data.get('connection_id')

        # Check if this is a file-based source
        is_file_based = data.get('is_file_based', False)

        # Database source fields
        schema_name = data.get('schema_name', '').strip()
        tables = data.get('tables', [])

        # File-based source fields (for cloud storage)
        file_path_prefix = data.get('file_path_prefix', '').strip()
        file_pattern = data.get('file_pattern', '').strip()
        file_format = data.get('file_format', '').strip()
        file_format_options = data.get('file_format_options', {})
        load_latest_only = data.get('load_latest_only', True)
        schema_fingerprint = data.get('schema_fingerprint', '').strip()

        # Extract Step 3 fields (Load Strategy)
        load_type = data.get('load_type', 'transactional')
        timestamp_column = data.get('timestamp_column', '').strip()
        historical_start_date = data.get('historical_start_date')
        selected_columns = data.get('selected_columns', [])

        # Extract Step 4 fields (BigQuery Table Setup)
        use_existing_table = data.get('use_existing_table', False)
        existing_table_name = data.get('existing_table_name', '').strip()
        bq_table_name = data.get('bigquery_table_name', '').strip()
        bq_schema_columns = data.get('bigquery_schema', [])

        # Extract Step 5 fields (Schedule) - RENAMED from Step 4
        schedule_config = data.get('schedule_config', {})
        schedule_type = schedule_config.get('schedule_type', 'manual')
        schedule_timezone = schedule_config.get('schedule_timezone', 'UTC')
        schedule_time = schedule_config.get('schedule_time')  # HH:MM format
        schedule_minute = schedule_config.get('schedule_minute')  # 0-59 for hourly
        schedule_day_of_week = schedule_config.get('schedule_day_of_week')  # 0-6
        schedule_day_of_month = schedule_config.get('schedule_day_of_month')  # 1-31

        if not job_name:
            return JsonResponse({
                'status': 'error',
                'message': 'ETL job name is required',
            }, status=400)

        if not connection_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Connection is required',
            }, status=400)

        # Validate based on source type
        if is_file_based:
            # File-based source validation
            if not file_pattern:
                return JsonResponse({
                    'status': 'error',
                    'message': 'File pattern is required for cloud storage sources',
                }, status=400)

            if not file_format:
                return JsonResponse({
                    'status': 'error',
                    'message': 'File format is required for cloud storage sources',
                }, status=400)
        else:
            # Database source validation
            if not tables or len(tables) == 0:
                return JsonResponse({
                    'status': 'error',
                    'message': 'At least one table must be selected',
                }, status=400)

        # Validate BigQuery table configuration
        if use_existing_table:
            if not existing_table_name:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Existing table name is required when using an existing table',
                }, status=400)
            # Use existing table name as the destination
            bq_table_name = existing_table_name
        else:
            if not bq_table_name:
                return JsonResponse({
                    'status': 'error',
                    'message': 'BigQuery table name is required',
                }, status=400)

        if not bq_schema_columns or len(bq_schema_columns) == 0:
            return JsonResponse({
                'status': 'error',
                'message': 'BigQuery schema must have at least one column',
            }, status=400)

        # Validate connection belongs to this model
        connection = get_object_or_404(Connection, id=connection_id, model_endpoint=model)

        # Check for duplicate job name
        if DataSource.objects.filter(etl_config=etl_config, name=job_name).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'ETL job "{job_name}" already exists. Please choose a different name.',
            }, status=400)

        # ============================================================
        # CREATE OR USE EXISTING BIGQUERY TABLE
        # ============================================================
        from ml_platform.utils.bigquery_manager import BigQueryTableManager
        import os
        from django.conf import settings
        import logging
        logger = logging.getLogger(__name__)

        # Get project ID (assumes you store it in settings or environment)
        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID'))
        if not project_id:
            return JsonResponse({
                'status': 'error',
                'message': 'GCP_PROJECT_ID not configured in settings',
            }, status=500)

        bq_manager = BigQueryTableManager(
            project_id=project_id,
            dataset_id='raw_data'
        )

        # Ensure dataset exists
        dataset_result = bq_manager.ensure_dataset_exists()
        if not dataset_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to create/verify dataset: {dataset_result["message"]}',
            }, status=500)

        if use_existing_table:
            # ============================================================
            # USE EXISTING TABLE MODE
            # ============================================================
            logger.info(f"Using existing BigQuery table: {existing_table_name}")

            # Verify table exists
            if not bq_manager.table_exists(existing_table_name):
                return JsonResponse({
                    'status': 'error',
                    'message': f'Table "{existing_table_name}" does not exist in dataset raw_data',
                }, status=400)

            # Get table metadata for load type validation
            table_metadata = bq_manager.get_table_metadata(existing_table_name)
            if not table_metadata['success']:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to get table metadata: {table_metadata["message"]}',
                }, status=500)

            existing_load_type = table_metadata['table']['load_type']

            # Validate load type compatibility (don't mix transactional and catalog)
            if existing_load_type != 'unknown' and existing_load_type != load_type:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Load type mismatch: existing table uses "{existing_load_type}" but you selected "{load_type}". Cannot mix load types.',
                }, status=400)

            # Add any new columns to existing table via ALTER TABLE
            add_result = bq_manager.add_columns_to_table(existing_table_name, bq_schema_columns)
            if not add_result['success']:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to add columns to existing table: {add_result["message"]}',
                }, status=500)

            if add_result['added_columns']:
                logger.info(f"Added columns to existing table: {add_result['added_columns']}")

            # Build table_result for consistency with new table path
            table_result = {
                'success': True,
                'full_table_id': f"{project_id}.raw_data.{existing_table_name}",
                'partitioned': table_metadata['table']['partitioned'],
                'message': f'Using existing table with {len(add_result["added_columns"])} new columns added' if add_result['added_columns'] else 'Using existing table'
            }

        else:
            # ============================================================
            # CREATE NEW TABLE MODE (original behavior)
            # ============================================================
            # Create description based on source type
            if is_file_based:
                table_description = f"ETL source: {file_pattern} files from {connection.name} ({load_type} load)"
            else:
                table_description = f"ETL source: {schema_name}.{tables[0]['source_table_name']} from {connection.name} ({load_type} load)"

            # Create BigQuery table
            table_result = bq_manager.create_table_from_schema(
                table_name=bq_table_name,
                schema_columns=bq_schema_columns,
                load_type=load_type,
                timestamp_column=timestamp_column if load_type == 'transactional' else None,
                description=table_description,
                overwrite=False  # Don't overwrite existing tables
            )

            if not table_result['success']:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to create BigQuery table: {table_result["message"]}',
                }, status=500)

            logger.info(f"Created BigQuery table: {table_result['full_table_id']}")

        # ============================================================
        # CREATE DATA SOURCE
        # ============================================================
        # Create DataSource (ETL job)
        data_source = DataSource.objects.create(
            etl_config=etl_config,
            connection=connection,
            name=job_name,
            source_type=connection.source_type,  # Denormalized from connection
            is_enabled=True,
            schedule_type=schedule_type,
            use_incremental=(load_type == 'transactional'),
            incremental_column=timestamp_column if load_type == 'transactional' else '',
            historical_start_date=historical_start_date,
        )

        # Create DataSourceTable objects
        if is_file_based:
            # Build column mapping from BigQuery schema (original_name -> sanitized_name)
            column_mapping = {}
            for col in bq_schema_columns:
                original_name = col.get('original_name')
                sanitized_name = col.get('name')
                if original_name and sanitized_name:
                    column_mapping[original_name] = sanitized_name

            # For file-based sources, create a single DataSourceTable with file config
            DataSourceTable.objects.create(
                data_source=data_source,
                schema_name='',  # Not applicable for files
                source_table_name=file_pattern,  # Use file pattern as source "table" name
                dest_table_name=bq_table_name,
                sync_mode='replace',  # Files don't use sync_mode
                # File-specific fields
                is_file_based=True,
                file_path_prefix=file_path_prefix,
                file_pattern=file_pattern,
                file_format=file_format,
                file_format_options=file_format_options,
                load_latest_only=load_latest_only,
                schema_fingerprint=schema_fingerprint,
                column_mapping=column_mapping,  # NEW: Store column name mapping
                # Common fields from Step 3, 4 & 5
                load_type=load_type,
                timestamp_column=timestamp_column if load_type == 'transactional' else '',
                historical_start_date=historical_start_date,
                selected_columns=selected_columns,
                schedule_type=schedule_type,
                schedule_time=schedule_time,
                schedule_minute=schedule_minute,
                schedule_day_of_week=schedule_day_of_week,
                schedule_day_of_month=schedule_day_of_month,
                schedule_timezone=schedule_timezone,
                is_enabled=True,
            )
        else:
            # For database sources, create DataSourceTable for each selected table
            for table_config in tables:
                source_table = table_config.get('source_table_name', '').strip()
                dest_table = table_config.get('dest_table_name', bq_table_name).strip()
                sync_mode = table_config.get('sync_mode', 'replace')
                incremental_column = table_config.get('incremental_column', '').strip()

                if source_table:
                    DataSourceTable.objects.create(
                        data_source=data_source,
                        schema_name=schema_name,
                        source_table_name=source_table,
                        dest_table_name=dest_table,
                        sync_mode=sync_mode,
                        incremental_column=incremental_column if sync_mode == 'incremental' else '',
                        # Database-specific
                        is_file_based=False,
                        # Common fields from Step 3, 4 & 5
                        load_type=load_type,
                        timestamp_column=timestamp_column,
                        historical_start_date=historical_start_date,
                        selected_columns=selected_columns,
                        schedule_type=schedule_type,
                        schedule_time=schedule_time,
                        schedule_minute=schedule_minute,
                        schedule_day_of_week=schedule_day_of_week,
                        schedule_day_of_month=schedule_day_of_month,
                        schedule_timezone=schedule_timezone,
                        is_enabled=True,
                    )

        # Update connection last_used_at
        connection.last_used_at = timezone.now()
        connection.save()

        # ============================================================
        # CREATE CLOUD SCHEDULER (if not manual)
        # ============================================================
        schedule_created = False
        scheduler_message = ''

        if schedule_type != 'manual':
            from ml_platform.utils.cloud_scheduler import CloudSchedulerManager

            try:
                scheduler_manager = CloudSchedulerManager(
                    project_id=project_id,
                    region='europe-central2'
                )

                # Build Django webhook URL dynamically from request
                # This works in both local dev and Cloud Run environments
                django_base_url = f"{request.scheme}://{request.get_host()}"
                webhook_url = f"{django_base_url}/api/etl/sources/{data_source.id}/scheduler-webhook/"
                service_account = f"etl-runner@{project_id}.iam.gserviceaccount.com"

                logger.info(f"Creating scheduler with webhook URL: {webhook_url}")

                scheduler_result = scheduler_manager.create_etl_schedule(
                    data_source_id=data_source.id,
                    job_name=job_name,
                    schedule_type=schedule_type,
                    cloud_run_job_url=webhook_url,
                    service_account_email=service_account,
                    timezone=schedule_timezone,
                    schedule_time=schedule_time,
                    schedule_minute=schedule_minute,
                    schedule_day_of_week=schedule_day_of_week,
                    schedule_day_of_month=schedule_day_of_month
                )

                if scheduler_result['success']:
                    # Save scheduler job name to DataSource
                    data_source.cloud_scheduler_job_name = scheduler_result['job_name']
                    data_source.save()

                    schedule_created = True
                    scheduler_message = scheduler_result['schedule']
                    logger.info(f"Created Cloud Scheduler job: {scheduler_result['job_name']}")
                else:
                    logger.warning(f"Failed to create Cloud Scheduler: {scheduler_result['message']}")
                    scheduler_message = scheduler_result['message']

            except Exception as e:
                logger.error(f"Error creating Cloud Scheduler: {str(e)}")
                scheduler_message = f"Scheduler creation failed: {str(e)}"

        return JsonResponse({
            'status': 'success',
            'message': f'ETL job "{job_name}" created successfully',
            'job_id': data_source.id,
            'job_name': data_source.name,
            'bigquery_table': table_result['full_table_id'],
            'bigquery_partitioned': table_result.get('partitioned', False),
            'schedule_created': schedule_created,
            'schedule_message': scheduler_message if scheduler_message else None,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error creating ETL job: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_bq_tables(request, dataset_id):
    """
    List all existing BigQuery tables in a dataset.
    Used in ETL wizard Step 4 to allow selecting existing tables.

    Returns:
        {
            'status': 'success',
            'tables': [
                {
                    'name': 'table_name',
                    'full_id': 'project.dataset.table',
                    'num_rows': 12345,
                    'load_type': 'transactional' or 'catalog' or 'unknown',
                    'partitioned': True/False,
                    'partition_field': 'field_name' or None
                }
            ]
        }
    """
    from ml_platform.utils.bigquery_manager import BigQueryTableManager
    import os
    from django.conf import settings

    try:
        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID'))
        if not project_id:
            return JsonResponse({
                'status': 'error',
                'message': 'GCP_PROJECT_ID not configured',
            }, status=500)

        bq_manager = BigQueryTableManager(
            project_id=project_id,
            dataset_id=dataset_id
        )

        result = bq_manager.list_tables()

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'tables': result['tables'],
                'message': result['message']
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error listing tables: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def validate_schema_compatibility(request):
    """
    Validate schema compatibility between source columns and existing BigQuery table.
    Used in ETL wizard Step 4 when user selects "Use existing table".

    Payload:
        {
            'source_columns': [
                {'name': 'col1', 'bigquery_type': 'STRING', ...},
                ...
            ],
            'existing_table_name': 'my_table',
            'load_type': 'transactional' or 'catalog'
        }

    Returns:
        {
            'status': 'success',
            'compatible': True/False,
            'load_type_compatible': True/False,
            'columns_to_add': [...],  # Source columns not in destination (will be added via ALTER TABLE)
            'columns_missing_in_source': [...],  # Dest columns not in source (will be NULL)
            'type_mismatches': [...],  # Incompatible type conversions
            'warnings': [...],
            'errors': [...]
        }
    """
    from ml_platform.utils.bigquery_manager import BigQueryTableManager
    import os
    from django.conf import settings

    try:
        data = json.loads(request.body)

        source_columns = data.get('source_columns', [])
        existing_table_name = data.get('existing_table_name', '').strip()
        requested_load_type = data.get('load_type', 'transactional')

        if not existing_table_name:
            return JsonResponse({
                'status': 'error',
                'message': 'existing_table_name is required',
            }, status=400)

        if not source_columns:
            return JsonResponse({
                'status': 'error',
                'message': 'source_columns is required',
            }, status=400)

        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID'))
        if not project_id:
            return JsonResponse({
                'status': 'error',
                'message': 'GCP_PROJECT_ID not configured',
            }, status=500)

        bq_manager = BigQueryTableManager(
            project_id=project_id,
            dataset_id='raw_data'
        )

        # Get existing table metadata
        table_result = bq_manager.get_table_metadata(existing_table_name)

        if not table_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f'Table not found: {table_result["message"]}',
            }, status=404)

        existing_table = table_result['table']
        existing_schema = {col['name']: col for col in existing_table['schema']}
        source_schema = {col['name']: col for col in source_columns}

        # Check load type compatibility
        existing_load_type = existing_table['load_type']
        load_type_compatible = True
        load_type_warning = None

        if existing_load_type != 'unknown' and existing_load_type != requested_load_type:
            load_type_compatible = False
            load_type_warning = f"Load type mismatch: table was created as '{existing_load_type}' but you selected '{requested_load_type}'. Mixing load types can cause data inconsistencies."

        # Find columns to add (in source but not in destination)
        columns_to_add = []
        for col_name, col_info in source_schema.items():
            if col_name not in existing_schema:
                columns_to_add.append({
                    'name': col_name,
                    'type': col_info.get('bigquery_type', 'STRING'),
                    'action': 'Will be added via ALTER TABLE'
                })

        # Find columns missing in source (in destination but not in source)
        columns_missing_in_source = []
        for col_name, col_info in existing_schema.items():
            if col_name not in source_schema:
                # Skip internal columns that ETL adds automatically
                if col_name.startswith('_'):
                    continue
                columns_missing_in_source.append({
                    'name': col_name,
                    'type': col_info['type'],
                    'action': 'Will be NULL for new rows'
                })

        # Check for type mismatches
        type_mismatches = []
        compatible_type_mappings = {
            # Source type -> allowed destination types
            # Note: INT64/INTEGER and FLOAT64/FLOAT are aliases in BigQuery
            'STRING': ['STRING'],
            'INT64': ['INT64', 'INTEGER', 'FLOAT64', 'FLOAT', 'NUMERIC', 'STRING'],
            'INTEGER': ['INT64', 'INTEGER', 'FLOAT64', 'FLOAT', 'NUMERIC', 'STRING'],
            'FLOAT64': ['FLOAT64', 'FLOAT', 'NUMERIC', 'STRING'],
            'FLOAT': ['FLOAT64', 'FLOAT', 'NUMERIC', 'STRING'],
            'NUMERIC': ['NUMERIC', 'FLOAT64', 'FLOAT', 'STRING'],
            'BIGNUMERIC': ['BIGNUMERIC', 'NUMERIC', 'STRING'],
            'BOOLEAN': ['BOOLEAN', 'BOOL', 'STRING'],
            'BOOL': ['BOOLEAN', 'BOOL', 'STRING'],
            'TIMESTAMP': ['TIMESTAMP', 'DATETIME', 'STRING'],
            'DATETIME': ['DATETIME', 'TIMESTAMP', 'STRING'],
            'DATE': ['DATE', 'STRING'],
            'TIME': ['TIME', 'STRING'],
            'BYTES': ['BYTES', 'STRING'],
            'JSON': ['JSON', 'STRING'],
        }

        for col_name, source_col in source_schema.items():
            if col_name in existing_schema:
                source_type = source_col.get('bigquery_type', 'STRING').upper()
                dest_type = existing_schema[col_name]['type'].upper()

                # Check if types are compatible
                allowed_types = compatible_type_mappings.get(source_type, [source_type])
                if dest_type not in allowed_types and source_type != dest_type:
                    type_mismatches.append({
                        'column': col_name,
                        'source_type': source_type,
                        'dest_type': dest_type,
                        'compatible': False,
                        'message': f"Incompatible types: cannot load {source_type} into {dest_type}"
                    })

        # Build warnings and errors
        warnings = []
        errors = []

        if load_type_warning:
            errors.append(load_type_warning)

        if columns_to_add:
            warnings.append(f"{len(columns_to_add)} column(s) will be added to the table: {', '.join([c['name'] for c in columns_to_add])}")

        if columns_missing_in_source:
            warnings.append(f"{len(columns_missing_in_source)} column(s) in destination table will be NULL: {', '.join([c['name'] for c in columns_missing_in_source])}")

        for mismatch in type_mismatches:
            errors.append(mismatch['message'])

        # Overall compatibility
        compatible = len(errors) == 0

        return JsonResponse({
            'status': 'success',
            'compatible': compatible,
            'load_type_compatible': load_type_compatible,
            'existing_table': {
                'name': existing_table['name'],
                'num_rows': existing_table['num_rows'],
                'load_type': existing_load_type,
                'partitioned': existing_table['partitioned'],
                'partition_field': existing_table['partition_field']
            },
            'columns_to_add': columns_to_add,
            'columns_missing_in_source': columns_missing_in_source,
            'type_mismatches': type_mismatches,
            'warnings': warnings,
            'errors': errors
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Error validating schema: {str(e)}',
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def job_config(request, data_source_id):
    """
    Get ETL job configuration for the ETL runner.
    Called by Cloud Run ETL runner to fetch job details.

    Returns complete configuration needed to execute ETL job.
    """
    from ml_platform.utils.connection_manager import get_credentials_from_secret_manager

    try:
        data_source = get_object_or_404(DataSource, id=data_source_id)

        # Get first table (for now we support single table per job)
        table = data_source.tables.first()
        if not table:
            return JsonResponse({
                'status': 'error',
                'message': 'No tables configured for this data source'
            }, status=400)

        # Get connection
        connection = data_source.connection
        if not connection:
            return JsonResponse({
                'status': 'error',
                'message': 'No connection associated with this data source'
            }, status=400)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection'
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Determine if this is a file-based source
        is_file_source = connection.source_type in ['gcs', 's3', 'azure_blob']

        # Build connection parameters based on source type
        if is_file_source:
            # File-based sources (GCS, S3, Azure Blob)
            # Extract bucket name with backward compatibility (bucket_path first, fallback to source_host)
            bucket_name = None

            if connection.source_type == 'gcs':
                # Try bucket_path first (primary), fallback to source_host (legacy)
                bucket_path = connection.bucket_path or (f'gs://{connection.source_host}' if connection.source_host else '')
                if bucket_path and bucket_path.startswith('gs://'):
                    bucket_name = bucket_path.replace('gs://', '').split('/')[0]
                elif bucket_path:
                    bucket_name = bucket_path.split('/')[0]

            elif connection.source_type == 's3':
                bucket_path = connection.bucket_path or (f's3://{connection.source_host}' if connection.source_host else '')
                if bucket_path and bucket_path.startswith('s3://'):
                    bucket_name = bucket_path.replace('s3://', '').split('/')[0]
                elif bucket_path:
                    bucket_name = bucket_path.split('/')[0]

            elif connection.source_type == 'azure_blob':
                bucket_name = connection.bucket_path or connection.source_host

            connection_params = {
                'source_type': connection.source_type,
                'bucket': bucket_name,
                'credentials': credentials,  # Cloud storage credentials (service account JSON or access keys)
            }
        elif connection.source_type == 'bigquery':
            # BigQuery source - different parameters
            connection_params = {
                'source_type': 'bigquery',
                'source_project': connection.bigquery_project or connection.source_database,
                'source_dataset': connection.bigquery_dataset or table.schema_name,
                'bigquery_project': connection.bigquery_project or connection.source_database,
                'bigquery_dataset': connection.bigquery_dataset or table.schema_name,
                'credentials': credentials,  # Service account JSON
            }
        elif connection.source_type == 'firestore':
            # Firestore (NoSQL) source - similar to BigQuery
            # DEBUG: Log credentials structure
            print(f"DEBUG: Raw credentials from Secret Manager: {type(credentials)}")
            print(f"DEBUG: Credentials keys: {credentials.keys() if isinstance(credentials, dict) else 'N/A'}")

            # Ensure credentials are in the format the extractor expects
            credentials_wrapped = {
                'service_account_json': credentials.get('service_account_json', json.dumps(credentials))
            }

            print(f"DEBUG: Wrapped credentials: {credentials_wrapped}")
            print(f"DEBUG: service_account_json present: {'service_account_json' in credentials_wrapped}")
            print(f"DEBUG: service_account_json value length: {len(str(credentials_wrapped.get('service_account_json', '')))}")

            connection_params = {
                'source_type': 'firestore',
                'project_id': connection.bigquery_project or connection.source_database,
                'bigquery_project': connection.bigquery_project or connection.source_database,
                'credentials': credentials_wrapped,  # Wrapped service account JSON
            }
        else:
            # Database sources (PostgreSQL, MySQL, etc.)
            connection_params = {
                'source_type': connection.source_type,
                'host': connection.source_host,
                'port': connection.source_port,
                'database': connection.source_database,
                'username': credentials.get('username', ''),
                'password': credentials.get('password', ''),
            }

        # Determine load type
        load_type = table.load_type if hasattr(table, 'load_type') else ('transactional' if data_source.use_incremental else 'catalog')

        # Build base job configuration
        config = {
            'source_type': connection.source_type,
            'connection_params': connection_params,
            'source_table_name': table.source_table_name,
            'schema_name': table.schema_name or connection.source_database,
            'dest_table_name': table.dest_table_name,
            'load_type': load_type,
            'timestamp_column': data_source.incremental_column or table.incremental_column or '',
            'selected_columns': table.selected_columns if hasattr(table, 'selected_columns') and table.selected_columns else [],
            'last_sync_value': data_source.last_sync_value or '',
            'historical_start_date': data_source.historical_start_date.isoformat() if data_source.historical_start_date else None,
            # Processing mode configuration (for conditional Dataflow usage)
            'processing_mode': table.processing_mode if hasattr(table, 'processing_mode') else 'auto',
            'row_count_threshold': table.row_count_threshold if hasattr(table, 'row_count_threshold') else 1_000_000,
        }

        # Add file-specific configuration if this is a file source
        if is_file_source:
            config.update({
                'file_path_prefix': table.file_path_prefix if hasattr(table, 'file_path_prefix') else '',
                'file_pattern': table.file_pattern if hasattr(table, 'file_pattern') else '*',
                'file_format': table.file_format if hasattr(table, 'file_format') else 'csv',
                'file_format_options': table.file_format_options if hasattr(table, 'file_format_options') else {},
                'selected_files': table.selected_files if hasattr(table, 'selected_files') else [],
                'load_latest_only': table.load_latest_only if hasattr(table, 'load_latest_only') else False,
                'column_mapping': table.column_mapping if hasattr(table, 'column_mapping') else {},  # NEW: Column name mapping
            })

        return JsonResponse(config)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["PATCH"])
def run_update(request, run_id):
    """
    Update ETL run status and progress.
    Called by Cloud Run ETL runner to report progress.

    Payload examples:
    {"status": "running", "data_source_id": 5}
    {"status": "completed", "data_source_id": 5, "rows_extracted": 1000, "rows_loaded": 1000, "duration_seconds": 120}
    {"status": "completed", "data_source_id": 5, "rows_extracted": 100, "max_extracted_timestamp": "2024-11-30T08:30:00"}
    {"rows_extracted": 5000, "rows_loaded": 5000}

    For transactional loads, max_extracted_timestamp updates DataSource.last_sync_value
    so the next run starts from where the previous run ended.
    """
    from django.utils import timezone

    try:
        etl_run = get_object_or_404(ETLRun, id=run_id)
        data = json.loads(request.body)

        # Update status if provided
        if 'status' in data:
            etl_run.status = data['status']

            # Set timestamps based on status
            if data['status'] == 'running' and not etl_run.started_at:
                etl_run.started_at = timezone.now()
            elif data['status'] in ['completed', 'failed', 'cancelled'] and not etl_run.completed_at:
                etl_run.completed_at = timezone.now()

            # Auto-update successful_tables and successful_sources based on final status
            if data['status'] == 'completed':
                # All tables/sources successful if job completed
                etl_run.successful_tables = etl_run.total_tables
                etl_run.successful_sources = etl_run.total_sources
            elif data['status'] == 'partial':
                # Partial success - at least some tables succeeded
                etl_run.successful_tables = max(0, etl_run.total_tables - 1)
                etl_run.successful_sources = etl_run.total_sources
            elif data['status'] in ['failed', 'cancelled']:
                # No tables successful if job failed/cancelled
                etl_run.successful_tables = 0
                etl_run.successful_sources = 0

        # Update metrics if provided
        if 'rows_extracted' in data:
            etl_run.total_rows_extracted = data['rows_extracted']
        if 'rows_loaded' in data:
            etl_run.rows_loaded = data['rows_loaded']
        if 'bytes_processed' in data:
            etl_run.bytes_processed = data['bytes_processed']
        if 'duration_seconds' in data:
            etl_run.duration_seconds = data['duration_seconds']
        if 'error_message' in data:
            etl_run.error_message = data['error_message']
        if 'dataflow_job_id' in data:
            etl_run.dataflow_job_id = data['dataflow_job_id']

        # Update error_type if provided (for failed runs)
        if 'error_type' in data:
            etl_run.error_type = data['error_type']

        # Update phase timestamps if provided (4-stage pipeline: INIT → VALIDATE → EXTRACT → LOAD)
        if 'init_completed_at' in data:
            etl_run.init_completed_at = timezone.now()
        if 'validation_completed_at' in data:
            etl_run.validation_completed_at = timezone.now()
        if 'extraction_started_at' in data:
            etl_run.extraction_started_at = timezone.now()
        if 'extraction_completed_at' in data:
            etl_run.extraction_completed_at = timezone.now()
        if 'loading_started_at' in data:
            etl_run.loading_started_at = timezone.now()
        if 'loading_completed_at' in data:
            etl_run.loading_completed_at = timezone.now()

        etl_run.save()

        # Update DataSource last run info if data_source_id provided and status is terminal
        if 'data_source_id' in data and 'status' in data and data['status'] in ['completed', 'failed', 'cancelled']:
            try:
                data_source = DataSource.objects.get(id=data['data_source_id'])
                data_source.last_run_at = timezone.now()
                data_source.last_run_status = data['status']

                # Only include fields that are actually being modified
                update_fields = ['last_run_at', 'last_run_status']

                if 'error_message' in data:
                    data_source.last_run_message = data['error_message']
                    update_fields.append('last_run_message')
                else:
                    # Clear any previous error message on success
                    data_source.last_run_message = ''
                    update_fields.append('last_run_message')

                # Update last_sync_value for successful transactional loads
                if data['status'] == 'completed' and 'max_extracted_timestamp' in data:
                    max_ts = data['max_extracted_timestamp']
                    if max_ts:
                        # Ensure max_ts is a string (handle various timestamp formats)
                        if hasattr(max_ts, 'isoformat'):
                            max_ts = max_ts.isoformat()
                        else:
                            max_ts = str(max_ts)
                        data_source.last_sync_value = max_ts
                        update_fields.append('last_sync_value')
                        logger.info(f"Updated last_sync_value to {max_ts} for DataSource {data_source.id}")

                data_source.save(update_fields=update_fields)
                logger.info(f"DataSource {data_source.id} updated successfully with fields: {update_fields}")
            except DataSource.DoesNotExist:
                logger.warning(f"DataSource {data['data_source_id']} not found, skipping update")
            except Exception as ds_error:
                logger.exception(f"Error updating DataSource {data.get('data_source_id')}: {str(ds_error)}")

        return JsonResponse({
            'status': 'success',
            'message': 'ETL run updated successfully'
        })

    except Exception as e:
        logger.exception(f"Error updating ETL run {run_id}: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def api_etl_scheduler_webhook(request, data_source_id):
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

        # Create ETL run record (no user for scheduled runs)
        etl_run = ETLRun.objects.create(
            etl_config=data_source.etl_config,
            model_endpoint=model,
            data_source=data_source,  # Link run to specific data source
            status='pending',
            triggered_by=None,  # Scheduled runs have no user
            started_at=timezone.now(),
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

            return JsonResponse({
                'status': 'success',
                'message': 'ETL job triggered successfully',
                'etl_run_id': etl_run.id
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


@login_required
@require_http_methods(["POST"])
def trigger_now(request, data_source_id):
    """
    Manually trigger an ETL run for a data source.
    Creates an ETL run record and triggers the Cloud Run job.
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

        # Create ETL run record
        etl_run = ETLRun.objects.create(
            etl_config=data_source.etl_config,
            model_endpoint=model,
            data_source=data_source,  # Link run to specific data source for card display
            status='pending',
            triggered_by=request.user,
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

            operation = client.run_job(request=exec_request)

            # Extract operation name and execution name for logging/tracking
            # Note: operation.result() would block until completion, so we extract from metadata
            operation_name = None
            execution_name = None

            if hasattr(operation, 'operation') and hasattr(operation.operation, 'name'):
                operation_name = operation.operation.name

            # Extract execution name from operation metadata
            # The metadata contains the Execution resource being created
            try:
                if hasattr(operation, 'metadata') and operation.metadata:
                    # metadata.name format: projects/{project}/locations/{loc}/jobs/{job}/executions/{exec_name}
                    metadata_name = getattr(operation.metadata, 'name', '')
                    if metadata_name and '/executions/' in metadata_name:
                        execution_name = metadata_name.split('/executions/')[-1]
                        logger.info(f"Extracted execution_name from metadata: {execution_name}")
            except Exception as meta_err:
                logger.warning(f"Could not extract execution_name from metadata: {meta_err}")

            etl_run.cloud_run_execution_id = operation_name or 'triggered'
            etl_run.cloud_run_execution_name = execution_name or ''
            etl_run.status = 'running'
            etl_run.save()

            return JsonResponse({
                'status': 'success',
                'message': f'ETL run triggered for "{data_source.name}"',
                'run_id': etl_run.id,
                'operation_name': operation_name,
                'execution_name': execution_name
            })

        except Exception as e:
            # Update ETL run to failed
            etl_run.status = 'failed'
            etl_run.error_message = f'Failed to trigger Cloud Run job: {str(e)}'
            etl_run.completed_at = timezone.now()
            etl_run.save()

            return JsonResponse({
                'status': 'error',
                'message': f'Failed to trigger ETL run: {str(e)}'
            }, status=500)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_processed_files(request, data_source_id):
    """
    Get list of previously processed files for a file-based data source.
    Used by ETL runner for incremental file loading.

    Returns:
        JSON with list of processed files including metadata
    """
    try:
        data_source = get_object_or_404(DataSource, id=data_source_id)

        # Get all tables for this data source
        tables = data_source.tables.filter(is_file_based=True)

        if not tables.exists():
            return JsonResponse({
                'status': 'success',
                'processed_files': []
            })

        # Get processed files from the first (and typically only) table
        # Note: File-based sources have one DataSourceTable per DataSource
        table = tables.first()

        processed_files = ProcessedFile.objects.filter(
            data_source_table=table
        ).order_by('-processed_at')

        # Convert to list of dicts
        files_data = []
        for pf in processed_files:
            files_data.append({
                'file_path': pf.file_path,
                'file_size_bytes': pf.file_size_bytes,
                'file_last_modified': pf.file_last_modified.isoformat() if pf.file_last_modified else None,
                'rows_loaded': pf.rows_loaded,
                'processed_at': pf.processed_at.isoformat() if pf.processed_at else None
            })

        return JsonResponse({
            'status': 'success',
            'processed_files': files_data,
            'count': len(files_data)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def record_processed_file(request, data_source_id):
    """
    Record a file as processed in the ProcessedFile table.
    Called by ETL runner after successfully loading a file to BigQuery.

    Payload:
        {
            "file_path": "path/to/file.csv",
            "file_size_bytes": 12345,
            "file_last_modified": "2024-11-20T10:30:00",
            "rows_loaded": 1000
        }
    """
    try:
        data_source = get_object_or_404(DataSource, id=data_source_id)

        # Parse request body
        data = json.loads(request.body)

        file_path = data.get('file_path')
        file_size_bytes = data.get('file_size_bytes')
        file_last_modified_str = data.get('file_last_modified')
        rows_loaded = data.get('rows_loaded', 0)

        if not file_path or file_size_bytes is None:
            return JsonResponse({
                'status': 'error',
                'message': 'file_path and file_size_bytes are required'
            }, status=400)

        # Parse file_last_modified datetime
        from dateutil import parser as date_parser
        from django.utils import timezone as django_timezone

        file_last_modified = None
        if file_last_modified_str:
            try:
                # Parse ISO format datetime
                file_last_modified = date_parser.isoparse(file_last_modified_str)
                # Make timezone-aware if needed
                if file_last_modified.tzinfo is None:
                    file_last_modified = django_timezone.make_aware(file_last_modified)
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Invalid file_last_modified format: {str(e)}'
                }, status=400)

        # Get the DataSourceTable (should be only one for file-based sources)
        tables = data_source.tables.filter(is_file_based=True)
        if not tables.exists():
            return JsonResponse({
                'status': 'error',
                'message': 'No file-based table found for this data source'
            }, status=404)

        table = tables.first()

        # Create or update ProcessedFile record
        processed_file, created = ProcessedFile.objects.update_or_create(
            data_source_table=table,
            file_path=file_path,
            defaults={
                'file_size_bytes': file_size_bytes,
                'file_last_modified': file_last_modified,
                'rows_loaded': rows_loaded,
                'processed_at': django_timezone.now()
            }
        )

        return JsonResponse({
            'status': 'success',
            'message': 'File recorded successfully',
            'file_path': file_path,
            'created': created  # True if new record, False if updated
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def etl_dashboard_stats(request, model_id):
    """
    API endpoint for ETL Dashboard chapter on the main Dashboard page.
    Returns KPIs, scheduled jobs, and bubble chart data.

    This endpoint reuses the same computation logic as the ETL page view
    to ensure data consistency.
    """
    from datetime import timedelta
    from django.db.models import Q, Sum, Count
    import os

    model = get_object_or_404(ModelEndpoint, id=model_id)

    # Get or create ETL configuration
    try:
        etl_config = model.etl_config
    except ETLConfiguration.DoesNotExist:
        # No ETL config - return empty state
        return JsonResponse({
            'success': True,
            'data': {
                'kpi': {
                    'total_runs': 0,
                    'completed_runs': 0,
                    'failed_runs': 0,
                    'successful_runs': 0,
                    'success_rate': 0,
                    'total_rows_extracted': 0,
                    'avg_duration_seconds': 0,
                },
                'scheduled_jobs': [],
                'scheduled_jobs_total': 0,
                'bubble_chart': {
                    'runs': [],
                    'job_names': [],
                    'date_range': {
                        'start': timezone.now().isoformat(),
                        'end': timezone.now().isoformat(),
                    },
                    'duration_stats': {
                        'min': 1,
                        'max': 1,
                    },
                },
            }
        })

    data_sources = etl_config.data_sources.all().select_related('connection').prefetch_related('tables')

    # =========================================================================
    # KPI Dashboard Aggregations (Last 30 Days)
    # =========================================================================
    cutoff_date = timezone.now() - timedelta(days=30)
    kpi_runs = model.etl_runs.filter(started_at__gte=cutoff_date)

    # Aggregate metrics
    kpi_aggregates = kpi_runs.aggregate(
        total_runs=Count('id'),
        completed_runs=Count('id', filter=Q(status='completed')),
        failed_runs=Count('id', filter=Q(status='failed')),
        partial_runs=Count('id', filter=Q(status='partial')),
        total_rows_extracted=Sum('total_rows_extracted'),
    )

    # Calculate average duration from timestamps
    completed_runs_with_times = kpi_runs.filter(
        status__in=['completed', 'partial'],
        started_at__isnull=False,
        completed_at__isnull=False
    )

    avg_duration_seconds = 0
    if completed_runs_with_times.exists():
        total_duration = 0
        count = 0
        for run in completed_runs_with_times:
            if run.started_at and run.completed_at:
                duration = (run.completed_at - run.started_at).total_seconds()
                if duration > 0:
                    total_duration += duration
                    count += 1
        if count > 0:
            avg_duration_seconds = total_duration / count

    # Calculate success rate
    total_runs = kpi_aggregates['total_runs'] or 0
    completed_runs = kpi_aggregates['completed_runs'] or 0
    partial_runs = kpi_aggregates['partial_runs'] or 0
    successful_runs = completed_runs + partial_runs
    success_rate = round((successful_runs / total_runs * 100), 1) if total_runs > 0 else 0

    kpi_data = {
        'total_runs': total_runs,
        'completed_runs': completed_runs,
        'failed_runs': kpi_aggregates['failed_runs'] or 0,
        'successful_runs': successful_runs,
        'success_rate': success_rate,
        'total_rows_extracted': kpi_aggregates['total_rows_extracted'] or 0,
        'avg_duration_seconds': round(avg_duration_seconds),
    }

    # =========================================================================
    # Scheduled Jobs
    # =========================================================================
    scheduled_jobs_list = []

    scheduled_sources = data_sources.filter(
        schedule_type__in=['hourly', 'daily', 'weekly', 'monthly'],
        cloud_scheduler_job_name__isnull=False
    ).exclude(cloud_scheduler_job_name='')

    if scheduled_sources.exists():
        from django.conf import settings

        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID'))
        region = os.getenv('CLOUD_SCHEDULER_REGION', 'europe-central2')

        if project_id:
            try:
                from ml_platform.utils.cloud_scheduler import CloudSchedulerManager
                scheduler_manager = CloudSchedulerManager(project_id=project_id, region=region)

                enabled_jobs = []
                paused_jobs = []

                for source in scheduled_sources:
                    # Get schedule display string
                    schedule_display = _get_schedule_display_api(source)

                    # Fetch status from Cloud Scheduler
                    try:
                        status = scheduler_manager.get_schedule_status(source.cloud_scheduler_job_name)
                        next_run_time = status.get('next_run_time') if status.get('success') else None
                        state = status.get('state', 'UNKNOWN') if status.get('success') else 'UNKNOWN'
                        is_paused = state == 'PAUSED'
                    except Exception:
                        next_run_time = None
                        state = 'UNKNOWN'
                        is_paused = not source.is_enabled

                    job_info = {
                        'id': source.id,
                        'name': source.name,
                        'schedule_type': source.schedule_type,
                        'schedule_display': schedule_display,
                        'next_run_time': next_run_time.isoformat() if next_run_time else None,
                        'state': state,
                        'is_paused': is_paused,
                    }

                    if is_paused:
                        paused_jobs.append(job_info)
                    else:
                        enabled_jobs.append(job_info)

                # Sort: enabled by next_run_time, paused alphabetically
                from datetime import datetime as dt
                far_future = dt(2099, 12, 31)
                enabled_jobs.sort(key=lambda x: x['next_run_time'] or far_future.isoformat())
                paused_jobs.sort(key=lambda x: x['name'].lower())

                scheduled_jobs_list = enabled_jobs + paused_jobs

            except ImportError:
                pass
            except Exception:
                pass

    # =========================================================================
    # Bubble Chart Data (Last 5 Days)
    # =========================================================================
    bubble_cutoff_date = timezone.now() - timedelta(days=5)
    all_runs_5_days = model.etl_runs.filter(
        started_at__gte=bubble_cutoff_date,
        status__in=['completed', 'partial', 'failed']
    ).select_related('data_source').order_by('started_at')

    bubble_runs = []
    all_job_names = set()
    durations = []

    for run in all_runs_5_days:
        if not run.data_source or not run.started_at:
            continue

        job_name = run.data_source.name
        duration = run.get_duration_seconds() or 0
        rows_loaded = run.total_rows_extracted or 0

        if run.status == 'completed':
            status = 'completed'
        elif run.status == 'partial':
            status = 'partial'
        else:
            status = 'failed'

        all_job_names.add(job_name)
        if duration > 0:
            durations.append(duration)

        bubble_runs.append({
            'job_name': job_name,
            'started_at': run.started_at.isoformat(),
            'duration': duration,
            'status': status,
            'rows_loaded': rows_loaded,
        })

    min_duration = min(durations) if durations else 1
    max_duration = max(durations) if durations else 1

    now = timezone.now()
    start_date = (now - timedelta(days=4)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now.replace(hour=23, minute=59, second=59, microsecond=0)

    sorted_job_names = sorted(list(all_job_names))

    bubble_chart_data = {
        'runs': bubble_runs,
        'job_names': sorted_job_names,
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        },
        'duration_stats': {
            'min': min_duration,
            'max': max_duration,
        },
    }

    return JsonResponse({
        'success': True,
        'data': {
            'kpi': kpi_data,
            'scheduled_jobs': scheduled_jobs_list,
            'scheduled_jobs_total': len(scheduled_jobs_list),
            'bubble_chart': bubble_chart_data,
        }
    })


def _get_schedule_display_api(source):
    """
    Convert schedule_type and related fields to human-readable format.
    Examples: "Daily 08:00", "Hourly :15", "Weekly Mon 09:00"
    """
    schedule_type = source.schedule_type

    # Try to get schedule details from first table
    first_table = source.tables.first()
    time_str = ""
    if first_table and first_table.schedule_time:
        time_str = first_table.schedule_time.strftime('%H:%M')

    if schedule_type == 'hourly':
        minute = first_table.schedule_minute if first_table and first_table.schedule_minute is not None else 0
        return f"Hourly :{minute:02d}"
    elif schedule_type == 'daily':
        return f"Daily {time_str}" if time_str else "Daily"
    elif schedule_type == 'weekly':
        day = first_table.schedule_day_of_week if first_table and first_table.schedule_day_of_week is not None else 0
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        day_name = days[day] if 0 <= day <= 6 else 'Mon'
        return f"Weekly {day_name} {time_str}" if time_str else f"Weekly {day_name}"
    elif schedule_type == 'monthly':
        day = first_table.schedule_day_of_month if first_table and first_table.schedule_day_of_month is not None else 1
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return f"Monthly {day}{suffix} {time_str}" if time_str else f"Monthly {day}{suffix}"
    return "Manual"