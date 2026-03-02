#!/usr/bin/env python3
"""
Integration test for proposed temporal split fix.

This test validates the complete flow:
1. SQL query generation with actual BigQueryService
2. Query wrapping for split-specific queries
3. TFX configuration validation (if TFX available)

Run with: python tests/test_proposed_fix_integration.py
"""

import os
import sys
import unittest

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class TestIntegrationWithBigQueryService(unittest.TestCase):
    """Test integration with actual BigQueryService."""

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

    def _get_test_dataset(self):
        """Get a test dataset."""
        from ml_platform.models import Dataset, ModelEndpoint
        try:
            ds = Dataset.objects.first()
            endpoint = ModelEndpoint.objects.first()
            if ds and endpoint:
                return ds, endpoint
        except Exception:
            pass
        return None, None

    def _find_date_column(self, ds):
        """Find a date column from the dataset."""
        for table, columns in ds.selected_columns.items():
            for col_name in columns:
                if any(x in col_name.lower() for x in ['date', 'time', 'timestamp']):
                    return col_name
        return None

    def test_generate_split_queries_time_holdout(self):
        """Test generating split-specific queries for time_holdout strategy."""
        from ml_platform.datasets.services import BigQueryService

        ds, endpoint = self._get_test_dataset()
        if not ds or not endpoint:
            self.skipTest("No test dataset available")

        date_column = self._find_date_column(ds)
        if not date_column:
            self.skipTest("No date column in test dataset")

        bq_service = BigQueryService(endpoint, ds)

        # Generate the base query (existing method - includes 'split' column)
        base_query = bq_service.generate_training_query(
            dataset=ds,
            split_strategy='time_holdout',
            holdout_days=3,  # Using parameter from wizard
            date_column=date_column,
            sample_percent=10,  # Small sample for testing
        )

        print("\n=== BASE QUERY (with split column) ===")
        print(f"Length: {len(base_query)} chars")
        has_split = "AS split" in base_query
        has_train = "'train'" in base_query
        has_eval = "'eval'" in base_query
        has_test = "'test'" in base_query
        has_interval = "INTERVAL 3 DAY" in base_query
        print(f"Contains 'AS split': {has_split}")
        print(f"Contains 'train': {has_train}")
        print(f"Contains 'eval': {has_eval}")
        print(f"Contains 'test': {has_test}")
        print(f"Contains 'INTERVAL 3 DAY': {has_interval}")

        # Verify base query has split column
        self.assertIn("AS split", base_query)
        self.assertIn("'train'", base_query)
        self.assertIn("'eval'", base_query)
        self.assertIn("'test'", base_query)

        # Now wrap for each split (proposed fix)
        def make_split_query(base: str, split_name: str) -> str:
            return f"WITH base AS (\n{base}\n)\nSELECT * EXCEPT(split) FROM base WHERE split = '{split_name}'"

        train_query = make_split_query(base_query, 'train')
        eval_query = make_split_query(base_query, 'eval')
        test_query = make_split_query(base_query, 'test')

        print("\n=== SPLIT-SPECIFIC QUERIES (proposed fix) ===")
        print(f"Train query length: {len(train_query)}")
        print(f"Eval query length: {len(eval_query)}")
        print(f"Test query length: {len(test_query)}")

        # Verify each split query
        self.assertIn("WHERE split = 'train'", train_query)
        self.assertIn("WHERE split = 'eval'", eval_query)
        self.assertIn("WHERE split = 'test'", test_query)
        self.assertIn("EXCEPT(split)", train_query)  # split column removed from output

        print("\n=== INTEGRATION TEST PASSED ===")
        print("Split-specific queries generated successfully from BigQueryService output")

    def test_generate_split_queries_strict_time(self):
        """Test generating split-specific queries for strict_time strategy."""
        from ml_platform.datasets.services import BigQueryService

        ds, endpoint = self._get_test_dataset()
        if not ds or not endpoint:
            self.skipTest("No test dataset available")

        date_column = self._find_date_column(ds)
        if not date_column:
            self.skipTest("No date column in test dataset")

        bq_service = BigQueryService(endpoint, ds)

        # Generate with custom days (from wizard parameters)
        base_query = bq_service.generate_training_query(
            dataset=ds,
            split_strategy='strict_time',
            date_column=date_column,
            train_days=48,   # Parameter from wizard
            val_days=9,      # Parameter from wizard
            test_days=3,     # Parameter from wizard
            sample_percent=10,
        )

        print("\n=== STRICT_TIME BASE QUERY ===")
        print(f"Length: {len(base_query)} chars")

        # Verify parameters are used (not hardcoded)
        self.assertIn("INTERVAL 3 DAY", base_query)   # test_days
        self.assertIn("INTERVAL 12 DAY", base_query)  # val_days + test_days
        self.assertIn("INTERVAL 60 DAY", base_query)  # total days

        # Generate split-specific queries
        def make_split_query(base: str, split_name: str) -> str:
            return f"WITH base AS (\n{base}\n)\nSELECT * EXCEPT(split) FROM base WHERE split = '{split_name}'"

        queries = {
            'train': make_split_query(base_query, 'train'),
            'eval': make_split_query(base_query, 'eval'),
            'test': make_split_query(base_query, 'test'),
        }

        for name, q in queries.items():
            self.assertIn(f"WHERE split = '{name}'", q)

        print("=== STRICT_TIME INTEGRATION TEST PASSED ===")

    def test_random_split_unchanged(self):
        """Verify random split doesn't need split-specific queries."""
        from ml_platform.datasets.services import BigQueryService

        ds, endpoint = self._get_test_dataset()
        if not ds or not endpoint:
            self.skipTest("No test dataset available")

        bq_service = BigQueryService(endpoint, ds)

        # Random split doesn't add 'split' column
        base_query = bq_service.generate_training_query(
            dataset=ds,
            split_strategy='random',
            sample_percent=10,
        )

        print("\n=== RANDOM SPLIT QUERY ===")
        print(f"Length: {len(base_query)} chars")
        print(f"Contains 'AS split': {'AS split' in base_query}")

        # Random split should NOT have 'split' column
        self.assertNotIn("AS split", base_query)

        print("=== RANDOM SPLIT UNCHANGED - NO SPLIT COLUMN ===")
        print("Random split continues to use hash_buckets (not affected by fix)")


