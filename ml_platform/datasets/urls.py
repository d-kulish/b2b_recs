"""
Datasets Sub-App URL Configuration

All dataset-related routes are defined here and included in the main urls.py.
"""
from django.urls import path
from . import views, api

urlpatterns = [
    # === PAGE VIEWS ===
    path('models/<int:model_id>/dataset/', views.model_dataset, name='model_dataset'),

    # === DATASET CRUD APIs ===
    path('api/models/<int:model_id>/datasets/', api.list_datasets, name='api_datasets_list'),
    path('api/models/<int:model_id>/datasets/create/', api.create_dataset, name='api_datasets_create'),
    path('api/models/<int:model_id>/datasets/check-name/', api.check_name, name='api_datasets_check_name'),
    path('api/datasets/<int:dataset_id>/', api.get_dataset, name='api_datasets_get'),
    path('api/datasets/<int:dataset_id>/update/', api.update_dataset, name='api_datasets_update'),
    path('api/datasets/<int:dataset_id>/delete/', api.delete_dataset, name='api_datasets_delete'),

    # === DATASET ACTIONS ===
    path('api/datasets/<int:dataset_id>/clone/', api.clone_dataset, name='api_datasets_clone'),
    path('api/datasets/<int:dataset_id>/activate/', api.activate_dataset, name='api_datasets_activate'),

    # === BIGQUERY INTEGRATION APIs ===
    path('api/models/<int:model_id>/bq-tables/', api.list_bq_tables, name='api_datasets_bq_tables'),
    path('api/models/<int:model_id>/bq-tables/<str:table_name>/schema/', api.get_table_schema, name='api_datasets_table_schema'),
    path('api/models/<int:model_id>/bq-tables/<str:table_name>/stats/', api.get_table_stats, name='api_datasets_table_stats'),
    path('api/models/<int:model_id>/bq-tables/<str:table_name>/columns/<str:column_name>/samples/', api.get_sample_values, name='api_datasets_sample_values'),

    # === SMART SUGGESTIONS ===
    path('api/models/<int:model_id>/detect-joins/', api.detect_joins, name='api_datasets_detect_joins'),
    path('api/models/<int:model_id>/suggest-columns/', api.suggest_columns, name='api_datasets_suggest_columns'),

    # === DATASET ANALYSIS ===
    path('api/datasets/<int:dataset_id>/analyze/', api.analyze_dataset, name='api_datasets_analyze'),
    path('api/datasets/<int:dataset_id>/preview/', api.preview_dataset, name='api_datasets_preview'),
    path('api/datasets/<int:dataset_id>/summary/', api.get_dataset_summary, name='api_datasets_summary'),

    # === QUERY GENERATION ===
    path('api/datasets/<int:dataset_id>/query/', api.get_generated_query, name='api_datasets_query'),
    path('api/datasets/<int:dataset_id>/query/split/', api.get_split_queries, name='api_datasets_split_queries'),
    path('api/datasets/<int:dataset_id>/query/tfx/', api.get_tfx_queries, name='api_datasets_tfx_queries'),
    path('api/datasets/<int:dataset_id>/validate-query/', api.validate_query, name='api_datasets_validate_query'),

    # === DATASET COMPARISON ===
    path('api/models/<int:model_id>/datasets/compare/', api.compare_datasets, name='api_datasets_compare'),

    # === VISUAL SCHEMA BUILDER (Preview Service) ===
    path('api/models/<int:model_id>/datasets/load-samples/', api.load_samples, name='api_datasets_load_samples'),
    path('api/models/<int:model_id>/datasets/preview/', api.generate_preview, name='api_datasets_generate_preview'),
    path('api/models/<int:model_id>/datasets/detect-joins-preview/', api.detect_joins_preview, name='api_datasets_detect_joins_preview'),
    path('api/models/<int:model_id>/datasets/cleanup-session/', api.cleanup_preview_session, name='api_datasets_cleanup_session'),

    # === PRODUCT REVENUE ANALYSIS ===
    path('api/models/<int:model_id>/datasets/analyze-product-revenue/', api.analyze_product_revenue, name='api_datasets_analyze_product_revenue'),

    # === CUSTOMER REVENUE ANALYSIS ===
    path('api/models/<int:model_id>/datasets/analyze-customer-revenue/', api.analyze_customer_revenue, name='api_datasets_analyze_customer_revenue'),

    # === CUSTOMER AGGREGATION ANALYSIS (transaction count, spending) ===
    path('api/models/<int:model_id>/datasets/analyze-customer-aggregations/', api.analyze_customer_aggregations, name='api_datasets_analyze_customer_aggregations'),

    # === DATASET STATS (for Dataset Summary panel) ===
    path('api/models/<int:model_id>/datasets/stats/', api.get_dataset_stats, name='api_datasets_stats'),

    # === COLUMN ANALYSIS (for Product Filters) ===
    path('api/models/<int:model_id>/datasets/analyze-columns/', api.analyze_columns_for_filters, name='api_datasets_analyze_columns'),
    path('api/models/<int:model_id>/datasets/search-category-values/', api.search_category_values, name='api_datasets_search_category_values'),
]
