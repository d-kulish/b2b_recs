#!/usr/bin/env python3
"""
Unit Tests for Split Strategies

Tests that all three split strategies (random, time_holdout, strict_time) are
correctly implemented in both SQL generation and TFX pipeline configuration.

Usage:
    # Run all tests
    python -m pytest tests/test_split_strategies.py -v

    # Run specific test
    python -m pytest tests/test_split_strategies.py::TestInlineScript -v

    # Run without Django (inline script tests only)
    python tests/test_split_strategies.py --no-django
"""

import argparse
import ast
import re
import sys
import os
import unittest

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class TestHashBucketsRatios(unittest.TestCase):
    """Test that hash_buckets configuration produces correct split ratios."""

    def test_random_split_ratios(self):
        """Verify 16/3/1 hash_buckets = 80/15/5 split."""
        train_buckets = 16
        eval_buckets = 3
        test_buckets = 1
        total = train_buckets + eval_buckets + test_buckets

        self.assertEqual(total, 20, "Total buckets should be 20")
        self.assertAlmostEqual(train_buckets / total, 0.80, places=2)
        self.assertAlmostEqual(eval_buckets / total, 0.15, places=2)
        self.assertAlmostEqual(test_buckets / total, 0.05, places=2)

    def test_old_broken_ratios(self):
        """Document the old broken 80/20 split (for reference)."""
        # This was the old configuration - documenting it here for clarity
        old_train_buckets = 8
        old_eval_buckets = 2
        old_total = old_train_buckets + old_eval_buckets

        self.assertEqual(old_total, 10)
        self.assertAlmostEqual(old_train_buckets / old_total, 0.80, places=2)
        self.assertAlmostEqual(old_eval_buckets / old_total, 0.20, places=2)
        # Note: No test split in old configuration!


