"""
TPE-inspired hyperparameter analysis for experiments.

This module provides analysis of experiment hyperparameters using a TPE
(Tree-structured Parzen Estimator) inspired probability ratio scoring.

Instead of simple average ranking (which is misleading with small samples),
this approach calculates the probability that a parameter value leads to
"good" outcomes vs "bad" outcomes, with Laplace smoothing to handle
low sample sizes.

Key benefits:
- Handles small sample sizes gracefully via smoothing
- Based on proven HPO methodology
- More robust to outliers than simple averaging
- Provides confidence indicators
"""

import logging
from collections import defaultdict
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class HyperparameterAnalyzer:
    """
    TPE-inspired hyperparameter analysis for experiments.

    Analyzes completed experiments to determine which parameter values
    are most associated with good outcomes (top 30% by recall@100).
    """

    # Top 30% of experiments by recall are considered "good"
    GOOD_PERCENTILE = 30

    # Laplace smoothing parameters
    # Higher values = more conservative (shrinks toward equal probability)
    LAPLACE_ALPHA = 1  # Prior for good count
    LAPLACE_BETA = 1   # Prior for bad count

    # Confidence thresholds based on sample count
    HIGH_CONFIDENCE_THRESHOLD = 5
    MEDIUM_CONFIDENCE_THRESHOLD = 3

    # Parameter definitions organized by category
    # Each parameter has: field (model attribute), label (display name)
    # Optional 'getter' function for computed fields
    PARAMETERS = {
        'training': [
            {'field': 'optimizer', 'label': 'Optimizer'},
            {'field': 'learning_rate', 'label': 'Learning Rate'},
            {'field': 'batch_size', 'label': 'Batch Size'},
            {'field': 'epochs', 'label': 'Epochs'},
            {'field': 'output_embedding_dim', 'label': 'Output Dim'},
            {'field': 'retrieval_algorithm', 'label': 'Algorithm'},
            {'field': 'top_k', 'label': 'Top-K'},
            {'field': 'split_strategy', 'label': 'Split Strategy'},
            {'field': 'data_sample_percent', 'label': 'Sample %', 'format': lambda v: f"{v}%"},
        ],
        'model': [
            {'field': 'buyer_tower_structure', 'label': 'Buyer Tower', 'getter': '_get_buyer_tower_structure'},
            {'field': 'product_tower_structure', 'label': 'Product Tower', 'getter': '_get_product_tower_structure'},
            {'field': 'buyer_activation', 'label': 'Buyer Activation', 'getter': '_get_buyer_activation'},
            {'field': 'product_activation', 'label': 'Product Activation', 'getter': '_get_product_activation'},
            {'field': 'buyer_l2_category', 'label': 'Buyer L2 Reg', 'getter': '_get_buyer_l2_category'},
            {'field': 'product_l2_category', 'label': 'Product L2 Reg', 'getter': '_get_product_l2_category'},
            {'field': 'buyer_total_params', 'label': 'Buyer Params', 'getter': '_get_buyer_total_params'},
            {'field': 'product_total_params', 'label': 'Product Params', 'getter': '_get_product_total_params'},
            # Ranking tower fields (computed from model_config)
            {'field': 'ranking_tower_structure', 'label': 'Ranking Tower', 'getter': '_get_ranking_tower_structure', 'ranking_only': True},
            {'field': 'ranking_total_params', 'label': 'Ranking Params', 'getter': '_get_ranking_total_params', 'ranking_only': True},
        ],
        'features': [
            {'field': 'buyer_tensor_dim', 'label': 'Buyer Vector Size'},
            {'field': 'product_tensor_dim', 'label': 'Product Vector Size'},
            {'field': 'buyer_feature_count', 'label': 'Buyer Features'},
            {'field': 'product_feature_count', 'label': 'Product Features'},
            {'field': 'buyer_cross_count', 'label': 'Buyer Crosses'},
            {'field': 'product_cross_count', 'label': 'Product Crosses'},
        ],
        'dataset': [
            {'field': 'dataset_row_count', 'label': 'Dataset Size', 'format': lambda v: f"{v:,}" if v else 'N/A'},
        ],
    }

    # Filter array fields that need special handling (similar to feature_details)
    FILTER_FIELDS = {
        'date_filters': 'dataset_date_filters',
        'customer_filters': 'dataset_customer_filters',
        'product_filters': 'dataset_product_filters',
    }

    def analyze(self, experiments: List[Any], model_type: str = 'retrieval') -> Dict:
        """
        Analyze all parameters using TPE-inspired scoring.

        Args:
            experiments: List of QuickTest instances (completed experiments)
            model_type: 'retrieval' (higher recall = better), 'ranking' (lower RMSE = better),
                        or 'hybrid' (uses recall as primary metric, but has ranking tower)

        Returns:
            Dictionary with analysis results organized by category:
            {
                'training': [
                    {
                        'param': 'Learning Rate',
                        'field': 'learning_rate',
                        'values': [
                            {
                                'value': '0.005',
                                'tpe_score': 2.3,
                                'avg_recall': 0.085,
                                'best_recall': 0.092,
                                'count': 5,
                                'good_count': 4,
                                'confidence': 'high'
                            },
                            ...
                        ]
                    },
                    ...
                ],
                'model': [...],
                'features': [...],
                'dataset': [...],
                'good_threshold': 0.072,
                'total_experiments': 15,
                'good_experiments': 5
            }
        """
        self._model_type = model_type

        # Filter experiments with valid metric (recall@100 for retrieval, test_rmse for ranking)
        experiments_with_metric = [
            exp for exp in experiments
            if self._get_metric(exp) is not None
        ]

        if not experiments_with_metric:
            return self._empty_result()

        # Calculate good threshold
        # For retrieval: higher recall = better, so top 30% = highest values
        # For ranking: lower RMSE = better, so top 30% = lowest values
        metrics = [self._get_metric(exp) for exp in experiments_with_metric]

        if model_type == 'ranking':
            # Lower is better - sort ascending, top 30% are the lowest values
            metrics.sort()
        else:
            # Higher is better - sort descending, top 30% are the highest values
            metrics.sort(reverse=True)

        # Calculate the index for 30% of experiments
        good_count = max(1, int(len(metrics) * self.GOOD_PERCENTILE / 100))
        good_threshold = metrics[good_count - 1] if metrics else 0

        result = {
            'good_threshold': round(good_threshold, 4),
            'total_experiments': len(experiments_with_metric),
            'good_experiments': good_count,
        }

        # Analyze each category
        for category, params in self.PARAMETERS.items():
            result[category] = []
            for param_def in params:
                # Skip ranking_only fields when not analyzing ranking or hybrid models
                if param_def.get('ranking_only') and model_type not in ('ranking', 'hybrid'):
                    continue

                analysis = self._analyze_parameter(
                    experiments_with_metric,
                    param_def,
                    good_threshold
                )
                # Only include parameters that have data
                if analysis['values']:
                    result[category].append(analysis)

        # Analyze feature details (name + dimension combinations)
        result['feature_details'] = self._analyze_feature_details(
            experiments_with_metric,
            good_threshold
        )

        # Analyze dataset filter details (date/customer/product filters)
        result['filter_details'] = self._analyze_filter_details(
            experiments_with_metric,
            good_threshold
        )

        return result

    def _analyze_parameter(
        self,
        experiments: List[Any],
        param_def: Dict,
        good_threshold: float
    ) -> Dict:
        """
        Analyze a single parameter using TPE-inspired scoring.

        Args:
            experiments: List of QuickTest instances
            param_def: Parameter definition dict with 'field', 'label', optional 'format'
            good_threshold: Metric value that defines "good" experiments

        Returns:
            Dictionary with parameter analysis:
            {
                'param': 'Learning Rate',
                'field': 'learning_rate',
                'values': [...]
            }
        """
        field = param_def['field']
        format_fn = param_def.get('format')
        getter_name = param_def.get('getter')

        # Group experiments by parameter value
        groups = defaultdict(list)
        for exp in experiments:
            # Use custom getter if provided, otherwise use getattr
            if getter_name:
                getter_fn = getattr(self, getter_name, None)
                value = getter_fn(exp) if getter_fn else None
            else:
                value = getattr(exp, field, None)

            if value is None:
                continue

            metric = self._get_metric(exp)
            if metric is not None:
                groups[value].append(metric)

        # Calculate TPE score for each value
        values = []
        for value, metrics in groups.items():
            # For ranking: lower is better (metric <= threshold is "good")
            # For retrieval: higher is better (metric >= threshold is "good")
            if self._model_type == 'ranking':
                n_good = sum(1 for m in metrics if m <= good_threshold)
            else:
                n_good = sum(1 for m in metrics if m >= good_threshold)

            n_bad = len(metrics) - n_good
            n_total = len(metrics)

            # TPE score with Laplace smoothing
            # P(good | value) / P(bad | value)
            # With smoothing: (n_good + alpha) / (n_bad + beta)
            p_good = (n_good + self.LAPLACE_ALPHA) / (n_total + self.LAPLACE_ALPHA + self.LAPLACE_BETA)
            p_bad = (n_bad + self.LAPLACE_BETA) / (n_total + self.LAPLACE_ALPHA + self.LAPLACE_BETA)

            # Avoid division by zero
            tpe_score = p_good / max(p_bad, 0.001)

            # Format display value
            display_value = format_fn(value) if format_fn else self._format_value(value)

            # For ranking: best metric is lowest, for retrieval: best is highest
            if self._model_type == 'ranking':
                best_metric = round(min(metrics), 4)
            else:
                best_metric = round(max(metrics), 4)

            values.append({
                'value': display_value,
                'raw_value': value,  # Keep raw value for sorting numerics
                'tpe_score': round(tpe_score, 2),
                'avg_recall': round(sum(metrics) / len(metrics), 4),  # Keep 'avg_recall' key for compatibility
                'best_recall': best_metric,  # Keep 'best_recall' key for compatibility
                'count': n_total,
                'good_count': n_good,
                'confidence': self._get_confidence(n_total),
            })

        # Sort by TPE score descending
        values.sort(key=lambda x: x['tpe_score'], reverse=True)

        return {
            'param': param_def['label'],
            'field': field,
            'values': values,
        }

    def _analyze_feature_details(
        self,
        experiments: List[Any],
        good_threshold: float
    ) -> Dict:
        """
        Analyze feature details (name + dimension) to find which features
        are most associated with good experiment outcomes.

        Args:
            experiments: List of QuickTest instances
            good_threshold: Recall value that defines "good" experiments

        Returns:
            Dictionary with feature details analysis:
            {
                'buyer': [{'value': 'customer_id 32D', 'tpe_score': 2.1, 'count': 12}, ...],
                'product': [...],
                'buyer_crosses': [...],
                'product_crosses': [...]
            }
        """
        result = {
            'buyer': [],
            'product': [],
            'buyer_crosses': [],
            'product_crosses': []
        }

        # Analyze each feature type
        feature_fields = [
            ('buyer', 'buyer_feature_details'),
            ('product', 'product_feature_details'),
            ('buyer_crosses', 'buyer_cross_details'),
            ('product_crosses', 'product_cross_details'),
        ]

        for result_key, field_name in feature_fields:
            # Group metrics by feature "name dim" key
            groups = defaultdict(list)

            for exp in experiments:
                details = getattr(exp, field_name, None)
                if not details:
                    continue

                metric = self._get_metric(exp)
                if metric is None:
                    continue

                # Each feature in the list contributes to its group
                for feature in details:
                    name = feature.get('name', 'unknown')
                    dim = feature.get('dim', 0)
                    key = f"{name} {dim}D"
                    groups[key].append(metric)

            # Calculate TPE scores for each feature
            values = []
            for feature_key, metrics in groups.items():
                # For ranking: lower is better, for retrieval: higher is better
                if self._model_type == 'ranking':
                    n_good = sum(1 for m in metrics if m <= good_threshold)
                else:
                    n_good = sum(1 for m in metrics if m >= good_threshold)

                n_bad = len(metrics) - n_good
                n_total = len(metrics)

                p_good = (n_good + self.LAPLACE_ALPHA) / (n_total + self.LAPLACE_ALPHA + self.LAPLACE_BETA)
                p_bad = (n_bad + self.LAPLACE_BETA) / (n_total + self.LAPLACE_ALPHA + self.LAPLACE_BETA)
                tpe_score = p_good / max(p_bad, 0.001)

                values.append({
                    'value': feature_key,
                    'tpe_score': round(tpe_score, 2),
                    'avg_recall': round(sum(metrics) / len(metrics), 4),  # Keep key name for compatibility
                    'count': n_total,
                    'good_count': n_good,
                    'confidence': self._get_confidence(n_total),
                })

            # Sort by TPE score descending, limit to top 5
            values.sort(key=lambda x: x['tpe_score'], reverse=True)
            result[result_key] = values[:5]

        return result

    def _analyze_filter_details(
        self,
        experiments: List[Any],
        good_threshold: float
    ) -> Dict:
        """
        Analyze dataset filter descriptions to find which filters
        are most associated with good experiment outcomes.

        Args:
            experiments: List of QuickTest instances
            good_threshold: Recall value that defines "good" experiments

        Returns:
            Dictionary with filter details analysis:
            {
                'date_filters': [{'value': 'Rolling 60 days', 'tpe_score': 2.1, 'count': 12}, ...],
                'customer_filters': [{'value': 'city = CHERNIGIV', 'tpe_score': 1.8, 'count': 8}, ...],
                'product_filters': [{'value': 'Top 80% products', 'tpe_score': 2.0, 'count': 10}, ...]
            }
        """
        result = {
            'date_filters': [],
            'customer_filters': [],
            'product_filters': [],
        }

        # Analyze each filter type
        for result_key, field_name in self.FILTER_FIELDS.items():
            # Group metrics by filter description
            groups = defaultdict(list)

            for exp in experiments:
                filters = getattr(exp, field_name, None)
                if not filters:
                    # Include "None" as a value for experiments without this filter type
                    filters = ['None']

                metric = self._get_metric(exp)
                if metric is None:
                    continue

                # Each filter in the list contributes to its group
                for filter_desc in filters:
                    groups[filter_desc].append(metric)

            # Calculate TPE scores for each filter
            values = []
            for filter_desc, metrics in groups.items():
                # For ranking: lower is better, for retrieval: higher is better
                if self._model_type == 'ranking':
                    n_good = sum(1 for m in metrics if m <= good_threshold)
                else:
                    n_good = sum(1 for m in metrics if m >= good_threshold)

                n_bad = len(metrics) - n_good
                n_total = len(metrics)

                p_good = (n_good + self.LAPLACE_ALPHA) / (n_total + self.LAPLACE_ALPHA + self.LAPLACE_BETA)
                p_bad = (n_bad + self.LAPLACE_BETA) / (n_total + self.LAPLACE_ALPHA + self.LAPLACE_BETA)
                tpe_score = p_good / max(p_bad, 0.001)

                values.append({
                    'value': filter_desc,
                    'tpe_score': round(tpe_score, 2),
                    'avg_recall': round(sum(metrics) / len(metrics), 4),  # Keep key name for compatibility
                    'count': n_total,
                    'good_count': n_good,
                    'confidence': self._get_confidence(n_total),
                })

            # Sort by TPE score descending
            values.sort(key=lambda x: x['tpe_score'], reverse=True)
            result[result_key] = values

        return result

    def _get_recall(self, experiment) -> Optional[float]:
        """
        Extract recall@100 from experiment.

        Tries multiple sources:
        1. Direct field (recall_at_100)
        2. Cached training history JSON

        Args:
            experiment: QuickTest instance

        Returns:
            Recall@100 value or None if not available
        """
        # Try direct field first
        if experiment.recall_at_100 is not None:
            return float(experiment.recall_at_100)

        # Try cached training history
        if experiment.training_history_json:
            history = experiment.training_history_json
            final_metrics = history.get('final_metrics', {})

            # Try different key formats
            for key in ['test_recall_at_100', 'recall_at_100', 'recall@100']:
                if key in final_metrics and final_metrics[key] is not None:
                    return float(final_metrics[key])

        return None

    def _get_test_rmse(self, experiment) -> Optional[float]:
        """
        Extract test_rmse from experiment.

        Tries multiple sources:
        1. Direct field (test_rmse)
        2. Cached training history JSON

        Args:
            experiment: QuickTest instance

        Returns:
            Test RMSE value or None if not available
        """
        # Try direct field first
        if experiment.test_rmse is not None:
            return float(experiment.test_rmse)

        # Try cached training history
        if experiment.training_history_json:
            history = experiment.training_history_json
            final_metrics = history.get('final_metrics', {})

            # Try different key formats
            for key in ['test_rmse']:
                if key in final_metrics and final_metrics[key] is not None:
                    return float(final_metrics[key])

        return None

    def _get_metric(self, experiment) -> Optional[float]:
        """
        Get the appropriate metric based on model type.

        For retrieval: returns recall@100 (higher is better)
        For ranking: returns test_rmse (lower is better)

        Args:
            experiment: QuickTest instance

        Returns:
            Metric value or None if not available
        """
        if getattr(self, '_model_type', 'retrieval') == 'ranking':
            return self._get_test_rmse(experiment)
        return self._get_recall(experiment)

    def _get_ranking_tower_structure(self, experiment) -> Optional[str]:
        """
        Get ranking tower structure from model_config.

        Returns structure like '128→64→32→1' or None if not available.
        """
        try:
            model_config = experiment.model_config
            if not model_config:
                return None

            rating_head_layers = model_config.rating_head_layers
            if not rating_head_layers:
                return None

            # Extract units from dense layers
            units = [layer['units'] for layer in rating_head_layers if layer.get('type') == 'dense']
            return '→'.join(map(str, units)) if units else None
        except Exception:
            return None

    def _get_ranking_total_params(self, experiment) -> Optional[int]:
        """
        Estimate total params in ranking tower from model_config.

        Returns estimated parameter count or None if not available.
        """
        try:
            model_config = experiment.model_config
            if not model_config:
                return None

            rating_head_layers = model_config.rating_head_layers
            if not rating_head_layers:
                return None

            # Input to rating head is concatenated embeddings (2 * output_embedding_dim)
            output_dim = model_config.output_embedding_dim or 32
            prev_dim = output_dim * 2

            total_params = 0
            for layer in rating_head_layers:
                if layer.get('type') == 'dense':
                    units = layer['units']
                    total_params += prev_dim * units + units  # weights + bias
                    prev_dim = units

            return total_params if total_params > 0 else None
        except Exception:
            return None

    def _get_buyer_tower_structure(self, experiment) -> Optional[str]:
        """Get buyer tower structure, falling back to model_config if QuickTest field is NULL."""
        # Try direct field first
        if experiment.buyer_tower_structure:
            return experiment.buyer_tower_structure

        # Fall back to model_config
        try:
            model_config = experiment.model_config
            if model_config and model_config.buyer_tower_layers:
                units = [layer['units'] for layer in model_config.buyer_tower_layers if layer.get('type') == 'dense']
                return '→'.join(map(str, units)) if units else None
        except Exception:
            pass
        return None

    def _get_product_tower_structure(self, experiment) -> Optional[str]:
        """Get product tower structure, falling back to model_config if QuickTest field is NULL."""
        if experiment.product_tower_structure:
            return experiment.product_tower_structure

        try:
            model_config = experiment.model_config
            if model_config and model_config.product_tower_layers:
                units = [layer['units'] for layer in model_config.product_tower_layers if layer.get('type') == 'dense']
                return '→'.join(map(str, units)) if units else None
        except Exception:
            pass
        return None

    def _get_buyer_activation(self, experiment) -> Optional[str]:
        """Get buyer activation, falling back to model_config if QuickTest field is NULL."""
        if experiment.buyer_activation:
            return experiment.buyer_activation

        try:
            model_config = experiment.model_config
            if model_config and model_config.buyer_tower_layers:
                activations = [layer.get('activation') for layer in model_config.buyer_tower_layers
                               if layer.get('type') == 'dense' and layer.get('activation')]
                return activations[0] if activations else None
        except Exception:
            pass
        return None

    def _get_product_activation(self, experiment) -> Optional[str]:
        """Get product activation, falling back to model_config if QuickTest field is NULL."""
        if experiment.product_activation:
            return experiment.product_activation

        try:
            model_config = experiment.model_config
            if model_config and model_config.product_tower_layers:
                activations = [layer.get('activation') for layer in model_config.product_tower_layers
                               if layer.get('type') == 'dense' and layer.get('activation')]
                return activations[0] if activations else None
        except Exception:
            pass
        return None

    def _get_buyer_l2_category(self, experiment) -> Optional[str]:
        """Get buyer L2 reg category, falling back to model_config if QuickTest field is NULL."""
        if experiment.buyer_l2_category:
            return experiment.buyer_l2_category

        try:
            model_config = experiment.model_config
            if model_config and model_config.buyer_tower_layers:
                max_l2 = max((layer.get('l2_reg', 0) or 0) for layer in model_config.buyer_tower_layers)
                return get_l2_category(max_l2)
        except Exception:
            pass
        return None

    def _get_product_l2_category(self, experiment) -> Optional[str]:
        """Get product L2 reg category, falling back to model_config if QuickTest field is NULL."""
        if experiment.product_l2_category:
            return experiment.product_l2_category

        try:
            model_config = experiment.model_config
            if model_config and model_config.product_tower_layers:
                max_l2 = max((layer.get('l2_reg', 0) or 0) for layer in model_config.product_tower_layers)
                return get_l2_category(max_l2)
        except Exception:
            pass
        return None

    def _get_buyer_total_params(self, experiment) -> Optional[int]:
        """Get buyer tower params, falling back to model_config if QuickTest field is NULL."""
        if experiment.buyer_total_params:
            return experiment.buyer_total_params

        try:
            model_config = experiment.model_config
            fc = experiment.feature_config
            if model_config and model_config.buyer_tower_layers and fc:
                input_dim = fc.buyer_tensor_dim or 100
                return estimate_tower_params(model_config.buyer_tower_layers, input_dim)
        except Exception:
            pass
        return None

    def _get_product_total_params(self, experiment) -> Optional[int]:
        """Get product tower params, falling back to model_config if QuickTest field is NULL."""
        if experiment.product_total_params:
            return experiment.product_total_params

        try:
            model_config = experiment.model_config
            fc = experiment.feature_config
            if model_config and model_config.product_tower_layers and fc:
                input_dim = fc.product_tensor_dim or 100
                return estimate_tower_params(model_config.product_tower_layers, input_dim)
        except Exception:
            pass
        return None

    def _get_confidence(self, count: int) -> str:
        """
        Determine confidence level based on sample count.

        Args:
            count: Number of experiments with this parameter value

        Returns:
            'high', 'medium', or 'low'
        """
        if count >= self.HIGH_CONFIDENCE_THRESHOLD:
            return 'high'
        elif count >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            return 'medium'
        else:
            return 'low'

    def _format_value(self, value: Any) -> str:
        """
        Format a value for display.

        Args:
            value: Raw parameter value

        Returns:
            Formatted string representation
        """
        if isinstance(value, float):
            # Format floats nicely (remove trailing zeros)
            if value == int(value):
                return str(int(value))
            elif value < 0.01:
                return f"{value:.4f}"
            elif value < 1:
                return f"{value:.3f}"
            else:
                return f"{value:.2f}"
        elif isinstance(value, int):
            # Format large integers with commas
            if value >= 1000:
                return f"{value:,}"
            return str(value)
        else:
            return str(value)

    def _empty_result(self) -> Dict:
        """
        Return empty result structure when no experiments are available.

        Returns:
            Dictionary with empty analysis
        """
        return {
            'training': [],
            'model': [],
            'features': [],
            'dataset': [],
            'good_threshold': 0,
            'total_experiments': 0,
            'good_experiments': 0,
        }


