"""
URL routes for Quick Test pipeline management.
"""
from django.urls import path
from . import api

urlpatterns = [
    # Quick Test endpoints
    path(
        'api/feature-configs/<int:config_id>/quick-test/',
        api.start_quick_test,
        name='start_quick_test'
    ),
    path(
        'api/feature-configs/<int:config_id>/quick-tests/',
        api.list_quick_tests,
        name='list_quick_tests'
    ),
    path(
        'api/quick-tests/<int:test_id>/',
        api.get_quick_test,
        name='get_quick_test'
    ),
    path(
        'api/quick-tests/<int:test_id>/cancel/',
        api.cancel_quick_test,
        name='cancel_quick_test'
    ),
]
