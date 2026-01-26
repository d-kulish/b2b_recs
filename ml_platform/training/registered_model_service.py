"""
Registered Model Service

Service layer for managing RegisteredModel entities.
Handles creation, updates, and synchronization with Vertex AI Model Registry.
"""
import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import RegisteredModel, TrainingRun

logger = logging.getLogger(__name__)


class RegisteredModelServiceError(Exception):
    """Exception raised by RegisteredModelService operations."""
    pass


class RegisteredModelService:
    """
    Service class for managing RegisteredModel entities.

    Provides:
    - Get or create RegisteredModel for training runs
    - Update RegisteredModel after Vertex AI registration
    - Update deployment status
    - Synchronize version cache
    """

    def __init__(self, ml_model):
        """
        Initialize RegisteredModelService for a specific model endpoint.

        Args:
            ml_model: ModelEndpoint instance
        """
        self.ml_model = ml_model

    def get_or_create_for_training(
        self,
        model_name: str,
        model_type: str = 'retrieval',
        description: str = '',
        created_by=None
    ) -> RegisteredModel:
        """
        Get or create a RegisteredModel for a training run.

        If a RegisteredModel with the given name already exists for this
        model endpoint, return it. Otherwise, create a new one.

        Args:
            model_name: Name for the model (becomes vertex_model_name)
            model_type: Type of model ('retrieval', 'ranking', 'multitask')
            description: Optional description
            created_by: User who created the training run

        Returns:
            RegisteredModel instance
        """
        with transaction.atomic():
            registered_model, created = RegisteredModel.objects.get_or_create(
                ml_model=self.ml_model,
                model_name=model_name,
                defaults={
                    'model_type': model_type,
                    'description': description,
                    'created_by': created_by,
                    'is_active': True,
                }
            )

            if created:
                logger.info(
                    f"Created RegisteredModel '{model_name}' for endpoint {self.ml_model.name}"
                )
            else:
                logger.info(
                    f"Found existing RegisteredModel '{model_name}' for endpoint {self.ml_model.name}"
                )

            return registered_model

    def update_after_registration(
        self,
        registered_model: RegisteredModel,
        training_run: TrainingRun
    ) -> RegisteredModel:
        """
        Update RegisteredModel after a training run is registered to Vertex AI.

        This is called when the Pusher component successfully registers a model
        version to Vertex AI Model Registry.

        Args:
            registered_model: RegisteredModel to update
            training_run: TrainingRun that was just registered

        Returns:
            Updated RegisteredModel instance
        """
        with transaction.atomic():
            # Lock the RegisteredModel for update
            registered_model = RegisteredModel.objects.select_for_update().get(
                id=registered_model.id
            )

            # Update first registration info if this is the first version
            if not registered_model.first_registered_at:
                registered_model.first_registered_at = training_run.registered_at or timezone.now()

            # Update Vertex AI resource name
            if training_run.vertex_model_resource_name:
                registered_model.vertex_model_resource_name = training_run.vertex_model_resource_name

            # Update latest version cache
            registered_model.latest_version_id = training_run.id
            registered_model.latest_version_number = training_run.vertex_model_version or ''

            # Update total versions count
            registered_model.total_versions = TrainingRun.objects.filter(
                registered_model=registered_model,
                vertex_model_resource_name__isnull=False
            ).exclude(vertex_model_resource_name='').count()

            registered_model.save(update_fields=[
                'first_registered_at',
                'vertex_model_resource_name',
                'latest_version_id',
                'latest_version_number',
                'total_versions',
                'updated_at',
            ])

            logger.info(
                f"Updated RegisteredModel '{registered_model.model_name}' after registration: "
                f"version={training_run.vertex_model_version}, total_versions={registered_model.total_versions}"
            )

            return registered_model

    def sync_version_cache(self, registered_model: RegisteredModel) -> RegisteredModel:
        """
        Synchronize the version cache fields with actual data.

        Recalculates total_versions, latest_version_id, and latest_version_number
        from the actual TrainingRun data.

        Args:
            registered_model: RegisteredModel to sync

        Returns:
            Updated RegisteredModel instance
        """
        with transaction.atomic():
            # Get all registered versions
            versions = TrainingRun.objects.filter(
                registered_model=registered_model,
                vertex_model_resource_name__isnull=False
            ).exclude(
                vertex_model_resource_name=''
            ).order_by('-registered_at')

            registered_model.total_versions = versions.count()

            if versions.exists():
                latest = versions.first()
                registered_model.latest_version_id = latest.id
                registered_model.latest_version_number = latest.vertex_model_version or ''

                # Update Vertex AI resource name from latest
                if latest.vertex_model_resource_name:
                    registered_model.vertex_model_resource_name = latest.vertex_model_resource_name

                # Update first_registered_at from earliest
                earliest = versions.last()
                if not registered_model.first_registered_at:
                    registered_model.first_registered_at = earliest.registered_at
            else:
                registered_model.latest_version_id = None
                registered_model.latest_version_number = ''

            registered_model.save(update_fields=[
                'total_versions',
                'latest_version_id',
                'latest_version_number',
                'vertex_model_resource_name',
                'first_registered_at',
                'updated_at',
            ])

            return registered_model

    def get_by_name(self, model_name: str) -> Optional[RegisteredModel]:
        """
        Get a RegisteredModel by name.

        Args:
            model_name: Model name to look up

        Returns:
            RegisteredModel instance or None if not found
        """
        return RegisteredModel.objects.filter(
            ml_model=self.ml_model,
            model_name=model_name
        ).first()

    def check_name_available(self, model_name: str) -> dict:
        """
        Check if a model name is available or already exists.

        Args:
            model_name: Model name to check

        Returns:
            Dict with:
                - exists: bool - whether the name exists
                - registered_model_id: int or None - ID if exists
                - has_schedule: bool - whether it has a schedule
                - schedule_id: int or None - schedule ID if has one
        """
        existing = RegisteredModel.objects.filter(
            ml_model=self.ml_model,
            model_name=model_name
        ).first()

        if not existing:
            return {
                'exists': False,
                'registered_model_id': None,
                'has_schedule': False,
                'schedule_id': None,
            }

        has_schedule = hasattr(existing, 'schedule') and existing.schedule is not None
        schedule_id = existing.schedule.id if has_schedule else None

        return {
            'exists': True,
            'registered_model_id': existing.id,
            'has_schedule': has_schedule,
            'schedule_id': schedule_id,
        }
