"""
Connection Manager for testing database connections and managing credentials.

This module provides functions to:
- Test connections to various database types (PostgreSQL, MySQL, BigQuery, etc.)
- Fetch table metadata (names, row counts, last updated)
- Store credentials securely in GCP Secret Manager
- Retrieve credentials for ETL runs
"""

import json
import psycopg2
import pymysql
from datetime import datetime
from google.cloud import secretmanager, storage
from google.api_core import exceptions as gcp_exceptions
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError


# GCP Project ID (should match your project)
GCP_PROJECT_ID = "b2b-recs"


def test_and_fetch_metadata(source_type, connection_params):
    """
    Main entry point for testing connections and fetching metadata.

    Args:
        source_type (str): Type of data source ('postgresql', 'mysql', 'bigquery', 'firestore', etc.)
        connection_params (dict): Connection parameters (host, port, database, username, password, etc.)

    Returns:
        dict: {
            'success': True/False,
            'message': 'Connection successful' or error details,
            'tables': [
                {'name': 'table1', 'row_count': 1000, 'last_updated': '2025-11-12'},
                ...
            ]
        }
    """
    # Route to appropriate test function based on source type
    if source_type == 'postgresql':
        return test_postgresql(**connection_params)
    elif source_type == 'mysql':
        return test_mysql(**connection_params)
    elif source_type == 'bigquery':
        return test_bigquery(**connection_params)
    elif source_type == 'firestore':
        return test_firestore(**connection_params)
    elif source_type == 'gcs':
        return test_gcs(**connection_params)
    elif source_type == 's3':
        return test_s3(**connection_params)
    elif source_type == 'azure_blob':
        return test_azure_blob(**connection_params)
    else:
        return {
            'success': False,
            'message': f'Database type "{source_type}" not yet implemented',
            'tables': []
        }


