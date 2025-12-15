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
    List Quick Tests, optionally filtered by feature_config_id or model_config_id.

    GET /api/quick-tests/?feature_config_id=123
    GET /api/quick-tests/?model_config_id=456
    GET /api/quick-tests/?status=running

    Returns:
    {
        "success": true,
        "quick_tests": [...]
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

        # Order by most recent first
        queryset = queryset.order_by('-created_at')[:50]

        return JsonResponse({
            'success': True,
            'quick_tests': [_serialize_quick_test(qt) for qt in queryset]
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
            {"name": "trans_date", "type": "TIMESTAMP"},
            {"name": "event_date", "type": "DATE"},
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

        # Get date/timestamp columns from dataset's selected columns and stats
        date_columns = []
        column_stats = dataset.column_stats or {}
        selected_columns = dataset.selected_columns or {}

        # Date types in BigQuery
        date_types = {'TIMESTAMP', 'DATETIME', 'DATE'}

        for table, columns in selected_columns.items():
            for col in columns:
                # Check column type from stats
                stats_key = f"{table}.{col}" if '.' not in col else col
                col_stats = column_stats.get(stats_key, {})
                col_type = col_stats.get('type', '').upper()

                if col_type in date_types:
                    date_columns.append({
                        'name': col,
                        'type': col_type,
                        'table': table
                    })

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
    data = {
        'id': quick_test.id,
        'feature_config_id': quick_test.feature_config_id,
        'feature_config_name': quick_test.feature_config.name,
        'model_config_id': quick_test.model_config_id,
        'model_config_name': quick_test.model_config.name if quick_test.model_config else None,
        'status': quick_test.status,
        'current_stage': quick_test.current_stage,
        'progress_percent': quick_test.progress_percent,

        # Configuration
        'split_strategy': quick_test.split_strategy,
        'holdout_days': quick_test.holdout_days,
        'date_column': quick_test.date_column,
        'data_sample_percent': quick_test.data_sample_percent,
        'epochs': quick_test.epochs,
        'batch_size': quick_test.batch_size,
        'learning_rate': quick_test.learning_rate,

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
        data['stage_timestamps'] = quick_test.stage_timestamps

    return data
