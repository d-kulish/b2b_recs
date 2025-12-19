"""
Error Pattern Matching for Pipeline Failures

Provides pattern-based error classification and user-friendly suggestions
for common pipeline failure scenarios.
"""
import re
from typing import Optional, Dict, List

# Error patterns with classification and suggested fixes
# Patterns are checked in order - first match wins
ERROR_PATTERNS: List[Dict] = [
    # Memory/Resource errors
    {
        'pattern': r'(ResourceExhausted|OOM|out of memory|memory limit|MemoryError)',
        'type': 'ResourceExhausted',
        'title': 'Memory Limit Exceeded',
        'suggestion': 'Try reducing batch_size or selecting larger hardware (Medium or Large).',
        'severity': 'error'
    },
    {
        'pattern': r'(RESOURCE_EXHAUSTED.*memory|Cannot allocate|allocation failed)',
        'type': 'ResourceExhausted',
        'title': 'Memory Allocation Failed',
        'suggestion': 'The dataset or model requires more memory. Reduce data_sample_percent or batch_size.',
        'severity': 'error'
    },

    # Schema/Column errors
    {
        'pattern': r'(column.*not found|KeyError.*[\'"](\w+)[\'"]|feature.*missing|Unknown feature)',
        'type': 'SchemaError',
        'title': 'Column Not Found',
        'suggestion': 'Check that Feature Config columns match the Dataset schema. A column may have been renamed or removed.',
        'severity': 'error'
    },
    {
        'pattern': r'(schema.*mismatch|type.*mismatch|incompatible.*type|cannot convert)',
        'type': 'SchemaError',
        'title': 'Data Type Mismatch',
        'suggestion': 'A column has an unexpected data type. Verify the Feature Config column types match the Dataset.',
        'severity': 'error'
    },

    # Data errors
    {
        'pattern': r'(no examples|empty dataset|zero rows|no data|0 examples)',
        'type': 'DataError',
        'title': 'No Data Found',
        'suggestion': 'The query returned no data. Check date range filters and ensure the Dataset contains data for the specified period.',
        'severity': 'error'
    },
    {
        'pattern': r'(null.*values|NaN|missing required|required field.*null)',
        'type': 'DataError',
        'title': 'Missing Required Values',
        'suggestion': 'Some required columns contain null values. Check data quality or add null handling in Feature Config.',
        'severity': 'error'
    },

    # BigQuery errors
    {
        'pattern': r'(BigQuery.*error|bq.*error|query.*failed|SQL.*error)',
        'type': 'BigQueryError',
        'title': 'BigQuery Query Failed',
        'suggestion': 'The data extraction query failed. Check Dataset configuration and BigQuery permissions.',
        'severity': 'error'
    },
    {
        'pattern': r'(table.*not found|dataset.*not found|Not found: Table)',
        'type': 'BigQueryError',
        'title': 'Table Not Found',
        'suggestion': 'The BigQuery table no longer exists or was renamed. Update the Dataset configuration.',
        'severity': 'error'
    },

    # Quota/Limit errors
    {
        'pattern': r'(quota|limit exceeded|RESOURCE_EXHAUSTED(?!.*memory)|rate limit)',
        'type': 'QuotaError',
        'title': 'Quota Limit Reached',
        'suggestion': 'GCP quota limit reached. Wait a few minutes and try again, or contact admin to increase quotas.',
        'severity': 'warning'
    },

    # Timeout errors
    {
        'pattern': r'(timeout|deadline exceeded|DEADLINE_EXCEEDED|timed out)',
        'type': 'TimeoutError',
        'title': 'Operation Timed Out',
        'suggestion': 'The pipeline timed out. Try reducing data_sample_percent or simplifying the Feature Config.',
        'severity': 'error'
    },

    # Permission errors
    {
        'pattern': r'(permission denied|403|PERMISSION_DENIED|access denied|unauthorized)',
        'type': 'PermissionError',
        'title': 'Permission Denied',
        'suggestion': 'Service account lacks required permissions. Contact administrator.',
        'severity': 'error'
    },

    # Transform/TFX specific errors
    {
        'pattern': r'(vocabulary.*error|vocab.*too large|StringToHashBucketFast)',
        'type': 'TransformError',
        'title': 'Vocabulary Error',
        'suggestion': 'A categorical column has too many unique values. Consider using hash_buckets instead of vocabulary.',
        'severity': 'error'
    },
    {
        'pattern': r'(transform.*failed|preprocessing.*error|feature engineering.*failed)',
        'type': 'TransformError',
        'title': 'Feature Transform Failed',
        'suggestion': 'Feature transformation failed. Check Feature Config for invalid column references or operations.',
        'severity': 'error'
    },

    # Training errors
    {
        'pattern': r'(loss.*nan|loss.*inf|gradient.*exploded|diverged)',
        'type': 'TrainingError',
        'title': 'Training Diverged',
        'suggestion': 'Model training diverged (loss became NaN/Inf). Try reducing learning_rate or batch_size.',
        'severity': 'error'
    },
    {
        'pattern': r'(embedding.*dimension|layer.*shape|shape.*mismatch)',
        'type': 'TrainingError',
        'title': 'Model Shape Mismatch',
        'suggestion': 'Model architecture mismatch. Check Model Config embedding dimensions match Feature Config.',
        'severity': 'error'
    },

    # Dataflow errors
    {
        'pattern': r'(Dataflow.*error|worker.*failed|beam.*error|pipeline.*aborted)',
        'type': 'DataflowError',
        'title': 'Dataflow Worker Failed',
        'suggestion': 'Distributed processing failed. This may be a transient error - try running again.',
        'severity': 'error'
    },

    # Network/Infrastructure errors
    {
        'pattern': r'(network.*error|connection.*refused|connection.*timeout|DNS.*failed)',
        'type': 'NetworkError',
        'title': 'Network Error',
        'suggestion': 'Network connectivity issue. This is usually transient - try running again.',
        'severity': 'warning'
    },
    {
        'pattern': r'(internal.*error|server.*error|500|service.*unavailable)',
        'type': 'InternalError',
        'title': 'Internal Service Error',
        'suggestion': 'A GCP service encountered an internal error. Try running again in a few minutes.',
        'severity': 'warning'
    },
]


