"""
Modeling Domain API Endpoints

REST API for Feature Config CRUD operations.
"""

import json
import logging

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404

from ml_platform.models import ModelEndpoint, Dataset, FeatureConfig, FeatureConfigVersion
from .services import (
    SmartDefaultsService,
    TensorDimensionCalculator,
    serialize_feature_config,
    validate_feature_config,
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def list_feature_configs(request, model_id):
    """
    List all feature configs for a model.

    Query params:
        dataset_id: Filter by dataset (optional)
        status: Filter by status (optional)

    Returns:
        JsonResponse with list of serialized feature configs
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)

        # Start with all feature configs for datasets belonging to this model
        configs = FeatureConfig.objects.filter(
            dataset__model_endpoint=model
        ).select_related('dataset', 'created_by')

        # Apply filters
        dataset_id = request.GET.get('dataset_id')
        if dataset_id:
            configs = configs.filter(dataset_id=dataset_id)

        status = request.GET.get('status')
        if status:
            configs = configs.filter(status=status)

        # Serialize
        data = [serialize_feature_config(fc) for fc in configs]

        return JsonResponse({
            'success': True,
            'data': data,
            'count': len(data),
        })

    except Exception as e:
        logger.exception(f"Error listing feature configs: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def create_feature_config(request, model_id):
    """
    Create a new feature config.

    Request body:
        name: str (required)
        description: str (optional)
        dataset_id: int (required)
        start_from: 'blank' | 'smart_defaults' | 'clone' (optional, default 'blank')
        clone_from_id: int (required if start_from='clone')
        buyer_model_features: list (optional)
        product_model_features: list (optional)
        buyer_model_crosses: list (optional)
        product_model_crosses: list (optional)

    Returns:
        JsonResponse with created feature config
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Get dataset
        dataset_id = data.get('dataset_id')
        if not dataset_id:
            return JsonResponse({
                'success': False,
                'error': 'dataset_id is required',
            }, status=400)

        dataset = get_object_or_404(Dataset, id=dataset_id, model_endpoint=model)

        # Handle start_from options
        start_from = data.get('start_from', 'blank')

        if start_from == 'smart_defaults':
            # Generate smart defaults
            smart_service = SmartDefaultsService(dataset)
            defaults = smart_service.generate()
            data['buyer_model_features'] = defaults['buyer_model_features']
            data['product_model_features'] = defaults['product_model_features']
            data['buyer_model_crosses'] = defaults['buyer_model_crosses']
            data['product_model_crosses'] = defaults['product_model_crosses']

        elif start_from == 'clone':
            # Clone from existing config
            clone_from_id = data.get('clone_from_id')
            if not clone_from_id:
                return JsonResponse({
                    'success': False,
                    'error': 'clone_from_id is required when start_from is clone',
                }, status=400)

            clone_from = get_object_or_404(FeatureConfig, id=clone_from_id)
            data['buyer_model_features'] = clone_from.buyer_model_features
            data['product_model_features'] = clone_from.product_model_features
            data['buyer_model_crosses'] = clone_from.buyer_model_crosses
            data['product_model_crosses'] = clone_from.product_model_crosses

        # Validate
        is_valid, errors = validate_feature_config(data, dataset)
        if not is_valid:
            return JsonResponse({
                'success': False,
                'errors': errors,
            }, status=400)

        # Create feature config
        fc = FeatureConfig.objects.create(
            name=data['name'].strip(),
            description=data.get('description', '').strip(),
            dataset=dataset,
            status='draft',
            buyer_model_features=data.get('buyer_model_features', []),
            product_model_features=data.get('product_model_features', []),
            buyer_model_crosses=data.get('buyer_model_crosses', []),
            product_model_crosses=data.get('product_model_crosses', []),
            created_by=request.user,
        )

        # Calculate and save tensor dimensions
        fc.calculate_tensor_dims()
        fc.save()

        return JsonResponse({
            'success': True,
            'data': serialize_feature_config(fc, include_details=True),
            'message': 'Feature config created successfully',
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error creating feature config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_feature_config(request, config_id):
    """
    Get a single feature config by ID.

    Returns:
        JsonResponse with feature config details
    """
    try:
        fc = get_object_or_404(
            FeatureConfig.objects.select_related('dataset', 'created_by'),
            id=config_id
        )

        return JsonResponse({
            'success': True,
            'data': serialize_feature_config(fc, include_details=True),
        })

    except Exception as e:
        logger.exception(f"Error getting feature config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["PUT"])
def update_feature_config(request, config_id):
    """
    Update an existing feature config.

    Request body:
        name: str (optional)
        description: str (optional)
        status: str (optional)
        buyer_model_features: list (optional)
        product_model_features: list (optional)
        buyer_model_crosses: list (optional)
        product_model_crosses: list (optional)

    Returns:
        JsonResponse with updated feature config
    """
    try:
        fc = get_object_or_404(FeatureConfig, id=config_id)
        data = json.loads(request.body)

        # Validate
        is_valid, errors = validate_feature_config(data, fc.dataset, exclude_config_id=fc.id)
        if not is_valid:
            return JsonResponse({
                'success': False,
                'errors': errors,
            }, status=400)

        # Check if features changed (for versioning)
        features_changed = (
            data.get('buyer_model_features') != fc.buyer_model_features or
            data.get('product_model_features') != fc.product_model_features or
            data.get('buyer_model_crosses') != fc.buyer_model_crosses or
            data.get('product_model_crosses') != fc.product_model_crosses
        )

        # Create version snapshot if features changed
        if features_changed and fc.buyer_tensor_dim is not None:
            FeatureConfigVersion.objects.create(
                feature_config=fc,
                version=fc.version,
                buyer_model_features=fc.buyer_model_features,
                product_model_features=fc.product_model_features,
                buyer_model_crosses=fc.buyer_model_crosses,
                product_model_crosses=fc.product_model_crosses,
                buyer_tensor_dim=fc.buyer_tensor_dim or 0,
                product_tensor_dim=fc.product_tensor_dim or 0,
                created_by=request.user,
            )
            fc.version += 1

        # Update fields
        if 'name' in data:
            fc.name = data['name'].strip()
        if 'description' in data:
            fc.description = data['description'].strip()
        if 'status' in data:
            fc.status = data['status']
        if 'buyer_model_features' in data:
            fc.buyer_model_features = data['buyer_model_features']
        if 'product_model_features' in data:
            fc.product_model_features = data['product_model_features']
        if 'buyer_model_crosses' in data:
            fc.buyer_model_crosses = data['buyer_model_crosses']
        if 'product_model_crosses' in data:
            fc.product_model_crosses = data['product_model_crosses']

        # Recalculate tensor dimensions
        fc.calculate_tensor_dims()
        fc.save()

        return JsonResponse({
            'success': True,
            'data': serialize_feature_config(fc, include_details=True),
            'message': 'Feature config updated successfully',
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error updating feature config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["DELETE"])
def delete_feature_config(request, config_id):
    """
    Delete a feature config.

    Returns:
        JsonResponse with success status
    """
    try:
        fc = get_object_or_404(FeatureConfig, id=config_id)
        fc_name = fc.name

        # Delete the config (versions will cascade delete)
        fc.delete()

        return JsonResponse({
            'success': True,
            'message': f'Feature config "{fc_name}" deleted successfully',
        })

    except Exception as e:
        logger.exception(f"Error deleting feature config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def clone_feature_config(request, config_id):
    """
    Clone a feature config.

    Request body:
        name: str (required) - Name for the cloned config

    Returns:
        JsonResponse with cloned feature config
    """
    try:
        source = get_object_or_404(FeatureConfig, id=config_id)
        data = json.loads(request.body)

        new_name = data.get('name', '').strip()
        if not new_name:
            new_name = f"{source.name} (Copy)"

        # Check name uniqueness
        if FeatureConfig.objects.filter(dataset=source.dataset, name=new_name).exists():
            return JsonResponse({
                'success': False,
                'error': f'A feature config named "{new_name}" already exists',
            }, status=400)

        # Create clone
        clone = FeatureConfig.objects.create(
            name=new_name,
            description=data.get('description', source.description),
            dataset=source.dataset,
            status='draft',
            buyer_model_features=source.buyer_model_features,
            product_model_features=source.product_model_features,
            buyer_model_crosses=source.buyer_model_crosses,
            product_model_crosses=source.product_model_crosses,
            created_by=request.user,
        )

        # Calculate tensor dimensions
        clone.calculate_tensor_dims()
        clone.save()

        return JsonResponse({
            'success': True,
            'data': serialize_feature_config(clone, include_details=True),
            'message': f'Feature config cloned as "{new_name}"',
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error cloning feature config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def generate_smart_defaults(request):
    """
    Generate smart default feature configuration for a dataset.

    Request body:
        dataset_id: int (required)

    Returns:
        JsonResponse with generated feature configurations
    """
    try:
        data = json.loads(request.body)
        dataset_id = data.get('dataset_id')

        if not dataset_id:
            return JsonResponse({
                'success': False,
                'error': 'dataset_id is required',
            }, status=400)

        dataset = get_object_or_404(Dataset, id=dataset_id)

        # Generate smart defaults
        smart_service = SmartDefaultsService(dataset)
        defaults = smart_service.generate()

        # Calculate dimensions for preview
        calc = TensorDimensionCalculator()
        buyer_dims = calc.calculate(
            defaults['buyer_model_features'],
            defaults['buyer_model_crosses']
        )
        product_dims = calc.calculate(
            defaults['product_model_features'],
            defaults['product_model_crosses']
        )

        return JsonResponse({
            'success': True,
            'data': {
                **defaults,
                'buyer_tensor_dim': buyer_dims['total'],
                'buyer_tensor_breakdown': buyer_dims['breakdown'],
                'product_tensor_dim': product_dims['total'],
                'product_tensor_breakdown': product_dims['breakdown'],
            },
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error generating smart defaults: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def calculate_dimensions(request):
    """
    Calculate tensor dimensions for a feature configuration.

    Request body:
        buyer_model_features: list
        product_model_features: list
        buyer_model_crosses: list
        product_model_crosses: list

    Returns:
        JsonResponse with calculated dimensions
    """
    try:
        data = json.loads(request.body)

        calc = TensorDimensionCalculator()

        buyer_dims = calc.calculate(
            data.get('buyer_model_features', []),
            data.get('buyer_model_crosses', [])
        )
        product_dims = calc.calculate(
            data.get('product_model_features', []),
            data.get('product_model_crosses', [])
        )

        return JsonResponse({
            'success': True,
            'data': {
                'buyer_tensor_dim': buyer_dims['total'],
                'buyer_tensor_breakdown': buyer_dims['breakdown'],
                'product_tensor_dim': product_dims['total'],
                'product_tensor_breakdown': product_dims['breakdown'],
            },
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error calculating dimensions: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_versions(request, config_id):
    """
    List all versions for a feature config.

    Returns:
        JsonResponse with list of versions
    """
    try:
        fc = get_object_or_404(FeatureConfig, id=config_id)

        versions = FeatureConfigVersion.objects.filter(
            feature_config=fc
        ).select_related('created_by').order_by('-version')

        data = [{
            'id': v.id,
            'version': v.version,
            'buyer_tensor_dim': v.buyer_tensor_dim,
            'product_tensor_dim': v.product_tensor_dim,
            'created_at': v.created_at.isoformat(),
            'created_by': v.created_by.username if v.created_by else None,
        } for v in versions]

        return JsonResponse({
            'success': True,
            'data': data,
            'count': len(data),
        })

    except Exception as e:
        logger.exception(f"Error listing versions: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_datasets_for_model(request, model_id):
    """
    List all datasets for a model (for dropdown selection).

    Returns:
        JsonResponse with list of datasets
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)

        datasets = Dataset.objects.filter(
            model_endpoint=model
        ).order_by('-updated_at')

        data = [{
            'id': ds.id,
            'name': ds.name,
            'description': ds.description,
            'primary_table': ds.primary_table,
            'row_count_estimate': ds.row_count_estimate,
            'unique_users_estimate': ds.unique_users_estimate,
            'unique_products_estimate': ds.unique_products_estimate,
            'updated_at': ds.updated_at.isoformat() if ds.updated_at else None,
            'feature_configs_count': ds.feature_configs.count(),
        } for ds in datasets]

        return JsonResponse({
            'success': True,
            'data': data,
            'count': len(data),
        })

    except Exception as e:
        logger.exception(f"Error listing datasets: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_dataset_columns(request, dataset_id):
    """
    Get column information for a dataset (for feature assignment).

    Returns:
        JsonResponse with columns and their statistics
    """
    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)

        columns = []
        column_mapping_reverse = {v: k for k, v in (dataset.column_mapping or {}).items()}

        for table, cols in (dataset.selected_columns or {}).items():
            for col in cols:
                stats_key = f"{table}.{col}"
                stats = (dataset.column_stats or {}).get(stats_key, {})

                columns.append({
                    'name': col,
                    'table': table,
                    'full_name': stats_key,
                    'type': stats.get('type', 'STRING'),
                    'mapping_role': column_mapping_reverse.get(col),
                    'stats': {
                        'cardinality': stats.get('cardinality', stats.get('unique_count')),
                        'null_percent': stats.get('null_percent'),
                        'min': stats.get('min'),
                        'max': stats.get('max'),
                        'mean': stats.get('mean'),
                    },
                })

        return JsonResponse({
            'success': True,
            'data': {
                'columns': columns,
                'column_mapping': dataset.column_mapping,
            },
        })

    except Exception as e:
        logger.exception(f"Error getting dataset columns: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)
