"""
BigQuery Schema Mapper
Maps source database types to BigQuery types with smart detection.
"""

import re
from typing import List, Dict, Any, Optional
from google.cloud import bigquery


class SchemaMapper:
    """Maps source database types to BigQuery types"""

    # PostgreSQL → BigQuery type mapping
    POSTGRES_TYPE_MAP = {
        # Integer types
        'smallint': 'INT64',
        'integer': 'INT64',
        'int': 'INT64',
        'bigint': 'INT64',
        'smallserial': 'INT64',
        'serial': 'INT64',
        'bigserial': 'INT64',

        # Numeric types
        'decimal': 'NUMERIC',
        'numeric': 'NUMERIC',
        'real': 'FLOAT64',
        'double precision': 'FLOAT64',
        'money': 'NUMERIC',

        # String types
        'character varying': 'STRING',
        'varchar': 'STRING',
        'character': 'STRING',
        'char': 'STRING',
        'text': 'STRING',

        # Boolean
        'boolean': 'BOOL',
        'bool': 'BOOL',

        # Date/Time types
        'date': 'DATE',
        'timestamp': 'TIMESTAMP',
        'timestamp without time zone': 'TIMESTAMP',
        'timestamp with time zone': 'TIMESTAMP',
        'timestamptz': 'TIMESTAMP',
        'time': 'TIME',
        'time without time zone': 'TIME',
        'time with time zone': 'TIME',
        'interval': 'STRING',  # No direct equivalent

        # JSON
        'json': 'JSON',
        'jsonb': 'JSON',

        # Other types
        'uuid': 'STRING',
        'bytea': 'BYTES',
        'inet': 'STRING',
        'cidr': 'STRING',
        'macaddr': 'STRING',
        'point': 'GEOGRAPHY',
        'geography': 'GEOGRAPHY',
    }

    # MySQL → BigQuery type mapping
    MYSQL_TYPE_MAP = {
        # Integer types
        'tinyint': 'INT64',
        'smallint': 'INT64',
        'mediumint': 'INT64',
        'int': 'INT64',
        'integer': 'INT64',
        'bigint': 'INT64',

        # Numeric types
        'float': 'FLOAT64',
        'double': 'FLOAT64',
        'decimal': 'NUMERIC',
        'numeric': 'NUMERIC',

        # String types
        'varchar': 'STRING',
        'char': 'STRING',
        'text': 'STRING',
        'tinytext': 'STRING',
        'mediumtext': 'STRING',
        'longtext': 'STRING',
        'enum': 'STRING',
        'set': 'STRING',

        # Boolean (MySQL uses TINYINT(1))
        'boolean': 'BOOL',
        'bool': 'BOOL',

        # Date/Time types
        'date': 'DATE',
        'datetime': 'DATETIME',
        'timestamp': 'TIMESTAMP',
        'time': 'TIME',
        'year': 'INT64',

        # JSON
        'json': 'JSON',

        # Binary types
        'binary': 'BYTES',
        'varbinary': 'BYTES',
        'blob': 'BYTES',
        'tinyblob': 'BYTES',
        'mediumblob': 'BYTES',
        'longblob': 'BYTES',
    }

    # BigQuery type choices for dropdown
    BIGQUERY_TYPES = [
        'STRING',
        'INT64',
        'FLOAT64',
        'NUMERIC',
        'BIGNUMERIC',
        'BOOL',
        'DATE',
        'DATETIME',
        'TIMESTAMP',
        'TIME',
        'JSON',
        'BYTES',
        'GEOGRAPHY',
    ]

    @classmethod
    def map_column(
        cls,
        source_type: str,
        column_name: str,
        column_type: str,
        nullable: bool,
        sample_values: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Map a single column from source to BigQuery.

        Args:
            source_type: 'postgresql' or 'mysql'
            column_name: Name of the column
            column_type: Source database type (e.g., 'varchar(50)', 'timestamp')
            nullable: Whether column allows NULL
            sample_values: Sample values for smart detection

        Returns:
            {
                'name': column_name,
                'source_type': 'varchar(50)',
                'bigquery_type': 'STRING',
                'bigquery_mode': 'NULLABLE',
                'confidence': 'high',
                'warning': None or warning message,
                'auto_detected': True/False
            }
        """
        # Normalize column type
        col_type_lower = column_type.lower().strip()

        # Extract base type (remove length/precision)
        base_type = col_type_lower.split('(')[0].strip()

        # Get type map
        type_map = (
            cls.POSTGRES_TYPE_MAP if source_type == 'postgresql'
            else cls.MYSQL_TYPE_MAP
        )

        # Special case: MySQL TINYINT(1) → BOOL
        if source_type == 'mysql' and 'tinyint(1)' in col_type_lower:
            bigquery_type = 'BOOL'
            confidence = 'high'
            warning = None
        else:
            # Get mapped type or default to STRING
            bigquery_type = type_map.get(base_type, 'STRING')
            confidence = 'high' if base_type in type_map else 'medium'
            warning = None

        # Smart detection based on sample values
        if sample_values and bigquery_type == 'STRING':
            detection = cls._smart_type_detection(column_name, sample_values)
            if detection:
                bigquery_type = detection['suggested_type']
                confidence = 'medium'
                warning = detection['warning']

        # Check for large text fields
        if base_type in ('text', 'mediumtext', 'longtext', 'blob', 'mediumblob', 'longblob'):
            warning = 'Large TEXT/BLOB field - may impact query performance. Consider excluding if not needed.'
            confidence = 'medium'

        # Determine mode (REQUIRED vs NULLABLE)
        bigquery_mode = 'NULLABLE' if nullable else 'REQUIRED'

        return {
            'name': column_name,
            'source_type': column_type,
            'bigquery_type': bigquery_type,
            'bigquery_mode': bigquery_mode,
            'confidence': confidence,
            'warning': warning,
            'auto_detected': True
        }

    @classmethod
    def _smart_type_detection(
        cls,
        column_name: str,
        sample_values: List[Any]
    ) -> Optional[Dict[str, str]]:
        """
        Detect if STRING column should be a different type based on:
        1. Column name patterns
        2. Sample value patterns

        Returns:
            {'suggested_type': 'DATE', 'warning': '...'} or None
        """
        # Filter out None/empty values
        values = [v for v in sample_values[:20] if v]

        if not values:
            return None

        # Pattern 1: Date-like column names
        date_name_patterns = [
            r'.*_date$', r'.*_dt$', r'date_.*',
            r'created', r'updated', r'modified',
            r'.*_on$', r'.*_at$'
        ]

        for pattern in date_name_patterns:
            if re.match(pattern, column_name.lower()):
                # Check if values look like dates
                if cls._looks_like_date(values):
                    return {
                        'suggested_type': 'DATE',
                        'warning': 'Auto-detected: Column name and values suggest DATE type'
                    }
                elif cls._looks_like_timestamp(values):
                    return {
                        'suggested_type': 'TIMESTAMP',
                        'warning': 'Auto-detected: Column name and values suggest TIMESTAMP type'
                    }

        # Pattern 2: Numeric strings
        if cls._looks_like_integer(values):
            return {
                'suggested_type': 'INT64',
                'warning': 'Auto-detected: All values are integers stored as strings'
            }

        if cls._looks_like_float(values):
            return {
                'suggested_type': 'FLOAT64',
                'warning': 'Auto-detected: All values are decimals stored as strings'
            }

        # Pattern 3: Boolean strings
        if cls._looks_like_boolean(values):
            return {
                'suggested_type': 'BOOL',
                'warning': 'Auto-detected: Values appear to be boolean (true/false, yes/no, 0/1)'
            }

        return None

    @staticmethod
    def _looks_like_date(values: List[Any]) -> bool:
        """Check if values match DATE pattern (YYYY-MM-DD)"""
        date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        matches = sum(1 for v in values if re.match(date_pattern, str(v)))
        return matches > len(values) * 0.8  # 80% threshold

    @staticmethod
    def _looks_like_timestamp(values: List[Any]) -> bool:
        """Check if values match TIMESTAMP pattern"""
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}'
        matches = sum(1 for v in values if re.match(timestamp_pattern, str(v)))
        return matches > len(values) * 0.8

    @staticmethod
    def _looks_like_integer(values: List[Any]) -> bool:
        """Check if all values are integers"""
        try:
            for v in values:
                int(v)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _looks_like_float(values: List[Any]) -> bool:
        """Check if all values are floats"""
        try:
            for v in values:
                float(v)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _looks_like_boolean(values: List[Any]) -> bool:
        """Check if values are boolean-like"""
        bool_values = {
            'true', 'false', 'yes', 'no',
            '0', '1', 't', 'f', 'y', 'n'
        }
        matches = sum(1 for v in values if str(v).lower() in bool_values)
        return matches > len(values) * 0.9

    @classmethod
    def generate_bigquery_schema(cls, columns_metadata: List[Dict]) -> List[bigquery.SchemaField]:
        """
        Generate BigQuery schema from column metadata.

        Args:
            columns_metadata: List of dicts with name, bigquery_type, bigquery_mode

        Returns:
            List of BigQuery SchemaField objects
        """
        schema = []
        for col in columns_metadata:
            schema.append(bigquery.SchemaField(
                name=col['name'],
                field_type=col['bigquery_type'],
                mode=col['bigquery_mode'],
                description=f"Source: {col.get('source_type', 'unknown')}"
            ))

        return schema
