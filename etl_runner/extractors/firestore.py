"""
Firestore Extractor

Extracts data from Google Cloud Firestore (NoSQL document database).
Converts documents to flat dictionaries with nested fields stored as JSON strings.
"""

from typing import Generator, List, Dict, Any, Optional
import pandas as pd
import logging
import json
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
from .base import BaseExtractor

# Import Firestore's special datetime type for explicit handling
try:
    from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
except ImportError:
    # Fallback if import path changes in future versions
    DatetimeWithNanoseconds = None

logger = logging.getLogger(__name__)


class FirestoreExtractor(BaseExtractor):
    """Extractor for Firestore collections"""

    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize Firestore extractor.

        Args:
            connection_params: Dictionary with connection details
                - project_id: GCP project ID
                - credentials: Service account JSON credentials
        """
        super().__init__(connection_params)

        self.project_id = connection_params.get('project_id') or connection_params.get('bigquery_project')

        # Initialize Firestore client
        self._db = None
        self._init_client()

        logger.info(f"Initialized Firestore extractor for project: {self.project_id}")

    def _init_client(self):
        """Initialize Firestore client with credentials"""
        credentials_dict = self.connection_params.get('credentials', {})
        service_account_json = credentials_dict.get('service_account_json', '')

        if not service_account_json:
            raise ValueError("Service account JSON is required for Firestore connection")

        try:
            credentials_info = json.loads(service_account_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_info)
            self._db = firestore.Client(
                project=self.project_id,
                credentials=credentials
            )
            logger.info(f"Initialized Firestore client for project: {self.project_id}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse service account JSON: {e}")
            raise ValueError(f"Invalid service account credentials: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the Firestore connection by listing collections.

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        try:
            # Try to list collections
            collections = list(self._db.collections())
            collection_count = len(collections)

            return {
                'success': True,
                'message': f'Connected successfully to Firestore project "{self.project_id}". Found {collection_count} collections.'
            }
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {
                'success': False,
                'message': f'Connection failed: {str(e)}'
            }

    def _sanitize_for_dataframe(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Final sanitization pass to ensure all values are DataFrame-safe primitives.
        Catches any complex objects that might have slipped through flattening.

        Args:
            rows: List of row dictionaries

        Returns:
            Sanitized list of row dictionaries with only primitive types
        """
        sanitized_rows = []

        for row in rows:
            sanitized_row = {}
            for key, value in row.items():
                # Only allow primitive types that Pandas/PyArrow can handle
                if value is None or isinstance(value, (str, int, float, bool)):
                    sanitized_row[key] = value
                else:
                    # Force convert to string
                    logger.warning(f"Complex object detected in DataFrame creation: field={key}, type={type(value).__name__}. Converting to string.")
                    sanitized_row[key] = str(value)

            sanitized_rows.append(sanitized_row)

        return sanitized_rows

    def _flatten_document(self, doc: firestore.DocumentSnapshot, selected_columns: List[str] = None) -> Dict[str, Any]:
        """
        Flatten a Firestore document to a dictionary suitable for BigQuery.

        Strategy:
        - Simple fields (string, int, float, bool, timestamp) → kept as-is
        - Nested objects (dict) → converted to JSON string
        - Arrays (list) → converted to JSON string
        - Add document_id and _extracted_at metadata fields

        Args:
            doc: Firestore DocumentSnapshot
            selected_columns: Optional list of columns to include (None = all)

        Returns:
            Flattened dictionary
        """
        flat_doc = {}

        # Always include document_id
        flat_doc['document_id'] = doc.id

        # Get document fields
        doc_dict = doc.to_dict()

        # If no columns selected, use all
        if not selected_columns or len(selected_columns) == 0:
            selected_columns = list(doc_dict.keys())

        # Process each field
        for field_name in selected_columns:
            # Skip document_id if user selected it (we already added it)
            if field_name == 'document_id':
                continue

            field_value = doc_dict.get(field_name)

            if field_value is None:
                flat_doc[field_name] = None

            elif isinstance(field_value, (str, int, float, bool)):
                # Simple types - keep as-is
                flat_doc[field_name] = field_value

            elif isinstance(field_value, (list, dict)):
                # Nested structures - convert to JSON string
                flat_doc[field_name] = json.dumps(field_value)

            elif isinstance(field_value, datetime):
                # CRITICAL FIX: Handle datetime types carefully
                # Firestore's DatetimeWithNanoseconds inherits from datetime but
                # its isoformat() may not return a pure Python string.
                # Use strftime() to guarantee a pure string output.
                field_type = type(field_value).__name__

                # Check if it's Firestore's special DatetimeWithNanoseconds
                if DatetimeWithNanoseconds is not None and isinstance(field_value, DatetimeWithNanoseconds):
                    logger.debug(f"Converting DatetimeWithNanoseconds field '{field_name}'")
                    # Use strftime to get a pure Python string (not a datetime-like object)
                    flat_doc[field_name] = field_value.strftime('%Y-%m-%dT%H:%M:%S.%f')
                elif field_type == 'DatetimeWithNanoseconds':
                    # Fallback check by class name if import failed
                    logger.debug(f"Converting DatetimeWithNanoseconds field '{field_name}' (by name)")
                    flat_doc[field_name] = field_value.strftime('%Y-%m-%dT%H:%M:%S.%f')
                else:
                    # Regular Python datetime - strftime is safer than isoformat
                    logger.debug(f"Converting datetime field '{field_name}': type={field_type}")
                    flat_doc[field_name] = field_value.strftime('%Y-%m-%dT%H:%M:%S.%f')

            else:
                # Fallback for unknown types (Firestore protobuf timestamps, GeoPoints, etc.)
                # Try to convert to datetime first, then to string
                try:
                    field_type = type(field_value).__name__

                    # Check if it has a timestamp-like interface (protobuf Timestamp)
                    if hasattr(field_value, 'seconds') and hasattr(field_value, 'nanos'):
                        # Firestore Timestamp object (google.protobuf.timestamp_pb2.Timestamp)
                        logger.debug(f"Converting protobuf Timestamp field '{field_name}': type={field_type}")
                        ts = datetime.utcfromtimestamp(field_value.seconds + field_value.nanos / 1e9)
                        # Use strftime to ensure pure string output
                        flat_doc[field_name] = ts.strftime('%Y-%m-%dT%H:%M:%S.%f')
                    elif hasattr(field_value, 'isoformat'):
                        # Has isoformat method (datetime-like) - wrap with str() to be safe
                        logger.debug(f"Converting datetime-like field '{field_name}': type={field_type}")
                        flat_doc[field_name] = str(field_value.isoformat())
                    else:
                        # Convert to string as last resort
                        logger.warning(f"Unknown field type for '{field_name}': {field_type}, converting to string")
                        flat_doc[field_name] = str(field_value)
                except Exception as e:
                    # If all else fails, convert to string
                    logger.warning(f"Failed to convert field '{field_name}' of type {type(field_value)}: {e}. Using string representation.")
                    flat_doc[field_name] = str(field_value)

        # Add extraction timestamp (use strftime for consistent pure string output)
        flat_doc['_extracted_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')

        return flat_doc

    def extract_full(
        self,
        table_name: str,
        schema_name: str,
        selected_columns: List[str],
        batch_size: int = 10000
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Extract all documents from a Firestore collection (full snapshot).

        Args:
            table_name: Firestore collection name
            schema_name: Not used for Firestore (no schema concept)
            selected_columns: List of field names to extract (empty = all fields)
            batch_size: Number of documents to batch before yielding (default: 10000)

        Yields:
            pandas DataFrame containing batches of flattened documents
        """
        collection_ref = self._db.collection(table_name)

        logger.info(f"Starting full extraction from Firestore collection: {table_name}")

        try:
            # Stream all documents
            batch_num = 0
            rows_buffer = []

            for doc in collection_ref.stream():
                # Flatten document
                try:
                    flat_doc = self._flatten_document(doc, selected_columns)
                    rows_buffer.append(flat_doc)
                except Exception as e:
                    # Log error but continue processing other documents
                    logger.warning(f"Failed to flatten document {doc.id}: {str(e)}. Skipping.")
                    continue

                # Yield batch when buffer is full
                if len(rows_buffer) >= batch_size:
                    batch_num += 1
                    # Sanitize before creating DataFrame to ensure all values are primitives
                    sanitized_rows = self._sanitize_for_dataframe(rows_buffer)
                    df = pd.DataFrame(sanitized_rows)

                    # Force convert any 'object' dtype columns to string to avoid PyArrow conversion errors
                    for col in df.select_dtypes(include=['object']).columns:
                        logger.info(f"Converting object column '{col}' to string dtype")
                        df[col] = df[col].astype(str)

                    logger.info(f"Extracted batch {batch_num}: {len(df)} documents")
                    yield df
                    rows_buffer = []

            # Yield remaining documents
            if rows_buffer:
                batch_num += 1
                # Sanitize before creating DataFrame
                sanitized_rows = self._sanitize_for_dataframe(rows_buffer)
                df = pd.DataFrame(sanitized_rows)

                # Force convert any 'object' dtype columns to string
                for col in df.select_dtypes(include=['object']).columns:
                    logger.info(f"Converting object column '{col}' to string dtype")
                    df[col] = df[col].astype(str)

                logger.info(f"Extracted final batch {batch_num}: {len(df)} documents")
                yield df

            logger.info(f"Completed full extraction from collection: {table_name}")

        except Exception as e:
            logger.error(f"Failed to extract from collection {table_name}: {str(e)}")
            raise

    def extract_incremental(
        self,
        table_name: str,
        schema_name: str,
        timestamp_column: str,
        since_datetime: str,
        selected_columns: List[str],
        batch_size: int = 10000
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Extract documents incrementally from Firestore using a timestamp field.

        NOTE: This requires:
        1. All documents must have the timestamp_column field
        2. The field must be indexed in Firestore
        3. Documents without the field will be skipped

        Args:
            table_name: Firestore collection name
            schema_name: Not used for Firestore
            timestamp_column: Field name to filter on (e.g., 'updated_at', 'created_at')
            since_datetime: Start datetime in ISO format (e.g., '2024-01-01T00:00:00')
            selected_columns: List of field names to extract
            batch_size: Number of documents per batch

        Yields:
            pandas DataFrame containing batches of flattened documents
        """
        collection_ref = self._db.collection(table_name)

        # Parse since_datetime to datetime object
        try:
            since_dt = datetime.fromisoformat(since_datetime.replace('Z', '+00:00'))
        except ValueError as e:
            logger.error(f"Invalid datetime format: {since_datetime}")
            raise ValueError(f"Invalid datetime format: {since_datetime}. Expected ISO format (e.g., '2024-01-01T00:00:00')")

        logger.info(f"Starting incremental extraction from collection: {table_name}")
        logger.info(f"Filter: {timestamp_column} > {since_datetime}")

        try:
            # Build query with timestamp filter
            # Note: This requires an index on the timestamp field in Firestore
            query = collection_ref.where(timestamp_column, '>', since_dt)

            # Stream filtered documents
            batch_num = 0
            rows_buffer = []
            skipped_count = 0

            for doc in query.stream():
                # Flatten document
                try:
                    flat_doc = self._flatten_document(doc, selected_columns)
                    rows_buffer.append(flat_doc)
                except Exception as e:
                    logger.warning(f"Failed to flatten document {doc.id}: {str(e)}. Skipping.")
                    skipped_count += 1
                    continue

                # Yield batch when buffer is full
                if len(rows_buffer) >= batch_size:
                    batch_num += 1
                    # Sanitize before creating DataFrame to ensure all values are primitives
                    sanitized_rows = self._sanitize_for_dataframe(rows_buffer)
                    df = pd.DataFrame(sanitized_rows)

                    # Force convert any 'object' dtype columns to string to avoid PyArrow conversion errors
                    for col in df.select_dtypes(include=['object']).columns:
                        logger.info(f"Converting object column '{col}' to string dtype")
                        df[col] = df[col].astype(str)

                    logger.info(f"Extracted batch {batch_num}: {len(df)} documents")
                    yield df
                    rows_buffer = []

            # Yield remaining documents
            if rows_buffer:
                batch_num += 1
                # Sanitize before creating DataFrame
                sanitized_rows = self._sanitize_for_dataframe(rows_buffer)
                df = pd.DataFrame(sanitized_rows)

                # Force convert any 'object' dtype columns to string
                for col in df.select_dtypes(include=['object']).columns:
                    logger.info(f"Converting object column '{col}' to string dtype")
                    df[col] = df[col].astype(str)

                logger.info(f"Extracted final batch {batch_num}: {len(df)} documents")
                yield df

            if skipped_count > 0:
                logger.warning(f"Skipped {skipped_count} documents due to flattening errors")

            logger.info(f"Completed incremental extraction from collection: {table_name}")

        except Exception as e:
            error_msg = str(e)

            # Provide helpful error message if index is missing
            if 'index' in error_msg.lower() or 'requires an index' in error_msg.lower():
                logger.error(f"Query requires an index on field '{timestamp_column}'. "
                           f"Create the index in Firestore console: "
                           f"https://console.cloud.google.com/firestore/indexes")
                raise ValueError(f"Firestore query requires an index on '{timestamp_column}'. "
                               f"Please create the index in Firestore console.")

            logger.error(f"Failed to extract from collection {table_name}: {error_msg}")
            raise

    def estimate_row_count(
        self,
        table_name: str,
        schema_name: str = None,
        timestamp_column: str = None,
        since_datetime: str = None
    ) -> int:
        """
        Estimate document count in a Firestore collection.

        Note: Firestore doesn't have a fast COUNT() operation.
        We estimate by sampling up to 1000 documents.

        Args:
            table_name: Collection name
            schema_name: Not used for Firestore
            timestamp_column: Optional timestamp column for filtered count
            since_datetime: Optional datetime for filtered count

        Returns:
            Estimated document count
        """
        try:
            collection_ref = self._db.collection(table_name)

            # Build query with optional filter
            if timestamp_column and since_datetime:
                try:
                    since_dt = datetime.fromisoformat(since_datetime.replace('Z', '+00:00'))
                    query = collection_ref.where(timestamp_column, '>', since_dt)
                except Exception as e:
                    logger.warning(f"Failed to parse datetime filter, estimating full collection: {e}")
                    query = collection_ref
            else:
                query = collection_ref

            # Sample up to 1000 documents
            docs = list(query.limit(1000).stream())
            doc_count = len(docs)

            if doc_count == 1000:
                # If we got exactly 1000, assume there are more
                # Return 999,999 to trigger Standard mode (< 1M threshold)
                logger.info(f"Collection {table_name}: sampled 1000 docs, assuming >= 1000 (returning 999,999)")
                return 999_999
            else:
                logger.info(f"Collection {table_name}: estimated {doc_count} documents")
                return doc_count

        except Exception as e:
            logger.warning(f"Failed to estimate row count for {table_name}: {str(e)}")
            return 0

    def get_row_count(
        self,
        table_name: str,
        schema_name: str,
        where_clause: Optional[str] = None
    ) -> int:
        """
        Get document count (alias for estimate_row_count for compatibility).

        Note: Firestore doesn't have an efficient COUNT operation.
        This returns an estimate based on sampling.

        Returns:
            Estimated document count
        """
        return self.estimate_row_count(table_name, schema_name)

    def close(self):
        """
        Close Firestore client.

        Note: Firestore client doesn't require explicit closing,
        but we implement this for consistency with other extractors.
        """
        logger.info("Firestore extractor closed")
        pass
