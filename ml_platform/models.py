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
        # Cloud Storage (Storage-first approach: connection = bucket access, file type selected during ETL)
        ('gcs', 'Google Cloud Storage'),
        ('s3', 'AWS S3'),
        ('azure_blob', 'Azure Blob Storage'),
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

    # Cloud Storage details (GCS, S3, Azure Blob)
    bucket_path = models.CharField(max_length=512, blank=True, help_text="Bucket/container path (gs://, s3://, https://)")

    # File upload details (legacy - for uploaded files)
    file_path = models.CharField(max_length=512, blank=True, help_text="File path within bucket")

    # BigQuery/Firestore source details
    bigquery_project = models.CharField(max_length=255, blank=True)
    bigquery_dataset = models.CharField(max_length=255, blank=True)

    # GCS Authentication (Google Cloud Storage, BigQuery, Firestore)
    service_account_json = models.TextField(blank=True, help_text="Service account JSON key (pasted)")
    service_account_file_path = models.CharField(max_length=512, blank=True, help_text="GCS path to service account JSON")

    # AWS S3 Authentication
    aws_access_key_id = models.CharField(max_length=255, blank=True, help_text="AWS Access Key ID")
    aws_secret_access_key_secret = models.CharField(max_length=255, blank=True, help_text="Secret Manager path for AWS Secret Access Key")
    aws_region = models.CharField(max_length=50, blank=True, default='us-east-1', help_text="AWS region")

    # Azure Blob Storage Authentication
    azure_storage_account = models.CharField(max_length=255, blank=True, help_text="Azure storage account name")
    azure_account_key_secret = models.CharField(max_length=255, blank=True, help_text="Secret Manager path for Azure account key")
    azure_sas_token_secret = models.CharField(max_length=255, blank=True, help_text="Secret Manager path for SAS token (alternative to account key)")

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

    # Usage tracking
    last_used_at = models.DateTimeField(null=True, blank=True, help_text="Last time this connection was used by an ETL job")

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
    Represents a single ETL job that extracts data from a Connection.
    Each ETL configuration can have multiple ETL jobs (data sources).
    """

    etl_config = models.ForeignKey(ETLConfiguration, on_delete=models.CASCADE, related_name='data_sources')

    # Reference to reusable Connection (will be required after data cleanup)
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT, null=True, blank=True, related_name='data_sources',
                                    help_text="Database connection used by this ETL job")

    # ETL Job identification
    name = models.CharField(max_length=255, help_text="ETL job name (e.g., 'Daily Transactions Extract')")

    # Denormalized from connection for quick filtering/display
    source_type = models.CharField(max_length=50, blank=True, help_text="Source type (copied from connection)")

    # Job settings
    is_enabled = models.BooleanField(default=True, help_text="Enable/disable this ETL job")

    # Schedule settings (Phase 2)
    SCHEDULE_CHOICES = [
        ('manual', 'Manual Only'),
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_CHOICES, default='manual', help_text="ETL run schedule")
    cloud_scheduler_job_name = models.CharField(max_length=500, blank=True, help_text="Cloud Scheduler job name (full path)")

    # Extraction settings
    use_incremental = models.BooleanField(default=False, help_text="Use incremental extraction")
    incremental_column = models.CharField(max_length=100, blank=True, help_text="Column for incremental loads (e.g., updated_at)")
    last_sync_value = models.CharField(max_length=255, blank=True, help_text="Last synced value for incremental loads")
    historical_start_date = models.DateField(null=True, blank=True, help_text="Start date for historical backfill")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['etl_config', 'name']  # Ensure unique ETL job names per model
        verbose_name = 'Data Source'
        verbose_name_plural = 'Data Sources'

    def __str__(self):
        return f"{self.name} (via {self.connection.name})"

    def save(self, *args, **kwargs):
        """Auto-populate source_type from connection on save"""
        if self.connection:
            self.source_type = self.connection.source_type
        super().save(*args, **kwargs)


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
    schema_name = models.CharField(max_length=255, blank=True, help_text="Schema name (for databases that support schemas)")
    source_table_name = models.CharField(max_length=255, help_text="Table name in source database")
    source_query = models.TextField(blank=True, help_text="Optional: custom SQL query instead of table name")

    # Destination configuration
    dest_table_name = models.CharField(max_length=255, help_text="Table name in BigQuery (e.g., 'transactions')")
    dest_dataset = models.CharField(max_length=255, default='raw_data', help_text="BigQuery dataset name")

    # Sync configuration (DEPRECATED - replaced by load_type)
    sync_mode = models.CharField(max_length=20, choices=SYNC_MODE_CHOICES, default='replace')
    incremental_column = models.CharField(max_length=100, blank=True, help_text="Column for incremental sync")
    last_sync_value = models.CharField(max_length=255, blank=True, help_text="Last synced value (for incremental)")

    # Load Strategy Configuration (NEW)
    LOAD_TYPE_CHOICES = [
        ('transactional', 'Transactional (Append-Only)'),
        ('catalog', 'Catalog (Daily Snapshot)'),
    ]

    load_type = models.CharField(
        max_length=20,
        choices=LOAD_TYPE_CHOICES,
        default='transactional',
        help_text="Type of data load strategy"
    )

    # Transactional load configuration
    timestamp_column = models.CharField(
        max_length=100,
        blank=True,
        help_text="Column used to track incremental changes (e.g., created_at, updated_at)"
    )
    historical_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date for historical backfill (optional)"
    )

    # Column selection
    selected_columns = models.JSONField(
        default=list,
        blank=True,
        help_text="List of column names to sync (empty = all columns)"
    )

    # Cloud Storage File Configuration (for GCS, S3, Azure Blob)
    is_file_based = models.BooleanField(
        default=False,
        help_text="True if source is cloud storage files (GCS/S3/Azure), False for databases"
    )
    file_path_prefix = models.CharField(
        max_length=500,
        blank=True,
        help_text="Folder path prefix for file search (e.g., 'data/transactions/')"
    )
    file_pattern = models.CharField(
        max_length=200,
        blank=True,
        help_text="File pattern using glob syntax (e.g., '*.csv', 'data_*.parquet')"
    )
    file_format = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('csv', 'CSV'),
            ('parquet', 'Parquet'),
            ('json', 'JSON/JSONL'),
        ],
        help_text="File format for cloud storage sources"
    )
    file_format_options = models.JSONField(
        default=dict,
        blank=True,
        help_text="Format-specific options (e.g., CSV delimiter, encoding, has_header)"
    )
    load_latest_only = models.BooleanField(
        default=True,
        help_text="If True, load only the latest unprocessed file. If False, load all unprocessed files."
    )
    schema_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        help_text="MD5 hash of column names + types for schema validation"
    )
    column_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Mapping of original column names to sanitized BigQuery column names (e.g., {'DiscountApplied(%)': 'discountapplied'})"
    )
    selected_files = models.JSONField(
        default=list,
        blank=True,
        help_text="List of specific file paths selected by user to include in ETL (empty = use pattern only)"
    )

    # Schedule configuration
    SCHEDULE_TYPE_CHOICES = [
        ('manual', 'Manual Only'),
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('custom', 'Custom (cron)'),
    ]

    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPE_CHOICES,
        default='manual',
        help_text="Schedule frequency"
    )
    schedule_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Time of day for daily/weekly/monthly schedules"
    )
    schedule_day_of_week = models.IntegerField(
        null=True,
        blank=True,
        help_text="Day of week for weekly schedules (0=Monday, 6=Sunday)"
    )
    schedule_day_of_month = models.IntegerField(
        null=True,
        blank=True,
        help_text="Day of month for monthly schedules (1-31)"
    )
    schedule_cron = models.CharField(
        max_length=100,
        blank=True,
        help_text="Custom cron expression"
    )
    schedule_minute = models.IntegerField(
        null=True,
        blank=True,
        help_text="Minute for hourly schedules (0-59)"
    )
    schedule_timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="Timezone for schedule (auto-detected from user's browser)"
    )

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

    # Detailed progress tracking (Phase 3)
    extraction_started_at = models.DateTimeField(null=True, blank=True, help_text="When data extraction started")
    extraction_completed_at = models.DateTimeField(null=True, blank=True, help_text="When data extraction completed")
    loading_started_at = models.DateTimeField(null=True, blank=True, help_text="When data loading started")
    loading_completed_at = models.DateTimeField(null=True, blank=True, help_text="When data loading completed")

    # Results summary
    total_sources = models.IntegerField(default=0, help_text="Total data sources processed")
    successful_sources = models.IntegerField(default=0)
    total_tables = models.IntegerField(default=0, help_text="Total tables processed")
    successful_tables = models.IntegerField(default=0)
    total_rows_extracted = models.BigIntegerField(default=0)
    rows_loaded = models.BigIntegerField(default=0, help_text="Total rows loaded to BigQuery")
    bytes_processed = models.BigIntegerField(default=0, help_text="Total bytes processed")
    duration_seconds = models.IntegerField(null=True, blank=True, help_text="Total duration in seconds")

    # Detailed results (JSON structure with per-table results)
    results_detail = models.JSONField(default=dict, help_text="Detailed results per source and table")
    error_message = models.TextField(blank=True)
    logs_url = models.URLField(blank=True, help_text="Cloud Run logs URL")

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


class ProcessedFile(models.Model):
    """
    Track which files from cloud storage have been successfully processed.
    Used for file-based ETL jobs to avoid reprocessing the same files.
    """
    data_source_table = models.ForeignKey(
        DataSourceTable,
        on_delete=models.CASCADE,
        related_name='processed_files',
        help_text="The ETL job that processed this file"
    )
    file_path = models.CharField(
        max_length=1000,
        help_text="Full path to the file in cloud storage (e.g., 'data/transactions/file.csv')"
    )
    file_size_bytes = models.BigIntegerField(help_text="File size in bytes")
    file_last_modified = models.DateTimeField(help_text="Last modified timestamp from cloud storage")

    # Processing details
    processed_at = models.DateTimeField(auto_now_add=True, help_text="When this file was successfully loaded")
    rows_loaded = models.IntegerField(null=True, blank=True, help_text="Number of rows loaded from this file")
    etl_run = models.ForeignKey(
        ETLRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_files',
        help_text="The ETL run that processed this file"
    )

    class Meta:
        ordering = ['-processed_at']
        unique_together = ['data_source_table', 'file_path']
        verbose_name = 'Processed File'
        verbose_name_plural = 'Processed Files'
        indexes = [
            models.Index(fields=['data_source_table', 'file_path']),
            models.Index(fields=['processed_at']),
        ]

    def __str__(self):
        return f"{self.file_path} (processed {self.processed_at.strftime('%Y-%m-%d %H:%M')})"


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