class TestInlineScript(unittest.TestCase):
    """Test the inline compile script in services.py."""

    @classmethod
    def setUpClass(cls):
        """Extract and parse the inline script."""
        services_path = os.path.join(
            project_root, 'ml_platform', 'experiments', 'services.py'
        )
        with open(services_path, 'r') as f:
            content = f.read()

        # Find the _get_compile_script method and extract its content
        # The script is a triple-quoted string returned by the method
        match = re.search(
            r"def _get_compile_script\(self\) -> str:\s*\"\"\".*?\"\"\"\s*return '''(.+?)'''",
            content,
            re.DOTALL
        )
        if not match:
            raise ValueError("Could not find _get_compile_script method in services.py")

        cls.inline_script = match.group(1)

    def test_transform_pb2_import_exists(self):
        """Verify transform_pb2 is imported."""
        self.assertIn(
            'transform_pb2',
            self.inline_script,
            "transform_pb2 must be imported for splits_config"
        )

    def test_transform_splits_config_exists(self):
        """Verify Transform component has splits_config."""
        self.assertIn(
            'splits_config=transform_pb2.SplitsConfig',
            self.inline_script,
            "Transform must have splits_config parameter"
        )

    def test_transform_analyze_excludes_test(self):
        """Verify analyze does NOT include 'test' (to avoid data leakage)."""
        # Find the analyze parameter
        analyze_match = re.search(
            r"analyze=\[([^\]]+)\]",
            self.inline_script
        )
        self.assertIsNotNone(analyze_match, "Could not find analyze parameter")

        analyze_content = analyze_match.group(1)
        # Should have train and eval, but NOT test
        self.assertIn("'train'", analyze_content)
        self.assertIn("'eval'", analyze_content)
        self.assertNotIn("'test'", analyze_content,
                        "analyze should NOT include 'test' to avoid data leakage!")

    def test_transform_transform_includes_test(self):
        """Verify transform includes 'test' (so TFRecords are created)."""
        # Find the transform parameter (different from analyze)
        transform_match = re.search(
            r"transform=\[([^\]]+)\]",
            self.inline_script
        )
        self.assertIsNotNone(transform_match, "Could not find transform parameter")

        transform_content = transform_match.group(1)
        # Should have train, eval, AND test
        self.assertIn("'train'", transform_content)
        self.assertIn("'eval'", transform_content)
        self.assertIn("'test'", transform_content,
                     "transform MUST include 'test' so TFRecords are created")

    def test_random_strategy_hash_buckets(self):
        """Verify random strategy uses 16/3/1 hash_buckets."""
        # Find the random strategy configuration
        self.assertIn('hash_buckets=16', self.inline_script,
                     "Random strategy train split should use 16 hash_buckets")
        self.assertIn('hash_buckets=3', self.inline_script,
                     "Random strategy eval split should use 3 hash_buckets")
        self.assertIn('hash_buckets=1', self.inline_script,
                     "Random strategy test split should use 1 hash_bucket")

    def test_random_strategy_creates_test_split(self):
        """Verify random strategy creates a test split."""
        # Look for the test split in the random strategy section
        # Find the section for random strategy
        random_section_match = re.search(
            r"if split_strategy == 'random':.*?else:",
            self.inline_script,
            re.DOTALL
        )
        self.assertIsNotNone(random_section_match)
        random_section = random_section_match.group(0)

        self.assertIn('name="test"', random_section,
                     "Random strategy must define a test split")

    def test_temporal_strategy_uses_input_config(self):
        """Verify temporal strategies use input_config with multiple splits (not partition_feature_name)."""
        # The new implementation uses input_config instead of partition_feature_name
        # to avoid the buggy code path in TFX
        self.assertIn(
            "input_config",
            self.inline_script,
            "Temporal strategies must use input_config with multiple splits"
        )
        # Should NOT use partition_feature_name='split' as a configuration
        # (it may appear in comments explaining what we're avoiding)
        self.assertNotIn(
            "partition_feature_name='split'",
            self.inline_script,
            "Temporal strategies should NOT use partition_feature_name='split' (buggy in TFX)"
        )

    def test_temporal_strategy_defines_three_splits(self):
        """Verify temporal strategies define train/eval/test splits via input_config."""
        # Verify all three Input.Split declarations exist for temporal strategies
        # Each split should reference split_queries dict
        train_split = re.search(
            r"Input\.Split\(name='train',\s*pattern=split_queries\['train'\]\)",
            self.inline_script
        )
        self.assertIsNotNone(train_split,
                            "Could not find Input.Split for 'train' split")

        eval_split = re.search(
            r"Input\.Split\(name='eval',\s*pattern=split_queries\['eval'\]\)",
            self.inline_script
        )
        self.assertIsNotNone(eval_split,
                            "Could not find Input.Split for 'eval' split")

        test_split = re.search(
            r"Input\.Split\(name='test',\s*pattern=split_queries\['test'\]\)",
            self.inline_script
        )
        self.assertIsNotNone(test_split,
                            "Could not find Input.Split for 'test' split")


