"""
Training Domain Services

Service layer for managing full-scale training runs on Vertex AI.
Handles creation, status tracking, cancellation, and deletion of training runs.
"""
import logging
from django.db import transaction
from django.utils import timezone

from .models import TrainingRun

logger = logging.getLogger(__name__)


class TrainingService:
    """
    Service class for managing training runs.

    This is a skeleton implementation that provides basic CRUD operations.
    Full pipeline submission and Vertex AI integration will be added in Phase 2.
    """

    def __init__(self, ml_model):
        """
        Initialize TrainingService for a specific model endpoint.

        Args:
            ml_model: ModelEndpoint instance
        """
        self.ml_model = ml_model

    def create_training_run(
        self,
        name: str,
        dataset,
        feature_config,
        model_config,
        description: str = '',
        base_experiment=None,
        training_params: dict = None,
        gpu_config: dict = None,
        evaluator_config: dict = None,
        deployment_config: dict = None,
        created_by=None,
    ) -> TrainingRun:
        """
        Create a new training run record.

        This creates the database record but does not submit the training pipeline.
        Pipeline submission will be implemented in Phase 2.

        Args:
            name: Model name in Vertex AI Model Registry
            dataset: Dataset instance
            feature_config: FeatureConfig instance
            model_config: ModelConfig instance
            description: Optional description
            base_experiment: Optional QuickTest experiment this is based on
            training_params: Training hyperparameters
            gpu_config: GPU configuration
            evaluator_config: Evaluator configuration
            deployment_config: Deployment configuration
            created_by: User who created the training run

        Returns:
            Created TrainingRun instance
        """
        with transaction.atomic():
            # Get next run number for this model endpoint
            last_run = TrainingRun.objects.filter(
                ml_model=self.ml_model
            ).order_by('-run_number').first()

            run_number = (last_run.run_number + 1) if last_run else 1

            # Determine model type from model_config
            model_type = TrainingRun.MODEL_TYPE_RETRIEVAL
            if model_config:
                config_model_type = getattr(model_config, 'model_type', None)
                if config_model_type == 'multitask':
                    model_type = TrainingRun.MODEL_TYPE_MULTITASK
                elif config_model_type == 'ranking':
                    model_type = TrainingRun.MODEL_TYPE_RANKING

            # Create training run
            training_run = TrainingRun.objects.create(
                ml_model=self.ml_model,
                name=name,
                run_number=run_number,
                description=description,
                model_type=model_type,
                dataset=dataset,
                feature_config=feature_config,
                model_config=model_config,
                base_experiment=base_experiment,
                training_params=training_params or {},
                gpu_config=gpu_config or {},
                evaluator_config=evaluator_config or {},
                deployment_config=deployment_config or {},
                created_by=created_by,
                status=TrainingRun.STATUS_PENDING,
            )

            logger.info(
                f"Created training run {training_run.display_name} "
                f"(id={training_run.id}) for model {self.ml_model.name}"
            )

            return training_run

    def refresh_status(self, training_run: TrainingRun) -> TrainingRun:
        """
        Refresh training run status from Vertex AI.

        This is a stub that will be implemented in Phase 2 when
        Vertex AI pipeline integration is added.

        Args:
            training_run: TrainingRun instance to refresh

        Returns:
            Updated TrainingRun instance
        """
        # TODO: Implement Vertex AI status polling in Phase 2
        # For now, just return the training run unchanged
        logger.debug(f"Status refresh stub called for {training_run.display_name}")
        return training_run

    def cancel_training_run(self, training_run: TrainingRun) -> TrainingRun:
        """
        Cancel a running training run.

        This is a stub that will be implemented in Phase 2 when
        Vertex AI pipeline integration is added.

        Args:
            training_run: TrainingRun instance to cancel

        Returns:
            Updated TrainingRun instance
        """
        # TODO: Implement Vertex AI pipeline cancellation in Phase 2
        # For now, just update the status
        training_run.status = TrainingRun.STATUS_CANCELLED
        training_run.completed_at = timezone.now()
        training_run.save(update_fields=['status', 'completed_at', 'updated_at'])

        logger.info(f"Cancelled training run {training_run.display_name} (id={training_run.id})")

        return training_run

    def delete_training_run(self, training_run: TrainingRun) -> None:
        """
        Delete a training run and its associated artifacts.

        This is a stub that will be implemented in Phase 2 when
        GCS artifact management is added.

        Args:
            training_run: TrainingRun instance to delete
        """
        # TODO: Implement GCS artifact deletion in Phase 2
        # For now, just delete the database record
        run_id = training_run.id
        display_name = training_run.display_name

        training_run.delete()

        logger.info(f"Deleted training run {display_name} (id={run_id})")

    def submit_training_pipeline(self, training_run: TrainingRun) -> TrainingRun:
        """
        Submit a training run to Vertex AI Pipeline.

        This will be implemented in Phase 2.

        Args:
            training_run: TrainingRun instance to submit

        Returns:
            Updated TrainingRun instance

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Pipeline submission will be implemented in Phase 2. "
            "For now, training runs are created in PENDING status only."
        )
