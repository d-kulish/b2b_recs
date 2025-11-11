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
    path('api/models/<int:model_id>/etl/toggle/', views.api_etl_toggle_enabled, name='api_etl_toggle_enabled'),
    path('api/models/<int:model_id>/etl/run/', views.api_etl_run_now, name='api_etl_run_now'),
    path('api/etl/sources/<int:source_id>/', views.api_etl_get_source, name='api_etl_get_source'),
    path('api/etl/sources/<int:source_id>/update/', views.api_etl_update_source, name='api_etl_update_source'),
    path('api/etl/sources/<int:source_id>/test/', views.api_etl_test_connection, name='api_etl_test_connection'),
    path('api/etl/sources/<int:source_id>/run/', views.api_etl_run_source, name='api_etl_run_source'),
    path('api/etl/sources/<int:source_id>/delete/', views.api_etl_delete_source, name='api_etl_delete_source'),
    path('api/etl/runs/<int:run_id>/status/', views.api_etl_run_status, name='api_etl_run_status'),
]
