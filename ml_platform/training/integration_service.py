"""
Integration Service for Deployed Endpoints

Provides functionality for testing deployed ML endpoints:
- Schema extraction from FeatureConfig
- Sample data retrieval from BigQuery
- Health check and prediction testing
- Code example generation (Python, JavaScript, cURL, Java)
"""
import json
import logging
import time
from typing import Dict, List, Optional, Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class IntegrationServiceError(Exception):
    """Exception raised by IntegrationService operations."""
    pass


class IntegrationService:
    """
    Service class for endpoint integration testing.

    Provides:
    - Schema extraction from feature configs
    - Sample data from BigQuery (using TFX-compatible format)
    - Health checks against deployed endpoints
    - Prediction tests with real data
    - Code example generation
    """

    # Type mapping from BigQuery types to user-friendly display
    TYPE_DISPLAY_MAP = {
        'STRING': 'STRING',
        'INT64': 'INT64',
        'INTEGER': 'INT64',
        'FLOAT64': 'FLOAT64',
        'FLOAT': 'FLOAT64',
        'NUMERIC': 'FLOAT64',
        'BOOLEAN': 'BOOLEAN',
        'BOOL': 'BOOLEAN',
        'TIMESTAMP': 'INT64',  # Converted to Unix epoch for TFX
        'DATE': 'INT64',       # Converted to Unix epoch for TFX
        'DATETIME': 'INT64',   # Converted to Unix epoch for TFX
    }

    # Notes for type conversions
    TYPE_NOTES = {
        'TIMESTAMP': 'Unix timestamp (converted)',
        'DATE': 'Unix timestamp (converted)',
        'DATETIME': 'Unix timestamp (converted)',
    }

    def __init__(self, deployed_endpoint):
        """
        Initialize IntegrationService for a specific endpoint.

        Args:
            deployed_endpoint: DeployedEndpoint model instance
        """
        self.endpoint = deployed_endpoint
        self.training_run = deployed_endpoint.deployed_training_run

        if not self.training_run:
            raise IntegrationServiceError("Endpoint has no deployed training run")

        self.feature_config = self.training_run.feature_config
        self.dataset = self.training_run.dataset

        if not self.feature_config:
            raise IntegrationServiceError("Training run has no feature config")
        if not self.dataset:
            raise IntegrationServiceError("Training run has no dataset")

    def get_input_schema(self) -> List[Dict]:
        """
        Extract input schema from feature_config.buyer_model_features.

        Returns:
            List of field definitions with name, type, and notes
        """
        fields = []

        # Get buyer model features from feature config
        buyer_features = self.feature_config.buyer_model_features or []

        # Get column types from dataset summary snapshot
        column_types = {}
        if self.dataset.summary_snapshot:
            column_stats = self.dataset.summary_snapshot.get('column_stats', {})
            for col_key, stats in column_stats.items():
                # Handle both "table.column" and just "column" formats
                col_name = col_key.split('.')[-1] if '.' in col_key else col_key
                column_types[col_name] = stats.get('type', 'STRING')

        for feature in buyer_features:
            column = feature.get('column', '')
            if not column:
                continue

            # Get the original BigQuery type
            original_type = column_types.get(column, 'STRING')

            # Map to display type (TFX converts timestamps to INT64)
            display_type = self.TYPE_DISPLAY_MAP.get(original_type, original_type)

            # Add notes for converted types
            notes = self.TYPE_NOTES.get(original_type, '')
            if not notes:
                # Add feature type notes
                feature_type = feature.get('type', '')
                if feature_type == 'string_embedding':
                    notes = 'String identifier'
                elif feature_type == 'numeric':
                    notes = 'Numeric value'
                elif feature_type == 'categorical':
                    notes = 'Categorical'
                else:
                    notes = 'Required'

            fields.append({
                'name': column,
                'type': display_type,
                'notes': notes
            })

        # Also add product model features
        product_features = self.feature_config.product_model_features or []
        for feature in product_features:
            column = feature.get('column', '')
            if not column:
                continue

            original_type = column_types.get(column, 'STRING')
            display_type = self.TYPE_DISPLAY_MAP.get(original_type, original_type)
            notes = self.TYPE_NOTES.get(original_type, '')
            if not notes:
                feature_type = feature.get('type', '')
                if feature_type == 'string_embedding':
                    notes = 'Product identifier'
                else:
                    notes = 'Required'

            fields.append({
                'name': column,
                'type': display_type,
                'notes': notes
            })

        return fields

    def get_sample_data(self, count: int = 1) -> Dict:
        """
        Query BigQuery for random sample using for_tfx=True.

        Args:
            count: Number of samples to retrieve (default 1)

        Returns:
            Dict with 'instance' containing sample feature values
        """
        from ml_platform.datasets.services import BigQueryService, BigQueryServiceError

        try:
            # Get the model endpoint from the registered model
            model_endpoint = self.endpoint.registered_model.ml_model

            # Initialize BigQuery service with dataset for location
            bq_service = BigQueryService(model_endpoint, dataset=self.dataset)

            # Generate query with TFX format (timestamps as INT64)
            query = bq_service.generate_query(self.dataset, for_analysis=False, for_tfx=True)

            # Add ORDER BY RAND() and LIMIT for random sampling
            # Wrap the query to add random ordering
            sample_query = f"""
            SELECT * FROM (
                {query}
            ) ORDER BY RAND() LIMIT {count}
            """

            # Execute query
            result = bq_service.client.query(sample_query).result()

            # Convert to dict
            rows = list(result)
            if not rows:
                return {'instance': {}, 'error': 'No data found'}

            # Get the first row as a dict
            row = rows[0]
            instance = {}

            # Get schema fields for this row
            for field in result.schema:
                value = getattr(row, field.name, None)
                # Convert to JSON-serializable format
                if value is not None:
                    if hasattr(value, 'isoformat'):
                        # Date/datetime objects
                        value = value.isoformat()
                    elif isinstance(value, bytes):
                        value = value.decode('utf-8')
                instance[field.name] = value

            return {'instance': instance}

        except BigQueryServiceError as e:
            logger.error(f"BigQuery error getting sample data: {e}")
            return {'instance': {}, 'error': str(e)}
        except Exception as e:
            logger.exception(f"Error getting sample data: {e}")
            return {'instance': {}, 'error': str(e)}

    def run_health_check(self) -> Dict:
        """
        Run health check against the deployed endpoint.

        GET /v1/models/recommender

        Returns:
            Dict with status, latency_ms, and response details
        """
        if not self.endpoint.is_active:
            return {
                'success': False,
                'status_code': 0,
                'error': 'Endpoint is not active',
                'latency_ms': 0
            }

        if not self.endpoint.service_url:
            return {
                'success': False,
                'status_code': 0,
                'error': 'Endpoint has no service URL',
                'latency_ms': 0
            }

        try:
            url = f"{self.endpoint.service_url.rstrip('/')}/v1/models/recommender"

            start_time = time.time()
            response = requests.get(url, timeout=30)
            latency_ms = int((time.time() - start_time) * 1000)

            return {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'latency_ms': latency_ms,
                'response': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            }

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'status_code': 0,
                'error': 'Request timed out',
                'latency_ms': 30000
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'status_code': 0,
                'error': str(e),
                'latency_ms': 0
            }
        except Exception as e:
            logger.exception(f"Error running health check: {e}")
            return {
                'success': False,
                'status_code': 0,
                'error': str(e),
                'latency_ms': 0
            }

    def run_prediction_test(self, instance: Dict) -> Dict:
        """
        Run prediction test against the deployed endpoint.

        POST /v1/models/recommender:predict

        Args:
            instance: Feature dictionary for prediction

        Returns:
            Dict with status, latency_ms, and prediction response
        """
        if not self.endpoint.is_active:
            return {
                'success': False,
                'status_code': 0,
                'error': 'Endpoint is not active',
                'latency_ms': 0
            }

        if not self.endpoint.service_url:
            return {
                'success': False,
                'status_code': 0,
                'error': 'Endpoint has no service URL',
                'latency_ms': 0
            }

        try:
            url = f"{self.endpoint.service_url.rstrip('/')}/v1/models/recommender:predict"

            # Format request according to TF Serving API
            payload = {
                "instances": [instance]
            }

            headers = {
                'Content-Type': 'application/json'
            }

            start_time = time.time()
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            latency_ms = int((time.time() - start_time) * 1000)

            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = {'raw': response.text}

            return {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'latency_ms': latency_ms,
                'response': response_data
            }

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'status_code': 0,
                'error': 'Request timed out',
                'latency_ms': 60000
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'status_code': 0,
                'error': str(e),
                'latency_ms': 0
            }
        except Exception as e:
            logger.exception(f"Error running prediction test: {e}")
            return {
                'success': False,
                'status_code': 0,
                'error': str(e),
                'latency_ms': 0
            }

    def generate_code_examples(self, instance: Dict) -> Dict[str, str]:
        """
        Generate code examples for Python, JavaScript, cURL, and Java.

        Args:
            instance: Sample feature dictionary for examples

        Returns:
            Dict with 'python', 'javascript', 'curl', 'java' code strings
        """
        url = f"{self.endpoint.service_url.rstrip('/')}/v1/models/recommender:predict"
        payload = {"instances": [instance]}
        payload_json = json.dumps(payload, indent=2)
        payload_json_compact = json.dumps(payload)

        # Python example
        python_code = f'''import requests

url = "{url}"
payload = {payload_json}

response = requests.post(url, json=payload)
print(response.json())
'''

        # JavaScript example
        javascript_code = f'''const url = "{url}";
const payload = {payload_json};

fetch(url, {{
  method: "POST",
  headers: {{ "Content-Type": "application/json" }},
  body: JSON.stringify(payload)
}})
  .then(response => response.json())
  .then(data => console.log(data));
'''

        # cURL example
        curl_code = f'''curl -X POST "{url}" \\
  -H "Content-Type: application/json" \\
  -d '{payload_json_compact}'
'''

        # Java example
        java_code = f'''import java.net.http.*;
import java.net.URI;

HttpClient client = HttpClient.newHttpClient();
String json = "{payload_json_compact.replace('"', '\\"')}";

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("{url}"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(json))
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.body());
'''

        return {
            'python': python_code,
            'javascript': javascript_code,
            'curl': curl_code,
            'java': java_code
        }

    def get_integration_data(self) -> Dict:
        """
        Get all integration data for the modal in one call.

        Returns:
            Dict with endpoint info, schema, sample data, and code examples
        """
        # Get schema
        schema_fields = self.get_input_schema()

        # Get sample data
        sample_result = self.get_sample_data(count=1)
        instance = sample_result.get('instance', {})

        # Generate code examples using sample data
        code_examples = self.generate_code_examples(instance)

        return {
            'endpoint': {
                'id': self.endpoint.id,
                'service_name': self.endpoint.service_name,
                'service_url': self.endpoint.service_url,
                'model_name': self.endpoint.registered_model.model_name,
                'model_type': self.endpoint.registered_model.model_type,
                'is_active': self.endpoint.is_active,
                'deployed_version': self.endpoint.deployed_version,
            },
            'schema': {
                'fields': schema_fields
            },
            'sample_data': {
                'instance': instance,
                'error': sample_result.get('error')
            },
            'code_examples': code_examples
        }
