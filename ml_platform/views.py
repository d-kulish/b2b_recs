from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from django.db import IntegrityError
import json
from .models import (
    ModelEndpoint,
    ETLConfiguration,
    DataSource,
    DataSourceTable,
    ETLRun,
    PipelineConfiguration,
    PipelineRun,
    Experiment,
    TrainedModel,
    Deployment,
    SystemMetrics,
)


# ============================================================================
# SYSTEM DASHBOARD (Landing Page)
# ============================================================================

@login_required
def system_dashboard(request):
    """
    System Dashboard - Landing page showing all models/endpoints and summary stats.
    """
    models = ModelEndpoint.objects.all().order_by('-created_at')

    # Get latest system metrics (if available)
    try:
        latest_metrics = SystemMetrics.objects.latest('date')
    except SystemMetrics.DoesNotExist:
        latest_metrics = None

    # Calculate summary stats
    total_models = models.count()
    active_models = models.filter(status='active').count()
    recent_runs = PipelineRun.objects.filter(status='running').count()

    context = {
        'models': models,
        'total_models': total_models,
        'active_models': active_models,
        'recent_runs': recent_runs,
        'latest_metrics': latest_metrics,
    }

    return render(request, 'ml_platform/system_dashboard.html', context)


# ============================================================================
# MODEL/ENDPOINT CREATION
# ============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def create_model_endpoint(request):
    """
    Create a new Model/Endpoint.
    """
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')

        try:
            model = ModelEndpoint.objects.create(
                name=name,
                description=description,
                created_by=request.user,
                status='draft',
            )

            # Create default configurations
            ETLConfiguration.objects.create(
                model_endpoint=model,
                source_type='postgresql',
            )

            PipelineConfiguration.objects.create(
                model_endpoint=model,
            )

            messages.success(request, f'Model/Endpoint "{name}" created successfully!')
            return redirect('model_dashboard', model_id=model.id)

        except Exception as e:
            messages.error(request, f'Error creating model: {str(e)}')
            return redirect('system_dashboard')

    return render(request, 'ml_platform/create_model_endpoint.html')


# ============================================================================
# INDIVIDUAL MODEL/ENDPOINT PAGES
# ============================================================================

@login_required
def model_dashboard(request, model_id):
    """
    Model Dashboard - Landing page for a specific model showing health, recent runs, performance.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    # Get recent pipeline runs
    recent_runs = model.pipeline_runs.all()[:10]

    # Get active deployment
    active_deployment = model.deployments.filter(status='active').first()

    # Get latest experiment
    latest_experiment = model.experiments.filter(is_production=True).first()

    # Get ETL status
    try:
        etl_config = model.etl_config
        latest_etl_run = model.etl_runs.first()
    except ETLConfiguration.DoesNotExist:
        etl_config = None
        latest_etl_run = None

    context = {
        'model': model,
        'recent_runs': recent_runs,
        'active_deployment': active_deployment,
        'latest_experiment': latest_experiment,
        'etl_config': etl_config,
        'latest_etl_run': latest_etl_run,
    }

    return render(request, 'ml_platform/model_dashboard.html', context)


@login_required
def model_etl(request, model_id):
    """
    ETL Page - Configure data source connections, set extraction schedules, monitor ETL jobs.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    # Get or create ETL configuration
    try:
        etl_config = model.etl_config
    except ETLConfiguration.DoesNotExist:
        etl_config = ETLConfiguration.objects.create(
            model_endpoint=model,
            schedule_type='manual',
        )

    # Get all data sources for this model
    data_sources = etl_config.data_sources.all().prefetch_related('tables')

    # Calculate statistics
    enabled_sources = data_sources.filter(is_enabled=True)
    enabled_sources_count = enabled_sources.count()

    # Count all tables across all data sources
    total_tables_count = sum(source.tables.count() for source in data_sources)
    enabled_tables_count = sum(source.tables.filter(is_enabled=True).count() for source in data_sources)

    # Get recent ETL runs
    recent_runs = model.etl_runs.all()[:10]

    context = {
        'model': model,
        'etl_config': etl_config,
        'data_sources': data_sources,
        'enabled_sources_count': enabled_sources_count,
        'total_tables_count': total_tables_count,
        'enabled_tables_count': enabled_tables_count,
        'recent_runs': recent_runs,
    }

    return render(request, 'ml_platform/model_etl.html', context)


