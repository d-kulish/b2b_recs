"""
Core Views for ML Platform

This module contains:
- System Dashboard (landing page)
- Model/Endpoint creation and page views
- Core API endpoints (training, deployment, pipeline status)

ETL-related views and APIs have been migrated to ml_platform.etl
Connection-related APIs have been migrated to ml_platform.connections
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .models import (
    ModelEndpoint,
    ETLConfiguration,
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


# Note: model_dataset view has been moved to ml_platform/datasets/views.py
# Note: model_configs view has been moved to ml_platform/configs/views.py


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
# CORE API ENDPOINTS (AJAX)
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
