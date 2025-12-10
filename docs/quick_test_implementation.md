# Quick Test Implementation Plan

## Document Purpose
This document provides a detailed implementation plan for the **Quick Test** functionality in the ML Platform. Quick Tests allow users to validate Feature Configs by running mini TFX pipelines on Vertex AI before committing to full-scale training.

**Created**: 2025-12-10
**Last Updated**: 2025-12-10
**Status**: Planning

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [GCP Infrastructure Setup (Phase 7A)](#phase-7a-gcp-infrastructure-setup)
4. [QuickTest Model (Phase 7B)](#phase-7b-quicktest-model--migrations)
5. [Pipeline Service (Phase 7C)](#phase-7c-pipeline-service)
6. [API Endpoints (Phase 7D)](#phase-7d-api-endpoints)
7. [Pipeline Definition (Phase 7E)](#phase-7e-pipeline-definition-kfp-v2)
8. [UI Components (Phase 7F)](#phase-7f-ui-components)
9. [MLflow Setup (Phase 7G - Deferred)](#phase-7g-mlflow-setup-deferred)
10. [Implementation Checklist](#implementation-checklist)
11. [Confirmed Configuration](#confirmed-configuration)

---

## Overview

### Purpose
Quick Tests enable users to:
1. Validate that generated TFX code (Transform + Trainer) executes correctly
2. Get preliminary metrics (loss, recall@k) on a sample dataset
3. Compare different Feature Configs before full training
4. Iterate rapidly on feature engineering decisions

### Key Principles

1. **Fast Feedback** - Quick Tests should complete in 15-30 minutes
2. **Cost-Effective** - Use smallest viable compute resources (~$1-3 per run)
3. **Non-Destructive** - Artifacts are temporary (7-day retention)
4. **Concurrent** - Multiple Quick Tests can run simultaneously

### Comparison: Quick Test vs Full Training

| Aspect | Quick Test | Full Training |
|--------|------------|---------------|
| Data | Full dataset (future: 10% sample) | Full dataset |
| Compute | n1-standard-4 (no GPU) | n1-highmem-8 + GPU |
| Epochs | 1-15 (user configurable) | 15-50 |
| Duration | 15-30 minutes | 2-6 hours |
| Cost | ~$1-3 | ~$30-100 |
| Artifacts | Temporary (7 days) | Permanent (30 days) |
| Output | Metrics only | SavedModel + artifacts |
| MLflow | Not logged (Phase 1) | Logged |

---

## Architecture

### System Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           QUICK TEST SYSTEM FLOW                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

  User Action                 Django Backend                    GCP Services
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────┐
  │ Click "Run  │
  │ Quick Test" │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐      ┌────────────────────────────────────┐
  │ Quick Test  │─────▶│ POST /api/feature-configs/{id}/    │
  │ Dialog      │      │      quick-test/                   │
  │ (settings)  │      └────────────────┬───────────────────┘
  └─────────────┘                       │
                                        ▼
                       ┌────────────────────────────────────┐
                       │ PipelineService.submit_quick_test()│
                       │                                    │
                       │ 1. Create QuickTest(status=pending)│
                       │ 2. Upload code to GCS              │───────▶ Cloud Storage
                       │ 3. Build pipeline parameters       │         (b2b-recs-quicktest-artifacts)
                       │ 4. Submit to Vertex AI             │───────▶ Vertex AI Pipelines
                       │ 5. Update status=running           │
                       └────────────────┬───────────────────┘
                                        │
                                        ▼
  ┌─────────────┐      ┌────────────────────────────────────┐      ┌──────────────────┐
  │ Progress    │◀─────│ GET /api/quick-tests/{id}/         │◀─────│ Vertex AI API    │
  │ Modal       │ poll │ (every 10 seconds)                 │      │ get_pipeline_job │
  │             │      │                                    │      └──────────────────┘
  │ ✅ Example  │      │ Returns:                           │
  │ ✅ Stats    │      │ - status                           │      ┌──────────────────┐
  │ 🔄 Transform│      │ - current_stage                    │      │ TFX Pipeline     │
  │ ⏳ Trainer  │      │ - stage_details[]                  │      │                  │
  └─────────────┘      │ - progress_percent                 │      │ ExampleGen       │
                       └────────────────────────────────────┘      │ StatisticsGen    │
                                        │                          │ SchemaGen        │
                                        │ on completion            │ Transform        │
                                        ▼                          │ Trainer          │
                       ┌────────────────────────────────────┐      └──────────────────┘
                       │ PipelineService.process_completion()│
                       │                                    │
                       │ 1. Extract metrics from GCS        │◀───── Cloud Storage
                       │ 2. Update QuickTest with results   │       (trainer output)
                       │ 3. Update FeatureConfig best_*     │
                       │ 4. Set status=completed            │
                       └────────────────────────────────────┘
                                        │
                                        ▼
  ┌─────────────┐      ┌────────────────────────────────────┐
  │ Results     │◀─────│ QuickTest record with:             │
  │ Display     │      │ - loss, recall@10/50/100           │
  │             │      │ - vocabulary_stats                 │
  │ Loss: 0.38  │      │ - duration_seconds                 │
  │ R@100: 47%  │      │ - comparison with previous best    │
  └─────────────┘      └────────────────────────────────────┘
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DJANGO APPLICATION                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐          │
│  │ ml_platform/     │    │ ml_platform/     │    │ ml_platform/     │          │
│  │ modeling/        │    │ pipelines/       │    │ models.py        │          │
│  │                  │    │ (NEW)            │    │                  │          │
│  │ - api.py         │    │                  │    │ - FeatureConfig  │          │
│  │ - services.py    │───▶│ - services.py    │───▶│ - QuickTest (NEW)│          │
│  │ (code gen)       │    │ - pipeline.py    │    │                  │          │
│  │                  │    │ - api.py         │    │                  │          │
│  └──────────────────┘    │ - urls.py        │    └──────────────────┘          │
│                          └────────┬─────────┘                                   │
│                                   │                                             │
└───────────────────────────────────┼─────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              GOOGLE CLOUD PLATFORM                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐          │
│  │ Cloud Storage    │    │ Vertex AI        │    │ BigQuery         │          │
│  │                  │    │ Pipelines        │    │                  │          │
│  │ Buckets:         │    │                  │    │ Dataset tables   │          │
│  │ - quicktest-     │◀───│ TFX Pipeline:    │───▶│ (training data)  │          │
│  │   artifacts      │    │ - ExampleGen     │    │                  │          │
│  │ - pipeline-      │    │ - StatisticsGen  │    └──────────────────┘          │
│  │   staging        │    │ - SchemaGen      │                                   │
│  │                  │    │ - Transform      │                                   │
│  │ Contents:        │    │ - Trainer        │                                   │
│  │ - transform.py   │    │                  │                                   │
│  │ - trainer.py     │    │ Machine:         │                                   │
│  │ - metrics.json   │    │ n1-standard-4    │                                   │
│  │ - vocabs/        │    │ (no GPU)         │                                   │
│  └──────────────────┘    └──────────────────┘                                   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 7A: GCP Infrastructure Setup

### Prerequisites
- GCP Project: `b2b-recs`
- Vertex AI API enabled
- Service account: `django-app@b2b-recs.iam.gserviceaccount.com`

### Task 7A.1: Enable Required APIs

```bash
# Enable Vertex AI API (includes Pipelines)
gcloud services enable aiplatform.googleapis.com --project=b2b-recs

# Verify enabled
gcloud services list --enabled --project=b2b-recs | grep aiplatform
```

### Task 7A.2: Add IAM Roles to Service Account

```bash
PROJECT_ID="b2b-recs"
SERVICE_ACCOUNT="django-app@b2b-recs.iam.gserviceaccount.com"

# Vertex AI User - run pipelines, view jobs
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/aiplatform.user"

# Storage Admin - create/manage buckets and objects
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/storage.admin"

# Service Account User - impersonate for pipeline execution
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/iam.serviceAccountUser"
```

### Task 7A.3: Create GCS Buckets

```bash
PROJECT_ID="b2b-recs"
REGION="europe-central2"  # Warsaw, Poland - must match BigQuery and Cloud Run

# Quick Test artifacts bucket (7-day lifecycle)
gsutil mb -p $PROJECT_ID -l $REGION gs://b2b-recs-quicktest-artifacts/
gsutil lifecycle set /dev/stdin gs://b2b-recs-quicktest-artifacts/ << 'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 7}
    }
  ]
}
EOF

# Full Training artifacts bucket (30-day lifecycle)
gsutil mb -p $PROJECT_ID -l $REGION gs://b2b-recs-training-artifacts/
gsutil lifecycle set /dev/stdin gs://b2b-recs-training-artifacts/ << 'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 30}
    }
  ]
}
EOF

# Pipeline staging bucket (working directory, 3-day lifecycle)
gsutil mb -p $PROJECT_ID -l $REGION gs://b2b-recs-pipeline-staging/
gsutil lifecycle set /dev/stdin gs://b2b-recs-pipeline-staging/ << 'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 3}
    }
  ]
}
EOF
```

### Task 7A.4: Add Python Dependencies

Add to `requirements.txt`:

```
# Vertex AI SDK
google-cloud-aiplatform>=1.38.0

# KFP v2 for pipeline definition
kfp>=2.4.0

# TFX for pipeline components
tfx>=1.14.0
```

### Task 7A.5: Update Django Settings

Add to `config/settings.py`:

```python
# =============================================================================
# VERTEX AI PIPELINES CONFIGURATION
# =============================================================================

VERTEX_AI_PROJECT = os.environ.get('GCP_PROJECT_ID', 'b2b-recs')
VERTEX_AI_LOCATION = os.environ.get('VERTEX_AI_LOCATION', 'europe-central2')  # Warsaw

# GCS Buckets
GCS_QUICKTEST_BUCKET = os.environ.get('GCS_QUICKTEST_BUCKET', 'b2b-recs-quicktest-artifacts')
GCS_TRAINING_BUCKET = os.environ.get('GCS_TRAINING_BUCKET', 'b2b-recs-training-artifacts')
GCS_PIPELINE_STAGING_BUCKET = os.environ.get('GCS_PIPELINE_STAGING_BUCKET', 'b2b-recs-pipeline-staging')

# Pipeline defaults
QUICKTEST_MACHINE_TYPE = 'n1-standard-4'  # 4 vCPU, 15GB RAM
QUICKTEST_DEFAULT_EPOCHS = 10
QUICKTEST_DEFAULT_BATCH_SIZE = 4096
QUICKTEST_DEFAULT_LEARNING_RATE = 0.001

# Polling interval for status checks (seconds)
PIPELINE_POLL_INTERVAL = 10
```

### Task 7A.6: Verify Setup

```bash
# Test Vertex AI access
python -c "
from google.cloud import aiplatform
aiplatform.init(project='b2b-recs', location='europe-central2')
print('Vertex AI initialized successfully')
"

# Test GCS access
python -c "
from google.cloud import storage
client = storage.Client(project='b2b-recs')
bucket = client.bucket('b2b-recs-quicktest-artifacts')
print(f'Bucket exists: {bucket.exists()}')
"
```

---

## Phase 7B: QuickTest Model & Migrations

### Task 7B.1: Create QuickTest Model

Add to `ml_platform/models.py`:

```python
class QuickTest(models.Model):
    """
    Tracks Quick Test pipeline runs for Feature Configs.
    Quick Tests validate feature engineering by running a mini TFX pipeline.
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
        'FeatureConfig',
        on_delete=models.CASCADE,
        related_name='quick_tests',
        help_text="Feature Config being tested"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who initiated the test"
    )

    # =========================================================================
    # Test Configuration
    # =========================================================================

    # Data settings (future: sampling)
    data_sample_percent = models.IntegerField(
        default=100,
        help_text="Percentage of dataset to use (100 = full, future: 5/10/25)"
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
    # Example:
    # [
    #   {"name": "ExampleGen", "status": "completed", "duration_seconds": 120},
    #   {"name": "StatisticsGen", "status": "completed", "duration_seconds": 45},
    #   {"name": "SchemaGen", "status": "completed", "duration_seconds": 10},
    #   {"name": "Transform", "status": "running", "duration_seconds": null},
    #   {"name": "Trainer", "status": "pending", "duration_seconds": null}
    # ]

    # =========================================================================
    # Results
    # =========================================================================

    # Training metrics
    loss = models.FloatField(
        null=True,
        blank=True,
        help_text="Final training loss"
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

    # Vocabulary statistics
    vocabulary_stats = models.JSONField(
        default=dict,
        help_text="Vocabulary sizes and OOV rates per feature"
    )
    # Example:
    # {
    #   "customer_id": {"vocab_size": 9823, "oov_rate": 0.012},
    #   "product_id": {"vocab_size": 3612, "oov_rate": 0.008},
    #   "city": {"vocab_size": 28, "oov_rate": 0.0}
    # }

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
    # Example: gs://b2b-recs-quicktest-artifacts/quicktest-42/

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
    def elapsed_seconds(self):
        """Calculate elapsed time for running tests."""
        if self.started_at:
            if self.completed_at:
                return (self.completed_at - self.started_at).total_seconds()
            else:
                from django.utils import timezone
                return (timezone.now() - self.started_at).total_seconds()
        return None

    def update_from_vertex_status(self, vertex_status):
        """
        Update model fields from Vertex AI pipeline status response.
        Called by the polling service.
        """
        # Implementation in PipelineService
        pass

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
```

### Task 7B.2: Update FeatureConfig Model

Add method to `FeatureConfig` class:

```python
def update_best_metrics(self, quick_test):
    """Update best metrics if this quick test improved them."""
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
```

### Task 7B.3: Create Migration

```bash
python manage.py makemigrations ml_platform --name add_quicktest_model
python manage.py migrate
```

---

## Phase 7C: Pipeline Service

### Task 7C.1: Create Pipeline Module Structure

```
ml_platform/pipelines/
├── __init__.py
├── services.py           # PipelineService class
├── pipeline_builder.py   # KFP v2 pipeline definition
├── api.py                # API views
├── urls.py               # URL routing
└── constants.py          # Pipeline constants
```

### Task 7C.2: Implement PipelineService

File: `ml_platform/pipelines/services.py`

```python
"""
Pipeline Service for submitting and monitoring Vertex AI pipelines.
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from django.conf import settings
from django.utils import timezone
from google.cloud import aiplatform
from google.cloud import storage

from ml_platform.models import QuickTest, FeatureConfig

logger = logging.getLogger(__name__)


class PipelineService:
    """
    Service for managing Vertex AI Pipeline execution.

    Responsibilities:
    - Upload generated code to GCS
    - Submit pipelines to Vertex AI
    - Poll pipeline status
    - Extract and store results
    """

    def __init__(self):
        self.project = settings.VERTEX_AI_PROJECT
        self.location = settings.VERTEX_AI_LOCATION
        self.quicktest_bucket = settings.GCS_QUICKTEST_BUCKET
        self.staging_bucket = settings.GCS_PIPELINE_STAGING_BUCKET

        # Initialize clients
        aiplatform.init(project=self.project, location=self.location)
        self.storage_client = storage.Client(project=self.project)

    # =========================================================================
    # Quick Test Submission
    # =========================================================================

    def submit_quick_test(
        self,
        feature_config: FeatureConfig,
        epochs: int = 10,
        batch_size: int = 4096,
        learning_rate: float = 0.001,
        user=None
    ) -> QuickTest:
        """
        Submit a Quick Test pipeline to Vertex AI.

        Args:
            feature_config: The FeatureConfig to test
            epochs: Number of training epochs
            batch_size: Training batch size
            learning_rate: Learning rate
            user: User who initiated the test

        Returns:
            QuickTest instance with pipeline job info
        """
        # Create QuickTest record
        quick_test = QuickTest.objects.create(
            feature_config=feature_config,
            created_by=user,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            status=QuickTest.STATUS_PENDING,
            stage_details=self._initial_stage_details()
        )

        try:
            # Update status to submitting
            quick_test.status = QuickTest.STATUS_SUBMITTING
            quick_test.save(update_fields=['status'])

            # 1. Upload generated code to GCS
            gcs_path = self._upload_code_to_gcs(feature_config, quick_test)
            quick_test.gcs_artifacts_path = gcs_path

            # 2. Build pipeline parameters
            pipeline_params = self._build_pipeline_params(
                feature_config=feature_config,
                quick_test=quick_test,
                gcs_path=gcs_path
            )

            # 3. Submit to Vertex AI
            job = self._submit_pipeline(pipeline_params, quick_test)

            # 4. Update QuickTest with job info
            quick_test.vertex_pipeline_job_name = job.resource_name
            quick_test.vertex_pipeline_job_id = job.name
            quick_test.status = QuickTest.STATUS_RUNNING
            quick_test.submitted_at = timezone.now()
            quick_test.save()

            logger.info(f"QuickTest {quick_test.pk} submitted: {job.resource_name}")
            return quick_test

        except Exception as e:
            logger.exception(f"Failed to submit QuickTest {quick_test.pk}")
            quick_test.status = QuickTest.STATUS_FAILED
            quick_test.error_message = str(e)
            quick_test.completed_at = timezone.now()
            quick_test.save()
            raise

    def _initial_stage_details(self) -> list:
        """Create initial stage details structure."""
        return [
            {"name": "ExampleGen", "status": "pending", "duration_seconds": None},
            {"name": "StatisticsGen", "status": "pending", "duration_seconds": None},
            {"name": "SchemaGen", "status": "pending", "duration_seconds": None},
            {"name": "Transform", "status": "pending", "duration_seconds": None},
            {"name": "Trainer", "status": "pending", "duration_seconds": None},
        ]

    def _upload_code_to_gcs(
        self,
        feature_config: FeatureConfig,
        quick_test: QuickTest
    ) -> str:
        """
        Upload Transform and Trainer code to GCS.

        Returns:
            GCS path prefix (e.g., gs://bucket/quicktest-42/)
        """
        bucket = self.storage_client.bucket(self.quicktest_bucket)
        prefix = f"quicktest-{quick_test.pk}"

        # Upload Transform code
        transform_blob = bucket.blob(f"{prefix}/transform_module.py")
        transform_blob.upload_from_string(
            feature_config.generated_transform_code,
            content_type='text/x-python'
        )

        # Upload Trainer code
        trainer_blob = bucket.blob(f"{prefix}/trainer_module.py")
        trainer_blob.upload_from_string(
            feature_config.generated_trainer_code,
            content_type='text/x-python'
        )

        gcs_path = f"gs://{self.quicktest_bucket}/{prefix}"
        logger.info(f"Uploaded code to {gcs_path}")
        return gcs_path

    def _build_pipeline_params(
        self,
        feature_config: FeatureConfig,
        quick_test: QuickTest,
        gcs_path: str
    ) -> Dict[str, Any]:
        """Build parameters for the pipeline."""
        dataset = feature_config.dataset

        # Generate the SQL query from dataset configuration
        # This uses the existing BigQueryService that handles joins, filters, etc.
        from ml_platform.datasets.services import BigQueryService
        bq_service = BigQueryService(dataset.model_endpoint)
        query_sql = bq_service.generate_query(dataset)

        return {
            # Data source - SQL query instead of direct table reference
            "bigquery_project": self.project,
            "bigquery_query": query_sql,  # Generated SQL with joins and filters

            # Module paths
            "transform_module_path": f"{gcs_path}/transform_module.py",
            "trainer_module_path": f"{gcs_path}/trainer_module.py",

            # Training params
            "epochs": quick_test.epochs,
            "batch_size": quick_test.batch_size,
            "learning_rate": quick_test.learning_rate,

            # Output paths
            "output_path": gcs_path,
            "pipeline_root": f"gs://{self.staging_bucket}/runs/quicktest-{quick_test.pk}",

            # Compute settings
            "machine_type": settings.QUICKTEST_MACHINE_TYPE,
        }

    def _submit_pipeline(
        self,
        params: Dict[str, Any],
        quick_test: QuickTest
    ) -> aiplatform.PipelineJob:
        """Submit pipeline to Vertex AI."""
        # TODO: Implement with compiled pipeline
        # For now, placeholder that will be replaced in Phase 7E
        raise NotImplementedError("Pipeline submission will be implemented in Phase 7E")

    # =========================================================================
    # Status Polling
    # =========================================================================

    def get_pipeline_status(self, quick_test: QuickTest) -> Dict[str, Any]:
        """
        Get current status of a pipeline from Vertex AI.

        Returns:
            Dict with status, stages, and progress info
        """
        if not quick_test.vertex_pipeline_job_name:
            return {
                "status": quick_test.status,
                "current_stage": quick_test.current_stage,
                "progress_percent": quick_test.progress_percent,
                "stage_details": quick_test.stage_details,
            }

        try:
            job = aiplatform.PipelineJob.get(quick_test.vertex_pipeline_job_name)

            # Parse job state
            state = job.state.name  # e.g., "PIPELINE_STATE_RUNNING"

            # Map Vertex AI state to our status
            status_map = {
                "PIPELINE_STATE_PENDING": QuickTest.STATUS_PENDING,
                "PIPELINE_STATE_RUNNING": QuickTest.STATUS_RUNNING,
                "PIPELINE_STATE_SUCCEEDED": QuickTest.STATUS_COMPLETED,
                "PIPELINE_STATE_FAILED": QuickTest.STATUS_FAILED,
                "PIPELINE_STATE_CANCELLED": QuickTest.STATUS_CANCELLED,
            }

            new_status = status_map.get(state, quick_test.status)

            # Parse task details for stage progress
            stage_details = self._parse_task_details(job)
            current_stage = self._determine_current_stage(stage_details)

            return {
                "status": new_status,
                "current_stage": current_stage,
                "progress_percent": self._calculate_progress(stage_details),
                "stage_details": stage_details,
                "vertex_state": state,
            }

        except Exception as e:
            logger.exception(f"Failed to get status for QuickTest {quick_test.pk}")
            return {
                "status": quick_test.status,
                "current_stage": quick_test.current_stage,
                "progress_percent": quick_test.progress_percent,
                "stage_details": quick_test.stage_details,
                "error": str(e)
            }

    def _parse_task_details(self, job) -> list:
        """Parse Vertex AI job task details into our stage format."""
        # Map component names to our stage names
        component_map = {
            "examplegen": "ExampleGen",
            "statisticsgen": "StatisticsGen",
            "schemagen": "SchemaGen",
            "transform": "Transform",
            "trainer": "Trainer",
        }

        stages = []
        task_details = job.task_details or []

        for task in task_details:
            component_name = task.task_name.lower()

            for key, stage_name in component_map.items():
                if key in component_name:
                    state = task.state.name if task.state else "pending"

                    # Map task state to our status
                    if "SUCCEEDED" in state:
                        status = "completed"
                    elif "RUNNING" in state:
                        status = "running"
                    elif "FAILED" in state:
                        status = "failed"
                    else:
                        status = "pending"

                    # Calculate duration
                    duration = None
                    if task.start_time and task.end_time:
                        duration = int((task.end_time - task.start_time).total_seconds())

                    stages.append({
                        "name": stage_name,
                        "status": status,
                        "duration_seconds": duration,
                        "error": task.error.message if hasattr(task, 'error') and task.error else None
                    })
                    break

        # Ensure all stages are present
        stage_names = [s["name"] for s in stages]
        for stage_name in ["ExampleGen", "StatisticsGen", "SchemaGen", "Transform", "Trainer"]:
            if stage_name not in stage_names:
                stages.append({
                    "name": stage_name,
                    "status": "pending",
                    "duration_seconds": None
                })

        # Sort by expected order
        order = ["ExampleGen", "StatisticsGen", "SchemaGen", "Transform", "Trainer"]
        stages.sort(key=lambda s: order.index(s["name"]) if s["name"] in order else 99)

        return stages

    def _determine_current_stage(self, stage_details: list) -> str:
        """Determine current stage from stage details."""
        for stage in stage_details:
            if stage["status"] == "running":
                return stage["name"].lower()
            if stage["status"] == "failed":
                return "failed"

        # Check if all completed
        if all(s["status"] == "completed" for s in stage_details):
            return "completed"

        return "pending"

    def _calculate_progress(self, stage_details: list) -> int:
        """Calculate progress percentage from stage details."""
        weights = {
            "ExampleGen": 20,
            "StatisticsGen": 10,
            "SchemaGen": 5,
            "Transform": 25,
            "Trainer": 40,
        }

        total = sum(weights.values())
        completed = 0

        for stage in stage_details:
            weight = weights.get(stage["name"], 0)
            if stage["status"] == "completed":
                completed += weight
            elif stage["status"] == "running":
                completed += weight * 0.5

        return int((completed / total) * 100)

    # =========================================================================
    # Results Extraction
    # =========================================================================

    def extract_results(self, quick_test: QuickTest) -> Dict[str, Any]:
        """
        Extract results from completed pipeline.

        Reads metrics from GCS output location.
        """
        if not quick_test.gcs_artifacts_path:
            return {}

        try:
            # Read metrics.json from GCS
            bucket_name = quick_test.gcs_artifacts_path.replace("gs://", "").split("/")[0]
            prefix = "/".join(quick_test.gcs_artifacts_path.replace("gs://", "").split("/")[1:])

            bucket = self.storage_client.bucket(bucket_name)
            metrics_blob = bucket.blob(f"{prefix}/metrics.json")

            if metrics_blob.exists():
                metrics_content = metrics_blob.download_as_string()
                metrics = json.loads(metrics_content)

                return {
                    "loss": metrics.get("loss"),
                    "recall_at_10": metrics.get("recall_at_10"),
                    "recall_at_50": metrics.get("recall_at_50"),
                    "recall_at_100": metrics.get("recall_at_100"),
                    "vocabulary_stats": metrics.get("vocabulary_stats", {}),
                }

            return {}

        except Exception as e:
            logger.exception(f"Failed to extract results for QuickTest {quick_test.pk}")
            return {"error": str(e)}

    # =========================================================================
    # Pipeline Management
    # =========================================================================

    def cancel_pipeline(self, quick_test: QuickTest) -> bool:
        """Cancel a running pipeline."""
        if not quick_test.vertex_pipeline_job_name:
            return False

        try:
            job = aiplatform.PipelineJob.get(quick_test.vertex_pipeline_job_name)
            job.cancel()

            quick_test.status = QuickTest.STATUS_CANCELLED
            quick_test.completed_at = timezone.now()
            quick_test.save()

            logger.info(f"Cancelled QuickTest {quick_test.pk}")
            return True

        except Exception as e:
            logger.exception(f"Failed to cancel QuickTest {quick_test.pk}")
            return False

    def update_quick_test_status(self, quick_test: QuickTest) -> QuickTest:
        """
        Update QuickTest from Vertex AI status.
        Called by polling mechanism.
        """
        if quick_test.is_terminal:
            return quick_test

        status_info = self.get_pipeline_status(quick_test)

        # Update fields
        quick_test.status = status_info["status"]
        quick_test.current_stage = status_info["current_stage"]
        quick_test.progress_percent = status_info["progress_percent"]
        quick_test.stage_details = status_info["stage_details"]

        # If completed, extract results
        if quick_test.status == QuickTest.STATUS_COMPLETED:
            quick_test.completed_at = timezone.now()
            if quick_test.started_at:
                quick_test.duration_seconds = int(
                    (quick_test.completed_at - quick_test.started_at).total_seconds()
                )

            results = self.extract_results(quick_test)
            quick_test.loss = results.get("loss")
            quick_test.recall_at_10 = results.get("recall_at_10")
            quick_test.recall_at_50 = results.get("recall_at_50")
            quick_test.recall_at_100 = results.get("recall_at_100")
            quick_test.vocabulary_stats = results.get("vocabulary_stats", {})

            # Update FeatureConfig best metrics
            quick_test.feature_config.update_best_metrics(quick_test)

        elif quick_test.status == QuickTest.STATUS_FAILED:
            quick_test.completed_at = timezone.now()
            # Error message from stage details
            for stage in quick_test.stage_details:
                if stage.get("status") == "failed" and stage.get("error"):
                    quick_test.error_message = stage["error"]
                    quick_test.error_stage = stage["name"]
                    break

        quick_test.save()
        return quick_test
```

---

## Phase 7D: API Endpoints

### Task 7D.1: Create API Views

File: `ml_platform/pipelines/api.py`

```python
"""
API endpoints for Quick Test pipeline management.
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from ml_platform.models import FeatureConfig, QuickTest
from ml_platform.pipelines.services import PipelineService

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def start_quick_test(request, config_id):
    """
    Start a Quick Test for a Feature Config.

    POST /api/feature-configs/{config_id}/quick-test/

    Request body:
    {
        "epochs": 10,
        "batch_size": 4096,
        "learning_rate": 0.001
    }

    Response:
    {
        "success": true,
        "data": {
            "quick_test_id": 42,
            "status": "submitting",
            ...
        }
    }
    """
    try:
        feature_config = FeatureConfig.objects.get(pk=config_id)
    except FeatureConfig.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Feature Config not found"
        }, status=404)

    # Validate generated code exists
    if not feature_config.generated_transform_code or not feature_config.generated_trainer_code:
        return JsonResponse({
            "success": False,
            "error": "Generated code not found. Please regenerate code first."
        }, status=400)

    # Parse request body
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    epochs = body.get("epochs", 10)
    batch_size = body.get("batch_size", 4096)
    learning_rate = body.get("learning_rate", 0.001)

    # Validate parameters
    if not (1 <= epochs <= 15):
        return JsonResponse({
            "success": False,
            "error": "Epochs must be between 1 and 15"
        }, status=400)

    if batch_size not in [1024, 2048, 4096, 8192]:
        return JsonResponse({
            "success": False,
            "error": "Batch size must be 1024, 2048, 4096, or 8192"
        }, status=400)

    # Submit quick test
    try:
        service = PipelineService()
        quick_test = service.submit_quick_test(
            feature_config=feature_config,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            user=request.user
        )

        return JsonResponse({
            "success": True,
            "data": _serialize_quick_test(quick_test)
        })

    except Exception as e:
        logger.exception(f"Failed to start Quick Test for config {config_id}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_quick_test(request, test_id):
    """
    Get Quick Test status and results.

    GET /api/quick-tests/{test_id}/

    Response:
    {
        "success": true,
        "data": {
            "id": 42,
            "status": "running",
            "progress_percent": 65,
            "current_stage": "Transform",
            "stages": [...],
            ...
        }
    }
    """
    try:
        quick_test = QuickTest.objects.select_related('feature_config').get(pk=test_id)
    except QuickTest.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Quick Test not found"
        }, status=404)

    # If still running, update status from Vertex AI
    if not quick_test.is_terminal:
        try:
            service = PipelineService()
            quick_test = service.update_quick_test_status(quick_test)
        except Exception as e:
            logger.warning(f"Failed to update QuickTest {test_id} status: {e}")

    return JsonResponse({
        "success": True,
        "data": _serialize_quick_test(quick_test)
    })


@login_required
@require_http_methods(["POST"])
def cancel_quick_test(request, test_id):
    """
    Cancel a running Quick Test.

    POST /api/quick-tests/{test_id}/cancel/
    """
    try:
        quick_test = QuickTest.objects.get(pk=test_id)
    except QuickTest.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Quick Test not found"
        }, status=404)

    if quick_test.is_terminal:
        return JsonResponse({
            "success": False,
            "error": f"Quick Test is already {quick_test.status}"
        }, status=400)

    try:
        service = PipelineService()
        success = service.cancel_pipeline(quick_test)

        return JsonResponse({
            "success": success,
            "data": _serialize_quick_test(quick_test) if success else None,
            "error": None if success else "Failed to cancel pipeline"
        })

    except Exception as e:
        logger.exception(f"Failed to cancel QuickTest {test_id}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_quick_tests(request, config_id):
    """
    List all Quick Tests for a Feature Config.

    GET /api/feature-configs/{config_id}/quick-tests/
    """
    try:
        feature_config = FeatureConfig.objects.get(pk=config_id)
    except FeatureConfig.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Feature Config not found"
        }, status=404)

    quick_tests = QuickTest.objects.filter(
        feature_config=feature_config
    ).order_by('-created_at')[:20]  # Limit to 20 most recent

    return JsonResponse({
        "success": True,
        "data": [_serialize_quick_test(qt) for qt in quick_tests]
    })


def _serialize_quick_test(quick_test: QuickTest) -> dict:
    """Serialize QuickTest to JSON-compatible dict."""
    return {
        "id": quick_test.pk,
        "feature_config_id": quick_test.feature_config_id,
        "feature_config_name": quick_test.feature_config.name,

        # Configuration
        "epochs": quick_test.epochs,
        "batch_size": quick_test.batch_size,
        "learning_rate": quick_test.learning_rate,
        "data_sample_percent": quick_test.data_sample_percent,

        # Status
        "status": quick_test.status,
        "current_stage": quick_test.current_stage,
        "progress_percent": quick_test.progress_percent,
        "stage_details": quick_test.stage_details,

        # Results
        "loss": quick_test.loss,
        "recall_at_10": quick_test.recall_at_10,
        "recall_at_50": quick_test.recall_at_50,
        "recall_at_100": quick_test.recall_at_100,
        "vocabulary_stats": quick_test.vocabulary_stats,

        # Error info
        "error_message": quick_test.error_message,
        "error_stage": quick_test.error_stage,

        # Timestamps
        "created_at": quick_test.created_at.isoformat() if quick_test.created_at else None,
        "submitted_at": quick_test.submitted_at.isoformat() if quick_test.submitted_at else None,
        "started_at": quick_test.started_at.isoformat() if quick_test.started_at else None,
        "completed_at": quick_test.completed_at.isoformat() if quick_test.completed_at else None,
        "duration_seconds": quick_test.duration_seconds,
        "elapsed_seconds": quick_test.elapsed_seconds,

        # Vertex AI
        "vertex_pipeline_job_id": quick_test.vertex_pipeline_job_id,
    }
```

### Task 7D.2: Create URL Routes

File: `ml_platform/pipelines/urls.py`

```python
from django.urls import path
from . import api

urlpatterns = [
    # Quick Test endpoints
    path(
        'api/feature-configs/<int:config_id>/quick-test/',
        api.start_quick_test,
        name='start_quick_test'
    ),
    path(
        'api/feature-configs/<int:config_id>/quick-tests/',
        api.list_quick_tests,
        name='list_quick_tests'
    ),
    path(
        'api/quick-tests/<int:test_id>/',
        api.get_quick_test,
        name='get_quick_test'
    ),
    path(
        'api/quick-tests/<int:test_id>/cancel/',
        api.cancel_quick_test,
        name='cancel_quick_test'
    ),
]
```

### Task 7D.3: Register URLs

Add to `ml_platform/urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... existing patterns ...
    path('', include('ml_platform.pipelines.urls')),
]
```

---

## Phase 7E: Pipeline Definition (KFP v2)

### Task 7E.1: Create Pipeline Builder

File: `ml_platform/pipelines/pipeline_builder.py`

```python
"""
KFP v2 Pipeline definition for Quick Tests.

This module defines the TFX pipeline that runs on Vertex AI.
"""
from typing import Optional
from kfp import dsl
from kfp.dsl import component, Output, Input, Artifact, Dataset, Model
from google_cloud_pipeline_components.v1.bigquery import BigqueryQueryJobOp


# Component definitions will be added here
# Each TFX component will be wrapped as a KFP component

@dsl.pipeline(
    name="quicktest-tfx-pipeline",
    description="Quick Test TFX pipeline for TFRS model validation"
)
def quicktest_pipeline(
    # Data source
    bigquery_project: str,
    bigquery_dataset: str,
    bigquery_table: str,

    # Module paths
    transform_module_path: str,
    trainer_module_path: str,

    # Training params
    epochs: int = 10,
    batch_size: int = 4096,
    learning_rate: float = 0.001,

    # Output
    output_path: str = "",
):
    """
    TFX Pipeline for Quick Tests.

    Components:
    1. ExampleGen - Read data from BigQuery
    2. StatisticsGen - Compute dataset statistics
    3. SchemaGen - Infer schema
    4. Transform - Apply preprocessing_fn
    5. Trainer - Train TFRS model
    """
    # TODO: Implement full pipeline in Phase 7E
    # This is the skeleton that will be filled in
    pass


def compile_pipeline(output_path: str = "quicktest_pipeline.json"):
    """Compile the pipeline to JSON for Vertex AI."""
    from kfp import compiler
    compiler.Compiler().compile(
        pipeline_func=quicktest_pipeline,
        package_path=output_path
    )
    return output_path
```

### Task 7E.2: TFX Component Wrappers

This will be implemented during the actual development phase. Each TFX component needs to be wrapped as a KFP component:

1. **ExampleGen** - BigQuery to TFRecords
2. **StatisticsGen** - TFDV statistics
3. **SchemaGen** - Schema inference
4. **Transform** - TFT with custom preprocessing_fn
5. **Trainer** - Custom trainer module

### Task 7E.3: Update PipelineService._submit_pipeline

Once the pipeline is compiled, update the service to submit it:

```python
def _submit_pipeline(
    self,
    params: Dict[str, Any],
    quick_test: QuickTest
) -> aiplatform.PipelineJob:
    """Submit compiled pipeline to Vertex AI."""

    # Load compiled pipeline template
    # Option 1: Compile on-the-fly
    # Option 2: Use pre-compiled template from GCS

    job = aiplatform.PipelineJob(
        display_name=f"quicktest-{quick_test.pk}",
        template_path="quicktest_pipeline.json",  # or GCS path
        parameter_values=params,
        pipeline_root=params["pipeline_root"],
    )

    job.submit(
        service_account=f"django-app@{self.project}.iam.gserviceaccount.com"
    )

    return job
```

---

## Phase 7F: UI Components

### Task 7F.1: Quick Test Button on Feature Config Card

Add to Feature Config card in `templates/ml_platform/model_modeling.html`:

```html
<button class="btn btn-sm btn-primary"
        onclick="openQuickTestDialog(${config.id})"
        ${!config.generated_transform_code ? 'disabled' : ''}>
    <i class="fas fa-play"></i> Quick Test
</button>
```

### Task 7F.2: Quick Test Dialog

```html
<!-- Quick Test Dialog Modal -->
<div class="modal fade" id="quickTestDialog" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">
                    Quick Test: <span id="qtConfigName"></span>
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <h6>Training Parameters</h6>

                <div class="mb-3">
                    <label class="form-label">Epochs</label>
                    <select class="form-select" id="qtEpochs">
                        <option value="1">1</option>
                        <option value="2">2</option>
                        <option value="5">5</option>
                        <option value="10" selected>10</option>
                        <option value="15">15</option>
                    </select>
                </div>

                <div class="mb-3">
                    <label class="form-label">Batch Size</label>
                    <select class="form-select" id="qtBatchSize">
                        <option value="1024">1024</option>
                        <option value="2048">2048</option>
                        <option value="4096" selected>4096</option>
                        <option value="8192">8192</option>
                    </select>
                </div>

                <div class="mb-3">
                    <label class="form-label">Learning Rate</label>
                    <input type="number" class="form-control" id="qtLearningRate"
                           value="0.001" step="0.0001" min="0.0001" max="0.1">
                </div>

                <hr>

                <div class="text-muted small">
                    <p><strong>Estimated duration:</strong> 15-25 minutes</p>
                    <p><strong>Machine type:</strong> n1-standard-4 (4 vCPU, 15GB RAM)</p>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                    Cancel
                </button>
                <button type="button" class="btn btn-primary" onclick="startQuickTest()">
                    <i class="fas fa-play"></i> Start Quick Test
                </button>
            </div>
        </div>
    </div>
</div>
```

### Task 7F.3: Progress Modal

```html
<!-- Quick Test Progress Modal -->
<div class="modal fade" id="quickTestProgress" tabindex="-1" data-bs-backdrop="static">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Quick Test Running</h5>
            </div>
            <div class="modal-body">
                <!-- Progress bar -->
                <div class="progress mb-3" style="height: 24px;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated"
                         id="qtProgressBar" style="width: 0%">
                        <span id="qtProgressText">0%</span>
                    </div>
                </div>

                <!-- Pipeline stages -->
                <h6>Pipeline Stages</h6>
                <div id="qtStages">
                    <!-- Populated by JavaScript -->
                </div>

                <!-- Elapsed time -->
                <div class="mt-3 text-muted">
                    <span>Elapsed: </span>
                    <span id="qtElapsed">0:00</span>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-danger" onclick="cancelQuickTest()">
                    Cancel Test
                </button>
            </div>
        </div>
    </div>
</div>
```

### Task 7F.4: Results Modal

```html
<!-- Quick Test Results Modal -->
<div class="modal fade" id="quickTestResults" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">
                    <span id="qtrStatus"></span> Quick Test Results
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <!-- Metrics -->
                <h6>Metrics</h6>
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Metric</th>
                            <th>Value</th>
                            <th>vs Previous Best</th>
                        </tr>
                    </thead>
                    <tbody id="qtrMetrics">
                        <!-- Populated by JavaScript -->
                    </tbody>
                </table>

                <!-- Vocabulary Stats -->
                <h6 class="mt-4">Vocabulary Statistics</h6>
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Feature</th>
                            <th>Vocab Size</th>
                            <th>OOV Rate</th>
                        </tr>
                    </thead>
                    <tbody id="qtrVocabStats">
                        <!-- Populated by JavaScript -->
                    </tbody>
                </table>

                <!-- Duration -->
                <div class="mt-3 text-muted">
                    Duration: <span id="qtrDuration"></span>
                </div>
            </div>
            <div class="modal-footer">
                <a href="#" id="qtrVertexLink" target="_blank" class="btn btn-outline-secondary">
                    View in Vertex AI
                </a>
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                    Close
                </button>
            </div>
        </div>
    </div>
</div>
```

### Task 7F.5: JavaScript Functions

```javascript
// Quick Test state
let currentQuickTestId = null;
let currentConfigId = null;
let pollInterval = null;

function openQuickTestDialog(configId) {
    currentConfigId = configId;
    const config = featureConfigs.find(c => c.id === configId);
    document.getElementById('qtConfigName').textContent = config.name;
    new bootstrap.Modal(document.getElementById('quickTestDialog')).show();
}

async function startQuickTest() {
    const epochs = parseInt(document.getElementById('qtEpochs').value);
    const batchSize = parseInt(document.getElementById('qtBatchSize').value);
    const learningRate = parseFloat(document.getElementById('qtLearningRate').value);

    // Close dialog
    bootstrap.Modal.getInstance(document.getElementById('quickTestDialog')).hide();

    // Show progress modal
    const progressModal = new bootstrap.Modal(document.getElementById('quickTestProgress'));
    progressModal.show();

    try {
        const response = await fetch(`/api/feature-configs/${currentConfigId}/quick-test/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ epochs, batch_size: batchSize, learning_rate: learningRate })
        });

        const data = await response.json();

        if (data.success) {
            currentQuickTestId = data.data.id;
            updateProgressUI(data.data);
            startPolling();
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        progressModal.hide();
        alert('Failed to start Quick Test: ' + error.message);
    }
}

function startPolling() {
    pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/quick-tests/${currentQuickTestId}/`);
            const data = await response.json();

            if (data.success) {
                updateProgressUI(data.data);

                if (['completed', 'failed', 'cancelled'].includes(data.data.status)) {
                    stopPolling();
                    showResults(data.data);
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 10000); // Poll every 10 seconds
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

function updateProgressUI(quickTest) {
    // Update progress bar
    document.getElementById('qtProgressBar').style.width = quickTest.progress_percent + '%';
    document.getElementById('qtProgressText').textContent = quickTest.progress_percent + '%';

    // Update stages
    const stagesHtml = quickTest.stage_details.map(stage => {
        let icon, color;
        switch (stage.status) {
            case 'completed':
                icon = 'check-circle';
                color = 'text-success';
                break;
            case 'running':
                icon = 'spinner fa-spin';
                color = 'text-primary';
                break;
            case 'failed':
                icon = 'times-circle';
                color = 'text-danger';
                break;
            default:
                icon = 'clock';
                color = 'text-muted';
        }

        const duration = stage.duration_seconds
            ? ` (${formatDuration(stage.duration_seconds)})`
            : '';

        return `
            <div class="d-flex align-items-center mb-2">
                <i class="fas fa-${icon} ${color} me-2"></i>
                <span>${stage.name}</span>
                <span class="ms-auto text-muted small">${duration}</span>
            </div>
        `;
    }).join('');

    document.getElementById('qtStages').innerHTML = stagesHtml;

    // Update elapsed time
    if (quickTest.elapsed_seconds) {
        document.getElementById('qtElapsed').textContent = formatDuration(quickTest.elapsed_seconds);
    }
}

function showResults(quickTest) {
    // Hide progress modal
    bootstrap.Modal.getInstance(document.getElementById('quickTestProgress')).hide();

    // Show results modal
    const resultsModal = new bootstrap.Modal(document.getElementById('quickTestResults'));

    // Status badge
    const statusBadge = quickTest.status === 'completed'
        ? '<span class="badge bg-success">Success</span>'
        : '<span class="badge bg-danger">Failed</span>';
    document.getElementById('qtrStatus').innerHTML = statusBadge;

    // Metrics table
    if (quickTest.status === 'completed') {
        const metricsHtml = `
            <tr>
                <td>Loss</td>
                <td>${quickTest.loss?.toFixed(4) || 'N/A'}</td>
                <td>-</td>
            </tr>
            <tr>
                <td>Recall@10</td>
                <td>${(quickTest.recall_at_10 * 100)?.toFixed(2)}%</td>
                <td>-</td>
            </tr>
            <tr>
                <td>Recall@50</td>
                <td>${(quickTest.recall_at_50 * 100)?.toFixed(2)}%</td>
                <td>-</td>
            </tr>
            <tr>
                <td>Recall@100</td>
                <td>${(quickTest.recall_at_100 * 100)?.toFixed(2)}%</td>
                <td>-</td>
            </tr>
        `;
        document.getElementById('qtrMetrics').innerHTML = metricsHtml;

        // Vocab stats
        const vocabHtml = Object.entries(quickTest.vocabulary_stats || {}).map(([feature, stats]) => `
            <tr>
                <td>${feature}</td>
                <td>${stats.vocab_size?.toLocaleString() || 'N/A'}</td>
                <td>${(stats.oov_rate * 100)?.toFixed(2)}%</td>
            </tr>
        `).join('');
        document.getElementById('qtrVocabStats').innerHTML = vocabHtml || '<tr><td colspan="3">No data</td></tr>';
    } else {
        document.getElementById('qtrMetrics').innerHTML = `
            <tr>
                <td colspan="3" class="text-danger">
                    ${quickTest.error_message || 'Unknown error'}
                </td>
            </tr>
        `;
    }

    // Duration
    document.getElementById('qtrDuration').textContent = formatDuration(quickTest.duration_seconds);

    // Vertex AI link
    if (quickTest.vertex_pipeline_job_id) {
        const link = `https://console.cloud.google.com/vertex-ai/pipelines/runs/${quickTest.vertex_pipeline_job_id}?project=b2b-recs`;
        document.getElementById('qtrVertexLink').href = link;
    }

    resultsModal.show();
}

async function cancelQuickTest() {
    if (!currentQuickTestId) return;

    try {
        const response = await fetch(`/api/quick-tests/${currentQuickTestId}/cancel/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.success) {
            stopPolling();
            bootstrap.Modal.getInstance(document.getElementById('quickTestProgress')).hide();
            alert('Quick Test cancelled');
        }
    } catch (error) {
        alert('Failed to cancel: ' + error.message);
    }
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}
```

---

## Phase 7G: MLflow Setup (Deferred)

**Status:** Deferred to a later phase.

For now, metrics are stored directly in the QuickTest model. MLflow integration will be added when:
1. Quick Tests are working end-to-end
2. Full Training is implemented
3. Experiment comparison features are needed

### Future MLflow Architecture

When implemented, MLflow will:
- Run on Cloud Run as a separate service
- Use Cloud SQL for tracking store
- Use GCS for artifact store
- Be integrated into Trainer module to log metrics

---

## Implementation Checklist

### Phase 7A: GCP Infrastructure
- [ ] Enable Vertex AI API
- [ ] Add IAM roles to service account
- [ ] Create GCS buckets with lifecycle policies
- [ ] Add google-cloud-aiplatform to requirements
- [ ] Update Django settings
- [ ] Verify setup with test scripts

### Phase 7B: QuickTest Model
- [ ] Create QuickTest model in models.py
- [ ] Add update_best_metrics to FeatureConfig
- [ ] Create migration
- [ ] Run migration

### Phase 7C: Pipeline Service
- [ ] Create ml_platform/pipelines/ module
- [ ] Implement PipelineService class
- [ ] Implement submit_quick_test method
- [ ] Implement get_pipeline_status method
- [ ] Implement extract_results method
- [ ] Implement cancel_pipeline method
- [ ] Implement update_quick_test_status method

### Phase 7D: API Endpoints
- [ ] Create api.py with views
- [ ] Create urls.py with routes
- [ ] Register URLs in main urls.py
- [ ] Test endpoints manually

### Phase 7E: Pipeline Definition
- [ ] Create pipeline_builder.py
- [ ] Define TFX component wrappers
- [ ] Create quicktest_pipeline function
- [ ] Compile pipeline to JSON
- [ ] Update _submit_pipeline to use compiled pipeline
- [ ] Test pipeline submission

### Phase 7F: UI Components
- [ ] Add Quick Test button to Feature Config cards
- [ ] Create Quick Test dialog modal
- [ ] Create Progress modal
- [ ] Create Results modal
- [ ] Implement JavaScript functions
- [ ] Test full UI flow

### Phase 7G: MLflow (Deferred)
- [ ] (Future) Deploy MLflow on Cloud Run
- [ ] (Future) Configure tracking in Trainer
- [ ] (Future) Add experiment comparison UI

---

## Confirmed Configuration

Based on analysis of the codebase:

| Setting | Value | Source |
|---------|-------|--------|
| **GCP Project ID** | `b2b-recs` | Confirmed |
| **Project Number** | `555035914949` | GCP Console |
| **Region** | `europe-central2` (Warsaw, Poland) | `deploy_django.sh` |
| **BigQuery Dataset** | `raw_data.*` | Dataset model, BigQueryService |
| **Data Source** | Via `Dataset` model + `BigQueryService.generate_query()` | `ml_platform/datasets/services.py:848` |
| **Trainer Output** | Both `metrics.json` + TFX Model | User preference |
| **UI Location** | New chapter on Modeling page | User preference |

### How Data Flows to Pipeline

The pipeline does NOT directly query BigQuery tables. Instead:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ FeatureConfig   │────▶│ Dataset         │────▶│ BigQueryService │
│ (has dataset FK)│     │ (configuration) │     │ .generate_query()│
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │ SQL Query       │
                                                │ (for ExampleGen)│
                                                └─────────────────┘
```

The `Dataset` model stores configuration (not data):
- `primary_table`: e.g., `raw_data.transactions`
- `secondary_tables`: e.g., `['raw_data.products', 'raw_data.customers']`
- `join_config`: How tables are joined
- `selected_columns`: Which columns to include
- `filters`: Date, customer, product filters

The `BigQueryService.generate_query(dataset)` method generates the SQL with:
- CTEs for date filtering
- JOINs for secondary tables
- Product/customer filters
- Selected columns

This SQL is passed to TFX `BigQueryExampleGen` component.

### Critical: Update Phase 7A with Correct Region

All GCS buckets and Vertex AI resources must be in `europe-central2`:

```bash
# Correct bucket creation commands
gsutil mb -p b2b-recs -l europe-central2 gs://b2b-recs-quicktest-artifacts/
gsutil mb -p b2b-recs -l europe-central2 gs://b2b-recs-training-artifacts/
gsutil mb -p b2b-recs -l europe-central2 gs://b2b-recs-pipeline-staging/
```

---

## Related Documentation

- [Phase: Modeling Domain](phase_modeling.md) - Feature engineering UI and workflow
- [TFX Code Generation](tfx_code_generation.md) - Generated Transform/Trainer code
- [Phase: Training Domain](phase_training.md) - Full training specifications
- [Phase: Experiments](phase_experiments.md) - Experiment tracking (future)