def classify_error(error_message: str) -> Dict:
    """
    Classify an error message and provide user-friendly information.

    Args:
        error_message: Raw error message from pipeline

    Returns:
        Dict with:
            - type: Error classification (e.g., 'ResourceExhausted')
            - title: User-friendly title
            - suggestion: Actionable fix suggestion
            - severity: 'error' or 'warning'
            - matched: Boolean indicating if pattern was matched
    """
    if not error_message:
        return {
            'type': 'Unknown',
            'title': 'Unknown Error',
            'suggestion': 'An unexpected error occurred. Check the error details below.',
            'severity': 'error',
            'matched': False
        }

    # Try each pattern in order
    for pattern_info in ERROR_PATTERNS:
        if re.search(pattern_info['pattern'], error_message, re.IGNORECASE):
            return {
                'type': pattern_info['type'],
                'title': pattern_info['title'],
                'suggestion': pattern_info['suggestion'],
                'severity': pattern_info['severity'],
                'matched': True
            }

    # No pattern matched - return generic error
    return {
        'type': 'Unknown',
        'title': 'Pipeline Error',
        'suggestion': 'An error occurred during pipeline execution. See the error details below for more information.',
        'severity': 'error',
        'matched': False
    }


def extract_key_info(error_message: str) -> Dict:
    """
    Extract key information from error message for display.

    Args:
        error_message: Raw error message

    Returns:
        Dict with extracted information:
            - summary: Short summary (first line or first 200 chars)
            - has_stack_trace: Boolean
            - failed_component: Extracted component name if found
    """
    if not error_message:
        return {
            'summary': 'No error message available',
            'has_stack_trace': False,
            'failed_component': None
        }

    lines = error_message.strip().split('\n')

    # Get summary (first non-empty line, truncated)
    summary = ''
    for line in lines:
        line = line.strip()
        if line:
            summary = line[:200] + ('...' if len(line) > 200 else '')
            break

    # Check for stack trace indicators
    has_stack_trace = any(
        indicator in error_message.lower()
        for indicator in ['traceback', 'file "', 'line ', 'exception', 'error:']
    )

    # Try to extract failed component
    failed_component = None
    component_patterns = [
        r'(BigQueryExampleGen|StatisticsGen|SchemaGen|Transform|Trainer)',
        r'component[:\s]+[\'"]?(\w+)[\'"]?',
        r'task[:\s]+[\'"]?(\w+)[\'"]?',
    ]

    for pattern in component_patterns:
        match = re.search(pattern, error_message, re.IGNORECASE)
        if match:
            failed_component = match.group(1)
            break

    return {
        'summary': summary or 'Error details not available',
        'has_stack_trace': has_stack_trace,
        'failed_component': failed_component
    }


def format_error_for_display(error_message: str) -> Dict:
    """
    Format error message for user-friendly display.

    Combines classification and extraction into a single response.

    Args:
        error_message: Raw error message

    Returns:
        Complete error display information
    """
    classification = classify_error(error_message)
    key_info = extract_key_info(error_message)

    return {
        'error_type': classification['type'],
        'title': classification['title'],
        'suggestion': classification['suggestion'],
        'severity': classification['severity'],
        'summary': key_info['summary'],
        'has_stack_trace': key_info['has_stack_trace'],
        'failed_component': key_info['failed_component'],
        'full_message': error_message,
    }
