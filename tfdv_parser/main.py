"""
TFDV Parser Cloud Run Service

Provides REST API endpoints for parsing TFX pipeline artifacts:
- Statistics from StatisticsGen (FeatureStats.pb)
- Schema from SchemaGen (schema.pbtxt)
- HTML visualizations using TFDV

Runs on Python 3.10 with full TFX/TFDV stack, enabling features
not available in the main Django app (Python 3.12).
"""
import os
import sys
import logging
from functools import wraps

from flask import Flask, request, jsonify

from parsers import StatisticsParser, SchemaParser

# Configure logging for Cloud Run (logs to stdout for Cloud Logging to capture)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s',
    stream=sys.stdout,
    force=True  # Override any existing handlers
)
logger = logging.getLogger(__name__)
# Also configure Flask's logger
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Initialize Flask app
app = Flask(__name__)

# Configuration
PROJECT_ID = os.environ.get('GCP_PROJECT_ID', 'b2b-recs')

# Initialize parsers (lazy initialization in handlers for better error handling)
_statistics_parser = None
_schema_parser = None


def get_statistics_parser():
    global _statistics_parser
    if _statistics_parser is None:
        _statistics_parser = StatisticsParser(project_id=PROJECT_ID)
    return _statistics_parser


def get_schema_parser():
    global _schema_parser
    if _schema_parser is None:
        _schema_parser = SchemaParser(project_id=PROJECT_ID)
    return _schema_parser


def validate_request(required_fields):
    """Decorator to validate request JSON fields."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'error': 'Request must be JSON'
                }), 400

            data = request.get_json()
            missing = [field for field in required_fields if field not in data]
            if missing:
                return jsonify({
                    'success': False,
                    'error': f'Missing required fields: {missing}'
                }), 400

            return f(*args, **kwargs)
        return wrapped
    return decorator


# =============================================================================
# Health Check
# =============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'service': 'tfdv-parser',
        'version': '1.0.0'
    })


# =============================================================================
# Statistics Parsing
# =============================================================================

@app.route('/parse/statistics', methods=['POST'])
@validate_request(['pipeline_root'])
def parse_statistics():
    """
    Parse statistics from pipeline artifacts.

    Request JSON:
    {
        "pipeline_root": "gs://bucket/pipeline_root/run_id",
        "include_html": false  // Optional, default false
    }

    Response:
    {
        "success": true,
        "statistics": {
            "available": true,
            "num_examples": 1234567,
            "num_features": 45,
            "num_numeric_features": 30,
            "num_categorical_features": 15,
            "avg_missing_pct": 2.3,
            "numeric_features": [...],
            "categorical_features": [...]
        },
        "html": "<html>...</html>"  // If include_html=true
    }
    """
    try:
        data = request.get_json()
        pipeline_root = data['pipeline_root']
        include_html = data.get('include_html', False)

        logger.info(f"[STATS] Parsing from: {pipeline_root}")

        parser = get_statistics_parser()
        statistics = parser.parse_from_gcs(pipeline_root)

        # Log the result
        if statistics.get('available'):
            logger.info(f"[STATS] Found {statistics.get('num_features', 0)} features, {statistics.get('num_examples', 0)} examples")
        else:
            logger.warning(f"[STATS] Not available: {statistics.get('error') or statistics.get('message', 'unknown reason')}")

        response = {
            'success': True,
            'statistics': statistics
        }

        # Optionally include HTML visualization
        if include_html and statistics.get('available'):
            html = parser.generate_html_visualization(pipeline_root)
            if html:
                response['html'] = html

        return jsonify(response)

    except Exception as e:
        logger.exception(f"[STATS] Error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/parse/statistics/html', methods=['POST'])
@validate_request(['pipeline_root'])
def parse_statistics_html():
    """
    Generate TFDV HTML visualization.

    Request JSON:
    {
        "pipeline_root": "gs://bucket/pipeline_root/run_id"
    }

    Response:
    {
        "success": true,
        "html": "<html>...</html>"
    }
    """
    try:
        data = request.get_json()
        pipeline_root = data['pipeline_root']

        logger.info(f"Generating HTML visualization from: {pipeline_root}")

        parser = get_statistics_parser()
        html = parser.generate_html_visualization(pipeline_root)

        if html:
            return jsonify({
                'success': True,
                'html': html
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to generate HTML visualization'
            }), 404

    except Exception as e:
        logger.exception(f"Error generating HTML: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Schema Parsing
# =============================================================================

@app.route('/parse/schema', methods=['POST'])
@validate_request(['pipeline_root'])
def parse_schema():
    """
    Parse schema from pipeline artifacts.

    Request JSON:
    {
        "pipeline_root": "gs://bucket/pipeline_root/run_id"
    }

    Response:
    {
        "success": true,
        "schema": {
            "available": true,
            "num_features": 45,
            "num_int_features": 20,
            "num_float_features": 10,
            "num_string_features": 15,
            "num_required_features": 40,
            "features": [...],
            "string_domains": {...},
            "int_domains": {...},
            "float_domains": {...}
        }
    }
    """
    try:
        data = request.get_json()
        pipeline_root = data['pipeline_root']

        logger.info(f"[SCHEMA] Parsing from: {pipeline_root}")

        parser = get_schema_parser()
        schema = parser.parse_from_gcs(pipeline_root)

        # Log the result
        if schema.get('available'):
            logger.info(f"[SCHEMA] Found {schema.get('num_features', 0)} features")
        else:
            logger.warning(f"[SCHEMA] Not available: {schema.get('error') or schema.get('message', 'unknown reason')}")

        return jsonify({
            'success': True,
            'schema': schema
        })

    except Exception as e:
        logger.exception(f"[SCHEMA] Error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Combined Parsing
# =============================================================================

@app.route('/parse/all', methods=['POST'])
@validate_request(['pipeline_root'])
def parse_all():
    """
    Parse both statistics and schema from pipeline artifacts.

    Request JSON:
    {
        "pipeline_root": "gs://bucket/pipeline_root/run_id",
        "include_html": false  // Optional
    }

    Response:
    {
        "success": true,
        "statistics": {...},
        "schema": {...},
        "html": "..."  // If include_html=true
    }
    """
    try:
        data = request.get_json()
        pipeline_root = data['pipeline_root']
        include_html = data.get('include_html', False)

        logger.info(f"Parsing all artifacts from: {pipeline_root}")

        stats_parser = get_statistics_parser()
        schema_parser = get_schema_parser()

        statistics = stats_parser.parse_from_gcs(pipeline_root)
        schema = schema_parser.parse_from_gcs(pipeline_root)

        response = {
            'success': True,
            'statistics': statistics,
            'schema': schema
        }

        if include_html and statistics.get('available'):
            html = stats_parser.generate_html_visualization(pipeline_root)
            if html:
                response['html'] = html

        return jsonify(response)

    except Exception as e:
        logger.exception(f"Error parsing artifacts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
