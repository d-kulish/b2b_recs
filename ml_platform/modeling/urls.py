"""
Modeling Domain URL Configuration

Routes for Feature Engineering (Modeling) domain.
"""

from django.urls import path
from . import views, api

urlpatterns = [
    # Page views
    path('models/<int:model_id>/modeling/', views.model_modeling, name='model_modeling'),

    # Feature Config CRUD API
    path('api/models/<int:model_id>/feature-configs/',
         api.list_feature_configs, name='api_modeling_list_configs'),
    path('api/models/<int:model_id>/feature-configs/create/',
         api.create_feature_config, name='api_modeling_create_config'),
    path('api/feature-configs/<int:config_id>/',
         api.get_feature_config, name='api_modeling_get_config'),
    path('api/feature-configs/<int:config_id>/update/',
         api.update_feature_config, name='api_modeling_update_config'),
    path('api/feature-configs/<int:config_id>/delete/',
         api.delete_feature_config, name='api_modeling_delete_config'),
    path('api/feature-configs/<int:config_id>/clone/',
         api.clone_feature_config, name='api_modeling_clone_config'),
    path('api/feature-configs/<int:config_id>/versions/',
         api.list_versions, name='api_modeling_list_versions'),

    # Utility endpoints
    path('api/feature-configs/smart-defaults/',
         api.generate_smart_defaults, name='api_modeling_smart_defaults'),
    path('api/feature-configs/calculate-dims/',
         api.calculate_dimensions, name='api_modeling_calculate_dims'),

    # Dataset endpoints for modeling
    path('api/models/<int:model_id>/modeling/datasets/',
         api.list_datasets_for_model, name='api_modeling_list_datasets'),
    path('api/datasets/<int:dataset_id>/columns/',
         api.get_dataset_columns, name='api_modeling_dataset_columns'),
]
