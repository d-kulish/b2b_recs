"""
Experiments Domain API

REST API endpoints for managing Quick Tests (ML experiments).
Handles starting, monitoring, and cancelling pipeline runs.
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from ml_platform.models import FeatureConfig, ModelConfig, QuickTest, Dataset
from .services import ExperimentService
from .artifact_service import ArtifactService

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


@csrf_exempt
@require_http_methods(["POST"])
def start_quick_test(request, feature_config_id):
    """
    Start a new Quick Test for a FeatureConfig.

    POST /api/feature-configs/<id>/quick-test/

    Request body:
    {
        "model_config_id": 123,           # Required: ModelConfig to use
        "split_strategy": "random",        # Optional: random|time_holdout|strict_time
        "holdout_days": 1,                # Optional: days to exclude (for time-based)
        "date_column": "trans_date",      # Optional: column for temporal split
        "data_sample_percent": 100,       # Optional: 5, 10, 25, or 100
        "epochs": 10,                     # Optional: override ModelConfig epochs
        "batch_size": 4096,               # Optional: override ModelConfig batch_size
        "learning_rate": 0.001            # Optional: override ModelConfig learning_rate
    }

    Returns:
    {
        "success": true,
        "quick_test": {
            "id": 456,
            "status": "submitting",
            "vertex_pipeline_job_id": "...",
            ...
        }
    }
    """
    try:
        # Get FeatureConfig first (to derive model_endpoint from it)
        try:
            feature_config = FeatureConfig.objects.select_related(
                'dataset__model_endpoint'
            ).get(id=feature_config_id)
        except FeatureConfig.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'FeatureConfig {feature_config_id} not found'
            }, status=404)

        # Get model endpoint from FeatureConfig's dataset
        model_endpoint = feature_config.dataset.model_endpoint

        # Parse request body
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)

        # Get ModelConfig (global, not tied to model_endpoint)
        model_config_id = data.get('model_config_id')
        if not model_config_id:
            return JsonResponse({
                'success': False,
                'error': 'model_config_id is required'
            }, status=400)

        try:
            model_config = ModelConfig.objects.get(id=model_config_id)
        except ModelConfig.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'ModelConfig {model_config_id} not found'
            }, status=404)

        # Validate model type compatibility
        # (Future: check that ModelConfig type matches what FeatureConfig supports)

        # Extract parameters
        params = {
            'split_strategy': data.get('split_strategy', QuickTest.SPLIT_RANDOM),
            'holdout_days': data.get('holdout_days', 1),
            'date_column': data.get('date_column', ''),
            'data_sample_percent': data.get('data_sample_percent', 100),
            'epochs': data.get('epochs', model_config.epochs),
            'batch_size': data.get('batch_size', model_config.batch_size),
            'learning_rate': data.get('learning_rate', model_config.learning_rate),
            # Rolling window parameters for strict_time
            'train_days': data.get('train_days', 60),
            'val_days': data.get('val_days', 7),
            'test_days': data.get('test_days', 7),
            # Hardware configuration
            'machine_type': data.get('machine_type', QuickTest.MACHINE_TYPE_SMALL),
            # Experiment metadata (optional)
            'experiment_name': data.get('experiment_name', ''),
            'experiment_description': data.get('experiment_description', ''),
        }

        # Validate split strategy requires date column
        if params['split_strategy'] in ('time_holdout', 'strict_time'):
            if not params['date_column']:
                return JsonResponse({
                    'success': False,
                    'error': 'date_column is required for time-based split strategies'
                }, status=400)

        # Initialize experiment service
        service = ExperimentService(model_endpoint)

        # Submit quick test
        quick_test = service.submit_quick_test(
            feature_config=feature_config,
            model_config=model_config,
            user=request.user if request.user.is_authenticated else None,
            **params
        )

        return JsonResponse({
            'success': True,
            'quick_test': _serialize_quick_test(quick_test)
        })

    except Exception as e:
        logger.exception(f"Error starting quick test: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def quick_test_list(request):
    """
    List Quick Tests with pagination and filters.

    GET /api/quick-tests/?page=1&page_size=10
    GET /api/quick-tests/?feature_config_id=123
    GET /api/quick-tests/?model_config_id=456
    GET /api/quick-tests/?status=running
    GET /api/quick-tests/?search=exp

    Returns:
    {
        "success": true,
        "quick_tests": [...],
        "pagination": {
            "page": 1,
            "page_size": 10,
            "total_count": 25,
            "total_pages": 3,
            "has_next": true,
            "has_prev": false
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

        # Build queryset with filters
        queryset = QuickTest.objects.filter(
            feature_config__dataset__model_endpoint=model_endpoint
        ).select_related('feature_config', 'model_config', 'created_by')

        # Apply filters
        feature_config_id = request.GET.get('feature_config_id')
        if feature_config_id:
            queryset = queryset.filter(feature_config_id=feature_config_id)

        model_config_id = request.GET.get('model_config_id')
        if model_config_id:
            queryset = queryset.filter(model_config_id=model_config_id)

        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Search filter (searches experiment number, feature config name, model config name)
        search = request.GET.get('search', '').strip()
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(feature_config__name__icontains=search) |
                Q(model_config__name__icontains=search) |
                Q(experiment_number__icontains=search)
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

        quick_tests = list(queryset[start_idx:end_idx])

        # Refresh status for running/submitting experiments from Vertex AI
        # This ensures the UI shows up-to-date status without requiring
        # the user to click on each experiment individually
        running_tests = [qt for qt in quick_tests
                        if qt.status in (QuickTest.STATUS_RUNNING, QuickTest.STATUS_SUBMITTING)]

        if running_tests:
            try:
                service = ExperimentService(model_endpoint)
                for qt in running_tests:
                    # Refresh status for all running/submitting experiments
                    # refresh_status() handles both phases:
                    # - Cloud Build phase (no vertex_pipeline_job_name yet)
                    # - Vertex AI phase (has vertex_pipeline_job_name)
                    try:
                        service.refresh_status(qt)
                    except Exception as refresh_error:
                        logger.warning(f"Failed to refresh status for {qt.display_name} (id={qt.id}): {refresh_error}")
            except Exception as service_error:
                logger.warning(f"Failed to initialize ExperimentService for status refresh: {service_error}")

        return JsonResponse({
            'success': True,
            'quick_tests': [_serialize_quick_test(qt) for qt in quick_tests],
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
        logger.exception(f"Error listing quick tests: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def quick_test_detail(request, quick_test_id):
    """
    Get detailed status and results for a Quick Test.

    GET /api/quick-tests/<id>/

    Returns:
    {
        "success": true,
        "quick_test": {
            "id": 456,
            "status": "completed",
            "results": {...},
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
            quick_test = QuickTest.objects.select_related(
                'feature_config', 'model_config', 'created_by'
            ).get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'QuickTest {quick_test_id} not found'
            }, status=404)

        # If running, check for status update from Vertex AI
        if quick_test.status in (QuickTest.STATUS_SUBMITTING, QuickTest.STATUS_RUNNING):
            service = ExperimentService(model_endpoint)
            quick_test = service.refresh_status(quick_test)

        return JsonResponse({
            'success': True,
            'quick_test': _serialize_quick_test(quick_test, include_details=True)
        })

    except Exception as e:
        logger.exception(f"Error getting quick test detail: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def quick_test_cancel(request, quick_test_id):
    """
    Cancel a running Quick Test.

    POST /api/quick-tests/<id>/cancel/

    Returns:
    {
        "success": true,
        "quick_test": {
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
            quick_test = QuickTest.objects.get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'QuickTest {quick_test_id} not found'
            }, status=404)

        # Check if cancellable
        if quick_test.status not in (QuickTest.STATUS_SUBMITTING, QuickTest.STATUS_RUNNING):
            return JsonResponse({
                'success': False,
                'error': f'QuickTest is not running (status: {quick_test.status})'
            }, status=400)

        # Cancel the pipeline
        service = ExperimentService(model_endpoint)
        quick_test = service.cancel_quick_test(quick_test)

        return JsonResponse({
            'success': True,
            'quick_test': _serialize_quick_test(quick_test)
        })

    except Exception as e:
        logger.exception(f"Error cancelling quick test: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_date_columns(request, dataset_id):
    """
    Get date/timestamp columns available in a dataset for temporal split.

    GET /api/datasets/<id>/date-columns/

    Returns:
    {
        "success": true,
        "date_columns": [
            {"name": "trans_date", "type": "DATE", "primary": true},
            {"name": "event_date", "type": "TIMESTAMP", "primary": false},
            ...
        ]
    }

    The primary date column is determined from the dataset's filter configuration
    (summary_snapshot.filters_applied.dates.column). Additional date columns are
    found from the summary_snapshot.column_stats.
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        try:
            dataset = Dataset.objects.get(
                id=dataset_id,
                model_endpoint=model_endpoint
            )
        except Dataset.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Dataset {dataset_id} not found'
            }, status=404)

        date_columns = []
        date_types = {'TIMESTAMP', 'DATETIME', 'DATE'}
        seen_columns = set()

        # 1. Primary source: dataset.filters['history']['timestamp_column']
        # This is the actual configuration used to generate the dataset query
        filters = dataset.filters or {}
        history_config = filters.get('history', {})
        timestamp_column = history_config.get('timestamp_column', '')

        # Extract just the column name (remove table prefix if present)
        if timestamp_column:
            primary_date_column = timestamp_column.split('.')[-1] if '.' in timestamp_column else timestamp_column

            # Try to get type from column_stats
            col_type = 'DATE'  # default
            column_stats = dataset.column_stats or {}
            for key, stats in column_stats.items():
                col_name = key.split('.')[-1] if '.' in key else key
                if col_name == primary_date_column:
                    col_type = stats.get('type', 'DATE').upper()
                    break

            date_columns.append({
                'name': primary_date_column,
                'type': col_type,
                'primary': True
            })
            seen_columns.add(primary_date_column)

        # 2. Also check column_stats for other date/timestamp columns
        column_stats = dataset.column_stats or {}
        for key, stats in column_stats.items():
            col_type = stats.get('type', '').upper()
            if col_type in date_types:
                col_name = key.split('.')[-1] if '.' in key else key
                if col_name not in seen_columns:
                    date_columns.append({
                        'name': col_name,
                        'type': col_type,
                        'primary': False
                    })
                    seen_columns.add(col_name)

        return JsonResponse({
            'success': True,
            'date_columns': date_columns
        })

    except Exception as e:
        logger.exception(f"Error getting date columns: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _serialize_quick_test(quick_test, include_details=False):
    """Serialize a QuickTest model to dict."""
    # Build stage_details for the response
    # Handle different statuses appropriately
    stage_details = _get_stage_details_for_status(quick_test)

    data = {
        'id': quick_test.id,
        'experiment_number': quick_test.experiment_number,
        'display_name': quick_test.display_name,
        'experiment_name': quick_test.experiment_name,
        'experiment_description': quick_test.experiment_description,
        'feature_config_id': quick_test.feature_config_id,
        'feature_config_name': quick_test.feature_config.name,
        'dataset_name': quick_test.feature_config.dataset.name if quick_test.feature_config.dataset else None,
        'model_config_id': quick_test.model_config_id,
        'model_config_name': quick_test.model_config.name if quick_test.model_config else None,
        'status': quick_test.status,
        'current_stage': quick_test.current_stage,
        'progress_percent': quick_test.progress_percent,
        'elapsed_seconds': quick_test.elapsed_seconds,
        'duration_seconds': quick_test.duration_seconds,

        # Stage details for progress bar (always included)
        'stage_details': stage_details,

        # Configuration
        'split_strategy': quick_test.split_strategy,
        'holdout_days': quick_test.holdout_days,
        'date_column': quick_test.date_column,
        'data_sample_percent': quick_test.data_sample_percent,
        'epochs': quick_test.epochs,
        'batch_size': quick_test.batch_size,
        'learning_rate': quick_test.learning_rate,
        'machine_type': quick_test.machine_type,

        # Key metrics for card display
        'recall_at_100': quick_test.recall_at_100,

        # Vertex AI info
        'vertex_pipeline_job_id': quick_test.vertex_pipeline_job_id,

        # Timestamps
        'created_at': quick_test.created_at.isoformat() if quick_test.created_at else None,
        'started_at': quick_test.started_at.isoformat() if quick_test.started_at else None,
        'completed_at': quick_test.completed_at.isoformat() if quick_test.completed_at else None,

        # User
        'created_by': quick_test.created_by.username if quick_test.created_by else None,
    }

    if include_details:
        # Include full results and metrics
        data['metrics'] = {
            'loss': quick_test.loss,
            'recall_at_10': quick_test.recall_at_10,
            'recall_at_50': quick_test.recall_at_50,
            'recall_at_100': quick_test.recall_at_100,
        }
        data['vocabulary_stats'] = quick_test.vocabulary_stats
        data['error_message'] = quick_test.error_message
        data['vertex_pipeline_job_name'] = quick_test.vertex_pipeline_job_name
        data['gcs_artifacts_path'] = quick_test.gcs_artifacts_path

    return data


def _get_stage_details_for_status(quick_test):
    """
    Build stage_details based on the current status.

    Handles special cases:
    - 'submitting': Show Compile as running, others pending
    - 'running'/'completed'/'failed': Use stored stage_details
    - 'pending': All stages pending
    """
    from ml_platform.models import QuickTest

    # Default stages with short names
    default_stages = [
        {'name': 'Compile', 'status': 'pending', 'duration_seconds': None},
        {'name': 'Examples', 'status': 'pending', 'duration_seconds': None},
        {'name': 'Stats', 'status': 'pending', 'duration_seconds': None},
        {'name': 'Schema', 'status': 'pending', 'duration_seconds': None},
        {'name': 'Transform', 'status': 'pending', 'duration_seconds': None},
        {'name': 'Train', 'status': 'pending', 'duration_seconds': None},
    ]

    if quick_test.status == QuickTest.STATUS_PENDING:
        # Not started yet - all pending
        return default_stages

    elif quick_test.status == QuickTest.STATUS_SUBMITTING:
        # Cloud Build is running - Compile is active
        stages = default_stages.copy()
        stages[0] = {'name': 'Compile', 'status': 'running', 'duration_seconds': None}
        return stages

    elif quick_test.status in (QuickTest.STATUS_RUNNING, QuickTest.STATUS_COMPLETED,
                                QuickTest.STATUS_FAILED, QuickTest.STATUS_CANCELLED):
        # Use stored stage_details if available
        if quick_test.stage_details and len(quick_test.stage_details) > 0:
            return quick_test.stage_details
        else:
            # Fallback: Compile completed, others based on status
            stages = default_stages.copy()
            stages[0] = {'name': 'Compile', 'status': 'completed', 'duration_seconds': None}

            if quick_test.status == QuickTest.STATUS_RUNNING:
                # Mark Examples as running if no details available
                stages[1] = {'name': 'Examples', 'status': 'running', 'duration_seconds': None}
            elif quick_test.status == QuickTest.STATUS_COMPLETED:
                # All completed
                for stage in stages:
                    stage['status'] = 'completed'
            elif quick_test.status == QuickTest.STATUS_FAILED:
                # Compile done, first pipeline stage failed (unknown which)
                stages[1] = {'name': 'Examples', 'status': 'failed', 'duration_seconds': None}

            return stages

    return default_stages


# =============================================================================
# Artifact API Endpoints (Lazy-loaded)
# =============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def quick_test_errors(request, quick_test_id):
    """
    Get detailed error information for a failed Quick Test.

    GET /api/quick-tests/<id>/errors/

    Returns:
    {
        "success": true,
        "error_details": {
            "has_error": true,
            "failed_component": "Transform",
            "error_type": "ResourceExhausted",
            "title": "Memory Limit Exceeded",
            "suggestion": "Try reducing batch_size...",
            "summary": "...",
            "has_stack_trace": true,
            "full_message": "..."
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
            quick_test = QuickTest.objects.get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'QuickTest {quick_test_id} not found'
            }, status=404)

        # Get detailed error information
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        error_details = artifact_service.get_detailed_error(quick_test)

        return JsonResponse({
            'success': True,
            'error_details': error_details
        })

    except Exception as e:
        logger.exception(f"Error getting error details: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def quick_test_statistics(request, quick_test_id):
    """
    Get dataset statistics from TFDV artifacts.

    GET /api/quick-tests/<id>/statistics/

    Returns:
    {
        "success": true,
        "statistics": {
            "available": true,
            "num_examples": 1234567,
            "num_features": 45,
            "avg_missing_ratio": 2.3,
            "features": [
                {
                    "name": "user_id",
                    "type": "CATEGORICAL",
                    "num_unique": 50234,
                    "missing_pct": 0
                },
                ...
            ]
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
            quick_test = QuickTest.objects.get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'QuickTest {quick_test_id} not found'
            }, status=404)

        # Get statistics summary
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        statistics = artifact_service.get_statistics_summary(quick_test)

        return JsonResponse({
            'success': True,
            'statistics': statistics
        })

    except Exception as e:
        logger.exception(f"Error getting statistics: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def quick_test_schema(request, quick_test_id):
    """
    Get schema information from TensorFlow Metadata artifacts.

    GET /api/quick-tests/<id>/schema/

    Returns:
    {
        "success": true,
        "schema": {
            "available": true,
            "num_features": 45,
            "features": [
                {
                    "name": "user_id",
                    "type": "INT64",
                    "required": true
                },
                ...
            ]
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
            quick_test = QuickTest.objects.get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'QuickTest {quick_test_id} not found'
            }, status=404)

        # Get schema summary
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        schema = artifact_service.get_schema_summary(quick_test)

        return JsonResponse({
            'success': True,
            'schema': schema
        })

    except Exception as e:
        logger.exception(f"Error getting schema: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def quick_test_training_history(request, quick_test_id):
    """
    Get training history (per-epoch metrics).

    Currently returns a placeholder response.
    Will be implemented with MLflow integration.

    GET /api/quick-tests/<id>/training-history/

    Returns:
    {
        "success": true,
        "training_history": {
            "available": false,
            "placeholder": true,
            "message": "Training curves will be available when MLflow integration is complete",
            "final_metrics": {
                "loss": 0.0234,
                "recall_at_10": 0.125,
                ...
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
            quick_test = QuickTest.objects.get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'QuickTest {quick_test_id} not found'
            }, status=404)

        # Get training history (placeholder for MLflow)
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        training_history = artifact_service.get_training_history(quick_test)

        return JsonResponse({
            'success': True,
            'training_history': training_history
        })

    except Exception as e:
        logger.exception(f"Error getting training history: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
