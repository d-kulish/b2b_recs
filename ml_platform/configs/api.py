"""
Configs Domain API Endpoints

REST API for Feature Config and Model Config CRUD operations.
"""

import json
import logging

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404

from ml_platform.models import ModelEndpoint, Dataset, FeatureConfig, FeatureConfigVersion, ModelConfig
from .services import (
    SmartDefaultsService,
    TensorDimensionCalculator,
    SemanticTypeService,
    PreprocessingFnGenerator,
    TrainerModuleGenerator,  # Now requires ModelConfig
    serialize_feature_config,
    validate_feature_config,
    validate_python_code,
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def list_feature_configs(request, model_id):
    """
    List all feature configs for a model.

    Query params:
        dataset_id: Filter by dataset (optional)

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

        # Serialize with details for tensor visualization
        data = [serialize_feature_config(fc, include_details=True) for fc in configs]

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
            buyer_model_features=data.get('buyer_model_features', []),
            product_model_features=data.get('product_model_features', []),
            buyer_model_crosses=data.get('buyer_model_crosses', []),
            product_model_crosses=data.get('product_model_crosses', []),
            target_column=data.get('target_column'),  # For ranking models
            created_by=request.user,
        )

        # Calculate and save tensor dimensions
        fc.calculate_tensor_dims()
        fc.save()

        # Generate TFX Transform code (only depends on FeatureConfig)
        transform_valid = True
        try:
            transform_generator = PreprocessingFnGenerator(fc)
            _, transform_valid, transform_error = transform_generator.generate_and_save()
            if not transform_valid:
                logger.warning(f"Transform code validation failed for config {fc.id}: {transform_error}")
        except Exception as gen_error:
            logger.warning(f"Failed to generate transform code for config {fc.id}: {gen_error}")
            transform_valid = False

        # Note: Trainer code is now generated at runtime when ModelConfig is selected
        # Use the /api/modeling/generate-trainer-code/ endpoint with both config IDs

        return JsonResponse({
            'success': True,
            'data': serialize_feature_config(fc, include_details=True),
            'message': 'Feature config created successfully',
            'code_validation': {
                'transform_valid': transform_valid,
            }
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

        # Check if features changed (for versioning and code regeneration)
        # Include target_column for ranking models - changing target affects transform code
        features_changed = (
            data.get('buyer_model_features') != fc.buyer_model_features or
            data.get('product_model_features') != fc.product_model_features or
            data.get('buyer_model_crosses') != fc.buyer_model_crosses or
            data.get('product_model_crosses') != fc.product_model_crosses or
            data.get('target_column') != fc.target_column
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
        if 'buyer_model_features' in data:
            fc.buyer_model_features = data['buyer_model_features']
        if 'product_model_features' in data:
            fc.product_model_features = data['product_model_features']
        if 'buyer_model_crosses' in data:
            fc.buyer_model_crosses = data['buyer_model_crosses']
        if 'product_model_crosses' in data:
            fc.product_model_crosses = data['product_model_crosses']
        if 'target_column' in data:
            fc.target_column = data['target_column']  # For ranking models

        # Recalculate tensor dimensions
        fc.calculate_tensor_dims()
        fc.save()

        # Regenerate TFX Transform code if features changed
        transform_valid = True
        if features_changed:
            try:
                transform_generator = PreprocessingFnGenerator(fc)
                _, transform_valid, transform_error = transform_generator.generate_and_save()
                if not transform_valid:
                    logger.warning(f"Transform code validation failed for config {fc.id}: {transform_error}")
            except Exception as gen_error:
                logger.warning(f"Failed to regenerate transform code for config {fc.id}: {gen_error}")
                transform_valid = False

            # Note: Trainer code is now generated at runtime when ModelConfig is selected

        response = {
            'success': True,
            'data': serialize_feature_config(fc, include_details=True),
            'message': 'Feature config updated successfully',
        }
        if features_changed:
            response['code_validation'] = {
                'transform_valid': transform_valid,
            }
        return JsonResponse(response)

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
            buyer_model_features=source.buyer_model_features,
            product_model_features=source.product_model_features,
            buyer_model_crosses=source.buyer_model_crosses,
            product_model_crosses=source.product_model_crosses,
            target_column=source.target_column,  # Copy target column for ranking configs
            created_by=request.user,
        )

        # Calculate tensor dimensions
        clone.calculate_tensor_dims()
        clone.save()

        # Generate TFX Transform code for clone (only depends on FeatureConfig)
        transform_valid = True
        try:
            transform_generator = PreprocessingFnGenerator(clone)
            _, transform_valid, transform_error = transform_generator.generate_and_save()
            if not transform_valid:
                logger.warning(f"Transform code validation failed for cloned config {clone.id}: {transform_error}")
        except Exception as gen_error:
            logger.warning(f"Failed to generate transform code for cloned config {clone.id}: {gen_error}")
            transform_valid = False

        # Note: Trainer code is now generated at runtime when ModelConfig is selected

        return JsonResponse({
            'success': True,
            'data': serialize_feature_config(clone, include_details=True),
            'message': f'Feature config cloned as "{new_name}"',
            'code_validation': {
                'transform_valid': transform_valid,
            }
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
        column_aliases = dataset.column_aliases or {}

        def get_display_name(col_name, full_key):
            """Get display name from column_aliases, trying multiple key formats."""
            if not column_aliases:
                return col_name
            # Try full key first (e.g., "raw_data.transactions_date")
            if column_aliases.get(full_key):
                return column_aliases[full_key]
            # Try underscore format
            underscore_key = full_key.replace('.', '_')
            if column_aliases.get(underscore_key):
                return column_aliases[underscore_key]
            # Try matching by column name suffix
            for key, alias in column_aliases.items():
                if key.endswith(col_name) or key.endswith(f'.{col_name}') or key.endswith(f'_{col_name}'):
                    return alias
            return col_name

        for table, cols in (dataset.selected_columns or {}).items():
            for col in cols:
                stats_key = f"{table}.{col}"
                stats = (dataset.column_stats or {}).get(stats_key, {})
                col_type = stats.get('type', 'STRING')

                columns.append({
                    'name': col,
                    'table': table,
                    'full_name': stats_key,
                    'type': col_type,
                    'dtype': col_type,  # Alias for compatibility with experiments wizard
                    'display_name': get_display_name(col, stats_key),
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
                'column_aliases': column_aliases,
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
        bq_service = BigQueryService(dataset.model_endpoint, dataset=dataset)

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

        # Get column aliases for display names
        column_aliases = dataset.column_aliases or {}

        def get_display_name(col_name):
            """Get display name from column_aliases, trying multiple key formats."""
            if not column_aliases:
                return col_name
            # Try direct match
            if column_aliases.get(col_name):
                return column_aliases[col_name]
            # Try with table prefix formats (dot and underscore)
            for table in (dataset.selected_columns or {}).keys():
                full_key = f"{table}.{col_name}"
                underscore_key = full_key.replace('.', '_')
                if column_aliases.get(full_key):
                    return column_aliases[full_key]
                if column_aliases.get(underscore_key):
                    return column_aliases[underscore_key]
            # Fallback: search all aliases for keys ending with the column name
            for key, alias in column_aliases.items():
                if key.endswith(col_name) or key.endswith(f'.{col_name}') or key.endswith(f'_{col_name}'):
                    return alias
            return col_name

        # Check which INTEGER columns are missing cardinality and compute on-the-fly
        int_cols_missing_cardinality = []
        for field in schema_fields:
            if field.field_type in ('INT64', 'INTEGER', 'FLOAT64', 'NUMERIC'):
                col_name = field.name
                # Check if cardinality is in any stats source
                has_cardinality = False
                for table in (dataset.selected_columns or {}).keys():
                    stats_key = f"{table.replace('raw_data.', '')}.{col_name}"
                    if stats_key in merged_stats:
                        stats = merged_stats[stats_key]
                        if stats.get('cardinality') or stats.get('unique_count'):
                            has_cardinality = True
                            break
                    if col_name in merged_stats:
                        stats = merged_stats[col_name]
                        if stats.get('cardinality') or stats.get('unique_count'):
                            has_cardinality = True
                            break
                if not has_cardinality:
                    int_cols_missing_cardinality.append(col_name)

        # Compute cardinality for INTEGER columns missing it
        computed_cardinality = {}
        if int_cols_missing_cardinality:
            logger.info(f"Computing cardinality on-the-fly for columns: {int_cols_missing_cardinality}")
            try:
                count_parts = [f"COUNT(DISTINCT `{col}`) AS `{col}`" for col in int_cols_missing_cardinality]
                cardinality_query = f"SELECT {', '.join(count_parts)} FROM ({base_query})"
                cardinality_result = bq_service.client.query(cardinality_query).result()
                cardinality_row = list(cardinality_result)[0]
                for col in int_cols_missing_cardinality:
                    computed_cardinality[col] = getattr(cardinality_row, col, 0) or 0
                logger.info(f"Computed cardinality: {computed_cardinality}")
            except Exception as e:
                logger.warning(f"Failed to compute cardinality on-the-fly: {e}")

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

            # Get cardinality from stats or computed on-the-fly
            cardinality = (
                stats.get('cardinality') or
                stats.get('unique_count') or
                computed_cardinality.get(col_name)
            )

            columns.append({
                'name': col_name,
                'display_name': get_display_name(col_name),
                'bq_type': bq_type,
                'semantic_type': semantic_type,
                'semantic_type_options': semantic_type_options,
                'mapping_role': column_mapping_reverse.get(col_name),
                'stats': {
                    'cardinality': cardinality,
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
                'column_aliases': column_aliases,
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

            # Validate the code
            is_valid = True
            error_msg = None
            error_line = None
            if code:
                is_valid, error_msg, error_line = validate_python_code(code, code_type)

            return JsonResponse({
                'success': True,
                'data': {
                    'code': code or '',
                    'code_type': code_type,
                    'generated_at': fc.generated_at.isoformat() if fc.generated_at else None,
                    'config_id': fc.id,
                    'config_name': fc.name,
                    'has_code': bool(code),
                    'is_valid': is_valid,
                    'validation_error': error_msg,
                    'error_line': error_line,
                },
            })
        elif code_type == 'trainer':
            # Trainer code is now generated at runtime with ModelConfig
            return JsonResponse({
                'success': False,
                'error': 'Trainer code is now generated at runtime with ModelConfig. '
                         'Use POST /api/modeling/generate-trainer-code/ with feature_config_id and model_config_id.',
            }, status=400)
        else:
            return JsonResponse({
                'success': False,
                'error': f'Invalid code type: {code_type}. Use "transform".',
            }, status=400)

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
    Regenerate TFX Transform code for a feature config.

    Request body (optional):
        type: 'transform' (default) - Only transform code is regenerated here

    Note: Trainer code is now generated at runtime via /api/modeling/generate-trainer-code/
    with both feature_config_id and model_config_id.

    Returns:
        JsonResponse with newly generated transform code
    """
    try:
        fc = get_object_or_404(FeatureConfig, id=config_id)

        # Get code type from request body
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}

        code_type = data.get('type', 'transform')

        # Trainer code now requires ModelConfig - redirect to new endpoint
        if code_type in ['trainer', 'all']:
            return JsonResponse({
                'success': False,
                'error': 'Trainer code generation now requires both FeatureConfig and ModelConfig. '
                         'Use POST /api/modeling/generate-trainer-code/ with feature_config_id and model_config_id.',
            }, status=400)

        result = {
            'config_id': fc.id,
            'config_name': fc.name,
            'validation': {},
        }

        # Generate Transform code
        transform_generator = PreprocessingFnGenerator(fc)
        transform_code, transform_valid, transform_error = transform_generator.generate_and_save()
        result['transform_code'] = transform_code
        result['validation']['transform_valid'] = transform_valid
        if not transform_valid:
            result['validation']['transform_error'] = transform_error

        result['generated_at'] = fc.generated_at.isoformat() if fc.generated_at else None

        if transform_valid:
            message = 'Transform code regenerated successfully'
        else:
            message = 'Transform code regenerated with validation errors'

        return JsonResponse({
            'success': True,
            'data': result,
            'message': message,
        })

    except Exception as e:
        logger.exception(f"Error regenerating code for config {config_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def generate_trainer_code(request):
    """
    Generate TFX Trainer code for a FeatureConfig + ModelConfig combination.

    Trainer code requires both configs because:
    - FeatureConfig defines WHAT features are transformed and how
    - ModelConfig defines the neural network architecture, optimizer, hyperparameters

    Request body:
        feature_config_id: int (required)
        model_config_id: int (required)

    Returns:
        JsonResponse with generated trainer code and validation status
    """
    try:
        data = json.loads(request.body)

        feature_config_id = data.get('feature_config_id')
        model_config_id = data.get('model_config_id')

        if not feature_config_id:
            return JsonResponse({
                'success': False,
                'error': 'feature_config_id is required',
            }, status=400)

        if not model_config_id:
            return JsonResponse({
                'success': False,
                'error': 'model_config_id is required',
            }, status=400)

        # Load both configs
        fc = get_object_or_404(FeatureConfig, id=feature_config_id)
        mc = get_object_or_404(ModelConfig, id=model_config_id)

        # Note: ModelConfig is dataset-independent (global) - no dataset validation needed

        # Generate trainer code
        generator = TrainerModuleGenerator(fc, mc)
        trainer_code, is_valid, error_msg, error_line = generator.generate_and_validate()

        result = {
            'feature_config_id': fc.id,
            'feature_config_name': fc.name,
            'model_config_id': mc.id,
            'model_config_name': mc.name,
            'trainer_code': trainer_code,
            'validation': {
                'is_valid': is_valid,
            },
        }

        if not is_valid:
            result['validation']['error'] = error_msg
            result['validation']['error_line'] = error_line

        # Also include transform code from FeatureConfig for convenience
        if fc.generated_transform_code:
            result['transform_code'] = fc.generated_transform_code

        if is_valid:
            message = 'Trainer code generated successfully'
        else:
            message = 'Trainer code generated with validation errors'

        return JsonResponse({
            'success': True,
            'data': result,
            'message': message,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error generating trainer code: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


# =============================================================================
# MODEL CONFIG API ENDPOINTS (Model Structure Domain)
# =============================================================================

def serialize_model_config(mc, include_details=False):
    """
    Serialize a ModelConfig instance to a dictionary.

    Args:
        mc: ModelConfig instance
        include_details: If True, includes full layer configurations

    Returns:
        Dictionary representation of the model config
    """
    data = {
        'id': mc.id,
        'model_endpoint_id': mc.model_endpoint_id,
        'name': mc.name,
        'description': mc.description,
        'model_type': mc.model_type,
        'model_type_display': mc.get_model_type_display(),

        # Tower summaries
        'buyer_tower_summary': mc.get_buyer_tower_summary(),
        'product_tower_summary': mc.get_product_tower_summary(),
        'buyer_layer_count': mc.count_layers('buyer'),
        'product_layer_count': mc.count_layers('product'),
        'output_embedding_dim': mc.output_embedding_dim,
        'share_tower_weights': mc.share_tower_weights,

        # Retrieval algorithm settings
        'retrieval_algorithm': mc.retrieval_algorithm,
        'retrieval_algorithm_display': mc.get_retrieval_algorithm_display(),
        'top_k': mc.top_k,
        'scann_num_leaves': mc.scann_num_leaves,
        'scann_leaves_to_search': mc.scann_leaves_to_search,

        # Training params
        'optimizer': mc.optimizer,
        'optimizer_display': mc.get_optimizer_display(),
        'learning_rate': mc.learning_rate,
        'batch_size': mc.batch_size,
        'epochs': mc.epochs,
        'loss_function': mc.loss_function,
        'loss_function_display': mc.get_loss_function_display(),

        # Multitask params
        'retrieval_weight': mc.retrieval_weight,
        'ranking_weight': mc.ranking_weight,

        # Metadata
        'created_at': mc.created_at.isoformat() if mc.created_at else None,
        'updated_at': mc.updated_at.isoformat() if mc.updated_at else None,
        'created_by': mc.created_by.username if mc.created_by else None,
    }

    # Include full layer details if requested
    if include_details:
        data['buyer_tower_layers'] = mc.buyer_tower_layers
        data['product_tower_layers'] = mc.product_tower_layers
        data['rating_head_layers'] = mc.rating_head_layers
        data['rating_head_summary'] = mc.get_rating_head_summary()
        data['towers_identical'] = mc.towers_are_identical()
        data['estimated_params'] = mc.estimate_params()
        data['validation_errors'] = mc.validate()

    return data


@login_required
@require_http_methods(["GET"])
def list_model_configs(request, model_id):
    """
    List model configs scoped to a project (ModelEndpoint).

    Query params:
        model_type: Filter by model type ('retrieval', 'ranking', 'multitask')

    Returns:
        JsonResponse with list of serialized model configs
    """
    try:
        configs = ModelConfig.objects.filter(
            model_endpoint_id=model_id
        ).select_related('created_by')

        # Apply filters
        model_type = request.GET.get('model_type')
        if model_type:
            configs = configs.filter(model_type=model_type)

        # Check if full layer details requested
        include_details = request.GET.get('include_details', 'false').lower() == 'true'

        # Serialize
        data = [serialize_model_config(mc, include_details=include_details) for mc in configs]

        return JsonResponse({
            'success': True,
            'data': data,
            'count': len(data),
        })

    except Exception as e:
        logger.exception(f"Error listing model configs: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def create_model_config(request, model_id):
    """
    Create a new model config scoped to a project.

    Request body:
        name: str (required)
        description: str (optional)
        model_type: str (default: 'retrieval')
        preset: str (optional) - One of 'minimal', 'standard', 'deep', 'regularized'
        buyer_tower_layers: list (optional - uses preset or default if not provided)
        product_tower_layers: list (optional)
        rating_head_layers: list (optional - for ranking/multitask)
        output_embedding_dim: int (default: 32)
        share_tower_weights: bool (default: False)
        optimizer: str (default: 'adagrad')
        learning_rate: float (default: 0.1)
        batch_size: int (default: 4096)
        epochs: int (default: 5)
        retrieval_weight: float (default: 1.0)
        ranking_weight: float (default: 0.0)

    Returns:
        JsonResponse with created model config
    """
    try:
        data = json.loads(request.body)

        # Validate required fields
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({
                'success': False,
                'error': 'Name is required',
            }, status=400)

        # Check name uniqueness within this project
        if ModelConfig.objects.filter(model_endpoint_id=model_id, name=name).exists():
            return JsonResponse({
                'success': False,
                'error': f'A model config named "{name}" already exists',
            }, status=400)

        # Handle preset
        preset_name = data.get('preset')
        if preset_name:
            preset = ModelConfig.get_preset(preset_name)
            buyer_tower_layers = data.get('buyer_tower_layers', preset.get('buyer_tower_layers', []))
            product_tower_layers = data.get('product_tower_layers', preset.get('product_tower_layers', []))
            output_embedding_dim = data.get('output_embedding_dim', preset.get('output_embedding_dim', 32))
        else:
            # Use provided values or defaults
            default_layers = ModelConfig.get_default_layers()
            buyer_tower_layers = data.get('buyer_tower_layers', default_layers)
            product_tower_layers = data.get('product_tower_layers', default_layers)
            output_embedding_dim = data.get('output_embedding_dim', 32)

        # Get model type
        model_type = data.get('model_type', ModelConfig.MODEL_TYPE_RETRIEVAL)

        # Handle rating head for ranking/multitask
        rating_head_layers = data.get('rating_head_layers', [])
        if model_type in [ModelConfig.MODEL_TYPE_RANKING, ModelConfig.MODEL_TYPE_MULTITASK]:
            if not rating_head_layers:
                rating_head_layers = ModelConfig.get_default_rating_head()

        # Create model config
        mc = ModelConfig.objects.create(
            model_endpoint_id=model_id,
            name=name,
            description=data.get('description', '').strip(),
            model_type=model_type,
            buyer_tower_layers=buyer_tower_layers,
            product_tower_layers=product_tower_layers,
            rating_head_layers=rating_head_layers,
            output_embedding_dim=output_embedding_dim,
            share_tower_weights=data.get('share_tower_weights', False),
            # Retrieval algorithm settings
            retrieval_algorithm=data.get('retrieval_algorithm', ModelConfig.RETRIEVAL_ALGORITHM_BRUTE_FORCE),
            top_k=data.get('top_k', 100),
            scann_num_leaves=data.get('scann_num_leaves', 100),
            scann_leaves_to_search=data.get('scann_leaves_to_search', 10),
            # Training params
            optimizer=data.get('optimizer', ModelConfig.OPTIMIZER_ADAGRAD),
            learning_rate=data.get('learning_rate', 0.1),
            batch_size=data.get('batch_size', 4096),
            epochs=data.get('epochs', 5),
            loss_function=data.get('loss_function', ModelConfig.LOSS_MSE),
            retrieval_weight=data.get('retrieval_weight', 1.0),
            ranking_weight=data.get('ranking_weight', 0.0),
            created_by=request.user,
        )

        # Validate the created config
        validation_errors = mc.validate()

        return JsonResponse({
            'success': True,
            'data': serialize_model_config(mc, include_details=True),
            'message': 'Model config created successfully',
            'validation_errors': validation_errors,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error creating model config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_model_config(request, config_id):
    """
    Get a single model config by ID.

    Returns:
        JsonResponse with model config details
    """
    try:
        mc = get_object_or_404(
            ModelConfig.objects.select_related('created_by'),
            id=config_id
        )

        return JsonResponse({
            'success': True,
            'data': serialize_model_config(mc, include_details=True),
        })

    except Exception as e:
        logger.exception(f"Error getting model config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["PUT"])
def update_model_config(request, config_id):
    """
    Update an existing model config.

    Request body: Same fields as create_model_config (all optional)

    Returns:
        JsonResponse with updated model config
    """
    try:
        mc = get_object_or_404(ModelConfig, id=config_id)
        data = json.loads(request.body)

        # Check name uniqueness within project if changing
        new_name = data.get('name', '').strip()
        if new_name and new_name != mc.name:
            if ModelConfig.objects.filter(
                model_endpoint=mc.model_endpoint, name=new_name
            ).exclude(id=mc.id).exists():
                return JsonResponse({
                    'success': False,
                    'error': f'A model config named "{new_name}" already exists',
                }, status=400)
            mc.name = new_name

        # Update fields
        if 'description' in data:
            mc.description = data['description'].strip()
        if 'model_type' in data:
            mc.model_type = data['model_type']
        if 'buyer_tower_layers' in data:
            mc.buyer_tower_layers = data['buyer_tower_layers']
        if 'product_tower_layers' in data:
            mc.product_tower_layers = data['product_tower_layers']
        if 'rating_head_layers' in data:
            mc.rating_head_layers = data['rating_head_layers']
        if 'output_embedding_dim' in data:
            mc.output_embedding_dim = data['output_embedding_dim']
        if 'share_tower_weights' in data:
            mc.share_tower_weights = data['share_tower_weights']
        # Retrieval algorithm settings
        if 'retrieval_algorithm' in data:
            mc.retrieval_algorithm = data['retrieval_algorithm']
        if 'top_k' in data:
            mc.top_k = data['top_k']
        if 'scann_num_leaves' in data:
            mc.scann_num_leaves = data['scann_num_leaves']
        if 'scann_leaves_to_search' in data:
            mc.scann_leaves_to_search = data['scann_leaves_to_search']

        # Training params
        if 'optimizer' in data:
            mc.optimizer = data['optimizer']
        if 'learning_rate' in data:
            mc.learning_rate = data['learning_rate']
        if 'batch_size' in data:
            mc.batch_size = data['batch_size']
        if 'epochs' in data:
            mc.epochs = data['epochs']
        if 'loss_function' in data:
            mc.loss_function = data['loss_function']
        if 'retrieval_weight' in data:
            mc.retrieval_weight = data['retrieval_weight']
        if 'ranking_weight' in data:
            mc.ranking_weight = data['ranking_weight']

        mc.save()

        # Validate the updated config
        validation_errors = mc.validate()

        return JsonResponse({
            'success': True,
            'data': serialize_model_config(mc, include_details=True),
            'message': 'Model config updated successfully',
            'validation_errors': validation_errors,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error updating model config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["DELETE"])
def delete_model_config(request, config_id):
    """
    Delete a model config.

    Returns:
        JsonResponse with success status
    """
    try:
        mc = get_object_or_404(ModelConfig, id=config_id)
        mc_name = mc.name

        # Note: In future, check if config is used in any QuickTests before deleting
        mc.delete()

        return JsonResponse({
            'success': True,
            'message': f'Model config "{mc_name}" deleted successfully',
        })

    except Exception as e:
        logger.exception(f"Error deleting model config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def clone_model_config(request, model_id, config_id):
    """
    Clone a model config into the specified project.

    Request body:
        name: str (optional) - Name for the cloned config

    Returns:
        JsonResponse with cloned model config
    """
    try:
        source = get_object_or_404(ModelConfig, id=config_id)
        data = json.loads(request.body) if request.body else {}

        new_name = data.get('name', '').strip()
        if not new_name:
            new_name = f"{source.name} (Copy)"

        # Check name uniqueness within target project
        if ModelConfig.objects.filter(model_endpoint_id=model_id, name=new_name).exists():
            # Auto-suffix with number
            counter = 2
            base_name = new_name
            while ModelConfig.objects.filter(model_endpoint_id=model_id, name=new_name).exists():
                new_name = f"{base_name} {counter}"
                counter += 1

        # Create clone
        clone = ModelConfig.objects.create(
            model_endpoint_id=model_id,
            name=new_name,
            description=data.get('description', source.description),
            model_type=source.model_type,
            buyer_tower_layers=source.buyer_tower_layers.copy() if source.buyer_tower_layers else [],
            product_tower_layers=source.product_tower_layers.copy() if source.product_tower_layers else [],
            rating_head_layers=source.rating_head_layers.copy() if source.rating_head_layers else [],
            output_embedding_dim=source.output_embedding_dim,
            share_tower_weights=source.share_tower_weights,
            # Retrieval algorithm settings
            retrieval_algorithm=source.retrieval_algorithm,
            top_k=source.top_k,
            scann_num_leaves=source.scann_num_leaves,
            scann_leaves_to_search=source.scann_leaves_to_search,
            # Training params
            optimizer=source.optimizer,
            learning_rate=source.learning_rate,
            batch_size=source.batch_size,
            epochs=source.epochs,
            loss_function=source.loss_function,
            retrieval_weight=source.retrieval_weight,
            ranking_weight=source.ranking_weight,
            created_by=request.user,
        )

        return JsonResponse({
            'success': True,
            'data': serialize_model_config(clone, include_details=True),
            'message': f'Model config cloned as "{new_name}"',
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error cloning model config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_model_config_presets(request):
    """
    Get all available model config presets.

    Returns:
        JsonResponse with preset configurations
    """
    try:
        presets = ModelConfig.get_all_presets()

        return JsonResponse({
            'success': True,
            'data': presets,
        })

    except Exception as e:
        logger.exception(f"Error getting model config presets: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_model_config_preset(request, preset_name):
    """
    Get a specific model config preset by name.

    Returns:
        JsonResponse with preset configuration
    """
    try:
        preset = ModelConfig.get_preset(preset_name)

        if preset_name not in ['minimal', 'standard', 'deep', 'regularized']:
            return JsonResponse({
                'success': False,
                'error': f'Unknown preset: {preset_name}',
            }, status=404)

        return JsonResponse({
            'success': True,
            'data': preset,
        })

    except Exception as e:
        logger.exception(f"Error getting model config preset: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_rating_head_presets(request):
    """
    Get all available rating head presets for ranking models.

    Returns:
        JsonResponse with rating head preset configurations
    """
    try:
        presets = ModelConfig.get_all_rating_head_presets()

        return JsonResponse({
            'success': True,
            'data': presets,
        })

    except Exception as e:
        logger.exception(f"Error getting rating head presets: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_loss_function_info(request):
    """
    Get information about available loss functions for ranking models.

    Returns:
        JsonResponse with loss function descriptions and use cases
    """
    try:
        loss_info = ModelConfig.get_loss_function_info()

        return JsonResponse({
            'success': True,
            'data': loss_info,
        })

    except Exception as e:
        logger.exception(f"Error getting loss function info: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def validate_model_config(request):
    """
    Validate a model config without saving it.

    Request body: Same fields as create_model_config

    Returns:
        JsonResponse with validation result
    """
    try:
        data = json.loads(request.body)

        # Create temporary instance for validation
        mc = ModelConfig(
            name=data.get('name', 'temp'),
            model_type=data.get('model_type', ModelConfig.MODEL_TYPE_RETRIEVAL),
            buyer_tower_layers=data.get('buyer_tower_layers', []),
            product_tower_layers=data.get('product_tower_layers', []),
            rating_head_layers=data.get('rating_head_layers', []),
            output_embedding_dim=data.get('output_embedding_dim', 32),
            share_tower_weights=data.get('share_tower_weights', False),
            retrieval_weight=data.get('retrieval_weight', 1.0),
            ranking_weight=data.get('ranking_weight', 0.0),
        )

        errors = mc.validate()
        is_valid = len(errors) == 0

        return JsonResponse({
            'success': True,
            'data': {
                'is_valid': is_valid,
                'errors': errors,
                'buyer_tower_summary': mc.get_buyer_tower_summary(),
                'product_tower_summary': mc.get_product_tower_summary(),
                'towers_identical': mc.towers_are_identical(),
                'estimated_params': mc.estimate_params(
                    buyer_input_dim=data.get('buyer_input_dim'),
                    product_input_dim=data.get('product_input_dim'),
                ),
            },
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body',
        }, status=400)
    except Exception as e:
        logger.exception(f"Error validating model config: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def check_model_config_name(request, model_id):
    """
    Check if a model config name is available within a project.

    Query params:
        name: str (required) - The name to check
        exclude_id: int (optional) - Config ID to exclude (for edit mode)

    Returns:
        JsonResponse with availability status
    """
    try:
        name = request.GET.get('name', '').strip()

        if not name:
            return JsonResponse({
                'success': False,
                'error': 'Name is required',
            }, status=400)

        # Check if name exists within this project
        existing = ModelConfig.objects.filter(model_endpoint_id=model_id, name=name)

        # Exclude current config if editing
        exclude_id = request.GET.get('exclude_id')
        if exclude_id:
            try:
                existing = existing.exclude(id=int(exclude_id))
            except ValueError:
                pass

        is_available = not existing.exists()

        return JsonResponse({
            'success': True,
            'data': {
                'name': name,
                'available': is_available,
                'message': None if is_available else f'A model config named "{name}" already exists',
            },
        })

    except Exception as e:
        logger.exception(f"Error checking model config name: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def check_feature_config_name(request):
    """
    Check if a feature config name is available for a given dataset.

    Query params:
        name: str (required) - The name to check
        dataset_id: int (required) - The dataset ID
        exclude_id: int (optional) - Config ID to exclude (for edit mode)

    Returns:
        JsonResponse with availability status
    """
    try:
        name = request.GET.get('name', '').strip()
        dataset_id = request.GET.get('dataset_id')

        if not name:
            return JsonResponse({
                'success': False,
                'error': 'Name is required',
            }, status=400)

        if not dataset_id:
            return JsonResponse({
                'success': False,
                'error': 'dataset_id is required',
            }, status=400)

        # Check if name exists for this dataset
        existing = FeatureConfig.objects.filter(
            dataset_id=int(dataset_id),
            name=name
        )

        # Exclude current config if editing
        exclude_id = request.GET.get('exclude_id')
        if exclude_id:
            try:
                existing = existing.exclude(id=int(exclude_id))
            except ValueError:
                pass

        is_available = not existing.exists()

        return JsonResponse({
            'success': True,
            'data': {
                'name': name,
                'available': is_available,
                'message': None if is_available else f'A feature config named "{name}" already exists for this dataset',
            },
        })

    except Exception as e:
        logger.exception(f"Error checking feature config name: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


# =============================================================================
# CONFIGS DASHBOARD STATS
# =============================================================================

@login_required
@require_http_methods(["GET"])
def get_configs_dashboard_stats(request, model_id):
    """
    Get dashboard statistics for the Configs page.

    Returns inventory tracking, usage analytics, and relationship data
    for Datasets, FeatureConfigs, and ModelConfigs.
    """
    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)

        from .services import ConfigDashboardStatsService
        service = ConfigDashboardStatsService(model)

        return JsonResponse({
            'success': True,
            'data': service.get_stats(),
        })

    except Exception as e:
        logger.exception(f"Error getting configs dashboard stats: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)
