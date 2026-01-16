"""
Training Domain URL Configuration

API endpoints for running and tracking full-scale training runs.
"""
from django.urls import path
from . import api

app_name = 'training'

urlpatterns = [
    # Training Run CRUD endpoints
    path(
        'api/training-runs/',
        api.training_run_list,
        name='training_run_list'
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

    # Future endpoints (skeleton)
    # path('api/training-runs/<int:training_run_id>/logs/', ...),
    # path('api/training-runs/<int:training_run_id>/training-history/', ...),
    # path('api/training-runs/<int:training_run_id>/deploy/', ...),
]
