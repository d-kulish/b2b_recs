from django.contrib import admin
from .models import (
    ModelEndpoint,
    ETLConfiguration,
    Connection,
    DataSource,
    DataSourceTable,
    ETLRun,
    PipelineConfiguration,
    PipelineRun,
    Experiment,
    TrainedModel,
    Deployment,
    PredictionLog,
    SystemMetrics,
    FeatureConfig,
    FeatureConfigVersion,
)


@admin.register(ModelEndpoint)
class ModelEndpointAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'is_endpoint_active', 'created_by', 'created_at', 'last_trained_at']
    list_filter = ['status', 'is_endpoint_active', 'created_at']
    search_fields = ['name', 'description', 'gcp_project_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ETLConfiguration)
class ETLConfigurationAdmin(admin.ModelAdmin):
    list_display = ['model_endpoint', 'schedule_type', 'is_enabled', 'last_run_at', 'last_run_status']
    list_filter = ['schedule_type', 'is_enabled']
    search_fields = ['model_endpoint__name']
    readonly_fields = ['created_at', 'updated_at', 'last_run_at']


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_type', 'model_endpoint', 'is_enabled', 'connection_tested', 'last_test_at', 'last_used_at']
    list_filter = ['source_type', 'is_enabled', 'connection_tested']
    search_fields = ['name', 'model_endpoint__name', 'source_host']
    readonly_fields = ['created_at', 'updated_at', 'last_test_at', 'last_used_at']


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_type', 'connection', 'etl_config', 'is_enabled']
    list_filter = ['source_type', 'is_enabled']
    search_fields = ['name', 'etl_config__model_endpoint__name', 'connection__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DataSourceTable)
class DataSourceTableAdmin(admin.ModelAdmin):
    list_display = ['source_table_name', 'dest_table_name', 'data_source', 'sync_mode', 'is_enabled']
    list_filter = ['sync_mode', 'is_enabled']
    search_fields = ['source_table_name', 'dest_table_name', 'data_source__name']
    readonly_fields = ['created_at', 'updated_at', 'last_synced_at']


@admin.register(ETLRun)
class ETLRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'model_endpoint', 'status', 'started_at', 'completed_at', 'total_tables', 'total_rows_extracted']
    list_filter = ['status', 'created_at']
    search_fields = ['model_endpoint__name']
    readonly_fields = ['created_at']


@admin.register(PipelineConfiguration)
class PipelineConfigurationAdmin(admin.ModelAdmin):
    list_display = ['model_endpoint', 'use_gpu', 'gpu_type', 'epochs', 'batch_size']
    search_fields = ['model_endpoint__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'model_endpoint', 'status', 'current_stage', 'started_at', 'completed_at']
    list_filter = ['status', 'current_stage', 'created_at']
    search_fields = ['model_endpoint__name']
    readonly_fields = ['created_at']


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ['name', 'model_endpoint', 'recall_at_100', 'is_production', 'created_at']
    list_filter = ['is_production', 'created_at']
    search_fields = ['name', 'model_endpoint__name']
    readonly_fields = ['created_at']


@admin.register(TrainedModel)
class TrainedModelAdmin(admin.ModelAdmin):
    list_display = ['model_endpoint', 'version', 'status', 'recall_at_100', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['model_endpoint__name', 'version']
    readonly_fields = ['created_at']


@admin.register(Deployment)
class DeploymentAdmin(admin.ModelAdmin):
    list_display = ['model_endpoint', 'environment', 'status', 'is_healthy', 'deployed_at']
    list_filter = ['environment', 'status', 'is_healthy']
    search_fields = ['model_endpoint__name']
    readonly_fields = ['deployed_at']


@admin.register(PredictionLog)
class PredictionLogAdmin(admin.ModelAdmin):
    list_display = ['deployment', 'window_start', 'window_end', 'total_requests', 'total_predictions']
    list_filter = ['logged_at']
    readonly_fields = ['logged_at']


@admin.register(SystemMetrics)
class SystemMetricsAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_endpoints', 'active_endpoints', 'total_pipeline_runs', 'total_predictions']
    list_filter = ['date']
    readonly_fields = ['recorded_at']


@admin.register(FeatureConfig)
class FeatureConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'dataset', 'version', 'buyer_tensor_dim', 'product_tensor_dim', 'created_at', 'updated_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description', 'dataset__name']
    readonly_fields = ['created_at', 'updated_at', 'buyer_tensor_dim', 'product_tensor_dim']
    raw_id_fields = ['dataset', 'created_by']


@admin.register(FeatureConfigVersion)
class FeatureConfigVersionAdmin(admin.ModelAdmin):
    list_display = ['feature_config', 'version', 'buyer_tensor_dim', 'product_tensor_dim', 'created_at']
    list_filter = ['created_at']
    search_fields = ['feature_config__name']
    readonly_fields = ['created_at']
    raw_id_fields = ['feature_config', 'created_by']
