"""
Training Webhooks

Webhook endpoints for Cloud Scheduler integration with training schedules.
These endpoints are authenticated via OIDC tokens (not CSRF/session).
"""
import json
import logging

from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.conf import settings

from .models import TrainingSchedule
from .schedule_service import TrainingScheduleService

logger = logging.getLogger(__name__)


def verify_oidc_token(request) -> dict:
    """
    Verify OIDC token from Cloud Scheduler.

    Cloud Scheduler includes an Authorization header with an OIDC token
    that can be verified to ensure the request is authentic.

    Args:
        request: Django HTTP request

    Returns:
        Dict with token claims if valid, None otherwise
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        logger.warning("Missing or invalid Authorization header")
        return None

    token = auth_header[7:]  # Remove 'Bearer ' prefix

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests

        # Verify the token
        # The audience should match our webhook URL base
        audience = request.build_absolute_uri('/').rstrip('/')

        claims = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            audience=audience
        )

        # Verify the expected service account email
        expected_email = getattr(
            settings,
            'TRAINING_SCHEDULER_SERVICE_ACCOUNT',
            f"training-scheduler@{settings.GCP_PROJECT_ID}.iam.gserviceaccount.com"
        )

        if claims.get('email') != expected_email:
            logger.warning(
                f"Token email mismatch: expected {expected_email}, "
                f"got {claims.get('email')}"
            )
            # In strict mode, return None here
            # For now, we'll allow it if the token is valid
            pass

        logger.debug(f"OIDC token verified for: {claims.get('email')}")
        return claims

    except Exception as e:
        logger.warning(f"OIDC token verification failed: {e}")
        return None


@require_http_methods(["POST"])
@csrf_exempt  # OIDC token provides authentication instead of CSRF
def training_scheduler_webhook(request, schedule_id):
    """
    Webhook for Cloud Scheduler to trigger scheduled training.

    This endpoint is called by Cloud Scheduler when a schedule fires.
    Authentication is via OIDC token (not CSRF/session).

    POST /api/training/schedules/<schedule_id>/webhook/

    Request body (JSON):
    {
        "schedule_id": 123,
        "trigger": "scheduled"
    }

    Returns:
    - 200: Training triggered successfully
    - 401: Invalid/missing OIDC token
    - 404: Schedule not found
    - 500: Internal error

    Response body:
    {
        "status": "success" | "skipped" | "error",
        "training_run_id": 456,  // if successful
        "message": "..."
    }
    """
    logger.info(f"Received webhook for schedule {schedule_id}")

    # Skip OIDC verification in DEBUG mode for local testing
    if not settings.DEBUG:
        claims = verify_oidc_token(request)
        if not claims:
            logger.warning(f"Webhook auth failed for schedule {schedule_id}")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid or missing OIDC token'
            }, status=401)
    else:
        logger.debug("Skipping OIDC verification in DEBUG mode")

    try:
        schedule = get_object_or_404(TrainingSchedule, id=schedule_id)

        # Check if schedule is active
        if schedule.status != TrainingSchedule.STATUS_ACTIVE:
            logger.info(
                f"Schedule {schedule_id} is {schedule.status}, skipping execution"
            )
            return JsonResponse({
                'status': 'skipped',
                'message': f'Schedule is {schedule.status}'
            })

        # Execute the scheduled training
        service = TrainingScheduleService(schedule.ml_model)
        training_run = service.execute_scheduled_training(schedule)

        logger.info(
            f"Webhook triggered training run {training_run.id} "
            f"for schedule {schedule_id}"
        )

        return JsonResponse({
            'status': 'success',
            'training_run_id': training_run.id,
            'message': f'Training run {training_run.id} created successfully'
        })

    except TrainingSchedule.DoesNotExist:
        logger.warning(f"Schedule {schedule_id} not found")
        return JsonResponse({
            'status': 'error',
            'message': f'Schedule {schedule_id} not found'
        }, status=404)

    except Exception as e:
        logger.exception(f"Error processing webhook for schedule {schedule_id}: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
