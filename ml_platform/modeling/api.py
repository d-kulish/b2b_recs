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
    SemanticTypeService,
    PreprocessingFnGenerator,
    TrainerModuleGenerator,
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

        # Generate TFX Transform code
        try:
            transform_generator = PreprocessingFnGenerator(fc)
            transform_generator.generate_and_save()
        except Exception as gen_error:
            logger.warning(f"Failed to generate transform code for config {fc.id}: {gen_error}")
            # Don't fail the request if code generation fails

        # Generate TFX Trainer code
        try:
            trainer_generator = TrainerModuleGenerator(fc)
            trainer_generator.generate_and_save()
        except Exception as gen_error:
            logger.warning(f"Failed to generate trainer code for config {fc.id}: {gen_error}")
            # Don't fail the request if code generation fails

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

        # Regenerate TFX code if features changed
        if features_changed:
            try:
                transform_generator = PreprocessingFnGenerator(fc)
                transform_generator.generate_and_save()
            except Exception as gen_error:
                logger.warning(f"Failed to regenerate transform code for config {fc.id}: {gen_error}")

            try:
                trainer_generator = TrainerModuleGenerator(fc)
                trainer_generator.generate_and_save()
            except Exception as gen_error:
                logger.warning(f"Failed to regenerate trainer code for config {fc.id}: {gen_error}")

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

        # Generate TFX code for clone
        try:
            transform_generator = PreprocessingFnGenerator(clone)
            transform_generator.generate_and_save()
        except Exception as gen_error:
            logger.warning(f"Failed to generate transform code for cloned config {clone.id}: {gen_error}")

        try:
            trainer_generator = TrainerModuleGenerator(clone)
            trainer_generator.generate_and_save()
        except Exception as gen_error:
            logger.warning(f"Failed to generate trainer code for cloned config {clone.id}: {gen_error}")

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

        data = []
        for ds in datasets:
            # Get total_rows from summary_snapshot
            summary = ds.summary_snapshot or {}
            total_rows = summary.get('total_rows')

            # Count columns from selected_columns
            column_count = 0
            if ds.selected_columns:
                for table_cols in ds.selected_columns.values():
                    if isinstance(table_cols, list):
                        column_count += len(table_cols)

            data.append({
                'id': ds.id,
                'name': ds.name,
                'description': ds.description,
                'primary_table': ds.primary_table,
                'total_rows': total_rows,
                'column_count': column_count,
                'updated_at': ds.updated_at.isoformat() if ds.updated_at else None,
                'feature_configs_count': ds.feature_configs.count(),
            })

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


