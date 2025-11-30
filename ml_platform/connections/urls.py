"""
Connections Sub-App URL Configuration

All connection management routes are defined here and included in the main urls.py.
"""
from django.urls import path
from . import api

urlpatterns = [
    # =========================================================================
    # CONNECTION MANAGEMENT APIs (Model-scoped)
    # =========================================================================
    path('api/models/<int:model_id>/connections/test-wizard/', api.test_wizard, name='api_connection_test_wizard'),
    path('api/models/<int:model_id>/connections/create/', api.create, name='api_connection_create'),
    path('api/models/<int:model_id>/connections/create-standalone/', api.create, name='api_connection_create_standalone'),
    path('api/models/<int:model_id>/connections/', api.list_connections, name='api_connection_list'),

    # =========================================================================
    # CONNECTION CRUD APIs (Connection-scoped)
    # =========================================================================
    path('api/connections/<int:connection_id>/', api.get, name='api_connection_get'),
    path('api/connections/<int:connection_id>/credentials/', api.get_credentials, name='api_connection_get_credentials'),
    path('api/connections/<int:connection_id>/test/', api.test, name='api_connection_test'),
    path('api/connections/<int:connection_id>/test-and-fetch-tables/', api.test_and_fetch_tables, name='api_connection_test_and_fetch_tables'),
    path('api/connections/<int:connection_id>/update/', api.update, name='api_connection_update'),
    path('api/connections/<int:connection_id>/usage/', api.get_usage, name='api_connection_get_usage'),
    path('api/connections/<int:connection_id>/delete/', api.delete, name='api_connection_delete'),

    # =========================================================================
    # SCHEMA AND TABLE FETCHING (Database connections)
    # =========================================================================
    path('api/connections/<int:connection_id>/fetch-schemas/', api.fetch_schemas, name='api_connection_fetch_schemas'),
    path('api/connections/<int:connection_id>/fetch-tables-for-schema/', api.fetch_tables_for_schema, name='api_connection_fetch_tables_for_schema'),

    # =========================================================================
    # FILE OPERATIONS (Cloud Storage connections)
    # =========================================================================
    path('api/connections/<int:connection_id>/list-files/', api.list_connections_files, name='api_connection_list_files'),
    path('api/connections/<int:connection_id>/detect-file-schema/', api.detect_file_schema, name='api_connection_detect_file_schema'),

    # =========================================================================
    # TABLE PREVIEW
    # =========================================================================
    path('api/connections/<int:connection_id>/fetch-table-preview/', api.fetch_table_preview, name='api_connection_fetch_table_preview'),
]
