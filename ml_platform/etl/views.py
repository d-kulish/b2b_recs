"""
ETL Page Views

Handles rendering of ETL-related pages.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Sum, Avg, Count, F, ExpressionWrapper, DurationField
from django.db.models.functions import Extract
from django.core.paginator import Paginator
from datetime import timedelta
from collections import defaultdict
import json
import os

from ml_platform.models import (
    ModelEndpoint,
    ETLConfiguration,
    DataSource,
    ETLRun,
)


def _get_schedule_display(source):
    """
    Convert schedule_type and related fields to human-readable format.
    Examples: "Daily 08:00", "Hourly :15", "Weekly Mon 09:00"
    """
    schedule_type = source.schedule_type

    # Try to get schedule details from first table
    first_table = source.tables.first()
    time_str = ""
    if first_table and first_table.schedule_time:
        time_str = first_table.schedule_time.strftime('%H:%M')

    if schedule_type == 'hourly':
        minute = first_table.schedule_minute if first_table and first_table.schedule_minute is not None else 0
        return f"Hourly :{minute:02d}"
    elif schedule_type == 'daily':
        return f"Daily {time_str}" if time_str else "Daily"
    elif schedule_type == 'weekly':
        day = first_table.schedule_day_of_week if first_table and first_table.schedule_day_of_week is not None else 0
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        day_name = days[day] if 0 <= day <= 6 else 'Mon'
        return f"Weekly {day_name} {time_str}" if time_str else f"Weekly {day_name}"
    elif schedule_type == 'monthly':
        day = first_table.schedule_day_of_month if first_table and first_table.schedule_day_of_month is not None else 1
        # Add ordinal suffix
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return f"Monthly {day}{suffix} {time_str}" if time_str else f"Monthly {day}{suffix}"
    return "Manual"


def sync_running_etl_runs_with_cloud_run(running_etl_runs):
    """
    Sync ETL run statuses with Cloud Run execution statuses.

    For any ETLRun records that show 'running' or 'pending', query Cloud Run
    to get the actual execution status and update the database accordingly.

    Strategy: List recent executions from Cloud Run and match them to our ETL runs
    by checking the --etl_run_id argument passed to each execution.

    Args:
        running_etl_runs: QuerySet of ETLRun objects with status 'running' or 'pending'

    Returns:
        int: Number of runs that were updated
    """
    from django.conf import settings
    import logging

    logger = logging.getLogger(__name__)

    if not running_etl_runs.exists():
        return 0

    # Get GCP project ID
    project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID'))
    if not project_id:
        logger.warning("GCP_PROJECT_ID not configured, cannot sync Cloud Run status")
        return 0

    try:
        from google.cloud import run_v2
        client = run_v2.ExecutionsClient()
    except Exception as e:
        logger.warning(f"Failed to initialize Cloud Run client: {e}")
        return 0

    region = 'europe-central2'
    job_name = f"projects/{project_id}/locations/{region}/jobs/etl-runner"

    # Build a map of ETL run IDs we're looking for
    etl_run_map = {str(run.id): run for run in running_etl_runs}

    if not etl_run_map:
        return 0

    updated_count = 0

    try:
        # List recent executions from Cloud Run
        # This gets us the actual execution objects with their statuses
        list_request = run_v2.ListExecutionsRequest(parent=job_name)
        executions = client.list_executions(request=list_request)

        for execution in executions:
            # Extract etl_run_id from execution's container overrides/args
            etl_run_id = None

            # Check the template's container args for --etl_run_id
            if execution.template and execution.template.containers:
                for container in execution.template.containers:
                    if container.args:
                        args = list(container.args)
                        for i, arg in enumerate(args):
                            if arg == '--etl_run_id' and i + 1 < len(args):
                                etl_run_id = args[i + 1]
                                break
                    if etl_run_id:
                        break

            # Skip if we couldn't find etl_run_id or it's not one we're looking for
            if not etl_run_id or etl_run_id not in etl_run_map:
                continue

            etl_run = etl_run_map[etl_run_id]

            # Determine Cloud Run execution status
            cloud_run_succeeded = execution.succeeded_count > 0 if execution.succeeded_count else False
            cloud_run_failed = execution.failed_count > 0 if execution.failed_count else False
            cloud_run_cancelled = execution.cancelled_count > 0 if execution.cancelled_count else False

            new_status = None
            error_message = None

            if cloud_run_succeeded:
                new_status = 'completed'
            elif cloud_run_cancelled:
                new_status = 'cancelled'
                error_message = 'Job was cancelled'
            elif cloud_run_failed:
                new_status = 'failed'
                # Try to get error message from conditions
                if execution.conditions:
                    for condition in execution.conditions:
                        if condition.type_ == 'Completed' and condition.message:
                            error_message = condition.message
                            break
                if not error_message:
                    error_message = 'Job failed in Cloud Run'

            # Update the ETL run if status changed to a terminal state
            if new_status and new_status != etl_run.status:
                etl_run.status = new_status
                if error_message:
                    etl_run.error_message = error_message
                if new_status in ('completed', 'failed', 'cancelled') and not etl_run.completed_at:
                    etl_run.completed_at = timezone.now()
                etl_run.save()
                updated_count += 1
                logger.info(f"Updated ETL run {etl_run.id} status to '{new_status}' from Cloud Run execution {execution.name}")

                # Remove from map so we don't process again
                del etl_run_map[etl_run_id]

            # Stop if we've matched all running runs
            if not etl_run_map:
                break

    except Exception as e:
        logger.warning(f"Failed to list Cloud Run executions: {e}")

    return updated_count


@login_required
def model_etl(request, model_id):
    """
    ETL Page - Configure data source connections, set extraction schedules, monitor ETL jobs.
    """
    model = get_object_or_404(ModelEndpoint, id=model_id)

    # Get or create ETL configuration
    try:
        etl_config = model.etl_config
    except ETLConfiguration.DoesNotExist:
        etl_config = ETLConfiguration.objects.create(
            model_endpoint=model,
            schedule_type='manual',
        )

    # Get all data sources for this model (prefetch connection, tables, and runs for display)
    data_sources = etl_config.data_sources.all().select_related('connection').prefetch_related('tables', 'runs')

    # Calculate statistics
    enabled_sources = data_sources.filter(is_enabled=True)
    enabled_sources_count = enabled_sources.count()

    # Count all tables across all data sources
    total_tables_count = sum(source.tables.count() for source in data_sources)
    enabled_tables_count = sum(source.tables.filter(is_enabled=True).count() for source in data_sources)

    # Get recent ETL runs with 30-day filter and pagination
    cutoff_date = timezone.now() - timedelta(days=30)

    # Filter runs from last 30 days, including runs with NULL started_at (pending/running jobs)
    filtered_runs = model.etl_runs.filter(
        Q(started_at__gte=cutoff_date) | Q(started_at__isnull=True)
    )

    # Sync any "running" or "pending" runs with Cloud Run to get actual status
    # This ensures cancelled/failed jobs in Cloud Run are reflected in our UI
    running_runs = model.etl_runs.filter(status__in=['running', 'pending'])
    sync_running_etl_runs_with_cloud_run(running_runs)

    # Re-fetch filtered runs after sync (to get updated statuses)
    filtered_runs = model.etl_runs.filter(
        Q(started_at__gte=cutoff_date) | Q(started_at__isnull=True)
    )

    # Check if any runs exist at all (for empty state differentiation)
    has_any_runs = model.etl_runs.exists()

    # Pagination: 6 runs per page
    paginator = Paginator(filtered_runs, 6)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Prepare bubble chart data for ETL Job Runs visualization
    # Shows individual runs as bubbles with size based on duration
    bubble_cutoff_date = timezone.now() - timedelta(days=5)
    all_runs_5_days = model.etl_runs.filter(
        started_at__gte=bubble_cutoff_date,
        status__in=['completed', 'partial', 'failed']
    ).select_related('data_source').order_by('started_at')

    # Build data structure for bubble chart
    # Each run is an individual bubble with position, size, color, and fill
    bubble_runs = []
    all_job_names = set()
    durations = []

    for run in all_runs_5_days:
        # Skip runs without a data source (Unknown jobs)
        if not run.data_source or not run.started_at:
            continue

        job_name = run.data_source.name
        duration = run.get_duration_seconds() or 0
        rows_loaded = run.total_rows_extracted or 0

        # Map status to category: completed, partial, failed
        if run.status == 'completed':
            status = 'completed'
        elif run.status == 'partial':
            status = 'partial'
        else:
            status = 'failed'

        all_job_names.add(job_name)
        if duration > 0:
            durations.append(duration)

        bubble_runs.append({
            'job_name': job_name,
            'started_at': run.started_at.isoformat(),
            'duration': duration,
            'status': status,
            'rows_loaded': rows_loaded,
        })

    # Calculate duration statistics for frontend scaling
    min_duration = min(durations) if durations else 1
    max_duration = max(durations) if durations else 1

    # Generate date range for X-axis
    now = timezone.now()
    start_date = (now - timedelta(days=4)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now.replace(hour=23, minute=59, second=59, microsecond=0)

    sorted_job_names = sorted(list(all_job_names))

    bubble_chart_json = json.dumps({
        'runs': bubble_runs,
        'job_names': sorted_job_names,
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        },
        'duration_stats': {
            'min': min_duration,
            'max': max_duration,
        },
    })

    # =========================================================================
    # KPI Dashboard Aggregations (Last 30 Days)
    # =========================================================================
    # Get all runs from the last 30 days for KPI calculations
    kpi_runs = model.etl_runs.filter(
        started_at__gte=cutoff_date
    )

    # Aggregate metrics
    kpi_aggregates = kpi_runs.aggregate(
        total_runs=Count('id'),
        completed_runs=Count('id', filter=Q(status='completed')),
        failed_runs=Count('id', filter=Q(status='failed')),
        partial_runs=Count('id', filter=Q(status='partial')),
        cancelled_runs=Count('id', filter=Q(status='cancelled')),
        total_rows_extracted=Sum('total_rows_extracted'),
        total_bytes_processed=Sum('bytes_processed'),
    )

    # Calculate average duration from timestamps (more reliable than duration_seconds field)
    # Only include completed runs with both start and end times
    completed_runs_with_times = kpi_runs.filter(
        status__in=['completed', 'partial'],
        started_at__isnull=False,
        completed_at__isnull=False
    )

    # Calculate average duration manually
    avg_duration_seconds = 0
    if completed_runs_with_times.exists():
        total_duration = 0
        count = 0
        for run in completed_runs_with_times:
            if run.started_at and run.completed_at:
                duration = (run.completed_at - run.started_at).total_seconds()
                if duration > 0:  # Only count positive durations
                    total_duration += duration
                    count += 1
        if count > 0:
            avg_duration_seconds = total_duration / count

    # Calculate success rate (completed + partial are considered successful)
    total_runs = kpi_aggregates['total_runs'] or 0
    completed_runs = kpi_aggregates['completed_runs'] or 0
    partial_runs = kpi_aggregates['partial_runs'] or 0
    successful_runs = completed_runs + partial_runs

    success_rate = round((successful_runs / total_runs * 100), 1) if total_runs > 0 else 0

    # Build KPI data dictionary
    kpi_data = {
        'total_runs': total_runs,
        'completed_runs': completed_runs,
        'failed_runs': kpi_aggregates['failed_runs'] or 0,
        'partial_runs': partial_runs,
        'cancelled_runs': kpi_aggregates['cancelled_runs'] or 0,
        'successful_runs': successful_runs,
        'success_rate': success_rate,
        'total_rows_extracted': kpi_aggregates['total_rows_extracted'] or 0,
        'avg_duration_seconds': round(avg_duration_seconds),
    }

    # =========================================================================
    # Scheduled Jobs: Fetch Cloud Scheduler status for dashboard display
    # =========================================================================
    scheduled_jobs_list = []

    # Get all scheduled data sources (non-manual with scheduler job name)
    scheduled_sources = data_sources.filter(
        schedule_type__in=['hourly', 'daily', 'weekly', 'monthly'],
        cloud_scheduler_job_name__isnull=False
    ).exclude(cloud_scheduler_job_name='')

    if scheduled_sources.exists():
        from django.conf import settings
        import logging
        logger = logging.getLogger(__name__)

        project_id = getattr(settings, 'GCP_PROJECT_ID', os.getenv('GCP_PROJECT_ID'))
        region = os.getenv('CLOUD_SCHEDULER_REGION', 'europe-central2')

        if project_id:
            try:
                from ml_platform.utils.cloud_scheduler import CloudSchedulerManager
                scheduler_manager = CloudSchedulerManager(project_id=project_id, region=region)

                enabled_jobs = []
                paused_jobs = []

                for source in scheduled_sources:
                    # Get schedule display string
                    schedule_display = _get_schedule_display(source)

                    # Fetch status from Cloud Scheduler
                    try:
                        status = scheduler_manager.get_schedule_status(source.cloud_scheduler_job_name)
                        next_run_time = status.get('next_run_time') if status.get('success') else None
                        state = status.get('state', 'UNKNOWN') if status.get('success') else 'UNKNOWN'
                        is_paused = state == 'PAUSED'
                    except Exception as e:
                        logger.warning(f"Failed to get scheduler status for {source.name}: {e}")
                        next_run_time = None
                        state = 'UNKNOWN'
                        is_paused = not source.is_enabled

                    job_info = {
                        'id': source.id,
                        'name': source.name,
                        'schedule_type': source.schedule_type,
                        'schedule_display': schedule_display,
                        'next_run_time': next_run_time,
                        'state': state,
                        'is_paused': is_paused,
                    }

                    if is_paused:
                        paused_jobs.append(job_info)
                    else:
                        enabled_jobs.append(job_info)

                # Sort: enabled by next_run_time, paused alphabetically
                # Use naive datetime for fallback since next_run_time is now naive
                from datetime import datetime as dt
                far_future = dt(2099, 12, 31)
                enabled_jobs.sort(key=lambda x: x['next_run_time'] or far_future)
                paused_jobs.sort(key=lambda x: x['name'].lower())

                # Combine: enabled first, then paused
                scheduled_jobs_list = enabled_jobs + paused_jobs

            except ImportError as e:
                logger.warning(f"CloudSchedulerManager not available: {e}")
            except Exception as e:
                logger.warning(f"Failed to fetch Cloud Scheduler status: {e}")

    # Paginate scheduled jobs (5 per page)
    scheduled_paginator = Paginator(scheduled_jobs_list, 5)
    sched_page_number = request.GET.get('sched_page', 1)
    scheduled_jobs_page = scheduled_paginator.get_page(sched_page_number)

    context = {
        'model': model,
        'etl_config': etl_config,
        'data_sources': data_sources,
        'enabled_sources_count': enabled_sources_count,
        'total_tables_count': total_tables_count,
        'enabled_tables_count': enabled_tables_count,
        'recent_runs': page_obj,
        'page_obj': page_obj,
        'has_any_runs': has_any_runs,
        'showing_last_30_days': True,
        'bubble_chart_data': bubble_chart_json,
        'kpi_data': kpi_data,
        'scheduled_jobs': scheduled_jobs_page,
        'has_scheduled_jobs': len(scheduled_jobs_list) > 0,
    }

    return render(request, 'ml_platform/model_etl.html', context)
