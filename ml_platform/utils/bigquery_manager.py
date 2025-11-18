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
