"""
Core Views for ML Platform

This module contains:
- System Dashboard (landing page)
- Model/Endpoint creation and page views
- Core API endpoints (training, deployment, pipeline status)
- System-level API endpoints (KPIs, charts, activity)

ETL-related views and APIs have been migrated to ml_platform.etl
Connection-related APIs have been migrated to ml_platform.connections
"""
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Avg, Max, Min
from django.db.models.functions import TruncDate
from django.conf import settings
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
    QuickTest,
    ResourceMetrics,
)
from .training.models import TrainingRun, DeployedEndpoint, RegisteredModel


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

    # Assets KPIs
    total_registered_models = RegisteredModel.objects.count()
    total_trainings = TrainingRun.objects.count()
    total_experiments = QuickTest.objects.count()

    # Accuracy KPIs (from TrainingRun only — QuickTests excluded as they're sampled runs)
    best_retrieval_recall = TrainingRun.objects.filter(
        model_type='retrieval', recall_at_100__isnull=False
    ).aggregate(Max('recall_at_100'))['recall_at_100__max']

    best_ranking_rmse = TrainingRun.objects.filter(
        model_type='ranking', rmse__isnull=False
    ).aggregate(Min('rmse'))['rmse__min']

    best_hybrid_recall = TrainingRun.objects.filter(
        model_type='multitask', recall_at_100__isnull=False
    ).aggregate(Max('recall_at_100'))['recall_at_100__max']

    context = {
        'models': models,
        'total_models': total_models,
        'active_models': active_models,
        'recent_runs': recent_runs,
        'latest_metrics': latest_metrics,
        'total_registered_models': total_registered_models,
        'total_trainings': total_trainings,
        'total_experiments': total_experiments,
        'best_retrieval_recall': best_retrieval_recall,
        'best_ranking_rmse': best_ranking_rmse,
        'best_hybrid_recall': best_hybrid_recall,
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

    # Set session for API calls
    request.session['model_endpoint_id'] = model_id

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


# ============================================================================
# SYSTEM-LEVEL API ENDPOINTS
# ============================================================================

@login_required
def api_system_kpis(request):
    """
    API endpoint returning 8 system KPIs for the dashboard.
    """
    try:
        now = timezone.now()
        cutoff_30d = now - timedelta(days=30)
        cutoff_24h = now - timedelta(hours=24)

        # Basic counts
        models_count = ModelEndpoint.objects.count()
        live_endpoints = DeployedEndpoint.objects.filter(is_active=True).count()

        # Training stats (30 days)
        training_runs_30d = TrainingRun.objects.filter(created_at__gte=cutoff_30d)
        training_runs_count = training_runs_30d.count()

        # Success rate calculation
        completed_count = training_runs_30d.filter(status='completed').count()
        total_finished = training_runs_30d.filter(
            status__in=['completed', 'failed', 'cancelled', 'not_blessed']
        ).count()
        success_rate = round((completed_count / total_finished) * 100, 1) if total_finished > 0 else 0

        # Experiments (30 days)
        experiments_30d = QuickTest.objects.filter(created_at__gte=cutoff_30d).count()

        # ETL runs (24 hours)
        etl_runs_24h = ETLRun.objects.filter(started_at__gte=cutoff_24h).count()

        # BigQuery data stats (with graceful fallback)
        data_tables = 0
        data_volume_gb = 0
        try:
            from .utils.bigquery_manager import BigQueryTableManager
            project_id = getattr(settings, 'GCP_PROJECT_ID', 'b2b-recs')
            bq_manager = BigQueryTableManager(project_id=project_id)
            tables_result = bq_manager.list_tables()
            if tables_result.get('success'):
                tables = tables_result.get('tables', [])
                data_tables = len(tables)
                total_bytes = sum(t.get('num_bytes', 0) or 0 for t in tables)
                data_volume_gb = round(total_bytes / (1024 ** 3), 2)
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'data': {
                'models': models_count,
                'live_endpoints': live_endpoints,
                'training_runs_30d': training_runs_count,
                'training_success_rate': success_rate,
                'experiments_30d': experiments_30d,
                'etl_runs_24h': etl_runs_24h,
                'data_tables': data_tables,
                'data_volume_gb': data_volume_gb,
                # Placeholder fields for future implementation
                'requests_30d': 0,
                'avg_latency_ms': 0,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e),
        }, status=500)


