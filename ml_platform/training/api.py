"""
Training Domain API Endpoints

API endpoints for managing full-scale training runs on Vertex AI.
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction

from .models import TrainingRun
from .services import TrainingService

logger = logging.getLogger(__name__)


def _get_model_endpoint(request):
    """Get model endpoint from session."""
    from ml_platform.models import ModelEndpoint
    endpoint_id = request.session.get('model_endpoint_id')
    if not endpoint_id:
        return None
    try:
        return ModelEndpoint.objects.get(id=endpoint_id)
    except ModelEndpoint.DoesNotExist:
        return None


def _serialize_training_run(training_run, include_details=False):
    """
    Serialize a TrainingRun model to dict.

    Args:
        training_run: TrainingRun model instance
        include_details: If True, include full configuration and error details

    Returns:
        Dict representation of the training run
    """
    data = {
        'id': training_run.id,
        'run_number': training_run.run_number,
        'display_name': training_run.display_name,
        'name': training_run.name,
        'description': training_run.description,

        # Relationships
        'ml_model_id': training_run.ml_model_id,
        'base_experiment_id': training_run.base_experiment_id,
        'dataset_id': training_run.dataset_id,
        'dataset_name': training_run.dataset.name if training_run.dataset else None,
        'feature_config_id': training_run.feature_config_id,
        'feature_config_name': training_run.feature_config.name if training_run.feature_config else None,
        'model_config_id': training_run.model_config_id,
        'model_config_name': training_run.model_config.name if training_run.model_config else None,

        # Type and status
        'model_type': training_run.model_type,
        'status': training_run.status,
        'current_stage': training_run.current_stage,
        'current_epoch': training_run.current_epoch,
        'total_epochs': training_run.total_epochs,
        'progress_percent': training_run.progress_percent,
        'stage_details': training_run.stage_details,

        # Pipeline info
        'vertex_pipeline_job_name': training_run.vertex_pipeline_job_name,

        # Timestamps
        'created_at': training_run.created_at.isoformat() if training_run.created_at else None,
        'started_at': training_run.started_at.isoformat() if training_run.started_at else None,
        'completed_at': training_run.completed_at.isoformat() if training_run.completed_at else None,
        'scheduled_at': training_run.scheduled_at.isoformat() if training_run.scheduled_at else None,
        'elapsed_seconds': training_run.elapsed_seconds,
        'duration_seconds': training_run.duration_seconds,

        # User
        'created_by': training_run.created_by.username if training_run.created_by else None,

        # Evaluation
        'is_blessed': training_run.is_blessed,

        # Deployment
        'is_deployed': training_run.is_deployed,
        'deployed_at': training_run.deployed_at.isoformat() if training_run.deployed_at else None,
    }

    # Add metrics based on model type
    if training_run.model_type == TrainingRun.MODEL_TYPE_MULTITASK:
        # Multitask: Include BOTH retrieval and ranking metrics
        data.update({
            # Retrieval metrics
            'recall_at_5': training_run.recall_at_5,
            'recall_at_10': training_run.recall_at_10,
            'recall_at_50': training_run.recall_at_50,
            'recall_at_100': training_run.recall_at_100,
            # Ranking metrics
            'rmse': training_run.rmse,
            'mae': training_run.mae,
            'test_rmse': training_run.test_rmse,
            'test_mae': training_run.test_mae,
            'loss': training_run.loss,
        })
    elif training_run.model_type == TrainingRun.MODEL_TYPE_RANKING:
        # Ranking model metrics
        data.update({
            'rmse': training_run.rmse,
            'mae': training_run.mae,
            'test_rmse': training_run.test_rmse,
            'test_mae': training_run.test_mae,
            'loss': training_run.loss,
            # Keep recall fields as None for consistency
            'recall_at_5': None,
            'recall_at_10': None,
            'recall_at_50': None,
            'recall_at_100': None,
        })
    else:
        # Retrieval model metrics
        data.update({
            'recall_at_5': training_run.recall_at_5,
            'recall_at_10': training_run.recall_at_10,
            'recall_at_50': training_run.recall_at_50,
            'recall_at_100': training_run.recall_at_100,
            'loss': training_run.loss,
            # Keep ranking fields as None for consistency
            'rmse': None,
            'mae': None,
            'test_rmse': None,
            'test_mae': None,
        })

    if include_details:
        # Include full configuration
        data['training_params'] = training_run.training_params
        data['gpu_config'] = training_run.gpu_config
        data['evaluator_config'] = training_run.evaluator_config
        data['deployment_config'] = training_run.deployment_config
        data['evaluation_results'] = training_run.evaluation_results
        data['artifacts'] = training_run.artifacts
        data['training_history_json'] = training_run.training_history_json

        # Model registry info
        data['vertex_model_name'] = training_run.vertex_model_name
        data['vertex_model_version'] = training_run.vertex_model_version
        data['vertex_model_resource_name'] = training_run.vertex_model_resource_name
        data['endpoint_resource_name'] = training_run.endpoint_resource_name

        # Error info
        data['error_message'] = training_run.error_message
        data['error_stage'] = training_run.error_stage
        data['error_details'] = training_run.error_details
        data['gcs_artifacts_path'] = training_run.gcs_artifacts_path

    return data


@csrf_exempt
@require_http_methods(["GET", "POST"])
def training_run_list(request):
    """
    List or create Training Runs.

    GET /api/training-runs/?page=1&page_size=10
    GET /api/training-runs/?status=running
    GET /api/training-runs/?model_type=retrieval
    GET /api/training-runs/?dataset_id=123

    POST /api/training-runs/
    {
        "name": "my-model-v1",
        "description": "...",
        "dataset_id": 1,
        "feature_config_id": 2,
        "model_config_id": 3,
        "base_experiment_id": 456,  // optional
        "training_params": {...},
        "gpu_config": {...},
        "evaluator_config": {...},
        "deployment_config": {...}
    }
    """
    model_endpoint = _get_model_endpoint(request)
    if not model_endpoint:
        return JsonResponse({
            'success': False,
            'error': 'No model endpoint selected'
        }, status=400)

    if request.method == 'GET':
        return _training_run_list_get(request, model_endpoint)
    else:
        return _training_run_create(request, model_endpoint)


def _training_run_list_get(request, model_endpoint):
    """Handle GET request for training run list."""
    try:
        # Build queryset with filters
        queryset = TrainingRun.objects.filter(
            ml_model=model_endpoint
        ).select_related('dataset', 'feature_config', 'model_config', 'created_by')

        # Apply filters
        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        model_type = request.GET.get('model_type')
        if model_type:
            queryset = queryset.filter(model_type=model_type)

        dataset_id = request.GET.get('dataset_id')
        if dataset_id:
            queryset = queryset.filter(dataset_id=dataset_id)

        feature_config_id = request.GET.get('feature_config_id')
        if feature_config_id:
            queryset = queryset.filter(feature_config_id=feature_config_id)

        model_config_id = request.GET.get('model_config_id')
        if model_config_id:
            queryset = queryset.filter(model_config_id=model_config_id)

        # Search filter
        search = request.GET.get('search', '').strip()
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(run_number__icontains=search)
            )

        # Order by most recent first
        queryset = queryset.order_by('-created_at')

        # Get total count before pagination
        total_count = queryset.count()

        # Pagination
        try:
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 10))
        except ValueError:
            page = 1
            page_size = 10

        # Clamp values
        page = max(1, page)
        page_size = max(1, min(50, page_size))  # Max 50 per page

        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        page = min(page, total_pages)  # Don't exceed total pages

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        training_runs = list(queryset[start_idx:end_idx])

        # Refresh status for running/submitting training runs from Vertex AI
        running_runs = [tr for tr in training_runs
                        if tr.status in (TrainingRun.STATUS_RUNNING, TrainingRun.STATUS_SUBMITTING)]

        if running_runs:
            try:
                service = TrainingService(model_endpoint)
                for tr in running_runs:
                    try:
                        service.refresh_status(tr)
                    except Exception as refresh_error:
                        logger.warning(f"Failed to refresh status for {tr.display_name} (id={tr.id}): {refresh_error}")
            except Exception as service_error:
                logger.warning(f"Failed to initialize TrainingService for status refresh: {service_error}")

        return JsonResponse({
            'success': True,
            'training_runs': [_serialize_training_run(tr) for tr in training_runs],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })

    except Exception as e:
        logger.exception(f"Error listing training runs: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _training_run_create(request, model_endpoint):
    """Handle POST request to create a training run."""
    try:
        data = json.loads(request.body)

        # Required fields
        required_fields = ['name', 'dataset_id', 'feature_config_id', 'model_config_id']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return JsonResponse({
                'success': False,
                'error': f"Missing required fields: {', '.join(missing)}"
            }, status=400)

        # Import models
        from ml_platform.models import Dataset, FeatureConfig, ModelConfig, QuickTest

        # Validate dataset
        try:
            dataset = Dataset.objects.get(
                id=data['dataset_id'],
                model_endpoint=model_endpoint
            )
        except Dataset.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f"Dataset {data['dataset_id']} not found"
            }, status=404)

        # Validate feature config
        try:
            feature_config = FeatureConfig.objects.get(
                id=data['feature_config_id'],
                dataset__model_endpoint=model_endpoint
            )
        except FeatureConfig.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f"FeatureConfig {data['feature_config_id']} not found"
            }, status=404)

        # Validate model config
        try:
            model_config = ModelConfig.objects.get(
                id=data['model_config_id'],
                model_endpoint=model_endpoint
            )
        except ModelConfig.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f"ModelConfig {data['model_config_id']} not found"
            }, status=404)

        # Validate base experiment (optional)
        base_experiment = None
        if data.get('base_experiment_id'):
            try:
                base_experiment = QuickTest.objects.get(
                    id=data['base_experiment_id'],
                    feature_config__dataset__model_endpoint=model_endpoint
                )
            except QuickTest.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f"Base experiment {data['base_experiment_id']} not found"
                }, status=404)

        # Create training run using service
        service = TrainingService(model_endpoint)
        training_run = service.create_training_run(
            name=data['name'],
            description=data.get('description', ''),
            dataset=dataset,
            feature_config=feature_config,
            model_config=model_config,
            base_experiment=base_experiment,
            training_params=data.get('training_params', {}),
            gpu_config=data.get('gpu_config', {}),
            evaluator_config=data.get('evaluator_config', {}),
            deployment_config=data.get('deployment_config', {}),
            created_by=request.user if request.user.is_authenticated else None,
        )

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run, include_details=True)
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error creating training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def training_run_detail(request, training_run_id):
    """
    Get detailed status and results for a Training Run.

    GET /api/training-runs/<id>/

    Returns:
    {
        "success": true,
        "training_run": {
            "id": 456,
            "status": "completed",
            "metrics": {...},
            ...
        }
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            training_run = TrainingRun.objects.select_related(
                'dataset', 'feature_config', 'model_config', 'created_by', 'base_experiment'
            ).get(
                id=training_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {training_run_id} not found'
            }, status=404)

        # Refresh status if running/submitting
        if training_run.status in (TrainingRun.STATUS_RUNNING, TrainingRun.STATUS_SUBMITTING):
            try:
                service = TrainingService(model_endpoint)
                service.refresh_status(training_run)
            except Exception as e:
                logger.warning(f"Failed to refresh status for training run {training_run_id}: {e}")

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run, include_details=True)
        })

    except Exception as e:
        logger.exception(f"Error getting training run detail: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_run_cancel(request, training_run_id):
    """
    Cancel a running Training Run.

    POST /api/training-runs/<id>/cancel/

    Returns:
    {
        "success": true,
        "training_run": {
            "id": 456,
            "status": "cancelled",
            ...
        }
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            training_run = TrainingRun.objects.get(
                id=training_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {training_run_id} not found'
            }, status=404)

        # Check if cancellable
        if not training_run.is_cancellable:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun is not running (status: {training_run.status})'
            }, status=400)

        # Cancel the training run
        service = TrainingService(model_endpoint)
        training_run = service.cancel_training_run(training_run)

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run)
        })

    except Exception as e:
        logger.exception(f"Error cancelling training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def training_run_delete(request, training_run_id):
    """
    Delete a Training Run and its associated GCS artifacts.

    DELETE /api/training-runs/<id>/delete/

    Only training runs in terminal states (completed, failed, cancelled, not_blessed)
    can be deleted. Running or submitting training runs must be cancelled first.

    Returns:
    {
        "success": true,
        "message": "Training run deleted successfully"
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            training_run = TrainingRun.objects.get(
                id=training_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {training_run_id} not found'
            }, status=404)

        # Check if deletable (must be in terminal state)
        if not training_run.is_terminal:
            return JsonResponse({
                'success': False,
                'error': f"Cannot delete training run in '{training_run.status}' state. Please cancel the training run first."
            }, status=400)

        # Delete the training run
        service = TrainingService(model_endpoint)
        service.delete_training_run(training_run)

        return JsonResponse({
            'success': True,
            'message': 'Training run deleted successfully'
        })

    except Exception as e:
        logger.exception(f"Error deleting training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
