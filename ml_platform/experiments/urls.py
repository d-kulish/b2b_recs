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
    path(
        'api/quick-tests/<int:quick_test_id>/delete/',
        api.quick_test_delete,
        name='quick_test_delete'
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
    # Standalone TFDV page (opens in new tab)
    path(
        'experiments/quick-tests/<int:quick_test_id>/tfdv/',
        api.quick_test_tfdv_page,
        name='quick_test_tfdv_page'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/training-history/',
        api.quick_test_training_history,
        name='quick_test_training_history'
    ),
    path(
        'api/quick-tests/<int:quick_test_id>/histogram-data/',
        api.quick_test_histogram_data,
        name='quick_test_histogram_data'
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

    # MLflow Comparison and Leaderboard
    path(
        'api/experiments/selectable/',
        api.selectable_experiments,
        name='selectable_experiments'
    ),
    path(
        'api/experiments/compare/',
        api.compare_experiments,
        name='compare_experiments'
    ),
    path(
        'api/experiments/leaderboard/',
        api.experiment_leaderboard,
        name='experiment_leaderboard'
    ),
    path(
        'api/experiments/heatmap/',
        api.experiment_heatmap,
        name='experiment_heatmap'
    ),
    path(
        'api/experiments/dashboard-stats/',
        api.experiment_dashboard_stats,
        name='experiment_dashboard_stats'
    ),

    # New Dashboard Analytics Endpoints
    path(
        'api/experiments/metrics-trend/',
        api.metrics_trend,
        name='metrics_trend'
    ),
    path(
        'api/experiments/hyperparameter-analysis/',
        api.hyperparameter_analysis,
        name='hyperparameter_analysis'
    ),
    path(
        'api/experiments/top-configurations/',
        api.top_configurations,
        name='top_configurations'
    ),
    path(
        'api/experiments/suggestions/',
        api.experiment_suggestions,
        name='experiment_suggestions'
    ),
    path(
        'api/experiments/dataset-comparison/',
        api.dataset_comparison,
        name='dataset_comparison'
    ),
]