class TestSQLGeneration(unittest.TestCase):
    """Test SQL generation for different split strategies.

    These tests require Django to be set up.
    """

    @classmethod
    def setUpClass(cls):
        """Set up Django."""
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        try:
            import django
            django.setup()
            cls.django_available = True
        except Exception as e:
            cls.django_available = False
            cls.django_error = str(e)

    def setUp(self):
        if not self.django_available:
            self.skipTest(f"Django not available: {self.django_error}")

    def _get_bq_service(self):
        """Get BigQueryService instance for testing."""
        from ml_platform.models import Dataset, ModelEndpoint
        from ml_platform.datasets.services import BigQueryService

        # Use a test dataset - adjust ID as needed
        try:
            ds = Dataset.objects.first()
            endpoint = ModelEndpoint.objects.first()
            if ds and endpoint:
                return BigQueryService(endpoint, ds), ds
        except Exception:
            pass
        return None, None

    def _find_date_column(self, ds):
        """Find a date column from the dataset's selected columns."""
        # selected_columns is a dict: {table_name: [col1, col2, ...]}
        # We need to find a column that's likely a date
        for table, columns in ds.selected_columns.items():
            for col_name in columns:
                # Common date column names
                if any(x in col_name.lower() for x in ['date', 'time', 'timestamp']):
                    return col_name
        return None

    def test_random_split_no_split_column(self):
        """Verify random split SQL does NOT add a 'split' column."""
        bq_service, ds = self._get_bq_service()
        if not bq_service:
            self.skipTest("No test dataset available")

        query = bq_service.generate_training_query(
            dataset=ds,
            split_strategy='random',
            sample_percent=100
        )

        # Random strategy should NOT have a 'split' column
        # (BigQueryExampleGen handles splitting via hash_buckets)
        self.assertNotIn('AS split', query,
                        "Random split should NOT add 'split' column to SQL")

    def test_time_holdout_has_split_column(self):
        """Verify time_holdout SQL adds 'split' column."""
        bq_service, ds = self._get_bq_service()
        if not bq_service:
            self.skipTest("No test dataset available")

        date_column = self._find_date_column(ds)
        if not date_column:
            self.skipTest("No suitable date column in test dataset")

        query = bq_service.generate_training_query(
            dataset=ds,
            split_strategy='time_holdout',
            holdout_days=1,
            date_column=date_column,
            sample_percent=100
        )

        # Time holdout should have a 'split' column
        self.assertIn('AS split', query,
                     "Time holdout should add 'split' column to SQL")
        # Should have all three split values
        self.assertIn("'train'", query)
        self.assertIn("'eval'", query)
        self.assertIn("'test'", query)

    def test_strict_time_has_split_column(self):
        """Verify strict_time SQL adds 'split' column with temporal boundaries."""
        bq_service, ds = self._get_bq_service()
        if not bq_service:
            self.skipTest("No test dataset available")

        date_column = self._find_date_column(ds)
        if not date_column:
            self.skipTest("No suitable date column in test dataset")

        query = bq_service.generate_training_query(
            dataset=ds,
            split_strategy='strict_time',
            date_column=date_column,
            train_days=48,
            val_days=9,
            test_days=3,
            sample_percent=100
        )

        # Strict time should have a 'split' column
        self.assertIn('AS split', query,
                     "Strict time should add 'split' column to SQL")
        # Should have all three split values
        self.assertIn("'train'", query)
        self.assertIn("'eval'", query)
        self.assertIn("'test'", query)

    def test_time_holdout_uses_max_date(self):
        """Verify time_holdout uses MAX date from data, not CURRENT_DATE()."""
        bq_service, ds = self._get_bq_service()
        if not bq_service:
            self.skipTest("No test dataset available")

        date_column = self._find_date_column(ds)
        if not date_column:
            self.skipTest("No suitable date column in test dataset")

        query = bq_service.generate_training_query(
            dataset=ds,
            split_strategy='time_holdout',
            holdout_days=1,
            date_column=date_column,
            sample_percent=100
        )

        # Should use MAX date calculation, not CURRENT_DATE()
        self.assertIn('max_date_ref', query.lower(),
                     "Time holdout should use max_date_ref CTE")
        self.assertNotIn('CURRENT_DATE()', query,
                        "Time holdout should NOT use CURRENT_DATE()")


def run_no_django_tests():
    """Run tests that don't require Django."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add tests that don't need Django
    suite.addTests(loader.loadTestsFromTestCase(TestHashBucketsRatios))
    suite.addTests(loader.loadTestsFromTestCase(TestInlineScript))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description="Test split strategies")
    parser.add_argument("--no-django", action="store_true",
                       help="Run only tests that don't require Django")
    args, remaining = parser.parse_known_args()

    if args.no_django:
        sys.exit(run_no_django_tests())
    else:
        # Run all tests via pytest or unittest
        # Pass remaining args to unittest
        unittest.main(argv=[''] + remaining)


if __name__ == "__main__":
    main()
