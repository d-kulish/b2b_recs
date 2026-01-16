"""
Training Signals

Django signals for training-related events.
Handles automatic updates like schedule statistics when training runs complete.
"""
import logging

from django.db.models import F
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import TrainingRun, TrainingSchedule

logger = logging.getLogger(__name__)


# Track previous status to detect transitions
_previous_statuses = {}


@receiver(pre_save, sender=TrainingRun)
def track_previous_status(sender, instance, **kwargs):
    """
    Track the previous status before save to detect status transitions.
    """
    if instance.pk:
        try:
            previous = TrainingRun.objects.get(pk=instance.pk)
            _previous_statuses[instance.pk] = previous.status
        except TrainingRun.DoesNotExist:
            pass


@receiver(post_save, sender=TrainingRun)
def update_schedule_statistics(sender, instance, created, **kwargs):
    """
    Update parent schedule statistics when a training run reaches a terminal state.

    This signal:
    - Increments successful_runs when a run completes successfully
    - Increments failed_runs when a run fails or is cancelled
    - Only triggers on status changes to terminal states (not on every save)
    """
    # Skip if no associated schedule
    if not instance.schedule:
        return

    # Skip if this is a new record (status changes are handled on subsequent saves)
    if created:
        return

    # Get previous status
    previous_status = _previous_statuses.pop(instance.pk, None)

    # Skip if status hasn't changed
    if previous_status == instance.status:
        return

    # Check if we've transitioned to a terminal state
    current_status = instance.status
    terminal_success_states = {
        TrainingRun.STATUS_COMPLETED,
        TrainingRun.STATUS_NOT_BLESSED,  # Not blessed is still a "successful" run
    }
    terminal_failure_states = {
        TrainingRun.STATUS_FAILED,
        TrainingRun.STATUS_CANCELLED,
    }

    schedule = instance.schedule

    if current_status in terminal_success_states and previous_status not in terminal_success_states:
        # Transition to success state
        TrainingSchedule.objects.filter(pk=schedule.pk).update(
            successful_runs=F('successful_runs') + 1
        )
        logger.info(
            f"Updated schedule {schedule.id} successful_runs for "
            f"training run {instance.id} (status: {current_status})"
        )

    elif current_status in terminal_failure_states and previous_status not in terminal_failure_states:
        # Transition to failure state
        TrainingSchedule.objects.filter(pk=schedule.pk).update(
            failed_runs=F('failed_runs') + 1
        )
        logger.info(
            f"Updated schedule {schedule.id} failed_runs for "
            f"training run {instance.id} (status: {current_status})"
        )