def get_l2_category(l2_value: Optional[float]) -> str:
    """
    Convert L2 regularization value to category.

    Args:
        l2_value: L2 regularization value (float)

    Returns:
        Category string: 'none', 'light', 'medium', or 'heavy'
    """
    if l2_value is None or l2_value == 0:
        return 'none'
    elif l2_value <= 0.001:
        return 'light'
    elif l2_value <= 0.01:
        return 'medium'
    else:
        return 'heavy'


def get_tower_structure(layers: List[Dict]) -> str:
    """
    Extract tower structure string from layer config.

    Args:
        layers: List of layer config dicts

    Returns:
        Structure string like '128→64→32'
    """
    units = [layer['units'] for layer in layers if layer.get('type') == 'dense']
    return '→'.join(map(str, units)) if units else 'Empty'


def get_primary_activation(layers: List[Dict]) -> Optional[str]:
    """
    Extract primary activation function from layer config.

    Uses the most common activation across dense layers.

    Args:
        layers: List of layer config dicts

    Returns:
        Activation function name or None
    """
    activations = [
        layer.get('activation')
        for layer in layers
        if layer.get('type') == 'dense' and layer.get('activation')
    ]
    if not activations:
        return None

    # Return most common activation
    from collections import Counter
    return Counter(activations).most_common(1)[0][0]


def get_max_l2_reg(layers: List[Dict]) -> Optional[float]:
    """
    Get maximum L2 regularization value from layer config.

    Args:
        layers: List of layer config dicts

    Returns:
        Maximum L2 reg value or None
    """
    l2_values = [
        layer.get('l2_reg', 0)
        for layer in layers
        if layer.get('type') == 'dense'
    ]
    return max(l2_values) if l2_values else None


def estimate_tower_params(layers: List[Dict], input_dim: int) -> int:
    """
    Estimate trainable parameters in a tower.

    Args:
        layers: List of layer config dicts
        input_dim: Input dimension (tensor dim from FeatureConfig)

    Returns:
        Estimated parameter count
    """
    total = 0
    prev_dim = input_dim

    for layer in layers:
        if layer.get('type') == 'dense':
            units = layer['units']
            # weights + bias
            total += prev_dim * units + units
            prev_dim = units

    return total
