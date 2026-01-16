"""
Training App Configuration

Django app configuration for the training module.
"""
from django.apps import AppConfig


class TrainingConfig(AppConfig):
    """Configuration for the Training app."""

    name = 'ml_platform.training'
    verbose_name = 'Training'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """
        Import signals when the app is ready.

        This ensures signal handlers are connected when Django starts.
        """
        # Import signals to register signal handlers
        from . import signals  # noqa: F401
