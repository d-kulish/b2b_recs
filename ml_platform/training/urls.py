"""
Training Domain URL Configuration

API endpoints for running and tracking full-scale training runs and schedules.
"""
from django.urls import path
from . import api
from . import webhooks

app_name = 'training'

urlpatterns = [
    # ==========================================================================
    # Training Run CRUD endpoints
    # ==========================================================================
    path(
        'api/training-runs/',
        api.training_run_list,
        name='training_run_list'
    ),
    path(
        'api/training-runs/check-name/',
        api.training_run_check_name,
        name='training_run_check_name'
    ),
    path(
        'api/training-runs/<int:training_run_id>/',
        api.training_run_detail,
        name='training_run_detail'
    ),
    path(
        'api/training-runs/<int:training_run_id>/cancel/',
        api.training_run_cancel,
        name='training_run_cancel'
    ),
    path(
        'api/training-runs/<int:training_run_id>/delete/',
        api.training_run_delete,
        name='training_run_delete'
    ),
    path(
        'api/training-runs/<int:training_run_id>/submit/',
        api.training_run_submit,
        name='training_run_submit'
    ),
    path(
        'api/training-runs/<int:training_run_id>/retry/',
        api.training_run_retry,
        name='training_run_retry'
    ),
    path(
        'api/training-runs/<int:training_run_id>/deploy/',
        api.training_run_deploy,
        name='training_run_deploy'
    ),
    path(
        'api/training-runs/<int:training_run_id>/push/',
        api.training_run_push,
        name='training_run_push'
    ),

    # ==========================================================================
    # Training Schedule CRUD endpoints
    # ==========================================================================
    path(
        'api/training/schedules/',
        api.training_schedule_list,
        name='training_schedule_list'
    ),
    path(
        'api/training/schedules/<int:schedule_id>/',
        api.training_schedule_detail,
        name='training_schedule_detail'
    ),
    path(
        'api/training/schedules/<int:schedule_id>/pause/',
        api.training_schedule_pause,
        name='training_schedule_pause'
    ),
    path(
        'api/training/schedules/<int:schedule_id>/resume/',
        api.training_schedule_resume,
        name='training_schedule_resume'
    ),
    path(
        'api/training/schedules/<int:schedule_id>/cancel/',
        api.training_schedule_cancel,
        name='training_schedule_cancel'
    ),
    path(
        'api/training/schedules/<int:schedule_id>/trigger/',
        api.training_schedule_trigger,
        name='training_schedule_trigger'
    ),

    # ==========================================================================
    # Webhook endpoint for Cloud Scheduler
    # ==========================================================================
    path(
        'api/training/schedules/<int:schedule_id>/webhook/',
        webhooks.training_scheduler_webhook,
        name='training_scheduler_webhook'
    ),
]
