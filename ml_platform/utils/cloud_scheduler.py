"""
Cloud Scheduler Utility

Manages Cloud Scheduler jobs for automated ETL execution.
"""

import logging
from typing import Dict, Any, Optional
from google.cloud import scheduler_v1
from google.protobuf import duration_pb2
import json

logger = logging.getLogger(__name__)


class CloudSchedulerManager:
    """Manager for Cloud Scheduler operations"""

    def __init__(self, project_id: str, region: str = 'us-central1'):
        """
        Initialize Cloud Scheduler manager.

        Args:
            project_id: GCP project ID
            region: GCP region for scheduler (default: us-central1)
        """
        self.project_id = project_id
        self.region = region
        self.client = scheduler_v1.CloudSchedulerClient()
        self.parent = f"projects/{project_id}/locations/{region}"

        logger.info(f"Initialized CloudSchedulerManager: {self.parent}")

    def create_etl_schedule(
        self,
        data_source_id: int,
        job_name: str,
        schedule_type: str,
        cloud_run_job_url: str,
        service_account_email: str,
        timezone: str = 'UTC',
        schedule_time: Optional[str] = None,
        schedule_minute: Optional[int] = None,
        schedule_day_of_week: Optional[int] = None,
        schedule_day_of_month: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a Cloud Scheduler job for ETL automation.

        Args:
            data_source_id: DataSource ID
            job_name: Human-readable job name (for scheduler job name)
            schedule_type: Schedule type ('hourly', 'daily', 'weekly', 'monthly')
            cloud_run_job_url: URL to trigger Cloud Run job
            service_account_email: Service account email for authentication
            timezone: Timezone for schedule (default: UTC)
            schedule_time: Time in HH:MM format for daily/weekly/monthly
            schedule_minute: Minute (0-59) for hourly schedules
            schedule_day_of_week: Day of week (0=Monday, 6=Sunday) for weekly
            schedule_day_of_month: Day of month (1-31) for monthly

        Returns:
            Dict with:
                - success: bool
                - job_name: Scheduler job name
                - schedule: Cron expression
                - message: Status message
        """
        try:
            # Generate scheduler job name (must be unique and valid)
            scheduler_job_name = f"etl-job-{data_source_id}"
            full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            # Get cron expression with all parameters
            cron_schedule = self._get_cron_expression(
                schedule_type,
                schedule_time=schedule_time,
                schedule_minute=schedule_minute,
                schedule_day_of_week=schedule_day_of_week,
                schedule_day_of_month=schedule_day_of_month
            )

            # Build HTTP target for Django webhook
            # Extract base URL for OIDC audience (scheme + netloc)
            from urllib.parse import urlparse
            parsed_url = urlparse(cloud_run_job_url)
            audience = f"{parsed_url.scheme}://{parsed_url.netloc}"

            http_target = scheduler_v1.HttpTarget(
                uri=cloud_run_job_url,
                http_method=scheduler_v1.HttpMethod.POST,
                headers={'Content-Type': 'application/json'},
                body=json.dumps({
                    'data_source_id': data_source_id,
                    'trigger': 'scheduled'
                }).encode('utf-8'),
                oidc_token=scheduler_v1.OidcToken(
                    service_account_email=service_account_email,
                    audience=audience
                )
            )

            # Create job configuration
            job = scheduler_v1.Job(
                name=full_job_name,
                description=f'ETL schedule for {job_name} (DataSource ID: {data_source_id})',
                schedule=cron_schedule,
                time_zone=timezone,
                http_target=http_target
            )

            # Create the job
            created_job = self.client.create_job(
                request=scheduler_v1.CreateJobRequest(
                    parent=self.parent,
                    job=job
                )
            )

            logger.info(f"Created Cloud Scheduler job: {created_job.name}")

            return {
                'success': True,
                'job_name': created_job.name,
                'schedule': cron_schedule,
                'message': f'Scheduler created: {cron_schedule}'
            }

        except Exception as e:
            logger.error(f"Failed to create Cloud Scheduler job: {str(e)}")
            return {
                'success': False,
                'job_name': None,
                'schedule': None,
                'message': f'Failed to create scheduler: {str(e)}'
            }

    def update_etl_schedule(
        self,
        data_source_id: int,
        schedule_type: str,
        timezone: str = 'UTC'
    ) -> Dict[str, Any]:
        """
        Update an existing Cloud Scheduler job's schedule.

        Args:
            data_source_id: DataSource ID
            schedule_type: New schedule type
            timezone: Timezone for schedule

        Returns:
            Dict with success status and message
        """
        try:
            scheduler_job_name = f"etl-job-{data_source_id}"
            full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            # Get existing job
            job = self.client.get_job(
                request=scheduler_v1.GetJobRequest(name=full_job_name)
            )

            # Update schedule
            job.schedule = self._get_cron_expression(schedule_type)
            job.time_zone = timezone

            # Update the job
            updated_job = self.client.update_job(
                request=scheduler_v1.UpdateJobRequest(job=job)
            )

            logger.info(f"Updated Cloud Scheduler job: {updated_job.name}")

            return {
                'success': True,
                'message': f'Schedule updated to: {updated_job.schedule}'
            }

        except Exception as e:
            logger.error(f"Failed to update Cloud Scheduler job: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to update scheduler: {str(e)}'
            }

    def delete_etl_schedule(self, data_source_id: int) -> Dict[str, Any]:
        """
        Delete a Cloud Scheduler job.

        Args:
            data_source_id: DataSource ID

        Returns:
            Dict with success status and message
        """
        try:
            scheduler_job_name = f"etl-job-{data_source_id}"
            full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            self.client.delete_job(
                request=scheduler_v1.DeleteJobRequest(name=full_job_name)
            )

            logger.info(f"Deleted Cloud Scheduler job: {full_job_name}")

            return {
                'success': True,
                'message': 'Scheduler deleted successfully'
            }

        except Exception as e:
            logger.error(f"Failed to delete Cloud Scheduler job: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to delete scheduler: {str(e)}'
            }

    def pause_etl_schedule(self, data_source_id: int) -> Dict[str, Any]:
        """
        Pause a Cloud Scheduler job.

        Args:
            data_source_id: DataSource ID

        Returns:
            Dict with success status and message
        """
        try:
            scheduler_job_name = f"etl-job-{data_source_id}"
            full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            self.client.pause_job(
                request=scheduler_v1.PauseJobRequest(name=full_job_name)
            )

            logger.info(f"Paused Cloud Scheduler job: {full_job_name}")

            return {
                'success': True,
                'message': 'Scheduler paused successfully'
            }

        except Exception as e:
            logger.error(f"Failed to pause Cloud Scheduler job: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to pause scheduler: {str(e)}'
            }

    def resume_etl_schedule(self, data_source_id: int) -> Dict[str, Any]:
        """
        Resume a paused Cloud Scheduler job.

        Args:
            data_source_id: DataSource ID

        Returns:
            Dict with success status and message
        """
        try:
            scheduler_job_name = f"etl-job-{data_source_id}"
            full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            self.client.resume_job(
                request=scheduler_v1.ResumeJobRequest(name=full_job_name)
            )

            logger.info(f"Resumed Cloud Scheduler job: {full_job_name}")

            return {
                'success': True,
                'message': 'Scheduler resumed successfully'
            }

        except Exception as e:
            logger.error(f"Failed to resume Cloud Scheduler job: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to resume scheduler: {str(e)}'
            }

    def get_schedule_status(self, job_name_or_id) -> Dict[str, Any]:
        """
        Get status of a Cloud Scheduler job.

        Args:
            job_name_or_id: Either full job name (string) or DataSource ID (int)
                - Full name: "projects/{project}/locations/{region}/jobs/etl-job-{id}"
                - ID: integer data_source_id

        Returns:
            Dict with job status information including state and next_run_time
        """
        try:
            # Determine if we got a full job name or just the ID
            if isinstance(job_name_or_id, str) and job_name_or_id.startswith('projects/'):
                full_job_name = job_name_or_id
            else:
                # It's a data_source_id (int or string representation)
                data_source_id = int(job_name_or_id) if not isinstance(job_name_or_id, int) else job_name_or_id
                scheduler_job_name = f"etl-job-{data_source_id}"
                full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            job = self.client.get_job(
                request=scheduler_v1.GetJobRequest(name=full_job_name)
            )

            # schedule_time and last_attempt_time are already DatetimeWithNanoseconds objects
            # (Python datetime subclass from Google Cloud library)
            # Convert to job's timezone for correct display
            import pytz

            next_run = job.schedule_time  # None for paused jobs
            last_attempt = job.last_attempt_time

            # Convert UTC times to job's configured timezone
            # Then strip tzinfo so Django won't reconvert to server timezone
            job_tz = pytz.timezone(job.time_zone) if job.time_zone else pytz.UTC
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
            logger.warning(f"Scheduler job not found or error: {str(e)}")
            return {
                'success': False,
                'exists': False,
                'message': str(e)
            }

    def _get_cron_expression(
        self,
        schedule_type: str,
        schedule_time: Optional[str] = None,
        schedule_minute: Optional[int] = None,
        schedule_day_of_week: Optional[int] = None,
        schedule_day_of_month: Optional[int] = None
    ) -> str:
        """
        Convert schedule parameters to cron expression.

        Args:
            schedule_type: Schedule type ('hourly', 'daily', 'weekly', 'monthly')
            schedule_time: Time in HH:MM format (for daily/weekly/monthly)
            schedule_minute: Minute 0-59 (for hourly)
            schedule_day_of_week: Day of week 0-6 where 0=Monday (for weekly)
            schedule_day_of_month: Day of month 1-31 (for monthly)

        Returns:
            Cron expression string (format: minute hour day_of_month month day_of_week)
        """
        if schedule_type == 'hourly':
            minute = schedule_minute if schedule_minute is not None else 0
            return f'{minute} * * * *'

        elif schedule_type == 'daily':
            if schedule_time:
                hour, minute = self._parse_time(schedule_time)
                return f'{minute} {hour} * * *'
            return '0 2 * * *'  # Default fallback

        elif schedule_type == 'weekly':
            # Convert our 0=Monday format to cron's 0=Sunday format
            # Our format: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
            # Cron format: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
            cron_day = ((schedule_day_of_week + 1) % 7) if schedule_day_of_week is not None else 0

            if schedule_time:
                hour, minute = self._parse_time(schedule_time)
                return f'{minute} {hour} * * {cron_day}'
            return f'0 2 * * {cron_day}'  # Default fallback

        elif schedule_type == 'monthly':
            day_of_month = schedule_day_of_month if schedule_day_of_month is not None else 1

            if schedule_time:
                hour, minute = self._parse_time(schedule_time)
                return f'{minute} {hour} {day_of_month} * *'
            return f'0 2 {day_of_month} * *'  # Default fallback

        # Default fallback for unknown types
        logger.warning(f"Unknown schedule type: {schedule_type}, defaulting to daily at 2 AM")
        return '0 2 * * *'

    def _parse_time(self, time_str: str) -> tuple:
        """
        Parse HH:MM format time string to (hour, minute) tuple.

        Args:
            time_str: Time in HH:MM format (e.g., "09:30")

        Returns:
            Tuple of (hour, minute) as integers
        """
        try:
            hour, minute = time_str.split(':')
            return int(hour), int(minute)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Invalid time format: {time_str}, defaulting to 02:00")
            return 2, 0

    def trigger_job_now(
        self,
        data_source_id: int
    ) -> Dict[str, Any]:
        """
        Manually trigger a Cloud Scheduler job immediately.

        Args:
            data_source_id: DataSource ID

        Returns:
            Dict with success status and message
        """
        try:
            scheduler_job_name = f"etl-job-{data_source_id}"
            full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            # Run the job immediately
            self.client.run_job(
                request=scheduler_v1.RunJobRequest(name=full_job_name)
            )

            logger.info(f"Triggered Cloud Scheduler job: {full_job_name}")

            return {
                'success': True,
                'message': 'Job triggered successfully'
            }

        except Exception as e:
            logger.error(f"Failed to trigger Cloud Scheduler job: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to trigger job: {str(e)}'
            }
