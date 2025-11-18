"""
Logging Configuration

Sets up structured logging for Cloud Run with JSON formatting.
"""

import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for Cloud Logging"""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record

        Returns:
            JSON-formatted log string
        """
        log_data: Dict[str, Any] = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'severity': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, 'data_source_id'):
            log_data['data_source_id'] = record.data_source_id
        if hasattr(record, 'etl_run_id'):
            log_data['etl_run_id'] = record.etl_run_id

        return json.dumps(log_data)


def setup_logging(log_level: str = 'INFO', json_format: bool = True):
    """
    Configure logging for the ETL runner.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatting for Cloud Logging (default: True)
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # Set formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Suppress noisy loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)

    logging.info(f"Logging configured: level={log_level}, json_format={json_format}")


class LogContext:
    """
    Context manager for adding context to logs.

    Usage:
        with LogContext(data_source_id=123, etl_run_id=456):
            logger.info("Processing data")  # Will include context in logs
    """

    def __init__(self, **kwargs):
        """
        Initialize log context.

        Args:
            **kwargs: Context fields to add to logs
        """
        self.context = kwargs
        self.old_factory = None

    def __enter__(self):
        """Enter context and add fields to log records"""
        self.old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore original log record factory"""
        logging.setLogRecordFactory(self.old_factory)