@login_required
def model_dataset(request, model_id):
    """
    Dataset Manager - Browse BigQuery tables/datasets, preview data, view data freshness.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    # TODO: Integrate with BigQuery to list datasets and tables
    # For now, we'll show placeholder data

    context = {
        'model': model,
    }

    return render(request, 'ml_platform/model_dataset.html', context)


@login_required
def model_pipeline_config(request, model_id):
    """
    Pipeline Configuration - Wizard-style interface for configuring ML pipeline parameters.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    try:
        pipeline_config = model.pipeline_config
    except PipelineConfiguration.DoesNotExist:
        pipeline_config = PipelineConfiguration.objects.create(
            model_endpoint=model,
        )

    if request.method == 'POST':
        # Update pipeline configuration
        pipeline_config.top_revenue_percentile = float(request.POST.get('top_revenue_percentile', 0.8))
        pipeline_config.min_transactions = int(request.POST.get('min_transactions', 10))
        pipeline_config.embedding_dim = int(request.POST.get('embedding_dim', 128))
        pipeline_config.batch_size = int(request.POST.get('batch_size', 8192))
        pipeline_config.epochs = int(request.POST.get('epochs', 3))
        pipeline_config.learning_rate = float(request.POST.get('learning_rate', 0.1))
        pipeline_config.use_gpu = request.POST.get('use_gpu') == 'on'
        pipeline_config.gpu_type = request.POST.get('gpu_type', 'nvidia-tesla-t4')
        pipeline_config.gpu_count = int(request.POST.get('gpu_count', 4))
        pipeline_config.use_preemptible = request.POST.get('use_preemptible') == 'on'
        pipeline_config.save()

        messages.success(request, 'Pipeline configuration updated successfully!')
        return redirect('model_pipeline_config', model_id=model_id)

    context = {
        'model': model,
        'pipeline_config': pipeline_config,
    }

    return render(request, 'ml_platform/model_pipeline_config.html', context)


@login_required
def model_feature_engineering(request, model_id):
    """
    Feature Engineering - Visual designer interface for creating features.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    context = {
        'model': model,
    }

    return render(request, 'ml_platform/model_feature_engineering.html', context)


@login_required
def model_training(request, model_id):
    """
    Training Interface - Launch training jobs, view real-time status, logs.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    pipeline_runs = model.pipeline_runs.all()[:20]

    context = {
        'model': model,
        'pipeline_runs': pipeline_runs,
    }

    return render(request, 'ml_platform/model_training.html', context)


@login_required
def model_experiments(request, model_id):
    """
    Experiments Dashboard - View MLflow experiments, compare models, metrics.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    experiments = model.experiments.all()
    trained_models = model.trained_models.all()

    context = {
        'model': model,
        'experiments': experiments,
        'trained_models': trained_models,
    }

    return render(request, 'ml_platform/model_experiments.html', context)


@login_required
def model_deployment(request, model_id):
    """
    Deployment Manager - Deploy models, manage versions, rollback.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    deployments = model.deployments.all()
    trained_models = model.trained_models.filter(status='completed')

    context = {
        'model': model,
        'deployments': deployments,
        'trained_models': trained_models,
    }

    return render(request, 'ml_platform/model_deployment.html', context)


# ============================================================================
# API ENDPOINTS (AJAX)
# ============================================================================

