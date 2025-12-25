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

    # Prepare ridge chart data for ETL Duration Analysis (3D histogram view)
    # Get all runs from the last 5 days with hourly granularity
    # Each individual run is shown as a separate histogram bar (not aggregated)
    ridge_cutoff_date = timezone.now() - timedelta(days=5)
    all_runs_3_days = model.etl_runs.filter(
        started_at__gte=ridge_cutoff_date,
        status__in=['completed', 'partial', 'failed']
    ).select_related('data_source').order_by('started_at')

    # Build data structure for ridge chart - grouped by job name
    # Each job has a list of individual runs with their exact hour timestamp
    # Structure: {job_name: [{hour: 'YYYY-MM-DD HH:00', duration: X, status: 'success'|'failed'}, ...]}
    ridge_data_by_job = defaultdict(list)

    # Collect all unique job names for Y-axis
    all_job_names = set()

    for run in all_runs_3_days:
        # Skip runs without a data source (Unknown jobs)
        if not run.data_source or not run.started_at:
            continue

        # Format hour as 'YYYY-MM-DD HH:00'
        hour_str = run.started_at.strftime('%Y-%m-%d %H:00')
        job_name = run.data_source.name
        duration = run.get_duration_seconds() or 0
        is_success = run.status in ['completed', 'partial']

        all_job_names.add(job_name)
        ridge_data_by_job[job_name].append({
            'hour': hour_str,
            'duration': duration,
            'status': 'success' if is_success else 'failed',
        })

    # Generate all 120 hours (5 days * 24 hours) for consistent X-axis
    all_hours = []
    now = timezone.now()
    # Start from 5 days ago at hour 0
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=4)
    for i in range(120):  # 5 days * 24 hours
        hour_time = start_time + timedelta(hours=i)
        hour_str = hour_time.strftime('%Y-%m-%d %H:00')
        all_hours.append(hour_str)

    # Format data for frontend - grouped by job name with individual runs
    ridge_chart_data = []
    sorted_job_names = sorted(list(all_job_names))

    for job_name in sorted_job_names:
        ridge_chart_data.append({
            'job_name': job_name,
            'runs': ridge_data_by_job[job_name],  # List of individual runs
        })

    ridge_chart_json = json.dumps({
        'data': ridge_chart_data,
        'hours': all_hours,
        'job_names': sorted_job_names,
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
        'ridge_chart_data': ridge_chart_json,
        'kpi_data': kpi_data,
    }

    return render(request, 'ml_platform/model_etl.html', context)
