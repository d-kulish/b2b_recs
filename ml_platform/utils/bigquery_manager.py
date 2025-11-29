"""
BigQuery Table Manager
Handles BigQuery dataset and table creation with schema validation.
"""

from google.cloud import bigquery
from .schema_mapper import SchemaMapper
import logging

logger = logging.getLogger(__name__)


class BigQueryTableManager:
    """Manages BigQuery table creation and schema operations"""

    def __init__(self, project_id, dataset_id='raw_data', location='US'):
        self.client = bigquery.Client(project=project_id)
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.location = location

    def ensure_dataset_exists(self):
        """
        Create dataset if it doesn't exist.

        Returns:
            {'success': True/False, 'created': True/False, 'message': '...'}
        """
        dataset_ref = f"{self.project_id}.{self.dataset_id}"

        try:
            dataset = self.client.get_dataset(dataset_ref)
            return {
                'success': True,
                'created': False,
                'message': f'Dataset {self.dataset_id} already exists'
            }
        except Exception:
            # Dataset doesn't exist, create it
            try:
                dataset = bigquery.Dataset(dataset_ref)
                dataset.location = self.location
                dataset.description = "Raw data from ETL sources"

                # Set default table expiration (optional - commented out)
                # dataset.default_table_expiration_ms = 90 * 24 * 60 * 60 * 1000

                created_dataset = self.client.create_dataset(dataset)
                logger.info(f"Created dataset {self.dataset_id}")

                return {
                    'success': True,
                    'created': True,
                    'message': f'Created dataset {self.dataset_id}'
                }
            except Exception as e:
                logger.error(f"Failed to create dataset: {str(e)}")
                return {
                    'success': False,
                    'created': False,
                    'message': f'Failed to create dataset: {str(e)}'
                }

    def table_exists(self, table_name):
        """Check if table already exists"""
        table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"
        try:
            self.client.get_table(table_ref)
            return True
        except Exception:
            return False

    def create_table_from_schema(
        self,
        table_name,
        schema_columns,
        load_type='transactional',
        timestamp_column=None,
        description=None,
        overwrite=False
    ):
        """
        Create BigQuery table from schema specification.

        Args:
            table_name: Name of the table
            schema_columns: List of dicts with name, bigquery_type, bigquery_mode
            load_type: 'transactional' or 'catalog'
            timestamp_column: Column for partitioning (transactional only)
            description: Table description
            overwrite: If True, delete existing table first

        Returns:
            {'success': True/False, 'table_id': '...', 'message': '...'}
        """
        table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"

        # Check if table exists
        if self.table_exists(table_name):
            if overwrite:
                logger.warning(f"Deleting existing table {table_name}")
                self.client.delete_table(table_ref)
            else:
                return {
                    'success': False,
                    'message': f'Table {table_name} already exists. Choose a different name or delete the existing table.'
                }

        try:
            # Generate BigQuery schema
            schema = SchemaMapper.generate_bigquery_schema(schema_columns)

            # Create table
            table = bigquery.Table(table_ref, schema=schema)

            # Set description
            table.description = description or f"ETL source table ({load_type} load)"

            # Configure partitioning for transactional loads
            if load_type == 'transactional' and timestamp_column:
                # Verify timestamp column exists in schema
                ts_col = next((c for c in schema_columns if c['name'] == timestamp_column), None)

                if ts_col and ts_col['bigquery_type'] in ('TIMESTAMP', 'DATETIME', 'DATE'):
                    table.time_partitioning = bigquery.TimePartitioning(
                        type_=bigquery.TimePartitioningType.DAY,
                        field=timestamp_column,
                        expiration_ms=None,  # No automatic deletion
                    )

                    # Add clustering for query optimization
                    table.clustering_fields = [timestamp_column]

                    logger.info(f"Table will be partitioned by {timestamp_column}")
                else:
                    logger.warning(f"Timestamp column {timestamp_column} not found or invalid type for partitioning")

            # Create the table
            created_table = self.client.create_table(table)

            logger.info(f"Created table {table_name} with {len(schema)} columns")

            return {
                'success': True,
                'table_id': created_table.table_id,
                'full_table_id': f"{self.project_id}.{self.dataset_id}.{table_name}",
                'num_columns': len(schema),
                'partitioned': bool(load_type == 'transactional' and timestamp_column),
                'message': f'Table {table_name} created successfully'
            }

        except Exception as e:
            logger.error(f"Failed to create table {table_name}: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                'success': False,
                'message': f'Failed to create table: {str(e)}'
            }

    def validate_table_schema(self, table_name, expected_columns):
        """
        Validate that existing table schema matches expected schema.

        Returns:
            {
                'matches': True/False,
                'differences': [...],
                'message': '...'
            }
        """
        table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"

        try:
            table = self.client.get_table(table_ref)
            existing_schema = {field.name: field for field in table.schema}

            differences = []

            for col in expected_columns:
                col_name = col['name']

                if col_name not in existing_schema:
                    differences.append({
                        'column': col_name,
                        'issue': 'missing',
                        'expected': col['bigquery_type']
                    })
                else:
                    existing_field = existing_schema[col_name]
                    if existing_field.field_type != col['bigquery_type']:
                        differences.append({
                            'column': col_name,
                            'issue': 'type_mismatch',
                            'expected': col['bigquery_type'],
                            'actual': existing_field.field_type
                        })

            matches = len(differences) == 0

            return {
                'matches': matches,
                'differences': differences,
                'message': 'Schema matches' if matches else f'{len(differences)} differences found'
            }

        except Exception as e:
            return {
                'matches': False,
                'differences': [],
                'message': f'Table not found or error: {str(e)}'
            }

    def get_table_schema(self, table_name):
        """Get current table schema"""
        table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"
        try:
            table = self.client.get_table(table_ref)
            return {
                'success': True,
                'schema': [
                    {
                        'name': field.name,
                        'type': field.field_type,
                        'mode': field.mode,
                        'description': field.description
                    }
                    for field in table.schema
                ]
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }

    def list_tables(self):
        """
        List all tables in the dataset with metadata.

        Returns:
            {
                'success': True/False,
                'tables': [
                    {
                        'name': 'table_name',
                        'full_id': 'project.dataset.table',
                        'num_rows': 12345,
                        'num_bytes': 67890,
                        'created': '2025-01-01T00:00:00',
                        'modified': '2025-01-15T00:00:00',
                        'description': '...',
                        'load_type': 'transactional' or 'catalog' or 'unknown',
                        'partitioned': True/False,
                        'partition_field': 'field_name' or None
                    }
                ],
                'message': '...'
            }
        """
        try:
            dataset_ref = f"{self.project_id}.{self.dataset_id}"
            tables = list(self.client.list_tables(dataset_ref))

            result = []
            for table_item in tables:
                # Get full table details
                table = self.client.get_table(table_item.reference)

                # Determine load type from description or partitioning
                load_type = 'unknown'
                if table.description:
                    if 'transactional' in table.description.lower():
                        load_type = 'transactional'
                    elif 'catalog' in table.description.lower():
                        load_type = 'catalog'
                elif table.time_partitioning:
                    load_type = 'transactional'  # Partitioned tables are typically transactional

                result.append({
                    'name': table.table_id,
                    'full_id': f"{self.project_id}.{self.dataset_id}.{table.table_id}",
                    'num_rows': table.num_rows,
                    'num_bytes': table.num_bytes,
                    'created': table.created.isoformat() if table.created else None,
                    'modified': table.modified.isoformat() if table.modified else None,
                    'description': table.description,
                    'load_type': load_type,
                    'partitioned': table.time_partitioning is not None,
                    'partition_field': table.time_partitioning.field if table.time_partitioning else None
                })

            logger.info(f"Listed {len(result)} tables in {self.dataset_id}")

            return {
                'success': True,
                'tables': result,
                'message': f'Found {len(result)} tables'
            }

        except Exception as e:
            logger.error(f"Failed to list tables: {str(e)}")
            return {
                'success': False,
                'tables': [],
                'message': f'Failed to list tables: {str(e)}'
            }

    def get_table_metadata(self, table_name):
        """
        Get detailed metadata for a specific table including schema and partitioning info.

        Returns:
            {
                'success': True/False,
                'table': {
                    'name': 'table_name',
                    'full_id': 'project.dataset.table',
                    'num_rows': 12345,
                    'description': '...',
                    'load_type': 'transactional' or 'catalog' or 'unknown',
                    'partitioned': True/False,
                    'partition_field': 'field_name' or None,
                    'schema': [...]
                },
                'message': '...'
            }
        """
        table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"
        try:
            table = self.client.get_table(table_ref)

            # Determine load type
            load_type = 'unknown'
            if table.description:
                if 'transactional' in table.description.lower():
                    load_type = 'transactional'
                elif 'catalog' in table.description.lower():
                    load_type = 'catalog'
            elif table.time_partitioning:
                load_type = 'transactional'

            return {
                'success': True,
                'table': {
                    'name': table.table_id,
                    'full_id': f"{self.project_id}.{self.dataset_id}.{table.table_id}",
                    'num_rows': table.num_rows,
                    'description': table.description,
                    'load_type': load_type,
                    'partitioned': table.time_partitioning is not None,
                    'partition_field': table.time_partitioning.field if table.time_partitioning else None,
                    'schema': [
                        {
                            'name': field.name,
                            'type': field.field_type,
                            'mode': field.mode,
                            'description': field.description
                        }
                        for field in table.schema
                    ]
                },
                'message': 'Table metadata retrieved'
            }

        except Exception as e:
            logger.error(f"Failed to get table metadata: {str(e)}")
            return {
                'success': False,
                'table': None,
                'message': f'Failed to get table metadata: {str(e)}'
            }

    def add_columns_to_table(self, table_name, new_columns):
        """
        Add new columns to an existing table via ALTER TABLE.

        Args:
            table_name: Name of the table
            new_columns: List of dicts with name, bigquery_type, bigquery_mode

        Returns:
            {'success': True/False, 'added_columns': [...], 'message': '...'}
        """
        table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"

        try:
            table = self.client.get_table(table_ref)
            original_schema = list(table.schema)
            existing_column_names = {field.name for field in original_schema}

            # Filter to only truly new columns
            columns_to_add = [
                col for col in new_columns
                if col['name'] not in existing_column_names
            ]

            if not columns_to_add:
                return {
                    'success': True,
                    'added_columns': [],
                    'message': 'No new columns to add'
                }

            # Create new schema fields
            new_fields = []
            for col in columns_to_add:
                new_fields.append(bigquery.SchemaField(
                    name=col['name'],
                    field_type=col.get('bigquery_type', 'STRING'),
                    mode=col.get('bigquery_mode', 'NULLABLE'),
                    description=col.get('description', f"Added via ETL job")
                ))

            # Update table schema
            table.schema = original_schema + new_fields
            updated_table = self.client.update_table(table, ['schema'])

            added_names = [col['name'] for col in columns_to_add]
            logger.info(f"Added {len(added_names)} columns to {table_name}: {added_names}")

            return {
                'success': True,
                'added_columns': added_names,
                'message': f'Added {len(added_names)} columns: {", ".join(added_names)}'
            }

        except Exception as e:
            logger.error(f"Failed to add columns to {table_name}: {str(e)}")
            return {
                'success': False,
                'added_columns': [],
                'message': f'Failed to add columns: {str(e)}'
            }
