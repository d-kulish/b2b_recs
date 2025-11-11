from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
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

        # Create data source
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

        return JsonResponse({
            'status': 'success',
            'source': {
                'id': source.id,
                'name': source.name,
                'source_type': source.source_type,
                'source_host': source.source_host or '',
                'source_port': source.source_port,
                'source_database': source.source_database or '',
                'source_schema': source.source_schema or '',
                'source_username': source.source_username or '',
                'bigquery_project': source.bigquery_project or '',
                'bigquery_dataset': source.bigquery_dataset or '',
                'file_path': source.file_path or '',
                'is_enabled': source.is_enabled,
                'tables': tables,
            }
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
def api_etl_test_connection(request, source_id):
    """
    API endpoint to test a data source connection.
    """
    try:
        source = get_object_or_404(DataSource, id=source_id)

        # TODO: Implement actual connection testing
        # For now, simulate success
        source.connection_tested = True
        source.last_test_at = timezone.now()
        source.last_test_message = "Connection test successful (simulated)"
        source.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Connection test successful',
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


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
