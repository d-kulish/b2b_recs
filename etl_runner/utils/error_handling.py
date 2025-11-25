"""
Error Handling Utilities

Provides retry logic and error handling for ETL operations.
"""

import time
import logging
from typing import Callable, Any, Optional, Type
from functools import wraps

logger = logging.getLogger(__name__)


class ETLError(Exception):
    """Base exception for ETL errors"""
    pass


class ExtractionError(ETLError):
    """Error during data extraction"""
    pass


class LoadError(ETLError):
    """Error during data loading"""
    pass


class ConfigurationError(ETLError):
    """Error in ETL configuration"""
    pass


class ConnectionError(ETLError):
    """Error connecting to source or destination"""
    pass


def retry_on_exception(
    max_retries: int = 3,
    retry_delay: int = 5,
    exponential_backoff: bool = True,
    exceptions: tuple = (Exception,)
):
    """
    Decorator to retry a function on exception.

    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        exponential_backoff: Use exponential backoff (default: True)
        exceptions: Tuple of exception types to catch and retry

    Usage:
        @retry_on_exception(max_retries=3, retry_delay=5)
        def my_function():
            # Function code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        # Calculate delay
                        if exponential_backoff:
                            delay = retry_delay * (2 ** attempt)
                        else:
                            delay = retry_delay

                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed: {str(e)}. "
                            f"Retrying in {delay} seconds..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed. Last error: {str(e)}"
                        )

            # All retries exhausted
            raise last_exception

        return wrapper
    return decorator


def handle_etl_error(
    error: Exception,
    config: Any,
    etl_run_id: Optional[int] = None
) -> None:
    """
    Handle ETL error by logging and updating status in Django.

    Args:
        error: Exception that occurred
        config: Config instance
        etl_run_id: ETL run ID (optional)
    """
    error_message = f"{type(error).__name__}: {str(error)}"

    logger.error(f"ETL error occurred: {error_message}", exc_info=True)

    # Update ETL run status to failed
    if etl_run_id and config:
        config.update_etl_run_status(
            etl_run_id=etl_run_id,
            status='failed',
            error_message=error_message
        )


def validate_job_config(config: dict) -> None:
    """
    Validate job configuration.

    Args:
        config: Job configuration dictionary

    Raises:
        ConfigurationError: If configuration is invalid
    """
    required_fields = [
        'source_type',
        'connection_params',
        'source_table_name',
        'schema_name',
        'dest_table_name',
        'load_type',
        'selected_columns'
    ]

    for field in required_fields:
        if field not in config:
            raise ConfigurationError(f"Missing required field: {field}")

    # Validate load type
    if config['load_type'] not in ['transactional', 'catalog']:
        raise ConfigurationError(
            f"Invalid load_type: {config['load_type']}. "
            f"Must be 'transactional' or 'catalog'"
        )

    # Validate source type first
    database_source_types = ['postgresql', 'mysql', 'bigquery']
    file_source_types = ['gcs', 's3', 'azure_blob']
    nosql_source_types = ['firestore']
    valid_source_types = database_source_types + file_source_types + nosql_source_types

    source_type = config['source_type']
    if source_type not in valid_source_types:
        raise ConfigurationError(
            f"Invalid source_type: {source_type}. "
            f"Must be one of: {', '.join(valid_source_types)}"
        )

    is_file_source = source_type in file_source_types
    is_nosql_source = source_type in nosql_source_types

    # Validate transactional load requirements
    # For database/NoSQL sources: timestamp_column is required
    # For file sources: files are tracked by metadata, no timestamp_column needed
    if config['load_type'] == 'transactional':
        if not is_file_source and not config.get('timestamp_column'):
            source_category = "NoSQL" if is_nosql_source else "database"
            raise ConfigurationError(
                f"timestamp_column is required for transactional loads from {source_category} sources"
            )

    # Validate selected columns
    # For database sources: selected_columns is required
    # For file/NoSQL sources: empty selected_columns means "load all columns"
    if not is_file_source and not is_nosql_source:
        if not config['selected_columns'] or len(config['selected_columns']) == 0:
            raise ConfigurationError("selected_columns cannot be empty for database sources")

    logger.info("Job configuration validated successfully")
