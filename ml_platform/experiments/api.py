"""
Experiments Domain API

REST API endpoints for managing Quick Tests (ML experiments).
Handles starting, monitoring, and cancelling pipeline runs.
"""
import json
import logging
from django.http import JsonResponse, HttpResponse
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
        'dataset_id': quick_test.feature_config.dataset.id if quick_test.feature_config.dataset else None,
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
def quick_test_tfdv_visualization(request, quick_test_id):
    """
    Get TFDV HTML visualization for dataset statistics.

    GET /api/quick-tests/<id>/tfdv-visualization/

    Returns:
    {
        "success": true,
        "html": "<html>...</html>"
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

        # Get TFDV HTML visualization
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        html = artifact_service.get_statistics_html(quick_test)

        if html:
            return JsonResponse({
                'success': True,
                'html': html
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'TFDV visualization not available'
            }, status=404)

    except Exception as e:
        logger.exception(f"Error getting TFDV visualization: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def quick_test_tfdv_page(request, quick_test_id):
    """
    Serve TFDV HTML visualization as a standalone page.

    Opens in a new browser tab with proper rendering (not embedded in iframe).

    GET /experiments/quick-tests/<id>/tfdv/

    Returns: HTML page (Content-Type: text/html)
    """
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
            quick_test = QuickTest.objects.get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return HttpResponse(
                f'<html><body><h1>Error</h1><p>QuickTest {quick_test_id} not found.</p></body></html>',
                content_type='text/html',
                status=404
            )

        # Get TFDV HTML visualization
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        html = artifact_service.get_statistics_html(quick_test)

        if html:
            # Wrap in a proper HTML page with title and basic styling
            page_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TFDV Statistics - {quick_test.display_name}</title>
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
        .close-btn {{
            padding: 8px 16px;
            background: #f0f0f0;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }}
        .close-btn:hover {{
            background: #e0e0e0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>TFDV Statistics Visualization</h1>
            <div class="subtitle">{quick_test.display_name}</div>
        </div>
        <button class="close-btn" onclick="window.close()">Close Tab</button>
    </div>
    {html}
</body>
</html>'''
            return HttpResponse(page_html, content_type='text/html')
        else:
            return HttpResponse(
                '<html><body><h1>Not Available</h1>'
                '<p>TFDV visualization is not available for this experiment. '
                'The Statistics stage may not have completed yet.</p></body></html>',
                content_type='text/html',
                status=404
            )

    except Exception as e:
        logger.exception(f"Error getting TFDV page: {e}")
        return HttpResponse(
            f'<html><body><h1>Error</h1><p>{str(e)}</p></body></html>',
            content_type='text/html',
            status=500
        )


@csrf_exempt
@require_http_methods(["GET"])
def quick_test_component_logs(request, quick_test_id, component):
    """
    Get recent logs for a specific pipeline component.

    GET /api/quick-tests/<id>/logs/<component>/

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
            quick_test = QuickTest.objects.get(
                id=quick_test_id,
                feature_config__dataset__model_endpoint=model_endpoint
            )
        except QuickTest.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'QuickTest {quick_test_id} not found'
            }, status=404)

        # Get component logs
        artifact_service = ArtifactService(project_id=model_endpoint.gcp_project_id)
        logs = artifact_service.get_component_logs(quick_test, component)

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


