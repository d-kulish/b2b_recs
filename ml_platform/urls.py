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
    path('', include('ml_platform.experiments.urls')),
    path('', include('ml_platform.training.urls')),

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

    # =========================================================================
    # SYSTEM-LEVEL API ENDPOINTS
    # =========================================================================
    path('api/system/kpis/', views.api_system_kpis, name='api_system_kpis'),
    path('api/system/charts/', views.api_system_charts, name='api_system_charts'),
    path('api/system/resource-charts/', views.api_system_resource_charts, name='api_system_resource_charts'),
    path('api/system/recent-activity/', views.api_system_recent_activity, name='api_system_recent_activity'),

    # Billing API
    path('api/system/billing/summary/', views.api_system_billing_summary, name='api_billing_summary'),
    path('api/system/billing/charts/', views.api_system_billing_charts, name='api_billing_charts'),
    path('api/system/billing/invoice/', views.api_system_billing_invoice, name='api_billing_invoice'),

    # =========================================================================
    # SCHEDULER WEBHOOKS
    # =========================================================================
    path('api/system/collect-metrics-webhook/', views.scheduler_collect_metrics_webhook, name='api_collect_metrics_webhook'),
    path('api/system/cleanup-artifacts-webhook/', views.scheduler_cleanup_artifacts_webhook, name='api_cleanup_artifacts_webhook'),
    path('api/system/collect-billing-webhook/', views.scheduler_collect_billing_webhook, name='api_collect_billing_webhook'),
    path('api/system/setup-metrics-scheduler/', views.api_setup_metrics_scheduler, name='api_setup_metrics_scheduler'),
    path('api/system/setup-cleanup-scheduler/', views.api_setup_cleanup_scheduler, name='api_setup_cleanup_scheduler'),
    path('api/system/cleanup-orphan-models-webhook/', views.scheduler_cleanup_orphan_models_webhook, name='api_cleanup_orphan_models_webhook'),
    path('api/system/setup-orphan-cleanup-scheduler/', views.api_setup_orphan_cleanup_scheduler, name='api_setup_orphan_cleanup_scheduler'),
]
