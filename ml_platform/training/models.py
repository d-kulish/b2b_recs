"""
Training Domain Models

Defines models for training runs and scheduling on Vertex AI.
- TrainingSchedule: Defines scheduled/recurring training configurations
- TrainingRun: Tracks individual full-scale training runs
"""
from django.db import models
from django.contrib.auth.models import User


class TrainingSchedule(models.Model):
    """
    Defines a scheduled or recurring training configuration.
    Each execution creates a new TrainingRun linked back to this schedule.

    Supports:
    - One-time scheduled training (schedule for a specific datetime)
    - Daily recurring training
    - Weekly recurring training
    """

    # =========================================================================
    # Schedule Type Choices
    # =========================================================================
    SCHEDULE_TYPE_ONCE = 'once'
    SCHEDULE_TYPE_DAILY = 'daily'
    SCHEDULE_TYPE_WEEKLY = 'weekly'

    SCHEDULE_TYPE_CHOICES = [
        (SCHEDULE_TYPE_ONCE, 'One-time'),
        (SCHEDULE_TYPE_DAILY, 'Daily'),
        (SCHEDULE_TYPE_WEEKLY, 'Weekly'),
    ]

    # =========================================================================
    # Status Choices
    # =========================================================================
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'  # For one-time schedules after execution
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # =========================================================================
    # Relationships
    # =========================================================================
    ml_model = models.ForeignKey(
        'ml_platform.ModelEndpoint',
        on_delete=models.CASCADE,
        related_name='training_schedules',
        help_text="Parent model/endpoint this schedule belongs to"
    )

    dataset = models.ForeignKey(
        'ml_platform.Dataset',
        on_delete=models.PROTECT,
        related_name='training_schedules',
        help_text="Dataset to use for scheduled training"
    )

    feature_config = models.ForeignKey(
        'ml_platform.FeatureConfig',
        on_delete=models.PROTECT,
        related_name='training_schedules',
        help_text="Feature configuration to use for scheduled training"
    )

    model_config = models.ForeignKey(
        'ml_platform.ModelConfig',
        on_delete=models.PROTECT,
        related_name='training_schedules',
        help_text="Model configuration (architecture) to use for scheduled training"
    )

    base_experiment = models.ForeignKey(
        'ml_platform.QuickTest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_schedules',
        help_text="Base experiment this schedule was created from"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_training_schedules',
        help_text="User who created the schedule"
    )

    # =========================================================================
    # Schedule Configuration
    # =========================================================================
    name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this schedule"
    )

    description = models.TextField(
        blank=True,
        help_text="Optional description of the schedule"
    )

    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPE_CHOICES,
        help_text="Type of schedule (once, daily, weekly)"
    )

    # For one-time schedules
    scheduled_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Specific datetime for one-time execution (for 'once' type)"
    )

    # For recurring schedules
    schedule_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Time of day for recurring execution (HH:MM for 'daily'/'weekly' types)"
    )

    schedule_day_of_week = models.IntegerField(
        null=True,
        blank=True,
        help_text="Day of week for weekly schedules (0=Monday, 6=Sunday)"
    )

    schedule_timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="Timezone for schedule execution"
    )

    # =========================================================================
    # Training Configuration (frozen at schedule creation)
    # =========================================================================
    training_params = models.JSONField(
        default=dict,
        help_text="Training hyperparameters (epochs, batch_size, learning_rate, etc.)"
    )

    gpu_config = models.JSONField(
        default=dict,
        help_text="GPU configuration (machine_type, accelerator_type, accelerator_count)"
    )

    evaluator_config = models.JSONField(
        default=dict,
        help_text="Model evaluation configuration (blessing thresholds, metrics)"
    )

    deployment_config = models.JSONField(
        default=dict,
        help_text="Deployment configuration (auto_deploy, endpoint settings)"
    )

    # =========================================================================
    # Cloud Scheduler Integration
    # =========================================================================
    cloud_scheduler_job_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Full Cloud Scheduler job resource name"
    )

    # =========================================================================
    # Status & Statistics
    # =========================================================================
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        help_text="Current status of the schedule"
    )

    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the schedule last triggered a training run"
    )

    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the schedule will next trigger (calculated)"
    )

    total_runs = models.IntegerField(
        default=0,
        help_text="Total number of training runs triggered by this schedule"
    )

    successful_runs = models.IntegerField(
        default=0,
        help_text="Number of successful (completed/blessed) training runs"
    )

    failed_runs = models.IntegerField(
        default=0,
        help_text="Number of failed/cancelled training runs"
    )

    # =========================================================================
    # Timestamps
    # =========================================================================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'training'
        ordering = ['-created_at']
        verbose_name = 'Training Schedule'
        verbose_name_plural = 'Training Schedules'

    def __str__(self):
        return f"TrainingSchedule '{self.name}' ({self.schedule_type}, {self.status})"

    @property
    def is_active(self):
        """Check if the schedule is currently active."""
        return self.status == self.STATUS_ACTIVE

    @property
    def is_recurring(self):
        """Check if this is a recurring schedule."""
        return self.schedule_type in (self.SCHEDULE_TYPE_DAILY, self.SCHEDULE_TYPE_WEEKLY)

    @property
    def success_rate(self):
        """Calculate success rate as percentage."""
        if self.total_runs == 0:
            return None
        return round((self.successful_runs / self.total_runs) * 100, 1)