class TestTFXInputConfigValidity(unittest.TestCase):
    """Test that TFX input_config approach is valid."""

    def test_tfx_bigquery_example_gen_accepts_input_config(self):
        """Verify BigQueryExampleGen can accept input_config with multiple splits."""
        try:
            from tfx.extensions.google_cloud_big_query.example_gen.component import BigQueryExampleGen
            from tfx.proto import example_gen_pb2
            tfx_available = True
        except ImportError:
            tfx_available = False
            self.skipTest("TFX not installed")

        # Create input_config with multiple splits (proposed approach)
        input_config = example_gen_pb2.Input(splits=[
            example_gen_pb2.Input.Split(name='train', pattern='SELECT 1 AS col WHERE 1=1'),
            example_gen_pb2.Input.Split(name='eval', pattern='SELECT 1 AS col WHERE 1=2'),
            example_gen_pb2.Input.Split(name='test', pattern='SELECT 1 AS col WHERE 1=3'),
        ])

        # Verify we can create BigQueryExampleGen with input_config
        # (This just tests that the component accepts the config - doesn't run the query)
        try:
            example_gen = BigQueryExampleGen(
                input_config=input_config,
                custom_config={'project': 'test-project'}
            )
            print("\n=== TFX BigQueryExampleGen accepts input_config ===")
            print(f"Component created: {type(example_gen).__name__}")
            print(f"Input splits: {[s.name for s in input_config.splits]}")
            self.assertIsNotNone(example_gen)
        except Exception as e:
            self.fail(f"BigQueryExampleGen rejected input_config: {e}")

    def test_tfx_input_config_output_split_names(self):
        """Test that TFX generates correct output split names from input_config."""
        try:
            from tfx.proto import example_gen_pb2
            from tfx.components.example_gen import utils
            tfx_available = True
        except ImportError:
            self.skipTest("TFX not installed")

        # Create input_config with multiple splits
        input_config = example_gen_pb2.Input(splits=[
            example_gen_pb2.Input.Split(name='train', pattern='Q1'),
            example_gen_pb2.Input.Split(name='eval', pattern='Q2'),
            example_gen_pb2.Input.Split(name='test', pattern='Q3'),
        ])

        # Empty output_config (no splits defined, no partition_feature_name)
        output_config = example_gen_pb2.Output()

        # This is the function that was failing with partition_feature_name
        # With input_config splits, it should take the elif branch instead
        try:
            split_names = utils.generate_output_split_names(input_config, output_config)
            print("\n=== TFX generate_output_split_names() SUCCESS ===")
            print(f"Generated split names: {split_names}")
            self.assertEqual(split_names, ['train', 'eval', 'test'])
        except RuntimeError as e:
            if 'hash buckets' in str(e):
                self.fail(f"Still hitting the hash_buckets error: {e}")
            raise

    def test_proposed_fix_avoids_buggy_code_path(self):
        """Verify the proposed fix avoids the buggy code path."""
        try:
            from tfx.proto import example_gen_pb2
            from tfx.components.example_gen import utils
        except ImportError:
            self.skipTest("TFX not installed")

        # BUGGY configuration (current - fails):
        # - Single input split
        # - output_config with partition_feature_name
        buggy_input = example_gen_pb2.Input(splits=[
            example_gen_pb2.Input.Split(name='single', pattern='Q')
        ])
        buggy_output = example_gen_pb2.Output(
            split_config=example_gen_pb2.SplitConfig(
                splits=[
                    example_gen_pb2.SplitConfig.Split(name='train'),
                    example_gen_pb2.SplitConfig.Split(name='eval'),
                    example_gen_pb2.SplitConfig.Split(name='test'),
                ],
                partition_feature_name='split'
            )
        )

        # Check if partition_feature_name is actually set
        # (This tests our hypothesis about the bug)
        print("\n=== TESTING BUGGY CONFIGURATION ===")
        print(f"partition_feature_name value: '{buggy_output.split_config.partition_feature_name}'")
        print(f"partition_feature_name bool: {bool(buggy_output.split_config.partition_feature_name)}")

        # If partition_feature_name is truthy, the buggy config should work
        # If it's falsy (empty string), it will fail
        if buggy_output.split_config.partition_feature_name:
            print("partition_feature_name IS set locally - bug may be in serialization/deserialization")
        else:
            print("partition_feature_name IS NOT set - bug confirmed locally")

        # FIXED configuration (proposed - should work):
        fixed_input = example_gen_pb2.Input(splits=[
            example_gen_pb2.Input.Split(name='train', pattern='Q1'),
            example_gen_pb2.Input.Split(name='eval', pattern='Q2'),
            example_gen_pb2.Input.Split(name='test', pattern='Q3'),
        ])
        fixed_output = example_gen_pb2.Output()  # Empty output_config

        print("\n=== TESTING FIXED CONFIGURATION ===")
        try:
            split_names = utils.generate_output_split_names(fixed_input, fixed_output)
            print(f"SUCCESS! Split names: {split_names}")
            self.assertEqual(split_names, ['train', 'eval', 'test'])
        except RuntimeError as e:
            self.fail(f"Fixed configuration failed: {e}")


def run_all_tests():
    """Run all integration tests."""
    print("="*70)
    print("INTEGRATION TESTS FOR PROPOSED FIX")
    print("="*70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationWithBigQueryService))
    suite.addTests(loader.loadTestsFromTestCase(TestTFXInputConfigValidity))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "="*70)
    print("INTEGRATION TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.wasSuccessful():
        print("\n*** ALL INTEGRATION TESTS PASSED ***")
    else:
        print("\n*** SOME TESTS FAILED ***")
        for test, traceback in result.failures + result.errors:
            print(f"\nFailed: {test}")
            print(traceback)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
