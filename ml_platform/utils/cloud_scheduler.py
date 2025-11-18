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
        timezone: str = 'UTC'
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

            # Get cron expression
            cron_schedule = self._get_cron_expression(schedule_type)

            # Build HTTP target for Cloud Run Jobs
            # Cloud Run Jobs use the Jobs API, not direct HTTP
            # We'll use HTTP POST to trigger the job via Cloud Run Jobs API
            http_target = scheduler_v1.HttpTarget(
                uri=cloud_run_job_url,
                http_method=scheduler_v1.HttpMethod.POST,
                headers={'Content-Type': 'application/json'},
                body=json.dumps({
                    'data_source_id': data_source_id,
                    'trigger': 'scheduled'
                }).encode('utf-8'),
                oidc_token=scheduler_v1.OidcToken(
                    service_account_email=service_account_email
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

    def get_schedule_status(self, data_source_id: int) -> Dict[str, Any]:
        """
        Get status of a Cloud Scheduler job.

        Args:
            data_source_id: DataSource ID

        Returns:
            Dict with job status information
        """
        try:
            scheduler_job_name = f"etl-job-{data_source_id}"
            full_job_name = f"{self.parent}/jobs/{scheduler_job_name}"

            job = self.client.get_job(
                request=scheduler_v1.GetJobRequest(name=full_job_name)
            )

            return {
                'success': True,
                'exists': True,
                'schedule': job.schedule,
                'state': job.state.name,
                'last_attempt_time': job.last_attempt_time,
                'next_run_time': job.schedule_time
            }

        except Exception as e:
            logger.warning(f"Scheduler job not found or error: {str(e)}")
            return {
                'success': False,
                'exists': False,
                'message': str(e)
            }

    def _get_cron_expression(self, schedule_type: str) -> str:
        """
        Convert schedule type to cron expression.

        Args:
            schedule_type: Schedule type

        Returns:
            Cron expression string
        """
        cron_map = {
            'hourly': '0 * * * *',        # Every hour at minute 0
            'daily': '0 2 * * *',          # Daily at 2:00 AM UTC
            'weekly': '0 2 * * 0',         # Weekly on Sunday at 2:00 AM
            'monthly': '0 2 1 * *',        # Monthly on 1st at 2:00 AM
            'every_15_min': '*/15 * * * *', # Every 15 minutes
            'every_30_min': '*/30 * * * *', # Every 30 minutes
        }

        if schedule_type not in cron_map:
            logger.warning(f"Unknown schedule type: {schedule_type}, defaulting to daily")
            return cron_map['daily']

        return cron_map[schedule_type]

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
