from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ModelEndpoint(models.Model):
    """
    Root project entity. Represents an isolated ML project workspace.
    Called "Project" in the UI. All other entities (datasets, configs,
    training runs, endpoints) are scoped to this.
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

    # Last run tracking
    last_run_at = models.DateTimeField(null=True, blank=True, help_text="When this job last ran")
    last_run_status = models.CharField(max_length=50, blank=True, help_text="Status of last run (completed, failed, etc.)")
    last_run_message = models.TextField(blank=True, help_text="Error message or summary from last run")

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

    def get_connection_details(self):
        """
        Returns connection details from the associated Connection.
        Used by API endpoints to retrieve connection info for editing.
        """
        if self.connection:
            return {
                'host': self.connection.source_host or '',
                'port': self.connection.source_port,
                'database': self.connection.source_database or '',
                'schema': self.connection.source_schema or '',
                'username': self.connection.source_username or '',
                'bigquery_project': self.connection.bigquery_project or '',
                'bigquery_dataset': self.connection.bigquery_dataset or '',
                'bucket_path': self.connection.bucket_path or '',
                'file_path': self.connection.file_path or '',
                'connection_string': self.connection.connection_string or '',
                'source_type': self.connection.source_type or '',
            }
        # Fallback for legacy data sources without Connection
        return {
            'host': '',
            'port': None,
            'database': '',
            'schema': '',
            'username': '',
            'bigquery_project': '',
            'bigquery_dataset': '',
            'bucket_path': '',
            'file_path': '',
            'connection_string': '',
            'source_type': self.source_type or '',
        }


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

    # Processing mode configuration (for conditional Dataflow usage)
    PROCESSING_MODE_CHOICES = [
        ('auto', 'Auto-detect (based on row count)'),
        ('standard', 'Standard (Cloud Run, < 1M rows)'),
        ('dataflow', 'Dataflow (large-scale, >= 1M rows)'),
    ]

    processing_mode = models.CharField(
        max_length=20,
        choices=PROCESSING_MODE_CHOICES,
        default='auto',
        help_text="Processing engine selection: auto-detect, standard (pandas), or dataflow (Apache Beam)"
    )
    row_count_threshold = models.IntegerField(
        default=1_000_000,
        help_text="Threshold for switching to Dataflow when processing_mode='auto' (default: 1 million rows)"
    )
    estimated_row_count = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Last estimated row count from most recent ETL run (used for planning/display)"
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

    ERROR_TYPE_CHOICES = [
        ('init', 'Initialization'),
        ('validation', 'Validation'),
        ('extraction', 'Extraction'),
        ('load', 'Load'),
        ('unknown', 'Unknown'),
    ]

    etl_config = models.ForeignKey(ETLConfiguration, on_delete=models.CASCADE, related_name='runs')
    model_endpoint = models.ForeignKey(ModelEndpoint, on_delete=models.CASCADE, related_name='etl_runs')
    data_source = models.ForeignKey(
        'DataSource',
        on_delete=models.CASCADE,
        related_name='runs',
        null=True,
        blank=True,
        help_text="The specific data source this run is for"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_type = models.CharField(
        max_length=20,
        choices=ERROR_TYPE_CHOICES,
        blank=True,
        help_text="Type of error that caused failure (init, validation, extraction, load)"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Job details
    cloud_run_execution_id = models.CharField(max_length=255, blank=True, help_text="Cloud Run Job execution ID")
    cloud_run_execution_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cloud Run Job execution name (e.g., 'etl-runner-abc123') for log queries"
    )
    dataflow_job_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Dataflow job ID for large-scale ETL runs (used for accurate status tracking)"
    )

    # Detailed progress tracking (4-stage pipeline: INIT → VALIDATE → EXTRACT → LOAD)
    init_completed_at = models.DateTimeField(null=True, blank=True, help_text="When initialization/config loading completed")
    validation_completed_at = models.DateTimeField(null=True, blank=True, help_text="When BigQuery table validation completed")
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


class ResourceMetrics(models.Model):
    """Daily snapshot of GCP resource usage for dashboard charts."""
    date = models.DateField(db_index=True)

    # BigQuery metrics
    bq_total_bytes = models.BigIntegerField(default=0, help_text="Total BQ storage in bytes")
    bq_table_details = models.JSONField(default=list, help_text="Per-table breakdown [{name, bytes, rows}]")
    bq_jobs_completed = models.IntegerField(default=0)
    bq_jobs_failed = models.IntegerField(default=0)
    bq_bytes_billed = models.BigIntegerField(default=0, help_text="Total bytes billed by BQ jobs")

    # Cloud Run metrics
    cloud_run_services = models.JSONField(default=list, help_text="[{name, status, is_ml_serving}]")
    cloud_run_active_services = models.IntegerField(default=0)
    cloud_run_total_requests = models.IntegerField(default=0, help_text="Total ML serving requests on this day")
    cloud_run_request_details = models.JSONField(default=list, help_text="[{name, requests, errors}]")

    # Database (Cloud SQL / PostgreSQL) metrics
    db_size_bytes = models.BigIntegerField(default=0, help_text="PostgreSQL database size in bytes")
    db_table_details = models.JSONField(default=list, help_text="[{name, size_bytes, row_count}]")

    # GCS Storage metrics
    gcs_bucket_details = models.JSONField(default=list, help_text="[{name, total_bytes, object_count}]")
    gcs_total_bytes = models.BigIntegerField(default=0)

    # ETL metrics (derived from ETLRun data)
    etl_jobs_completed = models.IntegerField(default=0, help_text="ETL jobs completed on this day")
    etl_jobs_failed = models.IntegerField(default=0, help_text="ETL jobs failed on this day")

    # GPU / Compute metrics (derived from TrainingRun data)
    gpu_training_hours = models.FloatField(default=0, help_text="Total GPU-hours for training jobs on this day")
    gpu_jobs_completed = models.IntegerField(default=0, help_text="Training jobs completed on this day")
    gpu_jobs_failed = models.IntegerField(default=0, help_text="Training jobs failed on this day")
    gpu_jobs_running = models.IntegerField(default=0, help_text="Training jobs running at snapshot time")
    gpu_jobs_by_type = models.JSONField(default=list, help_text="[{gpu_type, count, hours}]")

    # Collection metadata
    collection_errors = models.JSONField(default=list, blank=True, help_text="Errors from sub-collectors [{collector, error}]")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        unique_together = ['date']
        verbose_name = 'Resource Metrics'
        verbose_name_plural = 'Resource Metrics'

    def __str__(self):
        return f"Resource Metrics: {self.date}"


# =============================================================================
# DATASET DOMAIN MODELS
# =============================================================================

class Dataset(models.Model):
    """
    Defines WHAT data goes into model training.
    Does NOT define how to transform features - that's handled by Feature Engineering.

    A Dataset specifies:
    - Which BigQuery tables to use (from raw_data.*)
    - Which columns to include
    - How tables are joined
    - Data filters (date range, product/customer filters)
    - Train/eval split strategy
    """

    # Basic info
    name = models.CharField(max_length=255, help_text="Dataset name (e.g., 'Q4 2024 Training Data')")
    description = models.TextField(blank=True, help_text="Optional description of this dataset")
    model_endpoint = models.ForeignKey(
        ModelEndpoint,
        on_delete=models.CASCADE,
        related_name='datasets',
        help_text="The model this dataset belongs to"
    )

    # BigQuery location
    # IMPORTANT: BigQuery datasets are region-locked. Queries must be executed
    # in the same region where the data resides. This field stores the region
    # detected when the dataset is first created, ensuring all subsequent
    # queries use the correct location.
    bq_location = models.CharField(
        max_length=50,
        default='US',
        help_text="BigQuery region where the dataset exists (e.g., 'US', 'EU', 'europe-central2')"
    )

    # Source tables configuration
    # Primary table (required) - typically transactions
    primary_table = models.CharField(
        max_length=255,
        help_text="Primary BigQuery table (e.g., 'raw_data.transactions')"
    )

    # Secondary tables (optional) - for enrichment (products, customers)
    secondary_tables = models.JSONField(
        default=list,
        blank=True,
        help_text="List of secondary tables for joins (e.g., ['raw_data.products', 'raw_data.customers'])"
    )

    # Join configuration
    # Stores how tables are joined together
    # Example: {
    #   "raw_data.products": {"join_key": "product_id", "join_type": "left"},
    #   "raw_data.customers": {"join_key": "customer_id", "join_type": "left"}
    # }
    join_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Join configuration for secondary tables"
    )

    # Column selection
    # Stores which columns are selected from each table
    # Example: {
    #   "raw_data.transactions": ["customer_id", "product_id", "transaction_date", "amount"],
    #   "raw_data.products": ["product_id", "product_name", "category"]
    # }
    selected_columns = models.JSONField(
        default=dict,
        blank=True,
        help_text="Selected columns per table"
    )

    # Column role mapping (which columns serve which ML purpose)
    # Example: {
    #   "user_id": "customer_id",
    #   "product_id": "product_id",
    #   "timestamp": "transaction_date",
    #   "revenue": "amount"
    # }
    column_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Maps ML concepts to actual column names"
    )

    # Column display aliases (user-defined friendly names)
    # Example: {
    #   "transactions_customer_id": "customer_id",
    #   "transactions_date": "date",
    #   "products_name": "product_name"
    # }
    column_aliases = models.JSONField(
        default=dict,
        blank=True,
        help_text="Column display aliases. Maps prefixed column names to user-friendly aliases"
    )

    # Data filters
    # Example: {
    #   "date_range": {"type": "rolling", "months": 6},
    #   "product_filter": {"type": "top_revenue_percent", "value": 80},
    #   "customer_filter": {"type": "min_transactions", "value": 2}
    # }
    filters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Data filtering configuration"
    )

    # NOTE: split_config is kept for database compatibility but not actively used
    # Train/eval split is now handled by the Training domain (TFX ExampleGen)
    # This aligns with TFX architecture where data splitting is an execution-time concern
    split_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Deprecated - Train/eval split is handled by Training domain"
    )

    # Metadata (populated after analysis)
    row_count_estimate = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Estimated row count after filters"
    )
    unique_users_estimate = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated unique users after filters"
    )
    unique_products_estimate = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated unique products after filters"
    )
    date_range_start = models.DateField(
        null=True,
        blank=True,
        help_text="Actual start date of data"
    )
    date_range_end = models.DateField(
        null=True,
        blank=True,
        help_text="Actual end date of data"
    )

    # Column statistics (populated by analysis)
    # Example: {
    #   "customer_id": {"cardinality": 125234, "null_percent": 0.1},
    #   "amount": {"min": 0.5, "max": 12450, "mean": 45.67}
    # }
    column_stats = models.JSONField(
        default=dict,
        blank=True,
        help_text="Column statistics from BigQuery analysis"
    )

    # Summary snapshot from Step 4 Dataset Summary panel
    # Saved when dataset is created/updated, displayed in View modal
    # Example: {
    #   "total_rows": 8233,
    #   "filters_applied": {
    #       "dates": {"type": "rolling", "days": 30, "column": "trans_date"},
    #       "customers": {"type": "none"},
    #       "products": {"type": "multiple", "count": 2, "filters": [...]}
    #   },
    #   "column_stats": {
    #       "customers.customer_id": {"type": "INTEGER", "min": 59, "max": 999900},
    #       ...
    #   },
    #   "snapshot_at": "2024-12-07T10:30:00Z"
    # }
    summary_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dataset Summary snapshot from wizard Step 4 for View modal"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this dataset was used in training"
    )

    # Created by
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_datasets'
    )

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['model_endpoint', 'name']
        verbose_name = 'Dataset'
        verbose_name_plural = 'Datasets'

    def __str__(self):
        return self.name

    def get_all_tables(self):
        """Returns list of all tables (primary + secondary)"""
        tables = [self.primary_table]
        if self.secondary_tables:
            tables.extend(self.secondary_tables)
        return tables

    def get_all_selected_columns(self):
        """Returns flat list of all selected columns with table prefixes"""
        all_columns = []
        for table, columns in self.selected_columns.items():
            for col in columns:
                all_columns.append(f"{table}.{col}")
        return all_columns


class DatasetVersion(models.Model):
    """
    Tracks versions of a dataset for reproducibility.
    A new version is created when a dataset is used in training,
    capturing the exact configuration at that point in time.
    """

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='versions',
        help_text="The dataset this version belongs to"
    )
    version_number = models.IntegerField(help_text="Auto-incrementing version number")

    # Snapshot of configuration at time of use
    config_snapshot = models.JSONField(
        help_text="Full copy of dataset configuration at time of versioning"
    )

    # Stats at time of snapshot
    actual_row_count = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Actual row count when this version was created"
    )
    actual_unique_users = models.IntegerField(
        null=True,
        blank=True,
        help_text="Actual unique users when this version was created"
    )
    actual_unique_products = models.IntegerField(
        null=True,
        blank=True,
        help_text="Actual unique products when this version was created"
    )

    # Generated BigQuery SQL
    generated_query = models.TextField(
        blank=True,
        help_text="The BigQuery SQL generated from this dataset version"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    # Link to training run (optional, set when used in training)
    # Note: This will be linked when Training domain is implemented
    # training_run = models.ForeignKey('TrainingRun', ...)

    class Meta:
        ordering = ['-version_number']
        unique_together = ['dataset', 'version_number']
        verbose_name = 'Dataset Version'
        verbose_name_plural = 'Dataset Versions'

    def __str__(self):
        return f"{self.dataset.name} v{self.version_number}"

    def save(self, *args, **kwargs):
        """Auto-increment version number on create"""
        if not self.pk:  # New instance
            last_version = DatasetVersion.objects.filter(
                dataset=self.dataset
            ).order_by('-version_number').first()
            self.version_number = (last_version.version_number + 1) if last_version else 1
        super().save(*args, **kwargs)


# =============================================================================
# FEATURE CONFIG MODELS (Modeling Domain)
# =============================================================================

class FeatureConfig(models.Model):
    """
    Defines HOW data is transformed for training TFRS two-tower models.

    A Feature Config specifies:
    - Which columns go to BuyerModel (Query Tower) vs ProductModel (Candidate Tower)
    - Transformation logic for each column (embeddings, buckets, cyclical)
    - Cross features within each model
    - Generates the TFX Transform preprocessing_fn

    Multiple Feature Configs can exist per Dataset for experimentation.
    """

    # Basic info
    name = models.CharField(
        max_length=255,
        help_text="Feature config name (e.g., 'Rich Features v2')"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of this feature configuration"
    )
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='feature_configs',
        help_text="The dataset this feature config is based on"
    )

    # Version tracking
    version = models.PositiveIntegerField(
        default=1,
        help_text="Current version number"
    )

    # BuyerModel (Query Tower) features
    # JSON array of feature configurations
    # Example: [
    #   {"column": "customer_id", "type": "string_embedding", "embedding_dim": 64,
    #    "vocab_settings": {"max_size": 100000, "oov_buckets": 10, "min_frequency": 5}},
    #   {"column": "revenue", "type": "numeric", "transforms": {
    #       "normalize": {"enabled": true, "range": [-1, 1]},
    #       "bucketize": {"enabled": true, "buckets": 100, "embedding_dim": 32}
    #   }}
    # ]
    buyer_model_features = models.JSONField(
        default=list,
        blank=True,
        help_text="Features assigned to BuyerModel (Query Tower)"
    )

    # ProductModel (Candidate Tower) features
    product_model_features = models.JSONField(
        default=list,
        blank=True,
        help_text="Features assigned to ProductModel (Candidate Tower)"
    )

    # Cross features for BuyerModel
    # Example: [
    #   {"features": ["customer_id", "city"], "hash_bucket_size": 5000, "embedding_dim": 16}
    # ]
    buyer_model_crosses = models.JSONField(
        default=list,
        blank=True,
        help_text="Cross features for BuyerModel"
    )

    # Cross features for ProductModel
    product_model_crosses = models.JSONField(
        default=list,
        blank=True,
        help_text="Cross features for ProductModel"
    )

    # =========================================================================
    # Config Type (derived from target_column presence)
    # =========================================================================

    CONFIG_TYPE_RETRIEVAL = 'retrieval'
    CONFIG_TYPE_RANKING = 'ranking'

    CONFIG_TYPE_CHOICES = [
        (CONFIG_TYPE_RETRIEVAL, 'Retrieval'),
        (CONFIG_TYPE_RANKING, 'Ranking'),
    ]

    config_type = models.CharField(
        max_length=20,
        choices=CONFIG_TYPE_CHOICES,
        default=CONFIG_TYPE_RETRIEVAL,
        help_text="Derived from target_column presence. Retrieval=no target, Ranking=has target"
    )

    # =========================================================================
    # Target Column (for Ranking models)
    # =========================================================================

    # Schema:
    # {
    #   "column": "sales",
    #   "display_name": "sales",  # Optional alias
    #   "bq_type": "FLOAT64",
    #   "transforms": {
    #     "normalize": {"enabled": false, "range": [0, 1]},
    #     "log_transform": {"enabled": false},
    #     "clip_outliers": {"enabled": false, "percentile": 99}
    #   }
    # }
    target_column = models.JSONField(
        null=True,
        blank=True,
        help_text="Target column for ranking models (e.g., rating, sales, quantity)"
    )

    # Cached tensor dimensions (for quick display)
    buyer_tensor_dim = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total tensor dimensions for BuyerModel"
    )
    product_tensor_dim = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total tensor dimensions for ProductModel"
    )

    # Generated TFX Transform code (stored as text for Cloud Run compatibility)
    # Note: Trainer code is now generated at runtime with ModelConfig via TrainerModuleGenerator
    generated_transform_code = models.TextField(
        blank=True,
        help_text="Auto-generated TFX Transform preprocessing_fn code"
    )
    generated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When transform code was last generated"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Created by
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_feature_configs'
    )

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['dataset', 'name']
        verbose_name = 'Feature Config'
        verbose_name_plural = 'Feature Configs'

    def __str__(self):
        return f"{self.name} v{self.version}"

    def save(self, *args, **kwargs):
        """Override save to auto-derive config_type and remove target from models."""
        # Auto-derive config_type from target_column presence
        if self.target_column:
            self.config_type = self.CONFIG_TYPE_RANKING
        else:
            self.config_type = self.CONFIG_TYPE_RETRIEVAL

        # Auto-remove target column from buyer/product models to prevent data leakage
        self._remove_target_from_models()

        super().save(*args, **kwargs)

    def _remove_target_from_models(self):
        """Remove target column from feature models to prevent data leakage."""
        if not self.target_column:
            return

        target_col = self.target_column.get('column')
        target_display = self.target_column.get('display_name', target_col)

        # Remove from buyer_model_features
        if self.buyer_model_features:
            self.buyer_model_features = [
                f for f in self.buyer_model_features
                if f.get('column') != target_col and f.get('display_name') != target_display
            ]

        # Remove from product_model_features
        if self.product_model_features:
            self.product_model_features = [
                f for f in self.product_model_features
                if f.get('column') != target_col and f.get('display_name') != target_display
            ]

    def get_target_column_name(self):
        """Return the target column name for display."""
        if not self.target_column:
            return None
        return self.target_column.get('display_name') or self.target_column.get('column')

    def calculate_tensor_dims(self):
        """Calculate and cache tensor dimensions for both models."""
        self.buyer_tensor_dim = self._calc_model_dim(
            self.buyer_model_features, self.buyer_model_crosses
        )
        self.product_tensor_dim = self._calc_model_dim(
            self.product_model_features, self.product_model_crosses
        )

    def _calc_model_dim(self, features, crosses):
        """Calculate total dimension for a model."""
        total = 0
        for f in features:
            total += self._calc_feature_dim(f)
        for c in crosses:
            total += c.get('embedding_dim', 16)
        return total

    def _calc_feature_dim(self, feature):
        """Calculate dimension for a single feature."""
        dim = 0
        transforms = feature.get('transforms', {})

        # Text embedding (transforms.embedding.enabled)
        embedding = transforms.get('embedding', {})
        if embedding.get('enabled'):
            dim += embedding.get('embedding_dim', 32)

        # Legacy: String embedding (feature.type == 'string_embedding')
        if feature.get('type') == 'string_embedding':
            dim += feature.get('embedding_dim', 32)

        # Numeric transforms
        if transforms.get('normalize', {}).get('enabled'):
            dim += 1
        if transforms.get('bucketize', {}).get('enabled'):
            dim += transforms['bucketize'].get('embedding_dim', 32)

        # Cyclical features (2D each for sin/cos)
        cyclical = transforms.get('cyclical', {})
        for cycle in ['annual', 'quarterly', 'monthly', 'weekly', 'daily']:
            if cyclical.get(cycle):
                dim += 2

        return dim

    def get_columns_in_both_models(self):
        """Return columns that appear in both models (data leakage warning)."""
        buyer_cols = {f['column'] for f in self.buyer_model_features}
        product_cols = {f['column'] for f in self.product_model_features}
        return list(buyer_cols & product_cols)

    def get_config_hash(self):
        """Generate hash of configuration for duplicate detection."""
        import hashlib
        import json
        config = {
            'buyer_model_features': self.buyer_model_features,
            'product_model_features': self.product_model_features,
            'buyer_model_crosses': self.buyer_model_crosses,
            'product_model_crosses': self.product_model_crosses,
        }
        return hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()

    def update_best_metrics(self, quick_test):
        """
        Update best metrics if this quick test improved them.

        Args:
            quick_test: QuickTest instance with results

        Returns:
            bool: True if any metrics were updated
        """
        updated = False

        if quick_test.recall_at_100 is not None:
            if self.best_recall_at_100 is None or quick_test.recall_at_100 > self.best_recall_at_100:
                self.best_recall_at_100 = quick_test.recall_at_100
                updated = True

        if quick_test.recall_at_50 is not None:
            if self.best_recall_at_50 is None or quick_test.recall_at_50 > self.best_recall_at_50:
                self.best_recall_at_50 = quick_test.recall_at_50
                updated = True

        if quick_test.recall_at_10 is not None:
            if self.best_recall_at_10 is None or quick_test.recall_at_10 > self.best_recall_at_10:
                self.best_recall_at_10 = quick_test.recall_at_10
                updated = True

        if updated:
            self.save(update_fields=['best_recall_at_100', 'best_recall_at_50', 'best_recall_at_10', 'updated_at'])

        return updated


class FeatureConfigVersion(models.Model):
    """
    Stores historical versions of a FeatureConfig for audit trail.
    Created automatically when FeatureConfig is saved with changes.
    """

    feature_config = models.ForeignKey(
        FeatureConfig,
        on_delete=models.CASCADE,
        related_name='versions',
        help_text="The feature config this version belongs to"
    )
    version = models.PositiveIntegerField(
        help_text="Version number"
    )

    # Snapshot of config at this version
    buyer_model_features = models.JSONField(
        help_text="Snapshot of buyer model features"
    )
    product_model_features = models.JSONField(
        help_text="Snapshot of product model features"
    )
    buyer_model_crosses = models.JSONField(
        help_text="Snapshot of buyer model crosses"
    )
    product_model_crosses = models.JSONField(
        help_text="Snapshot of product model crosses"
    )
    buyer_tensor_dim = models.PositiveIntegerField(
        help_text="Buyer tensor dimensions at this version"
    )
    product_tensor_dim = models.PositiveIntegerField(
        help_text="Product tensor dimensions at this version"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_feature_config_versions'
    )

    class Meta:
        ordering = ['-version']
        unique_together = ['feature_config', 'version']
        verbose_name = 'Feature Config Version'
        verbose_name_plural = 'Feature Config Versions'

    def __str__(self):
        return f"{self.feature_config.name} v{self.version}"


class QuickTest(models.Model):
    """
    Tracks Quick Test pipeline runs for Feature Configs.
    Quick Tests validate feature engineering by running a mini TFX pipeline on Vertex AI.
    """

    # Status choices
    STATUS_PENDING = 'pending'
    STATUS_SUBMITTING = 'submitting'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUBMITTING, 'Submitting'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # Pipeline stage choices
    STAGE_CHOICES = [
        ('pending', 'Pending'),
        ('example_gen', 'ExampleGen'),
        ('statistics_gen', 'StatisticsGen'),
        ('schema_gen', 'SchemaGen'),
        ('transform', 'Transform'),
        ('trainer', 'Trainer'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    # =========================================================================
    # Relationships
    # =========================================================================

    feature_config = models.ForeignKey(
        FeatureConfig,
        on_delete=models.CASCADE,
        related_name='quick_tests',
        help_text="Feature Config being tested (defines feature transformations)"
    )

    model_config = models.ForeignKey(
        'ModelConfig',
        on_delete=models.CASCADE,
        null=True,  # Nullable for backward compatibility with existing QuickTests
        blank=True,
        related_name='quick_tests',
        help_text="Model Config being tested (defines neural network architecture)"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_quick_tests',
        help_text="User who initiated the test"
    )

    # =========================================================================
    # Experiment Metadata
    # =========================================================================

    experiment_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="User-defined name for this experiment (optional)"
    )

    experiment_description = models.TextField(
        blank=True,
        help_text="User-defined description for this experiment (optional)"
    )

    # =========================================================================
    # Test Configuration
    # =========================================================================

    # Split strategy choices
    SPLIT_RANDOM = 'random'
    SPLIT_TIME_HOLDOUT = 'time_holdout'
    SPLIT_STRICT_TIME = 'strict_time'

    SPLIT_STRATEGY_CHOICES = [
        (SPLIT_RANDOM, 'Random Split (fastest, may have data leakage)'),
        (SPLIT_TIME_HOLDOUT, 'Time Holdout (recommended for recommenders)'),
        (SPLIT_STRICT_TIME, 'Strict Temporal (train < val < test by date)'),
    ]

    # Data sampling and split settings
    data_sample_percent = models.IntegerField(
        default=100,
        help_text="Percentage of dataset to use (5, 10, 25, or 100)"
    )

    split_strategy = models.CharField(
        max_length=20,
        choices=SPLIT_STRATEGY_CHOICES,
        default=SPLIT_RANDOM,
        help_text="How to split data into train/eval sets"
    )

    holdout_days = models.IntegerField(
        default=1,
        help_text="Days to exclude from training for holdout (used with time_holdout strategy)"
    )

    date_column = models.CharField(
        max_length=255,
        blank=True,
        help_text="Column name for temporal split (required for time-based strategies)"
    )

    # For strict_time rolling window
    train_days = models.IntegerField(
        default=60,
        help_text="Number of days for training data (strict_time strategy)"
    )
    val_days = models.IntegerField(
        default=7,
        help_text="Number of days for validation data (strict_time strategy)"
    )
    test_days = models.IntegerField(
        default=7,
        help_text="Number of days for test data (strict_time strategy)"
    )

    # Training hyperparameters
    epochs = models.IntegerField(
        default=10,
        help_text="Number of training epochs (1-15)"
    )
    batch_size = models.IntegerField(
        default=4096,
        help_text="Training batch size"
    )
    learning_rate = models.FloatField(
        default=0.001,
        help_text="Learning rate for optimizer"
    )

    # Hardware configuration
    MACHINE_TYPE_SMALL = 'n1-standard-4'
    MACHINE_TYPE_MEDIUM = 'n1-standard-8'
    MACHINE_TYPE_LARGE = 'n1-standard-16'

    MACHINE_TYPE_CHOICES = [
        (MACHINE_TYPE_SMALL, 'Small (n1-standard-4: 4 vCPU, 15 GB)'),
        (MACHINE_TYPE_MEDIUM, 'Medium (n1-standard-8: 8 vCPU, 30 GB)'),
        (MACHINE_TYPE_LARGE, 'Large (n1-standard-16: 16 vCPU, 60 GB)'),
    ]

    machine_type = models.CharField(
        max_length=50,
        choices=MACHINE_TYPE_CHOICES,
        default=MACHINE_TYPE_SMALL,
        help_text="Compute machine type for Trainer and Dataflow workers"
    )

    # Rating column for ranking models
    rating_column = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Column name containing ratings/scores (required for ranking models)"
    )

    # =========================================================================
    # Denormalized Fields for Hyperparameter Analysis
    # These fields are copied from ModelConfig/FeatureConfig/Dataset at creation
    # to enable fast querying without joins for TPE-based analysis
    # =========================================================================

    # From ModelConfig - Training params
    optimizer = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Optimizer algorithm (denormalized from ModelConfig)"
    )
    output_embedding_dim = models.IntegerField(
        null=True,
        blank=True,
        help_text="Dimension of final tower embeddings (denormalized from ModelConfig)"
    )
    retrieval_algorithm = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Algorithm for top-K retrieval (denormalized from ModelConfig)"
    )
    top_k = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of top candidates to retrieve (denormalized from ModelConfig)"
    )

    # From ModelConfig - Architecture (derived)
    buyer_tower_structure = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Buyer tower structure e.g. '128→64→32' (derived from ModelConfig)"
    )
    product_tower_structure = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Product tower structure e.g. '128→64→32' (derived from ModelConfig)"
    )
    buyer_activation = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Primary activation function in buyer tower"
    )
    product_activation = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Primary activation function in product tower"
    )

    # L2 regularization as category: 'none', 'light', 'medium', 'heavy'
    L2_REG_NONE = 'none'
    L2_REG_LIGHT = 'light'
    L2_REG_MEDIUM = 'medium'
    L2_REG_HEAVY = 'heavy'

    L2_REG_CHOICES = [
        (L2_REG_NONE, 'None (0)'),
        (L2_REG_LIGHT, 'Light (0.0001-0.001)'),
        (L2_REG_MEDIUM, 'Medium (0.001-0.01)'),
        (L2_REG_HEAVY, 'Heavy (>0.01)'),
    ]

    buyer_l2_category = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=L2_REG_CHOICES,
        help_text="L2 regularization category for buyer tower"
    )
    product_l2_category = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=L2_REG_CHOICES,
        help_text="L2 regularization category for product tower"
    )

    # Tower parameter counts (computed)
    buyer_total_params = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated trainable params in buyer tower"
    )
    product_total_params = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated trainable params in product tower"
    )

    # From FeatureConfig
    buyer_tensor_dim = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total tensor dimensions for BuyerModel (denormalized from FeatureConfig)"
    )
    product_tensor_dim = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total tensor dimensions for ProductModel (denormalized from FeatureConfig)"
    )
    buyer_feature_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of columns in buyer tower"
    )
    product_feature_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of columns in product tower"
    )
    buyer_cross_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of cross features in buyer tower"
    )
    product_cross_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of cross features in product tower"
    )

    # Feature details for TPE analysis (name + dimension combinations)
    buyer_feature_details = models.JSONField(
        null=True,
        blank=True,
        help_text="List of buyer features with dimensions, e.g. [{'name': 'customer_id', 'dim': 32}]"
    )
    product_feature_details = models.JSONField(
        null=True,
        blank=True,
        help_text="List of product features with dimensions"
    )
    buyer_cross_details = models.JSONField(
        null=True,
        blank=True,
        help_text="List of buyer cross features, e.g. [{'name': 'customer_id × date', 'dim': 16}]"
    )
    product_cross_details = models.JSONField(
        null=True,
        blank=True,
        help_text="List of product cross features"
    )

    # From Dataset (via FeatureConfig)
    dataset_row_count = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated row count of dataset"
    )
    dataset_date_range_days = models.IntegerField(
        null=True,
        blank=True,
        help_text="Number of days in dataset date range"
    )
    dataset_unique_users = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated unique users in dataset"
    )
    dataset_unique_products = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated unique products in dataset"
    )

    # Dataset Filter Descriptions (for hyperparameter analysis)
    # Each field stores a list of human-readable filter descriptions
    # Example: ["Rolling 60 days"] or ["city = CHERNIGIV", "Transaction count > 2"]
    dataset_date_filters = models.JSONField(
        null=True,
        blank=True,
        default=list,
        help_text="List of date filter descriptions (e.g., ['Rolling 60 days'])"
    )
    dataset_customer_filters = models.JSONField(
        null=True,
        blank=True,
        default=list,
        help_text="List of customer filter descriptions (e.g., ['city = CHERNIGIV', 'Transaction count > 2'])"
    )
    dataset_product_filters = models.JSONField(
        null=True,
        blank=True,
        default=list,
        help_text="List of product filter descriptions (e.g., ['Top 80%', 'category = Books'])"
    )

    # Experiment number (auto-incrementing per Model Endpoint)
    experiment_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Sequential experiment number within the Model Endpoint (Exp #1, Exp #2, etc.)"
    )

    # =========================================================================
    # Pipeline Tracking
    # =========================================================================

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True
    )

    # Vertex AI Pipeline identifiers
    vertex_pipeline_job_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Full Vertex AI pipeline job resource name"
    )
    vertex_pipeline_job_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short pipeline job ID for display"
    )

    # Cloud Build tracking (for async compilation)
    cloud_build_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cloud Build ID for pipeline compilation"
    )
    cloud_build_run_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Run ID used for GCS result path"
    )

    # Progress tracking
    current_stage = models.CharField(
        max_length=50,
        choices=STAGE_CHOICES,
        default='pending',
        help_text="Current pipeline stage"
    )
    progress_percent = models.IntegerField(
        default=0,
        help_text="Overall progress percentage (0-100)"
    )

    # Detailed stage information for UI
    stage_details = models.JSONField(
        default=list,
        help_text="List of stage statuses: [{name, status, duration_seconds, error}]"
    )

    # =========================================================================
    # Results
    # =========================================================================

    # Training metrics
    loss = models.FloatField(
        null=True,
        blank=True,
        help_text="Final training loss"
    )
    recall_at_5 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@5 metric"
    )
    recall_at_10 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@10 metric"
    )
    recall_at_50 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@50 metric"
    )
    recall_at_100 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@100 metric"
    )

    # Ranking model metrics
    rmse = models.FloatField(
        null=True,
        blank=True,
        help_text="Root Mean Square Error (validation) - for ranking models"
    )
    mae = models.FloatField(
        null=True,
        blank=True,
        help_text="Mean Absolute Error (validation) - for ranking models"
    )
    test_rmse = models.FloatField(
        null=True,
        blank=True,
        help_text="Root Mean Square Error (test set) - for ranking models"
    )
    test_mae = models.FloatField(
        null=True,
        blank=True,
        help_text="Mean Absolute Error (test set) - for ranking models"
    )

    # Vocabulary statistics
    vocabulary_stats = models.JSONField(
        default=dict,
        help_text="Vocabulary sizes and OOV rates per feature"
    )

    # Error information
    error_message = models.TextField(
        blank=True,
        help_text="Error message if pipeline failed"
    )
    error_stage = models.CharField(
        max_length=50,
        blank=True,
        help_text="Stage where error occurred"
    )

    # =========================================================================
    # Artifacts
    # =========================================================================

    gcs_artifacts_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="GCS path for this run's artifacts"
    )

    # =========================================================================
    # MLflow Tracking
    # =========================================================================

    mlflow_run_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="MLflow run ID for this experiment"
    )
    mlflow_experiment_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="MLflow experiment name"
    )
    training_history_json = models.JSONField(
        null=True,
        blank=True,
        help_text="Cached training history data for fast loading (loss curves, metrics, params)"
    )

    # =========================================================================
    # Timestamps
    # =========================================================================

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When pipeline was submitted to Vertex AI"
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When pipeline started running"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When pipeline completed/failed"
    )

    # Computed duration
    duration_seconds = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total pipeline duration in seconds"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Quick Test'
        verbose_name_plural = 'Quick Tests'

    def __str__(self):
        return f"QuickTest #{self.pk} - {self.feature_config.name} ({self.status})"

    @property
    def is_terminal(self):
        """Check if the test has reached a terminal state."""
        return self.status in [
            self.STATUS_COMPLETED,
            self.STATUS_FAILED,
            self.STATUS_CANCELLED
        ]

    @property
    def display_name(self):
        """Return display name like 'Exp #1', 'Exp #2', etc."""
        if self.experiment_number:
            return f"Exp #{self.experiment_number}"
        return f"Exp #{self.pk}"

    def assign_experiment_number(self):
        """
        Assign the next sequential experiment number for this Model Endpoint.
        Should be called when creating a new QuickTest.
        """
        if self.experiment_number is not None:
            return  # Already assigned

        # Get the model endpoint through the feature config's dataset
        model_endpoint = self.feature_config.dataset.model_endpoint

        # Find the max experiment_number for this model endpoint
        max_number = QuickTest.objects.filter(
            feature_config__dataset__model_endpoint=model_endpoint,
            experiment_number__isnull=False
        ).aggregate(models.Max('experiment_number'))['experiment_number__max']

        self.experiment_number = (max_number or 0) + 1

    @property
    def elapsed_seconds(self):
        """Calculate elapsed time for running tests."""
        if self.started_at:
            if self.completed_at:
                return int((self.completed_at - self.started_at).total_seconds())
            else:
                from django.utils import timezone
                return int((timezone.now() - self.started_at).total_seconds())
        return None

    def get_initial_stage_details(self):
        """Create initial stage details structure."""
        return [
            {"name": "ExampleGen", "status": "pending", "duration_seconds": None},
            {"name": "StatisticsGen", "status": "pending", "duration_seconds": None},
            {"name": "SchemaGen", "status": "pending", "duration_seconds": None},
            {"name": "Transform", "status": "pending", "duration_seconds": None},
            {"name": "Trainer", "status": "pending", "duration_seconds": None},
        ]

    def calculate_progress(self):
        """Calculate overall progress percentage from stage details."""
        if not self.stage_details:
            return 0

        stage_weights = {
            'ExampleGen': 20,
            'StatisticsGen': 10,
            'SchemaGen': 5,
            'Transform': 25,
            'Trainer': 40,
        }

        total_weight = sum(stage_weights.values())
        completed_weight = 0

        for stage in self.stage_details:
            if stage.get('status') == 'completed':
                completed_weight += stage_weights.get(stage['name'], 0)
            elif stage.get('status') == 'running':
                # Partial credit for running stage
                completed_weight += stage_weights.get(stage['name'], 0) * 0.5

        return int((completed_weight / total_weight) * 100)


# =============================================================================
# MODEL CONFIG (Model Structure Domain)
# =============================================================================

class ModelConfig(models.Model):
    """
    Defines neural network architecture and training configuration.
    Scoped to a ModelEndpoint (project) - can be used with any feature set within that project.

    A ModelConfig specifies:
    - Model type (Retrieval, Ranking, Multitask)
    - Tower architecture (layer types, units, activations)
    - Training hyperparameters (optimizer, learning rate, batch size, epochs)
    - Output embedding dimensions

    ModelConfigs are project-scoped and reusable across any Dataset/FeatureConfig within the same project.
    """

    # =========================================================================
    # Project Scope
    # =========================================================================

    model_endpoint = models.ForeignKey(
        ModelEndpoint,
        on_delete=models.CASCADE,
        related_name='model_configs',
        help_text="The project this model config belongs to"
    )

    # =========================================================================
    # Model Types
    # =========================================================================

    MODEL_TYPE_RETRIEVAL = 'retrieval'
    MODEL_TYPE_RANKING = 'ranking'
    MODEL_TYPE_MULTITASK = 'multitask'

    MODEL_TYPE_CHOICES = [
        (MODEL_TYPE_RETRIEVAL, 'Retrieval'),
        (MODEL_TYPE_RANKING, 'Ranking'),
        (MODEL_TYPE_MULTITASK, 'Multitask'),
    ]

    # =========================================================================
    # Optimizer Choices
    # =========================================================================

    OPTIMIZER_ADAGRAD = 'adagrad'
    OPTIMIZER_ADAM = 'adam'
    OPTIMIZER_SGD = 'sgd'
    OPTIMIZER_RMSPROP = 'rmsprop'
    OPTIMIZER_ADAMW = 'adamw'
    OPTIMIZER_FTRL = 'ftrl'

    OPTIMIZER_CHOICES = [
        (OPTIMIZER_ADAGRAD, 'Adagrad'),
        (OPTIMIZER_ADAM, 'Adam'),
        (OPTIMIZER_SGD, 'SGD'),
        (OPTIMIZER_RMSPROP, 'RMSprop'),
        (OPTIMIZER_ADAMW, 'AdamW'),
        (OPTIMIZER_FTRL, 'FTRL'),
    ]

    # =========================================================================
    # Loss Function Choices (for Ranking/Multitask)
    # =========================================================================

    LOSS_MSE = 'mse'
    LOSS_BINARY_CROSSENTROPY = 'binary_crossentropy'
    LOSS_HUBER = 'huber'

    LOSS_FUNCTION_CHOICES = [
        (LOSS_MSE, 'Mean Squared Error'),
        (LOSS_BINARY_CROSSENTROPY, 'Binary Crossentropy'),
        (LOSS_HUBER, 'Huber'),
    ]

    # =========================================================================
    # Basic Info
    # =========================================================================

    name = models.CharField(
        max_length=255,
        help_text="Descriptive name (e.g., 'Standard Retrieval v1')"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of this configuration"
    )

    # =========================================================================
    # Model Type
    # =========================================================================

    model_type = models.CharField(
        max_length=20,
        choices=MODEL_TYPE_CHOICES,
        default=MODEL_TYPE_RETRIEVAL,
        help_text="Type of recommendation model"
    )

    # =========================================================================
    # Tower Architecture
    # =========================================================================

    # Buyer/Query tower layer configurations
    # Schema: Array of layer config objects
    # [
    #   {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
    #   {"type": "dropout", "rate": 0.2},
    #   {"type": "batch_norm"},
    #   {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
    #   {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0}
    # ]
    buyer_tower_layers = models.JSONField(
        default=list,
        help_text="Buyer/Query tower layer configurations"
    )

    # Product/Candidate tower layer configurations
    product_tower_layers = models.JSONField(
        default=list,
        help_text="Product/Candidate tower layer configurations"
    )

    # Rating prediction layers for ranking/multitask (after embedding concatenation)
    # Used only for ranking/multitask models
    # [
    #   {"type": "dense", "units": 256, "activation": "relu"},
    #   {"type": "dense", "units": 64, "activation": "relu"},
    #   {"type": "dense", "units": 1, "activation": null}  # Final scalar output
    # ]
    rating_head_layers = models.JSONField(
        default=list,
        help_text="Rating prediction layers for ranking/multitask (after embedding concatenation)"
    )

    # Output embedding dimension (must match between towers)
    output_embedding_dim = models.IntegerField(
        default=32,
        help_text="Dimension of final tower output embeddings (must match between towers)"
    )

    # Weight sharing option
    share_tower_weights = models.BooleanField(
        default=False,
        help_text="Use identical weights for both towers (requires identical architecture)"
    )

    # =========================================================================
    # Training Hyperparameters
    # =========================================================================

    optimizer = models.CharField(
        max_length=20,
        choices=OPTIMIZER_CHOICES,
        default=OPTIMIZER_ADAGRAD,
        help_text="Optimizer algorithm"
    )

    learning_rate = models.FloatField(
        default=0.1,
        help_text="Learning rate for optimizer"
    )

    batch_size = models.IntegerField(
        default=4096,
        help_text="Training batch size"
    )

    epochs = models.IntegerField(
        default=5,
        help_text="Number of training epochs"
    )

    # Loss function for ranking/multitask models
    loss_function = models.CharField(
        max_length=30,
        choices=LOSS_FUNCTION_CHOICES,
        default=LOSS_MSE,
        help_text="Loss function for ranking models (MSE for continuous ratings, BCE for binary)"
    )

    # =========================================================================
    # Multitask Configuration (Phase 3)
    # =========================================================================

    retrieval_weight = models.FloatField(
        default=1.0,
        help_text="Weight for retrieval loss in multitask model (0.0-1.0)"
    )

    ranking_weight = models.FloatField(
        default=0.0,
        help_text="Weight for ranking loss in multitask model (0.0-1.0)"
    )

    # Note: rating_column is NOT stored here because ModelConfig is dataset-independent.
    # It is specified at QuickTest time when the user selects which column to use.

    # =========================================================================
    # Retrieval Algorithm Configuration
    # =========================================================================

    RETRIEVAL_ALGORITHM_BRUTE_FORCE = 'brute_force'
    RETRIEVAL_ALGORITHM_SCANN = 'scann'

    RETRIEVAL_ALGORITHM_CHOICES = [
        (RETRIEVAL_ALGORITHM_BRUTE_FORCE, 'Brute Force'),
        (RETRIEVAL_ALGORITHM_SCANN, 'ScaNN'),
    ]

    retrieval_algorithm = models.CharField(
        max_length=20,
        choices=RETRIEVAL_ALGORITHM_CHOICES,
        default=RETRIEVAL_ALGORITHM_BRUTE_FORCE,
        help_text="Algorithm for top-K candidate retrieval"
    )

    top_k = models.IntegerField(
        default=100,
        help_text="Number of top candidates to retrieve"
    )

    # ScaNN-specific parameters (only used when retrieval_algorithm='scann')
    scann_num_leaves = models.IntegerField(
        default=100,
        help_text="Number of partitions for ScaNN index (recommended: sqrt(catalog_size))"
    )

    scann_leaves_to_search = models.IntegerField(
        default=10,
        help_text="Number of partitions to search at query time"
    )

    # =========================================================================
    # Metadata
    # =========================================================================

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_model_configs'
    )

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Model Configuration'
        verbose_name_plural = 'Model Configurations'
        unique_together = ['model_endpoint', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_model_type_display()})"

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_buyer_tower_summary(self):
        """Return human-readable summary like '128→64→32'"""
        units = [layer['units'] for layer in self.buyer_tower_layers if layer.get('type') == 'dense']
        return '→'.join(map(str, units)) if units else 'Empty'

    def get_product_tower_summary(self):
        """Return human-readable summary like '128→64→32'"""
        units = [layer['units'] for layer in self.product_tower_layers if layer.get('type') == 'dense']
        return '→'.join(map(str, units)) if units else 'Empty'

    def get_rating_head_summary(self):
        """Return human-readable summary for rating head"""
        units = [layer['units'] for layer in self.rating_head_layers if layer.get('type') == 'dense']
        return '→'.join(map(str, units)) if units else 'None'

    def count_layers(self, tower='buyer'):
        """Count total layers in a tower"""
        layers = self.buyer_tower_layers if tower == 'buyer' else self.product_tower_layers
        return len(layers)

    def towers_are_identical(self):
        """Check if both towers have identical architecture (required for weight sharing)"""
        return self.buyer_tower_layers == self.product_tower_layers

    def estimate_params(self, buyer_input_dim=None, product_input_dim=None):
        """
        Estimate total trainable parameters.

        Args:
            buyer_input_dim: Input dimension from FeatureConfig buyer tensor
            product_input_dim: Input dimension from FeatureConfig product tensor

        Returns:
            Estimated parameter count (int)
        """
        total = 0

        # Buyer tower
        prev_dim = buyer_input_dim or 100  # Default estimate
        for layer in self.buyer_tower_layers:
            if layer.get('type') == 'dense':
                units = layer['units']
                total += prev_dim * units + units  # weights + bias
                prev_dim = units

        # Product tower (skip if sharing weights)
        if not self.share_tower_weights:
            prev_dim = product_input_dim or 50  # Default estimate
            for layer in self.product_tower_layers:
                if layer.get('type') == 'dense':
                    units = layer['units']
                    total += prev_dim * units + units
                    prev_dim = units

        # Rating head (for ranking/multitask)
        if self.model_type in [self.MODEL_TYPE_RANKING, self.MODEL_TYPE_MULTITASK] and self.rating_head_layers:
            # Input is concatenated embeddings
            prev_dim = self.output_embedding_dim * 2
            for layer in self.rating_head_layers:
                if layer.get('type') == 'dense':
                    units = layer['units']
                    total += prev_dim * units + units
                    prev_dim = units

        return total

    def validate(self):
        """
        Validate configuration and return list of errors.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Basic validation
        if not self.buyer_tower_layers:
            errors.append("Buyer tower must have at least one layer")

        if not self.product_tower_layers:
            errors.append("Product tower must have at least one layer")

        # Weight sharing requires identical architectures
        if self.share_tower_weights and not self.towers_are_identical():
            errors.append("Weight sharing requires identical tower architectures")

        # Ranking/Multitask validation
        if self.model_type in [self.MODEL_TYPE_RANKING, self.MODEL_TYPE_MULTITASK]:
            if not self.rating_head_layers:
                errors.append("Rating head layers required for ranking/multitask models")

            # Check rating head ends with units=1
            if self.rating_head_layers:
                last_layer = self.rating_head_layers[-1]
                if last_layer.get('type') == 'dense' and last_layer.get('units') != 1:
                    errors.append("Rating head must end with Dense(1) for scalar output")

        # Multitask weight validation
        if self.model_type == self.MODEL_TYPE_MULTITASK:
            if self.retrieval_weight == 0 and self.ranking_weight == 0:
                errors.append("At least one loss weight must be greater than 0")

        # Output embedding dimension validation
        if self.output_embedding_dim < 8:
            errors.append("Output embedding dimension should be at least 8")
        if self.output_embedding_dim > 512:
            errors.append("Output embedding dimension should not exceed 512")

        return errors

    # =========================================================================
    # Class Methods for Presets
    # =========================================================================

    @classmethod
    def get_default_layers(cls):
        """Return default tower layers (standard preset)"""
        return [
            {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
        ]

    @classmethod
    def get_preset(cls, preset_name):
        """
        Return preset configuration dictionary.

        Args:
            preset_name: One of 'minimal', 'standard', 'deep', 'regularized'

        Returns:
            Dictionary with preset values
        """
        presets = {
            'minimal': {
                'name': 'Minimal',
                'description': 'Fast training, 2 layers, good for initial testing',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 32, "activation": "relu", "l2_reg": 0.0},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~3 min',
            },
            'standard': {
                'name': 'Standard',
                'description': 'Balanced 3-layer architecture with L2 regularization',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.001},
                    {"type": "dense", "units": 64, "activation": "relu"},
                    {"type": "dense", "units": 32, "activation": "relu"},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.001},
                    {"type": "dense", "units": 64, "activation": "relu"},
                    {"type": "dense", "units": 32, "activation": "relu"},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~8 min',
            },
            'deep': {
                'name': 'Deep',
                'description': 'High capacity 4-layer architecture with L2 regularization',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.001},
                    {"type": "dense", "units": 128, "activation": "relu"},
                    {"type": "dense", "units": 64, "activation": "relu"},
                    {"type": "dense", "units": 32, "activation": "relu"},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.001},
                    {"type": "dense", "units": 128, "activation": "relu"},
                    {"type": "dense", "units": 64, "activation": "relu"},
                    {"type": "dense", "units": 32, "activation": "relu"},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~15 min',
            },
            'regularized': {
                'name': 'Regularized',
                'description': 'With dropout and stronger L2 to prevent overfitting',
                'buyer_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.01},
                    {"type": "dropout", "rate": 0.2},
                    {"type": "dense", "units": 64, "activation": "relu"},
                    {"type": "dropout", "rate": 0.1},
                    {"type": "dense", "units": 32, "activation": "relu"},
                ],
                'product_tower_layers': [
                    {"type": "dense", "units": 128, "activation": "relu", "l2_reg": 0.01},
                    {"type": "dropout", "rate": 0.2},
                    {"type": "dense", "units": 64, "activation": "relu"},
                    {"type": "dropout", "rate": 0.1},
                    {"type": "dense", "units": 32, "activation": "relu"},
                ],
                'output_embedding_dim': 32,
                'estimated_time': '~10 min',
            },
        }
        return presets.get(preset_name, presets['standard'])

    @classmethod
    def get_all_presets(cls):
        """Return all available presets"""
        preset_names = ['minimal', 'standard', 'deep', 'regularized']
        return {name: cls.get_preset(name) for name in preset_names}

    @classmethod
    def get_default_rating_head(cls):
        """Return default rating head layers for ranking/multitask"""
        return [
            {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
            {"type": "dense", "units": 1, "activation": None},
        ]

    @classmethod
    def get_rating_head_preset(cls, preset_name):
        """
        Return rating head preset configuration.

        Args:
            preset_name: One of 'minimal', 'standard', 'deep'

        Returns:
            Dictionary with preset values
        """
        presets = {
            'minimal': {
                'name': 'Minimal',
                'description': 'Simple 2-layer rating head, fast training',
                'layers': [
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 1, "activation": None},
                ],
            },
            'standard': {
                'name': 'Standard',
                'description': 'Balanced 3-layer rating head (recommended)',
                'layers': [
                    {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 1, "activation": None},
                ],
            },
            'deep': {
                'name': 'Deep',
                'description': 'High capacity 4-layer rating head for complex patterns',
                'layers': [
                    {"type": "dense", "units": 512, "activation": "relu", "l2_reg": 0.001},
                    {"type": "dense", "units": 256, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 64, "activation": "relu", "l2_reg": 0.0},
                    {"type": "dense", "units": 1, "activation": None},
                ],
            },
        }
        return presets.get(preset_name, presets['standard'])

    @classmethod
    def get_all_rating_head_presets(cls):
        """Return all available rating head presets"""
        preset_names = ['minimal', 'standard', 'deep']
        return {name: cls.get_rating_head_preset(name) for name in preset_names}

    @classmethod
    def get_loss_function_info(cls):
        """Return descriptions for each loss function"""
        return {
            cls.LOSS_MSE: {
                'name': 'Mean Squared Error',
                'short_name': 'MSE',
                'description': 'Best for continuous ratings (e.g., 1.0-5.0). Penalizes large prediction errors more heavily.',
                'use_case': 'Continuous ratings',
            },
            cls.LOSS_BINARY_CROSSENTROPY: {
                'name': 'Binary Crossentropy',
                'short_name': 'BCE',
                'description': 'For binary outcomes (like/dislike, click/no-click). Use when rating is 0 or 1.',
                'use_case': 'Binary feedback',
            },
            cls.LOSS_HUBER: {
                'name': 'Huber Loss',
                'short_name': 'Huber',
                'description': 'Robust to outliers. Combines MSE for small errors and MAE for large errors. Good when ratings have noise.',
                'use_case': 'Noisy ratings',
            },
        }
