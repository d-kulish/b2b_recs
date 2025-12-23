"""
MLflow Service Client

Provides Django interface to MLflow Tracking Server REST API for experiment
tracking, training history, and comparison features.

Follows same authentication pattern as artifact_service.py for Cloud Run
service-to-service calls.
"""
import json
import logging
import os
import subprocess
from typing import Dict, List, Optional, Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# MLflow Tracking Server URL (Cloud Run)
MLFLOW_TRACKING_URI = getattr(
    settings, 'MLFLOW_TRACKING_URI',
    os.environ.get(
        'MLFLOW_TRACKING_URI',
        'https://mlflow-server-555035914949.europe-central2.run.app'
    )
)


class MLflowServiceError(Exception):
    """Custom exception for MLflow service errors."""
    pass


class MLflowService:
    """
    Client for MLflow Tracking Server REST API.

    Provides methods to query experiments, runs, and metrics
    for display in Django UI.

    Authentication:
    - Uses identity tokens for Cloud Run service-to-service calls
    - Falls back to gcloud CLI for local development
    """

    def __init__(self, tracking_uri: str = None):
        """
        Initialize the MLflow service.

        Args:
            tracking_uri: MLflow Tracking Server URL (defaults to settings)
        """
        self.tracking_uri = tracking_uri or MLFLOW_TRACKING_URI
        self._token_cache = None

    def _get_auth_token(self) -> Optional[str]:
        """
        Get identity token for Cloud Run service-to-service calls.

        Cloud Run requires an identity token (not access token) with the
        target service URL as the audience.

        For production (Cloud Run): Uses service account metadata endpoint
        For local development: Falls back to gcloud CLI
        """
        # Method 1: Try google.oauth2.id_token (works with service accounts)
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token

            auth_req = google.auth.transport.requests.Request()
            token = google.oauth2.id_token.fetch_id_token(auth_req, self.tracking_uri)
            return token
        except Exception as e:
            logger.debug(f"fetch_id_token failed (expected for user credentials): {e}")

        # Method 2: Fallback for local dev - use gcloud CLI
        try:
            result = subprocess.run(
                ['gcloud', 'auth', 'print-identity-token'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.debug(f"gcloud auth failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.debug("gcloud auth timed out")
        except FileNotFoundError:
            logger.debug("gcloud CLI not found")
        except Exception as e:
            logger.debug(f"gcloud auth error: {e}")

        logger.warning("Could not obtain identity token for MLflow - requests may fail")
        return None

    def _api_call(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        data: Dict = None,
        timeout: int = 30
    ) -> Optional[Dict]:
        """
        Make authenticated API call to MLflow server.

        Args:
            method: HTTP method (GET or POST)
            endpoint: API endpoint path (e.g., /runs/get)
            params: Query parameters for GET requests
            data: JSON body for POST requests
            timeout: Request timeout in seconds

        Returns:
            Response JSON or None on error
        """
        url = f"{self.tracking_uri}/api/2.0/mlflow{endpoint}"

        try:
            token = self._get_auth_token()
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = f'Bearer {token}'

            if method == 'GET':
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout
                )
            else:
                response = requests.post(
                    url,
                    json=data,
                    headers=headers,
                    timeout=timeout
                )

            if response.ok:
                return response.json()

            # Handle specific error codes
            if response.status_code == 401:
                logger.error("MLflow authentication failed - check service account permissions")
            elif response.status_code == 404:
                logger.debug(f"MLflow resource not found: {endpoint}")
            elif response.status_code == 503:
                logger.warning("MLflow server unavailable (possibly cold starting)")
            else:
                logger.warning(f"MLflow API error {response.status_code}: {response.text[:500]}")

            return None

        except requests.exceptions.Timeout:
            logger.warning(f"MLflow request timed out: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning("MLflow connection failed - server may be starting")
            return None
        except Exception as e:
            logger.exception(f"MLflow API call failed: {e}")
            return None

    # =========================================================================
    # Run Methods
    # =========================================================================

    def get_run(self, run_id: str) -> Optional[Dict]:
        """
        Get details for a specific MLflow run.

        Args:
            run_id: MLflow run ID

        Returns:
            Run dictionary with info, data (metrics, params, tags) or None
        """
        if not run_id:
            return None

        result = self._api_call('GET', '/runs/get', params={'run_id': run_id})
        return result.get('run') if result else None

    def get_run_metrics(self, run_id: str) -> Dict[str, List[Dict]]:
        """
        Get all metrics for a run including per-epoch history.

        Args:
            run_id: MLflow run ID

        Returns:
            Dict mapping metric names to list of {step, value, timestamp}
            Example: {'loss': [{'step': 0, 'value': 0.5, ...}, ...]}
        """
        if not run_id:
            return {}

        run = self.get_run(run_id)
        if not run:
            return {}

        metrics = {}
        run_metrics = run.get('data', {}).get('metrics', [])

        for metric in run_metrics:
            metric_key = metric.get('key')
            if not metric_key:
                continue

            # Get full metric history for this key
            history = self._api_call(
                'GET',
                '/metrics/get-history',
                params={'run_id': run_id, 'metric_key': metric_key}
            )

            if history and 'metrics' in history:
                metrics[metric_key] = [
                    {
                        'step': m.get('step', 0),
                        'value': m.get('value'),
                        'timestamp': m.get('timestamp')
                    }
                    for m in history['metrics']
                ]

        return metrics

    def get_run_params(self, run_id: str) -> Dict[str, str]:
        """
        Get parameters for a run.

        Args:
            run_id: MLflow run ID

        Returns:
            Dict mapping parameter names to values
        """
        if not run_id:
            return {}

        run = self.get_run(run_id)
        if not run:
            return {}

        params = {}
        for param in run.get('data', {}).get('params', []):
            params[param.get('key')] = param.get('value')

        return params

    def get_run_tags(self, run_id: str) -> Dict[str, str]:
        """
        Get tags for a run.

        Args:
            run_id: MLflow run ID

        Returns:
            Dict mapping tag names to values
        """
        if not run_id:
            return {}

        run = self.get_run(run_id)
        if not run:
            return {}

        tags = {}
        for tag in run.get('data', {}).get('tags', []):
            tags[tag.get('key')] = tag.get('value')

        return tags

    # =========================================================================
    # Training History Methods (for Charts)
    # =========================================================================

    def get_training_history(self, run_id: str) -> Dict:
        """
        Get training history suitable for Chart.js visualization.

        Returns structured data for loss curves and metric charts.

        Args:
            run_id: MLflow run ID

        Returns:
            {
                'available': True/False,
                'epochs': [0, 1, 2, ...],
                'loss': {'train': [...], 'val': [...]},
                'metrics': {
                    'recall_at_10': [...],
                    'recall_at_50': [...],
                    'recall_at_100': [...]
                },
                'final_metrics': {...}
            }
        """
        if not run_id:
            return {
                'available': False,
                'message': 'No MLflow run ID associated with this experiment'
            }

        metrics = self.get_run_metrics(run_id)

        if not metrics:
            return {
                'available': False,
                'message': 'Could not retrieve metrics from MLflow'
            }

        # Organize metrics for charting
        result = {
            'available': True,
            'epochs': [],
            'loss': {'train': [], 'val': []},
            'metrics': {},
            'final_metrics': {}
        }

        # Extract epoch numbers from loss metric
        loss_history = metrics.get('loss', [])
        if loss_history:
            result['epochs'] = [m['step'] for m in sorted(loss_history, key=lambda x: x['step'])]
            result['loss']['train'] = [m['value'] for m in sorted(loss_history, key=lambda x: x['step'])]

        # Validation loss
        val_loss_history = metrics.get('val_loss', [])
        if val_loss_history:
            result['loss']['val'] = [m['value'] for m in sorted(val_loss_history, key=lambda x: x['step'])]

        # Recall metrics (may have various naming patterns)
        recall_patterns = ['recall_at_10', 'recall_at_50', 'recall_at_100',
                          'factorized_top_k/top_10_categorical_accuracy',
                          'factorized_top_k/top_50_categorical_accuracy',
                          'factorized_top_k/top_100_categorical_accuracy']

        for pattern in recall_patterns:
            if pattern in metrics:
                # Normalize the key name
                clean_key = pattern.replace('factorized_top_k/', '').replace('_categorical_accuracy', '')
                history = metrics[pattern]
                result['metrics'][clean_key] = [
                    m['value'] for m in sorted(history, key=lambda x: x['step'])
                ]

        # Extract final metrics
        final_patterns = ['final_loss', 'final_val_loss', 'test_loss',
                         'test_recall_at_10', 'test_recall_at_50', 'test_recall_at_100']

        for key, values in metrics.items():
            if key.startswith('final_') or key.startswith('test_'):
                # Final metrics typically have only one value
                if values:
                    result['final_metrics'][key] = values[-1]['value']

        return result

    # =========================================================================
    # Experiment Methods
    # =========================================================================

    def get_experiment_by_name(self, name: str) -> Optional[Dict]:
        """
        Get experiment by name.

        Args:
            name: Experiment name

        Returns:
            Experiment dictionary or None
        """
        result = self._api_call(
            'GET',
            '/experiments/get-by-name',
            params={'experiment_name': name}
        )
        return result.get('experiment') if result else None

    def list_runs(
        self,
        experiment_name: str = None,
        experiment_id: str = None,
        max_results: int = 100,
        order_by: str = 'start_time DESC',
        filter_string: str = None
    ) -> List[Dict]:
        """
        List runs in an experiment.

        Args:
            experiment_name: Name of the experiment (will look up ID)
            experiment_id: Direct experiment ID (preferred if known)
            max_results: Maximum number of runs to return
            order_by: Ordering (e.g., 'metrics.recall_at_100 DESC')
            filter_string: MLflow filter expression

        Returns:
            List of run dictionaries
        """
        # Get experiment ID if name provided
        if experiment_name and not experiment_id:
            experiment = self.get_experiment_by_name(experiment_name)
            if experiment:
                experiment_id = experiment.get('experiment_id')

        if not experiment_id:
            logger.warning(f"Could not find experiment: {experiment_name}")
            return []

        data = {
            'experiment_ids': [experiment_id],
            'max_results': max_results,
            'order_by': [order_by] if order_by else None
        }

        if filter_string:
            data['filter'] = filter_string

        result = self._api_call('POST', '/runs/search', data=data)
        return result.get('runs', []) if result else []

    # =========================================================================
    # Comparison Methods
    # =========================================================================

    def compare_runs(self, run_ids: List[str]) -> Dict:
        """
        Compare multiple runs for side-by-side analysis.

        Args:
            run_ids: List of MLflow run IDs to compare

        Returns:
            {
                'runs': [run1, run2, ...],
                'metrics': {
                    'loss': {'run_id_1': 0.1, 'run_id_2': 0.2},
                    'recall_at_100': {...}
                },
                'params': {
                    'learning_rate': {'run_id_1': '0.001', 'run_id_2': '0.01'},
                    ...
                }
            }
        """
        runs = []
        all_metrics = {}
        all_params = {}

        for run_id in run_ids:
            run = self.get_run(run_id)
            if not run:
                continue

            runs.append({
                'run_id': run['info']['run_id'],
                'run_name': next(
                    (t['value'] for t in run.get('data', {}).get('tags', [])
                     if t['key'] == 'mlflow.runName'),
                    run['info']['run_id']
                ),
                'status': run['info'].get('status'),
                'start_time': run['info'].get('start_time'),
                'end_time': run['info'].get('end_time'),
            })

            # Collect metrics
            for metric in run.get('data', {}).get('metrics', []):
                key = metric['key']
                if key not in all_metrics:
                    all_metrics[key] = {}
                all_metrics[key][run_id] = metric['value']

            # Collect params
            for param in run.get('data', {}).get('params', []):
                key = param['key']
                if key not in all_params:
                    all_params[key] = {}
                all_params[key][run_id] = param['value']

        return {
            'runs': runs,
            'metrics': all_metrics,
            'params': all_params
        }

    def get_best_run(
        self,
        experiment_name: str,
        metric: str = 'test_recall_at_100',
        ascending: bool = False
    ) -> Optional[Dict]:
        """
        Get the best run by a specific metric.

        Args:
            experiment_name: Name of the experiment
            metric: Metric to sort by
            ascending: If True, lower is better (for loss)

        Returns:
            Best run dictionary or None
        """
        order = 'ASC' if ascending else 'DESC'
        runs = self.list_runs(
            experiment_name=experiment_name,
            max_results=1,
            order_by=f'metrics.{metric} {order}'
        )
        return runs[0] if runs else None

    # =========================================================================
    # Leaderboard Methods
    # =========================================================================

    def get_leaderboard(
        self,
        experiment_name: str,
        metric: str = 'test_recall_at_100',
        limit: int = 20
    ) -> List[Dict]:
        """
        Get experiment leaderboard sorted by metric.

        Args:
            experiment_name: Name of the experiment
            metric: Metric to sort by
            limit: Maximum number of entries

        Returns:
            List of leaderboard entries with rank, run info, and metrics
        """
        runs = self.list_runs(
            experiment_name=experiment_name,
            max_results=limit,
            order_by=f'metrics.{metric} DESC'
        )

        leaderboard = []
        for i, run in enumerate(runs):
            metrics = {m['key']: m['value'] for m in run.get('data', {}).get('metrics', [])}
            params = {p['key']: p['value'] for p in run.get('data', {}).get('params', [])}
            tags = {t['key']: t['value'] for t in run.get('data', {}).get('tags', [])}

            leaderboard.append({
                'rank': i + 1,
                'run_id': run['info']['run_id'],
                'run_name': tags.get('mlflow.runName', run['info']['run_id']),
                'status': run['info'].get('status'),
                'start_time': run['info'].get('start_time'),
                'metrics': metrics,
                'params': params,
                'tags': tags,
            })

        return leaderboard


# Convenience function for quick access
def get_mlflow_service() -> MLflowService:
    """Get a configured MLflow service instance."""
    return MLflowService()
