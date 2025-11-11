from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ModelEndpoint(models.Model):
    """
    Represents a complete ML project/pipeline instance.
    Each ModelEndpoint is a separate recommendation system that can be trained and deployed.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    ]

    # Basic information
    name = models.CharField(max_length=255, unique=True, help_text="Unique name for this model/endpoint")
    description = models.TextField(blank=True, help_text="Description of this model's purpose")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # GCP Configuration
    gcp_project_id = models.CharField(max_length=255, blank=True, help_text="GCP project ID for this model")
    gcp_region = models.CharField(max_length=100, default='us-central1')
    bigquery_dataset = models.CharField(max_length=255, blank=True, help_text="Main BigQuery dataset name")
    gcs_bucket = models.CharField(max_length=255, blank=True, help_text="GCS bucket for artifacts")

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_models')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_trained_at = models.DateTimeField(null=True, blank=True)
    last_deployed_at = models.DateTimeField(null=True, blank=True)

    # Endpoint information
    endpoint_url = models.URLField(blank=True, help_text="Production endpoint URL")
    is_endpoint_active = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Model/Endpoint'
        verbose_name_plural = 'Models/Endpoints'

    def __str__(self):
        return self.name


class ETLConfiguration(models.Model):
    """
    ETL configuration for extracting data from source systems to BigQuery.
    """

    SCHEDULE_CHOICES = [
        ('manual', 'Manual Only'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    SOURCE_TYPE_CHOICES = [
        ('postgresql', 'PostgreSQL'),
        ('mysql', 'MySQL'),
        ('sqlserver', 'SQL Server'),
        ('bigquery', 'BigQuery'),
        ('other', 'Other'),
    ]

    model_endpoint = models.OneToOneField(ModelEndpoint, on_delete=models.CASCADE, related_name='etl_config')

    # Source configuration
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPE_CHOICES)
    source_host = models.CharField(max_length=255, blank=True)
    source_port = models.IntegerField(null=True, blank=True)
    source_database = models.CharField(max_length=255, blank=True)
    source_credentials_secret = models.CharField(max_length=255, blank=True, help_text="Secret Manager secret name")

    # Schedule configuration
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_CHOICES, default='manual')
    schedule_time = models.TimeField(null=True, blank=True, help_text="Time of day to run (for daily/weekly)")
    schedule_day_of_week = models.IntegerField(null=True, blank=True, help_text="0=Monday, 6=Sunday")
    schedule_day_of_month = models.IntegerField(null=True, blank=True, help_text="Day of month (1-31)")

    # ETL settings
    is_enabled = models.BooleanField(default=False)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=50, blank=True)
    last_run_message = models.TextField(blank=True)

    # Data configuration
    lookback_days = models.IntegerField(default=90, help_text="Number of days of historical data to extract")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ETL Configuration'
        verbose_name_plural = 'ETL Configurations'

    def __str__(self):
        return f"ETL Config for {self.model_endpoint.name}"


class ETLRun(models.Model):
    """
    History of ETL job executions.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    etl_config = models.ForeignKey(ETLConfiguration, on_delete=models.CASCADE, related_name='runs')
    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='etl_runs')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Job details
    vertex_job_id = models.CharField(max_length=255, blank=True)
    cloud_run_job_id = models.CharField(max_length=255, blank=True)

    # Results
    rows_extracted = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    logs_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'ETL Run'
        verbose_name_plural = 'ETL Runs'

    def __str__(self):
        return f"ETL Run {self.id} - {self.model_endpoint.name} ({self.status})"


class PipelineConfiguration(models.Model):
    """
    ML pipeline configuration and parameters.
    """

    model_endpoint = models.OneToOneField(ModelEndpoint, on_delete=models.CASCADE, related_name='pipeline_config')

    # Data extraction parameters
    top_revenue_percentile = models.FloatField(default=0.8, help_text="Filter products by top X% revenue")
    min_transactions = models.IntegerField(default=10, help_text="Minimum transactions per customer")

    # Training parameters
    embedding_dim = models.IntegerField(default=128)
    batch_size = models.IntegerField(default=8192)
    epochs = models.IntegerField(default=3)
    learning_rate = models.FloatField(default=0.1)

    # Hardware configuration
    use_gpu = models.BooleanField(default=True)
    gpu_type = models.CharField(max_length=50, default='nvidia-tesla-t4')
    gpu_count = models.IntegerField(default=4)
    machine_type = models.CharField(max_length=50, default='n1-standard-32')
    use_preemptible = models.BooleanField(default=False, help_text="Use preemptible instances to reduce costs")

    # Feature configuration
    features_enabled = models.JSONField(default=dict, help_text="Which features to use in training")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pipeline Configuration'
        verbose_name_plural = 'Pipeline Configurations'

    def __str__(self):
        return f"Pipeline Config for {self.model_endpoint.name}"


