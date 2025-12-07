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
from .services import BigQueryService, ProductRevenueAnalysisService, DatasetStatsService, ColumnAnalysisService

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

    # NOTE: split_config validation removed - handled by Training domain

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
        - page: Page number (default 1)
        - per_page: Items per page (default 10, max 50)
        - search: Search in name/description
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        datasets = model.datasets.all().order_by('-updated_at')

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

        # Create dataset (split_config removed - handled by Training domain)
        dataset = Dataset.objects.create(
            model_endpoint=model,
            name=data.get('name', '').strip(),
            description=data.get('description', ''),
            primary_table=data.get('primary_table', '').strip(),
            secondary_tables=data.get('secondary_tables', []),
            join_config=data.get('join_config', {}),
            selected_columns=data.get('selected_columns', {}),
            column_mapping=data.get('column_mapping', {}),
            filters=data.get('filters', {}),
            summary_snapshot=data.get('summary_snapshot', {}),
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

        # Update fields if provided (split_config removed - handled by Training domain)
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

        if 'summary_snapshot' in data:
            dataset.summary_snapshot = data['summary_snapshot']

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
            primary_table=original.primary_table,
            secondary_tables=original.secondary_tables,
            join_config=original.join_config,
            selected_columns=original.selected_columns,
            column_mapping=original.column_mapping,
            filters=original.filters,
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
@require_http_methods(["GET"])
def check_join_key_uniqueness(request, model_id, table_name, column_name):
    """
    Check if a column has unique values (suitable as a join key).

    Non-unique join keys cause row multiplication in JOINs.
    This endpoint helps users identify potential issues before creating joins.

    Returns:
        {
            "status": "success",
            "table": "raw_data.products",
            "column": "product_code",
            "total_rows": 16,
            "unique_values": 4,
            "is_unique": false,
            "duplication_factor": 4.0,
            "warning": "Column 'product_code' has 4 unique values but 16 rows..."
        }
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        bq_service = BigQueryService(model)

        result = bq_service.check_join_key_uniqueness(table_name, column_name)

        return JsonResponse({
            'status': 'success',
            **result
        })

    except Exception as e:
        logger.error(f"Error checking join key uniqueness: {e}")
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
def get_dataset_query(request, dataset_id):
    """
    Get the base query for a dataset.

    Note: Train/eval split is now handled by the Training domain.
    This endpoint returns only the base query without split.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        for_analysis = request.GET.get('for_analysis', 'true').lower() == 'true'

        # Generate base query (no split - handled by Training domain)
        base_query = bq_service.generate_query(dataset, for_analysis=for_analysis)
        base_validation = bq_service.validate_query(base_query)

        return JsonResponse({
            'status': 'success',
            'dataset_name': dataset.name,
            'query': base_query,
            'validation': base_validation,
            'estimated_cost_usd': base_validation.get('estimated_cost_usd', 0) or 0,
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
    Get a summary of dataset configuration and saved summary snapshot.
    Does NOT run a new BigQuery query - returns saved snapshot data from wizard Step 4.
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)

        # Calculate table info
        tables = dataset.get_all_tables()
        total_columns = sum(len(cols) for cols in (dataset.selected_columns or {}).values())

        # Get summary snapshot (saved from Step 4 Dataset Summary panel)
        snapshot = dataset.summary_snapshot or {}

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
                'selected': dataset.selected_columns or {},
                'mapping': dataset.column_mapping or {},
            },
            # Join configuration for connecting tables
            'join_config': dataset.join_config or {},
            'filters': {
                'config': dataset.filters or {},
            },
            # Summary snapshot from wizard Step 4
            'summary_snapshot': {
                'total_rows': snapshot.get('total_rows', 0),
                'filters_applied': snapshot.get('filters_applied', {}),
                'column_stats': snapshot.get('column_stats', {}),
                'snapshot_at': snapshot.get('snapshot_at'),
                'has_snapshot': bool(snapshot.get('column_stats')),
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


@login_required
@require_http_methods(["POST"])
def get_dataset_stats(request, model_id):
    """
    Get comprehensive statistics for a dataset configuration.

    Used by the Dataset Summary panel in Step 4 to show users how filter
    parameters impact the dataset size and provide column-level statistics.

    Two main use cases:
    1. Initial load (no filters) - shows raw dataset stats when Step 4 opens
    2. With filters applied - shows filtered dataset stats after "Refresh Dataset"

    Request body:
        {
            "primary_table": "raw_data.transactions",
            "selected_columns": {
                "raw_data.transactions": ["customer_id", "product_id", "amount", "trans_date"],
                "raw_data.products": ["product_id", "category"]
            },
            "secondary_tables": ["raw_data.products"],  // optional
            "join_config": {  // optional, required if secondary_tables provided
                "raw_data.products": {
                    "join_key": "product_id",
                    "secondary_column": "product_id",
                    "join_type": "LEFT"
                }
            },
            "filters": {  // optional - omit for initial/unfiltered stats
                "timestamp_column": "transactions.trans_date",
                "date_filter": {"type": "rolling", "days": 30},
                "customer_filter": {"type": "min_transactions", "column": "customer_id", "value": 2},
                "product_filter": {"type": "top_revenue", "product_column": "product_id", "revenue_column": "amount", "percent": 80}
            }
        }

    Returns:
        {
            "status": "success",
            "filters_applied": {
                "dates": {"type": "none"} | {"type": "rolling", "days": 30},
                "customers": {"type": "none"} | {"type": "min_transactions", "value": 2},
                "products": {"type": "none"} | {"type": "top_revenue", "percent": 80}
            },
            "summary": {
                "total_rows": 2450000,
                "unique_customers": 98000,
                "unique_products": 36000,
                "date_range": {"min": "2024-06-01", "max": "2024-12-03"}
            },
            "column_stats": {
                "transactions.amount": {"type": "FLOAT64", "min": 0.5, "max": 12450, "avg": 45.67},
                "transactions.customer_id": {"type": "STRING", "unique_count": 98000},
                ...
            }
        }
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Validate required fields
        primary_table = data.get('primary_table')
        selected_columns = data.get('selected_columns', {})

        if not primary_table:
            return JsonResponse({
                'status': 'error',
                'message': 'primary_table is required',
            }, status=400)

        if not selected_columns:
            return JsonResponse({
                'status': 'error',
                'message': 'selected_columns is required',
            }, status=400)

        # Optional fields
        secondary_tables = data.get('secondary_tables', [])
        join_config = data.get('join_config', {})
        filters = data.get('filters')  # None means no filters (initial load)

        # Run the stats calculation
        stats_service = DatasetStatsService(model)
        result = stats_service.get_dataset_stats(
            primary_table=primary_table,
            selected_columns=selected_columns,
            secondary_tables=secondary_tables,
            join_config=join_config,
            filters=filters
        )

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error getting dataset stats: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# =============================================================================
# COLUMN ANALYSIS (for Product Filters)
# =============================================================================

@login_required
@require_http_methods(["POST"])
def analyze_columns_for_filters(request, model_id):
    """
    Analyze selected columns to provide metadata for product filtering.

    Uses cached sample data from Step 3 (Schema Builder) to analyze columns
    and return information needed to build filter UIs:
    - STRING columns: unique values, counts, display mode (list vs autocomplete)
    - NUMERIC columns: min, max, mean, null stats

    Request body:
        {
            "session_id": "abc12345",  // From load_samples()
            "selected_columns": {
                "raw_data.transactions": ["category", "price", "amount"],
                "raw_data.products": ["brand", "subcategory"]
            }
        }

    Returns:
        {
            "status": "success",
            "columns": {
                "transactions.category": {
                    "type": "STRING",
                    "unique_count": 12,
                    "display_mode": "list",
                    "values": [
                        {"value": "Electronics", "count": 45},
                        {"value": "Clothing", "count": 32}
                    ],
                    "null_count": 5,
                    "null_percent": 5.0,
                    "total_rows": 100,
                    "filterable": true,
                    "filter_type": "category"
                },
                "transactions.price": {
                    "type": "FLOAT",
                    "min": 0.50,
                    "max": 12450.00,
                    "mean": 245.67,
                    "null_count": 2,
                    "null_percent": 2.0,
                    "total_rows": 100,
                    "filterable": true,
                    "filter_type": "numeric"
                }
            }
        }
    """
    try:
        from .preview_service import DatasetPreviewService
        from django.core.cache import cache

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        session_id = data.get('session_id')
        selected_columns = data.get('selected_columns', {})

        if not session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'session_id is required',
            }, status=400)

        if not selected_columns:
            return JsonResponse({
                'status': 'error',
                'message': 'selected_columns is required',
            }, status=400)

        # Get cached session data
        preview_service = DatasetPreviewService(model)
        session_data = preview_service._get_from_cache(session_id)

        if not session_data:
            return JsonResponse({
                'status': 'error',
                'message': f'Session {session_id} not found or expired. Please reload samples.',
            }, status=404)

        # Analyze columns using the service
        analysis_service = ColumnAnalysisService(session_data)
        result = analysis_service.analyze_columns(selected_columns)

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error analyzing columns for filters: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def search_category_values(request, model_id):
    """
    Search for category values in a STRING column (for autocomplete mode).

    When a column has >100 unique values, the UI switches to autocomplete mode.
    This endpoint allows searching for values matching a search term.

    Request body:
        {
            "session_id": "abc12345",
            "table_name": "raw_data.products",
            "column_name": "brand",
            "search_term": "Nik",
            "limit": 20  // optional, default 20
        }

    Returns:
        {
            "status": "success",
            "values": [
                {"value": "Nike", "count": 45},
                {"value": "Nikita", "count": 12}
            ]
        }
    """
    try:
        from .preview_service import DatasetPreviewService

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        session_id = data.get('session_id')
        table_name = data.get('table_name')
        column_name = data.get('column_name')
        search_term = data.get('search_term', '')
        limit = data.get('limit', 20)

        if not session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'session_id is required',
            }, status=400)

        if not table_name or not column_name:
            return JsonResponse({
                'status': 'error',
                'message': 'table_name and column_name are required',
            }, status=400)

        # Get cached session data
        preview_service = DatasetPreviewService(model)
        session_data = preview_service._get_from_cache(session_id)

        if not session_data:
            return JsonResponse({
                'status': 'error',
                'message': f'Session {session_id} not found or expired. Please reload samples.',
            }, status=404)

        # Search using the analysis service
        analysis_service = ColumnAnalysisService(session_data)
        values = analysis_service.search_category_values(
            table_name=table_name,
            column_name=column_name,
            search_term=search_term,
            limit=limit
        )

        return JsonResponse({
            'status': 'success',
            'values': values,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error searching category values: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# =============================================================================
# CUSTOMER REVENUE ANALYSIS API
# =============================================================================

@login_required
@require_http_methods(["POST"])
def analyze_customer_revenue(request, model_id):
    """
    Analyze customer revenue distribution for filtering.

    This endpoint calculates the cumulative revenue distribution across customers,
    enabling users to filter their dataset to include only top-performing customers
    (e.g., customers generating 80% of total revenue).

    Uses cached session data (pandas DataFrames) for fast analysis.

    Request body:
        {
            "session_id": "abc12345",
            "customer_column": "transactions.customer_id",
            "revenue_column": "transactions.amount"
        }

    Returns:
        {
            "status": "success",
            "total_customers": 98234,
            "total_revenue": 15500000.0,
            "distribution": [
                {"customer_percent": 1, "cumulative_revenue_percent": 8.2},
                {"customer_percent": 5, "cumulative_revenue_percent": 28.1},
                ...
            ],
            "thresholds": {
                "70": {"customers": 12891, "percent": 13.1},
                "80": {"customers": 18521, "percent": 18.9},
                "90": {"customers": 32234, "percent": 32.8},
                "95": {"customers": 52234, "percent": 53.2}
            }
        }
    """
    try:
        from .preview_service import DatasetPreviewService
        from .services import CustomerRevenueAnalysisService

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Validate required fields
        session_id = data.get('session_id')
        customer_column = data.get('customer_column')
        revenue_column = data.get('revenue_column')

        if not session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'session_id is required',
            }, status=400)

        if not customer_column:
            return JsonResponse({
                'status': 'error',
                'message': 'customer_column is required',
            }, status=400)

        if not revenue_column:
            return JsonResponse({
                'status': 'error',
                'message': 'revenue_column is required',
            }, status=400)

        # Get cached session data to extract table info
        preview_service = DatasetPreviewService(model)
        session_data = preview_service._get_from_cache(session_id)

        if not session_data:
            return JsonResponse({
                'status': 'error',
                'message': f'Session {session_id} not found or expired. Please reload samples.',
            }, status=404)

        # Get the primary table from session data
        primary_table = session_data.get('primary_table')
        if not primary_table:
            # Fallback: extract from customer_column (format: "table.column")
            if '.' in customer_column:
                table_hint = customer_column.rsplit('.', 1)[0]
                # Find matching table in session
                for table_name in session_data.get('tables', {}).keys():
                    if table_name.endswith(table_hint) or table_name.split('.')[-1] == table_hint:
                        primary_table = table_name
                        break

        if not primary_table:
            return JsonResponse({
                'status': 'error',
                'message': 'Could not determine primary table from session data',
            }, status=400)

        # Get optional date filter params
        timestamp_column = data.get('timestamp_column')
        rolling_days = data.get('rolling_days')

        # Run the analysis using BigQuery
        analysis_service = CustomerRevenueAnalysisService(model)
        result = analysis_service.analyze_distribution(
            primary_table=primary_table,
            customer_column=customer_column,
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
        logger.error(f"Error analyzing customer revenue: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def analyze_customer_aggregations(request, model_id):
    """
    Analyze customer aggregation metrics (transaction count, spending).

    Used to provide statistics and distributions to help users set appropriate
    filter thresholds for transaction count and spending filters.

    Request body:
        {
            "session_id": "abc12345",
            "analysis_type": "transaction_count" | "spending",
            "customer_column": "transactions.customer_id",
            "amount_column": "transactions.amount"  // required for spending
        }

    Returns for transaction_count:
        {
            "status": "success",
            "total_customers": 98234,
            "total_transactions": 1500000,
            "stats": {
                "min": 1, "max": 523, "mean": 15.3, "median": 8,
                "percentiles": {"25": 3, "50": 8, "75": 18, "90": 32, "95": 52}
            },
            "distribution": [...]
        }

    Returns for spending:
        {
            "status": "success",
            "total_customers": 98234,
            "total_spending": 15500000.0,
            "stats": {
                "min": 0.50, "max": 152300.00, "mean": 157.85, "median": 82.50,
                "percentiles": {"25": 35.00, "50": 82.50, "75": 185.00, "90": 380.00, "95": 625.00}
            }
        }
    """
    try:
        from .preview_service import DatasetPreviewService
        from .services import CustomerAggregationService

        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Validate required fields
        session_id = data.get('session_id')
        analysis_type = data.get('analysis_type')
        customer_column = data.get('customer_column')

        if not session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'session_id is required',
            }, status=400)

        if not analysis_type:
            return JsonResponse({
                'status': 'error',
                'message': 'analysis_type is required (transaction_count or spending)',
            }, status=400)

        if analysis_type not in ['transaction_count', 'spending']:
            return JsonResponse({
                'status': 'error',
                'message': 'analysis_type must be "transaction_count" or "spending"',
            }, status=400)

        if not customer_column:
            return JsonResponse({
                'status': 'error',
                'message': 'customer_column is required',
            }, status=400)

        # For spending analysis, amount_column is required
        amount_column = data.get('amount_column')
        if analysis_type == 'spending' and not amount_column:
            return JsonResponse({
                'status': 'error',
                'message': 'amount_column is required for spending analysis',
            }, status=400)

        # Get cached session data
        preview_service = DatasetPreviewService(model)
        session_data = preview_service._get_from_cache(session_id)

        if not session_data:
            return JsonResponse({
                'status': 'error',
                'message': f'Session {session_id} not found or expired. Please reload samples.',
            }, status=404)

        # Run the analysis
        analysis_service = CustomerAggregationService(session_data)

        if analysis_type == 'transaction_count':
            result = analysis_service.analyze_transaction_counts(customer_column)
        else:
            result = analysis_service.analyze_customer_spending(customer_column, amount_column)

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.error(f"Error analyzing customer aggregations: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)