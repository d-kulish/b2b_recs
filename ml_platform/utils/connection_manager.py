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
from google.cloud import secretmanager
from google.api_core import exceptions as gcp_exceptions


# GCP Project ID (should match your project)
GCP_PROJECT_ID = "b2b-recs"


def test_and_fetch_metadata(source_type, connection_params):
    """
    Main entry point for testing connections and fetching metadata.

    Args:
        source_type (str): Type of data source ('postgresql', 'mysql', 'bigquery', etc.)
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
    Test BigQuery connection and fetch table metadata.

    Args:
        project_id (str): GCP project ID
        dataset (str): BigQuery dataset name
        service_account_json (str): Service account JSON key (as string)

    Returns:
        dict: Connection result with table metadata
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
        datasets = list(client.list_datasets())

        # Check if specified dataset exists
        dataset_ref = client.dataset(dataset)
        try:
            client.get_dataset(dataset_ref)
        except Exception:
            return {
                'success': False,
                'message': f'Dataset "{dataset}" not found in project "{project_id}"',
                'tables': []
            }

        # Fetch tables in the dataset
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
