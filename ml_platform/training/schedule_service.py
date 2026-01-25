"""
Training Schedule Service

Service layer for managing training schedules and Cloud Scheduler integration.
Handles creation, execution, pause/resume, and deletion of scheduled training.
"""
import logging
from datetime import datetime, time, timedelta
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import TrainingSchedule, TrainingRun

logger = logging.getLogger(__name__)


class TrainingScheduleServiceError(Exception):
    """Exception raised by TrainingScheduleService operations."""
    pass


class TrainingScheduleService:
    """
    Service class for managing training schedules.

    Provides:
    - Schedule creation with Cloud Scheduler job setup
    - Scheduled training execution (triggered by webhook)
    - Pause/Resume schedule operations
    - Schedule cancellation/deletion
    - Next run time calculation
    """

    def __init__(self, ml_model):
        """
        Initialize TrainingScheduleService for a specific model endpoint.

        Args:
            ml_model: ModelEndpoint instance
        """
        self.ml_model = ml_model
        self.project_id = ml_model.gcp_project_id or getattr(
            settings, 'GCP_PROJECT_ID', 'b2b-recs'
        )
        self.region = getattr(settings, 'CLOUD_SCHEDULER_REGION', 'europe-central2')

    def create_schedule(
        self,
        schedule: TrainingSchedule,
        webhook_base_url: str
    ) -> Dict[str, Any]:
        """
        Create Cloud Scheduler job for the schedule.

        Args:
            schedule: TrainingSchedule instance
            webhook_base_url: Base URL for the webhook endpoint

        Returns:
            Dict with:
                - success: bool
                - job_name: Cloud Scheduler job name (if successful)
                - message: Status message
        """
        from ml_platform.utils.cloud_scheduler import CloudSchedulerManager

        try:
            manager = CloudSchedulerManager(self.project_id, self.region)
            webhook_url = f"{webhook_base_url}/api/training/schedules/{schedule.id}/webhook/"

            # Service account for OIDC authentication
            service_account = getattr(
                settings,
                'TRAINING_SCHEDULER_SERVICE_ACCOUNT',
                f"training-scheduler@{self.project_id}.iam.gserviceaccount.com"
            )

            # Generate cron expression
            cron_expr = self._get_cron_expression(schedule)

            # Build scheduler job name
            scheduler_job_name = f"training-schedule-{schedule.id}"

            # Get audience from webhook URL
            parsed_url = urlparse(webhook_url)
            audience = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # Import scheduler types
            from google.cloud import scheduler_v1
            import json

            client = scheduler_v1.CloudSchedulerClient()
            parent = f"projects/{self.project_id}/locations/{self.region}"
            full_job_name = f"{parent}/jobs/{scheduler_job_name}"

            http_target = scheduler_v1.HttpTarget(
                uri=webhook_url,
                http_method=scheduler_v1.HttpMethod.POST,
                headers={'Content-Type': 'application/json'},
                body=json.dumps({
                    'schedule_id': schedule.id,
                    'trigger': 'scheduled'
                }).encode('utf-8'),
                oidc_token=scheduler_v1.OidcToken(
                    service_account_email=service_account,
                    audience=audience
                )
            )

            job = scheduler_v1.Job(
                name=full_job_name,
                description=f'Training schedule: {schedule.name} (ID: {schedule.id})',
                schedule=cron_expr,
                time_zone=schedule.schedule_timezone,
                http_target=http_target
            )

            created_job = client.create_job(
                request=scheduler_v1.CreateJobRequest(
                    parent=parent,
                    job=job
                )
            )

            logger.info(f"Created Cloud Scheduler job: {created_job.name}")

            # Update schedule with job name and next run
            schedule.cloud_scheduler_job_name = created_job.name
            schedule.next_run_at = self._calculate_next_run(schedule)
            schedule.save(update_fields=['cloud_scheduler_job_name', 'next_run_at'])

            return {
                'success': True,
                'job_name': created_job.name,
                'schedule': cron_expr,
                'message': f'Schedule created: {cron_expr}'
            }

        except Exception as e:
            logger.exception(f"Failed to create Cloud Scheduler job: {e}")
            return {
                'success': False,
                'job_name': None,
                'schedule': None,
                'message': f'Failed to create scheduler: {str(e)}'
            }

    def execute_scheduled_training(self, schedule: TrainingSchedule) -> TrainingRun:
        """
        Execute scheduled training: create and submit a new TrainingRun.

        Called by the webhook when Cloud Scheduler triggers the schedule.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Created TrainingRun instance
        """
        from .services import TrainingService

        logger.info(f"Executing scheduled training for schedule {schedule.id}: {schedule.name}")

        training_service = TrainingService(schedule.ml_model)

        # Get model name from RegisteredModel if available, otherwise from schedule name
        if schedule.registered_model:
            model_name = schedule.registered_model.model_name
        else:
            model_name = schedule.name

        # Create training run from schedule config
        run_timestamp = timezone.now().strftime('%Y%m%d-%H%M')
        training_run = TrainingRun.objects.create(
            ml_model=schedule.ml_model,
            name=model_name,
            description=f"Scheduled run from '{schedule.name}'",
            dataset=schedule.dataset,
            feature_config=schedule.feature_config,
            model_config=schedule.model_config,
            base_experiment=schedule.base_experiment,
            training_params=schedule.training_params,
            gpu_config=schedule.gpu_config,
            evaluator_config=schedule.evaluator_config,
            deployment_config=schedule.deployment_config,
            created_by=schedule.created_by,
            schedule=schedule,
            registered_model=schedule.registered_model,
            status=TrainingRun.STATUS_PENDING,
        )

        # Get next run number
        last_run = TrainingRun.objects.filter(
            ml_model=schedule.ml_model
        ).exclude(id=training_run.id).order_by('-run_number').first()
        training_run.run_number = (last_run.run_number + 1) if last_run else 1
        training_run.save(update_fields=['run_number'])

        # Submit the pipeline
        try:
            training_service.submit_training_pipeline(training_run)
            logger.info(f"Submitted training pipeline for scheduled run {training_run.id}")
        except Exception as e:
            logger.exception(f"Failed to submit scheduled training: {e}")
            training_run.status = TrainingRun.STATUS_FAILED
            training_run.error_message = str(e)
            training_run.save(update_fields=['status', 'error_message'])

        # Update schedule statistics
        schedule.last_run_at = timezone.now()
        schedule.total_runs += 1
        schedule.next_run_at = self._calculate_next_run(schedule)

        # For one-time schedules, mark as completed and delete scheduler job
        if schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_ONCE:
            schedule.status = TrainingSchedule.STATUS_COMPLETED
            self._delete_scheduler_job(schedule)

        schedule.save(update_fields=[
            'last_run_at', 'total_runs', 'next_run_at', 'status'
        ])

        return training_run

    def delete_schedule(self, schedule: TrainingSchedule) -> Dict[str, Any]:
        """
        Delete Cloud Scheduler job and mark schedule as cancelled.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Dict with success status and message
        """
        result = self._delete_scheduler_job(schedule)

        # Mark schedule as cancelled
        schedule.status = TrainingSchedule.STATUS_CANCELLED
        schedule.next_run_at = None
        schedule.save(update_fields=['status', 'next_run_at', 'updated_at'])

        return result

    def pause_schedule(self, schedule: TrainingSchedule) -> Dict[str, Any]:
        """
        Pause Cloud Scheduler job.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Dict with success status and message
        """
        if not schedule.cloud_scheduler_job_name:
            return {
                'success': False,
                'message': 'No Cloud Scheduler job associated with this schedule'
            }

        try:
            from google.cloud import scheduler_v1

            client = scheduler_v1.CloudSchedulerClient()
            client.pause_job(
                request=scheduler_v1.PauseJobRequest(
                    name=schedule.cloud_scheduler_job_name
                )
            )

            schedule.status = TrainingSchedule.STATUS_PAUSED
            schedule.save(update_fields=['status', 'updated_at'])

            logger.info(f"Paused Cloud Scheduler job: {schedule.cloud_scheduler_job_name}")

            return {
                'success': True,
                'message': 'Schedule paused successfully'
            }

        except Exception as e:
            logger.exception(f"Failed to pause schedule: {e}")
            return {
                'success': False,
                'message': f'Failed to pause schedule: {str(e)}'
            }

    def resume_schedule(self, schedule: TrainingSchedule) -> Dict[str, Any]:
        """
        Resume a paused Cloud Scheduler job.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Dict with success status and message
        """
        if not schedule.cloud_scheduler_job_name:
            return {
                'success': False,
                'message': 'No Cloud Scheduler job associated with this schedule'
            }

        try:
            from google.cloud import scheduler_v1

            client = scheduler_v1.CloudSchedulerClient()
            client.resume_job(
                request=scheduler_v1.ResumeJobRequest(
                    name=schedule.cloud_scheduler_job_name
                )
            )

            schedule.status = TrainingSchedule.STATUS_ACTIVE
            schedule.next_run_at = self._calculate_next_run(schedule)
            schedule.save(update_fields=['status', 'next_run_at', 'updated_at'])

            logger.info(f"Resumed Cloud Scheduler job: {schedule.cloud_scheduler_job_name}")

            return {
                'success': True,
                'message': 'Schedule resumed successfully'
            }

        except Exception as e:
            logger.exception(f"Failed to resume schedule: {e}")
            return {
                'success': False,
                'message': f'Failed to resume schedule: {str(e)}'
            }

    def trigger_now(self, schedule: TrainingSchedule) -> Dict[str, Any]:
        """
        Manually trigger a scheduled training immediately.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Dict with success status, training_run_id, and message
        """
        try:
            training_run = self.execute_scheduled_training(schedule)
            return {
                'success': True,
                'training_run_id': training_run.id,
                'message': f'Training run {training_run.id} triggered successfully'
            }
        except Exception as e:
            logger.exception(f"Failed to trigger scheduled training: {e}")
            return {
                'success': False,
                'training_run_id': None,
                'message': f'Failed to trigger training: {str(e)}'
            }

    def _delete_scheduler_job(self, schedule: TrainingSchedule) -> Dict[str, Any]:
        """
        Delete Cloud Scheduler job.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Dict with success status and message
        """
        if not schedule.cloud_scheduler_job_name:
            return {
                'success': True,
                'not_found': True,
                'message': 'No Cloud Scheduler job to delete'
            }

        try:
            from google.cloud import scheduler_v1
            from google.api_core import exceptions as google_exceptions

            client = scheduler_v1.CloudSchedulerClient()
            client.delete_job(
                request=scheduler_v1.DeleteJobRequest(
                    name=schedule.cloud_scheduler_job_name
                )
            )

            logger.info(f"Deleted Cloud Scheduler job: {schedule.cloud_scheduler_job_name}")

            # Clear the job name
            schedule.cloud_scheduler_job_name = ''
            schedule.save(update_fields=['cloud_scheduler_job_name'])

            return {
                'success': True,
                'not_found': False,
                'message': 'Scheduler deleted successfully'
            }

        except google_exceptions.NotFound:
            logger.info(f"Cloud Scheduler job already deleted: {schedule.cloud_scheduler_job_name}")
            schedule.cloud_scheduler_job_name = ''
            schedule.save(update_fields=['cloud_scheduler_job_name'])
            return {
                'success': True,
                'not_found': True,
                'message': 'Scheduler already deleted'
            }

        except Exception as e:
            logger.exception(f"Failed to delete scheduler: {e}")
            return {
                'success': False,
                'not_found': False,
                'message': f'Failed to delete scheduler: {str(e)}'
            }

    def _get_cron_expression(self, schedule: TrainingSchedule) -> str:
        """
        Generate cron expression from schedule settings.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Cron expression string
        """
        if schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_ONCE:
            # One-time schedule: specific datetime
            dt = schedule.scheduled_datetime
            if dt:
                return f"{dt.minute} {dt.hour} {dt.day} {dt.month} *"
            # Fallback: run in 1 hour
            future = timezone.now() + timedelta(hours=1)
            return f"{future.minute} {future.hour} {future.day} {future.month} *"

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_DAILY:
            # Daily: at specific time
            if schedule.schedule_time:
                return f"{schedule.schedule_time.minute} {schedule.schedule_time.hour} * * *"
            return "0 2 * * *"  # Default: 2 AM

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_WEEKLY:
            # Weekly: specific day and time
            # Convert 0=Monday to cron format (0=Sunday)
            cron_day = ((schedule.schedule_day_of_week or 0) + 1) % 7
            if schedule.schedule_time:
                return f"{schedule.schedule_time.minute} {schedule.schedule_time.hour} * * {cron_day}"
            return f"0 2 * * {cron_day}"  # Default: 2 AM on specified day

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_HOURLY:
            # Hourly: every hour at specified minute
            # Format: "minute * * * *"
            minute = schedule.schedule_time.minute if schedule.schedule_time else 0
            return f"{minute} * * * *"

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_MONTHLY:
            # Monthly: specific day of month and time
            # Format: "minute hour day * *"
            if schedule.schedule_time:
                minute = schedule.schedule_time.minute
                hour = schedule.schedule_time.hour
            else:
                minute, hour = 0, 2  # Default 2 AM
            day = schedule.schedule_day_of_month or 1
            return f"{minute} {hour} {day} * *"

        # Fallback
        logger.warning(f"Unknown schedule type: {schedule.schedule_type}")
        return "0 2 * * *"

    def _calculate_next_run(self, schedule: TrainingSchedule) -> Optional[datetime]:
        """
        Calculate next run time based on schedule type.

        Uses croniter library for accurate cron parsing.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Next run datetime or None
        """
        if schedule.status == TrainingSchedule.STATUS_COMPLETED:
            return None

        if schedule.status == TrainingSchedule.STATUS_PAUSED:
            return None

        if schedule.status == TrainingSchedule.STATUS_CANCELLED:
            return None

        try:
            from croniter import croniter
            import pytz

            cron_expr = self._get_cron_expression(schedule)
            tz = pytz.timezone(schedule.schedule_timezone)
            now = timezone.now().astimezone(tz)

            cron = croniter(cron_expr, now)
            next_run = cron.get_next(datetime)

            # Convert to UTC for storage
            if next_run.tzinfo is None:
                next_run = tz.localize(next_run)

            return next_run

        except ImportError:
            # croniter not available, use simple calculation
            logger.warning("croniter not installed, using simple next run calculation")
            return self._calculate_next_run_simple(schedule)

        except Exception as e:
            logger.warning(f"Error calculating next run: {e}")
            return None

    def _calculate_next_run_simple(self, schedule: TrainingSchedule) -> Optional[datetime]:
        """
        Simple next run calculation without croniter.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Next run datetime or None
        """
        import pytz

        try:
            tz = pytz.timezone(schedule.schedule_timezone)
        except Exception:
            tz = pytz.UTC

        now = timezone.now().astimezone(tz)

        if schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_ONCE:
            if schedule.scheduled_datetime and schedule.scheduled_datetime > now:
                return schedule.scheduled_datetime
            return None

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_DAILY:
            if schedule.schedule_time:
                next_run = now.replace(
                    hour=schedule.schedule_time.hour,
                    minute=schedule.schedule_time.minute,
                    second=0,
                    microsecond=0
                )
                if next_run <= now:
                    next_run += timedelta(days=1)
                return next_run
            return now + timedelta(days=1)

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_WEEKLY:
            target_day = schedule.schedule_day_of_week or 0
            days_ahead = target_day - now.weekday()
            if days_ahead < 0:
                days_ahead += 7

            next_run = now + timedelta(days=days_ahead)
            if schedule.schedule_time:
                next_run = next_run.replace(
                    hour=schedule.schedule_time.hour,
                    minute=schedule.schedule_time.minute,
                    second=0,
                    microsecond=0
                )
            if next_run <= now:
                next_run += timedelta(weeks=1)
            return next_run

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_HOURLY:
            minute = schedule.schedule_time.minute if schedule.schedule_time else 0
            next_run = now.replace(minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(hours=1)
            return next_run

        elif schedule.schedule_type == TrainingSchedule.SCHEDULE_TYPE_MONTHLY:
            target_day = schedule.schedule_day_of_month or 1
            if schedule.schedule_time:
                hour = schedule.schedule_time.hour
                minute = schedule.schedule_time.minute
            else:
                hour, minute = 2, 0  # Default 2 AM

            # Start with current month
            next_run = now.replace(
                day=target_day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )
            if next_run <= now:
                # Move to next month
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
            return next_run

        return None

    def get_schedule_status_from_cloud(self, schedule: TrainingSchedule) -> Dict[str, Any]:
        """
        Get schedule status from Cloud Scheduler.

        Args:
            schedule: TrainingSchedule instance

        Returns:
            Dict with status information
        """
        if not schedule.cloud_scheduler_job_name:
            return {
                'success': False,
                'exists': False,
                'message': 'No Cloud Scheduler job associated'
            }

        try:
            from google.cloud import scheduler_v1
            import pytz

            client = scheduler_v1.CloudSchedulerClient()
            job = client.get_job(
                request=scheduler_v1.GetJobRequest(
                    name=schedule.cloud_scheduler_job_name
                )
            )

            # Parse timezone
            job_tz = pytz.timezone(job.time_zone) if job.time_zone else pytz.UTC

            next_run = job.schedule_time
            last_attempt = job.last_attempt_time

            # Convert to job timezone
            if next_run:
                next_run = next_run.astimezone(job_tz).replace(tzinfo=None)
            if last_attempt:
                last_attempt = last_attempt.astimezone(job_tz).replace(tzinfo=None)

            return {
                'success': True,
                'exists': True,
                'schedule': job.schedule,
                'state': job.state.name,
                'time_zone': job.time_zone,
                'last_attempt_time': last_attempt,
                'next_run_time': next_run
            }

        except Exception as e:
            logger.warning(f"Error getting schedule status: {e}")
            return {
                'success': False,
                'exists': False,
                'message': str(e)
            }
