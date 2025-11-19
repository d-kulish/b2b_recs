from django.urls import path
from . import views

urlpatterns = [
    # System Dashboard (Landing Page)
    path('', views.system_dashboard, name='system_dashboard'),

    # Model/Endpoint Creation
    path('models/create/', views.create_model_endpoint, name='create_model_endpoint'),

    # Individual Model/Endpoint Pages
    path('models/<int:model_id>/', views.model_dashboard, name='model_dashboard'),
    path('models/<int:model_id>/etl/', views.model_etl, name='model_etl'),
    path('models/<int:model_id>/dataset/', views.model_dataset, name='model_dataset'),
    path('models/<int:model_id>/pipeline-config/', views.model_pipeline_config, name='model_pipeline_config'),
    path('models/<int:model_id>/feature-engineering/', views.model_feature_engineering, name='model_feature_engineering'),
    path('models/<int:model_id>/training/', views.model_training, name='model_training'),
    path('models/<int:model_id>/experiments/', views.model_experiments, name='model_experiments'),
    path('models/<int:model_id>/deployment/', views.model_deployment, name='model_deployment'),

    # API Endpoints (for AJAX operations)
    path('api/models/<int:model_id>/start-training/', views.api_start_training, name='api_start_training'),
    path('api/models/<int:model_id>/start-etl/', views.api_start_etl, name='api_start_etl'),
    path('api/models/<int:model_id>/deploy/', views.api_deploy_model, name='api_deploy_model'),
    path('api/pipeline-runs/<int:run_id>/status/', views.api_pipeline_run_status, name='api_pipeline_run_status'),

    # ETL API Endpoints
    path('api/models/<int:model_id>/etl/add-source/', views.api_etl_add_source, name='api_etl_add_source'),
    path('api/models/<int:model_id>/etl/save-draft/', views.api_etl_save_draft_source, name='api_etl_save_draft_source'),
    path('api/models/<int:model_id>/etl/check-name/', views.api_etl_check_job_name, name='api_etl_check_job_name'),
    path('api/models/<int:model_id>/etl/toggle/', views.api_etl_toggle_enabled, name='api_etl_toggle_enabled'),
    path('api/models/<int:model_id>/etl/run/', views.api_etl_run_now, name='api_etl_run_now'),
    path('api/etl/test-connection/', views.api_etl_test_connection_wizard, name='api_etl_test_connection_wizard'),
    path('api/etl/sources/<int:source_id>/', views.api_etl_get_source, name='api_etl_get_source'),
    path('api/etl/sources/<int:source_id>/update/', views.api_etl_update_source, name='api_etl_update_source'),
    path('api/etl/sources/<int:source_id>/test/', views.api_etl_test_connection, name='api_etl_test_connection'),
    path('api/etl/sources/<int:source_id>/run/', views.api_etl_run_source, name='api_etl_run_source'),
    path('api/etl/sources/<int:source_id>/delete/', views.api_etl_delete_source, name='api_etl_delete_source'),
    path('api/etl/runs/<int:run_id>/status/', views.api_etl_run_status, name='api_etl_run_status'),

    # ETL Runner API endpoints (Phase 2)
    path('api/etl/job-config/<int:data_source_id>/', views.api_etl_job_config, name='api_etl_job_config'),
    path('api/etl/runs/<int:run_id>/update/', views.api_etl_run_update, name='api_etl_run_update'),
    path('api/etl/sources/<int:data_source_id>/trigger/', views.api_etl_trigger_now, name='api_etl_trigger_now'),

    # Connection Management API (New Architecture)
    path('api/models/<int:model_id>/connections/test-wizard/', views.api_connection_test_wizard, name='api_connection_test_wizard'),
    path('api/models/<int:model_id>/connections/create/', views.api_connection_create, name='api_connection_create'),
    path('api/models/<int:model_id>/connections/create-standalone/', views.api_connection_create_standalone, name='api_connection_create_standalone'),
    path('api/models/<int:model_id>/connections/', views.api_connection_list, name='api_connection_list'),
    path('api/connections/<int:connection_id>/', views.api_connection_get, name='api_connection_get'),
    path('api/connections/<int:connection_id>/credentials/', views.api_connection_get_credentials, name='api_connection_get_credentials'),
    path('api/connections/<int:connection_id>/test/', views.api_connection_test, name='api_connection_test'),
    path('api/connections/<int:connection_id>/test-and-fetch-tables/', views.api_connection_test_and_fetch_tables, name='api_connection_test_and_fetch_tables'),
    path('api/connections/<int:connection_id>/update/', views.api_connection_update, name='api_connection_update'),
    path('api/connections/<int:connection_id>/usage/', views.api_connection_get_usage, name='api_connection_get_usage'),
    path('api/connections/<int:connection_id>/delete/', views.api_connection_delete, name='api_connection_delete'),

    # New Simplified ETL Wizard API (Simplified Flow - Connection-First Approach)
    path('api/models/<int:model_id>/etl/connections/', views.api_etl_get_connections, name='api_etl_get_connections'),
    path('api/models/<int:model_id>/etl/create-job/', views.api_etl_create_job, name='api_etl_create_job'),
    path('api/connections/<int:connection_id>/test-wizard/', views.api_etl_test_connection_in_wizard, name='api_etl_test_connection_in_wizard'),

    # Schema and Table Fetching (ETL Wizard Step 2 - Databases)
    path('api/connections/<int:connection_id>/fetch-schemas/', views.api_connection_fetch_schemas, name='api_connection_fetch_schemas'),
    path('api/connections/<int:connection_id>/fetch-tables-for-schema/', views.api_connection_fetch_tables_for_schema, name='api_connection_fetch_tables_for_schema'),

    # File Listing (ETL Wizard Step 2 - Cloud Storage)
    path('api/connections/<int:connection_id>/list-files/', views.api_connection_list_files, name='api_connection_list_files'),
    path('api/connections/<int:connection_id>/detect-file-schema/', views.api_connection_detect_file_schema, name='api_connection_detect_file_schema'),

    # Table Preview (ETL Wizard Step 3)
    path('api/connections/<int:connection_id>/fetch-table-preview/', views.api_connection_fetch_table_preview, name='api_connection_fetch_table_preview'),
]