class PipelineRun(models.Model):
    """
    Execution history of the complete ML pipeline (all 4 stages).
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    STAGE_CHOICES = [
        ('data_extraction', 'Data Extraction'),
        ('vocab_building', 'Vocabulary Building'),
        ('training', 'Training'),
        ('deployment', 'Deployment'),
    ]

    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='pipeline_runs')
    pipeline_config = models.ForeignKey(PipelineConfiguration, on_delete=models.SET_NULL, null=True, blank=True)

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    current_stage = models.CharField(max_length=50, choices=STAGE_CHOICES, blank=True)

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Stage timings
    data_extraction_started = models.DateTimeField(null=True, blank=True)
    data_extraction_completed = models.DateTimeField(null=True, blank=True)
    vocab_building_started = models.DateTimeField(null=True, blank=True)
    vocab_building_completed = models.DateTimeField(null=True, blank=True)
    training_started = models.DateTimeField(null=True, blank=True)
    training_completed = models.DateTimeField(null=True, blank=True)
    deployment_started = models.DateTimeField(null=True, blank=True)
    deployment_completed = models.DateTimeField(null=True, blank=True)

    # Results
    error_message = models.TextField(blank=True)
    artifacts_path = models.CharField(max_length=512, blank=True, help_text="GCS path to artifacts")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pipeline Run'
        verbose_name_plural = 'Pipeline Runs'

    def __str__(self):
        return f"Pipeline Run {self.id} - {self.model_endpoint.name} ({self.status})"

    def get_duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class Experiment(models.Model):
    """
    MLflow experiment tracking.
    """

    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='experiments')
    pipeline_run = models.OneToOneField(PipelineRun, on_delete=models.CASCADE, null=True, blank=True, related_name='experiment')

    # MLflow identifiers
    mlflow_experiment_id = models.CharField(max_length=255, blank=True)
    mlflow_run_id = models.CharField(max_length=255, blank=True)

    # Experiment details
    name = models.CharField(max_length=255)

    # Metrics (stored for quick access)
    recall_at_5 = models.FloatField(null=True, blank=True)
    recall_at_10 = models.FloatField(null=True, blank=True)
    recall_at_50 = models.FloatField(null=True, blank=True)
    recall_at_100 = models.FloatField(null=True, blank=True)
    training_loss = models.FloatField(null=True, blank=True)

    # Parameters snapshot
    parameters = models.JSONField(default=dict)

    # Tags
    tags = models.JSONField(default=dict)
    is_production = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Experiment'
        verbose_name_plural = 'Experiments'

    def __str__(self):
        return f"Experiment: {self.name}"


class TrainedModel(models.Model):
    """
    Represents a trained model version.
    """

    STATUS_CHOICES = [
        ('training', 'Training'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='trained_models')
    experiment = models.ForeignKey(Experiment, on_delete=models.SET_NULL, null=True, blank=True, related_name='models')
    pipeline_run = models.OneToOneField(PipelineRun, on_delete=models.CASCADE, null=True, blank=True, related_name='trained_model')

    # Model identification
    version = models.CharField(max_length=50, help_text="Semantic version (e.g., v1.0.0)")
    model_path = models.CharField(max_length=512, help_text="GCS path to saved model")

    # Model artifacts
    query_model_path = models.CharField(max_length=512, blank=True)
    candidate_model_path = models.CharField(max_length=512, blank=True)
    vocabularies_path = models.CharField(max_length=512, blank=True)

    # Performance metrics
    recall_at_100 = models.FloatField(null=True, blank=True)
    training_duration_seconds = models.IntegerField(null=True, blank=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='training')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    trained_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['model_endpoint', 'version']
        verbose_name = 'Trained Model'
        verbose_name_plural = 'Trained Models'

    def __str__(self):
        return f"{self.model_endpoint.name} - {self.version}"


class Deployment(models.Model):
    """
    Deployment history and active deployments.
    """

    STATUS_CHOICES = [
        ('deploying', 'Deploying'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('failed', 'Failed'),
    ]

    ENVIRONMENT_CHOICES = [
        ('staging', 'Staging'),
        ('production', 'Production'),
    ]

    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='deployments')
    trained_model = models.ForeignKey(TrainedModel, on_delete=models.CASCADE, related_name='deployments')

    # Deployment details
    environment = models.CharField(max_length=20, choices=ENVIRONMENT_CHOICES, default='production')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='deploying')

    # Cloud Run details
    cloud_run_service = models.CharField(max_length=255, blank=True)
    cloud_run_revision = models.CharField(max_length=255, blank=True)
    endpoint_url = models.URLField(blank=True)

    # Traffic management
    traffic_percentage = models.IntegerField(default=100, help_text="Percentage of traffic to this deployment")

    # Health and monitoring
    health_check_url = models.URLField(blank=True)
    is_healthy = models.BooleanField(default=False)
    last_health_check = models.DateTimeField(null=True, blank=True)

    # Timing
    deployed_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    deployed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-deployed_at']
        verbose_name = 'Deployment'
        verbose_name_plural = 'Deployments'

    def __str__(self):
        return f"{self.model_endpoint.name} - {self.environment} ({self.status})"


class PredictionLog(models.Model):
    """
    Aggregate prediction statistics (not individual predictions).
    """

    deployment = models.ForeignKey(Deployment, on_delete=models.CASCADE, related_name='prediction_logs')

    # Time window
    logged_at = models.DateTimeField(auto_now_add=True)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()

    # Aggregated metrics
    total_requests = models.IntegerField(default=0)
    total_predictions = models.IntegerField(default=0)
    avg_latency_ms = models.FloatField(null=True, blank=True)
    error_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-logged_at']
        verbose_name = 'Prediction Log'
        verbose_name_plural = 'Prediction Logs'

    def __str__(self):
        return f"Predictions: {self.deployment.model_endpoint.name} ({self.window_start} - {self.window_end})"


class SystemMetrics(models.Model):
    """
    System-wide metrics for the dashboard.
    """

    # Time window
    recorded_at = models.DateTimeField(auto_now_add=True)
    date = models.DateField()

    # Aggregate metrics
    total_endpoints = models.IntegerField(default=0)
    active_endpoints = models.IntegerField(default=0)
    total_pipeline_runs = models.IntegerField(default=0)
    successful_runs = models.IntegerField(default=0)
    total_predictions = models.BigIntegerField(default=0)

    # Costs (if available)
    total_compute_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_storage_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['date']
        verbose_name = 'System Metrics'
        verbose_name_plural = 'System Metrics'

    def __str__(self):
        return f"System Metrics: {self.date}"
