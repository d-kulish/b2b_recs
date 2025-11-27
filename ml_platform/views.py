from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.db.models import Q
from datetime import timedelta
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
    ProcessedFile,
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
            )

            PipelineConfiguration.objects.create(
                model_endpoint=model,
            )

            return redirect('system_dashboard')

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

    # Get recent ETL runs with 30-day filter and pagination
    cutoff_date = timezone.now() - timedelta(days=30)

    # Filter runs from last 30 days, including runs with NULL started_at (pending/running jobs)
    filtered_runs = model.etl_runs.filter(
        Q(started_at__gte=cutoff_date) | Q(started_at__isnull=True)
    )

    # Check if any runs exist at all (for empty state differentiation)
    has_any_runs = model.etl_runs.exists()

    # Pagination: 6 runs per page
    paginator = Paginator(filtered_runs, 6)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'model': model,
        'etl_config': etl_config,
        'data_sources': data_sources,
        'enabled_sources_count': enabled_sources_count,
        'total_tables_count': total_tables_count,
        'enabled_tables_count': enabled_tables_count,
        'recent_runs': page_obj,
        'page_obj': page_obj,
        'has_any_runs': has_any_runs,
        'showing_last_30_days': True,
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
    UNIFIED Connection Creation API - Source-Type Aware
    Handles ALL source types: Databases, Cloud Storage, NoSQL
    Replaces both old wizard and standalone APIs.
    """
    from .utils.connection_manager import test_and_fetch_metadata, save_connection_credentials
    from .models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Extract connection details
        connection_name = data.get('name', 'Untitled Connection')
        source_type = data.get('source_type')
        test_first = data.get('test_first', False)  # Standalone mode tests first

        # Get connection params (can be nested or flat depending on caller)
        connection_params = data.get('connection_params', {})
        if not connection_params:
            # Flat structure - extract from data directly
            connection_params = data

        print(f"=== UNIFIED CONNECTION CREATE ===")
        print(f"Connection name: '{connection_name}'")
        print(f"Source type: {source_type}")
        print(f"Test first: {test_first}")

        # Check for duplicate connection name
        if Connection.objects.filter(model_endpoint=model, name=connection_name).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'A connection named "{connection_name}" already exists. Please choose a different name.',
            }, status=400)

        # Define source type categories
        DB_TYPES = {'postgresql', 'mysql', 'oracle', 'sqlserver', 'db2', 'redshift', 'synapse', 'bigquery', 'snowflake', 'mariadb', 'teradata'}
        STORAGE_TYPES = {'gcs', 's3', 'azure_blob'}
        NOSQL_TYPES = {'mongodb', 'firestore', 'cassandra', 'dynamodb', 'redis'}

        # === SOURCE-TYPE AWARE FIELD EXTRACTION ===
        connection_data = {
            'model_endpoint': model,
            'name': connection_name,
            'source_type': source_type,
            'description': data.get('description', ''),
            'is_enabled': True,
        }
        credentials_dict = {}

        # Extract fields based on source type
        if source_type in DB_TYPES:
            # === RELATIONAL DATABASES ===
            connection_data.update({
                'source_host': connection_params.get('host', ''),
                'source_port': connection_params.get('port'),
                'source_database': connection_params.get('database', ''),
                'source_schema': connection_params.get('schema', ''),
                'source_username': connection_params.get('username', ''),
            })
            credentials_dict.update({
                'host': connection_params.get('host', ''),
                'port': connection_params.get('port'),
                'database': connection_params.get('database', ''),
                'schema': connection_params.get('schema', ''),
                'username': connection_params.get('username', ''),
                'password': connection_params.get('password', ''),
            })

            if source_type == 'bigquery':
                connection_data['bigquery_project'] = connection_params.get('project_id', '')
                connection_data['bigquery_dataset'] = connection_params.get('dataset', '')
                credentials_dict['project_id'] = connection_params.get('project_id', '')
                credentials_dict['dataset'] = connection_params.get('dataset', '')
                credentials_dict['service_account_json'] = connection_params.get('service_account_json', '')

        elif source_type == 'gcs':
            # === GOOGLE CLOUD STORAGE ===
            bucket_path = connection_params.get('bucket_path', '')
            # Extract bucket name from path (gs://bucket-name or just bucket-name)
            if bucket_path.startswith('gs://'):
                bucket_name = bucket_path.replace('gs://', '').split('/')[0]
            else:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f'gs://{bucket_path}' if bucket_path and not bucket_path.startswith('gs://') else bucket_path

            connection_data.update({
                'source_host': bucket_name,  # For backward compatibility (troubleshooting docs)
                'bucket_path': bucket_path,
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'service_account_json': connection_params.get('service_account_json', ''),
            })

        elif source_type == 's3':
            # === AWS S3 ===
            bucket_path = connection_params.get('bucket_path', '')
            # Extract bucket name from path (s3://bucket-name or just bucket-name)
            if bucket_path.startswith('s3://'):
                bucket_name = bucket_path.replace('s3://', '').split('/')[0]
            else:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f's3://{bucket_path}' if bucket_path and not bucket_path.startswith('s3://') else bucket_path

            connection_data.update({
                'source_host': bucket_name,  # Bucket name
                'bucket_path': bucket_path,
                'aws_access_key_id': connection_params.get('aws_access_key_id', ''),
                'aws_region': connection_params.get('aws_region', 'us-east-1'),
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'aws_access_key_id': connection_params.get('aws_access_key_id', ''),
                'aws_secret_access_key': connection_params.get('aws_secret_access_key', ''),
                'aws_region': connection_params.get('aws_region', 'us-east-1'),
            })

        elif source_type == 'azure_blob':
            # === AZURE BLOB STORAGE ===
            bucket_path = connection_params.get('bucket_path', '')
            connection_data.update({
                'bucket_path': bucket_path,
                'azure_storage_account': connection_params.get('azure_storage_account', ''),
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'azure_storage_account': connection_params.get('azure_storage_account', ''),
                'azure_account_key': connection_params.get('azure_account_key', ''),
                'azure_sas_token': connection_params.get('azure_sas_token', ''),
            })

        elif source_type in NOSQL_TYPES:
            # === NOSQL DATABASES ===
            connection_data.update({
                'connection_string': connection_params.get('connection_string', ''),
                'connection_params': connection_params.get('connection_params', {}),
            })
            credentials_dict.update({
                'connection_string': connection_params.get('connection_string', ''),
            })

            if source_type == 'firestore':
                connection_data['bigquery_project'] = connection_params.get('project_id', '')
                credentials_dict['project_id'] = connection_params.get('project_id', '')
                credentials_dict['service_account_json'] = connection_params.get('service_account_json', '')
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Unsupported source type: {source_type}',
            }, status=400)

        # === TEST CONNECTION IF REQUESTED (standalone mode) ===
        if test_first:
            test_result = test_and_fetch_metadata(source_type, credentials_dict)
            if not test_result['success']:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Connection test failed: {test_result["message"]}',
                }, status=400)

        # === CREATE CONNECTION ===
        try:
            connection = Connection.objects.create(**connection_data)
        except IntegrityError:
            # Duplicate credentials detected (based on unique_together constraint)
            return JsonResponse({
                'status': 'error',
                'message': f'A connection with these credentials already exists. Please check existing connections.',
            }, status=400)

        # === SAVE CREDENTIALS TO SECRET MANAGER ===
        try:
            secret_name = save_connection_credentials(
                model_id=model_id,
                connection_id=connection.id,
                credentials_dict=credentials_dict
            )

            connection.credentials_secret_name = secret_name
            connection.last_test_at = timezone.now()
            connection.last_test_status = 'success' if test_first else ''
            connection.connection_tested = test_first
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
        import traceback
        print(f"ERROR in api_connection_create: {str(e)}")
        print(traceback.format_exc())
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
    Get details of a single connection - SOURCE-TYPE AWARE
    Returns appropriate fields based on connection type (DB, Cloud Storage, NoSQL).
    """
    from .models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Define source type categories
        DB_TYPES = {'postgresql', 'mysql', 'oracle', 'sqlserver', 'db2', 'redshift', 'synapse', 'bigquery', 'snowflake', 'mariadb', 'teradata'}
        STORAGE_TYPES = {'gcs', 's3', 'azure_blob'}
        NOSQL_TYPES = {'mongodb', 'firestore', 'cassandra', 'dynamodb', 'redis'}

        # Base fields (common to all types)
        connection_data = {
            'id': connection.id,
            'name': connection.name,
            'source_type': connection.source_type,
            'source_type_display': connection.get_source_type_display(),
            'description': connection.description,
            'is_enabled': connection.is_enabled,
            'connection_tested': connection.connection_tested,
            'last_test_at': connection.last_test_at.isoformat() if connection.last_test_at else None,
            'last_test_status': connection.last_test_status,
            'last_test_message': connection.last_test_message,
            'jobs_count': connection.get_dependent_jobs_count(),
        }

        # === ADD SOURCE-TYPE SPECIFIC FIELDS ===
        if connection.source_type in DB_TYPES:
            # === RELATIONAL DATABASES ===
            connection_data.update({
                'source_host': connection.source_host or '',
                'source_port': connection.source_port,
                'source_database': connection.source_database or '',
                'source_schema': connection.source_schema or '',
                'source_username': connection.source_username or '',
            })
            if connection.source_type == 'bigquery':
                connection_data.update({
                    'bigquery_project': connection.bigquery_project or '',
                    'bigquery_dataset': connection.bigquery_dataset or '',
                })

        elif connection.source_type == 'gcs':
            # === GOOGLE CLOUD STORAGE ===
            # Handle backward compatibility: check bucket_path first, fallback to source_host
            bucket_path = connection.bucket_path or (f'gs://{connection.source_host}' if connection.source_host else '')
            connection_data.update({
                'bucket_path': bucket_path,
                'source_host': connection.source_host or '',  # Bucket name (legacy)
            })

        elif connection.source_type == 's3':
            # === AWS S3 ===
            connection_data.update({
                'bucket_path': connection.bucket_path or '',
                'source_host': connection.source_host or '',  # Bucket name
                'aws_access_key_id': connection.aws_access_key_id or '',
                'aws_region': connection.aws_region or 'us-east-1',
            })

        elif connection.source_type == 'azure_blob':
            # === AZURE BLOB STORAGE ===
            connection_data.update({
                'bucket_path': connection.bucket_path or '',
                'azure_storage_account': connection.azure_storage_account or '',
            })

        elif connection.source_type in NOSQL_TYPES:
            # === NOSQL DATABASES ===
            connection_data.update({
                'connection_string': connection.connection_string or '',
                'connection_params': connection.connection_params or {},
            })
            if connection.source_type == 'firestore':
                connection_data['bigquery_project'] = connection.bigquery_project or ''

        return JsonResponse({
            'status': 'success',
            'connection': connection_data,
        })

    except Exception as e:
        import traceback
        print(f"ERROR in api_connection_get: {str(e)}")
        print(traceback.format_exc())
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
            # Cloud storage parameters
            'bucket_path': connection.bucket_path,
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
    Update an existing connection - SOURCE-TYPE AWARE
    Handles ALL source types: Databases, Cloud Storage, NoSQL
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

        # Define source type categories
        DB_TYPES = {'postgresql', 'mysql', 'oracle', 'sqlserver', 'db2', 'redshift', 'synapse', 'bigquery', 'snowflake', 'mariadb', 'teradata'}
        STORAGE_TYPES = {'gcs', 's3', 'azure_blob'}
        NOSQL_TYPES = {'mongodb', 'firestore', 'cassandra', 'dynamodb', 'redis'}

        # === SOURCE-TYPE AWARE FIELD EXTRACTION ===
        connection_updates = {
            'name': connection_name,
            'source_type': source_type,
            'description': data.get('description', connection.description),
        }
        credentials_dict = {}

        # Extract fields based on source type
        if source_type in DB_TYPES:
            # === RELATIONAL DATABASES ===
            connection_updates.update({
                'source_host': data.get('host', connection.source_host),
                'source_port': data.get('port', connection.source_port),
                'source_database': data.get('database', connection.source_database),
                'source_schema': data.get('schema', connection.source_schema),
                'source_username': data.get('username', connection.source_username),
            })
            credentials_dict.update({
                'host': data.get('host', connection.source_host),
                'port': data.get('port', connection.source_port),
                'database': data.get('database', connection.source_database),
                'schema': data.get('schema', connection.source_schema),
                'username': data.get('username', connection.source_username),
                'password': data.get('password', ''),
            })

            if source_type == 'bigquery':
                connection_updates['bigquery_project'] = data.get('project_id', connection.bigquery_project)
                connection_updates['bigquery_dataset'] = data.get('dataset', connection.bigquery_dataset)
                credentials_dict['project_id'] = data.get('project_id', connection.bigquery_project)
                credentials_dict['dataset'] = data.get('dataset', connection.bigquery_dataset)
                credentials_dict['service_account_json'] = data.get('service_account_json', '')

        elif source_type == 'gcs':
            # === GOOGLE CLOUD STORAGE ===
            bucket_path = data.get('bucket_path', connection.bucket_path)
            # Extract bucket name from path
            if bucket_path and bucket_path.startswith('gs://'):
                bucket_name = bucket_path.replace('gs://', '').split('/')[0]
            elif bucket_path:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f'gs://{bucket_path}'
            else:
                bucket_name = ''

            connection_updates.update({
                'source_host': bucket_name,
                'bucket_path': bucket_path,
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'service_account_json': data.get('service_account_json', ''),
            })

        elif source_type == 's3':
            # === AWS S3 ===
            bucket_path = data.get('bucket_path', connection.bucket_path)
            # Extract bucket name from path
            if bucket_path and bucket_path.startswith('s3://'):
                bucket_name = bucket_path.replace('s3://', '').split('/')[0]
            elif bucket_path:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f's3://{bucket_path}'
            else:
                bucket_name = ''

            connection_updates.update({
                'source_host': bucket_name,
                'bucket_path': bucket_path,
                'aws_access_key_id': data.get('aws_access_key_id', connection.aws_access_key_id),
                'aws_region': data.get('aws_region', connection.aws_region),
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'aws_access_key_id': data.get('aws_access_key_id', connection.aws_access_key_id),
                'aws_secret_access_key': data.get('aws_secret_access_key', ''),
                'aws_region': data.get('aws_region', connection.aws_region),
            })

        elif source_type == 'azure_blob':
            # === AZURE BLOB STORAGE ===
            connection_updates.update({
                'bucket_path': data.get('bucket_path', connection.bucket_path),
                'azure_storage_account': data.get('azure_storage_account', connection.azure_storage_account),
            })
            credentials_dict.update({
                'bucket_path': data.get('bucket_path', connection.bucket_path),
                'azure_storage_account': data.get('azure_storage_account', connection.azure_storage_account),
                'azure_account_key': data.get('azure_account_key', ''),
                'azure_sas_token': data.get('azure_sas_token', ''),
            })

        elif source_type in NOSQL_TYPES:
            # === NOSQL DATABASES ===
            connection_updates.update({
                'connection_string': data.get('connection_string', connection.connection_string),
                'connection_params': data.get('connection_params', connection.connection_params),
            })
            credentials_dict.update({
                'connection_string': data.get('connection_string', connection.connection_string),
            })

            if source_type == 'firestore':
                connection_updates['bigquery_project'] = data.get('project_id', connection.bigquery_project)
                credentials_dict['project_id'] = data.get('project_id', connection.bigquery_project)
                credentials_dict['service_account_json'] = data.get('service_account_json', '')

        # === TEST CONNECTION FIRST ===
        test_result = test_and_fetch_metadata(source_type, credentials_dict)

        if not test_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection test failed: {test_result["message"]}',
            }, status=400)

        # === UPDATE CONNECTION OBJECT ===
        for field, value in connection_updates.items():
            setattr(connection, field, value)

        connection.last_test_at = timezone.now()
        connection.last_test_status = 'success'
        connection.last_test_message = test_result['message']
        connection.connection_tested = True

        # === UPDATE CREDENTIALS IN SECRET MANAGER ===
        try:
            secret_name = save_connection_credentials(
                model_id=connection.model_endpoint.id,
                connection_id=connection.id,
                credentials_dict=credentials_dict
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
        import traceback
        print(f"ERROR in api_connection_update: {str(e)}")
        print(traceback.format_exc())
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

        # Extract Step 4 fields (BigQuery Table Setup) - NEW
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

        # Create description based on source type
        if is_file_based:
            table_description = f"ETL source: {file_pattern} files from {connection.name}"
        else:
            table_description = f"ETL source: {schema_name}.{tables[0]['source_table_name']} from {connection.name}"

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
            from .utils.cloud_scheduler import CloudSchedulerManager

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
@require_http_methods(["GET"])
def api_connection_list_files(request, connection_id):
    """
    List files in cloud storage bucket matching a pattern.
    Used in ETL wizard Step 2 for cloud storage connections (GCS, S3, Azure).

    Query params:
        prefix: Folder path prefix (optional)
        pattern: File pattern using glob syntax (e.g., "*.csv", "data_*.parquet")

    Returns: {
        "status": "success",
        "files": [
            {
                "name": "data/file.csv",
                "size": 1024000,
                "last_modified": "2024-11-19 10:30:00"
            },
            ...
        ]
    }
    """
    from .utils.connection_manager import get_credentials_from_secret_manager
    from .models import Connection
    from google.cloud import storage
    from google.oauth2 import service_account
    import json
    import fnmatch

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Get query parameters
        prefix = request.GET.get('prefix', '').strip()
        pattern = request.GET.get('pattern', '*').strip()

        # Validate connection is cloud storage type
        if connection.source_type not in ['gcs', 's3', 'azure_blob']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection type "{connection.source_type}" is not a cloud storage type',
            }, status=400)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Handle different cloud storage types
        files = []

        if connection.source_type == 'gcs':
            # Google Cloud Storage
            bucket_path = connection.bucket_path  # gs://bucket-name

            if not bucket_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Bucket path not configured for this connection. Please edit the connection and set the bucket path.',
                }, status=400)

            if not bucket_path.startswith('gs://'):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid GCS bucket path. Must start with gs://',
                }, status=400)

            bucket_name = bucket_path.replace('gs://', '').split('/')[0]

            # Parse service account JSON
            service_account_json = credentials.get('service_account_json', '')
            credentials_info = json.loads(service_account_json)
            creds = service_account.Credentials.from_service_account_info(credentials_info)

            # Create GCS client
            client = storage.Client(credentials=creds, project=credentials_info.get('project_id'))
            bucket = client.get_bucket(bucket_name)

            # List all blobs with prefix (recursive)
            all_blobs = list(bucket.list_blobs(prefix=prefix, max_results=1000))

            # Filter by pattern (only filename, not full path)
            for blob in all_blobs:
                # Skip directories
                if blob.name.endswith('/'):
                    continue

                # Extract filename from full path
                filename = blob.name.split('/')[-1]

                # Match pattern against filename only
                if fnmatch.fnmatch(filename, pattern):
                    files.append({
                        'name': blob.name,
                        'size': blob.size,
                        'last_modified': blob.updated.strftime('%Y-%m-%d %H:%M:%S') if blob.updated else 'N/A'
                    })

        elif connection.source_type == 's3':
            # AWS S3 - to be implemented
            return JsonResponse({
                'status': 'error',
                'message': 'S3 file listing not yet implemented',
            }, status=501)

        elif connection.source_type == 'azure_blob':
            # Azure Blob Storage - to be implemented
            return JsonResponse({
                'status': 'error',
                'message': 'Azure Blob file listing not yet implemented',
            }, status=501)

        # Sort files by last modified (newest first)
        files.sort(key=lambda f: f['last_modified'], reverse=True)

        return JsonResponse({
            'status': 'success',
            'files': files,
            'count': len(files),
            'prefix': prefix,
            'pattern': pattern,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid service account JSON format',
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
def api_connection_detect_file_schema(request, connection_id):
    """
    Detect schema from a cloud storage file by downloading and analyzing a sample.
    Used in ETL wizard Step 2 for cloud storage connections.

    POST body: {
        "file_path": "data/transactions/file.csv",
        "file_format": "csv",
        "format_options": {
            "delimiter": ",",
            "encoding": "utf-8",
            "has_header": true
        }
    }

    Returns: {
        "status": "success",
        "columns": [
            {
                "name": "id",
                "type": "INTEGER",
                "bigquery_type": "INT64",
                "bigquery_mode": "NULLABLE",
                "sample_values": ["1", "2", "3"]
            },
            ...
        ],
        "total_rows": 1000 (estimated from sample),
        "schema_fingerprint": "abc123..."
    }
    """
    from .utils.connection_manager import get_credentials_from_secret_manager
    from .models import Connection
    from google.cloud import storage
    from google.oauth2 import service_account
    import json
    import pandas as pd
    import io
    import hashlib

    try:
        print(f"[SCHEMA DETECTION] Starting schema detection for connection_id={connection_id}")
        connection = get_object_or_404(Connection, id=connection_id)
        print(f"[SCHEMA DETECTION] Connection found: {connection.name} (type={connection.source_type})")

        # Parse request body
        data = json.loads(request.body)
        file_path = data.get('file_path')
        file_format = data.get('file_format', 'csv')
        format_options = data.get('format_options', {})

        print(f"[SCHEMA DETECTION] Request params: file_path={file_path}, format={file_format}, options={format_options}")
        print(f"[SCHEMA DETECTION] Bucket path: {connection.bucket_path}")
        print(f"[SCHEMA DETECTION] Has credentials: {bool(connection.credentials_secret_name)}")

        if not file_path:
            return JsonResponse({
                'status': 'error',
                'message': 'file_path is required',
            }, status=400)

        # Validate connection is cloud storage
        if connection.source_type not in ['gcs', 's3', 'azure_blob']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection type "{connection.source_type}" is not a cloud storage type',
            }, status=400)

        # Retrieve credentials
        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Download sample of file
        df_sample = None

        if connection.source_type == 'gcs':
            # Google Cloud Storage
            bucket_path = connection.bucket_path

            if not bucket_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Bucket path not configured for this connection. Please edit the connection and set the bucket path.',
                }, status=400)

            if not bucket_path.startswith('gs://'):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid GCS bucket path. Must start with gs://',
                }, status=400)

            bucket_name = bucket_path.replace('gs://', '').split('/')[0]

            # Parse service account JSON
            service_account_json = credentials.get('service_account_json', '')
            credentials_info = json.loads(service_account_json)
            creds = service_account.Credentials.from_service_account_info(credentials_info)

            # Create GCS client
            client = storage.Client(credentials=creds, project=credentials_info.get('project_id'))
            bucket = client.get_bucket(bucket_name)
            blob = bucket.blob(file_path)

            # Check file size
            blob.reload()  # Get metadata
            file_size = blob.size

            if file_size > 1024 * 1024 * 1024:  # 1GB
                return JsonResponse({
                    'status': 'error',
                    'message': f'File size ({file_size / (1024**3):.2f} GB) exceeds 1GB limit',
                }, status=400)

            # Download file content (limit to first 5MB for schema detection)
            max_bytes_to_download = min(file_size, 5 * 1024 * 1024)  # 5MB max
            file_content = blob.download_as_bytes(end=max_bytes_to_download)

            # Parse based on format
            if file_format == 'csv':
                delimiter = format_options.get('delimiter', ',')
                encoding = format_options.get('encoding', 'utf-8')
                has_header = format_options.get('has_header', True)

                # Handle tab delimiter
                if delimiter == '\\t':
                    delimiter = '\t'

                # Read CSV with pandas (limited rows)
                df_sample = pd.read_csv(
                    io.BytesIO(file_content),
                    delimiter=delimiter,
                    encoding=encoding,
                    header=0 if has_header else None,
                    nrows=1000,  # Sample first 1000 rows
                    low_memory=False
                )

                # If no header, create column names
                if not has_header:
                    df_sample.columns = [f'column_{i}' for i in range(len(df_sample.columns))]

            elif file_format == 'parquet':
                df_sample = pd.read_parquet(io.BytesIO(file_content))

            elif file_format == 'json':
                df_sample = pd.read_json(io.BytesIO(file_content), lines=True, nrows=1000)

            else:
                return JsonResponse({
                    'status': 'error',
                    'message': f'File format "{file_format}" not yet supported',
                }, status=400)

        else:
            # S3 and Azure not yet implemented
            return JsonResponse({
                'status': 'error',
                'message': f'{connection.source_type.upper()} schema detection not yet implemented',
            }, status=501)

        # Detect schema from pandas DataFrame
        from .utils.schema_mapper import SchemaMapper
        columns = []
        for col_name in df_sample.columns:
            col_data = df_sample[col_name]
            pandas_dtype = str(col_data.dtype)

            # Sanitize column name for BigQuery
            name_info = SchemaMapper.sanitize_column_name(str(col_name))

            # Map pandas dtype to BigQuery type
            if pandas_dtype.startswith('int'):
                bq_type = 'INT64'
            elif pandas_dtype.startswith('float'):
                bq_type = 'FLOAT64'
            elif pandas_dtype == 'bool':
                bq_type = 'BOOL'
            elif pandas_dtype == 'datetime64':
                bq_type = 'TIMESTAMP'
            elif pandas_dtype == 'object':
                # Try to infer if it's a date
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        pd.to_datetime(col_data.dropna().iloc[:10])
                    bq_type = 'TIMESTAMP'
                except:
                    bq_type = 'STRING'
            else:
                bq_type = 'STRING'

            # Get sample values (first 5 non-null values)
            sample_values = col_data.dropna().head(5).astype(str).tolist()

            # Determine if column has nulls
            has_nulls = col_data.isnull().any()
            bq_mode = 'NULLABLE' if has_nulls else 'REQUIRED'

            columns.append({
                'name': name_info['sanitized_name'],  # Use sanitized name for BigQuery
                'original_name': name_info['original_name'],  # Preserve original name
                'name_changed': name_info['name_changed'],  # Flag if name was changed
                'type': pandas_dtype,
                'bigquery_type': bq_type,
                'bigquery_mode': bq_mode,
                'sample_values': sample_values,
                'nullable': bool(has_nulls)  # Convert numpy.bool_ to Python bool for JSON serialization
            })

        # Generate schema fingerprint (hash of column names + types)
        schema_string = '|'.join([f"{c['name']}:{c['bigquery_type']}" for c in columns])
        schema_fingerprint = hashlib.md5(schema_string.encode()).hexdigest()

        return JsonResponse({
            'status': 'success',
            'columns': columns,
            'total_rows': len(df_sample),
            'schema_fingerprint': schema_fingerprint,
            'file_size': file_size,
        })

    except pd.errors.ParserError as e:
        import traceback
        print(f"[SCHEMA DETECTION] Parser error: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to parse file: {str(e)}. Check delimiter and encoding settings.',
        }, status=400)
    except Exception as e:
        import traceback
        print(f"[SCHEMA DETECTION] Unexpected error: {str(e)}")
        print(f"[SCHEMA DETECTION] Error type: {type(e).__name__}")
        print(f"[SCHEMA DETECTION] Connection ID: {connection_id}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'{type(e).__name__}: {str(e)}',
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

@csrf_exempt
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

            # Update ETL run with operation name (execution ID will be populated by ETL runner)
            # Note: operation.result() would block until completion, so we store operation name instead
            operation_name = None
            if hasattr(operation, 'operation') and hasattr(operation.operation, 'name'):
                operation_name = operation.operation.name

            etl_run.cloud_run_execution_id = operation_name or 'triggered'
            etl_run.status = 'running'
            etl_run.save()

            return JsonResponse({
                'status': 'success',
                'message': f'ETL run triggered for "{data_source.name}"',
                'run_id': etl_run.id,
                'operation_name': operation_name
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
def api_etl_get_processed_files(request, data_source_id):
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
def api_etl_record_processed_file(request, data_source_id):
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
