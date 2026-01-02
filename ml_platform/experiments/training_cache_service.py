"""
Training Cache Service

Caches training history from MLflow into Django database for fast loading.
This reduces Training tab load time from 2-3 minutes to <1 second.

Usage:
    from ml_platform.experiments.training_cache_service import TrainingCacheService

    cache_service = TrainingCacheService()

    # Cache at training completion
    cache_service.cache_training_history(quick_test)

    # Get cached or fetch fresh
    history = cache_service.get_training_history(quick_test)
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from django.utils import timezone

logger = logging.getLogger(__name__)


class TrainingCacheService:
    """
    Service to cache and retrieve training history from Django DB.

    Caches essential training data (loss curves, final metrics, params)
    but skips histogram data to keep cache size small (~5-10KB per experiment).
    Histogram data is fetched on-demand from MLflow when needed.
    """

    # Epoch sampling interval (e.g., 5 = keep every 5th epoch)
    # For 100 epochs, this gives 20 data points
    EPOCH_SAMPLE_INTERVAL = 5

    def cache_training_history(self, quick_test) -> bool:
        """
        Fetch training history from MLflow and store in quick_test.training_history_json.

        Args:
            quick_test: QuickTest model instance

        Returns:
            True if caching succeeded, False otherwise
        """
        if not quick_test.mlflow_run_id:
            logger.warning(
                f"QuickTest {quick_test.id}: Cannot cache training history - no mlflow_run_id"
            )
            return False

        try:
            from .mlflow_service import MLflowService

            mlflow_service = MLflowService()
            full_history = mlflow_service.get_training_history(quick_test.mlflow_run_id)

            if not full_history.get('available', False):
                logger.warning(
                    f"QuickTest {quick_test.id}: MLflow history not available - "
                    f"{full_history.get('message', 'unknown reason')}"
                )
                return False

            # Extract and cache essential data (without histograms)
            cached_data = self._extract_cacheable_data(full_history, quick_test)

            # Store in database
            quick_test.training_history_json = cached_data
            quick_test.save(update_fields=['training_history_json', 'updated_at'])

            logger.info(
                f"QuickTest {quick_test.id}: Cached training history "
                f"({len(cached_data.get('epochs', []))} epochs)"
            )
            return True

        except Exception as e:
            logger.exception(
                f"QuickTest {quick_test.id}: Failed to cache training history: {e}"
            )
            return False

    def get_training_history(self, quick_test) -> Dict:
        """
        Get training history, using cache if available.

        If cache exists, returns cached data immediately.
        If cache is missing, fetches from MLflow, caches it, and returns.

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
        logger.info(f"QuickTest {quick_test.id}: Cache miss, fetching from MLflow")

        if self.cache_training_history(quick_test):
            # Refresh from DB to get cached data
            quick_test.refresh_from_db(fields=['training_history_json'])
            return quick_test.training_history_json or self._empty_history()

        return self._empty_history()

    def _extract_cacheable_data(self, full_history: Dict, quick_test) -> Dict:
        """
        Extract essential data from full MLflow history for caching.

        Excludes histogram data (fetched on-demand) and samples epochs.

        Args:
            full_history: Full training history from MLflowService
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

            # Loss curves (sampled)
            'loss': self._sample_dict_values(full_history.get('loss', {}), sampled_indices),

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

    def _extract_weight_stats(self, weight_stats: Dict, indices: List[int]) -> Dict:
        """Extract weight stats without histogram data (sampled)."""
        result = {}
        for tower in ['query', 'candidate']:
            tower_data = weight_stats.get(tower, {})
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
        for tower in ['query', 'candidate']:
            tower_data = gradient_stats.get(tower, {})
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
        for tower in ['query', 'candidate']:
            if weight_stats.get(tower, {}).get('histogram'):
                return True

        gradient_stats = full_history.get('gradient_stats', {})
        for tower in ['query', 'candidate']:
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