@login_required
@require_http_methods(["POST"])
def api_start_training(request, model_id):
    """
    API endpoint to start a new training run.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    try:
        pipeline_config = model.pipeline_config

        # Create a new pipeline run
        pipeline_run = PipelineRun.objects.create(
            model_endpoint=model,
            pipeline_config=pipeline_config,
            status='pending',
            triggered_by=request.user,
        )

        # TODO: Trigger actual Vertex AI job via Celery task

        return JsonResponse({
            'status': 'success',
            'message': 'Training job started successfully',
            'run_id': pipeline_run.id,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def api_start_etl(request, model_id):
    """
    API endpoint to start an ETL run.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    try:
        etl_config = model.etl_config

        # Create a new ETL run
        etl_run = ETLRun.objects.create(
            etl_config=etl_config,
            model_endpoint=model,
            status='pending',
            triggered_by=request.user,
        )

        # TODO: Trigger actual ETL job

        return JsonResponse({
            'status': 'success',
            'message': 'ETL job started successfully',
            'run_id': etl_run.id,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def api_deploy_model(request, model_id):
    """
    API endpoint to deploy a trained model.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)
    trained_model_id = request.POST.get('trained_model_id')

    try:
        trained_model = get_object_or_404(TrainedModel, id=trained_model_id, model_endpoint=model)

        # Create a new deployment
        deployment = Deployment.objects.create(
            model_endpoint=model,
            trained_model=trained_model,
            environment='production',
            status='deploying',
            deployed_by=request.user,
        )

        # TODO: Trigger actual Cloud Run deployment

        return JsonResponse({
            'status': 'success',
            'message': 'Model deployment started',
            'deployment_id': deployment.id,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
def api_pipeline_run_status(request, run_id):
    """
    API endpoint to get the status of a pipeline run (for polling).
    """
    pipeline_run = get_object_or_404(PipelineRun, id=run_id)

    return JsonResponse({
        'status': pipeline_run.status,
        'current_stage': pipeline_run.current_stage,
        'started_at': pipeline_run.started_at.isoformat() if pipeline_run.started_at else None,
        'completed_at': pipeline_run.completed_at.isoformat() if pipeline_run.completed_at else None,
        'error_message': pipeline_run.error_message,
    })


# ============================================================================
# ETL API ENDPOINTS
# ============================================================================

@login_required
@require_http_methods(["POST"])
def api_etl_add_source(request, model_id):
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
            from .models import Connection
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
def api_etl_get_source(request, source_id):
    """
    API endpoint to get data source details for editing.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)

        # Get tables for this source
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
            'wizard_last_step': source.wizard_last_step,
            'wizard_completed_steps': source.wizard_completed_steps or [],
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
def api_etl_update_source(request, source_id):
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
def api_etl_test_connection_wizard(request):
    """
    API endpoint to test a data source connection during wizard (no saved source yet).
    """
    from .utils.connection_manager import test_and_fetch_metadata

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
def api_etl_check_job_name(request, model_id):
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
def api_etl_save_draft_source(request, model_id):
    """
    API endpoint to save draft DataSource after successful connection test.
    Handles both saved connections and new connections.
    """
    from .utils.connection_manager import save_credentials_to_secret_manager
    from .models import Connection

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
def api_etl_test_connection(request, source_id):
    """
    API endpoint to test a data source connection.
    """
    from .utils.connection_manager import test_and_fetch_metadata, save_credentials_to_secret_manager

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
def api_etl_delete_source(request, source_id):
    """
    API endpoint to delete a data source.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)
        source_name = source.name
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
def api_etl_toggle_enabled(request, model_id):
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
def api_etl_run_now(request, model_id):
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
def api_etl_run_source(request, source_id):
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
            status='pending',
            triggered_by=request.user,
            started_at=timezone.now(),
        )

        # TODO: Trigger actual Cloud Run ETL job for this specific source
        # For now, simulate success
        etl_run.status = 'running'
        etl_run.total_sources = 1
        etl_run.successful_sources = 0
        etl_run.total_tables = source.tables.filter(is_enabled=True).count()
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
def api_etl_run_status(request, run_id):
    """
    API endpoint to get ETL run status (for polling).
    """
    try:
        etl_run = get_object_or_404(ETLRun, id=run_id)

        return JsonResponse({
            'status': etl_run.status,
            'started_at': etl_run.started_at.isoformat() if etl_run.started_at else None,
            'completed_at': etl_run.completed_at.isoformat() if etl_run.completed_at else None,
            'total_sources': etl_run.total_sources,
            'successful_sources': etl_run.successful_sources,
            'total_tables': etl_run.total_tables,
            'successful_tables': etl_run.successful_tables,
            'total_rows_extracted': etl_run.total_rows_extracted,
            'error_message': etl_run.error_message,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


# ============================================================================
# Connection Management API Endpoints (New Architecture)
# ============================================================================

@login_required
@require_http_methods(["POST"])
def api_connection_test_wizard(request, model_id):
    """
    Test connection in wizard and check for duplicates.
    Returns existing connection if duplicate found, or creates new one.
    """
    from .utils.connection_manager import test_and_fetch_metadata, save_connection_credentials
    from .models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Extract connection parameters
        source_type = data.get('source_type')
        host = data.get('host', '')
        port = data.get('port')
        database = data.get('database', '')
        username = data.get('username', '')
        password = data.get('password', '')

        # Prepare connection params for testing
        connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'username': username,
            'password': password,
            'project_id': data.get('project_id', ''),
            'dataset': data.get('dataset', ''),
            'service_account_json': data.get('service_account_json', ''),
            'connection_string': data.get('connection_string', ''),
            # Cloud Storage parameters
            'bucket_path': data.get('bucket_path', ''),
            'aws_access_key_id': data.get('aws_access_key_id', ''),
            'aws_secret_access_key': data.get('aws_secret_access_key', ''),
            'aws_region': data.get('aws_region', ''),
            'azure_storage_account': data.get('azure_storage_account', ''),
            'azure_account_key': data.get('azure_account_key', ''),
            'azure_sas_token': data.get('azure_sas_token', ''),
        }

        # Test the connection
        test_result = test_and_fetch_metadata(source_type, connection_params)

        if not test_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': test_result['message'],
            }, status=400)

        # Connection test successful - check for duplicates
        existing_connection = Connection.objects.filter(
            model_endpoint=model,
            source_type=source_type,
            source_host=host,
            source_port=port,
            source_database=database,
            source_username=username
        ).first()

        if existing_connection:
            # Duplicate found - return existing connection
            return JsonResponse({
                'status': 'success',
                'duplicate': True,
                'connection_id': existing_connection.id,
                'connection_name': existing_connection.name,
                'message': test_result['message'],
                'tables': test_result['tables'],
            })
        else:
            # No duplicate - suggest auto-name and prepare to create
            source_type_display = dict(Connection.SOURCE_TYPE_CHOICES).get(source_type, source_type)
            suggested_name = f"{source_type_display} - {database}" if database else source_type_display

            return JsonResponse({
                'status': 'success',
                'duplicate': False,
                'suggested_name': suggested_name,
                'message': test_result['message'],
                'tables': test_result['tables'],
                # Store connection data for later creation
                'connection_data': {
                    'source_type': source_type,
                    'host': host,
                    'port': port,
                    'database': database,
                    'username': username,
                    'schema': data.get('schema', ''),
                }
            })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_connection_create(request, model_id):
    """
    Create a new reusable Connection.
    This is called after successful connection test in the wizard.
    """
    from .utils.connection_manager import save_connection_credentials
    from .models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Extract connection details
        connection_name = data.get('name', 'Untitled Connection')
        source_type = data.get('source_type')
        connection_params = data.get('connection_params', {})

        print(f"=== CONNECTION CREATE DEBUG ===")
        print(f"Received connection name: '{connection_name}'")
        print(f"Source type: {source_type}")

        # Check for duplicate connection name
        if Connection.objects.filter(model_endpoint=model, name=connection_name).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'A connection named "{connection_name}" already exists. Please choose a different name.',
            }, status=400)

        # Create Connection
        connection = Connection.objects.create(
            model_endpoint=model,
            name=connection_name,
            source_type=source_type,
            description=data.get('description', ''),
            source_host=connection_params.get('host', ''),
            source_port=connection_params.get('port'),
            source_database=connection_params.get('database', ''),
            source_schema=connection_params.get('schema', ''),
            source_username=connection_params.get('username', ''),
            bigquery_project=connection_params.get('project_id', ''),
            bigquery_dataset=connection_params.get('dataset', ''),
            connection_string=connection_params.get('connection_string', ''),
            is_enabled=True,
            connection_tested=True,
        )

        # Save credentials to Secret Manager
        try:
            secret_name = save_connection_credentials(
                model_id=model_id,
                connection_id=connection.id,
                credentials_dict=connection_params
            )

            connection.credentials_secret_name = secret_name
            connection.last_test_at = timezone.now()
            connection.last_test_status = 'success'
            connection.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Connection created successfully',
                'connection_id': connection.id,
                'connection_name': connection.name,
            })

        except Exception as secret_error:
            # If Secret Manager fails, delete the Connection
            connection.delete()
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to save credentials: {str(secret_error)}',
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to create connection: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_connection_create_standalone(request, model_id):
    """
    Create a new connection in standalone mode (not from ETL wizard).
    Tests connection first, creates only if test succeeds.
    """
    from .utils.connection_manager import test_and_fetch_metadata, save_connection_credentials
    from .models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Extract connection details
        connection_name = data.get('name', '').strip()
        source_type = data.get('source_type')
        host = data.get('host', '')
        port = data.get('port')
        database = data.get('database', '')
        username = data.get('username', '')
        password = data.get('password', '')
        schema = data.get('schema', 'public')

        # Validate required fields
        if not connection_name:
            return JsonResponse({
                'status': 'error',
                'message': 'Connection name is required.',
            }, status=400)

        # Check for duplicate connection name
        if Connection.objects.filter(model_endpoint=model, name=connection_name).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'A connection named "{connection_name}" already exists. Please choose a different name.',
            }, status=400)

        # Prepare connection params for testing
        connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'username': username,
            'password': password,
            'schema': schema,
            'project_id': data.get('project_id', ''),
            'dataset': data.get('dataset', ''),
            'service_account_json': data.get('service_account_json', ''),
            'connection_string': data.get('connection_string', ''),
            # Cloud Storage parameters
            'bucket_path': data.get('bucket_path', ''),
            'aws_access_key_id': data.get('aws_access_key_id', ''),
            'aws_secret_access_key': data.get('aws_secret_access_key', ''),
            'aws_region': data.get('aws_region', ''),
            'azure_storage_account': data.get('azure_storage_account', ''),
            'azure_account_key': data.get('azure_account_key', ''),
            'azure_sas_token': data.get('azure_sas_token', ''),
        }

        # Test the connection first
        test_result = test_and_fetch_metadata(source_type, connection_params)

        if not test_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection test failed: {test_result["message"]}',
            }, status=400)

        # Connection test successful - create the Connection object
        try:
            connection = Connection.objects.create(
                model_endpoint=model,
                name=connection_name,
                source_type=source_type,
                description=data.get('description', ''),
                source_host=host,
                source_port=port,
                source_database=database,
                source_schema=schema,
                source_username=username,
                bigquery_project=data.get('project_id', ''),
                bigquery_dataset=data.get('dataset', ''),
                connection_string=data.get('connection_string', ''),
                # Cloud Storage fields
                bucket_path=data.get('bucket_path', ''),
                service_account_json=data.get('service_account_json', ''),
                aws_access_key_id=data.get('aws_access_key_id', ''),
                aws_region=data.get('aws_region', ''),
                azure_storage_account=data.get('azure_storage_account', ''),
                is_enabled=True,
                connection_tested=True,
                last_test_at=timezone.now(),
                last_test_status='success',
                last_test_message=test_result['message'],
            )
        except IntegrityError:
            # Duplicate credentials detected
            existing_conn = Connection.objects.filter(
                model_endpoint=model,
                source_type=source_type,
                source_host=host,
                source_port=port,
                source_database=database,
                source_username=username,
            ).first()

            return JsonResponse({
                'status': 'error',
                'message': f'A connection with these credentials already exists.\n\n'
                          f'Existing connection: "{existing_conn.name}"\n'
                          f'Database: {existing_conn.source_database}\n'
                          f'Host: {existing_conn.source_host}:{existing_conn.source_port}\n'
                          f'Username: {existing_conn.source_username}\n\n'
                          f'Please use a different database or reuse the existing connection.',
            }, status=400)

        # Save credentials to Secret Manager
        try:
            secret_name = save_connection_credentials(
                model_id=model_id,
                connection_id=connection.id,
                credentials_dict=connection_params
            )

            connection.credentials_secret_name = secret_name
            connection.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Connection created successfully',
                'connection_id': connection.id,
                'connection': {
                    'id': connection.id,
                    'name': connection.name,
                    'source_type': connection.source_type,
                    'source_type_display': connection.get_source_type_display(),
                    'source_host': connection.source_host,
                    'source_database': connection.source_database,
                    'last_test_status': connection.last_test_status,
                    'jobs_count': 0,
                },
            })

        except Exception as secret_error:
            # If Secret Manager fails, delete the Connection
            connection.delete()
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to save credentials: {str(secret_error)}',
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to create connection: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_connection_list(request, model_id):
    """
    List all connections for a model.
    """
    from .models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        connections = Connection.objects.filter(model_endpoint=model).order_by('-created_at')

        connections_data = [{
            'id': conn.id,
            'name': conn.name,
            'source_type': conn.source_type,
            'source_type_display': conn.get_source_type_display(),
            'source_host': conn.source_host,
            'source_port': conn.source_port,
            'source_database': conn.source_database,
            'source_schema': conn.source_schema,
            'source_username': conn.source_username,
            'bigquery_project': conn.bigquery_project,
            'bigquery_dataset': conn.bigquery_dataset,
            'connection_string': conn.connection_string,
            'is_enabled': conn.is_enabled,
            'connection_tested': conn.connection_tested,
            'last_test_at': conn.last_test_at.isoformat() if conn.last_test_at else None,
            'last_test_status': conn.last_test_status,
            'created_at': conn.created_at.isoformat(),
            'jobs_count': conn.get_dependent_jobs_count(),
        } for conn in connections]

        return JsonResponse({
            'status': 'success',
            'connections': connections_data,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["GET"])
def api_connection_get(request, connection_id):
    """
    Get details of a single connection.
    """
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        connection_data = {
            'id': connection.id,
            'name': connection.name,
            'source_type': connection.source_type,
            'source_type_display': connection.get_source_type_display(),
            'description': connection.description,
            'source_host': connection.source_host,
            'source_port': connection.source_port,
            'source_database': connection.source_database,
            'source_schema': connection.source_schema,
            'source_username': connection.source_username,
            'bigquery_project': connection.bigquery_project,
            'bigquery_dataset': connection.bigquery_dataset,
            'is_enabled': connection.is_enabled,
            'connection_tested': connection.connection_tested,
            'last_test_at': connection.last_test_at.isoformat() if connection.last_test_at else None,
            'last_test_status': connection.last_test_status,
            'last_test_message': connection.last_test_message,
            'jobs_count': connection.get_dependent_jobs_count(),
        }

        return JsonResponse({
            'status': 'success',
            'connection': connection_data,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["GET"])
def api_connection_get_credentials(request, connection_id):
    """
    Fetch connection credentials from Secret Manager for editing.
    Returns password so Step 2 can be pre-populated when reusing saved connection.
    """
    from .utils.connection_manager import get_credentials_from_secret_manager
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=404)

        # Fetch credentials from Secret Manager
        try:
            credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

            return JsonResponse({
                'status': 'success',
                'credentials': credentials,
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to retrieve credentials: {str(e)}',
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def api_connection_test(request, connection_id):
    """
    Test an existing connection using stored credentials.
    Used by auto-test feature on ETL page.
    """
    from .utils.connection_manager import test_and_fetch_metadata, get_credentials_from_secret_manager
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Check if credentials are stored
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection. Please edit and save the connection.',
            }, status=400)

        # Retrieve credentials from Secret Manager
        try:
            credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)
        except Exception as cred_error:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to retrieve credentials: {str(cred_error)}',
            }, status=500)

        # Prepare connection parameters with stored credentials
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
            'connection_string': connection.connection_string,
        }

        # Test connection
        result = test_and_fetch_metadata(connection.source_type, connection_params)

        # Update connection status
        connection.last_test_at = timezone.now()
        connection.last_test_status = 'success' if result['success'] else 'failed'
        connection.last_test_message = result['message']
        connection.connection_tested = result['success']
        connection.save()

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
            })
        else:
            return JsonResponse({
                'status': 'failed',  # Changed from 'error' to 'failed' to match frontend expectations
                'message': result['message'],
            })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in api_connection_test: {error_details}")  # Log to console for debugging
        return JsonResponse({
            'status': 'error',
            'message': f'System error: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_connection_update(request, connection_id):
    """
    Update an existing connection (credentials, connection details, name).
    Tests connection before updating. Affects all ETL jobs using this connection.
    """
    from .utils.connection_manager import test_and_fetch_metadata, save_connection_credentials
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)
        data = json.loads(request.body)

        # Extract updated connection details
        connection_name = data.get('name', connection.name)
        source_type = data.get('source_type', connection.source_type)
        host = data.get('host', connection.source_host)
        port = data.get('port', connection.source_port)
        database = data.get('database', connection.source_database)
        username = data.get('username', connection.source_username)
        password = data.get('password', '')  # Password required for update
        schema = data.get('schema', connection.source_schema)

        # Check if connection name changed and if new name is taken
        if connection_name != connection.name:
            if Connection.objects.filter(
                model_endpoint=connection.model_endpoint,
                name=connection_name
            ).exclude(id=connection_id).exists():
                return JsonResponse({
                    'status': 'error',
                    'message': f'A connection named "{connection_name}" already exists. Please choose a different name.',
                }, status=400)

        # Prepare connection params for testing
        connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'username': username,
            'password': password,
            'project_id': data.get('project_id', connection.bigquery_project),
            'dataset': data.get('dataset', connection.bigquery_dataset),
            'service_account_json': data.get('service_account_json', ''),
            'connection_string': data.get('connection_string', connection.connection_string),
        }

        # Test the connection first
        test_result = test_and_fetch_metadata(source_type, connection_params)

        if not test_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection test failed: {test_result["message"]}',
            }, status=400)

        # Connection test successful - update the Connection object
        connection.name = connection_name
        connection.source_type = source_type
        connection.source_host = host
        connection.source_port = port
        connection.source_database = database
        connection.source_schema = schema
        connection.source_username = username
        connection.bigquery_project = data.get('project_id', '')
        connection.bigquery_dataset = data.get('dataset', '')
        connection.connection_string = data.get('connection_string', '')
        connection.last_test_at = timezone.now()
        connection.last_test_status = 'success'
        connection.last_test_message = test_result['message']
        connection.connection_tested = True

        # Update credentials in Secret Manager
        try:
            secret_name = save_connection_credentials(
                model_id=connection.model_endpoint.id,
                connection_id=connection.id,
                credentials_dict=connection_params
            )
            connection.credentials_secret_name = secret_name
            connection.save()

            # Get count of affected jobs
            affected_jobs_count = connection.data_sources.count()

            return JsonResponse({
                'status': 'success',
                'message': f'Connection updated successfully. {affected_jobs_count} ETL job(s) will use the new credentials.',
                'connection_id': connection.id,
                'affected_jobs_count': affected_jobs_count,
                'tables': test_result.get('tables', []),
            })

        except Exception as secret_error:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to update credentials: {str(secret_error)}',
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_connection_test_and_fetch_tables(request, connection_id):
    """
    Test an existing connection and fetch tables using stored credentials.
    Used in edit mode to refresh table list without requiring password input.
    """
    from .utils.connection_manager import test_and_fetch_metadata, get_credentials_from_secret_manager
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
            'connection_string': connection.connection_string,
        }

        # Test connection and fetch tables
        result = test_and_fetch_metadata(connection.source_type, connection_params)

        # Update connection status
        connection.last_test_at = timezone.now()
        connection.last_test_status = 'success' if result['success'] else 'failed'
        connection.last_test_message = result['message']
        connection.connection_tested = result['success']
        connection.save()

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'tables': result['tables'],
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
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_connection_get_usage(request, connection_id):
    """
    Get list of ETL jobs that depend on this connection.
    """
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Get all DataSources using this connection
        dependent_jobs = []
        for ds in connection.data_sources.all():
            dependent_jobs.append({
                'id': ds.id,
                'name': ds.name,
                'source_type': ds.source_type,
                'is_enabled': ds.is_enabled,
                'created_at': ds.created_at.isoformat() if ds.created_at else None,
            })

        return JsonResponse({
            'status': 'success',
            'connection_id': connection.id,
            'connection_name': connection.name,
            'jobs_count': len(dependent_jobs),
            'jobs': dependent_jobs,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_connection_delete(request, connection_id):
    """
    Delete a connection.
    Only allowed if no ETL jobs depend on it.
    """
    from .utils.connection_manager import delete_secret_from_secret_manager
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Get list of dependent jobs
        dependent_jobs = list(connection.data_sources.all().values_list('name', flat=True))

        if dependent_jobs:
            return JsonResponse({
                'status': 'error',
                'message': f'Cannot delete connection: {len(dependent_jobs)} ETL job(s) depend on it.',
                'dependent_jobs': dependent_jobs,
            }, status=400)

        # Delete secret from Secret Manager
        if connection.credentials_secret_name:
            try:
                delete_secret_from_secret_manager(connection.credentials_secret_name)
            except Exception as e:
                # Log but don't fail deletion if secret doesn't exist
                print(f"Warning: Could not delete secret {connection.credentials_secret_name}: {str(e)}")

        # Delete the connection
        connection_name = connection.name
        connection.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'Connection "{connection_name}" deleted successfully',
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# ============================================================================
# NEW ETL WIZARD API ENDPOINTS (Simplified Flow)
# ============================================================================

@login_required
@require_http_methods(["GET"])
def api_etl_get_connections(request, model_id):
    """
    Get all connections for a model to populate ETL wizard Step 1.
    Returns connections with test status and usage count.
    """
    from .models import Connection

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
def api_etl_test_connection_in_wizard(request, connection_id):
    """
    Test an existing connection from within ETL wizard.
    Does NOT create or modify anything, just tests and fetches tables.
    Updates connection last_test_at and last_test_status.
    """
    from .models import Connection
    from .utils.connection_manager import test_and_fetch_metadata
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
def api_etl_create_job(request, model_id):
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
    from .models import Connection, DataSourceTable
    from django.utils import timezone

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        etl_config = model.etl_config

        data = json.loads(request.body)

        # Extract and validate required fields
        job_name = data.get('name', '').strip()
        connection_id = data.get('connection_id')
        schema_name = data.get('schema_name', '').strip()
        tables = data.get('tables', [])

        # Extract Step 3 fields (Load Strategy)
        load_type = data.get('load_type', 'transactional')
        timestamp_column = data.get('timestamp_column', '').strip()
        historical_start_date = data.get('historical_start_date')
        selected_columns = data.get('selected_columns', [])

        # Extract Step 4 fields (BigQuery Table Setup) - NEW
        bq_table_name = data.get('bigquery_table_name', '').strip()
        bq_schema_columns = data.get('bigquery_schema', [])

        # Extract Step 5 fields (Schedule) - RENAMED from Step 4
        schedule_type = data.get('schedule_type', 'manual')

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

        if not tables or len(tables) == 0:
            return JsonResponse({
                'status': 'error',
                'message': 'At least one table must be selected',
            }, status=400)

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
        # CREATE BIGQUERY TABLE FIRST
        # ============================================================
        from .utils.bigquery_manager import BigQueryTableManager
        import os
        from django.conf import settings

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

        # Create BigQuery table
        table_result = bq_manager.create_table_from_schema(
            table_name=bq_table_name,
            schema_columns=bq_schema_columns,
            load_type=load_type,
            timestamp_column=timestamp_column if load_type == 'transactional' else None,
            description=f"ETL source: {schema_name}.{tables[0]['source_table_name']} from {connection.name}",
            overwrite=False  # Don't overwrite existing tables
        )

        if not table_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to create BigQuery table: {table_result["message"]}',
            }, status=500)

        import logging
        logger = logging.getLogger(__name__)
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

        # Create DataSourceTable objects for each selected table
        for table_config in tables:
            source_table = table_config.get('source_table_name', '').strip()
            dest_table = table_config.get('dest_table_name', bq_table_name).strip()  # Use BigQuery table name
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
                    # New fields from Step 3, 4 & 5
                    load_type=load_type,
                    timestamp_column=timestamp_column,
                    historical_start_date=historical_start_date,
                    selected_columns=selected_columns,
                    schedule_type=schedule_type,
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
            from .utils.cloud_scheduler import CloudSchedulerManager

            try:
                scheduler_manager = CloudSchedulerManager(
                    project_id=project_id,
                    region='europe-central2'
                )

                # Cloud Run Jobs execution URL
                # Format: https://{region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/{project_id}/jobs/{job_name}:run
                cloud_run_job_url = f"https://europe-central2-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/{project_id}/jobs/etl-runner:run"
                service_account = f"etl-runner@{project_id}.iam.gserviceaccount.com"

                scheduler_result = scheduler_manager.create_etl_schedule(
                    data_source_id=data_source.id,
                    job_name=job_name,
                    schedule_type=schedule_type,
                    cloud_run_job_url=cloud_run_job_url,
                    service_account_email=service_account
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
def api_connection_fetch_schemas(request, connection_id):
    """
    Fetch available schemas for a connection.
    Used in ETL wizard Step 2 to show schema dropdown.
    """
    from .utils.connection_manager import fetch_schemas, get_credentials_from_secret_manager
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
        }

        # Fetch schemas
        result = fetch_schemas(connection.source_type, connection_params)

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'schemas': result['schemas'],
                'source_type': connection.source_type,
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_connection_fetch_tables_for_schema(request, connection_id):
    """
    Fetch tables for a specific schema within a connection.
    Used in ETL wizard Step 2 after schema selection.

    POST body: {
        "schema_name": "public"
    }
    """
    from .utils.connection_manager import fetch_tables_for_schema, get_credentials_from_secret_manager
    from .models import Connection
    import json

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Parse request body
        data = json.loads(request.body)
        schema_name = data.get('schema_name')

        if not schema_name:
            return JsonResponse({
                'status': 'error',
                'message': 'schema_name is required',
            }, status=400)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
        }

        # Fetch tables for the specified schema
        result = fetch_tables_for_schema(connection.source_type, schema_name, connection_params)

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'tables': result['tables'],
                'schema_name': schema_name,
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)

@login_required
@require_http_methods(["POST"])
def api_connection_fetch_table_preview(request, connection_id):
    """
    Fetch table preview with column metadata and sample data.
    Used in ETL wizard Step 3 to show table structure.

    POST body: {
        "schema_name": "public",
        "table_name": "transactions"
    }

    Returns: {
        "columns": [...],
        "total_rows": 1234567,
        "recommended": {...}
    }
    """
    from .utils.connection_manager import fetch_table_metadata, get_credentials_from_secret_manager
    from .models import Connection
    import json

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Parse request body
        data = json.loads(request.body)
        schema_name = data.get('schema_name')
        table_name = data.get('table_name')

        if not schema_name or not table_name:
            return JsonResponse({
                'status': 'error',
                'message': 'schema_name and table_name are required',
            }, status=400)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
        }

        # Fetch table metadata
        result = fetch_table_metadata(
            connection.source_type,
            schema_name,
            table_name,
            connection_params
        )

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'columns': result['columns'],
                'total_rows': result['total_rows'],
                'recommended': result.get('recommended', {}),
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# ============================================================
# ETL RUNNER API ENDPOINTS (Phase 2)
# ============================================================

@require_http_methods(["GET"])
def api_etl_job_config(request, data_source_id):
    """
    Get ETL job configuration for the ETL runner.
    Called by Cloud Run ETL runner to fetch job details.

    Returns complete configuration needed to execute ETL job.
    """
    from .utils.connection_manager import get_credentials_from_secret_manager

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

        # Build connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
        }

        # Determine load type
        load_type = table.load_type if hasattr(table, 'load_type') else ('transactional' if data_source.use_incremental else 'catalog')

        # Build job configuration
        config = {
            'source_type': connection.source_type,
            'connection_params': connection_params,
            'source_table_name': table.source_table_name,
            'schema_name': table.schema_name or connection.source_database,
            'dest_table_name': table.dest_table_name,
            'load_type': load_type,
            'timestamp_column': data_source.incremental_column or table.incremental_column,
            'selected_columns': table.selected_columns if hasattr(table, 'selected_columns') and table.selected_columns else [],
            'last_sync_value': data_source.last_sync_value,
            'historical_start_date': data_source.historical_start_date.isoformat() if data_source.historical_start_date else None,
        }

        return JsonResponse(config)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["PATCH"])
def api_etl_run_update(request, run_id):
    """
    Update ETL run status and progress.
    Called by Cloud Run ETL runner to report progress.

    Payload examples:
    {"status": "running"}
    {"status": "completed", "rows_extracted": 1000, "rows_loaded": 1000, "duration_seconds": 120}
    {"rows_extracted": 5000, "rows_loaded": 5000}
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

        # Update phase timestamps if provided
        if 'extraction_started_at' in data:
            etl_run.extraction_started_at = timezone.now()
        if 'extraction_completed_at' in data:
            etl_run.extraction_completed_at = timezone.now()
        if 'loading_started_at' in data:
            etl_run.loading_started_at = timezone.now()
        if 'loading_completed_at' in data:
            etl_run.loading_completed_at = timezone.now()

        etl_run.save()

        return JsonResponse({
            'status': 'success',
            'message': 'ETL run updated successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_etl_trigger_now(request, data_source_id):
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

        # Create ETL run record
        etl_run = ETLRun.objects.create(
            etl_config=data_source.etl_config,
            model_endpoint=model,
            status='pending',
            triggered_by=request.user,
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

            operation = client.run_job(request=exec_request)

            # Update ETL run with execution ID
            etl_run.cloud_run_execution_id = operation.name
            etl_run.save()

            return JsonResponse({
                'status': 'success',
                'message': f'ETL run triggered for "{data_source.name}"',
                'run_id': etl_run.id,
                'execution_name': operation.name
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