# =============================================================================
# MLflow Comparison and Leaderboard Endpoints
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def compare_experiments(request):
    """
    Compare multiple experiments side-by-side with full configuration details.

    POST /api/experiments/compare/

    Request body:
    {
        "quick_test_ids": [1, 2, 3]
    }

    Returns comprehensive comparison data including:
    - Dataset details (name, rows, users, products)
    - Feature config details (buyer/product features with dimensions)
    - Model config details (type, optimizer, layers)
    - Training parameters
    - Results metrics
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        # Parse request body
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)

        quick_test_ids = data.get('quick_test_ids', [])

        if len(quick_test_ids) < 2:
            return JsonResponse({
                'success': False,
                'error': 'At least 2 experiments required for comparison'
            }, status=400)

        if len(quick_test_ids) > 5:
            return JsonResponse({
                'success': False,
                'error': 'Maximum 5 experiments can be compared at once'
            }, status=400)

        # Get QuickTests and verify access
        quick_tests = QuickTest.objects.filter(
            pk__in=quick_test_ids,
            feature_config__dataset__model_endpoint=model_endpoint
        ).select_related('feature_config', 'model_config', 'feature_config__dataset')

        if quick_tests.count() < 2:
            return JsonResponse({
                'success': False,
                'error': 'Not enough valid experiments found'
            }, status=400)

        # Build comprehensive comparison data
        experiments = []

        for qt in quick_tests:
            fc = qt.feature_config
            mc = qt.model_config
            ds = fc.dataset if fc else None

            # Build feature list strings (e.g., "user_id(64d), city(16d)")
            buyer_features_list = _format_feature_list(fc.buyer_model_features if fc else [])
            product_features_list = _format_feature_list(fc.product_model_features if fc else [])
            buyer_crosses_list = _format_crosses_list(fc.buyer_model_crosses if fc else [])
            product_crosses_list = _format_crosses_list(fc.product_model_crosses if fc else [])

            # Build model config summary
            model_layers_summary = _format_tower_layers(mc.buyer_tower_layers if mc else [])

            exp_data = {
                'id': qt.id,
                'experiment_number': qt.experiment_number,
                'display_name': qt.display_name,
                'experiment_name': qt.experiment_name or '',
                'status': qt.status,

                # Dataset details
                'dataset': {
                    'name': ds.name if ds else None,
                    'primary_table': ds.primary_table if ds else None,
                    'row_count': ds.summary_snapshot.get('estimated_rows') if ds and ds.summary_snapshot else None,
                    'unique_users': ds.summary_snapshot.get('unique_users') if ds and ds.summary_snapshot else None,
                    'unique_products': ds.summary_snapshot.get('unique_products') if ds and ds.summary_snapshot else None,
                },

                # Feature config details
                'feature_config': {
                    'name': fc.name if fc else None,
                    'version': fc.version if fc else None,
                    'buyer_features': buyer_features_list,
                    'buyer_features_count': len(fc.buyer_model_features) if fc else 0,
                    'buyer_tensor_dim': fc.buyer_tensor_dim if fc else None,
                    'buyer_crosses': buyer_crosses_list,
                    'product_features': product_features_list,
                    'product_features_count': len(fc.product_model_features) if fc else 0,
                    'product_tensor_dim': fc.product_tensor_dim if fc else None,
                    'product_crosses': product_crosses_list,
                },

                # Model config details
                'model_config': {
                    'name': mc.name if mc else None,
                    'model_type': mc.model_type if mc else None,
                    'optimizer': mc.optimizer if mc else None,
                    'output_embedding_dim': mc.output_embedding_dim if mc else None,
                    'tower_layers': model_layers_summary,
                },

                # Sampling parameters
                'sampling': {
                    'data_sample_percent': qt.data_sample_percent,
                    'split_strategy': qt.split_strategy,
                    'holdout_days': qt.holdout_days,
                    'date_column': qt.date_column or None,
                },

                # Training parameters
                'training': {
                    'epochs': qt.epochs,
                    'batch_size': qt.batch_size,
                    'learning_rate': float(qt.learning_rate) if qt.learning_rate else None,
                    'machine_type': qt.machine_type,
                },

                # Results
                'results': {
                    'loss': qt.loss,
                    'recall_at_10': qt.recall_at_10,
                    'recall_at_50': qt.recall_at_50,
                    'recall_at_100': qt.recall_at_100,
                    'duration_seconds': qt.duration_seconds,
                },
            }
            experiments.append(exp_data)

        return JsonResponse({
            'success': True,
            'comparison': {
                'experiments': experiments,
                'count': len(experiments)
            }
        })

    except Exception as e:
        logger.exception(f"Error comparing experiments: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _format_feature_list(features):
    """Format features as a readable list: 'user_id(64d), city(16d)'"""
    if not features:
        return ''
    parts = []
    for f in features:
        col = f.get('column', '')
        dim = f.get('embedding_dim', '')
        if col and dim:
            parts.append(f"{col}({dim}d)")
        elif col:
            parts.append(col)
    return ', '.join(parts)


def _format_crosses_list(crosses):
    """Format cross features as a readable list: 'user_id×city(16d)'"""
    if not crosses:
        return ''
    parts = []
    for c in crosses:
        features = c.get('features', [])
        dim = c.get('embedding_dim', '')
        if features:
            # Handle both string features and dict features with 'column' key
            feature_names = []
            for f in features:
                if isinstance(f, str):
                    feature_names.append(f)
                elif isinstance(f, dict):
                    feature_names.append(f.get('column', str(f)))
                else:
                    feature_names.append(str(f))
            cross_name = '×'.join(feature_names)
            if dim:
                parts.append(f"{cross_name}({dim}d)")
            else:
                parts.append(cross_name)
    return ', '.join(parts)


def _format_tower_layers(layers):
    """Format tower layers as a summary: '256→128→64'"""
    if not layers:
        return ''
    units = []
    for layer in layers:
        if layer.get('type') == 'dense':
            units.append(str(layer.get('units', '')))
    return '→'.join(units) if units else ''


@csrf_exempt
@require_http_methods(["GET"])
def experiment_leaderboard(request):
    """
    Get experiment leaderboard sorted by metric.

    GET /api/experiments/leaderboard/?metric=recall_at_100&limit=20

    Query params:
        metric: Metric to sort by (default: recall_at_100)
        limit: Max results (default: 20)

    Returns:
    {
        "success": true,
        "leaderboard": [
            {
                "rank": 1,
                "quick_test_id": 123,
                "experiment_number": "Exp #45",
                "feature_config": "...",
                "metrics": {...}
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

        # Parse query params
        metric = request.GET.get('metric', 'recall_at_100')
        try:
            limit = int(request.GET.get('limit', 20))
            limit = min(max(1, limit), 100)  # Clamp between 1 and 100
        except ValueError:
            limit = 20

        # Map metric name to model field
        metric_field_map = {
            'recall_at_100': 'recall_at_100',
            'recall_at_50': 'recall_at_50',
            'recall_at_10': 'recall_at_10',
            'loss': 'loss',
        }

        order_field = metric_field_map.get(metric, 'recall_at_100')

        # For loss, lower is better; for recall, higher is better
        if metric == 'loss':
            order_by = order_field  # Ascending
        else:
            order_by = f'-{order_field}'  # Descending

        # Query completed experiments with the metric
        queryset = QuickTest.objects.filter(
            feature_config__dataset__model_endpoint=model_endpoint,
            status=QuickTest.STATUS_COMPLETED
        ).exclude(
            **{f'{order_field}__isnull': True}
        ).select_related(
            'feature_config', 'model_config', 'feature_config__dataset'
        ).order_by(order_by)[:limit]

        # Build leaderboard
        leaderboard = []
        for i, qt in enumerate(queryset):
            leaderboard.append({
                'rank': i + 1,
                'quick_test_id': qt.id,
                'experiment_number': qt.experiment_number,
                'display_name': qt.display_name,
                'feature_config': qt.feature_config.name,
                'model_config': qt.model_config.name if qt.model_config else None,
                'dataset': qt.feature_config.dataset.name if qt.feature_config.dataset else None,
                'mlflow_run_id': qt.mlflow_run_id,
                'metrics': {
                    'loss': qt.loss,
                    'recall_at_10': qt.recall_at_10,
                    'recall_at_50': qt.recall_at_50,
                    'recall_at_100': qt.recall_at_100,
                },
                'created_at': qt.created_at.isoformat() if qt.created_at else None,
            })

        return JsonResponse({
            'success': True,
            'leaderboard': leaderboard,
            'metric': metric,
            'count': len(leaderboard)
        })

    except Exception as e:
        logger.exception(f"Error getting leaderboard: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def experiment_heatmap(request):
    """
    Get heatmap data showing best metric for each Feature Config × Model Config combination.

    GET /api/experiments/heatmap/?metric=recall_at_100

    Query params:
        metric: Metric to show (default: recall_at_100)

    Returns:
    {
        "success": true,
        "heatmap": {
            "feature_configs": ["FC1", "FC2", ...],
            "model_configs": ["MC1", "MC2", ...],
            "data": [
                {"x": 0, "y": 0, "v": 0.45, "exp_id": 123},
                {"x": 0, "y": 1, "v": 0.42, "exp_id": 124},
                ...
            ],
            "min_value": 0.35,
            "max_value": 0.48
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

        # Parse query params
        metric = request.GET.get('metric', 'recall_at_100')

        # Map metric name to model field
        metric_field_map = {
            'recall_at_100': 'recall_at_100',
            'recall_at_50': 'recall_at_50',
            'recall_at_10': 'recall_at_10',
        }

        metric_field = metric_field_map.get(metric, 'recall_at_100')

        # Get all completed experiments with the metric
        from django.db.models import Max

        queryset = QuickTest.objects.filter(
            feature_config__dataset__model_endpoint=model_endpoint,
            status=QuickTest.STATUS_COMPLETED
        ).exclude(
            **{f'{metric_field}__isnull': True}
        ).select_related('feature_config', 'model_config')

        # Build a mapping of (feature_config_id, model_config_id) -> best experiment
        config_best = {}  # (fc_id, mc_id) -> (metric_value, exp_id)

        for qt in queryset:
            fc_id = qt.feature_config_id
            mc_id = qt.model_config_id if qt.model_config else None
            if mc_id is None:
                continue

            metric_value = getattr(qt, metric_field)
            if metric_value is None:
                continue

            key = (fc_id, mc_id)
            if key not in config_best or metric_value > config_best[key][0]:
                config_best[key] = (metric_value, qt.id)

        # Get unique feature configs and model configs
        fc_ids = set()
        mc_ids = set()
        for (fc_id, mc_id) in config_best.keys():
            fc_ids.add(fc_id)
            mc_ids.add(mc_id)

        # Get names for display
        fc_names = {}
        mc_names = {}

        if fc_ids:
            for fc in FeatureConfig.objects.filter(id__in=fc_ids):
                fc_names[fc.id] = fc.name

        if mc_ids:
            for mc in ModelConfig.objects.filter(id__in=mc_ids):
                mc_names[mc.id] = mc.name

        # Sort by name for consistent display
        fc_list = sorted(fc_names.items(), key=lambda x: x[1])
        mc_list = sorted(mc_names.items(), key=lambda x: x[1])

        # Build index maps
        fc_index = {fc_id: i for i, (fc_id, _) in enumerate(fc_list)}
        mc_index = {mc_id: i for i, (mc_id, _) in enumerate(mc_list)}

        # Build heatmap data points
        data = []
        values = []

        for (fc_id, mc_id), (metric_value, exp_id) in config_best.items():
            x = mc_index.get(mc_id)
            y = fc_index.get(fc_id)
            if x is not None and y is not None:
                data.append({
                    'x': x,
                    'y': y,
                    'v': round(metric_value, 4) if metric_value else None,
                    'exp_id': exp_id
                })
                if metric_value:
                    values.append(metric_value)

        return JsonResponse({
            'success': True,
            'heatmap': {
                'feature_configs': [name for _, name in fc_list],
                'model_configs': [name for _, name in mc_list],
                'data': data,
                'min_value': round(min(values), 4) if values else None,
                'max_value': round(max(values), 4) if values else None,
                'metric': metric
            }
        })

    except Exception as e:
        logger.exception(f"Error getting heatmap data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def experiment_dashboard_stats(request):
    """
    Get summary statistics for the experiments dashboard.

    GET /api/experiments/dashboard-stats/

    Returns:
    {
        "success": true,
        "stats": {
            "total": 25,
            "completed": 18,
            "running": 2,
            "failed": 5,
            "best_recall_100": 0.473,
            "avg_recall_100": 0.412
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

        from django.db.models import Count, Max, Avg

        # Base queryset
        base_qs = QuickTest.objects.filter(
            feature_config__dataset__model_endpoint=model_endpoint
        )

        # Get counts by status
        status_counts = base_qs.values('status').annotate(count=Count('id'))
        counts_by_status = {item['status']: item['count'] for item in status_counts}

        total = sum(counts_by_status.values())
        completed = counts_by_status.get(QuickTest.STATUS_COMPLETED, 0)
        running = counts_by_status.get(QuickTest.STATUS_RUNNING, 0) + \
                  counts_by_status.get(QuickTest.STATUS_SUBMITTING, 0)
        failed = counts_by_status.get(QuickTest.STATUS_FAILED, 0)

        # Get metrics for completed experiments
        metrics = base_qs.filter(
            status=QuickTest.STATUS_COMPLETED,
            recall_at_100__isnull=False
        ).aggregate(
            best_recall_100=Max('recall_at_100'),
            avg_recall_100=Avg('recall_at_100')
        )

        return JsonResponse({
            'success': True,
            'stats': {
                'total': total,
                'completed': completed,
                'running': running,
                'failed': failed,
                'best_recall_100': round(metrics['best_recall_100'], 4) if metrics['best_recall_100'] else None,
                'avg_recall_100': round(metrics['avg_recall_100'], 4) if metrics['avg_recall_100'] else None,
            }
        })

    except Exception as e:
        logger.exception(f"Error getting dashboard stats: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def selectable_experiments(request):
    """
    Get list of experiments available for comparison selection.

    Returns experiments with status: completed, failed, or cancelled.
    Excludes running, submitting, and pending experiments.

    GET /api/experiments/selectable/

    Returns:
    {
        "success": true,
        "experiments": [
            {
                "id": 123,
                "experiment_number": "Exp #45",
                "experiment_name": "Testing Q4 features",
                "experiment_description_short": "First 30 chars of desc...",
                "status": "completed",
                "recall_at_100": 0.473,
                "feature_config_name": "Q4 v2",
                "model_config_name": "Standard",
                "created_at": "2024-12-23T10:30:00Z"
            },
            ...
        ],
        "count": 25
    }
    """
    try:
        model_endpoint = _get_model_endpoint(request)
        if not model_endpoint:
            return JsonResponse({
                'success': False,
                'error': 'No model endpoint selected'
            }, status=400)

        # Get experiments that can be compared (not running/submitting/pending)
        selectable_statuses = [
            QuickTest.STATUS_COMPLETED,
            QuickTest.STATUS_FAILED,
            QuickTest.STATUS_CANCELLED,
        ]

        queryset = QuickTest.objects.filter(
            feature_config__dataset__model_endpoint=model_endpoint,
            status__in=selectable_statuses
        ).select_related(
            'feature_config', 'model_config'
        ).order_by('-created_at')

        experiments = []
        for qt in queryset:
            # Truncate description to 30 chars
            desc_short = ''
            if qt.experiment_description:
                desc_short = qt.experiment_description[:30]
                if len(qt.experiment_description) > 30:
                    desc_short += '...'

            experiments.append({
                'id': qt.id,
                'experiment_number': qt.experiment_number,
                'display_name': qt.display_name,
                'experiment_name': qt.experiment_name or '',
                'experiment_description_short': desc_short,
                'status': qt.status,
                'recall_at_100': qt.recall_at_100,
                'feature_config_name': qt.feature_config.name if qt.feature_config else None,
                'model_config_name': qt.model_config.name if qt.model_config else None,
                'created_at': qt.created_at.isoformat() if qt.created_at else None,
            })

        return JsonResponse({
            'success': True,
            'experiments': experiments,
            'count': len(experiments)
        })

    except Exception as e:
        logger.exception(f"Error getting selectable experiments: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
