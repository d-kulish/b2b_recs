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
