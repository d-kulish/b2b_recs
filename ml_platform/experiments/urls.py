"""
Experiments Domain URL Configuration

API endpoints for running and tracking experiments (Quick Tests).
"""
from django.urls import path
from . import api

app_name = 'experiments'

urlpatterns = [
    # Quick Test API endpoints
    path(
        'api/quick-tests/',
        api.quick_test_list,
        name='quick_test_list'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/',
        api.quick_test_detail,
        name='quick_test_detail'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/cancel/',
        api.quick_test_cancel,
        name='quick_test_cancel'
    ),

    # Artifact endpoints (lazy-loaded)
    path(
        'api/quick-tests/<int:quick_test_id>/errors/',
        api.quick_test_errors,
        name='quick_test_errors'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/statistics/',
        api.quick_test_statistics,
        name='quick_test_statistics'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/schema/',
        api.quick_test_schema,
        name='quick_test_schema'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/tfdv-visualization/',
        api.quick_test_tfdv_visualization,
        name='quick_test_tfdv_visualization'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/training-history/',
        api.quick_test_training_history,
        name='quick_test_training_history'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/logs/<str:component>/',
        api.quick_test_component_logs,
        name='quick_test_component_logs'
    ),

    # Start a new Quick Test (from FeatureConfig)
    path(
        'api/feature-configs/<int:feature_config_id>/quick-test/',
        api.start_quick_test,
        name='start_quick_test'
    ),

    # Get available date columns for a dataset (for split strategy UI)
    path(
        'api/datasets/<int:dataset_id>/date-columns/',
        api.get_date_columns,
        name='get_date_columns'
    ),
]
