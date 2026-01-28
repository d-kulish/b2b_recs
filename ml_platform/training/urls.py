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
        'api/training-runs/<int:training_run_id>/rerun/',
        api.training_run_rerun,
        name='training_run_rerun'
    ),
    path(
        'api/training-runs/<int:training_run_id>/config/',
        api.training_run_config,
        name='training_run_config'
    ),
    path(
        'api/training-runs/<int:training_run_id>/schedule-webhook/',
        api.training_run_schedule_webhook,
        name='training_run_schedule_webhook'
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
    path(
        'api/training-runs/<int:training_run_id>/register/',
        api.training_run_register,
        name='training_run_register'
    ),
    path(
        'api/training-runs/<int:training_run_id>/deploy-cloud-run/',
        api.training_run_deploy_cloud_run,
        name='training_run_deploy_cloud_run'
    ),

    # ==========================================================================
    # Cloud Run Services endpoint
    # ==========================================================================
    path(
        'api/cloud-run/services/',
        api.cloud_run_services_list,
        name='cloud_run_services_list'
    ),

    # ==========================================================================
    # Training Run Data Insights endpoints
    # ==========================================================================
    path(
        'api/training-runs/<int:training_run_id>/statistics/',
        api.training_run_statistics,
        name='training_run_statistics'
    ),
    path(
        'api/training-runs/<int:training_run_id>/schema/',
        api.training_run_schema,
        name='training_run_schema'
    ),
    path(
        'api/training-runs/<int:training_run_id>/training-history/',
        api.training_run_training_history,
        name='training_run_training_history'
    ),
    path(
        'api/training-runs/<int:training_run_id>/histogram-data/',
        api.training_run_histogram_data,
        name='training_run_histogram_data'
    ),
    path(
        'api/training-runs/<int:training_run_id>/logs/<str:component>/',
        api.training_run_component_logs,
        name='training_run_component_logs'
    ),
    path(
        'training/runs/<int:training_run_id>/tfdv/',
        api.training_run_tfdv_page,
        name='training_run_tfdv_page'
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

    # Schedule convenience endpoints (create from existing runs)
    path(
        'api/training/schedules/from-run/',
        api.training_schedule_from_run,
        name='training_schedule_from_run'
    ),
    path(
        'api/training/schedules/preview/',
        api.training_schedule_preview,
        name='training_schedule_preview'
    ),

    # ==========================================================================
    # Webhook endpoint for Cloud Scheduler
    # ==========================================================================
    path(
        'api/training/schedules/<int:schedule_id>/webhook/',
        webhooks.training_scheduler_webhook,
        name='training_scheduler_webhook'
    ),

    # ==========================================================================
    # RegisteredModel API endpoints
    # ==========================================================================
    path(
        'api/registered-models/',
        api.registered_models_list,
        name='registered_models_list'
    ),
    path(
        'api/registered-models/check-name/',
        api.registered_model_check_name,
        name='registered_model_check_name'
    ),
    path(
        'api/registered-models/<int:registered_model_id>/',
        api.registered_model_detail,
        name='registered_model_detail'
    ),
    path(
        'api/registered-models/<int:registered_model_id>/versions/',
        api.registered_model_versions,
        name='registered_model_versions'
    ),
    path(
        'api/registered-models/<int:registered_model_id>/endpoints/',
        api.registered_model_endpoints,
        name='registered_model_endpoints'
    ),

    # ==========================================================================
    # Models Registry API endpoints
    # ==========================================================================
    path(
        'api/models/',
        api.models_list,
        name='models_list'
    ),
    path(
        'api/models/names/',
        api.registered_model_names,
        name='registered_model_names'
    ),
    path(
        'api/models/<int:model_id>/',
        api.model_detail,
        name='model_detail'
    ),
    path(
        'api/models/<int:model_id>/versions/',
        api.model_versions,
        name='model_versions'
    ),
    path(
        'api/models/<int:model_id>/deploy/',
        api.model_deploy,
        name='model_deploy'
    ),
    path(
        'api/models/<int:model_id>/undeploy/',
        api.model_undeploy,
        name='model_undeploy'
    ),
    path(
        'api/models/<int:model_id>/delete/',
        api.model_delete,
        name='model_delete'
    ),
    path(
        'api/models/<int:model_id>/lineage/',
        api.model_lineage,
        name='model_lineage'
    ),
    path(
        'api/training-schedules/calendar/',
        api.training_schedules_calendar,
        name='training_schedules_calendar'
    ),
]