class TrainingRun(models.Model):
    """
    Tracks full-scale training runs on Vertex AI with GPU support.
    Each TrainingRun represents a production model training job that can be
    registered in Vertex AI Model Registry and deployed to endpoints.
    """

    # =========================================================================
    # Status choices
    # =========================================================================
    STATUS_PENDING = 'pending'
    STATUS_SCHEDULED = 'scheduled'
    STATUS_SUBMITTING = 'submitting'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_NOT_BLESSED = 'not_blessed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_SUBMITTING, 'Submitting'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_NOT_BLESSED, 'Not Blessed'),
    ]

    # Model type choices
    MODEL_TYPE_RETRIEVAL = 'retrieval'
    MODEL_TYPE_RANKING = 'ranking'
    MODEL_TYPE_MULTITASK = 'multitask'

    MODEL_TYPE_CHOICES = [
        (MODEL_TYPE_RETRIEVAL, 'Retrieval'),
        (MODEL_TYPE_RANKING, 'Ranking'),
        (MODEL_TYPE_MULTITASK, 'Multitask'),
    ]

    # =========================================================================
    # Relationships
    # =========================================================================

    ml_model = models.ForeignKey(
        'ml_platform.ModelEndpoint',
        on_delete=models.CASCADE,
        related_name='training_runs',
        help_text="Parent model/endpoint this training run belongs to"
    )

    base_experiment = models.ForeignKey(
        'ml_platform.QuickTest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_runs',
        help_text="Quick test experiment this training run is based on"
    )

    # Configuration links (PROTECT to prevent deletion of used configs)
    dataset = models.ForeignKey(
        'ml_platform.Dataset',
        on_delete=models.PROTECT,
        related_name='training_runs',
        help_text="Dataset used for training"
    )

    feature_config = models.ForeignKey(
        'ml_platform.FeatureConfig',
        on_delete=models.PROTECT,
        related_name='training_runs',
        help_text="Feature configuration used for training"
    )

    model_config = models.ForeignKey(
        'ml_platform.ModelConfig',
        on_delete=models.PROTECT,
        related_name='training_runs',
        help_text="Model configuration (architecture) used for training"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_training_runs',
        help_text="User who initiated the training run"
    )

    schedule = models.ForeignKey(
        'TrainingSchedule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_runs',
        help_text="Schedule that triggered this run (null for manual runs)"
    )

    # =========================================================================
    # Basic Info
    # =========================================================================

    name = models.CharField(
        max_length=255,
        help_text="Model name in Vertex AI Model Registry"
    )

    run_number = models.IntegerField(
        help_text="Auto-increment run number per model endpoint"
    )

    description = models.TextField(
        blank=True,
        help_text="User-provided description of this training run"
    )

    model_type = models.CharField(
        max_length=20,
        choices=MODEL_TYPE_CHOICES,
        default=MODEL_TYPE_RETRIEVAL,
        help_text="Type of model being trained"
    )

    # =========================================================================
    # Configuration (JSON fields)
    # =========================================================================

    training_params = models.JSONField(
        default=dict,
        help_text="Training hyperparameters (epochs, batch_size, learning_rate, etc.)"
    )

    gpu_config = models.JSONField(
        default=dict,
        help_text="GPU configuration (machine_type, accelerator_type, accelerator_count)"
    )

    evaluator_config = models.JSONField(
        default=dict,
        help_text="Model evaluation configuration (blessing thresholds, metrics)"
    )

    deployment_config = models.JSONField(
        default=dict,
        help_text="Deployment configuration (auto_deploy, endpoint settings)"
    )

    # =========================================================================
    # Status Tracking
    # =========================================================================

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Current status of the training run"
    )

    current_stage = models.CharField(
        max_length=100,
        blank=True,
        help_text="Current pipeline stage (e.g., 'ExampleGen', 'Trainer')"
    )

    current_epoch = models.IntegerField(
        null=True,
        blank=True,
        help_text="Current training epoch (for progress tracking)"
    )

    total_epochs = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total number of training epochs"
    )

    progress_percent = models.IntegerField(
        default=0,
        help_text="Overall progress percentage (0-100)"
    )

    stage_details = models.JSONField(
        default=list,
        help_text="Detailed status of each pipeline stage"
    )

    # =========================================================================
    # Pipeline Tracking
    # =========================================================================

    cloud_build_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cloud Build job ID for pipeline compilation"
    )

    cloud_build_run_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cloud Build run ID"
    )

    vertex_pipeline_job_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Vertex AI Pipeline job name"
    )

    gcs_artifacts_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="GCS path for training artifacts"
    )

    # =========================================================================
    # Metrics (Retrieval)
    # =========================================================================

    loss = models.FloatField(
        null=True,
        blank=True,
        help_text="Final training loss"
    )

    recall_at_5 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@5 metric for retrieval models"
    )

    recall_at_10 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@10 metric for retrieval models"
    )

    recall_at_50 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@50 metric for retrieval models"
    )

    recall_at_100 = models.FloatField(
        null=True,
        blank=True,
        help_text="Recall@100 metric for retrieval models"
    )

    # =========================================================================
    # Metrics (Ranking)
    # =========================================================================

    rmse = models.FloatField(
        null=True,
        blank=True,
        help_text="Root Mean Square Error (validation set)"
    )

    mae = models.FloatField(
        null=True,
        blank=True,
        help_text="Mean Absolute Error (validation set)"
    )

    test_rmse = models.FloatField(
        null=True,
        blank=True,
        help_text="Root Mean Square Error (test set)"
    )

    test_mae = models.FloatField(
        null=True,
        blank=True,
        help_text="Mean Absolute Error (test set)"
    )

    # =========================================================================
    # Evaluation Results
    # =========================================================================

    is_blessed = models.BooleanField(
        null=True,
        help_text="Whether the model passed evaluation (blessing)"
    )

    evaluation_results = models.JSONField(
        default=dict,
        help_text="Detailed evaluation results from model evaluation"
    )

    # =========================================================================
    # Model Registry
    # =========================================================================

    vertex_model_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Vertex AI Model Registry model name"
    )

    vertex_model_version = models.CharField(
        max_length=100,
        blank=True,
        help_text="Vertex AI Model Registry version"
    )

    vertex_model_resource_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Full Vertex AI Model resource name"
    )

    registered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the model was registered to Model Registry"
    )

    # =========================================================================
    # Deployment
    # =========================================================================

    is_deployed = models.BooleanField(
        default=False,
        help_text="Whether the model is currently deployed"
    )

    deployed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the model was deployed"
    )

    endpoint_resource_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Vertex AI Endpoint resource name where model is deployed"
    )

    # =========================================================================
    # Artifacts
    # =========================================================================

    artifacts = models.JSONField(
        default=dict,
        help_text="Paths to generated artifacts (model, embeddings, etc.)"
    )

    training_history_json = models.JSONField(
        default=dict,
        help_text="Cached training history data (loss curves, metrics)"
    )

    # =========================================================================
    # Error Tracking
    # =========================================================================

    error_message = models.TextField(
        blank=True,
        help_text="Error message if training failed"
    )

    error_stage = models.CharField(
        max_length=100,
        blank=True,
        help_text="Pipeline stage where error occurred"
    )

    error_details = models.JSONField(
        default=dict,
        help_text="Detailed error information"
    )

    # =========================================================================
    # Timestamps
    # =========================================================================

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When training started"
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When training completed/failed"
    )

    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When training is scheduled to start"
    )

    duration_seconds = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total training duration in seconds"
    )

    class Meta:
        app_label = 'training'
        ordering = ['-created_at']
        unique_together = ['ml_model', 'run_number']
        verbose_name = 'Training Run'
        verbose_name_plural = 'Training Runs'

    def __str__(self):
        return f"TrainingRun #{self.run_number} - {self.name} ({self.status})"

    @property
    def is_terminal(self):
        """Check if the training run has reached a terminal state."""
        return self.status in [
            self.STATUS_COMPLETED,
            self.STATUS_FAILED,
            self.STATUS_CANCELLED,
            self.STATUS_NOT_BLESSED,
        ]

    @property
    def is_cancellable(self):
        """Check if the training run can be cancelled."""
        return self.status in [
            self.STATUS_SUBMITTING,
            self.STATUS_RUNNING,
        ]

    @property
    def display_name(self):
        """Get a display-friendly name for the training run."""
        return f"Training #{self.run_number}"

    @property
    def elapsed_seconds(self):
        """Calculate elapsed time since training started."""
        if not self.started_at:
            return None
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        from django.utils import timezone
        return int((timezone.now() - self.started_at).total_seconds())
