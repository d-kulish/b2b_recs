"""
Training Cache Service

Caches training history from GCS (training_metrics.json) into Django database for fast loading.
This reduces Training tab load time from minutes to <1 second.

The trainer saves metrics to GCS as training_metrics.json at training completion.
This service reads that file and caches it in Django DB.

Usage:
    from ml_platform.experiments.training_cache_service import TrainingCacheService

    cache_service = TrainingCacheService()

    # Cache at training completion
    cache_service.cache_training_history(quick_test)

    # Get cached or fetch fresh
    history = cache_service.get_training_history(quick_test)
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from django.utils import timezone

logger = logging.getLogger(__name__)


class TrainingCacheService:
    """
    Service to cache and retrieve training history from Django DB.

    Reads training metrics from GCS (training_metrics.json) and caches
    essential data (loss curves, final metrics, params) in Django DB.
    Histogram data is included in the cache for visualization.
    """

    # Epoch sampling interval (e.g., 5 = keep every 5th epoch)
    # For 100 epochs, this gives 20 data points
    EPOCH_SAMPLE_INTERVAL = 5

    def cache_training_history(self, quick_test) -> bool:
        """
        Fetch training history from GCS and store in quick_test.training_history_json.

        Reads training_metrics.json from the quick_test's GCS artifacts path.

        Args:
            quick_test: QuickTest model instance

        Returns:
            True if caching succeeded, False otherwise
        """
        # Read from GCS (training_metrics.json)
        if quick_test.gcs_artifacts_path:
            success = self._cache_from_gcs(quick_test)
            if success:
                return True

        logger.warning(
            f"QuickTest {quick_test.id}: Cannot cache training history - "
            f"no GCS artifacts path"
        )
        return False

    def _cache_from_gcs(self, quick_test) -> bool:
        """
        Read training_metrics.json from GCS and cache it.

        Args:
            quick_test: QuickTest model instance

        Returns:
            True if successful, False otherwise
        """
        try:
            from google.cloud import storage

            gcs_path = quick_test.gcs_artifacts_path
            if not gcs_path or not gcs_path.startswith('gs://'):
                return False

            # Parse GCS path
            path = gcs_path[5:]  # Remove 'gs://'
            bucket_name = path.split('/')[0]
            blob_path = '/'.join(path.split('/')[1:]) + '/training_metrics.json'

            # Read from GCS
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)

            if not blob.exists():
                logger.debug(
                    f"QuickTest {quick_test.id}: training_metrics.json not found at "
                    f"gs://{bucket_name}/{blob_path}"
                )
                return False

            content = blob.download_as_string().decode('utf-8')
            full_history = json.loads(content)

            if not full_history.get('available', False):
                logger.warning(
                    f"QuickTest {quick_test.id}: GCS metrics not available"
                )
                return False

            # Extract and cache essential data
            cached_data = self._extract_cacheable_data(full_history, quick_test)

            # Store in database
            quick_test.training_history_json = cached_data
            quick_test.save(update_fields=['training_history_json', 'updated_at'])

            logger.info(
                f"QuickTest {quick_test.id}: Cached training history from GCS "
                f"({len(cached_data.get('epochs', []))} epochs)"
            )
            return True

        except Exception as e:
            logger.debug(
                f"QuickTest {quick_test.id}: Could not read from GCS: {e}"
            )
            return False

    def get_training_history(self, quick_test) -> Dict:
        """
        Get training history, using cache if available.

        If cache exists, returns cached data immediately.
        If cache is missing, fetches from GCS, caches it, and returns.

        Args:
            quick_test: QuickTest model instance

        Returns:
            Training history dict suitable for UI rendering
        """
        # Try cache first
        if quick_test.training_history_json:
            logger.debug(f"QuickTest {quick_test.id}: Returning cached training history")
            return quick_test.training_history_json

        # Cache miss - fetch and cache
        logger.info(f"QuickTest {quick_test.id}: Cache miss, fetching from GCS/MLflow")

        if self.cache_training_history(quick_test):
            # Refresh from DB to get cached data
            quick_test.refresh_from_db(fields=['training_history_json'])
            return quick_test.training_history_json or self._empty_history()

        return self._empty_history()

    def _extract_cacheable_data(self, full_history: Dict, quick_test) -> Dict:
        """
        Extract essential data from full training history for caching.

        Excludes histogram data (fetched on-demand) and samples epochs.

        Args:
            full_history: Full training history from GCS (training_metrics.json)
            quick_test: QuickTest instance for additional metadata

        Returns:
            Cacheable training history dict
        """
        epochs = full_history.get('epochs', [])
        sampled_indices = self._get_sample_indices(epochs)
        sampled_epochs = [epochs[i] for i in sampled_indices] if epochs else []

        cached = {
            'cached_at': timezone.now().isoformat(),
            'mlflow_run_id': quick_test.mlflow_run_id,
            'available': True,

            # Sampled epochs
            'epochs': sampled_epochs,

            # Loss curves (sampled) - remap keys for UI compatibility
            'loss': self._remap_and_sample_loss(full_history.get('loss', {}), sampled_indices),

            # Gradient/weight norms (sampled) - keep same key as MLflow service
            'gradient': self._sample_dict_values(
                full_history.get('gradient', {}),
                sampled_indices
            ),

            # Weight stats without histograms (sampled)
            'weight_stats': self._extract_weight_stats(
                full_history.get('weight_stats', {}),
                sampled_indices
            ),

            # Gradient stats without histograms (sampled)
            'gradient_stats': self._extract_gradient_stats(
                full_history.get('gradient_stats', {}),
                sampled_indices
            ),

            # Final metrics (not sampled - single values)
            'final_metrics': full_history.get('final_metrics', {}),

            # Recall metrics (sampled)
            'metrics': self._sample_dict_values(full_history.get('metrics', {}), sampled_indices),

            # Training params from quick_test
            'params': {
                'epochs': quick_test.epochs,
                'batch_size': quick_test.batch_size,
                'learning_rate': float(quick_test.learning_rate) if quick_test.learning_rate else None,
                'optimizer': quick_test.model_config.optimizer if quick_test.model_config else None,
                'embedding_dim': quick_test.model_config.output_embedding_dim if quick_test.model_config else None,
            },

            # Flag indicating histogram data available via on-demand endpoint
            'histogram_available': self._has_histogram_data(full_history),
        }

        return cached

    def _get_sample_indices(self, epochs: List[int]) -> List[int]:
        """
        Get indices of epochs to keep after sampling.

        Keeps every Nth epoch plus always includes first and last.

        Args:
            epochs: List of epoch numbers

        Returns:
            List of indices to keep
        """
        if not epochs:
            return []

        n = len(epochs)
        interval = self.EPOCH_SAMPLE_INTERVAL

        if n <= interval:
            # Keep all if fewer than interval epochs
            return list(range(n))

        # Keep every Nth epoch
        indices = list(range(0, n, interval))

        # Ensure last epoch is included
        if (n - 1) not in indices:
            indices.append(n - 1)

        return sorted(indices)

    def _sample_list(self, data: List, indices: List[int]) -> List:
        """Sample list values at given indices."""
        if not data or not indices:
            return []
        return [data[i] for i in indices if i < len(data)]

    def _sample_dict_values(self, data: Dict[str, List], indices: List[int]) -> Dict[str, List]:
        """Sample all list values in a dict at given indices."""
        return {
            key: self._sample_list(values, indices)
            for key, values in data.items()
            if isinstance(values, list)
        }

    def _remap_and_sample_loss(self, loss_data: Dict[str, List], indices: List[int]) -> Dict[str, List]:
        """
        Remap loss keys from MetricsCollector format to UI-expected format and sample.

        MetricsCollector (Keras native):    UI expects (legacy MLflow format):
        - loss                              → train
        - val_loss                          → val
        - total_loss                        → total
        - val_total_loss                    → val_total
        - regularization_loss               → regularization
        - val_regularization_loss           → val_regularization
        """
        # Key mapping: new_key → old_key
        key_mapping = {
            'loss': 'train',
            'val_loss': 'val',
            'total_loss': 'total',
            'val_total_loss': 'val_total',
            'regularization_loss': 'regularization',
            'val_regularization_loss': 'val_regularization',
        }

        result = {}
        for old_key, values in loss_data.items():
            if not isinstance(values, list):
                continue
            # Remap key if it's in the mapping, otherwise keep as-is
            new_key = key_mapping.get(old_key, old_key)
            result[new_key] = self._sample_list(values, indices)

        return result

    def _extract_weight_stats(self, weight_stats: Dict, indices: List[int]) -> Dict:
        """Extract weight stats without histogram data (sampled)."""
        result = {}
        # Include rating_head for ranking models
        for tower in ['query', 'candidate', 'rating_head']:
            tower_data = weight_stats.get(tower, {})
            if tower_data:  # Only include if data exists
                result[tower] = {}
                for stat in ['mean', 'std', 'min', 'max']:
                    values = tower_data.get(stat, [])
                    if values:
                        result[tower][stat] = self._sample_list(values, indices)
                # Skip histogram - fetched on demand
        return result

    def _extract_gradient_stats(self, gradient_stats: Dict, indices: List[int]) -> Dict:
        """Extract gradient stats without histogram data (sampled)."""
        result = {}
        # Include rating_head for ranking models
        for tower in ['query', 'candidate', 'rating_head']:
            tower_data = gradient_stats.get(tower, {})
            if tower_data:  # Only include if data exists
                result[tower] = {}
                for stat in ['mean', 'std', 'min', 'max', 'norm']:
                    values = tower_data.get(stat, [])
                    if values:
                        result[tower][stat] = self._sample_list(values, indices)
                # Skip histogram - fetched on demand
        return result

    def _has_histogram_data(self, full_history: Dict) -> bool:
        """Check if histogram data is available in the full history."""
        weight_stats = full_history.get('weight_stats', {})
        # Include rating_head for ranking models
        for tower in ['query', 'candidate', 'rating_head']:
            if weight_stats.get(tower, {}).get('histogram'):
                return True

        gradient_stats = full_history.get('gradient_stats', {})
        # Include rating_head for ranking models
        for tower in ['query', 'candidate', 'rating_head']:
            if gradient_stats.get(tower, {}).get('histogram'):
                return True

        return False

    def _empty_history(self) -> Dict:
        """Return empty history structure for failed fetches."""
        return {
            'available': False,
            'message': 'Training history not available',
            'epochs': [],
            'loss': {},
            'gradient': {},
            'weight_stats': {},
            'gradient_stats': {},
            'final_metrics': {},
            'metrics': {},
            'params': {},
            'histogram_available': False,
        }

    def invalidate_cache(self, quick_test) -> None:
        """
        Clear cached training history.

        Useful if training history needs to be re-fetched.

        Args:
            quick_test: QuickTest model instance
        """
        quick_test.training_history_json = None
        quick_test.save(update_fields=['training_history_json', 'updated_at'])
        logger.info(f"QuickTest {quick_test.id}: Invalidated training history cache")
