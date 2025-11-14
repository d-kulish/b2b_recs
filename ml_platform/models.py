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
    This is the parent configuration that can have multiple data sources.
    """

    SCHEDULE_CHOICES = [
        ('manual', 'Manual Only'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    model_endpoint = models.OneToOneField(ModelEndpoint, on_delete=models.CASCADE, related_name='etl_config')

    # Schedule configuration (applies to all data sources)
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_CHOICES, default='manual')
    schedule_time = models.TimeField(null=True, blank=True, help_text="Time of day to run (for daily/weekly)")
    schedule_day_of_week = models.IntegerField(null=True, blank=True, help_text="0=Monday, 6=Sunday")
    schedule_day_of_month = models.IntegerField(null=True, blank=True, help_text="Day of month (1-31)")
    schedule_cron = models.CharField(max_length=100, blank=True, help_text="Cloud Scheduler cron expression")

    # ETL settings
    is_enabled = models.BooleanField(default=False)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=50, blank=True)
    last_run_message = models.TextField(blank=True)

    # Cloud Scheduler job ID (for this client's scheduled job)
    cloud_scheduler_job_name = models.CharField(max_length=255, blank=True)
    cloud_run_service_url = models.URLField(blank=True, help_text="Cloud Run ETL service URL")

    # Data configuration
    lookback_days = models.IntegerField(default=90, help_text="Number of days of historical data to extract")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ETL Configuration'
        verbose_name_plural = 'ETL Configurations'

    def __str__(self):
        return f"ETL Config for {self.model_endpoint.name}"


class Connection(models.Model):
    """
    Reusable database/data connection.
    Multiple ETL jobs can share the same connection.
    This separates connection credentials from ETL job configuration.
    """

    # Organized by category for UI display
    SOURCE_TYPE_CHOICES = [
        # Relational Databases
        ('postgresql', 'PostgreSQL'),
        ('mysql', 'MySQL'),
        ('oracle', 'Oracle Database'),
        ('sqlserver', 'Microsoft SQL Server'),
        ('db2', 'IBM DB2'),
        ('redshift', 'Amazon Redshift'),
        ('synapse', 'Azure Synapse'),
        ('bigquery', 'Google BigQuery'),
        ('snowflake', 'Snowflake'),
        ('mariadb', 'MariaDB'),
        ('teradata', 'Teradata'),
        # Flat Files
        ('csv', 'CSV Files'),
        ('parquet', 'Parquet Files'),
        ('json', 'JSON Files'),
        ('excel', 'Excel (XLS/XLSX)'),
        ('txt', 'Text Files'),
        ('avro', 'Avro Files'),
        # NoSQL Databases
        ('mongodb', 'MongoDB'),
        ('firestore', 'Google Firestore'),
        ('cassandra', 'Apache Cassandra'),
        ('dynamodb', 'Amazon DynamoDB'),
        ('redis', 'Redis'),
    ]

    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='connections')

    # Connection identification
    name = models.CharField(max_length=255, help_text="Friendly name (e.g., 'Production PostgreSQL')")
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPE_CHOICES)
    description = models.TextField(blank=True, help_text="Optional description")

    # Connection details (for database sources)
    source_host = models.CharField(max_length=255, blank=True)
    source_port = models.IntegerField(null=True, blank=True)
    source_database = models.CharField(max_length=255, blank=True)
    source_schema = models.CharField(max_length=255, blank=True, help_text="Database schema (optional)")
    source_username = models.CharField(max_length=255, blank=True, help_text="Database username (for deduplication)")
    credentials_secret_name = models.CharField(max_length=255, blank=True, help_text="Secret Manager secret name")

    # File upload details (for CSV/Parquet sources)
    file_path = models.CharField(max_length=512, blank=True, help_text="GCS path to uploaded file")

    # BigQuery/Firestore source details
    bigquery_project = models.CharField(max_length=255, blank=True)
    bigquery_dataset = models.CharField(max_length=255, blank=True)

    # Service Account Authentication (BigQuery, Firestore, etc.)
    service_account_json = models.TextField(blank=True, help_text="Service account JSON key (pasted)")
    service_account_file_path = models.CharField(max_length=512, blank=True, help_text="GCS path to service account JSON")

    # NoSQL connection strings
    connection_string = models.TextField(blank=True, help_text="Connection string (MongoDB, Redis, etc.)")

    # Additional connection parameters (stored as JSON for flexibility)
    connection_params = models.JSONField(default=dict, blank=True, help_text="Additional connection parameters")

    # Connection status
    is_enabled = models.BooleanField(default=True)
    connection_tested = models.BooleanField(default=False)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=20, blank=True, help_text="success or failed")
    last_test_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = [
            ['model_endpoint', 'name'],  # Unique connection names per model
            ['model_endpoint', 'source_type', 'source_host', 'source_port', 'source_database', 'source_username']  # Prevent duplicate connections
        ]
        verbose_name = 'Connection'
        verbose_name_plural = 'Connections'

    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"

    def get_dependent_jobs_count(self):
        """Returns count of ETL jobs using this connection"""
        return self.data_sources.filter(is_enabled=True).count()


class DataSource(models.Model):
    """
    Represents a single data source (database connection or file upload).
    Each ETL configuration can have multiple data sources.
    """

    # Organized by category for UI display
    SOURCE_TYPE_CHOICES = [
        # Relational Databases
        ('postgresql', 'PostgreSQL'),
        ('mysql', 'MySQL'),
        ('oracle', 'Oracle Database'),
        ('sqlserver', 'Microsoft SQL Server'),
        ('db2', 'IBM DB2'),
        ('redshift', 'Amazon Redshift'),
        ('synapse', 'Azure Synapse'),
        ('bigquery', 'Google BigQuery'),
        ('snowflake', 'Snowflake'),
        ('mariadb', 'MariaDB'),
        ('teradata', 'Teradata'),
        # Flat Files
        ('csv', 'CSV Files'),
        ('parquet', 'Parquet Files'),
        ('json', 'JSON Files'),
        ('excel', 'Excel (XLS/XLSX)'),
        ('txt', 'Text Files'),
        ('avro', 'Avro Files'),
        # NoSQL Databases
        ('mongodb', 'MongoDB'),
        ('firestore', 'Google Firestore'),
        ('cassandra', 'Apache Cassandra'),
        ('dynamodb', 'Amazon DynamoDB'),
        ('redis', 'Redis'),
    ]

    etl_config = models.ForeignKey(ETLConfiguration, on_delete=models.CASCADE, related_name='data_sources')

    # NEW: Reference to reusable Connection
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT, null=True, blank=True, related_name='data_sources',
                                    help_text="Reusable connection (new architecture)")

    # Source identification
    name = models.CharField(max_length=255, help_text="Friendly name (e.g., 'Main Transaction DB')")
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPE_CHOICES)

    # DEPRECATED: Direct connection fields (kept for backward compatibility during migration)
    # These will be removed once all DataSources use Connection model
    source_host = models.CharField(max_length=255, blank=True, null=True)
    source_port = models.IntegerField(null=True, blank=True)
    source_database = models.CharField(max_length=255, blank=True, null=True)
    source_schema = models.CharField(max_length=255, blank=True, null=True, help_text="Database schema (optional)")
    credentials_secret_name = models.CharField(max_length=255, blank=True, null=True, help_text="Secret Manager secret name")

    # File upload details (for CSV/Parquet sources)
    file_path = models.CharField(max_length=512, blank=True, help_text="GCS path to uploaded file")

    # BigQuery/Firestore source details
    bigquery_project = models.CharField(max_length=255, blank=True)
    bigquery_dataset = models.CharField(max_length=255, blank=True)

    # Service Account Authentication (BigQuery, Firestore, etc.)
    service_account_json = models.TextField(blank=True, help_text="Service account JSON key (pasted)")
    service_account_file_path = models.CharField(max_length=512, blank=True, help_text="GCS path to service account JSON")

    # NoSQL connection strings
    connection_string = models.TextField(blank=True, help_text="Connection string (MongoDB, Redis, etc.)")

    # Additional connection parameters (stored as JSON for flexibility)
    connection_params = models.JSONField(default=dict, blank=True, help_text="Additional connection parameters")

    # Source settings
    is_enabled = models.BooleanField(default=True)
    connection_tested = models.BooleanField(default=False)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_message = models.TextField(blank=True)

    # Extraction settings
    use_incremental = models.BooleanField(default=False, help_text="Use incremental extraction")
    incremental_column = models.CharField(max_length=100, blank=True, help_text="Column for incremental loads (e.g., updated_at)")

    # Wizard state tracking
    wizard_last_step = models.IntegerField(default=1, help_text="Last wizard step user completed")
    wizard_completed_steps = models.JSONField(default=list, blank=True, help_text="List of completed step numbers [1,2,3]")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['etl_config', 'name']  # Ensure unique ETL job names per model
        verbose_name = 'Data Source'
        verbose_name_plural = 'Data Sources'

    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"

    def get_connection_details(self):
        """
        Returns connection details from either Connection FK or direct fields.
        Supports both old and new architecture during migration.
        """
        if self.connection:
            # New architecture: use Connection model
            return {
                'source_type': self.connection.source_type,
                'host': self.connection.source_host,
                'port': self.connection.source_port,
                'database': self.connection.source_database,
                'schema': self.connection.source_schema,
                'credentials_secret_name': self.connection.credentials_secret_name,
                'bigquery_project': self.connection.bigquery_project,
                'bigquery_dataset': self.connection.bigquery_dataset,
                'connection_string': self.connection.connection_string,
                'file_path': self.connection.file_path,
            }
        else:
            # Old architecture: use direct fields
            return {
                'source_type': self.source_type,
                'host': self.source_host,
                'port': self.source_port,
                'database': self.source_database,
                'schema': self.source_schema,
                'credentials_secret_name': self.credentials_secret_name,
                'bigquery_project': self.bigquery_project,
                'bigquery_dataset': self.bigquery_dataset,
                'connection_string': self.connection_string,
                'file_path': self.file_path,
            }

    def uses_connection_model(self):
        """Returns True if this DataSource uses the new Connection model"""
        return self.connection is not None


class DataSourceTable(models.Model):
    """
    Represents a table/file to extract from a data source.
    Each data source can have multiple tables configured.
    """

    SYNC_MODE_CHOICES = [
        ('replace', 'Replace All (Full Refresh)'),
        ('append', 'Append New Records'),
        ('incremental', 'Incremental (Date-based)'),
    ]

    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name='tables')

    # Source table configuration
    source_table_name = models.CharField(max_length=255, help_text="Table name in source database")
    source_query = models.TextField(blank=True, help_text="Optional: custom SQL query instead of table name")

    # Destination configuration
    dest_table_name = models.CharField(max_length=255, help_text="Table name in BigQuery (e.g., 'transactions')")
    dest_dataset = models.CharField(max_length=255, default='raw_data', help_text="BigQuery dataset name")

    # Sync configuration
    sync_mode = models.CharField(max_length=20, choices=SYNC_MODE_CHOICES, default='replace')
    incremental_column = models.CharField(max_length=100, blank=True, help_text="Column for incremental sync")
    last_sync_value = models.CharField(max_length=255, blank=True, help_text="Last synced value (for incremental)")

    # Table settings
    is_enabled = models.BooleanField(default=True)
    row_limit = models.IntegerField(null=True, blank=True, help_text="Optional: limit rows for testing")

    # Statistics
    last_row_count = models.IntegerField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source_table_name']
        unique_together = ['data_source', 'source_table_name']
        verbose_name = 'Data Source Table'
        verbose_name_plural = 'Data Source Tables'

    def __str__(self):
        return f"{self.source_table_name} → {self.dest_table_name}"


class ETLRun(models.Model):
    """
    History of ETL job executions.
    Tracks execution of all data sources and tables in a single run.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('partial', 'Partially Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    etl_config = models.ForeignKey(ETLConfiguration, on_delete=models.CASCADE, related_name='runs')
    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='etl_runs')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Job details
    cloud_run_execution_id = models.CharField(max_length=255, blank=True, help_text="Cloud Run Job execution ID")

    # Results summary
    total_sources = models.IntegerField(default=0, help_text="Total data sources processed")
    successful_sources = models.IntegerField(default=0)
    total_tables = models.IntegerField(default=0, help_text="Total tables processed")
    successful_tables = models.IntegerField(default=0)
    total_rows_extracted = models.BigIntegerField(default=0)

    # Detailed results (JSON structure with per-table results)
    results_detail = models.JSONField(default=dict, help_text="Detailed results per source and table")
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

    def get_duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


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