@login_required
def api_system_charts(request):
    """
    API endpoint returning 4 chart datasets for the dashboard.
    """
    try:
        now = timezone.now()
        cutoff_30d = now - timedelta(days=30)
        cutoff_14d = now - timedelta(days=14)
        cutoff_7d = now - timedelta(days=7)

        # 1. Training Activity (30 days) - line chart
        training_by_day = TrainingRun.objects.filter(
            created_at__gte=cutoff_30d
        ).annotate(
            date=TruncDate('created_at')
        ).values('date', 'status').annotate(
            count=Count('id')
        ).order_by('date')

        training_activity = {}
        for row in training_by_day:
            date_str = row['date'].strftime('%Y-%m-%d')
            if date_str not in training_activity:
                training_activity[date_str] = {'started': 0, 'completed': 0, 'failed': 0}
            status = row['status']
            if status in ['pending', 'submitting', 'running', 'scheduled']:
                training_activity[date_str]['started'] += row['count']
            elif status == 'completed':
                training_activity[date_str]['completed'] += row['count']
            elif status in ['failed', 'cancelled', 'not_blessed']:
                training_activity[date_str]['failed'] += row['count']

        training_labels = sorted(training_activity.keys())
        training_data = {
            'labels': training_labels,
            'started': [training_activity.get(d, {}).get('started', 0) for d in training_labels],
            'completed': [training_activity.get(d, {}).get('completed', 0) for d in training_labels],
            'failed': [training_activity.get(d, {}).get('failed', 0) for d in training_labels],
        }

        # 2. Model Performance (best/avg Recall@100 trend)
        perf_by_day = TrainingRun.objects.filter(
            created_at__gte=cutoff_30d,
            recall_at_100__isnull=False
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            best_recall=Max('recall_at_100'),
            avg_recall=Avg('recall_at_100')
        ).order_by('date')

        perf_labels = [row['date'].strftime('%Y-%m-%d') for row in perf_by_day]
        model_performance = {
            'labels': perf_labels,
            'best': [round(row['best_recall'] * 100, 2) if row['best_recall'] else 0 for row in perf_by_day],
            'avg': [round(row['avg_recall'] * 100, 2) if row['avg_recall'] else 0 for row in perf_by_day],
        }

        # 3. Endpoint Requests (7 days) - placeholder data for now
        endpoint_labels = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
        endpoint_requests = {
            'labels': endpoint_labels,
            'requests': [0] * 7,  # Placeholder - would need request logging to populate
        }

        # 4. ETL Health (14 days) - stacked bar
        etl_by_day = ETLRun.objects.filter(
            started_at__gte=cutoff_14d
        ).annotate(
            date=TruncDate('started_at')
        ).values('date', 'status').annotate(
            count=Count('id')
        ).order_by('date')

        etl_health = {}
        for row in etl_by_day:
            if row['date']:
                date_str = row['date'].strftime('%Y-%m-%d')
                if date_str not in etl_health:
                    etl_health[date_str] = {'completed': 0, 'failed': 0}
                if row['status'] == 'completed':
                    etl_health[date_str]['completed'] += row['count']
                elif row['status'] in ['failed', 'partial']:
                    etl_health[date_str]['failed'] += row['count']

        etl_labels = sorted(etl_health.keys())
        etl_data = {
            'labels': etl_labels,
            'completed': [etl_health.get(d, {}).get('completed', 0) for d in etl_labels],
            'failed': [etl_health.get(d, {}).get('failed', 0) for d in etl_labels],
        }

        return JsonResponse({
            'success': True,
            'data': {
                'training_activity': training_data,
                'model_performance': model_performance,
                'endpoint_requests': endpoint_requests,
                'etl_health': etl_data,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e),
        }, status=500)


