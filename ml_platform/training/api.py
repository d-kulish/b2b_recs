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
from .services import TrainingService, TrainingServiceError

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
def training_run_retry(request, training_run_id):
    """
    Retry a failed Training Run.

    POST /api/training-runs/<id>/retry/

    Creates a new TrainingRun with the same configuration and submits it.

    Returns:
    {
        "success": true,
        "training_run": {
            "id": 789,  // New run ID
            "status": "submitting",
            ...
        },
        "message": "Retry created and submitted"
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

        # Only allow retry for failed runs
        if training_run.status != TrainingRun.STATUS_FAILED:
            return JsonResponse({
                'success': False,
                'error': f"Cannot retry training run in '{training_run.status}' state. "
                         f"Only failed training runs can be retried."
            }, status=400)

        # Retry the training run
        service = TrainingService(model_endpoint)
        try:
            new_run = service.retry_training_run(training_run)
        except TrainingServiceError as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(new_run, include_details=True),
            'message': f"Retry created as {new_run.display_name}"
        })

    except Exception as e:
        logger.exception(f"Error retrying training run: {e}")
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
            training_run = TrainingRun.objects.get(
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

        if training_run.is_deployed:
            return JsonResponse({
                'success': False,
                'error': f"Training run is already deployed to: {training_run.endpoint_resource_name}"
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

        return JsonResponse({
            'success': True,
            'training_run': _serialize_training_run(training_run, include_details=True),
            'message': f"Model deployed to {training_run.endpoint_resource_name}"
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

from .models import TrainingSchedule
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
        valid_types = [TrainingSchedule.SCHEDULE_TYPE_ONCE, TrainingSchedule.SCHEDULE_TYPE_DAILY, TrainingSchedule.SCHEDULE_TYPE_WEEKLY]
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

        # Create the schedule
        schedule = TrainingSchedule.objects.create(
            ml_model=model_endpoint,
            name=data['name'],
            description=data.get('description', ''),
            schedule_type=schedule_type,
            scheduled_datetime=scheduled_datetime,
            schedule_time=schedule_time,
            schedule_day_of_week=schedule_day_of_week,
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
@require_http_methods(["GET", "DELETE"])
def training_schedule_detail(request, schedule_id):
    """
    Get or delete a Training Schedule.

    GET /api/training/schedules/<id>/
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
