"""
ML Platform URL Configuration

This is the main URL router for the ml_platform app.
Sub-apps (ETL, Connections, Datasets, Configs) have their own URL files that are included here.
"""
from django.urls import path, include
from . import views

urlpatterns = [
    # =========================================================================
    # SUB-APP INCLUDES (must be first to take precedence)
    # =========================================================================
    path('', include('ml_platform.etl.urls')),
    path('', include('ml_platform.connections.urls')),
    path('', include('ml_platform.datasets.urls')),
    path('', include('ml_platform.configs.urls')),
    path('', include('ml_platform.pipelines.urls')),

    # =========================================================================
    # SYSTEM DASHBOARD (Landing Page)
    # =========================================================================
    path('', views.system_dashboard, name='system_dashboard'),

    # =========================================================================
    # MODEL/ENDPOINT MANAGEMENT
    # =========================================================================
    path('models/create/', views.create_model_endpoint, name='create_model_endpoint'),

    # Individual Model/Endpoint Pages
    path('models/<int:model_id>/', views.model_dashboard, name='model_dashboard'),
    # Note: model_dataset is now handled by datasets sub-app
    # Note: model_configs is now handled by configs sub-app
    path('models/<int:model_id>/training/', views.model_training, name='model_training'),
    path('models/<int:model_id>/experiments/', views.model_experiments, name='model_experiments'),
    path('models/<int:model_id>/deployment/', views.model_deployment, name='model_deployment'),

    # =========================================================================
    # CORE API ENDPOINTS (Training, Deployment, Pipeline)
    # =========================================================================
    path('api/models/<int:model_id>/start-training/', views.api_start_training, name='api_start_training'),
    path('api/models/<int:model_id>/start-etl/', views.api_start_etl, name='api_start_etl'),
    path('api/models/<int:model_id>/deploy/', views.api_deploy_model, name='api_deploy_model'),
    path('api/pipeline-runs/<int:run_id>/status/', views.api_pipeline_run_status, name='api_pipeline_run_status'),
]