@login_required
def api_system_resource_charts(request):
    """
    API endpoint returning resource-oriented chart data from ResourceMetrics snapshots.
    Returns chart datasets: combined_storage, bq_jobs, etl_health,
    cloud_run_requests, gpu_hours, gpu_types.
    """
    try:
        cutoff_30d = timezone.now().date() - timedelta(days=30)

        snapshots_30d = list(
            ResourceMetrics.objects.filter(date__gte=cutoff_30d).order_by('date')
        )

        # Latest snapshot for current-state charts
        latest = snapshots_30d[-1] if snapshots_30d else None

        # 1. Combined Storage (30d) - stacked bar (BigQuery + SQL + GCS)
        combined_storage = {'labels': [], 'bigquery_gb': [], 'sql_gb': [], 'buckets_gb': []}
        if snapshots_30d:
            combined_storage['labels'] = [s.date.isoformat() for s in snapshots_30d]
            combined_storage['bigquery_gb'] = [
                round(s.bq_total_bytes / (1024**3), 2) for s in snapshots_30d
            ]
            combined_storage['sql_gb'] = [
                round(s.db_size_bytes / (1024**3), 2) for s in snapshots_30d
            ]
            combined_storage['buckets_gb'] = [
                round(s.gcs_total_bytes / (1024**3), 2) for s in snapshots_30d
            ]

        # 2. BQ Jobs & Bytes Billed (14d) - dual axis
        bq_jobs = {'labels': [], 'completed': [], 'failed': [], 'bytes_billed_gb': []}
        if snapshots_30d:
            bq_jobs['labels'] = [s.date.isoformat() for s in snapshots_30d]
            bq_jobs['completed'] = [s.bq_jobs_completed for s in snapshots_30d]
            bq_jobs['failed'] = [s.bq_jobs_failed for s in snapshots_30d]
            bq_jobs['bytes_billed_gb'] = [
                round(s.bq_bytes_billed / (1024**3), 2) for s in snapshots_30d
            ]

        # 3. ETL Health (30d) - stacked bar (from ResourceMetrics snapshots)
        etl_health = {'labels': [], 'completed': [], 'failed': []}
        if snapshots_30d:
            etl_health['labels'] = [s.date.isoformat() for s in snapshots_30d]
            etl_health['completed'] = [s.etl_jobs_completed for s in snapshots_30d]
            etl_health['failed'] = [s.etl_jobs_failed for s in snapshots_30d]

        # 4. Cloud Run Request Volume (30d)
        cloud_run_requests = {'labels': [], 'requests': []}
        if snapshots_30d:
            cloud_run_requests['labels'] = [s.date.isoformat() for s in snapshots_30d]
            cloud_run_requests['requests'] = [s.cloud_run_total_requests for s in snapshots_30d]

        # 5. GPU Training Hours (30d) - bar chart
        gpu_hours = {'labels': [], 'hours': [], 'completed': [], 'failed': []}
        if snapshots_30d:
            gpu_hours['labels'] = [s.date.isoformat() for s in snapshots_30d]
            gpu_hours['hours'] = [s.gpu_training_hours for s in snapshots_30d]
            gpu_hours['completed'] = [s.gpu_jobs_completed for s in snapshots_30d]
            gpu_hours['failed'] = [s.gpu_jobs_failed for s in snapshots_30d]

        # 6. GPU Jobs by Type (latest snapshot) - horizontal bar
        gpu_types = {'types': [], 'total_hours': 0}
        if latest and latest.gpu_jobs_by_type:
            gpu_types['types'] = latest.gpu_jobs_by_type
            gpu_types['total_hours'] = sum(
                t.get('hours', 0) for t in latest.gpu_jobs_by_type
            )

        return JsonResponse({
            'success': True,
            'data': {
                'combined_storage': combined_storage,
                'bq_jobs': bq_jobs,
                'etl_health': etl_health,
                'cloud_run_requests': cloud_run_requests,
                'gpu_hours': gpu_hours,
                'gpu_types': gpu_types,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e),
        }, status=500)


