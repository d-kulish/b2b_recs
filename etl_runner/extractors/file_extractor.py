"""
File Extractor for Cloud Storage Sources

Supports extracting data from files in:
- Google Cloud Storage (GCS)
- AWS S3
- Azure Blob Storage

File formats supported:
- CSV
- Parquet
- JSON/JSONL
"""

import logging
from typing import Generator, List, Dict, Any, Optional, Tuple
from datetime import datetime
import pandas as pd
import io
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class FileExtractor:
    """
    File extractor for cloud storage sources.

    Supports GCS, S3, and Azure Blob Storage with CSV, Parquet, and JSON formats.
    """

    def __init__(self, connection_params: Dict[str, Any], file_config: Dict[str, Any]):
        """
        Initialize the file extractor.

        Args:
            connection_params: Cloud storage connection details
                - source_type: 'gcs', 's3', or 'azure_blob'
                - bucket/container: Bucket or container name
                - credentials: Cloud-specific credentials
            file_config: File extraction configuration
                - file_path_prefix: Optional folder path
                - file_pattern: Glob pattern for matching files
                - file_format: 'csv', 'parquet', or 'json'
                - file_format_options: Format-specific options (delimiters, encoding, etc.)
                - selected_files: List of specific file paths to load
                - load_latest_only: Boolean for catalog mode
        """
        self.connection_params = connection_params
        self.file_config = file_config

        self.source_type = connection_params.get('source_type')
        self.bucket_name = connection_params.get('bucket') or connection_params.get('container')

        self.file_path_prefix = file_config.get('file_path_prefix', '')
        self.file_pattern = file_config.get('file_pattern', '*')
        self.file_format = file_config.get('file_format', 'csv')
        self.file_format_options = file_config.get('file_format_options', {})
        self.selected_files = file_config.get('selected_files', [])
        self.load_latest_only = file_config.get('load_latest_only', False)

        # Initialize cloud storage client
        self.storage_client = None
        self._init_storage_client()

        logger.info(f"Initialized FileExtractor: {self.source_type} / {self.bucket_name}")

    def _init_storage_client(self):
        """Initialize the appropriate cloud storage client."""
        if self.source_type == 'gcs':
            from google.cloud import storage
            from google.oauth2 import service_account

            # Extract service account credentials from connection params
            credentials_dict = self.connection_params.get('credentials', {})
            service_account_json = credentials_dict.get('service_account_json', '')

            if service_account_json:
                # Parse and use provided service account credentials
                try:
                    credentials_info = json.loads(service_account_json)
                    creds = service_account.Credentials.from_service_account_info(credentials_info)
                    project_id = credentials_info.get('project_id')
                    self.storage_client = storage.Client(credentials=creds, project=project_id)
                    logger.info(f"Initialized Google Cloud Storage client with service account (project: {project_id})")
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to parse service account JSON: {e}")
                    raise ValueError(f"Invalid service account credentials: {e}")
            else:
                # Fallback to default credentials (for backward compatibility)
                self.storage_client = storage.Client()
                logger.warning("No service account credentials provided, using default credentials")

        elif self.source_type == 's3':
            import boto3
            credentials_dict = self.connection_params.get('credentials', {})
            aws_access_key = credentials_dict.get('aws_access_key_id') or self.connection_params.get('aws_access_key_id')
            aws_secret_key = credentials_dict.get('aws_secret_access_key') or self.connection_params.get('aws_secret_access_key')
            region = self.connection_params.get('region', 'us-east-1')

            self.storage_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=region
            )
            logger.info(f"Initialized AWS S3 client (region: {region})")

        elif self.source_type == 'azure_blob':
            from azure.storage.blob import BlobServiceClient
            credentials_dict = self.connection_params.get('credentials', {})
            connection_string = credentials_dict.get('connection_string') or self.connection_params.get('connection_string')
            self.storage_client = BlobServiceClient.from_connection_string(connection_string)
            logger.info("Initialized Azure Blob Storage client")

        else:
            raise ValueError(f"Unsupported storage type: {self.source_type}")

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the cloud storage connection by listing bucket/container.

        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        try:
            if self.source_type == 'gcs':
                bucket = self.storage_client.bucket(self.bucket_name)
                # Try to get bucket metadata
                bucket.reload()
                return {'success': True, 'message': f'Successfully connected to GCS bucket: {self.bucket_name}'}

            elif self.source_type == 's3':
                # Try to list objects (limit 1)
                self.storage_client.head_bucket(Bucket=self.bucket_name)
                return {'success': True, 'message': f'Successfully connected to S3 bucket: {self.bucket_name}'}

            elif self.source_type == 'azure_blob':
                container_client = self.storage_client.get_container_client(self.bucket_name)
                # Try to get container properties
                container_client.get_container_properties()
                return {'success': True, 'message': f'Successfully connected to Azure container: {self.bucket_name}'}

        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {'success': False, 'message': f'Connection failed: {str(e)}'}

    def list_files(self) -> List[Dict[str, Any]]:
        """
        List all files matching the configured pattern.

        Returns:
            List of dicts with file metadata:
                - file_path: Full path to file
                - file_size_bytes: Size in bytes
                - file_last_modified: Last modified datetime
        """
        files = []

        try:
            if self.source_type == 'gcs':
                files = self._list_gcs_files()
            elif self.source_type == 's3':
                files = self._list_s3_files()
            elif self.source_type == 'azure_blob':
                files = self._list_azure_files()

            logger.info(f"Found {len(files)} files matching pattern: {self.file_pattern}")
            return files

        except Exception as e:
            logger.error(f"Failed to list files: {str(e)}")
            raise

    def _list_gcs_files(self) -> List[Dict[str, Any]]:
        """List files from Google Cloud Storage."""
        from fnmatch import fnmatch

        bucket = self.storage_client.bucket(self.bucket_name)
        prefix = self.file_path_prefix if self.file_path_prefix else None
        blobs = bucket.list_blobs(prefix=prefix)

        files = []
        for blob in blobs:
            # Skip directories
            if blob.name.endswith('/'):
                continue

            # Match against pattern
            file_name = Path(blob.name).name
            if not fnmatch(file_name, self.file_pattern):
                continue

            files.append({
                'file_path': blob.name,
                'file_size_bytes': blob.size,
                'file_last_modified': blob.updated
            })

        return files

    def _list_s3_files(self) -> List[Dict[str, Any]]:
        """List files from AWS S3."""
        from fnmatch import fnmatch

        prefix = self.file_path_prefix if self.file_path_prefix else ''

        files = []
        paginator = self.storage_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)

        for page in pages:
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                # Skip directories
                if obj['Key'].endswith('/'):
                    continue

                # Match against pattern
                file_name = Path(obj['Key']).name
                if not fnmatch(file_name, self.file_pattern):
                    continue

                files.append({
                    'file_path': obj['Key'],
                    'file_size_bytes': obj['Size'],
                    'file_last_modified': obj['LastModified']
                })

        return files

    def _list_azure_files(self) -> List[Dict[str, Any]]:
        """List files from Azure Blob Storage."""
        from fnmatch import fnmatch

        container_client = self.storage_client.get_container_client(self.bucket_name)
        prefix = self.file_path_prefix if self.file_path_prefix else None
        blobs = container_client.list_blobs(name_starts_with=prefix)

        files = []
        for blob in blobs:
            # Skip directories
            if blob.name.endswith('/'):
                continue

            # Match against pattern
            file_name = Path(blob.name).name
            if not fnmatch(file_name, self.file_pattern):
                continue

            files.append({
                'file_path': blob.name,
                'file_size_bytes': blob.size,
                'file_last_modified': blob.last_modified
            })

        return files

    def extract_file(self, file_path: str) -> pd.DataFrame:
        """
        Extract data from a single file.

        Args:
            file_path: Path to the file in cloud storage

        Returns:
            pandas DataFrame with file contents
        """
        logger.info(f"Extracting file: {file_path}")

        try:
            # Download file to memory
            file_bytes = self._download_file(file_path)

            # Parse based on file format
            if self.file_format == 'csv':
                df = self._parse_csv(file_bytes)
            elif self.file_format == 'parquet':
                df = self._parse_parquet(file_bytes)
            elif self.file_format in ['json', 'jsonl']:
                df = self._parse_json(file_bytes)
            else:
                raise ValueError(f"Unsupported file format: {self.file_format}")

            logger.info(f"Extracted {len(df)} rows from {file_path}")
            return df

        except Exception as e:
            logger.error(f"Failed to extract file {file_path}: {str(e)}")
            raise

    def _download_file(self, file_path: str) -> bytes:
        """Download file from cloud storage to memory."""
        if self.source_type == 'gcs':
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(file_path)
            return blob.download_as_bytes()

        elif self.source_type == 's3':
            response = self.storage_client.get_object(Bucket=self.bucket_name, Key=file_path)
            return response['Body'].read()

        elif self.source_type == 'azure_blob':
            blob_client = self.storage_client.get_blob_client(container=self.bucket_name, blob=file_path)
            return blob_client.download_blob().readall()

    def _parse_csv(self, file_bytes: bytes) -> pd.DataFrame:
        """Parse CSV file using pandas."""
        # Extract format options
        delimiter = self.file_format_options.get('delimiter', ',')
        encoding = self.file_format_options.get('encoding', 'utf-8')
        has_header = self.file_format_options.get('has_header', True)

        header = 0 if has_header else None

        return pd.read_csv(
            io.BytesIO(file_bytes),
            delimiter=delimiter,
            encoding=encoding,
            header=header
        )

    def _parse_parquet(self, file_bytes: bytes) -> pd.DataFrame:
        """Parse Parquet file using pandas."""
        return pd.read_parquet(io.BytesIO(file_bytes))

    def _parse_json(self, file_bytes: bytes) -> pd.DataFrame:
        """Parse JSON/JSONL file using pandas."""
        encoding = self.file_format_options.get('encoding', 'utf-8')

        # Try JSONL first (lines=True), fall back to regular JSON
        try:
            return pd.read_json(
                io.BytesIO(file_bytes),
                lines=True,
                encoding=encoding
            )
        except ValueError:
            # Not JSONL, try regular JSON
            return pd.read_json(
                io.BytesIO(file_bytes),
                encoding=encoding
            )

    def extract_files(
        self,
        processed_files: Dict[str, Dict[str, Any]],
        batch_size: int = 10000
    ) -> Generator[Tuple[pd.DataFrame, Dict[str, Any]], None, None]:
        """
        Extract data from files based on load strategy.

        Args:
            processed_files: Dict mapping file_path -> metadata (size, last_modified)
                             from ProcessedFile table
            batch_size: Not used for files (yields entire file at once)

        Yields:
            Tuple of (DataFrame, file_metadata) for each file to process
        """
        # Get list of available files
        available_files = self.list_files()

        if not available_files:
            logger.warning("No files found matching pattern")
            return

        # Determine which files to process
        if self.load_latest_only:
            # Catalog mode: Load only the latest file
            files_to_process = [max(available_files, key=lambda f: f['file_last_modified'])]
            logger.info(f"Catalog mode (latest only): Processing 1 file")

        elif self.selected_files:
            # User-selected files: Load only specified files
            files_to_process = [f for f in available_files if f['file_path'] in self.selected_files]
            logger.info(f"Selected files mode: Processing {len(files_to_process)} files")

        else:
            # Transactional mode: Load all NEW or CHANGED files
            files_to_process = []
            for file in available_files:
                file_path = file['file_path']

                # Check if file was already processed
                if file_path in processed_files:
                    # Check if file has changed (size or modification time)
                    prev_metadata = processed_files[file_path]
                    if (file['file_size_bytes'] == prev_metadata['file_size_bytes'] and
                        file['file_last_modified'] == prev_metadata['file_last_modified']):
                        # File unchanged, skip
                        logger.debug(f"Skipping unchanged file: {file_path}")
                        continue
                    else:
                        logger.info(f"File changed, reprocessing: {file_path}")

                files_to_process.append(file)

            logger.info(f"Transactional mode: Processing {len(files_to_process)} new/changed files")

        # Extract and yield each file
        for file_metadata in files_to_process:
            file_path = file_metadata['file_path']

            try:
                df = self.extract_file(file_path)

                # Yield DataFrame with metadata
                yield df, file_metadata

            except Exception as e:
                logger.error(f"Failed to process file {file_path}: {str(e)}")
                # Continue with next file instead of failing entire job
                continue

    def close(self):
        """Close storage client connections."""
        # Most cloud storage clients don't need explicit closing
        # but we log it for consistency
        logger.info(f"Closed {self.source_type} storage client")
