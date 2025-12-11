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

    # Generated code endpoints
    path('api/feature-configs/<int:config_id>/generated-code/',
         api.get_generated_code, name='api_modeling_get_generated_code'),
    path('api/feature-configs/<int:config_id>/regenerate-code/',
         api.regenerate_code, name='api_modeling_regenerate_code'),

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
    path('api/datasets/<int:dataset_id>/schema-with-sample/',
         api.get_schema_with_sample, name='api_modeling_schema_with_sample'),

    # ==========================================================================
    # Model Config API (Model Structure Domain)
    # ==========================================================================

    # Model Config CRUD
    path('api/model-configs/',
         api.list_model_configs, name='api_model_configs_list'),
    path('api/model-configs/create/',
         api.create_model_config, name='api_model_configs_create'),
    path('api/model-configs/<int:config_id>/',
         api.get_model_config, name='api_model_configs_get'),
    path('api/model-configs/<int:config_id>/update/',
         api.update_model_config, name='api_model_configs_update'),
    path('api/model-configs/<int:config_id>/delete/',
         api.delete_model_config, name='api_model_configs_delete'),
    path('api/model-configs/<int:config_id>/clone/',
         api.clone_model_config, name='api_model_configs_clone'),

    # Model Config presets and validation
    path('api/model-configs/presets/',
         api.get_model_config_presets, name='api_model_configs_presets'),
    path('api/model-configs/presets/<str:preset_name>/',
         api.get_model_config_preset, name='api_model_configs_preset'),
    path('api/model-configs/validate/',
         api.validate_model_config, name='api_model_configs_validate'),
]
