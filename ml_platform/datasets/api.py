"""
Datasets REST API Endpoints

Handles all dataset-related API operations (JSON responses).
This module contains dataset CRUD, BigQuery integration, and analysis APIs.
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.utils import timezone
import json
import logging

from ml_platform.models import ModelEndpoint, Dataset, DatasetVersion
from .services import BigQueryService, ProductRevenueAnalysisService

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def serialize_dataset(ds, include_details=False):
    """
    Serialize a Dataset object to dict.

    Args:
        ds: Dataset instance
        include_details: If True, include all configuration details

    Returns:
        Dict representation of the dataset
    """
    data = {
        'id': ds.id,
        'name': ds.name,
        'description': ds.description,
        'status': ds.status,
        'primary_table': ds.primary_table,
        'secondary_tables': ds.secondary_tables,
        'table_count': 1 + len(ds.secondary_tables or []),
        'row_count_estimate': ds.row_count_estimate,
        'unique_users_estimate': ds.unique_users_estimate,
        'unique_products_estimate': ds.unique_products_estimate,
        'created_at': ds.created_at.isoformat(),
        'updated_at': ds.updated_at.isoformat(),
        'last_used_at': ds.last_used_at.isoformat() if ds.last_used_at else None,
        'created_by': ds.created_by.username if ds.created_by else None,
        'version_count': ds.versions.count(),
    }

    if include_details:
        data.update({
            'join_config': ds.join_config,
            'selected_columns': ds.selected_columns,
            'column_mapping': ds.column_mapping,
            'filters': ds.filters,
            'split_config': ds.split_config,
            'date_range_start': ds.date_range_start.isoformat() if ds.date_range_start else None,
            'date_range_end': ds.date_range_end.isoformat() if ds.date_range_end else None,
            'column_stats': ds.column_stats,
        })

    return data


def validate_dataset_config(data, model_endpoint, exclude_dataset_id=None):
    """
    Validate dataset configuration.

    Args:
        data: Dict with dataset configuration
        model_endpoint: ModelEndpoint instance
        exclude_dataset_id: Dataset ID to exclude from duplicate check

    Returns:
        Tuple of (is_valid, errors_dict)
    """
    errors = {}

    # Validate name
    name = data.get('name', '').strip()
    if not name:
        errors['name'] = 'Dataset name is required'
    elif len(name) > 255:
        errors['name'] = 'Dataset name must be 255 characters or less'
    else:
        # Check for duplicate
        existing = model_endpoint.datasets.filter(name=name)
        if exclude_dataset_id:
            existing = existing.exclude(id=exclude_dataset_id)
        if existing.exists():
            errors['name'] = f'Dataset "{name}" already exists'

    # Validate primary table
    primary_table = data.get('primary_table', '').strip()
    if not primary_table:
        errors['primary_table'] = 'Primary table is required'
    elif not primary_table.startswith('raw_data.'):
        errors['primary_table'] = 'Primary table must be from raw_data dataset'

    # Validate secondary tables
    secondary_tables = data.get('secondary_tables', [])
    if secondary_tables:
        for table in secondary_tables:
            if not table.startswith('raw_data.'):
                errors['secondary_tables'] = 'All secondary tables must be from raw_data dataset'
                break

    # Validate join config (if secondary tables exist)
    if secondary_tables and data.get('join_config'):
        join_config = data['join_config']
        for table in secondary_tables:
            if table not in join_config:
                errors['join_config'] = f'Missing join configuration for {table}'
                break
            if not join_config[table].get('join_key'):
                errors['join_config'] = f'Missing join key for {table}'
                break

    # Validate split config
    split_config = data.get('split_config', {})
    if split_config:
        strategy = split_config.get('strategy')
        if strategy not in (None, '', 'time_based', 'random'):
            errors['split_config'] = 'Split strategy must be "time_based" or "random"'
        elif strategy == 'time_based':
            if not split_config.get('eval_days'):
                errors['split_config'] = 'eval_days required for time_based split'
        elif strategy == 'random':
            train_percent = split_config.get('train_percent')
            if train_percent is None or not (0 < train_percent < 100):
                errors['split_config'] = 'train_percent must be between 0 and 100'

    return len(errors) == 0, errors


# =============================================================================
# DATASET CRUD APIs
# =============================================================================

@login_required
@require_http_methods(["GET"])
def list_datasets(request, model_id):
    """
    List all datasets for a model.

    Query params:
        - status: Filter by status ('draft', 'active')
        - page: Page number (default 1)
        - per_page: Items per page (default 10, max 50)
        - search: Search in name/description
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        datasets = model.datasets.all().order_by('-updated_at')

        # Optional status filter
        status = request.GET.get('status')
        if status:
            datasets = datasets.filter(status=status)

        # Optional search filter
        search = request.GET.get('search', '').strip()
        if search:
            from django.db.models import Q
            datasets = datasets.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        # Get total before pagination
        total_count = datasets.count()

        # Pagination
        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('per_page', 10)), 50)  # Max 50

        paginator = Paginator(datasets, per_page)
        page_obj = paginator.get_page(page)

        # Serialize datasets
        datasets_data = [serialize_dataset(ds) for ds in page_obj]

        return JsonResponse({
            'status': 'success',
            'datasets': datasets_data,
            'pagination': {
                'total': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }
        })

    except Exception as e:
        logger.error(f"Error listing datasets: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def create_dataset(request, model_id):
    """
    Create a new dataset.

    Required fields:
        - name: Dataset name
        - primary_table: Primary BigQuery table (must be raw_data.*)

    Optional fields:
        - description: Dataset description
        - secondary_tables: List of secondary tables for joins
        - join_config: Join configuration for secondary tables
        - selected_columns: Columns to include per table
        - column_mapping: ML concept to column mapping
        - filters: Data filters configuration
        - split_config: Train/eval split configuration
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Validate configuration
        is_valid, errors = validate_dataset_config(data, model)
        if not is_valid:
            return JsonResponse({
                'status': 'error',
                'message': 'Validation failed',
                'errors': errors,
            }, status=400)

        # Create dataset
        dataset = Dataset.objects.create(
            model_endpoint=model,
            name=data.get('name', '').strip(),
            description=data.get('description', ''),
            status='draft',
            primary_table=data.get('primary_table', '').strip(),
            secondary_tables=data.get('secondary_tables', []),
            join_config=data.get('join_config', {}),
            selected_columns=data.get('selected_columns', {}),
            column_mapping=data.get('column_mapping', {}),
            filters=data.get('filters', {}),
            split_config=data.get('split_config', {}),
            created_by=request.user,
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Dataset created successfully',
            'dataset_id': dataset.id,
            'dataset': serialize_dataset(dataset),
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_dataset(request, dataset_id):
    """
    Get dataset details including all configuration.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)

        # Get versions info
        versions = []
        for v in dataset.versions.all()[:5]:  # Last 5 versions
            versions.append({
                'version_number': v.version_number,
                'created_at': v.created_at.isoformat(),
                'actual_row_count': v.actual_row_count,
            })

        response_data = serialize_dataset(dataset, include_details=True)
        response_data['versions'] = versions
        response_data['model_id'] = dataset.model_endpoint.id
        response_data['model_name'] = dataset.model_endpoint.name

        return JsonResponse({
            'status': 'success',
            'dataset': response_data,
        })

    except Exception as e:
        logger.error(f"Error getting dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def update_dataset(request, dataset_id):
    """
    Update an existing dataset.

    All fields are optional - only provided fields will be updated.
    Note: Updating an active dataset will NOT automatically create a new version.
    Versions are created when the dataset is used in training.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        data = json.loads(request.body)

        # Build a merged config for validation
        merged_data = {
            'name': data.get('name', dataset.name),
            'primary_table': data.get('primary_table', dataset.primary_table),
            'secondary_tables': data.get('secondary_tables', dataset.secondary_tables),
            'join_config': data.get('join_config', dataset.join_config),
            'split_config': data.get('split_config', dataset.split_config),
        }

        # Validate the merged configuration
        is_valid, errors = validate_dataset_config(
            merged_data,
            dataset.model_endpoint,
            exclude_dataset_id=dataset_id
        )
        if not is_valid:
            return JsonResponse({
                'status': 'error',
                'message': 'Validation failed',
                'errors': errors,
            }, status=400)

        # Update fields if provided
        if 'name' in data:
            dataset.name = data['name'].strip()

        if 'description' in data:
            dataset.description = data['description']

        if 'primary_table' in data:
            dataset.primary_table = data['primary_table'].strip()

        if 'secondary_tables' in data:
            dataset.secondary_tables = data['secondary_tables']

        if 'join_config' in data:
            dataset.join_config = data['join_config']

        if 'selected_columns' in data:
            dataset.selected_columns = data['selected_columns']

        if 'column_mapping' in data:
            dataset.column_mapping = data['column_mapping']

        if 'filters' in data:
            dataset.filters = data['filters']

        if 'split_config' in data:
            dataset.split_config = data['split_config']

        # Clear cached analysis when config changes
        config_fields = ['primary_table', 'secondary_tables', 'join_config',
                         'selected_columns', 'filters']
        if any(field in data for field in config_fields):
            dataset.row_count_estimate = None
            dataset.unique_users_estimate = None
            dataset.unique_products_estimate = None
            dataset.column_stats = {}

        dataset.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Dataset updated successfully',
            'dataset_id': dataset.id,
            'dataset': serialize_dataset(dataset, include_details=True),
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_dataset(request, dataset_id):
    """
    Delete a dataset.

    Note: Active datasets that have been used in training cannot be deleted
    unless force=true is provided in the request body.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        data = json.loads(request.body) if request.body else {}

        # Check if dataset has been used (has versions)
        if dataset.versions.exists() and not data.get('force'):
            return JsonResponse({
                'status': 'error',
                'message': 'This dataset has version history and may have been used in training. '
                           'Send force=true to delete anyway.',
                'has_versions': True,
                'version_count': dataset.versions.count(),
            }, status=400)

        dataset_name = dataset.name
        model_id = dataset.model_endpoint.id
        dataset.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'Dataset "{dataset_name}" deleted successfully',
            'model_id': model_id,
        })

    except json.JSONDecodeError:
        # Empty body is OK for delete
        dataset = get_object_or_404(Dataset, id=dataset_id)
        if dataset.versions.exists():
            return JsonResponse({
                'status': 'error',
                'message': 'This dataset has version history. Send force=true to delete.',
            }, status=400)
        dataset_name = dataset.name
        model_id = dataset.model_endpoint.id
        dataset.delete()
        return JsonResponse({
            'status': 'success',
            'message': f'Dataset "{dataset_name}" deleted successfully',
            'model_id': model_id,
        })
    except Exception as e:
        logger.error(f"Error deleting dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def check_name(request, model_id):
    """
    Check if a dataset name is available.
    Used by the wizard for real-time validation.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        name = data.get('name', '').strip()
        exclude_id = data.get('exclude_id')  # For edit mode

        if not name:
            return JsonResponse({
                'status': 'error',
                'available': False,
                'message': 'Name is required',
            })

        existing = model.datasets.filter(name=name)
        if exclude_id:
            existing = existing.exclude(id=exclude_id)

        available = not existing.exists()

        return JsonResponse({
            'status': 'success',
            'available': available,
            'message': None if available else f'Dataset "{name}" already exists',
        })

    except Exception as e:
        logger.error(f"Error checking name: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# =============================================================================
# DATASET ACTIONS
# =============================================================================

@login_required
@require_http_methods(["POST"])
def clone_dataset(request, dataset_id):
    """
    Clone an existing dataset.
    """
    try:
        original = get_object_or_404(Dataset, id=dataset_id)
        data = json.loads(request.body) if request.body else {}

        # Generate new name
        new_name = data.get('name', f"{original.name} (Copy)")

        # Check for duplicate name
        if original.model_endpoint.datasets.filter(name=new_name).exists():
            # Add number suffix
            counter = 2
            base_name = new_name
            while original.model_endpoint.datasets.filter(name=new_name).exists():
                new_name = f"{base_name} {counter}"
                counter += 1

        # Create clone
        clone = Dataset.objects.create(
            model_endpoint=original.model_endpoint,
            name=new_name,
            description=original.description,
            status='draft',  # Always start as draft
            primary_table=original.primary_table,
            secondary_tables=original.secondary_tables,
            join_config=original.join_config,
            selected_columns=original.selected_columns,
            column_mapping=original.column_mapping,
            filters=original.filters,
            split_config=original.split_config,
            created_by=request.user,
        )

        return JsonResponse({
            'status': 'success',
            'message': f'Dataset cloned as "{new_name}"',
            'dataset_id': clone.id,
        })

    except Exception as e:
        logger.error(f"Error cloning dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def activate_dataset(request, dataset_id):
    """
    Activate a dataset (change status from draft to active).
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)

        if dataset.status == 'active':
            return JsonResponse({
                'status': 'error',
                'message': 'Dataset is already active',
            }, status=400)

        dataset.status = 'active'
        dataset.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Dataset activated successfully',
        })

    except Exception as e:
        logger.error(f"Error activating dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# =============================================================================
# BIGQUERY INTEGRATION APIs
# =============================================================================

@login_required
@require_http_methods(["GET"])
def list_bq_tables(request, model_id):
    """
    List available BigQuery tables from raw_data.* dataset.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        bq_service = BigQueryService(model)

        tables = bq_service.list_tables()

        return JsonResponse({
            'status': 'success',
            'tables': tables,
        })

    except Exception as e:
        logger.error(f"Error listing BigQuery tables: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_table_schema(request, model_id, table_name):
    """
    Get schema for a BigQuery table.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        bq_service = BigQueryService(model)

        schema = bq_service.get_table_schema(table_name)

        return JsonResponse({
            'status': 'success',
            'table_name': table_name,
            'schema': schema,
        })

    except Exception as e:
        logger.error(f"Error getting table schema: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_table_stats(request, model_id, table_name):
    """
    Get column statistics for a BigQuery table.
    Uses full table scan for accurate statistics.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        bq_service = BigQueryService(model)

        stats = bq_service.get_column_stats(table_name)

        return JsonResponse({
            'status': 'success',
            'table_name': table_name,
            'stats': stats,
        })

    except Exception as e:
        logger.error(f"Error getting table stats: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def detect_joins(request, model_id):
    """
    Auto-detect potential join keys between tables.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        tables = data.get('tables', [])
        if len(tables) < 2:
            return JsonResponse({
                'status': 'error',
                'message': 'At least 2 tables required for join detection',
            }, status=400)

        bq_service = BigQueryService(model)
        joins = bq_service.detect_join_keys(tables)

        return JsonResponse({
            'status': 'success',
            'detected_joins': joins,
        })

    except Exception as e:
        logger.error(f"Error detecting joins: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def suggest_columns(request, model_id):
    """
    Suggest column mappings for ML concepts based on selected tables.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        tables = data.get('tables', [])
        if not tables:
            return JsonResponse({
                'status': 'error',
                'message': 'At least 1 table required for column suggestions',
            }, status=400)

        bq_service = BigQueryService(model)
        suggestions = bq_service.suggest_columns(tables)

        return JsonResponse({
            'status': 'success',
            'suggestions': suggestions,
        })

    except Exception as e:
        logger.error(f"Error suggesting columns: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_sample_values(request, model_id, table_name, column_name):
    """
    Get sample distinct values for a column.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        limit = int(request.GET.get('limit', 10))

        bq_service = BigQueryService(model)
        values = bq_service.get_sample_values(table_name, column_name, limit=limit)

        return JsonResponse({
            'status': 'success',
            'table_name': table_name,
            'column_name': column_name,
            'sample_values': values,
        })

    except Exception as e:
        logger.error(f"Error getting sample values: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def validate_query(request, dataset_id):
    """
    Validate the generated BigQuery query without executing it (dry run).
    Returns estimated bytes processed and cost.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        query = bq_service.generate_query(dataset)
        validation = bq_service.validate_query(query)

        return JsonResponse({
            'status': 'success',
            'query': query,
            'validation': validation,
        })

    except Exception as e:
        logger.error(f"Error validating query: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# =============================================================================
# DATASET ANALYSIS APIs
# =============================================================================

@login_required
@require_http_methods(["POST"])
def analyze_dataset(request, dataset_id):
    """
    Analyze a dataset to get row counts, unique counts, split estimates, etc.

    This performs a BigQuery query to calculate:
    - Total row count after filters
    - Unique users and products
    - Date range of data
    - Train/eval split estimates based on split_config
    - Data quality metrics
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        # Run base analysis
        analysis = bq_service.analyze_dataset(dataset)

        # Calculate train/eval split estimates
        split_info = calculate_split_estimates(dataset, analysis)
        analysis['split_estimates'] = split_info

        # Calculate data quality metrics
        quality_metrics = calculate_quality_metrics(analysis)
        analysis['quality_metrics'] = quality_metrics

        # Update dataset with analysis results
        dataset.row_count_estimate = analysis.get('row_count')
        dataset.unique_users_estimate = analysis.get('unique_users')
        dataset.unique_products_estimate = analysis.get('unique_products')
        dataset.date_range_start = analysis.get('date_range_start')
        dataset.date_range_end = analysis.get('date_range_end')
        dataset.column_stats = analysis.get('column_stats', {})
        dataset.save()

        # Format dates for JSON response
        if analysis.get('date_range_start'):
            analysis['date_range_start'] = analysis['date_range_start'].isoformat()
        if analysis.get('date_range_end'):
            analysis['date_range_end'] = analysis['date_range_end'].isoformat()

        return JsonResponse({
            'status': 'success',
            'analysis': analysis,
            'dataset_id': dataset.id,
        })

    except Exception as e:
        logger.error(f"Error analyzing dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


def calculate_split_estimates(dataset, analysis):
    """
    Calculate train/eval split estimates based on dataset configuration.

    Args:
        dataset: Dataset model instance
        analysis: Analysis results dict

    Returns:
        Dict with split estimates
    """
    split_config = dataset.split_config or {}
    strategy = split_config.get('strategy', 'time_based')
    row_count = analysis.get('row_count', 0)

    if strategy == 'random':
        train_percent = split_config.get('train_percent', 80)
        train_rows = int(row_count * train_percent / 100)
        eval_rows = row_count - train_rows

        return {
            'strategy': 'random',
            'train_percent': train_percent,
            'eval_percent': 100 - train_percent,
            'estimated_train_rows': train_rows,
            'estimated_eval_rows': eval_rows,
        }

    elif strategy == 'time_based':
        eval_days = split_config.get('eval_days', 14)
        date_start = analysis.get('date_range_start')
        date_end = analysis.get('date_range_end')

        if date_start and date_end:
            total_days = (date_end - date_start).days
            if total_days > 0:
                train_days = total_days - eval_days
                train_percent = round(train_days / total_days * 100, 1)
                eval_percent = round(eval_days / total_days * 100, 1)

                # Estimate rows (assuming uniform distribution)
                train_rows = int(row_count * train_percent / 100)
                eval_rows = row_count - train_rows

                return {
                    'strategy': 'time_based',
                    'eval_days': eval_days,
                    'total_days': total_days,
                    'train_days': train_days,
                    'train_percent': train_percent,
                    'eval_percent': eval_percent,
                    'estimated_train_rows': train_rows,
                    'estimated_eval_rows': eval_rows,
                    'train_end_date': (date_end - timezone.timedelta(days=eval_days)).isoformat() if date_end else None,
                    'eval_start_date': (date_end - timezone.timedelta(days=eval_days)).isoformat() if date_end else None,
                }

    return {
        'strategy': strategy or 'not_configured',
        'estimated_train_rows': row_count,
        'estimated_eval_rows': 0,
    }


def calculate_quality_metrics(analysis):
    """
    Calculate data quality metrics from analysis results.

    Args:
        analysis: Analysis results dict

    Returns:
        Dict with quality metrics
    """
    row_count = analysis.get('row_count', 0)
    unique_users = analysis.get('unique_users', 0)
    unique_products = analysis.get('unique_products', 0)

    if row_count == 0:
        return {'overall_score': 0, 'issues': ['No data found']}

    issues = []
    score = 100

    # Check interaction density
    avg_per_user = analysis.get('avg_items_per_user', 0)
    avg_per_product = analysis.get('avg_users_per_product', 0)

    if avg_per_user < 2:
        issues.append(f'Low user engagement: avg {avg_per_user:.1f} interactions per user')
        score -= 15

    if avg_per_product < 5:
        issues.append(f'Sparse product coverage: avg {avg_per_product:.1f} users per product')
        score -= 10

    # Check for cold start issues
    if unique_users < 100:
        issues.append(f'Very few users ({unique_users}). Model may not generalize well.')
        score -= 20

    if unique_products < 50:
        issues.append(f'Very few products ({unique_products}). Consider expanding catalog.')
        score -= 15

    # Check sparsity
    if unique_users > 0 and unique_products > 0:
        sparsity = 1 - (row_count / (unique_users * unique_products))
        if sparsity > 0.9999:
            issues.append(f'Extremely sparse data ({sparsity*100:.4f}% empty). Collaborative filtering may struggle.')
            score -= 20
        elif sparsity > 0.999:
            issues.append(f'Very sparse data ({sparsity*100:.2f}% empty). Consider content-based features.')
            score -= 10

    # Date range check
    date_start = analysis.get('date_range_start')
    date_end = analysis.get('date_range_end')
    if date_start and date_end:
        days = (date_end - date_start).days
        if days < 30:
            issues.append(f'Short date range ({days} days). More history would improve model.')
            score -= 15
        elif days < 90:
            issues.append(f'Limited date range ({days} days). 3+ months recommended.')
            score -= 5

    # Determine overall rating
    if score >= 80:
        rating = 'excellent'
    elif score >= 60:
        rating = 'good'
    elif score >= 40:
        rating = 'fair'
    else:
        rating = 'poor'

    return {
        'overall_score': max(0, score),
        'rating': rating,
        'issues': issues if issues else ['No issues detected'],
        'metrics': {
            'avg_interactions_per_user': round(avg_per_user, 2),
            'avg_users_per_product': round(avg_per_product, 2),
            'user_count': unique_users,
            'product_count': unique_products,
            'interaction_count': row_count,
        }
    }


@login_required
@require_http_methods(["GET"])
def preview_dataset(request, dataset_id):
    """
    Preview sample data from a dataset.

    Query params:
        - limit: Max rows to return (default 100, max 1000)
        - offset: Skip first N rows (default 0)
        - format: 'table' (default) or 'json'
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        limit = min(int(request.GET.get('limit', 100)), 1000)
        output_format = request.GET.get('format', 'table')

        preview = bq_service.preview_dataset(dataset, limit=limit)

        # Add column mapping info for display
        column_mapping = dataset.column_mapping or {}
        reverse_mapping = {v: k for k, v in column_mapping.items()}

        # Enrich columns with mapping info
        for col in preview.get('columns', []):
            col_name = col['name']
            if col_name in reverse_mapping:
                col['ml_role'] = reverse_mapping[col_name]

        return JsonResponse({
            'status': 'success',
            'preview': preview,
            'dataset_name': dataset.name,
            'format': output_format,
        })

    except Exception as e:
        logger.error(f"Error previewing dataset: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_generated_query(request, dataset_id):
    """
    Get the generated BigQuery SQL for a dataset.

    Query params:
        - for_analysis: If 'true', use mapped column names
        - split: 'train', 'eval', or empty for full dataset
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        for_analysis = request.GET.get('for_analysis', 'false').lower() == 'true'
        split = request.GET.get('split', None)
        if split and split not in ('train', 'eval'):
            return JsonResponse({
                'status': 'error',
                'message': "split must be 'train', 'eval', or empty",
            }, status=400)

        query = bq_service.generate_query(dataset, for_analysis=for_analysis, split=split)

        # Get validation info
        validation = bq_service.validate_query(query)

        return JsonResponse({
            'status': 'success',
            'query': query,
            'for_analysis': for_analysis,
            'split': split,
            'validation': validation,
            'dataset_name': dataset.name,
        })

    except Exception as e:
        logger.error(f"Error generating query: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_split_queries(request, dataset_id):
    """
    Get both train and eval queries for a dataset.
    Useful for reviewing the split before training.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        for_analysis = request.GET.get('for_analysis', 'true').lower() == 'true'

        train_query = bq_service.generate_train_query(dataset, for_analysis=for_analysis)
        eval_query = bq_service.generate_eval_query(dataset, for_analysis=for_analysis)

        # Validate both queries
        train_validation = bq_service.validate_query(train_query)
        eval_validation = bq_service.validate_query(eval_query)

        return JsonResponse({
            'status': 'success',
            'dataset_name': dataset.name,
            'split_config': dataset.split_config,
            'queries': {
                'train': {
                    'query': train_query,
                    'validation': train_validation,
                },
                'eval': {
                    'query': eval_query,
                    'validation': eval_validation,
                },
            },
            'total_estimated_cost_usd': (
                (train_validation.get('estimated_cost_usd', 0) or 0) +
                (eval_validation.get('estimated_cost_usd', 0) or 0)
            ),
        })

    except Exception as e:
        logger.error(f"Error generating split queries: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_tfx_queries(request, dataset_id):
    """
    Get queries formatted for TFX ExampleGen component.
    Returns train/eval queries with TFX configuration.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        tfx_config = bq_service.generate_tfx_queries(dataset)

        return JsonResponse({
            'status': 'success',
            'dataset_name': dataset.name,
            'dataset_id': dataset.id,
            **tfx_config,
        })

    except Exception as e:
        logger.error(f"Error generating TFX queries: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_dataset_summary(request, dataset_id):
    """
    Get a summary of dataset configuration and cached analysis.
    Does NOT run a new BigQuery query - returns cached data.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)

        # Calculate table info
        tables = dataset.get_all_tables()
        total_columns = sum(len(cols) for cols in (dataset.selected_columns or {}).values())

        # Get filter summary
        filters = dataset.filters or {}
        filter_summary = []

        date_filter = filters.get('date_range', {})
        if date_filter.get('type') == 'rolling':
            filter_summary.append(f"Last {date_filter.get('months', 6)} months")
        elif date_filter.get('type') == 'fixed':
            start = date_filter.get('start', 'N/A')
            end = date_filter.get('end', 'N/A')
            filter_summary.append(f"Date: {start} to {end}")

        product_filter = filters.get('product_filter', {})
        if product_filter.get('type') == 'top_revenue_percent':
            filter_summary.append(f"Top {product_filter.get('value', 80)}% products by revenue")

        customer_filter = filters.get('customer_filter', {})
        if customer_filter.get('type') == 'min_transactions':
            filter_summary.append(f"Min {customer_filter.get('value', 2)} transactions per customer")

        # Get split summary
        split_config = dataset.split_config or {}
        split_summary = "Not configured"
        if split_config.get('strategy') == 'time_based':
            split_summary = f"Time-based: last {split_config.get('eval_days', 14)} days for eval"
        elif split_config.get('strategy') == 'random':
            split_summary = f"Random: {split_config.get('train_percent', 80)}% train"

        summary = {
            'id': dataset.id,
            'name': dataset.name,
            'description': dataset.description,
            'status': dataset.status,
            'tables': {
                'primary': dataset.primary_table,
                'secondary': dataset.secondary_tables or [],
                'total_count': len(tables),
            },
            'columns': {
                'total_selected': total_columns,
                'mapping': dataset.column_mapping or {},
            },
            'filters': {
                'summary': filter_summary if filter_summary else ['No filters applied'],
                'config': filters,
            },
            'split': {
                'summary': split_summary,
                'config': split_config,
            },
            'cached_analysis': {
                'row_count': dataset.row_count_estimate,
                'unique_users': dataset.unique_users_estimate,
                'unique_products': dataset.unique_products_estimate,
                'date_range_start': dataset.date_range_start.isoformat() if dataset.date_range_start else None,
                'date_range_end': dataset.date_range_end.isoformat() if dataset.date_range_end else None,
                'has_analysis': dataset.row_count_estimate is not None,
            },
            'timestamps': {
                'created_at': dataset.created_at.isoformat(),
                'updated_at': dataset.updated_at.isoformat(),
                'last_used_at': dataset.last_used_at.isoformat() if dataset.last_used_at else None,
            },
            'version_count': dataset.versions.count(),
        }

        return JsonResponse({
            'status': 'success',
            'summary': summary,
        })

    except Exception as e:
        logger.error(f"Error getting dataset summary: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def compare_datasets(request, model_id):
    """
    Compare two or more datasets side by side.
    Useful for understanding differences between dataset configurations.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        dataset_ids = data.get('dataset_ids', [])
        if len(dataset_ids) < 2:
            return JsonResponse({
                'status': 'error',
                'message': 'At least 2 dataset IDs required for comparison',
            }, status=400)

        if len(dataset_ids) > 5:
            return JsonResponse({
                'status': 'error',
                'message': 'Maximum 5 datasets can be compared at once',
            }, status=400)

        # Fetch datasets
        datasets = Dataset.objects.filter(
            id__in=dataset_ids,
            model_endpoint=model
        )

        if datasets.count() != len(dataset_ids):
            return JsonResponse({
                'status': 'error',
                'message': 'Some dataset IDs not found or do not belong to this model',
            }, status=404)

        comparison = []
        for ds in datasets:
            comparison.append({
                'id': ds.id,
                'name': ds.name,
                'status': ds.status,
                'tables': {
                    'primary': ds.primary_table,
                    'secondary_count': len(ds.secondary_tables or []),
                },
                'columns': {
                    'total': sum(len(cols) for cols in (ds.selected_columns or {}).values()),
                    'mapped': len(ds.column_mapping or {}),
                },
                'filters': {
                    'date_range': ds.filters.get('date_range', {}).get('type') if ds.filters else None,
                    'has_product_filter': bool(ds.filters.get('product_filter')) if ds.filters else False,
                    'has_customer_filter': bool(ds.filters.get('customer_filter')) if ds.filters else False,
                },
                'split': ds.split_config.get('strategy') if ds.split_config else None,
                'analysis': {
                    'row_count': ds.row_count_estimate,
                    'unique_users': ds.unique_users_estimate,
                    'unique_products': ds.unique_products_estimate,
                    'date_range_start': ds.date_range_start.isoformat() if ds.date_range_start else None,
                    'date_range_end': ds.date_range_end.isoformat() if ds.date_range_end else None,
                },
                'updated_at': ds.updated_at.isoformat(),
            })

        return JsonResponse({
            'status': 'success',
            'comparison': comparison,
            'dataset_count': len(comparison),
        })

    except Exception as e:
        logger.error(f"Error comparing datasets: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# =============================================================================
# VISUAL SCHEMA BUILDER APIs (Preview Service)
# =============================================================================

@login_required
@require_http_methods(["POST"])
def load_samples(request, model_id):
    """
    Load random samples from BigQuery tables for the Visual Schema Builder.

    This creates a session with cached sample data that can be used for
    fast preview generation without repeated BigQuery queries.

    Request body:
        {
            "tables": ["raw_data.transactions", "raw_data.products", ...]
        }

    Returns:
        {
            "status": "success",
            "session_id": "abc12345",
            "tables": {
                "raw_data.transactions": {
                    "columns": [...],
                    "row_count": 100,
                    "sample_preview": [...]
                },
                ...
            }
        }
    """
    try:
        from .preview_service import DatasetPreviewService

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        tables = data.get('tables', [])
        if not tables:
            return JsonResponse({
                'status': 'error',
                'message': 'At least one table is required',
            }, status=400)

        # Validate tables are from raw_data
        for table in tables:
            if not table.startswith('raw_data.'):
                return JsonResponse({
                    'status': 'error',
                    'message': f'Table {table} must be from raw_data dataset',
                }, status=400)

        preview_service = DatasetPreviewService(model)
        result = preview_service.load_samples(tables)

        return JsonResponse({
            'status': 'success',
            **result,
        })

    except Exception as e:
        logger.error(f"Error loading samples: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def generate_preview(request, model_id):
    """
    Generate a preview of the dataset based on current join/column configuration.

    Uses cached sample data from load_samples() to perform pandas joins
    and return a preview of the resulting dataset.

    Request body:
        {
            "session_id": "abc12345",
            "primary_table": "raw_data.transactions",
            "joins": [
                {
                    "table": "raw_data.products",
                    "left_col": "product_id",
                    "right_col": "product_id",
                    "type": "left"
                }
            ],
            "selected_columns": {
                "raw_data.transactions": ["id", "amount", "product_id"],
                "raw_data.products": ["name", "category"]
            }
        }

    Returns:
        {
            "status": "success",
            "preview_rows": [...10 rows...],
            "column_order": ["transactions_id", "transactions_amount", ...],
            "stats": {
                "total_rows": 87,
                "null_counts": {"products_name": 3},
                "warnings": []
            }
        }
    """
    try:
        from .preview_service import DatasetPreviewService

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        session_id = data.get('session_id')
        if not session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'session_id is required',
            }, status=400)

        primary_table = data.get('primary_table')
        if not primary_table:
            return JsonResponse({
                'status': 'error',
                'message': 'primary_table is required',
            }, status=400)

        joins = data.get('joins', [])
        selected_columns = data.get('selected_columns', {})

        preview_service = DatasetPreviewService(model)

        try:
            result = preview_service.generate_preview(
                session_id=session_id,
                primary_table=primary_table,
                joins=joins,
                selected_columns=selected_columns
            )
        except ValueError as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e),
            }, status=400)

        return JsonResponse({
            'status': 'success',
            **result,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def detect_joins_preview(request, model_id):
    """
    Auto-detect potential joins between tables using cached session data.

    Request body:
        {
            "session_id": "abc12345"
        }

    Returns:
        {
            "status": "success",
            "suggested_joins": [
                {
                    "left_table": "raw_data.transactions",
                    "left_col": "product_id",
                    "right_table": "raw_data.products",
                    "right_col": "product_id",
                    "confidence": "high",
                    "reason": "Exact column name match"
                }
            ]
        }
    """
    try:
        from .preview_service import DatasetPreviewService

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        session_id = data.get('session_id')
        if not session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'session_id is required',
            }, status=400)

        preview_service = DatasetPreviewService(model)

        try:
            suggestions = preview_service.detect_joins(session_id)
        except ValueError as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e),
            }, status=400)

        return JsonResponse({
            'status': 'success',
            'suggested_joins': suggestions,
        })

    except Exception as e:
        logger.error(f"Error detecting joins: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def cleanup_preview_session(request, model_id):
    """
    Clean up a preview session and release cached data.

    Request body:
        {
            "session_id": "abc12345"
        }

    Returns:
        {
            "status": "success",
            "message": "Session cleaned up"
        }
    """
    try:
        from .preview_service import DatasetPreviewService

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        session_id = data.get('session_id')
        if not session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'session_id is required',
            }, status=400)

        preview_service = DatasetPreviewService(model)
        found = preview_service.cleanup_session(session_id)

        return JsonResponse({
            'status': 'success',
            'message': 'Session cleaned up' if found else 'Session not found (may have expired)',
        })

    except Exception as e:
        logger.error(f"Error cleaning up session: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# =============================================================================
# PRODUCT REVENUE ANALYSIS APIs
# =============================================================================

@login_required
@require_http_methods(["POST"])
def analyze_product_revenue(request, model_id):
    """
    Analyze product revenue distribution for filtering.

    This endpoint calculates the cumulative revenue distribution across products,
    enabling users to filter their dataset to include only top-performing products
    (e.g., products generating 80% of total revenue).

    Request body:
        {
            "primary_table": "raw_data.transactions",
            "product_column": "transactions.product_id",
            "revenue_column": "transactions.amount",
            "timestamp_column": "transactions.transaction_date",  // optional
            "rolling_days": 30  // optional, requires timestamp_column
        }

    Returns:
        {
            "status": "success",
            "total_products": 48234,
            "total_revenue": 15500000.0,
            "date_range": {"start": "2024-11-03", "end": "2024-12-03"},
            "distribution": [
                {"percent_products": 1, "cumulative_revenue_percent": 15.2},
                {"percent_products": 5, "cumulative_revenue_percent": 42.1},
                ...
            ],
            "thresholds": {
                "70": {"products": 2891, "percent": 6.0},
                "80": {"products": 4521, "percent": 9.4},
                "90": {"products": 8234, "percent": 17.1},
                "95": {"products": 15234, "percent": 31.6}
            }
        }
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Validate required fields
        primary_table = data.get('primary_table')
        product_column = data.get('product_column')
        revenue_column = data.get('revenue_column')

        if not primary_table:
            return JsonResponse({
                'status': 'error',
                'message': 'primary_table is required',
            }, status=400)

        if not product_column:
            return JsonResponse({
                'status': 'error',
                'message': 'product_column is required',
            }, status=400)

        if not revenue_column:
            return JsonResponse({
                'status': 'error',
                'message': 'revenue_column is required',
            }, status=400)

        # Optional fields
        timestamp_column = data.get('timestamp_column')
        rolling_days = data.get('rolling_days')

        # Validate rolling_days requires timestamp_column
        if rolling_days and not timestamp_column:
            return JsonResponse({
                'status': 'error',
                'message': 'timestamp_column is required when rolling_days is specified',
            }, status=400)

        # Run the analysis
        analysis_service = ProductRevenueAnalysisService(model)
        result = analysis_service.analyze_distribution(
            primary_table=primary_table,
            product_column=product_column,
            revenue_column=revenue_column,
            timestamp_column=timestamp_column,
            rolling_days=rolling_days
        )

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error analyzing product revenue: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)