def _time_ago(dt):
    """Convert datetime to human-readable time ago string."""
    if not dt:
        return ''
    now = timezone.now()
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return 'just now'
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f'{minutes}m ago'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f'{hours}h ago'
    else:
        days = int(seconds / 86400)
        return f'{days}d ago'


@login_required
def api_system_recent_activity(request):
    """
    API endpoint returning recent activity merged from multiple sources.
    """
    try:
        activities = []

        # Training runs (last 10)
        training_runs = TrainingRun.objects.select_related('ml_model').order_by('-created_at')[:10]
        for run in training_runs:
            status_map = {
                'pending': 'pending',
                'submitting': 'pending',
                'scheduled': 'pending',
                'running': 'running',
                'completed': 'completed',
                'deployed': 'completed',
                'failed': 'failed',
                'cancelled': 'failed',
                'not_blessed': 'failed',
                'deploy_failed': 'failed',
            }
            activities.append({
                'type': 'Training',
                'status': status_map.get(run.status, 'pending'),
                'model': run.ml_model.name if run.ml_model else run.name,
                'time': run.created_at.isoformat(),
                'time_ago': _time_ago(run.created_at),
            })

        # Quick tests (last 10)
        quick_tests = QuickTest.objects.select_related('feature_config__model_endpoint').order_by('-created_at')[:10]
        for qt in quick_tests:
            status_map = {
                'pending': 'pending',
                'submitting': 'pending',
                'running': 'running',
                'completed': 'completed',
                'failed': 'failed',
                'cancelled': 'failed',
            }
            model_name = ''
            if qt.feature_config and qt.feature_config.model_endpoint:
                model_name = qt.feature_config.model_endpoint.name
            activities.append({
                'type': 'Experiment',
                'status': status_map.get(qt.status, 'pending'),
                'model': model_name,
                'time': qt.created_at.isoformat(),
                'time_ago': _time_ago(qt.created_at),
            })

        # ETL runs (last 10)
        etl_runs = ETLRun.objects.select_related('model_endpoint').order_by('-created_at')[:10]
        for run in etl_runs:
            status_map = {
                'pending': 'pending',
                'running': 'running',
                'completed': 'completed',
                'partial': 'completed',
                'failed': 'failed',
                'cancelled': 'failed',
            }
            activities.append({
                'type': 'ETL',
                'status': status_map.get(run.status, 'pending'),
                'model': run.model_endpoint.name if run.model_endpoint else '',
                'time': run.created_at.isoformat(),
                'time_ago': _time_ago(run.created_at),
            })

        # Deployed endpoints (last 10)
        deployments = DeployedEndpoint.objects.select_related('registered_model').order_by('-updated_at')[:10]
        for dep in deployments:
            activities.append({
                'type': 'Deployment',
                'status': 'completed' if dep.is_active else 'failed',
                'model': dep.registered_model.model_name if dep.registered_model else dep.service_name,
                'time': dep.updated_at.isoformat(),
                'time_ago': _time_ago(dep.updated_at),
            })

        # Sort all activities by time and take top 5
        activities.sort(key=lambda x: x['time'], reverse=True)
        activities = activities[:5]

        return JsonResponse({
            'success': True,
            'data': activities
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e),
        }, status=500)


# ============================================================================
# SCHEDULER WEBHOOKS
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def scheduler_collect_metrics_webhook(request):
    """
    Webhook for Cloud Scheduler to trigger daily resource metrics collection.
    Accepts OIDC authenticated requests from Cloud Scheduler.
    No login required as this uses OIDC token authentication.
    """
    import logging
    from datetime import date
    from django.core.management import call_command
    from io import StringIO

    logger = logging.getLogger(__name__)

    try:
        output = StringIO()
        call_command('collect_resource_metrics', stdout=output)
        logger.info(f'Scheduled metrics collection completed for {date.today()}')

        return JsonResponse({
            'status': 'success',
            'message': f'Metrics collected for {date.today()}',
            'output': output.getvalue(),
        })

    except Exception as e:
        logger.error(f'Scheduled metrics collection failed: {e}')
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)
