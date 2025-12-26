"""
Connections REST API Endpoints

Handles all connection management operations (JSON responses).
This module contains all connection CRUD, testing, schema fetching, and file listing APIs.
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
import json
import os
import logging

from ml_platform.models import (
    ModelEndpoint,
    Connection,
    DataSource,
)

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def test_wizard(request, model_id):
    """
    Test connection in wizard and check for duplicates.
    Returns existing connection if duplicate found, or creates new one.
    """
    from ml_platform.utils.connection_manager import test_and_fetch_metadata, save_connection_credentials
    from ml_platform.models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Extract connection parameters
        source_type = data.get('source_type')
        host = data.get('host', '')
        port = data.get('port')
        database = data.get('database', '')
        username = data.get('username', '')
        password = data.get('password', '')

        # Prepare connection params for testing
        connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'username': username,
            'password': password,
            'project_id': data.get('project_id', ''),
            'dataset': data.get('dataset', ''),
            'service_account_json': data.get('service_account_json', ''),
            'connection_string': data.get('connection_string', ''),
            # Cloud Storage parameters
            'bucket_path': data.get('bucket_path', ''),
            'aws_access_key_id': data.get('aws_access_key_id', ''),
            'aws_secret_access_key': data.get('aws_secret_access_key', ''),
            'aws_region': data.get('aws_region', ''),
            'azure_storage_account': data.get('azure_storage_account', ''),
            'azure_account_key': data.get('azure_account_key', ''),
            'azure_sas_token': data.get('azure_sas_token', ''),
        }

        # Test the connection
        test_result = test_and_fetch_metadata(source_type, connection_params)

        if not test_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': test_result['message'],
            }, status=400)

        # Connection test successful - check for duplicates
        existing_connection = Connection.objects.filter(
            model_endpoint=model,
            source_type=source_type,
            source_host=host,
            source_port=port,
            source_database=database,
            source_username=username
        ).first()

        if existing_connection:
            # Duplicate found - return existing connection
            return JsonResponse({
                'status': 'success',
                'duplicate': True,
                'connection_id': existing_connection.id,
                'connection_name': existing_connection.name,
                'message': test_result['message'],
                'tables': test_result['tables'],
            })
        else:
            # No duplicate - suggest auto-name and prepare to create
            source_type_display = dict(Connection.SOURCE_TYPE_CHOICES).get(source_type, source_type)
            suggested_name = f"{source_type_display} - {database}" if database else source_type_display

            return JsonResponse({
                'status': 'success',
                'duplicate': False,
                'suggested_name': suggested_name,
                'message': test_result['message'],
                'tables': test_result['tables'],
                # Store connection data for later creation
                'connection_data': {
                    'source_type': source_type,
                    'host': host,
                    'port': port,
                    'database': database,
                    'username': username,
                    'schema': data.get('schema', ''),
                }
            })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def create(request, model_id):
    """
    UNIFIED Connection Creation API - Source-Type Aware
    Handles ALL source types: Databases, Cloud Storage, NoSQL
    Replaces both old wizard and standalone APIs.
    """
    from ml_platform.utils.connection_manager import test_and_fetch_metadata, save_connection_credentials
    from ml_platform.models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        data = json.loads(request.body)

        # Extract connection details
        connection_name = data.get('name', 'Untitled Connection')
        source_type = data.get('source_type')
        test_first = data.get('test_first', False)  # Standalone mode tests first

        # Get connection params (can be nested or flat depending on caller)
        connection_params = data.get('connection_params', {})
        if not connection_params:
            # Flat structure - extract from data directly
            connection_params = data

        print(f"=== UNIFIED CONNECTION CREATE ===")
        print(f"Connection name: '{connection_name}'")
        print(f"Source type: {source_type}")
        print(f"Test first: {test_first}")

        # Check for duplicate connection name
        if Connection.objects.filter(model_endpoint=model, name=connection_name).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'A connection named "{connection_name}" already exists. Please choose a different name.',
            }, status=400)

        # Define source type categories
        DB_TYPES = {'postgresql', 'mysql', 'oracle', 'sqlserver', 'db2', 'redshift', 'synapse', 'bigquery', 'snowflake', 'mariadb', 'teradata'}
        STORAGE_TYPES = {'gcs', 's3', 'azure_blob'}
        NOSQL_TYPES = {'mongodb', 'firestore', 'cassandra', 'dynamodb', 'redis'}

        # === SOURCE-TYPE AWARE FIELD EXTRACTION ===
        connection_data = {
            'model_endpoint': model,
            'name': connection_name,
            'source_type': source_type,
            'description': data.get('description', ''),
            'is_enabled': True,
        }
        credentials_dict = {}

        # Extract fields based on source type
        if source_type in DB_TYPES:
            # === RELATIONAL DATABASES ===
            connection_data.update({
                'source_host': connection_params.get('host', ''),
                'source_port': connection_params.get('port'),
                'source_database': connection_params.get('database', ''),
                'source_schema': connection_params.get('schema', ''),
                'source_username': connection_params.get('username', ''),
            })
            credentials_dict.update({
                'host': connection_params.get('host', ''),
                'port': connection_params.get('port'),
                'database': connection_params.get('database', ''),
                'schema': connection_params.get('schema', ''),
                'username': connection_params.get('username', ''),
                'password': connection_params.get('password', ''),
            })

            if source_type == 'bigquery':
                connection_data['bigquery_project'] = connection_params.get('project_id', '')
                connection_data['bigquery_dataset'] = connection_params.get('dataset', '')
                credentials_dict['project_id'] = connection_params.get('project_id', '')
                credentials_dict['dataset'] = connection_params.get('dataset', '')
                credentials_dict['service_account_json'] = connection_params.get('service_account_json', '')

        elif source_type == 'gcs':
            # === GOOGLE CLOUD STORAGE ===
            bucket_path = connection_params.get('bucket_path', '')
            # Extract bucket name from path (gs://bucket-name or just bucket-name)
            if bucket_path.startswith('gs://'):
                bucket_name = bucket_path.replace('gs://', '').split('/')[0]
            else:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f'gs://{bucket_path}' if bucket_path and not bucket_path.startswith('gs://') else bucket_path

            connection_data.update({
                'source_host': bucket_name,  # For backward compatibility (troubleshooting docs)
                'bucket_path': bucket_path,
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'service_account_json': connection_params.get('service_account_json', ''),
            })

        elif source_type == 's3':
            # === AWS S3 ===
            bucket_path = connection_params.get('bucket_path', '')
            # Extract bucket name from path (s3://bucket-name or just bucket-name)
            if bucket_path.startswith('s3://'):
                bucket_name = bucket_path.replace('s3://', '').split('/')[0]
            else:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f's3://{bucket_path}' if bucket_path and not bucket_path.startswith('s3://') else bucket_path

            connection_data.update({
                'source_host': bucket_name,  # Bucket name
                'bucket_path': bucket_path,
                'aws_access_key_id': connection_params.get('aws_access_key_id', ''),
                'aws_region': connection_params.get('aws_region', 'us-east-1'),
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'aws_access_key_id': connection_params.get('aws_access_key_id', ''),
                'aws_secret_access_key': connection_params.get('aws_secret_access_key', ''),
                'aws_region': connection_params.get('aws_region', 'us-east-1'),
            })

        elif source_type == 'azure_blob':
            # === AZURE BLOB STORAGE ===
            bucket_path = connection_params.get('bucket_path', '')
            connection_data.update({
                'bucket_path': bucket_path,
                'azure_storage_account': connection_params.get('azure_storage_account', ''),
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'azure_storage_account': connection_params.get('azure_storage_account', ''),
                'azure_account_key': connection_params.get('azure_account_key', ''),
                'azure_sas_token': connection_params.get('azure_sas_token', ''),
            })

        elif source_type in NOSQL_TYPES:
            # === NOSQL DATABASES ===
            connection_data.update({
                'connection_string': connection_params.get('connection_string', ''),
                'connection_params': connection_params.get('connection_params', {}),
            })
            credentials_dict.update({
                'connection_string': connection_params.get('connection_string', ''),
            })

            if source_type == 'firestore':
                connection_data['bigquery_project'] = connection_params.get('project_id', '')
                credentials_dict['project_id'] = connection_params.get('project_id', '')
                credentials_dict['service_account_json'] = connection_params.get('service_account_json', '')
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Unsupported source type: {source_type}',
            }, status=400)

        # === TEST CONNECTION IF REQUESTED (standalone mode) ===
        if test_first:
            test_result = test_and_fetch_metadata(source_type, credentials_dict)
            if not test_result['success']:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Connection test failed: {test_result["message"]}',
                }, status=400)

        # === CREATE CONNECTION ===
        try:
            connection = Connection.objects.create(**connection_data)
        except IntegrityError:
            # Duplicate credentials detected (based on unique_together constraint)
            return JsonResponse({
                'status': 'error',
                'message': f'A connection with these credentials already exists. Please check existing connections.',
            }, status=400)

        # === SAVE CREDENTIALS TO SECRET MANAGER ===
        try:
            secret_name = save_connection_credentials(
                model_id=model_id,
                connection_id=connection.id,
                credentials_dict=credentials_dict
            )

            connection.credentials_secret_name = secret_name
            connection.last_test_at = timezone.now()
            connection.last_test_status = 'success' if test_first else ''
            connection.connection_tested = test_first
            connection.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Connection created successfully',
                'connection_id': connection.id,
                'connection_name': connection.name,
            })

        except Exception as secret_error:
            # If Secret Manager fails, delete the Connection
            connection.delete()
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to save credentials: {str(secret_error)}',
            }, status=500)

    except Exception as e:
        import traceback
        print(f"ERROR in api_connection_create: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to create connection: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_connections(request, model_id):
    """
    List all connections for a model.
    """
    from ml_platform.models import Connection

    try:
        model = get_object_or_404(ModelEndpoint, id=model_id)
        connections = Connection.objects.filter(model_endpoint=model).order_by('-created_at')

        connections_data = [{
            'id': conn.id,
            'name': conn.name,
            'source_type': conn.source_type,
            'source_type_display': conn.get_source_type_display(),
            'source_host': conn.source_host,
            'source_port': conn.source_port,
            'source_database': conn.source_database,
            'source_schema': conn.source_schema,
            'source_username': conn.source_username,
            'bigquery_project': conn.bigquery_project,
            'bigquery_dataset': conn.bigquery_dataset,
            'bucket_path': conn.bucket_path,  # For cloud storage connections
            'connection_string': conn.connection_string,
            'is_enabled': conn.is_enabled,
            'connection_tested': conn.connection_tested,
            'last_test_at': conn.last_test_at.isoformat() if conn.last_test_at else None,
            'last_test_status': conn.last_test_status,
            'created_at': conn.created_at.isoformat(),
            'jobs_count': conn.get_dependent_jobs_count(),
        } for conn in connections]

        return JsonResponse({
            'status': 'success',
            'connections': connections_data,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["GET"])
def get(request, connection_id):
    """
    Get details of a single connection - SOURCE-TYPE AWARE
    Returns appropriate fields based on connection type (DB, Cloud Storage, NoSQL).
    """
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Define source type categories
        DB_TYPES = {'postgresql', 'mysql', 'oracle', 'sqlserver', 'db2', 'redshift', 'synapse', 'bigquery', 'snowflake', 'mariadb', 'teradata'}
        STORAGE_TYPES = {'gcs', 's3', 'azure_blob'}
        NOSQL_TYPES = {'mongodb', 'firestore', 'cassandra', 'dynamodb', 'redis'}

        # Base fields (common to all types)
        connection_data = {
            'id': connection.id,
            'name': connection.name,
            'source_type': connection.source_type,
            'source_type_display': connection.get_source_type_display(),
            'description': connection.description,
            'is_enabled': connection.is_enabled,
            'connection_tested': connection.connection_tested,
            'last_test_at': connection.last_test_at.isoformat() if connection.last_test_at else None,
            'last_test_status': connection.last_test_status,
            'last_test_message': connection.last_test_message,
            'jobs_count': connection.get_dependent_jobs_count(),
        }

        # === ADD SOURCE-TYPE SPECIFIC FIELDS ===
        if connection.source_type in DB_TYPES:
            # === RELATIONAL DATABASES ===
            connection_data.update({
                'source_host': connection.source_host or '',
                'source_port': connection.source_port,
                'source_database': connection.source_database or '',
                'source_schema': connection.source_schema or '',
                'source_username': connection.source_username or '',
            })
            if connection.source_type == 'bigquery':
                connection_data.update({
                    'bigquery_project': connection.bigquery_project or '',
                    'bigquery_dataset': connection.bigquery_dataset or '',
                })

        elif connection.source_type == 'gcs':
            # === GOOGLE CLOUD STORAGE ===
            # Handle backward compatibility: check bucket_path first, fallback to source_host
            bucket_path = connection.bucket_path or (f'gs://{connection.source_host}' if connection.source_host else '')
            connection_data.update({
                'bucket_path': bucket_path,
                'source_host': connection.source_host or '',  # Bucket name (legacy)
            })

        elif connection.source_type == 's3':
            # === AWS S3 ===
            connection_data.update({
                'bucket_path': connection.bucket_path or '',
                'source_host': connection.source_host or '',  # Bucket name
                'aws_access_key_id': connection.aws_access_key_id or '',
                'aws_region': connection.aws_region or 'us-east-1',
            })

        elif connection.source_type == 'azure_blob':
            # === AZURE BLOB STORAGE ===
            connection_data.update({
                'bucket_path': connection.bucket_path or '',
                'azure_storage_account': connection.azure_storage_account or '',
            })

        elif connection.source_type in NOSQL_TYPES:
            # === NOSQL DATABASES ===
            connection_data.update({
                'connection_string': connection.connection_string or '',
                'connection_params': connection.connection_params or {},
            })
            if connection.source_type == 'firestore':
                connection_data['bigquery_project'] = connection.bigquery_project or ''

        return JsonResponse({
            'status': 'success',
            'connection': connection_data,
        })

    except Exception as e:
        import traceback
        print(f"ERROR in api_connection_get: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["GET"])
def get_credentials(request, connection_id):
    """
    Fetch connection credentials from Secret Manager for editing.
    Returns password so Step 2 can be pre-populated when reusing saved connection.
    """
    from ml_platform.utils.connection_manager import get_credentials_from_secret_manager
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=404)

        # Fetch credentials from Secret Manager
        try:
            credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

            return JsonResponse({
                'status': 'success',
                'credentials': credentials,
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to retrieve credentials: {str(e)}',
            }, status=500)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=400)


@login_required
@require_http_methods(["POST"])
def test(request, connection_id):
    """
    Test an existing connection using stored credentials.
    Used by auto-test feature on ETL page.
    """
    from ml_platform.utils.connection_manager import test_and_fetch_metadata, get_credentials_from_secret_manager
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Check if credentials are stored
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection. Please edit and save the connection.',
            }, status=400)

        # Retrieve credentials from Secret Manager
        try:
            credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)
        except Exception as cred_error:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to retrieve credentials: {str(cred_error)}',
            }, status=500)

        # Prepare connection parameters with stored credentials
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
            'connection_string': connection.connection_string,
            # Cloud storage parameters
            'bucket_path': connection.bucket_path,
        }

        # Test connection
        result = test_and_fetch_metadata(connection.source_type, connection_params)

        # Update connection status
        connection.last_test_at = timezone.now()
        connection.last_test_status = 'success' if result['success'] else 'failed'
        connection.last_test_message = result['message']
        connection.connection_tested = result['success']
        connection.save()

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
            })
        else:
            return JsonResponse({
                'status': 'failed',  # Changed from 'error' to 'failed' to match frontend expectations
                'message': result['message'],
            })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in api_connection_test: {error_details}")  # Log to console for debugging
        return JsonResponse({
            'status': 'error',
            'message': f'System error: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def update(request, connection_id):
    """
    Update an existing connection - SOURCE-TYPE AWARE
    Handles ALL source types: Databases, Cloud Storage, NoSQL
    Tests connection before updating. Affects all ETL jobs using this connection.
    """
    from ml_platform.utils.connection_manager import test_and_fetch_metadata, save_connection_credentials
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)
        data = json.loads(request.body)

        # Extract updated connection details
        connection_name = data.get('name', connection.name)
        source_type = data.get('source_type', connection.source_type)

        # Check if connection name changed and if new name is taken
        if connection_name != connection.name:
            if Connection.objects.filter(
                model_endpoint=connection.model_endpoint,
                name=connection_name
            ).exclude(id=connection_id).exists():
                return JsonResponse({
                    'status': 'error',
                    'message': f'A connection named "{connection_name}" already exists. Please choose a different name.',
                }, status=400)

        # Define source type categories
        DB_TYPES = {'postgresql', 'mysql', 'oracle', 'sqlserver', 'db2', 'redshift', 'synapse', 'bigquery', 'snowflake', 'mariadb', 'teradata'}
        STORAGE_TYPES = {'gcs', 's3', 'azure_blob'}
        NOSQL_TYPES = {'mongodb', 'firestore', 'cassandra', 'dynamodb', 'redis'}

        # === SOURCE-TYPE AWARE FIELD EXTRACTION ===
        connection_updates = {
            'name': connection_name,
            'source_type': source_type,
            'description': data.get('description', connection.description),
        }
        credentials_dict = {}

        # Extract fields based on source type
        if source_type in DB_TYPES:
            # === RELATIONAL DATABASES ===
            connection_updates.update({
                'source_host': data.get('host', connection.source_host),
                'source_port': data.get('port', connection.source_port),
                'source_database': data.get('database', connection.source_database),
                'source_schema': data.get('schema', connection.source_schema),
                'source_username': data.get('username', connection.source_username),
            })
            credentials_dict.update({
                'host': data.get('host', connection.source_host),
                'port': data.get('port', connection.source_port),
                'database': data.get('database', connection.source_database),
                'schema': data.get('schema', connection.source_schema),
                'username': data.get('username', connection.source_username),
                'password': data.get('password', ''),
            })

            if source_type == 'bigquery':
                connection_updates['bigquery_project'] = data.get('project_id', connection.bigquery_project)
                connection_updates['bigquery_dataset'] = data.get('dataset', connection.bigquery_dataset)
                credentials_dict['project_id'] = data.get('project_id', connection.bigquery_project)
                credentials_dict['dataset'] = data.get('dataset', connection.bigquery_dataset)
                credentials_dict['service_account_json'] = data.get('service_account_json', '')

        elif source_type == 'gcs':
            # === GOOGLE CLOUD STORAGE ===
            bucket_path = data.get('bucket_path', connection.bucket_path)
            # Extract bucket name from path
            if bucket_path and bucket_path.startswith('gs://'):
                bucket_name = bucket_path.replace('gs://', '').split('/')[0]
            elif bucket_path:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f'gs://{bucket_path}'
            else:
                bucket_name = ''

            connection_updates.update({
                'source_host': bucket_name,
                'bucket_path': bucket_path,
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'service_account_json': data.get('service_account_json', ''),
            })

        elif source_type == 's3':
            # === AWS S3 ===
            bucket_path = data.get('bucket_path', connection.bucket_path)
            # Extract bucket name from path
            if bucket_path and bucket_path.startswith('s3://'):
                bucket_name = bucket_path.replace('s3://', '').split('/')[0]
            elif bucket_path:
                bucket_name = bucket_path.split('/')[0]
                bucket_path = f's3://{bucket_path}'
            else:
                bucket_name = ''

            connection_updates.update({
                'source_host': bucket_name,
                'bucket_path': bucket_path,
                'aws_access_key_id': data.get('aws_access_key_id', connection.aws_access_key_id),
                'aws_region': data.get('aws_region', connection.aws_region),
            })
            credentials_dict.update({
                'bucket_path': bucket_path,
                'aws_access_key_id': data.get('aws_access_key_id', connection.aws_access_key_id),
                'aws_secret_access_key': data.get('aws_secret_access_key', ''),
                'aws_region': data.get('aws_region', connection.aws_region),
            })

        elif source_type == 'azure_blob':
            # === AZURE BLOB STORAGE ===
            connection_updates.update({
                'bucket_path': data.get('bucket_path', connection.bucket_path),
                'azure_storage_account': data.get('azure_storage_account', connection.azure_storage_account),
            })
            credentials_dict.update({
                'bucket_path': data.get('bucket_path', connection.bucket_path),
                'azure_storage_account': data.get('azure_storage_account', connection.azure_storage_account),
                'azure_account_key': data.get('azure_account_key', ''),
                'azure_sas_token': data.get('azure_sas_token', ''),
            })

        elif source_type in NOSQL_TYPES:
            # === NOSQL DATABASES ===
            connection_updates.update({
                'connection_string': data.get('connection_string', connection.connection_string),
                'connection_params': data.get('connection_params', connection.connection_params),
            })
            credentials_dict.update({
                'connection_string': data.get('connection_string', connection.connection_string),
            })

            if source_type == 'firestore':
                connection_updates['bigquery_project'] = data.get('project_id', connection.bigquery_project)
                credentials_dict['project_id'] = data.get('project_id', connection.bigquery_project)
                credentials_dict['service_account_json'] = data.get('service_account_json', '')

        # === TEST CONNECTION FIRST ===
        test_result = test_and_fetch_metadata(source_type, credentials_dict)

        if not test_result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection test failed: {test_result["message"]}',
            }, status=400)

        # === UPDATE CONNECTION OBJECT ===
        for field, value in connection_updates.items():
            setattr(connection, field, value)

        connection.last_test_at = timezone.now()
        connection.last_test_status = 'success'
        connection.last_test_message = test_result['message']
        connection.connection_tested = True

        # === UPDATE CREDENTIALS IN SECRET MANAGER ===
        try:
            secret_name = save_connection_credentials(
                model_id=connection.model_endpoint.id,
                connection_id=connection.id,
                credentials_dict=credentials_dict
            )
            connection.credentials_secret_name = secret_name
            connection.save()

            # Get count of affected jobs
            affected_jobs_count = connection.data_sources.count()

            return JsonResponse({
                'status': 'success',
                'message': f'Connection updated successfully. {affected_jobs_count} ETL job(s) will use the new credentials.',
                'connection_id': connection.id,
                'affected_jobs_count': affected_jobs_count,
                'tables': test_result.get('tables', []),
            })

        except Exception as secret_error:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to update credentials: {str(secret_error)}',
            }, status=500)

    except Exception as e:
        import traceback
        print(f"ERROR in api_connection_update: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_and_fetch_tables(request, connection_id):
    """
    Test an existing connection and fetch tables using stored credentials.
    Used in edit mode to refresh table list without requiring password input.
    """
    from ml_platform.utils.connection_manager import test_and_fetch_metadata, get_credentials_from_secret_manager
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
            'connection_string': connection.connection_string,
        }

        # Test connection and fetch tables
        result = test_and_fetch_metadata(connection.source_type, connection_params)

        # Update connection status
        connection.last_test_at = timezone.now()
        connection.last_test_status = 'success' if result['success'] else 'failed'
        connection.last_test_message = result['message']
        connection.connection_tested = result['success']
        connection.save()

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'tables': result['tables'],
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_usage(request, connection_id):
    """
    Get list of ETL jobs that depend on this connection.
    """
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Get all DataSources using this connection
        dependent_jobs = []
        for ds in connection.data_sources.all():
            dependent_jobs.append({
                'id': ds.id,
                'name': ds.name,
                'source_type': ds.source_type,
                'is_enabled': ds.is_enabled,
                'created_at': ds.created_at.isoformat() if ds.created_at else None,
            })

        return JsonResponse({
            'status': 'success',
            'connection_id': connection.id,
            'connection_name': connection.name,
            'jobs_count': len(dependent_jobs),
            'jobs': dependent_jobs,
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete(request, connection_id):
    """
    Delete a connection.
    Only allowed if no ETL jobs depend on it.
    """
    from ml_platform.utils.connection_manager import delete_secret_from_secret_manager
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Get list of dependent jobs
        dependent_jobs = list(connection.data_sources.all().values_list('name', flat=True))

        if dependent_jobs:
            return JsonResponse({
                'status': 'error',
                'message': f'Cannot delete connection: {len(dependent_jobs)} ETL job(s) depend on it.',
                'dependent_jobs': dependent_jobs,
            }, status=400)

        # Delete secret from Secret Manager
        if connection.credentials_secret_name:
            try:
                delete_secret_from_secret_manager(connection.credentials_secret_name)
            except Exception as e:
                # Log but don't fail deletion if secret doesn't exist
                print(f"Warning: Could not delete secret {connection.credentials_secret_name}: {str(e)}")

        # Delete the connection
        connection_name = connection.name
        connection.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'Connection "{connection_name}" deleted successfully',
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


# ============================================================================
# NEW ETL WIZARD API ENDPOINTS (Simplified Flow)
# ============================================================================
@login_required
@require_http_methods(["GET"])
def fetch_schemas(request, connection_id):
    """
    Fetch available schemas for a connection.
    Used in ETL wizard Step 2 to show schema dropdown.
    """
    from ml_platform.utils.connection_manager import fetch_schemas, get_credentials_from_secret_manager
    from ml_platform.models import Connection

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
        }

        # Fetch schemas
        result = fetch_schemas(connection.source_type, connection_params)

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'schemas': result['schemas'],
                'source_type': connection.source_type,
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def fetch_tables_for_schema(request, connection_id):
    """
    Fetch tables for a specific schema within a connection.
    Used in ETL wizard Step 2 after schema selection.

    POST body: {
        "schema_name": "public"
    }
    """
    from ml_platform.utils.connection_manager import fetch_tables_for_schema, get_credentials_from_secret_manager
    from ml_platform.models import Connection
    import json

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Parse request body
        data = json.loads(request.body)
        schema_name = data.get('schema_name')

        if not schema_name:
            return JsonResponse({
                'status': 'error',
                'message': 'schema_name is required',
            }, status=400)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
        }

        # Fetch tables for the specified schema
        result = fetch_tables_for_schema(connection.source_type, schema_name, connection_params)

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'tables': result['tables'],
                'schema_name': schema_name,
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_connections_files(request, connection_id):
    """
    List files in cloud storage bucket matching a pattern.
    Used in ETL wizard Step 2 for cloud storage connections (GCS, S3, Azure).

    Query params:
        prefix: Folder path prefix (optional)
        pattern: File pattern using glob syntax (e.g., "*.csv", "data_*.parquet")

    Returns: {
        "status": "success",
        "files": [
            {
                "name": "data/file.csv",
                "size": 1024000,
                "last_modified": "2024-11-19 10:30:00"
            },
            ...
        ]
    }
    """
    from ml_platform.utils.connection_manager import get_credentials_from_secret_manager
    from ml_platform.models import Connection
    from google.cloud import storage
    from google.oauth2 import service_account
    import json
    import fnmatch

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Get query parameters
        prefix = request.GET.get('prefix', '').strip()
        pattern = request.GET.get('pattern', '*').strip()

        # Validate connection is cloud storage type
        if connection.source_type not in ['gcs', 's3', 'azure_blob']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection type "{connection.source_type}" is not a cloud storage type',
            }, status=400)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Handle different cloud storage types
        files = []

        if connection.source_type == 'gcs':
            # Google Cloud Storage
            bucket_path = connection.bucket_path  # gs://bucket-name

            if not bucket_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Bucket path not configured for this connection. Please edit the connection and set the bucket path.',
                }, status=400)

            if not bucket_path.startswith('gs://'):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid GCS bucket path. Must start with gs://',
                }, status=400)

            bucket_name = bucket_path.replace('gs://', '').split('/')[0]

            # Parse service account JSON
            service_account_json = credentials.get('service_account_json', '')
            credentials_info = json.loads(service_account_json)
            creds = service_account.Credentials.from_service_account_info(credentials_info)

            # Create GCS client
            client = storage.Client(credentials=creds, project=credentials_info.get('project_id'))
            bucket = client.get_bucket(bucket_name)

            # List all blobs with prefix (recursive)
            all_blobs = list(bucket.list_blobs(prefix=prefix, max_results=1000))

            # Filter by pattern (only filename, not full path)
            for blob in all_blobs:
                # Skip directories
                if blob.name.endswith('/'):
                    continue

                # Extract filename from full path
                filename = blob.name.split('/')[-1]

                # Match pattern against filename only
                if fnmatch.fnmatch(filename, pattern):
                    files.append({
                        'name': blob.name,
                        'size': blob.size,
                        'last_modified': blob.updated.strftime('%Y-%m-%d %H:%M:%S') if blob.updated else 'N/A'
                    })

        elif connection.source_type == 's3':
            # AWS S3 - to be implemented
            return JsonResponse({
                'status': 'error',
                'message': 'S3 file listing not yet implemented',
            }, status=501)

        elif connection.source_type == 'azure_blob':
            # Azure Blob Storage - to be implemented
            return JsonResponse({
                'status': 'error',
                'message': 'Azure Blob file listing not yet implemented',
            }, status=501)

        # Sort files by last modified (newest first)
        files.sort(key=lambda f: f['last_modified'], reverse=True)

        return JsonResponse({
            'status': 'success',
            'files': files,
            'count': len(files),
            'prefix': prefix,
            'pattern': pattern,
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid service account JSON format',
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)


@login_required
@require_http_methods(["POST"])
def detect_file_schema(request, connection_id):
    """
    Detect schema from a cloud storage file by downloading and analyzing a sample.
    Used in ETL wizard Step 2 for cloud storage connections.

    POST body: {
        "file_path": "data/transactions/file.csv",
        "file_format": "csv",
        "format_options": {
            "delimiter": ",",
            "encoding": "utf-8",
            "has_header": true
        }
    }

    Returns: {
        "status": "success",
        "columns": [
            {
                "name": "id",
                "type": "INTEGER",
                "bigquery_type": "INT64",
                "bigquery_mode": "NULLABLE",
                "sample_values": ["1", "2", "3"]
            },
            ...
        ],
        "total_rows": 1000 (estimated from sample),
        "schema_fingerprint": "abc123..."
    }
    """
    from ml_platform.utils.connection_manager import get_credentials_from_secret_manager
    from ml_platform.models import Connection
    from google.cloud import storage
    from google.oauth2 import service_account
    import json
    import pandas as pd
    import io
    import hashlib

    try:
        print(f"[SCHEMA DETECTION] Starting schema detection for connection_id={connection_id}")
        connection = get_object_or_404(Connection, id=connection_id)
        print(f"[SCHEMA DETECTION] Connection found: {connection.name} (type={connection.source_type})")

        # Parse request body
        data = json.loads(request.body)
        file_path = data.get('file_path')
        file_format = data.get('file_format', 'csv')
        format_options = data.get('format_options', {})

        print(f"[SCHEMA DETECTION] Request params: file_path={file_path}, format={file_format}, options={format_options}")
        print(f"[SCHEMA DETECTION] Bucket path: {connection.bucket_path}")
        print(f"[SCHEMA DETECTION] Has credentials: {bool(connection.credentials_secret_name)}")

        if not file_path:
            return JsonResponse({
                'status': 'error',
                'message': 'file_path is required',
            }, status=400)

        # Validate connection is cloud storage
        if connection.source_type not in ['gcs', 's3', 'azure_blob']:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection type "{connection.source_type}" is not a cloud storage type',
            }, status=400)

        # Retrieve credentials
        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Download sample of file
        df_sample = None

        if connection.source_type == 'gcs':
            # Google Cloud Storage
            bucket_path = connection.bucket_path

            if not bucket_path:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Bucket path not configured for this connection. Please edit the connection and set the bucket path.',
                }, status=400)

            if not bucket_path.startswith('gs://'):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid GCS bucket path. Must start with gs://',
                }, status=400)

            bucket_name = bucket_path.replace('gs://', '').split('/')[0]

            # Parse service account JSON
            service_account_json = credentials.get('service_account_json', '')
            credentials_info = json.loads(service_account_json)
            creds = service_account.Credentials.from_service_account_info(credentials_info)

            # Create GCS client
            client = storage.Client(credentials=creds, project=credentials_info.get('project_id'))
            bucket = client.get_bucket(bucket_name)
            blob = bucket.blob(file_path)

            # Get file metadata
            blob.reload()
            file_size = blob.size

            # Download file content (limit to first 5MB for schema detection)
            max_bytes_to_download = min(file_size, 5 * 1024 * 1024)  # 5MB max
            file_content = blob.download_as_bytes(end=max_bytes_to_download)

            # Parse based on format
            if file_format == 'csv':
                delimiter = format_options.get('delimiter', ',')
                encoding = format_options.get('encoding', 'utf-8')
                has_header = format_options.get('has_header', True)

                # Handle tab delimiter
                if delimiter == '\\t':
                    delimiter = '\t'

                # Read CSV with pandas (limited rows)
                df_sample = pd.read_csv(
                    io.BytesIO(file_content),
                    delimiter=delimiter,
                    encoding=encoding,
                    header=0 if has_header else None,
                    nrows=1000,  # Sample first 1000 rows
                    low_memory=False
                )

                # If no header, create column names
                if not has_header:
                    df_sample.columns = [f'column_{i}' for i in range(len(df_sample.columns))]

            elif file_format == 'parquet':
                df_sample = pd.read_parquet(io.BytesIO(file_content))

            elif file_format == 'json':
                df_sample = pd.read_json(io.BytesIO(file_content), lines=True, nrows=1000)

            else:
                return JsonResponse({
                    'status': 'error',
                    'message': f'File format "{file_format}" not yet supported',
                }, status=400)

        else:
            # S3 and Azure not yet implemented
            return JsonResponse({
                'status': 'error',
                'message': f'{connection.source_type.upper()} schema detection not yet implemented',
            }, status=501)

        # Detect schema from pandas DataFrame
        from ml_platform.utils.schema_mapper import SchemaMapper
        columns = []
        for col_name in df_sample.columns:
            col_data = df_sample[col_name]
            pandas_dtype = str(col_data.dtype)

            # Sanitize column name for BigQuery
            name_info = SchemaMapper.sanitize_column_name(str(col_name))

            # Map pandas dtype to BigQuery type
            if pandas_dtype.startswith('int'):
                bq_type = 'INT64'
            elif pandas_dtype.startswith('float'):
                bq_type = 'FLOAT64'
            elif pandas_dtype == 'bool':
                bq_type = 'BOOL'
            elif pandas_dtype == 'datetime64':
                bq_type = 'TIMESTAMP'
            elif pandas_dtype == 'object':
                # Try to infer if it's a date
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        pd.to_datetime(col_data.dropna().iloc[:10])
                    bq_type = 'TIMESTAMP'
                except:
                    bq_type = 'STRING'
            else:
                bq_type = 'STRING'

            # Get sample values (first 5 non-null values)
            sample_values = col_data.dropna().head(5).astype(str).tolist()

            # Determine if column has nulls
            has_nulls = col_data.isnull().any()
            bq_mode = 'NULLABLE' if has_nulls else 'REQUIRED'

            columns.append({
                'name': name_info['sanitized_name'],  # Use sanitized name for BigQuery
                'original_name': name_info['original_name'],  # Preserve original name
                'name_changed': name_info['name_changed'],  # Flag if name was changed
                'type': pandas_dtype,
                'bigquery_type': bq_type,
                'bigquery_mode': bq_mode,
                'sample_values': sample_values,
                'nullable': bool(has_nulls)  # Convert numpy.bool_ to Python bool for JSON serialization
            })

        # Generate schema fingerprint (hash of column names + types)
        schema_string = '|'.join([f"{c['name']}:{c['bigquery_type']}" for c in columns])
        schema_fingerprint = hashlib.md5(schema_string.encode()).hexdigest()

        return JsonResponse({
            'status': 'success',
            'columns': columns,
            'total_rows': len(df_sample),
            'schema_fingerprint': schema_fingerprint,
            'file_size': file_size,
        })

    except pd.errors.ParserError as e:
        import traceback
        print(f"[SCHEMA DETECTION] Parser error: {str(e)}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to parse file: {str(e)}. Check delimiter and encoding settings.',
        }, status=400)
    except Exception as e:
        import traceback
        print(f"[SCHEMA DETECTION] Unexpected error: {str(e)}")
        print(f"[SCHEMA DETECTION] Error type: {type(e).__name__}")
        print(f"[SCHEMA DETECTION] Connection ID: {connection_id}")
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': f'{type(e).__name__}: {str(e)}',
        }, status=500)


@login_required
@require_http_methods(["POST"])
def fetch_table_preview(request, connection_id):
    """
    Fetch table preview with column metadata and sample data.
    Used in ETL wizard Step 3 to show table structure.

    POST body: {
        "schema_name": "public",
        "table_name": "transactions"
    }

    Returns: {
        "columns": [...],
        "total_rows": 1234567,
        "recommended": {...}
    }
    """
    from ml_platform.utils.connection_manager import fetch_table_metadata, get_credentials_from_secret_manager
    from ml_platform.models import Connection
    import json

    try:
        connection = get_object_or_404(Connection, id=connection_id)

        # Parse request body
        data = json.loads(request.body)
        schema_name = data.get('schema_name')
        table_name = data.get('table_name')

        if not schema_name or not table_name:
            return JsonResponse({
                'status': 'error',
                'message': 'schema_name and table_name are required',
            }, status=400)

        # Retrieve credentials from Secret Manager
        if not connection.credentials_secret_name:
            return JsonResponse({
                'status': 'error',
                'message': 'No credentials stored for this connection',
            }, status=400)

        credentials = get_credentials_from_secret_manager(connection.credentials_secret_name)

        # Prepare connection parameters
        connection_params = {
            'host': connection.source_host,
            'port': connection.source_port,
            'database': connection.source_database,
            'username': credentials.get('username', ''),
            'password': credentials.get('password', ''),
            'project_id': connection.bigquery_project,
            'dataset': connection.bigquery_dataset,
            'service_account_json': credentials.get('service_account_json', ''),
        }

        # Fetch table metadata
        result = fetch_table_metadata(
            connection.source_type,
            schema_name,
            table_name,
            connection_params
        )

        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': result['message'],
                'columns': result['columns'],
                'total_rows': result['total_rows'],
                'recommended': result.get('recommended', {}),
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': result['message'],
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e),
        }, status=500)