def test_postgresql(host, port, database, username, password, timeout=10, **kwargs):
    """
    Test PostgreSQL connection and fetch table metadata.

    Args:
        host (str): Database host (IP or hostname)
        port (int): Database port (usually 5432)
        database (str): Database name
        username (str): Database username
        password (str): Database password
        timeout (int): Connection timeout in seconds

    Returns:
        dict: Connection result with table metadata
    """
    conn = None
    cursor = None

    try:
        # Attempt connection
        conn = psycopg2.connect(
            host=host,
            port=port or 5432,
            database=database,
            user=username,
            password=password,
            connect_timeout=timeout
        )

        cursor = conn.cursor()

        # Test query to verify connection
        cursor.execute("SELECT 1")
        cursor.fetchone()

        # Fetch table metadata
        tables = []

        # Query to get all tables in the database (excluding system tables)
        cursor.execute("""
            SELECT
                table_name,
                pg_total_relation_size(quote_ident(table_name)::regclass) as size_bytes
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)

        for row in cursor.fetchall():
            table_name = row[0]

            # Get row count for each table
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = None

            # Get last modified time (if possible)
            try:
                cursor.execute(f"""
                    SELECT pg_stat_get_last_analyze_time(c.oid) as last_updated
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = '{table_name}'
                    AND n.nspname = 'public'
                """)
                result = cursor.fetchone()
                last_updated = result[0].strftime('%Y-%m-%d %H:%M:%S') if result and result[0] else None
            except Exception:
                last_updated = None

            tables.append({
                'name': table_name,
                'row_count': row_count,
                'last_updated': last_updated or 'Unknown'
            })

        return {
            'success': True,
            'message': f'Successfully connected to PostgreSQL database "{database}" ({len(tables)} tables found)',
            'tables': tables
        }

    except psycopg2.OperationalError as e:
        error_msg = str(e)
        if 'timeout' in error_msg.lower():
            return {
                'success': False,
                'message': f'Connection timeout after {timeout} seconds. Check hostname and firewall rules.',
                'tables': []
            }
        elif 'authentication failed' in error_msg.lower() or 'password' in error_msg.lower():
            return {
                'success': False,
                'message': 'Authentication failed. Please check username and password.',
                'tables': []
            }
        elif 'does not exist' in error_msg.lower():
            return {
                'success': False,
                'message': f'Database "{database}" does not exist on server.',
                'tables': []
            }
        else:
            return {
                'success': False,
                'message': f'Connection error: {error_msg}',
                'tables': []
            }

    except Exception as e:
        return {
            'success': False,
            'message': f'Unexpected error: {str(e)}',
            'tables': []
        }

    finally:
        # Clean up connections
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def test_mysql(host, port, database, username, password, timeout=10, **kwargs):
    """
    Test MySQL connection and fetch table metadata.

    Args:
        host (str): Database host
        port (int): Database port (usually 3306)
        database (str): Database name
        username (str): Database username
        password (str): Database password
        timeout (int): Connection timeout in seconds

    Returns:
        dict: Connection result with table metadata
    """
    conn = None
    cursor = None

    try:
        # Attempt connection
        conn = pymysql.connect(
            host=host,
            port=port or 3306,
            database=database,
            user=username,
            password=password,
            connect_timeout=timeout
        )

        cursor = conn.cursor()

        # Test query
        cursor.execute("SELECT 1")
        cursor.fetchone()

        # Fetch table metadata
        tables = []

        # Get all tables
        cursor.execute("SHOW TABLES")

        for row in cursor.fetchall():
            table_name = row[0]

            # Get row count
            try:
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = None

            # Get last update time
            try:
                cursor.execute(f"""
                    SELECT UPDATE_TIME
                    FROM information_schema.tables
                    WHERE table_schema = '{database}'
                    AND table_name = '{table_name}'
                """)
                result = cursor.fetchone()
                last_updated = result[0].strftime('%Y-%m-%d %H:%M:%S') if result and result[0] else None
            except Exception:
                last_updated = None

            tables.append({
                'name': table_name,
                'row_count': row_count,
                'last_updated': last_updated or 'Unknown'
            })

        return {
            'success': True,
            'message': f'Successfully connected to MySQL database "{database}" ({len(tables)} tables found)',
            'tables': tables
        }

    except pymysql.OperationalError as e:
        error_msg = str(e)
        if 'Access denied' in error_msg:
            return {
                'success': False,
                'message': 'Authentication failed. Please check username and password.',
                'tables': []
            }
        elif 'Unknown database' in error_msg:
            return {
                'success': False,
                'message': f'Database "{database}" does not exist on server.',
                'tables': []
            }
        else:
            return {
                'success': False,
                'message': f'Connection error: {error_msg}',
                'tables': []
            }

    except Exception as e:
        return {
            'success': False,
            'message': f'Unexpected error: {str(e)}',
            'tables': []
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def test_bigquery(project_id, dataset, service_account_json, **kwargs):
    """
    Test BigQuery connection and fetch dataset/table metadata.

    Args:
        project_id (str): GCP project ID
        dataset (str): Optional - BigQuery dataset name (if empty, lists all datasets)
        service_account_json (str): Service account JSON key (as string)

    Returns:
        dict: Connection result with dataset/table metadata
    """
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        # Parse service account JSON
        credentials_dict = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)

        # Create BigQuery client
        client = bigquery.Client(
            project=project_id,
            credentials=credentials
        )

        # Test connection by listing datasets
        all_datasets = list(client.list_datasets())

        # If dataset is specified, validate it and list tables
        if dataset and dataset.strip():
            dataset_ref = client.dataset(dataset)
            try:
                client.get_dataset(dataset_ref)
            except Exception:
                return {
                    'success': False,
                    'message': f'Dataset "{dataset}" not found in project "{project_id}"',
                    'tables': []
                }

            # Fetch tables in the specified dataset
            tables = []
            table_list = client.list_tables(dataset)

            for table_item in table_list:
                table_ref = client.get_table(f"{project_id}.{dataset}.{table_item.table_id}")

                tables.append({
                    'name': table_item.table_id,
                    'row_count': table_ref.num_rows,
                    'last_updated': table_ref.modified.strftime('%Y-%m-%d %H:%M:%S') if table_ref.modified else 'Unknown'
                })

            return {
                'success': True,
                'message': f'Successfully connected to BigQuery dataset "{dataset}" ({len(tables)} tables found)',
                'tables': tables
            }
        else:
            # No dataset specified - list all datasets in the project
            datasets_info = []
            for dataset_item in all_datasets:
                # Get dataset details
                try:
                    dataset_ref = client.get_dataset(dataset_item.dataset_id)
                    table_count = len(list(client.list_tables(dataset_item.dataset_id)))

                    datasets_info.append({
                        'name': dataset_item.dataset_id,
                        'row_count': f'{table_count} tables',
                        'last_updated': dataset_ref.modified.strftime('%Y-%m-%d %H:%M:%S') if dataset_ref.modified else 'Unknown'
                    })
                except Exception:
                    datasets_info.append({
                        'name': dataset_item.dataset_id,
                        'row_count': 'Unknown',
                        'last_updated': 'Unknown'
                    })

            return {
                'success': True,
                'message': f'Successfully connected to BigQuery project "{project_id}" ({len(datasets_info)} datasets found)',
                'tables': datasets_info
            }

    except json.JSONDecodeError:
        return {
            'success': False,
            'message': 'Invalid service account JSON. Please check the format.',
            'tables': []
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'BigQuery connection error: {str(e)}',
            'tables': []
        }


def test_firestore(project_id, dataset, service_account_json, **kwargs):
    """
    Test Firestore connection and fetch collection metadata.

    Args:
        project_id (str): GCP project ID
        dataset (str): Optional - specific collection name to validate (not required)
        service_account_json (str): Service account JSON key (as string)

    Returns:
        dict: Connection result with collection metadata (collections shown as 'tables')
    """
    try:
        from google.cloud import firestore
        from google.oauth2 import service_account

        # Parse service account JSON
        credentials_dict = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)

        # Create Firestore client
        db = firestore.Client(
            project=project_id,
            credentials=credentials
        )

        # Test connection by listing collections
        collections = []
        collection_refs = db.collections()

        # Firestore collections() returns an iterator
        for collection_ref in collection_refs:
            collection_name = collection_ref.id

            # Count documents in collection (limit to 1000 for performance)
            try:
                docs = list(collection_ref.limit(1000).stream())
                doc_count = len(docs)

                # If we got exactly 1000, there might be more
                if doc_count == 1000:
                    doc_count_display = "1000+"
                else:
                    doc_count_display = doc_count

            except Exception:
                doc_count_display = "Unknown"

            collections.append({
                'name': collection_name,
                'row_count': doc_count_display,
                'last_updated': 'N/A'  # Firestore doesn't provide collection-level timestamps
            })

        # If a specific collection was provided, validate it exists
        if dataset and dataset.strip():
            collection_found = any(c['name'] == dataset for c in collections)
            if not collection_found:
                return {
                    'success': False,
                    'message': f'Collection "{dataset}" not found in Firestore database',
                    'tables': []
                }
            # Filter to show only the requested collection
            collections = [c for c in collections if c['name'] == dataset]
            return {
                'success': True,
                'message': f'Successfully connected to Firestore. Collection "{dataset}" found with {collections[0]["row_count"]} documents',
                'tables': collections
            }

        # No specific collection requested - show all collections
        if len(collections) == 0:
            return {
                'success': True,
                'message': f'Successfully connected to Firestore project "{project_id}" (no collections found - database is empty)',
                'tables': []
            }

        return {
            'success': True,
            'message': f'Successfully connected to Firestore project "{project_id}" ({len(collections)} collections found)',
            'tables': collections
        }

    except json.JSONDecodeError:
        return {
            'success': False,
            'message': 'Invalid service account JSON. Please check the format.',
            'tables': []
        }

    except Exception as e:
        error_msg = str(e)

        # Provide helpful error messages for common issues
        if 'permission' in error_msg.lower() or 'forbidden' in error_msg.lower():
            return {
                'success': False,
                'message': f'Permission denied. Service account needs "Cloud Datastore User" or "Cloud Datastore Viewer" role for project "{project_id}"',
                'tables': []
            }
        elif 'not found' in error_msg.lower():
            return {
                'success': False,
                'message': f'Project "{project_id}" not found or Firestore is not enabled',
                'tables': []
            }
        else:
            return {
                'success': False,
                'message': f'Firestore connection error: {error_msg}',
                'tables': []
            }


def save_credentials_to_secret_manager(model_id, source_id, credentials_dict):
    """
    Save credentials to GCP Secret Manager.

    Args:
        model_id (int): Model endpoint ID
        source_id (int): Data source ID
        credentials_dict (dict): Credentials to store (host, username, password, etc.)

    Returns:
        str: Secret name (e.g., 'model-5-source-12-credentials')

    Raises:
        Exception: If secret creation fails
    """
    try:
        client = secretmanager.SecretManagerServiceClient()

        # Generate secret name
        secret_name = f"model-{model_id}-source-{source_id}-credentials"
        parent = f"projects/{GCP_PROJECT_ID}"
        secret_id = secret_name

        # Convert credentials to JSON string
        payload = json.dumps(credentials_dict).encode('UTF-8')

        # Check if secret already exists
        secret_path = f"{parent}/secrets/{secret_id}"
        try:
            client.get_secret(name=secret_path)
            # Secret exists, add new version
            version_parent = secret_path
            response = client.add_secret_version(
                request={
                    "parent": version_parent,
                    "payload": {"data": payload}
                }
            )
        except gcp_exceptions.NotFound:
            # Secret doesn't exist, create it
            secret = client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {
                        "replication": {"automatic": {}},
                    },
                }
            )
            # Add first version
            response = client.add_secret_version(
                request={
                    "parent": secret.name,
                    "payload": {"data": payload}
                }
            )

        return secret_name

    except Exception as e:
        raise Exception(f"Failed to save credentials to Secret Manager: {str(e)}")


def get_credentials_from_secret_manager(secret_name):
    """
    Retrieve credentials from GCP Secret Manager.

    Args:
        secret_name (str): Secret name (e.g., 'model-5-source-12-credentials')

    Returns:
        dict: Credentials dictionary

    Raises:
        Exception: If secret retrieval fails
    """
    try:
        client = secretmanager.SecretManagerServiceClient()

        # Build secret version name
        name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"

        # Access the secret version
        response = client.access_secret_version(request={"name": name})

        # Parse and return credentials
        payload = response.payload.data.decode('UTF-8')
        return json.loads(payload)

    except gcp_exceptions.NotFound:
        raise Exception(f"Secret '{secret_name}' not found in Secret Manager")

    except Exception as e:
        raise Exception(f"Failed to retrieve credentials from Secret Manager: {str(e)}")


def save_connection_credentials(model_id, connection_id, credentials_dict):
    """
    Save connection credentials to GCP Secret Manager.
    Uses naming convention: model-{model_id}-connection-{connection_id}-credentials

    Args:
        model_id (int): Model endpoint ID
        connection_id (int): Connection ID
        credentials_dict (dict): Credentials to store

    Returns:
        str: Secret name

    Raises:
        Exception: If secret creation fails
    """
    try:
        client = secretmanager.SecretManagerServiceClient()

        # Generate secret name for Connection (different from DataSource)
        secret_name = f"model-{model_id}-connection-{connection_id}-credentials"
        parent = f"projects/{GCP_PROJECT_ID}"
        secret_id = secret_name

        # Convert credentials to JSON string
        payload = json.dumps(credentials_dict).encode('UTF-8')

        # Check if secret already exists
        secret_path = f"{parent}/secrets/{secret_id}"
        try:
            client.get_secret(name=secret_path)
            # Secret exists, add new version
            version_parent = secret_path
            response = client.add_secret_version(
                request={
                    "parent": version_parent,
                    "payload": {"data": payload}
                }
            )
        except gcp_exceptions.NotFound:
            # Secret doesn't exist, create it
            secret = client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {
                        "replication": {"automatic": {}},
                    },
                }
            )
            # Add first version
            response = client.add_secret_version(
                request={
                    "parent": secret.name,
                    "payload": {"data": payload}
                }
            )

        return secret_name

    except Exception as e:
        raise Exception(f"Failed to save credentials to Secret Manager: {str(e)}")


def delete_secret_from_secret_manager(secret_name):
    """
    Delete a secret from GCP Secret Manager.

    Args:
        secret_name (str): Secret name to delete

    Returns:
        bool: True if deleted successfully, False if secret didn't exist

    Raises:
        Exception: If deletion fails for reasons other than "not found"
    """
    try:
        client = secretmanager.SecretManagerServiceClient()

        # Build secret path
        secret_path = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}"

        # Delete the secret
        client.delete_secret(request={"name": secret_path})

        return True

    except gcp_exceptions.NotFound:
        # Secret doesn't exist - that's okay
        return False

    except Exception as e:
        raise Exception(f"Failed to delete secret from Secret Manager: {str(e)}")


def test_gcs(bucket_path, service_account_json, **kwargs):
    """
    Test Google Cloud Storage connection and list available files.

    Args:
        bucket_path (str): GCS bucket path (e.g., gs://my-bucket-name)
        service_account_json (str): Service account JSON key as string

    Returns:
        dict: Connection result with file metadata
    """
    try:
        # Parse service account JSON
        try:
            credentials_info = json.loads(service_account_json)
        except json.JSONDecodeError:
            return {
                'success': False,
                'message': 'Invalid service account JSON format',
                'tables': []
            }

        # Extract bucket name from path (gs://bucket-name)
        if not bucket_path.startswith('gs://'):
            return {
                'success': False,
                'message': 'Bucket path must start with gs://',
                'tables': []
            }

        bucket_name = bucket_path.replace('gs://', '').split('/')[0]

        # Create GCS client with service account
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = storage.Client(credentials=credentials, project=credentials_info.get('project_id'))

        # Test connection by accessing bucket
        bucket = client.get_bucket(bucket_name)

        # List files in bucket (limit to 100 for performance)
        blobs = list(bucket.list_blobs(max_results=100))

        file_list = []
        for blob in blobs:
            file_list.append({
                'name': blob.name,
                'size': blob.size,
                'last_modified': blob.updated.strftime('%Y-%m-%d %H:%M:%S') if blob.updated else 'N/A'
            })

        return {
            'success': True,
            'message': f'Successfully connected to GCS bucket: {bucket_name}. Found {len(file_list)} files (showing up to 100).',
            'tables': file_list  # Using 'tables' for consistency with other connection types
        }

    except gcp_exceptions.NotFound:
        return {
            'success': False,
            'message': f'Bucket not found: {bucket_name}. Check bucket name and permissions.',
            'tables': []
        }
    except gcp_exceptions.Forbidden:
        return {
            'success': False,
            'message': 'Access denied. Service account does not have permission to access this bucket.',
            'tables': []
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'GCS connection failed: {str(e)}',
            'tables': []
        }


def test_s3(bucket_path, aws_access_key_id, aws_secret_access_key, aws_region, **kwargs):
    """
    Test AWS S3 connection and list available files.

    Args:
        bucket_path (str): S3 bucket path (e.g., s3://my-bucket-name)
        aws_access_key_id (str): AWS access key ID
        aws_secret_access_key (str): AWS secret access key
        aws_region (str): AWS region (e.g., us-east-1)

    Returns:
        dict: Connection result with file metadata
    """
    try:
        # Extract bucket name from path (s3://bucket-name)
        if not bucket_path.startswith('s3://'):
            return {
                'success': False,
                'message': 'Bucket path must start with s3://',
                'tables': []
            }

        bucket_name = bucket_path.replace('s3://', '').split('/')[0]

        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )

        # Test connection by listing objects (limit to 100)
        response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=100)

        file_list = []
        if 'Contents' in response:
            for obj in response['Contents']:
                file_list.append({
                    'name': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].strftime('%Y-%m-%d %H:%M:%S')
                })

        return {
            'success': True,
            'message': f'Successfully connected to S3 bucket: {bucket_name}. Found {len(file_list)} files (showing up to 100).',
            'tables': file_list
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            return {
                'success': False,
                'message': f'Bucket not found: {bucket_name}',
                'tables': []
            }
        elif error_code == 'InvalidAccessKeyId':
            return {
                'success': False,
                'message': 'Invalid AWS Access Key ID',
                'tables': []
            }
        elif error_code == 'SignatureDoesNotMatch':
            return {
                'success': False,
                'message': 'Invalid AWS Secret Access Key',
                'tables': []
            }
        elif error_code == 'AccessDenied':
            return {
                'success': False,
                'message': 'Access denied. Check IAM permissions for this bucket.',
                'tables': []
            }
        else:
            return {
                'success': False,
                'message': f'S3 error: {error_code} - {e.response["Error"]["Message"]}',
                'tables': []
            }
    except NoCredentialsError:
        return {
            'success': False,
            'message': 'AWS credentials not provided',
            'tables': []
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'S3 connection failed: {str(e)}',
            'tables': []
        }


def test_azure_blob(bucket_path, azure_storage_account, azure_account_key=None, azure_sas_token=None, **kwargs):
    """
    Test Azure Blob Storage connection and list available files.

    Args:
        bucket_path (str): Azure container URL (e.g., https://account.blob.core.windows.net/container)
        azure_storage_account (str): Storage account name
        azure_account_key (str, optional): Account key for authentication
        azure_sas_token (str, optional): SAS token for authentication (alternative to account key)

    Returns:
        dict: Connection result with file metadata
    """
    try:
        # Validate authentication method
        if not azure_account_key and not azure_sas_token:
            return {
                'success': False,
                'message': 'Either account key or SAS token must be provided',
                'tables': []
            }

        # Extract container name from URL
        # Expected format: https://storageaccount.blob.core.windows.net/container
        if not bucket_path.startswith('https://'):
            return {
                'success': False,
                'message': 'Container path must be a valid HTTPS URL',
                'tables': []
            }

        parts = bucket_path.replace('https://', '').split('/')
        if len(parts) < 2:
            return {
                'success': False,
                'message': 'Invalid container path format. Expected: https://account.blob.core.windows.net/container',
                'tables': []
            }

        container_name = parts[1]

        # Create BlobServiceClient
        if azure_account_key:
            account_url = f"https://{azure_storage_account}.blob.core.windows.net"
            blob_service_client = BlobServiceClient(account_url=account_url, credential=azure_account_key)
        else:
            # SAS token authentication
            account_url = f"https://{azure_storage_account}.blob.core.windows.net"
            blob_service_client = BlobServiceClient(account_url=account_url, credential=azure_sas_token)

        # Get container client and list blobs (limit to 100)
        container_client = blob_service_client.get_container_client(container_name)

        # Test connection by listing blobs
        blob_list = list(container_client.list_blobs(results_per_page=100))

        file_list = []
        for blob in blob_list[:100]:  # Limit to 100
            file_list.append({
                'name': blob.name,
                'size': blob.size,
                'last_modified': blob.last_modified.strftime('%Y-%m-%d %H:%M:%S') if blob.last_modified else 'N/A'
            })

        auth_method = "Account Key" if azure_account_key else "SAS Token"
        return {
            'success': True,
            'message': f'Successfully connected to Azure container: {container_name} using {auth_method}. Found {len(file_list)} files (showing up to 100).',
            'tables': file_list
        }

    except AzureError as e:
        error_msg = str(e)
        if 'AuthenticationFailed' in error_msg:
            return {
                'success': False,
                'message': 'Authentication failed. Check account key or SAS token.',
                'tables': []
            }
        elif 'ContainerNotFound' in error_msg:
            return {
                'success': False,
                'message': f'Container not found: {container_name}',
                'tables': []
            }
        else:
            return {
                'success': False,
                'message': f'Azure Blob error: {error_msg}',
                'tables': []
            }
    except Exception as e:
        return {
            'success': False,
            'message': f'Azure Blob connection failed: {str(e)}',
            'tables': []
        }


# ============================================================================
# Schema Fetching Functions
# ============================================================================

def fetch_schemas(source_type, connection_params):
    """
    Fetch available schemas for a given connection.

    Args:
        source_type (str): Type of data source ('postgresql', 'mysql', 'bigquery', etc.)
        connection_params (dict): Connection parameters

    Returns:
        dict: {
            'success': True/False,
            'message': 'Success message' or error details,
            'schemas': ['public', 'analytics', 'staging', ...]
        }
    """
    if source_type == 'postgresql':
        return fetch_schemas_postgresql(**connection_params)
    elif source_type == 'mysql':
        return fetch_schemas_mysql(**connection_params)
    elif source_type == 'bigquery':
        return fetch_schemas_bigquery(**connection_params)
    else:
        # For databases without schema support, return a default schema
        return {
            'success': True,
            'message': 'Schema not applicable for this database type',
            'schemas': ['default']
        }


def fetch_schemas_postgresql(host, port, database, username, password, timeout=10, **kwargs):
    """
    Fetch all schemas from a PostgreSQL database.

    Returns:
        dict: List of schema names
    """
    conn = None
    cursor = None

    try:
        conn = psycopg2.connect(
            host=host,
            port=port or 5432,
            database=database,
            user=username,
            password=password,
            connect_timeout=timeout
        )

        cursor = conn.cursor()

        # Fetch all schemas excluding system schemas
        cursor.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY schema_name
        """)

        schemas = [row[0] for row in cursor.fetchall()]

        return {
            'success': True,
            'message': f'Found {len(schemas)} schemas',
            'schemas': schemas
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching schemas: {str(e)}',
            'schemas': []
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def fetch_schemas_mysql(host, port, database, username, password, timeout=10, **kwargs):
    """
    Fetch schemas from MySQL (in MySQL, database = schema).
    For MySQL, we just return the current database as the only schema.

    Returns:
        dict: Single schema (the database itself)
    """
    return {
        'success': True,
        'message': 'MySQL uses database as schema',
        'schemas': [database]  # In MySQL, database IS the schema
    }


def fetch_schemas_bigquery(project_id, dataset, service_account_json, **kwargs):
    """
    Fetch datasets from BigQuery (datasets act as schemas).

    Returns:
        dict: List of dataset names
    """
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        # Parse service account JSON
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json)
        )

        client = bigquery.Client(
            credentials=credentials,
            project=project_id
        )

        # List all datasets
        datasets = list(client.list_datasets())
        schema_names = [d.dataset_id for d in datasets]

        return {
            'success': True,
            'message': f'Found {len(schema_names)} datasets',
            'schemas': schema_names
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching BigQuery datasets: {str(e)}',
            'schemas': []
        }


def fetch_tables_for_schema(source_type, schema_name, connection_params):
    """
    Fetch tables for a specific schema.

    Args:
        source_type (str): Type of data source
        schema_name (str): Schema to fetch tables from
        connection_params (dict): Connection parameters

    Returns:
        dict: {
            'success': True/False,
            'message': 'Success message' or error,
            'tables': [{'name': 'table1', 'row_count': 1000, 'last_updated': '2025-11-12'}, ...]
        }
    """
    if source_type == 'postgresql':
        return fetch_tables_postgresql(schema_name, **connection_params)
    elif source_type == 'mysql':
        return fetch_tables_mysql(schema_name, **connection_params)
    elif source_type == 'bigquery':
        return fetch_tables_bigquery(schema_name, **connection_params)
    else:
        return {
            'success': False,
            'message': f'Database type "{source_type}" not yet implemented',
            'tables': []
        }


def fetch_tables_postgresql(schema_name, host, port, database, username, password, timeout=10, **kwargs):
    """
    Fetch tables from a specific PostgreSQL schema.
    """
    conn = None
    cursor = None

    try:
        conn = psycopg2.connect(
            host=host,
            port=port or 5432,
            database=database,
            user=username,
            password=password,
            connect_timeout=timeout
        )

        cursor = conn.cursor()

        # Fetch tables from specific schema
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """, (schema_name,))

        tables = []
        for row in cursor.fetchall():
            table_name = row[0]

            # Get row count
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.{table_name}")
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = None

            # Get last modified time
            try:
                cursor.execute(f"""
                    SELECT pg_stat_get_last_analyze_time(c.oid) as last_updated
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = %s
                    AND n.nspname = %s
                """, (table_name, schema_name))
                result = cursor.fetchone()
                last_updated = result[0].strftime('%Y-%m-%d %H:%M:%S') if result and result[0] else None
            except Exception:
                last_updated = None

            tables.append({
                'name': table_name,
                'row_count': row_count,
                'last_updated': last_updated or 'Unknown'
            })

        return {
            'success': True,
            'message': f'Found {len(tables)} tables in schema "{schema_name}"',
            'tables': tables
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching tables: {str(e)}',
            'tables': []
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def fetch_tables_mysql(schema_name, host, port, database, username, password, timeout=10, **kwargs):
    """
    Fetch tables from MySQL database (schema_name is the database name).
    """
    conn = None
    cursor = None

    try:
        conn = pymysql.connect(
            host=host,
            port=port or 3306,
            database=schema_name,  # Use schema_name as database
            user=username,
            password=password,
            connect_timeout=timeout
        )

        cursor = conn.cursor()

        # Fetch all tables
        cursor.execute("SHOW TABLES")

        tables = []
        for row in cursor.fetchall():
            table_name = row[0]

            # Get row count
            try:
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = None

            # Get last modified time
            try:
                cursor.execute(f"""
                    SELECT UPDATE_TIME
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                """, (schema_name, table_name))
                result = cursor.fetchone()
                last_updated = result[0].strftime('%Y-%m-%d %H:%M:%S') if result and result[0] else None
            except Exception:
                last_updated = None

            tables.append({
                'name': table_name,
                'row_count': row_count,
                'last_updated': last_updated or 'Unknown'
            })

        return {
            'success': True,
            'message': f'Found {len(tables)} tables in database "{schema_name}"',
            'tables': tables
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching tables: {str(e)}',
            'tables': []
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def fetch_tables_bigquery(dataset_name, project_id, service_account_json, **kwargs):
    """
    Fetch tables from a specific BigQuery dataset.
    """
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json)
        )

        client = bigquery.Client(
            credentials=credentials,
            project=project_id
        )

        # List tables in dataset
        dataset_ref = client.dataset(dataset_name)
        tables_list = list(client.list_tables(dataset_ref))

        tables = []
        for table_item in tables_list:
            table_ref = dataset_ref.table(table_item.table_id)
            table = client.get_table(table_ref)

            tables.append({
                'name': table.table_id,
                'row_count': table.num_rows,
                'last_updated': table.modified.strftime('%Y-%m-%d %H:%M:%S') if table.modified else 'Unknown'
            })

        return {
            'success': True,
            'message': f'Found {len(tables)} tables in dataset "{dataset_name}"',
            'tables': tables
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching BigQuery tables: {str(e)}',
            'tables': []
        }


# ============================================================================
# Table Metadata & Preview Functions
# ============================================================================

def fetch_table_metadata(source_type, schema_name, table_name, connection_params):
    """
    Fetch detailed table metadata including column information and sample data.
    NOW ENHANCED: Includes BigQuery type mapping for each column.

    Args:
        source_type (str): Type of data source ('postgresql', 'mysql', etc.)
        schema_name (str): Schema name
        table_name (str): Table name
        connection_params (dict): Connection parameters

    Returns:
        dict: {
            'success': True/False,
            'message': 'Success message' or error,
            'columns': [
                {
                    'name': 'id',
                    'type': 'INTEGER',
                    'nullable': False,
                    'is_primary_key': True,
                    'is_timestamp': False,
                    'sample_values': [1, 2, 3, 4, 5],
                    'bigquery_type': 'INT64',  # NEW
                    'bigquery_mode': 'REQUIRED',  # NEW
                    'confidence': 'high',  # NEW
                    'warning': None  # NEW
                },
                ...
            ],
            'total_rows': 1234567,
            'recommended': {
                'timestamp_column': 'created_at',
                'primary_key': 'id'
            }
        }
    """
    # Import SchemaMapper for BigQuery type mapping
    from .schema_mapper import SchemaMapper

    # Fetch metadata from source database
    if source_type == 'postgresql':
        result = fetch_table_metadata_postgresql(schema_name, table_name, **connection_params)
    elif source_type == 'mysql':
        result = fetch_table_metadata_mysql(schema_name, table_name, **connection_params)
    elif source_type == 'bigquery':
        result = fetch_table_metadata_bigquery(schema_name, table_name, **connection_params)
    else:
        return {
            'success': False,
            'message': f'Table metadata not implemented for {source_type}',
            'columns': [],
            'total_rows': 0
        }

    if not result['success']:
        return result

    # ENHANCEMENT: Map each column to BigQuery type
    mapped_columns = []
    for col in result['columns']:
        # Map column using SchemaMapper
        mapped_col = SchemaMapper.map_column(
            source_type=source_type,
            column_name=col['name'],
            column_type=col['type'],
            nullable=col['nullable'],
            sample_values=col.get('sample_values', [])
        )

        # Merge with existing column info
        mapped_col.update({
            'is_primary_key': col.get('is_primary_key', False),
            'is_timestamp': col.get('is_timestamp', False),
            'sample_values': col.get('sample_values', [])
        })

        mapped_columns.append(mapped_col)

    # Replace columns with mapped versions
    result['columns'] = mapped_columns

    return result


def fetch_table_metadata_postgresql(schema_name, table_name, host, port, database, username, password, timeout=10, **kwargs):
    """
    Fetch table metadata for PostgreSQL.
    """
    conn = None
    cursor = None

    try:
        conn = psycopg2.connect(
            host=host,
            port=port or 5432,
            database=database,
            user=username,
            password=password,
            connect_timeout=timeout
        )

        cursor = conn.cursor()

        # Get column metadata
        cursor.execute("""
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                CASE
                    WHEN pk.column_name IS NOT NULL THEN true
                    ELSE false
                END as is_primary_key
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                    AND tc.table_schema = ku.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema = %s
                    AND tc.table_name = %s
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_schema = %s
                AND c.table_name = %s
            ORDER BY c.ordinal_position
        """, (schema_name, table_name, schema_name, table_name))

        columns = []
        timestamp_columns = []
        primary_key = None

        for row in cursor.fetchall():
            column_name = row[0]
            data_type = row[1].upper()
            nullable = row[2] == 'YES'
            is_pk = row[3]

            # Detect timestamp columns
            is_timestamp = any(ts_type in data_type for ts_type in ['TIMESTAMP', 'DATE', 'TIME'])
            if is_timestamp:
                timestamp_columns.append(column_name)

            if is_pk:
                primary_key = column_name

            # Get sample values
            try:
                cursor.execute(f"SELECT {column_name} FROM {schema_name}.{table_name} LIMIT 5")
                sample_values = [str(r[0]) if r[0] is not None else 'NULL' for r in cursor.fetchall()]
            except Exception:
                sample_values = []

            columns.append({
                'name': column_name,
                'type': data_type,
                'nullable': nullable,
                'is_primary_key': is_pk,
                'is_timestamp': is_timestamp,
                'sample_values': sample_values
            })

        # Get total row count
        cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.{table_name}")
        total_rows = cursor.fetchone()[0]

        # Recommend timestamp column (prefer created_at, then updated_at, then any timestamp)
        recommended_timestamp = None
        for col in ['created_at', 'createdat', 'created', 'timestamp', 'date']:
            if col in [c.lower() for c in timestamp_columns]:
                recommended_timestamp = next(c for c in timestamp_columns if c.lower() == col)
                break
        if not recommended_timestamp and timestamp_columns:
            recommended_timestamp = timestamp_columns[0]

        return {
            'success': True,
            'message': f'Fetched metadata for {schema_name}.{table_name}',
            'columns': columns,
            'total_rows': total_rows,
            'recommended': {
                'timestamp_column': recommended_timestamp,
                'primary_key': primary_key
            }
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching table metadata: {str(e)}',
            'columns': [],
            'total_rows': 0
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def fetch_table_metadata_mysql(schema_name, table_name, host, port, database, username, password, timeout=10, **kwargs):
    """
    Fetch table metadata for MySQL.
    """
    conn = None
    cursor = None

    try:
        conn = pymysql.connect(
            host=host,
            port=port or 3306,
            database=schema_name,
            user=username,
            password=password,
            connect_timeout=timeout
        )

        cursor = conn.cursor()

        # Get column metadata
        cursor.execute("""
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_KEY
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
                AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (schema_name, table_name))

        columns = []
        timestamp_columns = []
        primary_key = None

        for row in cursor.fetchall():
            column_name = row[0]
            data_type = row[1].upper()
            nullable = row[2] == 'YES'
            is_pk = row[3] == 'PRI'

            # Detect timestamp columns
            is_timestamp = any(ts_type in data_type for ts_type in ['TIMESTAMP', 'DATETIME', 'DATE', 'TIME'])
            if is_timestamp:
                timestamp_columns.append(column_name)

            if is_pk:
                primary_key = column_name

            # Get sample values
            try:
                cursor.execute(f"SELECT `{column_name}` FROM `{table_name}` LIMIT 5")
                sample_values = [str(r[0]) if r[0] is not None else 'NULL' for r in cursor.fetchall()]
            except Exception:
                sample_values = []

            columns.append({
                'name': column_name,
                'type': data_type,
                'nullable': nullable,
                'is_primary_key': is_pk,
                'is_timestamp': is_timestamp,
                'sample_values': sample_values
            })

        # Get total row count
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        total_rows = cursor.fetchone()[0]

        # Recommend timestamp column
        recommended_timestamp = None
        for col in ['created_at', 'createdat', 'created', 'timestamp', 'date']:
            if col in [c.lower() for c in timestamp_columns]:
                recommended_timestamp = next(c for c in timestamp_columns if c.lower() == col)
                break
        if not recommended_timestamp and timestamp_columns:
            recommended_timestamp = timestamp_columns[0]

        return {
            'success': True,
            'message': f'Fetched metadata for {schema_name}.{table_name}',
            'columns': columns,
            'total_rows': total_rows,
            'recommended': {
                'timestamp_column': recommended_timestamp,
                'primary_key': primary_key
            }
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching table metadata: {str(e)}',
            'columns': [],
            'total_rows': 0
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def fetch_table_metadata_bigquery(dataset_name, table_name, project_id, service_account_json, **kwargs):
    """
    Fetch table metadata for BigQuery.
    """
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json)
        )

        client = bigquery.Client(
            credentials=credentials,
            project=project_id
        )

        # Get table reference
        dataset_ref = client.dataset(dataset_name)
        table_ref = dataset_ref.table(table_name)
        table = client.get_table(table_ref)

        columns = []
        timestamp_columns = []
        primary_key = None

        # Get column metadata
        for field in table.schema:
            is_timestamp = field.field_type in ['TIMESTAMP', 'DATETIME', 'DATE', 'TIME']
            if is_timestamp:
                timestamp_columns.append(field.name)

            # Get sample values
            try:
                query = f"SELECT {field.name} FROM `{project_id}.{dataset_name}.{table_name}` LIMIT 5"
                query_job = client.query(query)
                results = query_job.result()
                sample_values = [str(row[0]) if row[0] is not None else 'NULL' for row in results]
            except Exception:
                sample_values = []

            columns.append({
                'name': field.name,
                'type': field.field_type,
                'nullable': field.mode != 'REQUIRED',
                'is_primary_key': False,  # BigQuery doesn't have primary keys
                'is_timestamp': is_timestamp,
                'sample_values': sample_values
            })

        # Recommend timestamp column
        recommended_timestamp = None
        for col in ['created_at', 'createdat', 'created', 'timestamp', 'date']:
            if col in [c.lower() for c in timestamp_columns]:
                recommended_timestamp = next(c for c in timestamp_columns if c.lower() == col)
                break
        if not recommended_timestamp and timestamp_columns:
            recommended_timestamp = timestamp_columns[0]

        return {
            'success': True,
            'message': f'Fetched metadata for {dataset_name}.{table_name}',
            'columns': columns,
            'total_rows': table.num_rows,
            'recommended': {
                'timestamp_column': recommended_timestamp,
                'primary_key': None  # BigQuery doesn't have PKs
            }
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error fetching BigQuery table metadata: {str(e)}',
            'columns': [],
            'total_rows': 0
        }
