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
from django.utils import timezone

from .models import TrainingRun, TrainingSchedule, RegisteredModel
from .services import TrainingService, TrainingServiceError
from .registered_model_service import RegisteredModelService

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
    # Badge shows whether pipeline deployment succeeded (historical fact)
    # - 'deployed' status means deployment step completed successfully
    # - STATUS_DEPLOYED constant also indicates successful deployment
    is_deployed = (
        training_run.deployment_status == 'deployed' or
        training_run.status == TrainingRun.STATUS_DEPLOYED
    )

    # Also provide current endpoint state for UI that needs it
    has_active_endpoint = (
        training_run.deployed_endpoint is not None and
        training_run.deployed_endpoint.is_active
    )

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
        'retrieval_algorithm': training_run.model_config.retrieval_algorithm if training_run.model_config else None,
        'base_experiment_number': training_run.base_experiment.experiment_number if training_run.base_experiment else None,
        'is_scheduled': training_run.schedule_id is not None,
        'registered_model_id': training_run.registered_model_id,

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

        # Deployment (shows pipeline deployment result - historical fact)
        'is_deployed': is_deployed,
        # Current endpoint state (for UI that needs real-time status)
        'has_active_endpoint': has_active_endpoint,

        # Deployment tracking
        'deploy_enabled': training_run.deploy_enabled,
        'deployment_status': training_run.deployment_status,
        'deployment_error': training_run.deployment_error,
        'deployed_endpoint_id': training_run.deployed_endpoint_id,
        'deployed_endpoint_url': training_run.deployed_endpoint.service_url if training_run.deployed_endpoint else None,
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
        data['schedule_config'] = training_run.schedule_config
        data['evaluation_results'] = training_run.evaluation_results
        data['artifacts'] = training_run.artifacts
        data['training_history_json'] = training_run.training_history_json

        # Model registry info
        data['vertex_model_name'] = training_run.vertex_model_name
        data['vertex_model_version'] = training_run.vertex_model_version
        data['vertex_model_resource_name'] = training_run.vertex_model_resource_name
        data['vertex_parent_model_resource_name'] = training_run.vertex_parent_model_resource_name
        data['is_version'] = bool(training_run.vertex_parent_model_resource_name)

        # Error info
        data['error_message'] = training_run.error_message
        data['error_stage'] = training_run.error_stage
        data['error_details'] = training_run.error_details
        data['gcs_artifacts_path'] = training_run.gcs_artifacts_path

        # Deployment timestamps
        data['deployment_started_at'] = (
            training_run.deployment_started_at.isoformat()
            if training_run.deployment_started_at else None
        )
        data['deployment_completed_at'] = (
            training_run.deployment_completed_at.isoformat()
            if training_run.deployment_completed_at else None
        )

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

        # Filter by registered model name (for Models Registry dropdown)
        vertex_model_name = request.GET.get('vertex_model_name')
        if vertex_model_name:
            queryset = queryset.filter(vertex_model_name=vertex_model_name)

        # Search filter
        search = request.GET.get('search', '').strip()
        if search:
            import re
            from django.db.models import Q

            # Check for "Run #N" or "#N" or just "N" pattern
            run_match = re.match(r'^(?:run\s*)?#?(\d+)$', search, re.IGNORECASE)
            if run_match:
                # Exact match on run_number
                queryset = queryset.filter(run_number=int(run_match.group(1)))
            else:
                # Text search on name and description
                queryset = queryset.filter(
                    Q(name__icontains=search) |
                    Q(description__icontains=search)
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

        # Validate model config (ModelConfig is global, not tied to model_endpoint)
        try:
            model_config = ModelConfig.objects.get(id=data['model_config_id'])
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

        # Auto-submit pipeline unless explicitly disabled or scheduled
        # If scheduled_at is provided, keep in PENDING for scheduler
        auto_submit = data.get('auto_submit', True)
        scheduled_at = data.get('scheduled_at')

        if auto_submit and not scheduled_at:
            try:
                service.submit_training_pipeline(training_run)
                logger.info(f"Training pipeline submitted for {training_run.display_name}")
            except Exception as submit_error:
                # Log but don't fail - training run was created successfully
                logger.error(f"Failed to submit pipeline for {training_run.display_name}: {submit_error}")
                # Refresh to get error status
                training_run.refresh_from_db()

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
def training_run_check_name(request):
    """
    Check if a training run name is available (unique).

    GET /api/training-runs/check-name/?name=my-model-v1

    Returns:
    {
        "success": true,
        "available": true/false,
        "message": "Name is available" / "Name already exists"
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        name = request.GET.get('name', '').strip()
        if not name:
            return JsonResponse({
                'success': False,
                'error': 'Name parameter is required'
            }, status=400)

        # Check if name exists for this model endpoint
        exists = TrainingRun.objects.filter(
            ml_model=model_endpoint,
            name=name
        ).exists()

        return JsonResponse({
            'success': True,
            'available': not exists,
            'message': 'Name is available' if not exists else 'Name already exists'
        })

    except Exception as e:
        logger.exception(f"Error checking training run name: {e}")
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


@csrf_exempt
@require_http_methods(["POST"])
def training_run_submit(request, training_run_id):
    """
    Submit a PENDING Training Run to Vertex AI.

    POST /api/training-runs/<id>/submit/

    This is used for training runs that were created without auto_submit,
    or for scheduled training runs that need to be submitted manually.

    Returns:
    {
        "success": true,
        "training_run": {
            "id": 456,
            "status": "submitting",
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
                'dataset', 'feature_config', 'model_config'
            ).get(
                id=training_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {training_run_id} not found'
            }, status=404)

        # Check if training run can be submitted
        if training_run.status != TrainingRun.STATUS_PENDING:
            return JsonResponse({
                'success': False,
                'error': f"Cannot submit training run in '{training_run.status}' state. "
                         f"Only PENDING training runs can be submitted."
            }, status=400)

        # Submit the training run
        service = TrainingService(model_endpoint)
        try:
            training_run = service.submit_training_pipeline(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run, include_details=True)
        })

    except Exception as e:
        logger.exception(f"Error submitting training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_run_rerun(request, training_run_id):
    """
    Re-run a Training Run with the same configuration.

    POST /api/training-runs/<id>/rerun/

    Creates a new TrainingRun with the same configuration and submits it.
    Works for any terminal state (completed, failed, not_blessed, cancelled).

    Returns:
    {
        "success": true,
        "training_run": {
            "id": 789,  // New run ID
            "status": "submitting",
            ...
        },
        "message": "Re-run created and submitted"
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
                'dataset', 'feature_config', 'model_config', 'base_experiment'
            ).get(
                id=training_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {training_run_id} not found'
            }, status=404)

        # Only allow rerun for terminal states
        TERMINAL_STATUSES = ['completed', 'failed', 'not_blessed', 'cancelled']
        if training_run.status not in TERMINAL_STATUSES:
            return JsonResponse({
                'success': False,
                'error': f"Cannot re-run training in '{training_run.status}' state. "
                         f"Only terminal states can be re-run."
            }, status=400)

        # Re-run the training run
        service = TrainingService(model_endpoint)
        try:
            new_run = service.rerun_training_run(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(new_run, include_details=True),
            'message': f"Re-run created as {new_run.display_name}"
        })

    except Exception as e:
        logger.exception(f"Error re-running training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def training_run_config(request, training_run_id):
    """
    Get or update training run configuration for editing.

    GET /api/training-runs/<id>/config/
    Returns the training run configuration for the edit wizard.

    PATCH /api/training-runs/<id>/config/
    Updates the training run configuration. Only allowed for terminal states.
    """
    model_endpoint = _get_model_endpoint(request)
    if not model_endpoint:
        return JsonResponse({
            'success': False,
            'error': 'No model endpoint selected'
        }, status=400)

    try:
        training_run = TrainingRun.objects.select_related(
            'dataset', 'feature_config', 'model_config', 'base_experiment'
        ).get(
            id=training_run_id,
            ml_model=model_endpoint
        )
    except TrainingRun.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'TrainingRun {training_run_id} not found'
        }, status=404)

    if request.method == 'GET':
        return _training_run_config_get(training_run)
    else:
        return _training_run_config_patch(request, training_run, model_endpoint)


def _training_run_config_get(training_run):
    """Handle GET request for training run config."""
    config_data = {
        'id': training_run.id,
        'name': training_run.name,
        'dataset_id': training_run.dataset_id,
        'dataset_name': training_run.dataset.name if training_run.dataset else None,
        'feature_config_id': training_run.feature_config_id,
        'feature_config_name': training_run.feature_config.name if training_run.feature_config else None,
        'model_config_id': training_run.model_config_id,
        'model_config_name': training_run.model_config.name if training_run.model_config else None,
        'base_experiment_id': training_run.base_experiment_id,
        'base_experiment_number': training_run.base_experiment.experiment_number if training_run.base_experiment else None,
        'training_params': training_run.training_params,
        'gpu_config': training_run.gpu_config,
        'evaluator_config': training_run.evaluator_config,
        'schedule_config': training_run.schedule_config,
        'status': training_run.status,
        'is_terminal': training_run.is_terminal,
    }

    return JsonResponse({
        'success': True,
        'config': config_data
    })


def _training_run_config_patch(request, training_run, model_endpoint):
    """Handle PATCH request to update training run config."""
    # Only allow editing for terminal states
    if not training_run.is_terminal:
        return JsonResponse({
            'success': False,
            'error': f"Cannot edit training run in '{training_run.status}' state. "
                     f"Only terminal states (completed, failed, cancelled) can be edited."
        }, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)

    # Track what fields are updated
    updated_fields = []

    # Update training_params if provided
    if 'training_params' in data:
        training_run.training_params = {
            **training_run.training_params,
            **data['training_params']
        }
        updated_fields.append('training_params')

    # Update gpu_config if provided
    if 'gpu_config' in data:
        training_run.gpu_config = {
            **training_run.gpu_config,
            **data['gpu_config']
        }
        updated_fields.append('gpu_config')

    # Update evaluator_config if provided
    if 'evaluator_config' in data:
        training_run.evaluator_config = {
            **training_run.evaluator_config,
            **data['evaluator_config']
        }
        updated_fields.append('evaluator_config')

    # Update schedule_config if provided
    if 'schedule_config' in data:
        old_schedule_config = training_run.schedule_config or {}
        new_schedule_config = data['schedule_config']

        # Handle Cloud Scheduler job updates
        old_job_name = old_schedule_config.get('cloud_scheduler_job_name', '')
        old_schedule_type = old_schedule_config.get('schedule_type', 'now')
        new_schedule_type = new_schedule_config.get('schedule_type', 'now')

        # If schedule type changed or schedule was removed, handle Cloud Scheduler
        if old_schedule_type != 'now' and old_job_name:
            # Need to delete old Cloud Scheduler job
            try:
                service = TrainingService(model_endpoint)
                service.delete_cloud_scheduler_job(old_job_name)
                logger.info(f"Deleted old Cloud Scheduler job: {old_job_name}")
            except Exception as e:
                logger.warning(f"Failed to delete old Cloud Scheduler job: {e}")

        # Create new Cloud Scheduler job if needed
        if new_schedule_type != 'now':
            try:
                service = TrainingService(model_endpoint)
                job_name = service.create_cloud_scheduler_job_for_training_run(
                    training_run=training_run,
                    schedule_config=new_schedule_config
                )
                new_schedule_config['cloud_scheduler_job_name'] = job_name
                logger.info(f"Created new Cloud Scheduler job: {job_name}")
            except Exception as e:
                logger.error(f"Failed to create Cloud Scheduler job: {e}")
                return JsonResponse({
                    'success': False,
                    'error': f"Failed to create schedule: {str(e)}"
                }, status=500)

        training_run.schedule_config = new_schedule_config
        updated_fields.append('schedule_config')

    # Save if any fields were updated
    if updated_fields:
        training_run.save(update_fields=updated_fields)
        logger.info(f"Updated training run {training_run.id} fields: {updated_fields}")

    return JsonResponse({
        'success': True,
        'config': {
            'id': training_run.id,
            'training_params': training_run.training_params,
            'gpu_config': training_run.gpu_config,
            'evaluator_config': training_run.evaluator_config,
            'schedule_config': training_run.schedule_config,
        },
        'updated_fields': updated_fields
    })


@csrf_exempt
@require_http_methods(["POST"])
def training_run_schedule_webhook(request, training_run_id):
    """
    Webhook endpoint for Cloud Scheduler to trigger training runs.

    POST /api/training-runs/<id>/schedule-webhook/

    This endpoint is called by Cloud Scheduler when a scheduled training
    should be triggered. It reads the template training run's CURRENT
    configuration and creates a new training run.
    """
    # Authenticate webhook request (OIDC token validation)
    # In production, this should verify the Cloud Scheduler OIDC token
    auth_header = request.headers.get('Authorization', '')

    try:
        training_run = TrainingRun.objects.select_related(
            'dataset', 'feature_config', 'model_config', 'base_experiment', 'ml_model'
        ).get(id=training_run_id)
    except TrainingRun.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'TrainingRun {training_run_id} not found'
        }, status=404)

    # Verify the training run has a schedule config
    schedule_config = training_run.schedule_config or {}
    if not schedule_config.get('schedule_type') or schedule_config.get('schedule_type') == 'now':
        return JsonResponse({
            'success': False,
            'error': 'Training run does not have an active schedule'
        }, status=400)

    try:
        # Create a new training run with the template's current config
        service = TrainingService(training_run.ml_model)
        new_run = service.create_training_run(
            name=training_run.name,
            description=f"Scheduled run from template {training_run.display_name}",
            dataset=training_run.dataset,
            feature_config=training_run.feature_config,
            model_config=training_run.model_config,
            base_experiment=training_run.base_experiment,
            training_params=training_run.training_params,
            gpu_config=training_run.gpu_config,
            evaluator_config=training_run.evaluator_config,
            deployment_config=training_run.deployment_config,
            created_by=training_run.created_by,
        )

        # Submit the new run
        service.submit_training_pipeline(new_run)

        logger.info(
            f"Scheduled webhook triggered new training run {new_run.id} "
            f"from template {training_run.id}"
        )

        return JsonResponse({
            'success': True,
            'training_run_id': new_run.id,
            'message': f"Created and submitted training run {new_run.display_name}"
        })

    except Exception as e:
        logger.exception(f"Error in schedule webhook for training run {training_run_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_run_deploy(request, training_run_id):
    """
    Deploy a completed, blessed Training Run to a Vertex AI Endpoint.

    POST /api/training-runs/<id>/deploy/

    Returns:
    {
        "success": true,
        "training_run": {
            "id": 456,
            "is_deployed": true,
            "deployed_at": "2024-01-15T10:30:00Z",
            "endpoint_resource_name": "projects/.../endpoints/...",
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
            training_run = TrainingRun.objects.select_related('deployed_endpoint').get(
                id=training_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {training_run_id} not found'
            }, status=404)

        # Validate state
        if training_run.status != TrainingRun.STATUS_COMPLETED:
            return JsonResponse({
                'success': False,
                'error': f"Cannot deploy training run in '{training_run.status}' state. "
                         f"Only completed training runs can be deployed."
            }, status=400)

        if not training_run.is_blessed:
            return JsonResponse({
                'success': False,
                'error': "Cannot deploy unblessed model. Use 'Push Anyway' first."
            }, status=400)

        # Check if already deployed to Cloud Run
        if training_run.deployed_endpoint and training_run.deployed_endpoint.is_active:
            return JsonResponse({
                'success': False,
                'error': 'Training run is already deployed to endpoint'
            }, status=400)

        # Deploy the model
        service = TrainingService(model_endpoint)
        try:
            training_run = service.deploy_model(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        # Re-fetch training run to get updated deployment info
        training_run.refresh_from_db()

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(
                training_run,
                include_details=True
            ),
            'message': 'Model deployed to endpoint'
        })

    except Exception as e:
        logger.exception(f"Error deploying training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_run_push(request, training_run_id):
    """
    Force-push a not-blessed Training Run to Vertex AI Model Registry.

    POST /api/training-runs/<id>/push/

    This allows manual override when the evaluator threshold wasn't met
    but the user wants to use the model anyway.

    Returns:
    {
        "success": true,
        "training_run": {
            "id": 456,
            "status": "completed",  // Promoted from not_blessed
            "is_blessed": true,
            "vertex_model_resource_name": "projects/.../models/...",
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

        # Only allow for not_blessed runs
        if training_run.status != TrainingRun.STATUS_NOT_BLESSED:
            return JsonResponse({
                'success': False,
                'error': f"Cannot force-push training run in '{training_run.status}' state. "
                         f"Only not-blessed training runs can be force-pushed."
            }, status=400)

        # Force push the model
        service = TrainingService(model_endpoint)
        try:
            training_run = service.force_push_model(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run, include_details=True),
            'message': "Model force-pushed to registry and status promoted to completed"
        })

    except Exception as e:
        logger.exception(f"Error force-pushing training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_run_register(request, training_run_id):
    """
    Register a completed Training Run to Vertex AI Model Registry.

    POST /api/training-runs/<id>/register/

    For completed runs that failed initial automatic registration
    (e.g., due to invalid container image or transient errors).

    Returns:
    {
        "success": true,
        "training_run": {...},
        "message": "Model registered to Vertex AI Model Registry"
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

        # Only allow for completed runs that aren't registered yet
        if training_run.status != TrainingRun.STATUS_COMPLETED:
            return JsonResponse({
                'success': False,
                'error': f"Cannot register training run in '{training_run.status}' state. "
                         f"Only completed training runs can be registered."
            }, status=400)

        if training_run.vertex_model_resource_name:
            return JsonResponse({
                'success': False,
                'error': f"Training run is already registered as {training_run.vertex_model_name}."
            }, status=400)

        # Register the model
        service = TrainingService(model_endpoint)
        try:
            training_run = service.register_model(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run, include_details=True),
            'message': f"Model registered to Vertex AI Model Registry as {training_run.vertex_model_name}"
        })

    except Exception as e:
        logger.exception(f"Error registering training run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def cloud_run_services_list(request):
    """
    List existing Cloud Run services in the project.

    GET /api/cloud-run/services/

    Returns list of Cloud Run services that can be updated with new model deployments.
    Services ending in '-serving' are flagged as ML serving endpoints.

    Returns:
    {
        "success": true,
        "services": [
            {
                "name": "model-serving",
                "url": "https://model-serving-xxx.run.app",
                "status": "Ready",
                "is_ml_serving": true
            },
            ...
        ]
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        service = TrainingService(model_endpoint)
        services = service.list_cloud_run_services()

        return JsonResponse({
            'success': True,
            'services': services
        })

    except Exception as e:
        logger.exception(f"Error listing Cloud Run services: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'services': []
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_run_deploy_cloud_run(request, training_run_id):
    """
    Deploy a trained model to Cloud Run with TF Serving.

    POST /api/training-runs/<id>/deploy-cloud-run/

    Request body (optional):
    {
        "deployment_config": {
            "min_instances": 1,
            "max_instances": 10,
            "memory": "4Gi",
            "cpu": "2",
            "timeout": "300"
        }
    }

    This deploys the model to a Cloud Run service for serverless inference.
    The model must be registered in the Model Registry first.

    Returns:
    {
        "success": true,
        "training_run": {...},
        "endpoint_url": "https://model-serving-xxx.run.app",
        "message": "Model deployed to Cloud Run"
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

        # Validate state - allow both completed and not_blessed
        if training_run.status not in [TrainingRun.STATUS_COMPLETED, TrainingRun.STATUS_NOT_BLESSED]:
            return JsonResponse({
                'success': False,
                'error': f"Cannot deploy training run in '{training_run.status}' state. "
                         f"Only completed or not-blessed training runs can be deployed."
            }, status=400)

        # Check if model is registered
        if not training_run.vertex_model_resource_name:
            return JsonResponse({
                'success': False,
                'error': "Model not registered in Model Registry. Wait for registration to complete."
            }, status=400)

        # Parse deployment config from request body
        try:
            body = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            body = {}

        deployment_config = body.get('deployment_config', {})
        service_name = body.get('service_name')  # Optional custom service name

        # Merge with existing config (request takes precedence)
        existing_config = training_run.deployment_config or {}
        merged_config = {**existing_config, **deployment_config}

        # Update training run with new deployment config
        if deployment_config:
            training_run.deployment_config = merged_config
            training_run.save(update_fields=['deployment_config'])

        # Deploy to Cloud Run (independent of Vertex AI endpoint deployment)
        service = TrainingService(model_endpoint)
        try:
            endpoint_url = service.deploy_to_cloud_run(training_run, service_name=service_name)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run, include_details=True),
            'endpoint_url': endpoint_url,
            'message': f"Model deployed to Cloud Run: {endpoint_url}"
        })

    except Exception as e:
        logger.exception(f"Error deploying training run to Cloud Run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def registered_model_endpoints(request, registered_model_id):
    """
    GET /api/registered-models/<id>/endpoints/

    List Cloud Run endpoints associated with a registered model.
    """
    from .models import DeployedEndpoint

    try:
        registered_model = RegisteredModel.objects.get(id=registered_model_id)
    except RegisteredModel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Model not found'}, status=404)

    endpoints = DeployedEndpoint.objects.filter(
        registered_model=registered_model,
        is_active=True
    ).order_by('-updated_at')

    return JsonResponse({
        'success': True,
        'endpoints': [
            {
                'id': ep.id,
                'service_name': ep.service_name,
                'service_url': ep.service_url,
                'deployed_version': ep.deployed_version,
                'deployed_training_run_id': ep.deployed_training_run_id,
                'updated_at': ep.updated_at.isoformat(),
            }
            for ep in endpoints
        ]
    })


# =============================================================================
# Training Run Data Insights API Endpoints
# =============================================================================

def _get_training_run_pipeline_root(training_run) -> str:
    """
    Get pipeline root GCS path for a training run.

    Uses the same bucket pattern as experiments.

    Args:
        training_run: TrainingRun instance

    Returns:
        GCS path to pipeline root, or None if not available
    """
    run_id = training_run.cloud_build_run_id
    if not run_id:
        return None
    return f"gs://b2b-recs-pipeline-staging/pipeline_root/{run_id}"


@csrf_exempt
@require_http_methods(["GET"])
def training_run_statistics(request, training_run_id):
    """
    Get dataset statistics from TFDV artifacts for a training run.

    GET /api/training-runs/<id>/statistics/

    Returns:
    {
        "success": true,
        "statistics": {
            "available": true,
            "num_examples": 1234567,
            "num_features": 45,
            "avg_missing_ratio": 2.3,
            ...
        }
    }
    """
    from django.http import HttpResponse
    from ml_platform.experiments.artifact_service import ArtifactService

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

        # Get pipeline root for this training run
        pipeline_root = _get_training_run_pipeline_root(training_run)
        if not pipeline_root:
            return JsonResponse({
                'success': True,
                'statistics': {
                    'available': False,
                    'message': 'Pipeline artifacts not available'
                }
            })

        # Use ArtifactService to get statistics via tfdv-parser
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)

        # Call tfdv-parser service directly with pipeline_root
        response = artifact_service._call_tfdv_parser('/parse/statistics', {
            'pipeline_root': pipeline_root,
            'include_html': False
        })

        if not response:
            return JsonResponse({
                'success': True,
                'statistics': {
                    'available': False,
                    'message': 'Failed to connect to statistics parser service'
                }
            })

        if not response.get('success'):
            return JsonResponse({
                'success': True,
                'statistics': {
                    'available': False,
                    'message': response.get('error', 'Unknown error from parser service')
                }
            })

        statistics = response.get('statistics', {})
        return JsonResponse({
            'success': True,
            'statistics': statistics
        })

    except Exception as e:
        logger.exception(f"Error getting training run statistics: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def training_run_schema(request, training_run_id):
    """
    Get schema information from TensorFlow Metadata artifacts for a training run.

    GET /api/training-runs/<id>/schema/

    Returns:
    {
        "success": true,
        "schema": {
            "available": true,
            "num_features": 45,
            "features": [...]
        }
    }
    """
    from ml_platform.experiments.artifact_service import ArtifactService

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

        # Get pipeline root for this training run
        pipeline_root = _get_training_run_pipeline_root(training_run)
        if not pipeline_root:
            return JsonResponse({
                'success': True,
                'schema': {
                    'available': False,
                    'message': 'Pipeline artifacts not available'
                }
            })

        # Use ArtifactService to get schema via tfdv-parser
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)

        # Call tfdv-parser service directly with pipeline_root
        response = artifact_service._call_tfdv_parser('/parse/schema', {
            'pipeline_root': pipeline_root
        })

        if not response:
            return JsonResponse({
                'success': True,
                'schema': {
                    'available': False,
                    'message': 'Failed to connect to schema parser service'
                }
            })

        if not response.get('success'):
            return JsonResponse({
                'success': True,
                'schema': {
                    'available': False,
                    'message': response.get('error', 'Unknown error from parser service')
                }
            })

        schema = response.get('schema', {})
        return JsonResponse({
            'success': True,
            'schema': schema
        })

    except Exception as e:
        logger.exception(f"Error getting training run schema: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def training_run_training_history(request, training_run_id):
    """
    Get training history (per-epoch metrics) with caching.

    Uses cached training history from Django DB for fast loading (<1 second).
    Falls back to GCS if cache is empty, and caches the result.

    GET /api/training-runs/<id>/training-history/

    Returns:
    {
        "success": true,
        "training_history": {
            "available": true,
            "cached_at": "2024-12-30T10:30:00Z",
            "epochs": [0, 5, 10, ...],
            "loss": {"train": [...], "val": [...]},
            "final_metrics": {...},
            ...
        },
        "source": "cache" | "gcs"
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

        # Use cache for fast loading
        from ml_platform.experiments.training_cache_service import TrainingCacheService

        cache_service = TrainingCacheService()

        # Check if cache exists
        if training_run.training_history_json:
            return JsonResponse({
                'success': True,
                'training_history': training_run.training_history_json,
                'source': 'cache'
            })

        # Cache miss - fetch from GCS and cache
        training_history = cache_service.get_training_history_for_run(training_run)

        return JsonResponse({
            'success': True,
            'training_history': training_history,
            'source': 'gcs'
        })

    except Exception as e:
        logger.exception(f"Error getting training history: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def training_run_histogram_data(request, training_run_id):
    """
    Get histogram data (weight/gradient distributions) on demand.

    This endpoint fetches histogram data from GCS (training_metrics.json).
    It's called only when the user expands the Weight Analysis section.

    GET /api/training-runs/<id>/histogram-data/

    Returns:
    {
        "success": true,
        "histogram_data": {
            "weight_stats": {
                "query": {"histogram": {"bin_edges": [...], "counts": [[...], ...]}},
                "candidate": {...}
            },
            "gradient_stats": {
                "query": {"histogram": {...}},
                "candidate": {...}
            }
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

        if not training_run.gcs_artifacts_path:
            return JsonResponse({
                'success': False,
                'error': 'No GCS artifacts path - histogram data not available'
            }, status=404)

        # Fetch histogram data from GCS (training_metrics.json)
        try:
            from google.cloud import storage

            gcs_path = training_run.gcs_artifacts_path
            path = gcs_path[5:]  # Remove 'gs://'
            bucket_name = path.split('/')[0]
            blob_path = '/'.join(path.split('/')[1:]) + '/training_metrics.json'

            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)

            if not blob.exists():
                return JsonResponse({
                    'success': False,
                    'error': 'training_metrics.json not found in GCS'
                }, status=404)

            content = blob.download_as_string().decode('utf-8')
            metrics = json.loads(content)

            # Extract histogram data
            histogram_data = {
                'weight_stats': {},
                'gradient_stats': {}
            }

            for tower in ['query', 'candidate', 'rating_head']:
                if tower in metrics.get('weight_stats', {}):
                    tower_data = metrics['weight_stats'][tower]
                    if 'histogram' in tower_data:
                        histogram_data['weight_stats'][tower] = {'histogram': tower_data['histogram']}

                if tower in metrics.get('gradient_stats', {}):
                    tower_data = metrics['gradient_stats'][tower]
                    if 'histogram' in tower_data:
                        histogram_data['gradient_stats'][tower] = {'histogram': tower_data['histogram']}

            return JsonResponse({
                'success': True,
                'histogram_data': histogram_data
            })

        except Exception as e:
            logger.warning(f"Could not read histogram data from GCS: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Could not read histogram data from GCS'
            }, status=500)

    except Exception as e:
        logger.exception(f"Error getting histogram data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def training_run_component_logs(request, training_run_id, component):
    """
    Get recent logs for a specific pipeline component of a training run.

    GET /api/training-runs/<id>/logs/<component>/

    Components: Examples, Stats, Schema, Transform, Train

    Returns:
    {
        "success": true,
        "logs": {
            "available": true,
            "component": "Transform",
            "logs": [
                {"timestamp": "14:32:05", "severity": "INFO", "message": "Starting..."},
                ...
            ],
            "count": 10
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

        # Get component logs using dedicated logs service
        from ml_platform.experiments.pipeline_logs_service import PipelineLogsService
        logs_service = PipelineLogsService(project_id=model_endpoint.gcp_project_id)
        logs = logs_service.get_component_logs(training_run, component)

        return JsonResponse({
            'success': True,
            'logs': logs
        })

    except Exception as e:
        logger.exception(f"Error getting component logs: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def training_run_tfdv_page(request, training_run_id):
    """
    Serve TFDV HTML visualization as a standalone page for a training run.

    Opens in a new browser tab with proper rendering.

    GET /training/runs/<id>/tfdv/

    Returns: HTML page (Content-Type: text/html)
    """
    from django.http import HttpResponse
    from ml_platform.experiments.artifact_service import ArtifactService

    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return HttpResponse(
                '<html><body><h1>Error</h1><p>No model endpoint selected. '
                'Please select a model endpoint first.</p></body></html>',
                content_type='text/html',
                status=400
            )

        try:
            training_run = TrainingRun.objects.get(
                id=training_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return HttpResponse(
                f'<html><body><h1>Error</h1><p>TrainingRun {training_run_id} not found.</p></body></html>',
                content_type='text/html',
                status=404
            )

        # Get pipeline root for this training run
        pipeline_root = _get_training_run_pipeline_root(training_run)
        if not pipeline_root:
            return HttpResponse(
                '<html><body><h1>Error</h1><p>Pipeline artifacts not available for this training run.</p></body></html>',
                content_type='text/html',
                status=404
            )

        # Get TFDV HTML visualization
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        response = artifact_service._call_tfdv_parser('/parse/statistics/html', {
            'pipeline_root': pipeline_root
        })

        if response and response.get('success'):
            html = response.get('html')
            if html:
                # Wrap in a proper HTML page with title and basic styling
                page_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TFDV Statistics - Run #{training_run.run_number}</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 16px 24px;
            margin: -20px -20px 20px -20px;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 20px;
            color: #333;
        }}
        .header .subtitle {{
            color: #666;
            font-size: 14px;
            margin-top: 4px;
        }}
        .header .back-btn {{
            color: #1a73e8;
            text-decoration: none;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .header .back-btn:hover {{
            text-decoration: underline;
        }}
        .tfdv-container {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>TFDV Statistics</h1>
            <div class="subtitle">Training Run #{training_run.run_number} - {training_run.name or 'Unnamed'}</div>
        </div>
        <a href="javascript:window.close()" class="back-btn">
            <span>&larr;</span> Close
        </a>
    </div>
    <div class="tfdv-container">
        {html}
    </div>
</body>
</html>'''
                return HttpResponse(page_html, content_type='text/html')

        return HttpResponse(
            '<html><body><h1>Error</h1><p>TFDV visualization not available for this training run.</p></body></html>',
            content_type='text/html',
            status=404
        )

    except Exception as e:
        logger.exception(f"Error getting training run TFDV page: {e}")
        return HttpResponse(
            f'<html><body><h1>Error</h1><p>Failed to load TFDV visualization: {str(e)}</p></body></html>',
            content_type='text/html',
            status=500
        )


# =============================================================================
# Training Schedule API Endpoints
# =============================================================================

from .schedule_service import TrainingScheduleService, TrainingScheduleServiceError


def _serialize_training_schedule(schedule, include_runs=False):
    """
    Serialize a TrainingSchedule model to dict.

    Args:
        schedule: TrainingSchedule model instance
        include_runs: If True, include recent training runs

    Returns:
        Dict representation of the schedule
    """
    data = {
        'id': schedule.id,
        'name': schedule.name,
        'description': schedule.description,

        # Schedule configuration
        'schedule_type': schedule.schedule_type,
        'schedule_type_display': schedule.get_schedule_type_display(),
        'scheduled_datetime': schedule.scheduled_datetime.isoformat() if schedule.scheduled_datetime else None,
        'schedule_time': schedule.schedule_time.strftime('%H:%M') if schedule.schedule_time else None,
        'schedule_day_of_week': schedule.schedule_day_of_week,
        'schedule_day_of_month': schedule.schedule_day_of_month,
        'schedule_timezone': schedule.schedule_timezone,

        # Relationships
        'ml_model_id': schedule.ml_model_id,
        'dataset_id': schedule.dataset_id,
        'dataset_name': schedule.dataset.name if schedule.dataset else None,
        'feature_config_id': schedule.feature_config_id,
        'feature_config_name': schedule.feature_config.name if schedule.feature_config else None,
        'model_config_id': schedule.model_config_id,
        'model_config_name': schedule.model_config.name if schedule.model_config else None,
        'base_experiment_id': schedule.base_experiment_id,

        # RegisteredModel info
        'registered_model_id': schedule.registered_model_id,
        'registered_model_name': schedule.registered_model.model_name if schedule.registered_model else None,

        # Status
        'status': schedule.status,
        'status_display': schedule.get_status_display(),
        'is_active': schedule.is_active,
        'is_recurring': schedule.is_recurring,

        # Statistics
        'last_run_at': schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        'next_run_at': schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        'total_runs': schedule.total_runs,
        'successful_runs': schedule.successful_runs,
        'failed_runs': schedule.failed_runs,
        'success_rate': schedule.success_rate,

        # Configuration
        'training_params': schedule.training_params,
        'gpu_config': schedule.gpu_config,
        'evaluator_config': schedule.evaluator_config,
        'deployment_config': schedule.deployment_config,

        # User
        'created_by': schedule.created_by.username if schedule.created_by else None,

        # Timestamps
        'created_at': schedule.created_at.isoformat() if schedule.created_at else None,
        'updated_at': schedule.updated_at.isoformat() if schedule.updated_at else None,
    }

    if include_runs:
        # Include recent training runs
        recent_runs = schedule.training_runs.order_by('-created_at')[:5]
        data['recent_runs'] = [
            {
                'id': run.id,
                'run_number': run.run_number,
                'status': run.status,
                'created_at': run.created_at.isoformat() if run.created_at else None,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
            }
            for run in recent_runs
        ]

    return data


@csrf_exempt
@require_http_methods(["GET", "POST"])
def training_schedule_list(request):
    """
    List or create Training Schedules.

    GET /api/training/schedules/?status=active
    POST /api/training/schedules/
    {
        "name": "Weekly Retraining",
        "schedule_type": "weekly",  // 'once', 'daily', 'weekly', or 'now' for immediate
        "schedule_time": "09:00",
        "schedule_day_of_week": 0,
        "schedule_timezone": "UTC",
        "dataset_id": 1,
        "feature_config_id": 2,
        "model_config_id": 3,
        "base_experiment_id": 456,
        "training_params": {...},
        "gpu_config": {...},
        "evaluator_config": {...}
    }
    """
    model_endpoint = _get_model_endpoint(request)
    if not model_endpoint:
        return JsonResponse({
            'success': False,
            'error': 'No model endpoint selected'
        }, status=400)

    if request.method == 'GET':
        return _training_schedule_list_get(request, model_endpoint)
    else:
        return _training_schedule_create(request, model_endpoint)


def _training_schedule_list_get(request, model_endpoint):
    """Handle GET request for training schedule list."""
    try:
        queryset = TrainingSchedule.objects.filter(
            ml_model=model_endpoint
        ).select_related('dataset', 'feature_config', 'model_config', 'created_by')

        # Filter by status
        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Order by most recent first
        queryset = queryset.order_by('-created_at')

        # Pagination
        try:
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 20))
        except ValueError:
            page = 1
            page_size = 20

        page = max(1, page)
        page_size = max(1, min(50, page_size))

        total_count = queryset.count()
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        page = min(page, total_pages)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        schedules = list(queryset[start_idx:end_idx])

        return JsonResponse({
            'success': True,
            'schedules': [_serialize_training_schedule(s) for s in schedules],
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
        logger.exception(f"Error listing training schedules: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _training_schedule_create(request, model_endpoint):
    """Handle POST request to create a training schedule."""
    try:
        data = json.loads(request.body)

        # Required fields
        required_fields = ['name', 'schedule_type', 'dataset_id', 'feature_config_id', 'model_config_id']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return JsonResponse({
                'success': False,
                'error': f"Missing required fields: {', '.join(missing)}"
            }, status=400)

        schedule_type = data['schedule_type']

        # If schedule_type is 'now', create a TrainingRun and submit immediately
        if schedule_type == 'now' or schedule_type == 'immediate':
            return _create_immediate_training_run(request, model_endpoint, data)

        # Validate schedule type
        valid_types = [
            TrainingSchedule.SCHEDULE_TYPE_ONCE,
            TrainingSchedule.SCHEDULE_TYPE_HOURLY,
            TrainingSchedule.SCHEDULE_TYPE_DAILY,
            TrainingSchedule.SCHEDULE_TYPE_WEEKLY,
            TrainingSchedule.SCHEDULE_TYPE_MONTHLY
        ]
        if schedule_type not in valid_types:
            return JsonResponse({
                'success': False,
                'error': f"Invalid schedule_type. Must be one of: {', '.join(valid_types)}, 'now'"
            }, status=400)

        # Import models
        from ml_platform.models import Dataset, FeatureConfig, ModelConfig, QuickTest
        from datetime import datetime, time as dt_time

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

        # Validate model config (ModelConfig is global, not tied to model_endpoint)
        try:
            model_config = ModelConfig.objects.get(id=data['model_config_id'])
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

        # Parse schedule-specific fields
        scheduled_datetime = None
        schedule_time = None
        schedule_day_of_week = None
        schedule_day_of_month = None

        if schedule_type == TrainingSchedule.SCHEDULE_TYPE_ONCE:
            if not data.get('scheduled_datetime'):
                return JsonResponse({
                    'success': False,
                    'error': 'scheduled_datetime is required for one-time schedules'
                }, status=400)
            try:
                scheduled_datetime = datetime.fromisoformat(data['scheduled_datetime'].replace('Z', '+00:00'))
            except ValueError as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid scheduled_datetime format: {e}'
                }, status=400)

        elif schedule_type == TrainingSchedule.SCHEDULE_TYPE_HOURLY:
            # Hourly: uses schedule_time for the minute (e.g., "00:15" means run at :15 each hour)
            if data.get('schedule_time'):
                try:
                    hour, minute = map(int, data['schedule_time'].split(':'))
                    schedule_time = dt_time(0, minute)  # Only minute matters for hourly
                except (ValueError, AttributeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid schedule_time format. Use HH:MM'
                    }, status=400)
            else:
                schedule_time = dt_time(0, 0)  # Default to :00

        elif schedule_type in (TrainingSchedule.SCHEDULE_TYPE_DAILY, TrainingSchedule.SCHEDULE_TYPE_WEEKLY):
            if data.get('schedule_time'):
                try:
                    hour, minute = map(int, data['schedule_time'].split(':'))
                    schedule_time = dt_time(hour, minute)
                except (ValueError, AttributeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid schedule_time format. Use HH:MM'
                    }, status=400)
            else:
                schedule_time = dt_time(9, 0)  # Default to 9 AM

            if schedule_type == TrainingSchedule.SCHEDULE_TYPE_WEEKLY:
                schedule_day_of_week = data.get('schedule_day_of_week', 0)
                if not isinstance(schedule_day_of_week, int) or schedule_day_of_week < 0 or schedule_day_of_week > 6:
                    return JsonResponse({
                        'success': False,
                        'error': 'schedule_day_of_week must be 0-6 (Monday-Sunday)'
                    }, status=400)

        elif schedule_type == TrainingSchedule.SCHEDULE_TYPE_MONTHLY:
            # Monthly: day of month (1-28) and time of day
            schedule_day_of_month = data.get('schedule_day_of_month', 1)
            if not isinstance(schedule_day_of_month, int) or schedule_day_of_month < 1 or schedule_day_of_month > 31:
                return JsonResponse({
                    'success': False,
                    'error': 'schedule_day_of_month must be 1-31'
                }, status=400)

            if data.get('schedule_time'):
                try:
                    hour, minute = map(int, data['schedule_time'].split(':'))
                    schedule_time = dt_time(hour, minute)
                except (ValueError, AttributeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid schedule_time format. Use HH:MM'
                    }, status=400)
            else:
                schedule_time = dt_time(9, 0)  # Default to 9 AM

        # Handle schedule_name vs name distinction (for wizard mode)
        # - schedule_name: the name for the TrainingSchedule
        # - name: the model name (for RegisteredModel)
        # For backward compatibility, if schedule_name is not provided, use name for the schedule
        schedule_name = data.get('schedule_name', data['name'])
        schedule_description = data.get('schedule_description', data.get('description', ''))
        model_name = data['name']

        # Determine model type from model config (QuickTest links to ModelConfig)
        model_type = 'retrieval'  # Default
        if model_config:
            model_type = model_config.model_type or 'retrieval'
        elif base_experiment and base_experiment.model_config:
            model_type = base_experiment.model_config.model_type or 'retrieval'

        # Get or create RegisteredModel for this model name
        reg_model_service = RegisteredModelService(model_endpoint)
        registered_model = reg_model_service.get_or_create_for_training(
            model_name=model_name,
            model_type=model_type,
            created_by=request.user if request.user.is_authenticated else None
        )

        # Create the schedule
        schedule = TrainingSchedule.objects.create(
            ml_model=model_endpoint,
            name=schedule_name,
            description=schedule_description,
            schedule_type=schedule_type,
            scheduled_datetime=scheduled_datetime,
            schedule_time=schedule_time,
            schedule_day_of_week=schedule_day_of_week,
            schedule_day_of_month=schedule_day_of_month,
            schedule_timezone=data.get('schedule_timezone', 'UTC'),
            dataset=dataset,
            feature_config=feature_config,
            model_config=model_config,
            base_experiment=base_experiment,
            training_params=data.get('training_params', {}),
            gpu_config=data.get('gpu_config', {}),
            evaluator_config=data.get('evaluator_config', {}),
            deployment_config=data.get('deployment_config', {}),
            created_by=request.user if request.user.is_authenticated else None,
            status=TrainingSchedule.STATUS_ACTIVE,
            # Link to RegisteredModel
            registered_model=registered_model,
        )

        # Create Cloud Scheduler job
        service = TrainingScheduleService(model_endpoint)
        webhook_base_url = request.build_absolute_uri('/').rstrip('/')
        result = service.create_schedule(schedule, webhook_base_url)

        if not result['success']:
            # Rollback schedule creation if scheduler job fails
            schedule.delete()
            return JsonResponse({
                'success': False,
                'error': f"Failed to create Cloud Scheduler job: {result['message']}"
            }, status=500)

        logger.info(f"Created training schedule {schedule.id}: {schedule.name}")

        return JsonResponse({
            'success': True,
            'schedule': _serialize_training_schedule(schedule)
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error creating training schedule: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _create_immediate_training_run(request, model_endpoint, data):
    """Create and submit a training run immediately (schedule_type='now')."""
    from ml_platform.models import Dataset, FeatureConfig, ModelConfig, QuickTest

    try:
        # Validate dataset
        dataset = Dataset.objects.get(
            id=data['dataset_id'],
            model_endpoint=model_endpoint
        )
    except Dataset.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f"Dataset {data['dataset_id']} not found"
        }, status=404)

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

    # ModelConfig is global, not tied to model_endpoint
    try:
        model_config = ModelConfig.objects.get(id=data['model_config_id'])
    except ModelConfig.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f"ModelConfig {data['model_config_id']} not found"
        }, status=404)

    base_experiment = None
    if data.get('base_experiment_id'):
        try:
            base_experiment = QuickTest.objects.get(
                id=data['base_experiment_id'],
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            pass

    # Create and submit training run using existing logic
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

    # Submit pipeline
    try:
        service.submit_training_pipeline(training_run)
        logger.info(f"Training pipeline submitted for {training_run.display_name}")
    except Exception as submit_error:
        logger.error(f"Failed to submit pipeline: {submit_error}")
        training_run.refresh_from_db()

    return JsonResponse({
        'success': True,
        'training_run': _serialize_training_run(training_run, include_details=True)
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def training_schedule_detail(request, schedule_id):
    """
    Get, update, or delete a Training Schedule.

    GET /api/training/schedules/<id>/
    PUT /api/training/schedules/<id>/
    DELETE /api/training/schedules/<id>/
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            schedule = TrainingSchedule.objects.select_related(
                'dataset', 'feature_config', 'model_config', 'created_by', 'base_experiment'
            ).get(
                id=schedule_id,
                ml_model=model_endpoint
            )
        except TrainingSchedule.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingSchedule {schedule_id} not found'
            }, status=404)

        if request.method == 'GET':
            return JsonResponse({
                'success': True,
                'schedule': _serialize_training_schedule(schedule, include_runs=True)
            })
        elif request.method == 'PUT':
            return _training_schedule_update(request, model_endpoint, schedule)
        else:  # DELETE
            service = TrainingScheduleService(model_endpoint)
            result = service.delete_schedule(schedule)

            if result['success']:
                schedule.delete()
                return JsonResponse({
                    'success': True,
                    'message': 'Schedule deleted successfully'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': result['message']
                }, status=500)

    except Exception as e:
        logger.exception(f"Error with training schedule detail: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _training_schedule_update(request, model_endpoint, schedule):
    """
    Handle PUT request to update a training schedule.

    Editable fields: name, description, schedule_type, schedule_time,
    schedule_day_of_week, schedule_day_of_month, schedule_timezone,
    scheduled_datetime.

    Training configuration (training_params, gpu_config, etc.) remains frozen.
    """
    from .schedule_service import TrainingScheduleService

    try:
        data = json.loads(request.body)

        # Validate schedule status
        if schedule.status not in (TrainingSchedule.STATUS_ACTIVE, TrainingSchedule.STATUS_PAUSED):
            return JsonResponse({
                'success': False,
                'error': f'Cannot edit schedule in {schedule.status} status. Only active or paused schedules can be edited.'
            }, status=400)

        # Validate required fields
        if 'name' in data and not data['name'].strip():
            return JsonResponse({
                'success': False,
                'error': 'Schedule name cannot be empty'
            }, status=400)

        # Validate schedule_type if provided
        if 'schedule_type' in data:
            valid_types = [
                TrainingSchedule.SCHEDULE_TYPE_ONCE,
                TrainingSchedule.SCHEDULE_TYPE_HOURLY,
                TrainingSchedule.SCHEDULE_TYPE_DAILY,
                TrainingSchedule.SCHEDULE_TYPE_WEEKLY,
                TrainingSchedule.SCHEDULE_TYPE_MONTHLY
            ]
            if data['schedule_type'] not in valid_types:
                return JsonResponse({
                    'success': False,
                    'error': f"Invalid schedule_type. Must be one of: {', '.join(valid_types)}"
                }, status=400)

        # Validate schedule_day_of_week if provided
        if 'schedule_day_of_week' in data:
            day = data['schedule_day_of_week']
            if day is not None and (not isinstance(day, int) or day < 0 or day > 6):
                return JsonResponse({
                    'success': False,
                    'error': 'schedule_day_of_week must be 0-6 (Monday=0, Sunday=6)'
                }, status=400)

        # Validate schedule_day_of_month if provided
        if 'schedule_day_of_month' in data:
            day = data['schedule_day_of_month']
            if day is not None and (not isinstance(day, int) or day < 1 or day > 31):
                return JsonResponse({
                    'success': False,
                    'error': 'schedule_day_of_month must be 1-31'
                }, status=400)

        # Validate scheduled_datetime for 'once' type
        schedule_type = data.get('schedule_type', schedule.schedule_type)
        if schedule_type == TrainingSchedule.SCHEDULE_TYPE_ONCE:
            if 'scheduled_datetime' in data:
                from django.utils.dateparse import parse_datetime
                dt = parse_datetime(data['scheduled_datetime']) if data['scheduled_datetime'] else None
                if dt and dt <= timezone.now():
                    return JsonResponse({
                        'success': False,
                        'error': 'scheduled_datetime must be in the future'
                    }, status=400)

        # Build webhook base URL
        webhook_base_url = request.build_absolute_uri('/').rstrip('/')

        # Extract only editable fields
        update_data = {}
        editable_fields = [
            'name', 'description', 'schedule_type', 'schedule_time',
            'schedule_day_of_week', 'schedule_day_of_month',
            'schedule_timezone', 'scheduled_datetime'
        ]
        for field in editable_fields:
            if field in data:
                update_data[field] = data[field]

        # Update schedule
        service = TrainingScheduleService(model_endpoint)
        result = service.update_schedule(schedule, webhook_base_url, update_data)

        if result['success']:
            # Refresh from DB to get updated fields
            schedule.refresh_from_db()
            return JsonResponse({
                'success': True,
                'schedule': _serialize_training_schedule(schedule),
                'message': result['message']
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['message']
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error updating training schedule: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_schedule_pause(request, schedule_id):
    """
    Pause a Training Schedule.

    POST /api/training/schedules/<id>/pause/
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            schedule = TrainingSchedule.objects.get(
                id=schedule_id,
                ml_model=model_endpoint
            )
        except TrainingSchedule.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingSchedule {schedule_id} not found'
            }, status=404)

        if schedule.status != TrainingSchedule.STATUS_ACTIVE:
            return JsonResponse({
                'success': False,
                'error': f'Cannot pause schedule in {schedule.status} status'
            }, status=400)

        service = TrainingScheduleService(model_endpoint)
        result = service.pause_schedule(schedule)

        if result['success']:
            schedule.refresh_from_db()
            return JsonResponse({
                'success': True,
                'schedule': _serialize_training_schedule(schedule)
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['message']
            }, status=500)

    except Exception as e:
        logger.exception(f"Error pausing training schedule: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_schedule_resume(request, schedule_id):
    """
    Resume a paused Training Schedule.

    POST /api/training/schedules/<id>/resume/
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            schedule = TrainingSchedule.objects.get(
                id=schedule_id,
                ml_model=model_endpoint
            )
        except TrainingSchedule.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingSchedule {schedule_id} not found'
            }, status=404)

        if schedule.status != TrainingSchedule.STATUS_PAUSED:
            return JsonResponse({
                'success': False,
                'error': f'Cannot resume schedule in {schedule.status} status'
            }, status=400)

        service = TrainingScheduleService(model_endpoint)
        result = service.resume_schedule(schedule)

        if result['success']:
            schedule.refresh_from_db()
            return JsonResponse({
                'success': True,
                'schedule': _serialize_training_schedule(schedule)
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['message']
            }, status=500)

    except Exception as e:
        logger.exception(f"Error resuming training schedule: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_schedule_cancel(request, schedule_id):
    """
    Cancel a Training Schedule (deletes Cloud Scheduler job).

    POST /api/training/schedules/<id>/cancel/
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            schedule = TrainingSchedule.objects.get(
                id=schedule_id,
                ml_model=model_endpoint
            )
        except TrainingSchedule.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingSchedule {schedule_id} not found'
            }, status=404)

        if schedule.status == TrainingSchedule.STATUS_CANCELLED:
            return JsonResponse({
                'success': False,
                'error': 'Schedule is already cancelled'
            }, status=400)

        service = TrainingScheduleService(model_endpoint)
        result = service.delete_schedule(schedule)

        schedule.refresh_from_db()
        return JsonResponse({
            'success': True,
            'schedule': _serialize_training_schedule(schedule)
        })

    except Exception as e:
        logger.exception(f"Error cancelling training schedule: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_schedule_trigger(request, schedule_id):
    """
    Manually trigger a scheduled training immediately.

    POST /api/training/schedules/<id>/trigger/
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            schedule = TrainingSchedule.objects.get(
                id=schedule_id,
                ml_model=model_endpoint
            )
        except TrainingSchedule.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingSchedule {schedule_id} not found'
            }, status=404)

        if schedule.status not in (TrainingSchedule.STATUS_ACTIVE, TrainingSchedule.STATUS_PAUSED):
            return JsonResponse({
                'success': False,
                'error': f'Cannot trigger schedule in {schedule.status} status'
            }, status=400)

        service = TrainingScheduleService(model_endpoint)
        result = service.trigger_now(schedule)

        if result['success']:
            training_run = TrainingRun.objects.get(id=result['training_run_id'])
            return JsonResponse({
                'success': True,
                'training_run': _serialize_training_run(training_run, include_details=True),
                'message': result['message']
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['message']
            }, status=500)

    except Exception as e:
        logger.exception(f"Error triggering training schedule: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def training_schedule_preview(request):
    """
    Preview the configuration that would be used for a schedule from a training run.

    GET /api/training/schedules/preview/?source_run_id=123

    Returns:
    {
        "success": true,
        "preview": {
            "source_run_id": 123,
            "source_run_name": "my-model-v1",
            "source_run_number": 5,
            "dataset_id": 1,
            "dataset_name": "Product Data",
            "feature_config_id": 2,
            "feature_config_name": "Standard Features",
            "model_config_id": 3,
            "model_config_name": "Retrieval Model",
            "model_type": "retrieval",
            "training_params": {...},
            "gpu_config": {...},
            "evaluator_config": {...}
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

        source_run_id = request.GET.get('source_run_id')
        if not source_run_id:
            return JsonResponse({
                'success': False,
                'error': 'source_run_id parameter is required'
            }, status=400)

        try:
            training_run = TrainingRun.objects.select_related(
                'dataset', 'feature_config', 'model_config', 'base_experiment'
            ).get(
                id=source_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {source_run_id} not found'
            }, status=404)

        preview = {
            'source_run_id': training_run.id,
            'source_run_name': training_run.name,
            'source_run_number': training_run.run_number,
            'source_run_display_name': training_run.display_name,
            'vertex_model_name': training_run.vertex_model_name,  # Trained model name (e.g., "chern_retriv_v5")
            'dataset_id': training_run.dataset_id,
            'dataset_name': training_run.dataset.name if training_run.dataset else None,
            'feature_config_id': training_run.feature_config_id,
            'feature_config_name': training_run.feature_config.name if training_run.feature_config else None,
            'model_config_id': training_run.model_config_id,
            'model_config_name': training_run.model_config.name if training_run.model_config else None,
            'model_type': training_run.model_type,
            'base_experiment_id': training_run.base_experiment_id,
            'base_experiment_number': training_run.base_experiment.experiment_number if training_run.base_experiment else None,
            'training_params': training_run.training_params or {},
            'gpu_config': training_run.gpu_config or {},
            'evaluator_config': training_run.evaluator_config or {},
            'deployment_config': training_run.deployment_config or {},
        }

        return JsonResponse({
            'success': True,
            'preview': preview
        })

    except Exception as e:
        logger.exception(f"Error getting schedule preview: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def training_schedule_from_run(request):
    """
    Create a new training schedule from an existing training run's configuration.

    POST /api/training/schedules/from-run/
    {
        "source_training_run_id": 123,
        "name": "Weekly Retraining",
        "description": "Optional description",
        "schedule_type": "weekly",  // 'once', 'daily', 'weekly'
        "schedule_time": "09:00",   // For daily/weekly
        "schedule_day_of_week": 0,  // For weekly (0=Monday, 6=Sunday)
        "schedule_timezone": "UTC",
        "scheduled_datetime": "2024-01-15T10:30:00Z"  // For one-time only
    }

    Returns:
    {
        "success": true,
        "schedule": {...}
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        data = json.loads(request.body)

        # Required fields
        required_fields = ['source_training_run_id', 'name', 'schedule_type']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return JsonResponse({
                'success': False,
                'error': f"Missing required fields: {', '.join(missing)}"
            }, status=400)

        # Get source training run
        source_run_id = data['source_training_run_id']
        try:
            source_run = TrainingRun.objects.select_related(
                'dataset', 'feature_config', 'model_config', 'base_experiment'
            ).get(
                id=source_run_id,
                ml_model=model_endpoint
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'TrainingRun {source_run_id} not found'
            }, status=404)

        schedule_type = data['schedule_type']

        # Validate schedule type
        valid_types = [
            TrainingSchedule.SCHEDULE_TYPE_ONCE,
            TrainingSchedule.SCHEDULE_TYPE_HOURLY,
            TrainingSchedule.SCHEDULE_TYPE_DAILY,
            TrainingSchedule.SCHEDULE_TYPE_WEEKLY,
            TrainingSchedule.SCHEDULE_TYPE_MONTHLY
        ]
        if schedule_type not in valid_types:
            return JsonResponse({
                'success': False,
                'error': f"Invalid schedule_type. Must be one of: {', '.join(valid_types)}"
            }, status=400)

        # Parse schedule-specific fields
        from datetime import datetime, time as dt_time

        scheduled_datetime = None
        schedule_time = None
        schedule_day_of_week = None
        schedule_day_of_month = None

        if schedule_type == TrainingSchedule.SCHEDULE_TYPE_ONCE:
            if not data.get('scheduled_datetime'):
                return JsonResponse({
                    'success': False,
                    'error': 'scheduled_datetime is required for one-time schedules'
                }, status=400)
            try:
                scheduled_datetime = datetime.fromisoformat(data['scheduled_datetime'].replace('Z', '+00:00'))
            except ValueError as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid scheduled_datetime format: {e}'
                }, status=400)

        elif schedule_type == TrainingSchedule.SCHEDULE_TYPE_HOURLY:
            # Hourly: uses schedule_time for the minute (e.g., "00:15" means run at :15 each hour)
            if data.get('schedule_time'):
                try:
                    hour, minute = map(int, data['schedule_time'].split(':'))
                    schedule_time = dt_time(0, minute)  # Only minute matters for hourly
                except (ValueError, AttributeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid schedule_time format. Use HH:MM'
                    }, status=400)
            else:
                schedule_time = dt_time(0, 0)  # Default to :00

        elif schedule_type in (TrainingSchedule.SCHEDULE_TYPE_DAILY, TrainingSchedule.SCHEDULE_TYPE_WEEKLY):
            if data.get('schedule_time'):
                try:
                    hour, minute = map(int, data['schedule_time'].split(':'))
                    schedule_time = dt_time(hour, minute)
                except (ValueError, AttributeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid schedule_time format. Use HH:MM'
                    }, status=400)
            else:
                schedule_time = dt_time(9, 0)  # Default to 9 AM

            if schedule_type == TrainingSchedule.SCHEDULE_TYPE_WEEKLY:
                schedule_day_of_week = data.get('schedule_day_of_week', 0)
                if not isinstance(schedule_day_of_week, int) or schedule_day_of_week < 0 or schedule_day_of_week > 6:
                    return JsonResponse({
                        'success': False,
                        'error': 'schedule_day_of_week must be 0-6 (Monday-Sunday)'
                    }, status=400)

        elif schedule_type == TrainingSchedule.SCHEDULE_TYPE_MONTHLY:
            # Monthly: day of month (1-28) and time of day
            schedule_day_of_month = data.get('schedule_day_of_month', 1)
            if not isinstance(schedule_day_of_month, int) or schedule_day_of_month < 1 or schedule_day_of_month > 31:
                return JsonResponse({
                    'success': False,
                    'error': 'schedule_day_of_month must be 1-31'
                }, status=400)

            if data.get('schedule_time'):
                try:
                    hour, minute = map(int, data['schedule_time'].split(':'))
                    schedule_time = dt_time(hour, minute)
                except (ValueError, AttributeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid schedule_time format. Use HH:MM'
                    }, status=400)
            else:
                schedule_time = dt_time(9, 0)  # Default to 9 AM

        # Get or create RegisteredModel for the source run's model name
        reg_model_service = RegisteredModelService(model_endpoint)

        # Use source run's name (or vertex_model_name if registered)
        model_name = source_run.vertex_model_name or source_run.name

        # Check if model already has a schedule
        name_check = reg_model_service.check_name_available(model_name)
        if name_check['has_schedule']:
            return JsonResponse({
                'success': False,
                'error': f"Model '{model_name}' already has a schedule (ID: {name_check['schedule_id']}). "
                         "Each model can only have one schedule."
            }, status=400)

        # Get or create the RegisteredModel
        registered_model = reg_model_service.get_or_create_for_training(
            model_name=model_name,
            model_type=source_run.model_type,
            description=source_run.description or '',
            created_by=request.user if request.user.is_authenticated else None,
        )

        # Link source run to RegisteredModel if not already linked
        if not source_run.registered_model:
            source_run.registered_model = registered_model
            source_run.save(update_fields=['registered_model'])

        # Create the schedule, inheriting config from source training run
        schedule = TrainingSchedule.objects.create(
            ml_model=model_endpoint,
            name=data['name'],
            description=data.get('description', ''),
            schedule_type=schedule_type,
            scheduled_datetime=scheduled_datetime,
            schedule_time=schedule_time,
            schedule_day_of_week=schedule_day_of_week,
            schedule_day_of_month=schedule_day_of_month,
            schedule_timezone=data.get('schedule_timezone', 'UTC'),
            # Inherit from source training run
            dataset=source_run.dataset,
            feature_config=source_run.feature_config,
            model_config=source_run.model_config,
            base_experiment=source_run.base_experiment,
            training_params=source_run.training_params or {},
            gpu_config=source_run.gpu_config or {},
            evaluator_config=source_run.evaluator_config or {},
            deployment_config=source_run.deployment_config or {},
            created_by=request.user if request.user.is_authenticated else None,
            status=TrainingSchedule.STATUS_ACTIVE,
            # Link to RegisteredModel
            registered_model=registered_model,
        )

        # Create Cloud Scheduler job
        service = TrainingScheduleService(model_endpoint)
        webhook_base_url = request.build_absolute_uri('/').rstrip('/')
        result = service.create_schedule(schedule, webhook_base_url)

        if not result['success']:
            # Rollback schedule creation if scheduler job fails
            schedule.delete()
            return JsonResponse({
                'success': False,
                'error': f"Failed to create Cloud Scheduler job: {result['message']}"
            }, status=500)

        logger.info(f"Created training schedule {schedule.id} from training run {source_run_id}: {schedule.name}")

        return JsonResponse({
            'success': True,
            'schedule': _serialize_training_schedule(schedule),
            'message': f"Schedule '{schedule.name}' created successfully"
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        logger.exception(f"Error creating training schedule from run: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# Models Registry API Endpoints
# =============================================================================

def _serialize_registered_model(training_run, include_details=False, deployed_model_names=None, deployed_training_run_ids=None):
    """
    Serialize a TrainingRun that has a registered model to dict.

    Args:
        training_run: TrainingRun model instance with vertex_model_resource_name
        include_details: If True, include full configuration and artifacts
        deployed_model_names: Set of vertex_model_name strings that have active Cloud Run endpoints
        deployed_training_run_ids: Set of TrainingRun IDs that have active Cloud Run endpoints

    Returns:
        Dict representation of the registered model
    """
    # Determine deployment status from Cloud Run endpoints
    # Three states: 'deployed' (this version on endpoint), 'outdated' (other version deployed), 'idle' (none)
    # Check via DeployedEndpoint.deployed_training_run (the reverse FK that IS set correctly)
    if deployed_training_run_ids and training_run.id in deployed_training_run_ids:
        model_status = 'deployed'
    elif deployed_model_names and training_run.vertex_model_name in deployed_model_names:
        # Another version of this model has an active endpoint
        model_status = 'outdated'
    else:
        model_status = 'idle'

    # Get primary metrics based on model type
    metrics = {}
    if training_run.model_type == TrainingRun.MODEL_TYPE_MULTITASK:
        metrics = {
            'recall_at_100': training_run.recall_at_100,
            'recall_at_50': training_run.recall_at_50,
            'rmse': training_run.rmse,
            'mae': training_run.mae,
            'test_rmse': training_run.test_rmse,
            'test_mae': training_run.test_mae,
        }
    elif training_run.model_type == TrainingRun.MODEL_TYPE_RANKING:
        metrics = {
            'rmse': training_run.rmse,
            'mae': training_run.mae,
            'test_rmse': training_run.test_rmse,
            'test_mae': training_run.test_mae,
        }
    else:  # Retrieval
        metrics = {
            'recall_at_100': training_run.recall_at_100,
            'recall_at_50': training_run.recall_at_50,
            'recall_at_10': training_run.recall_at_10,
            'recall_at_5': training_run.recall_at_5,
        }

    # Derive is_deployed from model_status (dynamic from Vertex AI)
    is_deployed = model_status == 'deployed'

    data = {
        'id': training_run.id,
        'training_run_id': training_run.id,
        'run_number': training_run.run_number,

        # Model Registry info
        'vertex_model_name': training_run.vertex_model_name,
        'vertex_model_version': training_run.vertex_model_version,
        'vertex_model_resource_name': training_run.vertex_model_resource_name,
        'registered_at': training_run.registered_at.isoformat() if training_run.registered_at else None,

        # Type and status
        'model_type': training_run.model_type,
        'model_status': model_status,
        'is_blessed': training_run.is_blessed,
        'is_deployed': is_deployed,

        # Metrics
        'metrics': metrics,

        # Configuration names and IDs
        'dataset_id': training_run.dataset_id,
        'dataset_name': training_run.dataset.name if training_run.dataset else None,
        'feature_config_id': training_run.feature_config_id,
        'feature_config_name': training_run.feature_config.name if training_run.feature_config else None,
        'model_config_id': training_run.model_config_id,
        'model_config_name': training_run.model_config.name if training_run.model_config else None,
        'retrieval_algorithm': training_run.model_config.retrieval_algorithm if training_run.model_config else None,

        # Versioning info
        'vertex_parent_model_resource_name': training_run.vertex_parent_model_resource_name,
        'is_version': bool(training_run.vertex_parent_model_resource_name),

        # Training info
        'base_experiment_number': training_run.base_experiment.experiment_number if training_run.base_experiment else None,
        'created_by': training_run.created_by.username if training_run.created_by else None,

        # RegisteredModel and Schedule info
        'registered_model_id': training_run.registered_model_id,
        'has_schedule': training_run.registered_model.has_schedule if training_run.registered_model else False,
        'schedule_id': training_run.registered_model.schedule.id if (training_run.registered_model and training_run.registered_model.has_schedule) else None,
        'schedule_status': training_run.registered_model.schedule.status if (training_run.registered_model and training_run.registered_model.has_schedule) else None,
    }

    if include_details:
        data['training_params'] = training_run.training_params
        data['gpu_config'] = training_run.gpu_config
        data['evaluator_config'] = training_run.evaluator_config
        data['deployment_config'] = training_run.deployment_config
        data['evaluation_results'] = training_run.evaluation_results
        data['artifacts'] = training_run.artifacts
        data['gcs_artifacts_path'] = training_run.gcs_artifacts_path

    return data


# =============================================================================
# RegisteredModel API Endpoints
# =============================================================================

def _serialize_registered_model_entity(registered_model, include_details=False):
    """
    Serialize a RegisteredModel entity to dict.

    Args:
        registered_model: RegisteredModel model instance
        include_details: If True, include schedule info and version list

    Returns:
        Dict representation of the registered model entity
    """
    # Determine model status from Cloud Run endpoints
    is_deployed = registered_model.deployed_endpoints.filter(is_active=True).exists()
    if is_deployed:
        model_status = 'deployed'
    elif registered_model.is_registered:
        model_status = 'registered'
    else:
        model_status = 'pending'

    data = {
        'id': registered_model.id,
        'model_name': registered_model.model_name,
        'model_type': registered_model.model_type,
        'description': registered_model.description,
        'status': model_status,

        # Vertex AI state
        'vertex_model_resource_name': registered_model.vertex_model_resource_name,
        'is_registered': registered_model.is_registered,
        'first_registered_at': registered_model.first_registered_at.isoformat() if registered_model.first_registered_at else None,

        # Version info
        'latest_version_id': registered_model.latest_version_id,
        'latest_version_number': registered_model.latest_version_number,
        'total_versions': registered_model.total_versions,

        # Deployment (dynamic from Vertex AI)
        'is_deployed': is_deployed,

        # Schedule info
        'has_schedule': registered_model.has_schedule,
        'schedule_id': registered_model.schedule.id if registered_model.has_schedule else None,
        'schedule_status': registered_model.schedule.status if registered_model.has_schedule else None,

        # Metadata
        'is_active': registered_model.is_active,
        'created_by': registered_model.created_by.username if registered_model.created_by else None,
        'created_at': registered_model.created_at.isoformat() if registered_model.created_at else None,
        'updated_at': registered_model.updated_at.isoformat() if registered_model.updated_at else None,
    }

    if include_details and registered_model.has_schedule:
        schedule = registered_model.schedule
        data['schedule'] = {
            'id': schedule.id,
            'name': schedule.name,
            'schedule_type': schedule.schedule_type,
            'status': schedule.status,
            'next_run_at': schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            'last_run_at': schedule.last_run_at.isoformat() if schedule.last_run_at else None,
            'total_runs': schedule.total_runs,
            'successful_runs': schedule.successful_runs,
        }

    return data


@csrf_exempt
@require_http_methods(["GET"])
def registered_models_list(request):
    """
    List RegisteredModel entities.

    GET /api/registered-models/
    GET /api/registered-models/?model_type=retrieval
    GET /api/registered-models/?has_schedule=true
    GET /api/registered-models/?search=product

    Returns RegisteredModel entities with schedule info.
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        from django.db.models import Q

        queryset = RegisteredModel.objects.filter(
            ml_model=model_endpoint,
            is_active=True
        ).select_related('created_by', 'schedule')

        # Apply filters
        model_type = request.GET.get('model_type')
        if model_type and model_type != 'all':
            queryset = queryset.filter(model_type=model_type)

        has_schedule = request.GET.get('has_schedule')
        if has_schedule == 'true':
            queryset = queryset.filter(schedule__isnull=False)
        elif has_schedule == 'false':
            queryset = queryset.filter(schedule__isnull=True)

        is_registered = request.GET.get('is_registered')
        if is_registered == 'true':
            queryset = queryset.exclude(vertex_model_resource_name='')
        elif is_registered == 'false':
            queryset = queryset.filter(vertex_model_resource_name='')

        # Search filter
        search = request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(model_name__icontains=search) |
                Q(description__icontains=search)
            )

        # Sorting
        sort = request.GET.get('sort', 'latest')
        if sort == 'oldest':
            queryset = queryset.order_by('created_at')
        elif sort == 'name':
            queryset = queryset.order_by('model_name')
        elif sort == 'versions':
            queryset = queryset.order_by('-total_versions', '-created_at')
        else:  # Default: latest
            queryset = queryset.order_by('-created_at')

        # Pagination
        try:
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 20))
        except ValueError:
            page = 1
            page_size = 20

        page = max(1, page)
        page_size = max(1, min(50, page_size))

        total_count = queryset.count()
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        page = min(page, total_pages)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        registered_models = list(queryset.prefetch_related('deployed_endpoints')[start_idx:end_idx])

        # Calculate KPIs with Cloud Run deployment status
        from .models import DeployedEndpoint
        all_models = list(RegisteredModel.objects.filter(ml_model=model_endpoint, is_active=True).prefetch_related('deployed_endpoints'))
        deployed_count = sum(
            1 for rm in all_models
            if rm.deployed_endpoints.filter(is_active=True).exists()
        )
        kpi = {
            'total': len(all_models),
            'registered': sum(1 for rm in all_models if rm.vertex_model_resource_name),
            'with_schedule': sum(1 for rm in all_models if rm.has_schedule),
            'deployed': deployed_count,
        }

        return JsonResponse({
            'success': True,
            'registered_models': [
                _serialize_registered_model_entity(rm)
                for rm in registered_models
            ],
            'kpi': kpi,
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
        logger.exception(f"Error listing registered models: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def registered_model_detail(request, registered_model_id):
    """
    Get RegisteredModel details.

    GET /api/registered-models/<id>/
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            registered_model = RegisteredModel.objects.select_related(
                'created_by', 'schedule'
            ).prefetch_related('deployed_endpoints').get(
                id=registered_model_id,
                ml_model=model_endpoint
            )
        except RegisteredModel.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'RegisteredModel {registered_model_id} not found'
            }, status=404)

        return JsonResponse({
            'success': True,
            'registered_model': _serialize_registered_model_entity(
                registered_model,
                include_details=True
            )
        })

    except Exception as e:
        logger.exception(f"Error getting registered model detail: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def registered_model_versions(request, registered_model_id):
    """
    List all versions (TrainingRuns) for a RegisteredModel.

    GET /api/registered-models/<id>/versions/
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            registered_model = RegisteredModel.objects.prefetch_related(
                'deployed_endpoints'
            ).get(
                id=registered_model_id,
                ml_model=model_endpoint
            )
        except RegisteredModel.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'RegisteredModel {registered_model_id} not found'
            }, status=404)

        # Get all versions (TrainingRuns linked to this RegisteredModel)
        versions = TrainingRun.objects.filter(
            registered_model=registered_model
        ).select_related(
            'dataset', 'feature_config', 'model_config', 'created_by'
        ).order_by('-registered_at', '-created_at')

        return JsonResponse({
            'success': True,
            'registered_model': _serialize_registered_model_entity(registered_model),
            'versions': [_serialize_training_run(v) for v in versions]
        })

    except Exception as e:
        logger.exception(f"Error getting registered model versions: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def registered_model_endpoints(request, registered_model_id):
    """
    GET /api/registered-models/<id>/endpoints/

    List Cloud Run endpoints associated with a registered model.
    """
    from .models import RegisteredModel, DeployedEndpoint

    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            registered_model = RegisteredModel.objects.get(
                id=registered_model_id,
                ml_model=model_endpoint
            )
        except RegisteredModel.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Model not found'
            }, status=404)

        endpoints = DeployedEndpoint.objects.filter(
            registered_model=registered_model,
            is_active=True
        ).order_by('-updated_at')

        return JsonResponse({
            'success': True,
            'endpoints': [
                {
                    'id': ep.id,
                    'service_name': ep.service_name,
                    'service_url': ep.service_url,
                    'deployed_version': ep.deployed_version,
                    'deployed_training_run_id': ep.deployed_training_run_id,
                    'updated_at': ep.updated_at.isoformat(),
                }
                for ep in endpoints
            ]
        })

    except Exception as e:
        logger.exception(f"Error getting registered model endpoints: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def registered_model_check_name(request):
    """
    Check if a model name is available or already exists.

    GET /api/registered-models/check-name/?name=my-model

    Returns:
    {
        "success": true,
        "exists": true/false,
        "registered_model_id": 123 or null,
        "has_schedule": true/false,
        "schedule_id": 456 or null
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        name = request.GET.get('name', '').strip()
        if not name:
            return JsonResponse({
                'success': False,
                'error': 'name parameter is required'
            }, status=400)

        service = RegisteredModelService(model_endpoint)
        result = service.check_name_available(name)

        return JsonResponse({
            'success': True,
            **result
        })

    except Exception as e:
        logger.exception(f"Error checking registered model name: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def models_list(request):
    """
    List registered models in Vertex AI Model Registry.

    GET /api/models/
    GET /api/models/?model_type=retrieval
    GET /api/models/?status=deployed
    GET /api/models/?sort=latest
    GET /api/models/?search=product

    Returns registered models with KPI summary.
    Shows only the latest version of each unique model name.
    Deployment status is dynamically queried from Vertex AI endpoint.
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        from django.db.models import Q
        from .models import DeployedEndpoint

        # Query Cloud Run endpoints to get deployed training run IDs and model names
        # NOTE: Do NOT filter through registered_model - that FK may be NULL
        # Use DeployedEndpoint.deployed_training_run which is the correctly maintained FK
        active_endpoints = DeployedEndpoint.objects.filter(
            is_active=True,
            deployed_training_run__isnull=False
        ).values_list('deployed_training_run_id', 'deployed_training_run__vertex_model_name')

        deployed_training_run_ids = set()
        deployed_model_names = set()
        for tr_id, model_name in active_endpoints:
            deployed_training_run_ids.add(tr_id)
            deployed_model_names.add(model_name)

        # Base filter for all registered models
        base_filter = {
            'ml_model': model_endpoint,
            'vertex_model_resource_name__isnull': False,
        }

        # Build filter queryset (applied before deduplication)
        filter_queryset = TrainingRun.objects.filter(**base_filter).exclude(
            vertex_model_resource_name=''
        )

        # Apply filters that can be done at database level
        model_type = request.GET.get('model_type')
        if model_type and model_type != 'all':
            filter_queryset = filter_queryset.filter(model_type=model_type)

        status_filter = request.GET.get('status')
        # blessed and not_blessed can be filtered at database level
        if status_filter and status_filter != 'all':
            if status_filter == 'blessed':
                filter_queryset = filter_queryset.filter(is_blessed=True)
            elif status_filter == 'not_blessed':
                filter_queryset = filter_queryset.filter(is_blessed=False)
            # deployed and idle filters are handled in memory after fetching

        # Search filter
        search = request.GET.get('search', '').strip()
        if search:
            filter_queryset = filter_queryset.filter(
                Q(name__icontains=search) |
                Q(vertex_model_name__icontains=search) |
                Q(description__icontains=search)
            )

        # Step 1: Get IDs of the latest version per unique model name
        # Using PostgreSQL's DISTINCT ON via Django's distinct() with order_by
        # The order_by must have the distinct field first, then the tiebreaker
        latest_ids = filter_queryset.order_by(
            'vertex_model_name', '-registered_at'
        ).distinct('vertex_model_name').values_list('id', flat=True)

        # Step 2: Query those IDs with user's desired sort order
        queryset = TrainingRun.objects.filter(
            id__in=list(latest_ids)
        ).select_related('dataset', 'feature_config', 'model_config', 'created_by', 'base_experiment', 'registered_model', 'registered_model__schedule', 'deployed_endpoint')

        # Apply user sorting
        sort = request.GET.get('sort', 'latest')
        if sort == 'oldest':
            queryset = queryset.order_by('registered_at')
        elif sort == 'name':
            queryset = queryset.order_by('vertex_model_name')
        elif sort == 'best_metrics':
            # Sort by recall_at_100 descending for retrieval models
            queryset = queryset.order_by('-recall_at_100', '-registered_at')
        else:  # Default: latest
            queryset = queryset.order_by('-registered_at')

        # Fetch all models for filtering and pagination
        all_filtered_models = list(queryset)

        def get_model_status(m):
            """
            Determine deployment status based on Cloud Run endpoints:
            - 'deployed': This training run has an active Cloud Run endpoint
            - 'outdated': Another version of the same model has an active endpoint
            - 'idle': No version of this model has an active endpoint
            """
            # Check via DeployedEndpoint.deployed_training_run (the reverse FK that IS set correctly)
            if m.id in deployed_training_run_ids:
                return 'deployed'
            # Check if another version of this model has an active endpoint
            if m.vertex_model_name in deployed_model_names:
                return 'outdated'
            return 'idle'

        # Apply deployed/outdated/idle filters in memory using dynamic deployment status
        if status_filter == 'deployed':
            all_filtered_models = [m for m in all_filtered_models if get_model_status(m) == 'deployed']
        elif status_filter == 'outdated':
            all_filtered_models = [m for m in all_filtered_models if get_model_status(m) == 'outdated']
        elif status_filter == 'idle':
            all_filtered_models = [m for m in all_filtered_models if get_model_status(m) == 'idle']

        # Calculate KPIs - count unique models, not all versions
        # For each KPI, we get the latest version per model name, then count
        all_models = TrainingRun.objects.filter(**base_filter).exclude(vertex_model_resource_name='')

        # Get unique model count (total unique model names)
        total_unique = all_models.values('vertex_model_name').distinct().count()

        # For deployed/outdated/idle, we need to check the LATEST version of each model
        # Get latest IDs for all models (unfiltered)
        all_latest_ids = all_models.order_by(
            'vertex_model_name', '-registered_at'
        ).distinct('vertex_model_name').values_list('id', flat=True)

        latest_models = list(
            TrainingRun.objects.filter(id__in=list(all_latest_ids))
            .select_related('deployed_endpoint')
        )

        # Calculate KPIs using Cloud Run deployment status
        deployed_count = sum(1 for m in latest_models if get_model_status(m) == 'deployed')
        outdated_count = sum(1 for m in latest_models if get_model_status(m) == 'outdated')
        idle_count = sum(1 for m in latest_models if get_model_status(m) == 'idle')

        kpi = {
            'total': total_unique,
            'deployed': deployed_count,
            'outdated': outdated_count,
            'idle': idle_count,
            'scheduled': TrainingSchedule.objects.filter(
                ml_model=model_endpoint,
                status='active'
            ).count(),
        }

        # Pagination
        try:
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 10))
        except ValueError:
            page = 1
            page_size = 10

        page = max(1, page)
        page_size = max(1, min(50, page_size))

        total_count = len(all_filtered_models)
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        page = min(page, total_pages)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        models = all_filtered_models[start_idx:end_idx]

        # Build version count mapping for all models
        version_counts = {}
        for m in models:
            if m.vertex_model_name not in version_counts:
                version_counts[m.vertex_model_name] = TrainingRun.objects.filter(
                    ml_model=model_endpoint,
                    vertex_model_name=m.vertex_model_name,
                    vertex_model_resource_name__isnull=False
                ).exclude(vertex_model_resource_name='').count()

        return JsonResponse({
            'success': True,
            'models': [
                {
                    **_serialize_registered_model(
                        m,
                        deployed_model_names=deployed_model_names,
                        deployed_training_run_ids=deployed_training_run_ids
                    ),
                    'version_count': version_counts.get(m.vertex_model_name, 1)
                }
                for m in models
            ],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'kpi': kpi
        })

    except Exception as e:
        logger.exception(f"Error listing registered models: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def registered_model_names(request):
    """
    GET /api/models/names/
    Returns list of unique registered model names for filter dropdown.
    """
    model_endpoint = _get_model_endpoint(request)
    if not model_endpoint:
        return JsonResponse({'success': False, 'error': 'No model endpoint selected'}, status=400)

    names = TrainingRun.objects.filter(
        ml_model=model_endpoint,
        vertex_model_resource_name__isnull=False
    ).exclude(
        vertex_model_resource_name=''
    ).values_list('vertex_model_name', flat=True).distinct().order_by('vertex_model_name')

    return JsonResponse({'success': True, 'model_names': list(names)})


@csrf_exempt
@require_http_methods(["GET"])
def model_detail(request, model_id):
    """
    Get detailed information about a registered model.

    GET /api/models/<id>/

    Returns full model details including artifacts and configuration.
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
                'dataset', 'feature_config', 'model_config', 'created_by', 'base_experiment', 'deployed_endpoint'
            ).get(
                id=model_id,
                ml_model=model_endpoint,
                vertex_model_resource_name__isnull=False
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Registered model {model_id} not found'
            }, status=404)

        # Query Cloud Run endpoints to get deployed training run IDs and model names
        # NOTE: Do NOT filter through registered_model - that FK may be NULL
        from .models import DeployedEndpoint
        active_endpoints = DeployedEndpoint.objects.filter(
            is_active=True,
            deployed_training_run__isnull=False
        ).values_list('deployed_training_run_id', 'deployed_training_run__vertex_model_name')

        deployed_training_run_ids = set()
        deployed_model_names = set()
        for tr_id, model_name in active_endpoints:
            deployed_training_run_ids.add(tr_id)
            deployed_model_names.add(model_name)

        return JsonResponse({
            'success': True,
            'model': _serialize_registered_model(
                training_run,
                include_details=True,
                deployed_model_names=deployed_model_names,
                deployed_training_run_ids=deployed_training_run_ids
            )
        })

    except Exception as e:
        logger.exception(f"Error getting model detail: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def model_versions(request, model_id):
    """
    Get version history for a model (all versions with same vertex_model_name).

    GET /api/models/<id>/versions/

    Returns all versions of the same model name, sorted by version.
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        # Get the source model to find its name
        try:
            source_model = TrainingRun.objects.get(
                id=model_id,
                ml_model=model_endpoint,
                vertex_model_resource_name__isnull=False
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Registered model {model_id} not found'
            }, status=404)

        # Get all versions with the same model name
        versions = TrainingRun.objects.filter(
            ml_model=model_endpoint,
            vertex_model_name=source_model.vertex_model_name,
            vertex_model_resource_name__isnull=False
        ).exclude(
            vertex_model_resource_name=''
        ).select_related(
            'dataset', 'feature_config', 'model_config', 'created_by', 'deployed_endpoint'
        ).order_by('-registered_at')

        # Query Cloud Run endpoints to get deployed training run IDs and model names
        # NOTE: Do NOT filter through registered_model - that FK may be NULL
        from .models import DeployedEndpoint
        active_endpoints = DeployedEndpoint.objects.filter(
            is_active=True,
            deployed_training_run__isnull=False
        ).values_list('deployed_training_run_id', 'deployed_training_run__vertex_model_name')

        deployed_training_run_ids = set()
        deployed_model_names = set()
        for tr_id, model_name in active_endpoints:
            deployed_training_run_ids.add(tr_id)
            deployed_model_names.add(model_name)

        return JsonResponse({
            'success': True,
            'model_name': source_model.vertex_model_name,
            'versions': [
                _serialize_registered_model(
                    v,
                    deployed_model_names=deployed_model_names,
                    deployed_training_run_ids=deployed_training_run_ids
                )
                for v in versions
            ]
        })

    except Exception as e:
        logger.exception(f"Error getting model versions: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def model_deploy(request, model_id):
    """
    Deploy a registered model to a Vertex AI Endpoint.

    POST /api/models/<id>/deploy/

    Uses TrainingService.deploy_model() for actual Vertex AI API integration.
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            training_run = TrainingRun.objects.select_related('deployed_endpoint').get(
                id=model_id,
                ml_model=model_endpoint,
                vertex_model_resource_name__isnull=False
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Registered model {model_id} not found'
            }, status=404)

        # Validate model can be deployed
        if not training_run.is_blessed:
            return JsonResponse({
                'success': False,
                'error': 'Cannot deploy unblessed model. Model must pass evaluation first.'
            }, status=400)

        # Check if already deployed to Cloud Run (using reverse FK)
        from .models import DeployedEndpoint
        if DeployedEndpoint.objects.filter(deployed_training_run=training_run, is_active=True).exists():
            return JsonResponse({
                'success': False,
                'error': 'Model is already deployed to endpoint'
            }, status=400)

        # Deploy using TrainingService
        service = TrainingService(model_endpoint)
        try:
            training_run = service.deploy_model(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        # Re-fetch training run to get updated deployment info
        training_run.refresh_from_db()

        # Query Cloud Run endpoints to get deployed training run IDs and model names
        # NOTE: Do NOT filter through registered_model - that FK may be NULL
        from .models import DeployedEndpoint
        active_endpoints = DeployedEndpoint.objects.filter(
            is_active=True,
            deployed_training_run__isnull=False
        ).values_list('deployed_training_run_id', 'deployed_training_run__vertex_model_name')

        deployed_training_run_ids = set()
        deployed_model_names = set()
        for tr_id, model_name in active_endpoints:
            deployed_training_run_ids.add(tr_id)
            deployed_model_names.add(model_name)

        return JsonResponse({
            'success': True,
            'model': _serialize_registered_model(
                training_run,
                include_details=True,
                deployed_model_names=deployed_model_names,
                deployed_training_run_ids=deployed_training_run_ids
            ),
            'message': f'Model deployed to endpoint'
        })

    except Exception as e:
        logger.exception(f"Error deploying model: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def model_undeploy(request, model_id):
    """
    Undeploy a model from its Vertex AI Endpoint.

    POST /api/models/<id>/undeploy/

    Removes the model from the endpoint but keeps it in the Model Registry.
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            training_run = TrainingRun.objects.select_related('deployed_endpoint').get(
                id=model_id,
                ml_model=model_endpoint,
                vertex_model_resource_name__isnull=False
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Registered model {model_id} not found'
            }, status=404)

        # Check if actually deployed to Cloud Run (using reverse FK)
        from .models import DeployedEndpoint
        if not DeployedEndpoint.objects.filter(deployed_training_run=training_run, is_active=True).exists():
            return JsonResponse({
                'success': False,
                'error': 'Model is not currently deployed'
            }, status=400)

        # Undeploy using TrainingService
        service = TrainingService(model_endpoint)
        try:
            training_run = service.undeploy_model(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        # Re-fetch training run to get updated deployment info
        training_run.refresh_from_db()

        # Query Cloud Run endpoints to get deployed training run IDs and model names
        # NOTE: Do NOT filter through registered_model - that FK may be NULL
        from .models import DeployedEndpoint
        active_endpoints = DeployedEndpoint.objects.filter(
            is_active=True,
            deployed_training_run__isnull=False
        ).values_list('deployed_training_run_id', 'deployed_training_run__vertex_model_name')

        deployed_training_run_ids = set()
        deployed_model_names = set()
        for tr_id, model_name in active_endpoints:
            deployed_training_run_ids.add(tr_id)
            deployed_model_names.add(model_name)

        return JsonResponse({
            'success': True,
            'model': _serialize_registered_model(
                training_run,
                include_details=True,
                deployed_model_names=deployed_model_names,
                deployed_training_run_ids=deployed_training_run_ids
            ),
            'message': 'Model undeployed successfully'
        })

    except Exception as e:
        logger.exception(f"Error undeploying model: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def model_delete(request, model_id):
    """
    Delete a registered model from Vertex AI Model Registry.

    DELETE /api/models/<id>/delete/

    This removes the model from Vertex AI Model Registry and clears
    the registration data from the TrainingRun.
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
                id=model_id,
                ml_model=model_endpoint,
                vertex_model_resource_name__isnull=False
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Registered model {model_id} not found'
            }, status=404)

        # Check if model is deployed - cannot delete deployed models
        service = TrainingService(model_endpoint)
        endpoint_info = service.get_deployed_model_resource_names()
        deployed_models = endpoint_info['deployed_models']

        if training_run.vertex_model_resource_name in deployed_models:
            return JsonResponse({
                'success': False,
                'error': 'Cannot delete a deployed model. Undeploy it first.'
            }, status=400)

        # Store model name for response
        model_name = training_run.vertex_model_name

        # Delete from Vertex AI Model Registry
        try:
            service.delete_model_from_registry(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        # Clear registration data from training run
        # Note: CharField fields use empty string, not None (they have blank=True but not null=True)
        training_run.vertex_model_resource_name = ''
        training_run.vertex_model_name = ''
        training_run.vertex_model_version = ''
        training_run.registered_at = None
        training_run.save(update_fields=[
            'vertex_model_resource_name',
            'vertex_model_name',
            'vertex_model_version',
            'registered_at'
        ])

        return JsonResponse({
            'success': True,
            'message': f'Model "{model_name}" deleted successfully'
        })

    except Exception as e:
        logger.exception(f"Error deleting model: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def model_lineage(request, model_id):
    """
    Get model lineage DAG data.

    GET /api/models/<id>/lineage/

    Returns lineage showing QuickTest -> TrainingRun -> Model relationships.
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
                'dataset', 'feature_config', 'model_config', 'base_experiment'
            ).get(
                id=model_id,
                ml_model=model_endpoint,
                vertex_model_resource_name__isnull=False
            )
        except TrainingRun.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Registered model {model_id} not found'
            }, status=404)

        # Query Vertex AI endpoint to get deployment status
        service = TrainingService(model_endpoint)
        endpoint_info = service.get_deployed_model_resource_names()
        deployed_models = endpoint_info['deployed_models']
        is_deployed = training_run.vertex_model_resource_name in deployed_models

        # Build lineage DAG
        nodes = []
        edges = []

        # Dataset node
        if training_run.dataset:
            nodes.append({
                'id': f'dataset-{training_run.dataset.id}',
                'type': 'dataset',
                'label': training_run.dataset.name,
                'data': {
                    'id': training_run.dataset.id,
                    'name': training_run.dataset.name
                }
            })

        # Feature Config node
        if training_run.feature_config:
            nodes.append({
                'id': f'feature-config-{training_run.feature_config.id}',
                'type': 'feature_config',
                'label': training_run.feature_config.name,
                'data': {
                    'id': training_run.feature_config.id,
                    'name': training_run.feature_config.name
                }
            })
            if training_run.dataset:
                edges.append({
                    'source': f'dataset-{training_run.dataset.id}',
                    'target': f'feature-config-{training_run.feature_config.id}'
                })

        # Base Experiment node (if exists)
        if training_run.base_experiment:
            exp = training_run.base_experiment
            nodes.append({
                'id': f'experiment-{exp.id}',
                'type': 'experiment',
                'label': f'Exp #{exp.experiment_number}',
                'data': {
                    'id': exp.id,
                    'experiment_number': exp.experiment_number,
                    'status': exp.status
                }
            })
            if training_run.feature_config:
                edges.append({
                    'source': f'feature-config-{training_run.feature_config.id}',
                    'target': f'experiment-{exp.id}'
                })

        # Training Run node
        nodes.append({
            'id': f'training-run-{training_run.id}',
            'type': 'training_run',
            'label': f'Run #{training_run.run_number}',
            'data': {
                'id': training_run.id,
                'run_number': training_run.run_number,
                'status': training_run.status
            }
        })

        # Edge from experiment or feature config to training run
        if training_run.base_experiment:
            edges.append({
                'source': f'experiment-{training_run.base_experiment.id}',
                'target': f'training-run-{training_run.id}'
            })
        elif training_run.feature_config:
            edges.append({
                'source': f'feature-config-{training_run.feature_config.id}',
                'target': f'training-run-{training_run.id}'
            })

        # Registered Model node
        nodes.append({
            'id': f'model-{training_run.id}',
            'type': 'model',
            'label': training_run.vertex_model_name or 'Model',
            'data': {
                'id': training_run.id,
                'vertex_model_name': training_run.vertex_model_name,
                'vertex_model_version': training_run.vertex_model_version,
                'is_blessed': training_run.is_blessed,
                'is_deployed': is_deployed
            }
        })
        edges.append({
            'source': f'training-run-{training_run.id}',
            'target': f'model-{training_run.id}'
        })

        # Endpoint node (if deployed)
        if is_deployed and endpoint_info.get('endpoint_resource_name'):
            nodes.append({
                'id': f'endpoint-{training_run.id}',
                'type': 'endpoint',
                'label': 'Endpoint',
                'data': {
                    'endpoint_resource_name': endpoint_info['endpoint_resource_name']
                }
            })
            edges.append({
                'source': f'model-{training_run.id}',
                'target': f'endpoint-{training_run.id}'
            })

        return JsonResponse({
            'success': True,
            'lineage': {
                'nodes': nodes,
                'edges': edges
            }
        })

    except Exception as e:
        logger.exception(f"Error getting model lineage: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def training_schedules_calendar(request):
    """
    Get calendar grid data for schedule visualization.

    GET /api/training-schedules/calendar/

    Returns 10 weeks of past data (from TrainingRun completions) and
    30 weeks of future projections (from active TrainingSchedule records).
    """
    from datetime import timedelta
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        today = timezone.now().date()

        # Calculate date range: 10 weeks past, 30 weeks future
        start_date = today - timedelta(weeks=10)
        end_date = today + timedelta(weeks=30)

        calendar_data = {}

        # 1. Historical data: Successfully completed TrainingRuns
        historical_runs = TrainingRun.objects.filter(
            ml_model=model_endpoint,
            completed_at__date__gte=start_date,
            completed_at__date__lte=today,
            status='completed'
        ).annotate(
            completion_date=TruncDate('completed_at')
        ).values('completion_date').annotate(
            count=Count('id')
        ).order_by('completion_date')

        for entry in historical_runs:
            date_str = entry['completion_date'].isoformat()
            calendar_data[date_str] = {
                'count': entry['count'],
                'type': 'historical',
                'runs': []
            }

        # Get run details for historical dates (completed runs)
        historical_details = TrainingRun.objects.filter(
            ml_model=model_endpoint,
            completed_at__date__gte=start_date,
            completed_at__date__lte=today,
            status='completed'
        ).values('id', 'run_number', 'name', 'status', 'completed_at')

        for run in historical_details:
            date_str = run['completed_at'].date().isoformat()
            if date_str in calendar_data:
                calendar_data[date_str]['runs'].append({
                    'id': run['id'],
                    'run_number': run['run_number'],
                    'name': run['name'],
                    'status': run['status']
                })

        # 2. Future data: Project from active TrainingSchedules
        active_schedules = TrainingSchedule.objects.filter(
            ml_model=model_endpoint,
            status=TrainingSchedule.STATUS_ACTIVE
        )

        for schedule in active_schedules:
            # Project future run dates based on schedule type
            if schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_ONCE:
                if schedule.scheduled_datetime and schedule.scheduled_datetime.date() > today:
                    date_str = schedule.scheduled_datetime.date().isoformat()
                    if date_str not in calendar_data:
                        calendar_data[date_str] = {'count': 0, 'type': 'scheduled', 'schedules': []}
                    calendar_data[date_str]['count'] += 1
                    calendar_data[date_str]['schedules'] = calendar_data[date_str].get('schedules', [])
                    calendar_data[date_str]['schedules'].append({
                        'id': schedule.id,
                        'name': schedule.name,
                        'schedule_type': schedule.schedule_type
                    })

            elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_DAILY:
                # Project daily runs for next 30 weeks
                current_date = max(today + timedelta(days=1), start_date)
                while current_date <= end_date:
                    date_str = current_date.isoformat()
                    if date_str not in calendar_data:
                        calendar_data[date_str] = {'count': 0, 'type': 'scheduled', 'schedules': []}
                    calendar_data[date_str]['count'] += 1
                    calendar_data[date_str]['schedules'] = calendar_data[date_str].get('schedules', [])
                    calendar_data[date_str]['schedules'].append({
                        'id': schedule.id,
                        'name': schedule.name,
                        'schedule_type': schedule.schedule_type
                    })
                    current_date += timedelta(days=1)

            elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_WEEKLY:
                # Project weekly runs
                day_of_week = schedule.schedule_day_of_week or 0
                current_date = today + timedelta(days=1)
                # Find next occurrence of scheduled day
                while current_date.weekday() != day_of_week:
                    current_date += timedelta(days=1)

                while current_date <= end_date:
                    date_str = current_date.isoformat()
                    if date_str not in calendar_data:
                        calendar_data[date_str] = {'count': 0, 'type': 'scheduled', 'schedules': []}
                    calendar_data[date_str]['count'] += 1
                    calendar_data[date_str]['schedules'] = calendar_data[date_str].get('schedules', [])
                    calendar_data[date_str]['schedules'].append({
                        'id': schedule.id,
                        'name': schedule.name,
                        'schedule_type': schedule.schedule_type
                    })
                    current_date += timedelta(weeks=1)

        return JsonResponse({
            'success': True,
            'calendar': calendar_data,
            'range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'today': today.isoformat()
        })

    except Exception as e:
        logger.exception(f"Error getting training schedules calendar: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# DEPLOYED ENDPOINTS API
# =============================================================================

def _serialize_deployed_endpoint(endpoint, include_details=False):
    """
    Serialize a DeployedEndpoint model to dict.

    Args:
        endpoint: DeployedEndpoint model instance
        include_details: If True, include full deployment config

    Returns:
        Dict representation of the deployed endpoint
    """
    from .models import DeployedEndpoint

    data = {
        'id': endpoint.id,
        'service_name': endpoint.service_name,
        'service_url': endpoint.service_url,
        'deployed_version': endpoint.deployed_version,
        'is_active': endpoint.is_active,

        # Registered model info
        'registered_model_id': endpoint.registered_model_id,
        'model_name': endpoint.registered_model.model_name if endpoint.registered_model else None,
        'model_type': endpoint.registered_model.model_type if endpoint.registered_model else None,

        # Training run info (currently deployed)
        'training_run_id': endpoint.deployed_training_run_id,
        'run_number': endpoint.deployed_training_run.run_number if endpoint.deployed_training_run else None,

        # Timestamps
        'created_at': endpoint.created_at.isoformat() if endpoint.created_at else None,
        'updated_at': endpoint.updated_at.isoformat() if endpoint.updated_at else None,
    }

    if include_details:
        data['deployment_config'] = endpoint.deployment_config or {}

    return data


@csrf_exempt
@require_http_methods(["GET"])
def deployed_endpoints_list(request):
    """
    List all deployed ML serving endpoints with filters, pagination, KPIs.

    GET /api/deployed-endpoints/
    GET /api/deployed-endpoints/?model_type=retrieval
    GET /api/deployed-endpoints/?status=active
    GET /api/deployed-endpoints/?model_name=my-model
    GET /api/deployed-endpoints/?search=product

    Returns deployed endpoints with KPI summary.
    Only shows endpoints with service names ending in '-serving'.
    """
    from .models import DeployedEndpoint
    from django.db.models import Q

    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        # Base queryset: only ML serving endpoints (ending with '-serving')
        queryset = DeployedEndpoint.objects.filter(
            registered_model__ml_model=model_endpoint,
            service_name__endswith='-serving'
        ).select_related('registered_model', 'deployed_training_run')

        # Calculate KPIs before filtering
        all_endpoints = queryset
        total_count = all_endpoints.count()
        active_count = all_endpoints.filter(is_active=True).count()
        inactive_count = all_endpoints.filter(is_active=False).count()
        last_updated = all_endpoints.order_by('-updated_at').values_list('updated_at', flat=True).first()

        kpi = {
            'total': total_count,
            'active': active_count,
            'inactive': inactive_count,
            'last_updated': last_updated.isoformat() if last_updated else None,
        }

        # Get unique model names for filter dropdown
        model_names = list(
            queryset.values_list('registered_model__model_name', flat=True)
            .distinct()
            .order_by('registered_model__model_name')
        )

        # Apply filters
        model_type = request.GET.get('model_type')
        if model_type and model_type != 'all':
            queryset = queryset.filter(registered_model__model_type=model_type)

        status_filter = request.GET.get('status')
        if status_filter and status_filter != 'all':
            if status_filter == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter == 'inactive':
                queryset = queryset.filter(is_active=False)

        model_name_filter = request.GET.get('model_name')
        if model_name_filter and model_name_filter != 'all':
            queryset = queryset.filter(registered_model__model_name=model_name_filter)

        search = request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(service_name__icontains=search) |
                Q(registered_model__model_name__icontains=search) |
                Q(deployed_version__icontains=search)
            )

        # Order by most recently updated
        queryset = queryset.order_by('-updated_at')

        # Pagination
        try:
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 10))
        except ValueError:
            page = 1
            page_size = 10

        page = max(1, page)
        page_size = max(1, min(50, page_size))

        filtered_count = queryset.count()
        total_pages = (filtered_count + page_size - 1) // page_size if filtered_count > 0 else 1
        page = min(page, total_pages)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        endpoints = list(queryset[start_idx:end_idx])

        return JsonResponse({
            'success': True,
            'endpoints': [
                _serialize_deployed_endpoint(ep, include_details=True)
                for ep in endpoints
            ],
            'kpi': kpi,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': filtered_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'model_names': model_names
        })

    except Exception as e:
        logger.exception(f"Error listing deployed endpoints: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def endpoint_detail(request, endpoint_id):
    """
    Get detailed information about a deployed endpoint.

    GET /api/deployed-endpoints/<id>/

    Returns full endpoint details including deployment config.
    """
    from .models import DeployedEndpoint

    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            endpoint = DeployedEndpoint.objects.select_related(
                'registered_model', 'deployed_training_run'
            ).get(
                id=endpoint_id,
                registered_model__ml_model=model_endpoint
            )
        except DeployedEndpoint.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Endpoint {endpoint_id} not found'
            }, status=404)

        return JsonResponse({
            'success': True,
            'endpoint': _serialize_deployed_endpoint(endpoint, include_details=True)
        })

    except Exception as e:
        logger.exception(f"Error getting endpoint detail: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def endpoint_undeploy(request, endpoint_id):
    """
    Undeploy an endpoint by deleting the Cloud Run service.

    POST /api/deployed-endpoints/<id>/undeploy/

    Deletes the Cloud Run service and marks the endpoint as inactive.
    """
    from .models import DeployedEndpoint

    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            endpoint = DeployedEndpoint.objects.select_related(
                'registered_model', 'deployed_training_run'
            ).get(
                id=endpoint_id,
                registered_model__ml_model=model_endpoint
            )
        except DeployedEndpoint.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Endpoint {endpoint_id} not found'
            }, status=404)

        if not endpoint.is_active:
            return JsonResponse({
                'success': False,
                'error': 'Endpoint is already inactive'
            }, status=400)

        # Delete the Cloud Run service
        service = TrainingService(model_endpoint)
        try:
            success = service.delete_cloud_run_service(endpoint.service_name)
            if not success:
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to delete Cloud Run service'
                }, status=500)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        # Mark endpoint as inactive
        endpoint.is_active = False
        endpoint.save(update_fields=['is_active', 'updated_at'])

        # Update training run deployment status if linked
        if endpoint.deployed_training_run:
            training_run = endpoint.deployed_training_run
            training_run.deployment_status = 'pending'  # Reset to pending (ready to deploy again)
            training_run.deployed_endpoint = None

            # Reset status from 'deployed' to allow redeployment
            # Restore to 'completed' or 'not_blessed' based on blessing status
            if training_run.status in [
                TrainingRun.STATUS_DEPLOYED,
                TrainingRun.STATUS_DEPLOYING,
                TrainingRun.STATUS_DEPLOY_FAILED
            ]:
                if training_run.is_blessed:
                    training_run.status = TrainingRun.STATUS_COMPLETED
                else:
                    training_run.status = TrainingRun.STATUS_NOT_BLESSED

            training_run.save(update_fields=['deployment_status', 'deployed_endpoint', 'status'])

        return JsonResponse({
            'success': True,
            'message': f'Endpoint {endpoint.service_name} undeployed successfully',
            'endpoint': _serialize_deployed_endpoint(endpoint, include_details=True)
        })

    except Exception as e:
        logger.exception(f"Error undeploying endpoint: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
