"""
Configs Domain URL Configuration

Routes for Feature & Model Configuration (Configs) domain.
"""

from django.urls import path
from . import views, api

urlpatterns = [
    # Page views
    path('models/<int:model_id>/configs/', views.model_configs, name='model_configs'),

    # Feature Config CRUD API
    path('api/models/<int:model_id>/feature-configs/',
         api.list_feature_configs, name='api_configs_list'),
    path('api/models/<int:model_id>/feature-configs/create/',
         api.create_feature_config, name='api_configs_create'),
    path('api/feature-configs/<int:config_id>/',
         api.get_feature_config, name='api_configs_get'),
    path('api/feature-configs/<int:config_id>/update/',
         api.update_feature_config, name='api_configs_update'),
    path('api/feature-configs/<int:config_id>/delete/',
         api.delete_feature_config, name='api_configs_delete'),
    path('api/feature-configs/<int:config_id>/clone/',
         api.clone_feature_config, name='api_configs_clone'),
    path('api/feature-configs/<int:config_id>/versions/',
         api.list_versions, name='api_configs_list_versions'),

    # Generated code endpoints
    path('api/feature-configs/<int:config_id>/generated-code/',
         api.get_generated_code, name='api_configs_get_generated_code'),
    path('api/feature-configs/<int:config_id>/regenerate-code/',
         api.regenerate_code, name='api_configs_regenerate_code'),

    # Combined trainer code generation (requires both FeatureConfig + ModelConfig)
    path('api/configs/generate-trainer-code/',
         api.generate_trainer_code, name='api_configs_generate_trainer_code'),

    # Utility endpoints
    path('api/feature-configs/smart-defaults/',
         api.generate_smart_defaults, name='api_configs_smart_defaults'),
    path('api/feature-configs/calculate-dims/',
         api.calculate_dimensions, name='api_configs_calculate_dims'),

    # Dashboard stats API
    path('api/models/<int:model_id>/configs/dashboard-stats/',
         api.get_configs_dashboard_stats, name='api_configs_dashboard_stats'),

    # Dataset endpoints for configs
    path('api/models/<int:model_id>/configs/datasets/',
         api.list_datasets_for_model, name='api_configs_list_datasets'),
    path('api/datasets/<int:dataset_id>/columns/',
         api.get_dataset_columns, name='api_configs_dataset_columns'),
    path('api/datasets/<int:dataset_id>/schema-with-sample/',
         api.get_schema_with_sample, name='api_configs_schema_with_sample'),

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
    path('api/model-configs/check-name/',
         api.check_model_config_name, name='api_model_configs_check_name'),

    # Ranking model specific endpoints
    path('api/model-configs/rating-head-presets/',
         api.get_rating_head_presets, name='api_model_configs_rating_head_presets'),
    path('api/model-configs/loss-functions/',
         api.get_loss_function_info, name='api_model_configs_loss_functions'),

    # Feature Config name check
    path('api/feature-configs/check-name/',
         api.check_feature_config_name, name='api_feature_configs_check_name'),
]
