"""
API endpoints for Quick Test pipeline management.

Endpoints:
- POST /api/feature-configs/{config_id}/quick-test/ - Start a quick test
- GET /api/quick-tests/{test_id}/ - Get quick test status/results
- POST /api/quick-tests/{test_id}/cancel/ - Cancel a running test
- GET /api/feature-configs/{config_id}/quick-tests/ - List tests for a config
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from ml_platform.models import FeatureConfig, QuickTest
from ml_platform.pipelines.services import PipelineService, PipelineServiceError

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def start_quick_test(request, config_id):
    """
    Start a Quick Test for a Feature Config.

    POST /api/feature-configs/{config_id}/quick-test/

    Request body:
    {
        "epochs": 10,
        "batch_size": 4096,
        "learning_rate": 0.001
    }

    Response:
    {
        "success": true,
        "data": {
            "quick_test_id": 42,
            "status": "submitting",
            ...
        }
    }
    """
    try:
        feature_config = FeatureConfig.objects.select_related('dataset').get(pk=config_id)
    except FeatureConfig.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Feature Config not found"
        }, status=404)

    # Validate generated code exists
    if not feature_config.generated_transform_code or not feature_config.generated_trainer_code:
        return JsonResponse({
            "success": False,
            "error": "Generated code not found. Please regenerate code first."
        }, status=400)

    # Validate dataset exists
    if not feature_config.dataset:
        return JsonResponse({
            "success": False,
            "error": "No dataset associated with this Feature Config."
        }, status=400)

    # Parse request body
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    epochs = body.get("epochs", 10)
    batch_size = body.get("batch_size", 4096)
    learning_rate = body.get("learning_rate", 0.001)

    # Validate parameters
    if not isinstance(epochs, int) or not (1 <= epochs <= 15):
        return JsonResponse({
            "success": False,
            "error": "Epochs must be an integer between 1 and 15"
        }, status=400)

    if batch_size not in [1024, 2048, 4096, 8192]:
        return JsonResponse({
            "success": False,
            "error": "Batch size must be 1024, 2048, 4096, or 8192"
        }, status=400)

    if not isinstance(learning_rate, (int, float)) or not (0.0001 <= learning_rate <= 0.1):
        return JsonResponse({
            "success": False,
            "error": "Learning rate must be between 0.0001 and 0.1"
        }, status=400)

    # Submit quick test
    try:
        service = PipelineService()
        quick_test = service.submit_quick_test(
            feature_config=feature_config,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=float(learning_rate),
            user=request.user
        )

        return JsonResponse({
            "success": True,
            "data": _serialize_quick_test(quick_test),
            "message": "Quick Test started successfully"
        })

    except PipelineServiceError as e:
        logger.error(f"Pipeline service error for config {config_id}: {e}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)
    except NotImplementedError as e:
        # Pipeline definition not yet implemented
        logger.warning(f"Pipeline not yet implemented: {e}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=501)
    except Exception as e:
        logger.exception(f"Failed to start Quick Test for config {config_id}")
        return JsonResponse({
            "success": False,
            "error": f"Failed to start Quick Test: {str(e)}"
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_quick_test(request, test_id):
    """
    Get Quick Test status and results.

    GET /api/quick-tests/{test_id}/

    Response:
    {
        "success": true,
        "data": {
            "id": 42,
            "status": "running",
            "progress_percent": 65,
            "current_stage": "Transform",
            "stages": [...],
            ...
        }
    }
    """
    try:
        quick_test = QuickTest.objects.select_related('feature_config').get(pk=test_id)
    except QuickTest.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Quick Test not found"
        }, status=404)

    # If still running, update status from Vertex AI
    if not quick_test.is_terminal and quick_test.vertex_pipeline_job_name:
        try:
            service = PipelineService()
            quick_test = service.update_quick_test_status(quick_test)
        except Exception as e:
            logger.warning(f"Failed to update QuickTest {test_id} status: {e}")

    return JsonResponse({
        "success": True,
        "data": _serialize_quick_test(quick_test)
    })


@login_required
@require_http_methods(["POST"])
def cancel_quick_test(request, test_id):
    """
    Cancel a running Quick Test.

    POST /api/quick-tests/{test_id}/cancel/
    """
    try:
        quick_test = QuickTest.objects.get(pk=test_id)
    except QuickTest.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Quick Test not found"
        }, status=404)

    if quick_test.is_terminal:
        return JsonResponse({
            "success": False,
            "error": f"Quick Test is already {quick_test.status}"
        }, status=400)

    try:
        service = PipelineService()
        success = service.cancel_pipeline(quick_test)

        if success:
            return JsonResponse({
                "success": True,
                "data": _serialize_quick_test(quick_test),
                "message": "Quick Test cancelled successfully"
            })
        else:
            return JsonResponse({
                "success": False,
                "error": "Failed to cancel pipeline"
            }, status=500)

    except Exception as e:
        logger.exception(f"Failed to cancel QuickTest {test_id}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_quick_tests(request, config_id):
    """
    List all Quick Tests for a Feature Config.

    GET /api/feature-configs/{config_id}/quick-tests/

    Query params:
    - limit: max number of results (default: 20)
    """
    try:
        feature_config = FeatureConfig.objects.get(pk=config_id)
    except FeatureConfig.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Feature Config not found"
        }, status=404)

    limit = int(request.GET.get('limit', 20))
    limit = min(limit, 100)  # Max 100

    quick_tests = QuickTest.objects.filter(
        feature_config=feature_config
    ).order_by('-created_at')[:limit]

    return JsonResponse({
        "success": True,
        "data": [_serialize_quick_test(qt) for qt in quick_tests],
        "count": len(quick_tests),
        "feature_config_id": config_id,
        "feature_config_name": feature_config.name
    })


def _serialize_quick_test(quick_test: QuickTest) -> dict:
    """Serialize QuickTest to JSON-compatible dict."""
    return {
        "id": quick_test.pk,
        "feature_config_id": quick_test.feature_config_id,
        "feature_config_name": quick_test.feature_config.name,

        # Configuration
        "epochs": quick_test.epochs,
        "batch_size": quick_test.batch_size,
        "learning_rate": quick_test.learning_rate,
        "data_sample_percent": quick_test.data_sample_percent,

        # Status
        "status": quick_test.status,
        "current_stage": quick_test.current_stage,
        "progress_percent": quick_test.progress_percent,
        "stage_details": quick_test.stage_details,

        # Results
        "loss": quick_test.loss,
        "recall_at_10": quick_test.recall_at_10,
        "recall_at_50": quick_test.recall_at_50,
        "recall_at_100": quick_test.recall_at_100,
        "vocabulary_stats": quick_test.vocabulary_stats,

        # Error info
        "error_message": quick_test.error_message,
        "error_stage": quick_test.error_stage,

        # Timestamps
        "created_at": quick_test.created_at.isoformat() if quick_test.created_at else None,
        "submitted_at": quick_test.submitted_at.isoformat() if quick_test.submitted_at else None,
        "started_at": quick_test.started_at.isoformat() if quick_test.started_at else None,
        "completed_at": quick_test.completed_at.isoformat() if quick_test.completed_at else None,
        "duration_seconds": quick_test.duration_seconds,
        "elapsed_seconds": quick_test.elapsed_seconds,

        # Vertex AI
        "vertex_pipeline_job_id": quick_test.vertex_pipeline_job_id,
        "gcs_artifacts_path": quick_test.gcs_artifacts_path,
    }
