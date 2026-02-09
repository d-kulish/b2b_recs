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
    ResourceMetrics,
    ProjectMetrics,
    FeatureConfig,
    FeatureConfigVersion,
    ModelConfig,
    BillingConfig,
    BillingSnapshot,
)
from ml_platform.training.models import TrainingRun


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


@admin.register(ResourceMetrics)
class ResourceMetricsAdmin(admin.ModelAdmin):
    list_display = ('date', 'bq_total_bytes', 'cloud_run_active_services', 'db_size_bytes', 'gcs_total_bytes', 'gpu_training_hours', 'gpu_jobs_completed')
    list_filter = ('date',)
    readonly_fields = ('created_at',)


@admin.register(ProjectMetrics)
class ProjectMetricsAdmin(admin.ModelAdmin):
    list_display = ('date', 'model_endpoint', 'total_requests', 'error_count', 'latency_p95_ms')
    list_filter = ('date', 'model_endpoint')
    readonly_fields = ('created_at',)


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


@admin.register(ModelConfig)
class ModelConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'model_endpoint', 'model_type', 'get_buyer_tower_summary', 'get_product_tower_summary',
                    'output_embedding_dim', 'optimizer', 'epochs', 'created_at']
    list_filter = ['model_endpoint', 'model_type', 'optimizer', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['created_by', 'model_endpoint']
    fieldsets = (
        ('Project', {
            'fields': ('model_endpoint',)
        }),
        ('Basic Info', {
            'fields': ('name', 'description', 'model_type')
        }),
        ('Tower Architecture', {
            'fields': ('buyer_tower_layers', 'product_tower_layers', 'output_embedding_dim',
                       'share_tower_weights', 'rating_head_layers'),
            'classes': ('collapse',),
        }),
        ('Training Hyperparameters', {
            'fields': ('optimizer', 'learning_rate', 'batch_size', 'epochs'),
        }),
        ('Multitask Settings', {
            'fields': ('retrieval_weight', 'ranking_weight'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
        }),
    )


@admin.register(TrainingRun)
class TrainingRunAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'run_number',
        'status',
        'model_type',
        'is_blessed',
        'get_primary_metric',
        'ml_model',
        'created_at'
    ]
    list_filter = [
        'status',
        'model_type',
        'is_blessed',
        'created_at'
    ]
    search_fields = [
        'name',
        'description',
        'vertex_pipeline_job_name',
        'ml_model__name'
    ]
    readonly_fields = [
        'run_number',
        'created_at',
        'updated_at',
        'started_at',
        'completed_at',
        'duration_seconds',
        'progress_percent',
        'current_stage',
        'current_epoch'
    ]
    raw_id_fields = [
        'ml_model',
        'base_experiment',
        'dataset',
        'feature_config',
        'model_config',
        'created_by'
    ]
    fieldsets = (
        ('Basic Info', {
            'fields': (
                'name',
                'run_number',
                'description',
                'model_type',
                'ml_model',
                'base_experiment'
            )
        }),
        ('Configuration', {
            'fields': (
                'dataset',
                'feature_config',
                'model_config',
                'training_params',
                'gpu_config',
                'evaluator_config',
                'deployment_config'
            ),
            'classes': ('collapse',),
        }),
        ('Status & Progress', {
            'fields': (
                'status',
                'current_stage',
                'current_epoch',
                'total_epochs',
                'progress_percent',
                'stage_details'
            )
        }),
        ('Metrics - Retrieval', {
            'fields': (
                'loss',
                'recall_at_5',
                'recall_at_10',
                'recall_at_50',
                'recall_at_100'
            ),
            'classes': ('collapse',),
        }),
        ('Metrics - Ranking', {
            'fields': (
                'rmse',
                'mae',
                'test_rmse',
                'test_mae'
            ),
            'classes': ('collapse',),
        }),
        ('Pipeline', {
            'fields': (
                'cloud_build_id',
                'cloud_build_run_id',
                'vertex_pipeline_job_name',
                'gcs_artifacts_path'
            ),
            'classes': ('collapse',),
        }),
        ('Model Registry', {
            'fields': (
                'is_blessed',
                'evaluation_results',
                'vertex_model_name',
                'vertex_model_version',
                'vertex_model_resource_name'
            ),
            'classes': ('collapse',),
        }),
        ('Artifacts', {
            'fields': (
                'artifacts',
                'training_history_json'
            ),
            'classes': ('collapse',),
        }),
        ('Errors', {
            'fields': (
                'error_message',
                'error_stage',
                'error_details'
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': (
                'created_by',
                'created_at',
                'updated_at',
                'started_at',
                'completed_at',
                'scheduled_at',
                'duration_seconds'
            )
        }),
    )

    def get_primary_metric(self, obj):
        """Display primary metric based on model type."""
        if obj.model_type == 'ranking':
            if obj.rmse is not None:
                return f"RMSE: {obj.rmse:.4f}"
            return '-'
        else:
            if obj.recall_at_100 is not None:
                return f"R@100: {obj.recall_at_100:.3f}"
            return '-'
    get_primary_metric.short_description = 'Primary Metric'


@admin.register(BillingConfig)
class BillingConfigAdmin(admin.ModelAdmin):
    list_display = ('license_fee', 'license_discount_pct', 'default_margin_pct', 'gpu_margin_pct', 'client_project_id')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Pricing', {
            'fields': ('license_fee', 'license_discount_pct', 'default_margin_pct', 'gpu_margin_pct')
        }),
        ('GCP Billing Export', {
            'fields': ('billing_export_project', 'billing_export_dataset', 'client_project_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def has_add_permission(self, request):
        """Only allow one BillingConfig (singleton)."""
        return not BillingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BillingSnapshot)
class BillingSnapshotAdmin(admin.ModelAdmin):
    list_display = ('date', 'service_name', 'gcp_cost', 'margin_pct', 'platform_fee', 'total_cost')
    list_filter = ('date', 'service_name')
    readonly_fields = ('created_at',)
    ordering = ('-date', 'service_name')
