"""
ETL Sub-App URL Configuration

All ETL-related routes are defined here and included in the main urls.py.
"""
from django.urls import path
from . import views, api, webhooks

urlpatterns = [
    # === PAGE VIEWS ===
    path('models/<int:model_id>/etl/', views.model_etl, name='model_etl'),

    # === ETL JOB MANAGEMENT APIs ===
    path('api/models/<int:model_id>/etl/add-source/', api.add_source, name='api_etl_add_source'),
    path('api/models/<int:model_id>/etl/save-draft/', api.save_draft_source, name='api_etl_save_draft_source'),
    path('api/models/<int:model_id>/etl/check-name/', api.check_job_name, name='api_etl_check_job_name'),
    path('api/models/<int:model_id>/etl/toggle/', api.toggle_enabled, name='api_etl_toggle_enabled'),
    path('api/models/<int:model_id>/etl/run/', api.run_now, name='api_etl_run_now'),
    path('api/models/<int:model_id>/etl/dashboard-stats/', api.etl_dashboard_stats, name='api_etl_dashboard_stats'),

    # === ETL SOURCE APIs ===
    path('api/etl/sources/<int:source_id>/', api.get_source, name='api_etl_get_source'),
    path('api/etl/sources/<int:source_id>/update/', api.update_source, name='api_etl_update_source'),
    path('api/etl/sources/<int:source_id>/test/', api.test_connection, name='api_etl_test_connection'),
    path('api/etl/sources/<int:source_id>/run/', api.run_source, name='api_etl_run_source'),
    path('api/etl/sources/<int:source_id>/delete/', api.delete_source, name='api_etl_delete_source'),
    path('api/etl/sources/<int:source_id>/toggle-pause/', api.toggle_pause, name='api_etl_toggle_pause'),
    path('api/etl/sources/<int:source_id>/edit/', api.edit_source, name='api_etl_edit_source'),
    path('api/etl/sources/<int:source_id>/available-columns/', api.available_columns, name='api_etl_available_columns'),

    # === ETL RUN APIs ===
    path('api/etl/runs/<int:run_id>/status/', api.run_status, name='api_etl_run_status'),
    path('api/etl/runs/<int:run_id>/update/', api.run_update, name='api_etl_run_update'),
    path('api/etl/runs/<int:run_id>/logs/', api.run_logs, name='api_etl_run_logs'),

    # === ETL RUNNER APIs (Cloud Run Job interaction) ===
    path('api/etl/job-config/<int:data_source_id>/', api.job_config, name='api_etl_job_config'),
    path('api/etl/sources/<int:data_source_id>/trigger/', api.trigger_now, name='api_etl_trigger_now'),
    path('api/etl/sources/<int:data_source_id>/processed-files/', api.get_processed_files, name='api_etl_get_processed_files'),
    path('api/etl/sources/<int:data_source_id>/record-processed-file/', api.record_processed_file, name='api_etl_record_processed_file'),

    # === WEBHOOKS ===
    path('api/etl/sources/<int:data_source_id>/scheduler-webhook/', webhooks.scheduler_webhook, name='api_etl_scheduler_webhook'),

    # === TEST CONNECTION ===
    path('api/etl/test-connection/', api.test_connection_wizard, name='api_etl_test_connection_wizard'),

    # === NEW SIMPLIFIED ETL WIZARD APIs ===
    path('api/models/<int:model_id>/etl/connections/', api.get_connections, name='api_etl_get_connections'),
    path('api/models/<int:model_id>/etl/create-job/', api.create_job, name='api_etl_create_job'),
    path('api/connections/<int:connection_id>/test-wizard/', api.test_connection_in_wizard, name='api_etl_test_connection_in_wizard'),

    # === BIGQUERY TABLE MANAGEMENT ===
    path('api/etl/datasets/<str:dataset_id>/tables/', api.list_bq_tables, name='api_etl_list_bq_tables'),
    path('api/etl/validate-schema-compatibility/', api.validate_schema_compatibility, name='api_etl_validate_schema_compatibility'),
]