@login_required
@require_http_methods(["GET"])
def get_schema_with_sample(request, dataset_id):
    """
    Get column schema with accurate types from BigQuery and sample data.

    This endpoint executes the dataset query with LIMIT to get:
    1. Accurate column types from BigQuery result schema
    2. Sample data rows for preview
    3. Inferred semantic types for feature engineering

    Returns:
        JsonResponse with columns, sample_rows, and column_order
    """
    try:
        from ml_platform.datasets.services import BigQueryService

        dataset = get_object_or_404(Dataset, id=dataset_id)
        bq_service = BigQueryService(dataset.model_endpoint)

        # Generate the dataset query
        base_query = bq_service.generate_query(dataset)

        # Execute with LIMIT to get schema + sample
        sample_query = f"SELECT * FROM ({base_query}) LIMIT 10"

        logger.info(f"Executing schema sample query for dataset {dataset_id}")
        result = bq_service.client.query(sample_query).result()

        # Extract schema from result
        schema_fields = list(result.schema)

        # Build column order from schema
        column_order = [field.name for field in schema_fields]

        # Convert rows to list of dicts
        sample_rows = []
        for row in result:
            row_dict = {}
            for field in schema_fields:
                val = getattr(row, field.name, None)
                # Handle special types for JSON serialization
                if val is None:
                    row_dict[field.name] = None
                elif hasattr(val, 'isoformat'):
                    row_dict[field.name] = val.isoformat()
                elif isinstance(val, bytes):
                    row_dict[field.name] = val.decode('utf-8', errors='replace')
                else:
                    row_dict[field.name] = val
            sample_rows.append(row_dict)

        # Get existing stats from dataset for enrichment
        existing_stats = dataset.column_stats or {}
        summary_stats = (dataset.summary_snapshot or {}).get('column_stats', {})

        # Merge stats sources
        merged_stats = {**summary_stats, **existing_stats}

        # Get column mapping for role detection
        column_mapping_reverse = {v: k for k, v in (dataset.column_mapping or {}).items()}

        # Build columns with semantic types
        columns = []
        for field in schema_fields:
            col_name = field.name
            bq_type = field.field_type

            # Try to find stats - could be under different keys
            stats = {}
            for table in (dataset.selected_columns or {}).keys():
                stats_key = f"{table.replace('raw_data.', '')}.{col_name}"
                if stats_key in merged_stats:
                    stats = merged_stats[stats_key]
                    break
                # Also try without table prefix
                if col_name in merged_stats:
                    stats = merged_stats[col_name]
                    break

            # Extract sample values for this column
            sample_values = [row.get(col_name) for row in sample_rows if row.get(col_name) is not None]

            # Add total_rows to stats for cardinality ratio calculation
            if sample_rows:
                stats['total_rows'] = len(sample_rows)

            # Infer semantic type
            semantic_type = SemanticTypeService.infer_semantic_type(
                col_name=col_name,
                bq_type=bq_type,
                stats=stats,
                sample_values=sample_values
            )

            # Get available options for this BigQuery type
            semantic_type_options = SemanticTypeService.get_type_options(bq_type)

            columns.append({
                'name': col_name,
                'bq_type': bq_type,
                'semantic_type': semantic_type,
                'semantic_type_options': semantic_type_options,
                'mapping_role': column_mapping_reverse.get(col_name),
                'stats': {
                    'cardinality': stats.get('cardinality') or stats.get('unique_count'),
                    'null_percent': stats.get('null_percent'),
                    'min': stats.get('min'),
                    'max': stats.get('max'),
                    'avg': stats.get('avg'),
                },
            })

        return JsonResponse({
            'success': True,
            'data': {
                'columns': columns,
                'sample_rows': sample_rows,
                'column_order': column_order,
                'row_count': len(sample_rows),
            },
        })

    except Exception as e:
        logger.exception(f"Error getting schema with sample for dataset {dataset_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_generated_code(request, config_id):
    """
    Get generated TFX code for a feature config.

    Query params:
        type: 'transform' | 'trainer' (default: 'transform')

    Returns:
        JsonResponse with generated code and metadata
    """
    try:
        fc = get_object_or_404(FeatureConfig, id=config_id)
        code_type = request.GET.get('type', 'transform')

        if code_type == 'transform':
            code = fc.generated_transform_code
        elif code_type == 'trainer':
            code = fc.generated_trainer_code
        else:
            return JsonResponse({
                'success': False,
                'error': f'Invalid code type: {code_type}. Use "transform" or "trainer".',
            }, status=400)

        return JsonResponse({
            'success': True,
            'data': {
                'code': code or '',
                'code_type': code_type,
                'generated_at': fc.generated_at.isoformat() if fc.generated_at else None,
                'config_id': fc.id,
                'config_name': fc.name,
                'has_code': bool(code),
            },
        })

    except Exception as e:
        logger.exception(f"Error getting generated code for config {config_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def regenerate_code(request, config_id):
    """
    Regenerate TFX code for a feature config.

    Request body (optional):
        type: 'transform' | 'trainer' | 'all' (default: 'all')

    Useful if code generation failed or config was created before
    the generator was implemented.

    Returns:
        JsonResponse with newly generated code
    """
    try:
        fc = get_object_or_404(FeatureConfig, id=config_id)

        # Get code type from request body
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}

        code_type = data.get('type', 'all')

        result = {
            'config_id': fc.id,
            'config_name': fc.name,
        }

        # Generate Transform code
        if code_type in ['transform', 'all']:
            transform_generator = PreprocessingFnGenerator(fc)
            transform_code = transform_generator.generate_and_save()
            result['transform_code'] = transform_code

        # Generate Trainer code
        if code_type in ['trainer', 'all']:
            trainer_generator = TrainerModuleGenerator(fc)
            trainer_code = trainer_generator.generate_and_save()
            result['trainer_code'] = trainer_code

        result['generated_at'] = fc.generated_at.isoformat() if fc.generated_at else None

        return JsonResponse({
            'success': True,
            'data': result,
            'message': f'{code_type.capitalize()} code regenerated successfully',
        })

    except Exception as e:
        logger.exception(f"Error regenerating code for config {config_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)
