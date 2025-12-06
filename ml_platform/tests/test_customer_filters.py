"""
Tests for Customer Filter functionality in DatasetStatsService.

These tests verify that the customer filter logic generates correct SQL
and can be executed against BigQuery.

Usage:
    python manage.py test ml_platform.tests.test_customer_filters -v 2

    Or run directly:
    python -m pytest ml_platform/tests/test_customer_filters.py -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'b2b_recs.settings')

import django
django.setup()

from ml_platform.datasets.services import DatasetStatsService


class TestCustomerFilterQueryGeneration(unittest.TestCase):
    """Test that customer filters generate correct SQL queries."""

    def setUp(self):
        """Set up mock BigQuery service."""
        # Create a mock model endpoint
        self.mock_endpoint = MagicMock()
        self.mock_endpoint.gcp_project_id = 'test-project'

        # Create service with mocked BigQuery client
        with patch('ml_platform.datasets.services.BigQueryService') as MockBQService:
            self.mock_bq = MockBQService.return_value
            self.mock_bq.client = MagicMock()
            self.mock_bq._get_full_table_ref = lambda x: f"test-project.{x}"
            self.service = DatasetStatsService(self.mock_endpoint)
            self.service.bq_service = self.mock_bq

    def test_top_customer_revenue_filter(self):
        """Test top customer revenue filter (Pareto-based) generates correct CTE."""
        filters = {
            'customer_filter': {
                'top_revenue': {
                    'customer_column': 'transactions.customer_id',
                    'revenue_column': 'transactions.amount',
                    'percent': 80
                }
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount', 'trans_date']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify CTE is generated
        self.assertIn('top_customers AS', query)
        self.assertIn('SUM(`amount`) as total_revenue', query)
        self.assertIn('running_total', query)
        self.assertIn('grand_total * 0.8', query)

        # Verify WHERE clause references the CTE
        self.assertIn('IN (SELECT `customer_id` FROM top_customers)', query)

        # Verify applied_filters
        self.assertEqual(applied_filters['customers']['type'], 'multiple')
        self.assertEqual(applied_filters['customers']['filters'][0]['type'], 'top_revenue')
        self.assertEqual(applied_filters['customers']['filters'][0]['percent'], 80)

    def test_transaction_count_filter_greater_than(self):
        """Test transaction count filter with greater_than condition."""
        filters = {
            'customer_filter': {
                'aggregation_filters': [
                    {
                        'type': 'transaction_count',
                        'customer_column': 'transactions.customer_id',
                        'filter_type': 'greater_than',
                        'value': 5
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify CTE with HAVING COUNT(*) > 5
        self.assertIn('customer_agg_1 AS', query)
        self.assertIn('GROUP BY `customer_id`', query)
        self.assertIn('HAVING COUNT(*) > 5', query)

        # Verify WHERE clause
        self.assertIn('IN (SELECT `customer_id` FROM customer_agg_1)', query)

        # Verify applied_filters
        self.assertEqual(applied_filters['customers']['filters'][0]['type'], 'transaction_count')
        self.assertEqual(applied_filters['customers']['filters'][0]['filter_type'], 'greater_than')

    def test_transaction_count_filter_range(self):
        """Test transaction count filter with range condition."""
        filters = {
            'customer_filter': {
                'aggregation_filters': [
                    {
                        'type': 'transaction_count',
                        'customer_column': 'transactions.customer_id',
                        'filter_type': 'range',
                        'min': 2,
                        'max': 10
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify CTE with HAVING COUNT(*) >= 2 AND COUNT(*) <= 10
        self.assertIn('HAVING COUNT(*) >= 2 AND COUNT(*) <= 10', query)

    def test_spending_filter_greater_than(self):
        """Test spending filter (SUM-based) with greater_than condition."""
        filters = {
            'customer_filter': {
                'aggregation_filters': [
                    {
                        'type': 'spending',
                        'customer_column': 'transactions.customer_id',
                        'amount_column': 'transactions.amount',
                        'filter_type': 'greater_than',
                        'value': 1000
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify CTE with HAVING SUM(amount) > 1000
        self.assertIn('customer_agg_1 AS', query)
        self.assertIn('HAVING SUM(`amount`) > 1000', query)

        # Verify applied_filters
        self.assertEqual(applied_filters['customers']['filters'][0]['type'], 'spending')

    def test_spending_filter_range(self):
        """Test spending filter with range condition."""
        filters = {
            'customer_filter': {
                'aggregation_filters': [
                    {
                        'type': 'spending',
                        'customer_column': 'transactions.customer_id',
                        'amount_column': 'transactions.amount',
                        'filter_type': 'range',
                        'min': 100,
                        'max': 5000
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify CTE with SUM range
        self.assertIn('HAVING SUM(`amount`) >= 100 AND SUM(`amount`) <= 5000', query)

    def test_customer_category_filter_include(self):
        """Test customer category filter with include mode."""
        filters = {
            'customer_filter': {
                'category_filters': [
                    {
                        'column': 'transactions.category',
                        'mode': 'include',
                        'values': ['Electronics', 'Clothing']
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'category']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify WHERE clause with IN
        self.assertIn("`transactions`.`category` IN ('Electronics', 'Clothing')", query)

        # Verify applied_filters
        self.assertEqual(applied_filters['customers']['filters'][0]['type'], 'category')
        self.assertEqual(applied_filters['customers']['filters'][0]['mode'], 'include')

    def test_customer_category_filter_exclude(self):
        """Test customer category filter with exclude mode."""
        filters = {
            'customer_filter': {
                'category_filters': [
                    {
                        'column': 'transactions.category',
                        'mode': 'exclude',
                        'values': ['Returned', 'Cancelled']
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'category']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify WHERE clause with NOT IN
        self.assertIn("`transactions`.`category` NOT IN ('Returned', 'Cancelled')", query)

    def test_customer_numeric_filter_range(self):
        """Test customer numeric filter with range."""
        filters = {
            'customer_filter': {
                'numeric_filters': [
                    {
                        'column': 'transactions.quantity',
                        'filter_type': 'range',
                        'min': 1,
                        'max': 100,
                        'include_nulls': False
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'quantity']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify WHERE clause with range and NOT NULL
        self.assertIn('`transactions`.`quantity` >= 1', query)
        self.assertIn('`transactions`.`quantity` <= 100', query)
        self.assertIn('IS NOT NULL', query)

    def test_customer_numeric_filter_greater_than(self):
        """Test customer numeric filter with greater_than."""
        filters = {
            'customer_filter': {
                'numeric_filters': [
                    {
                        'column': 'transactions.amount',
                        'filter_type': 'greater_than',
                        'value': 50,
                        'include_nulls': True
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify WHERE clause with > and OR NULL
        self.assertIn('> 50 OR', query)
        self.assertIn('IS NULL', query)

    def test_customer_date_filter_relative(self):
        """Test customer date filter with relative option."""
        filters = {
            'customer_filter': {
                'date_filters': [
                    {
                        'column': 'transactions.trans_date',
                        'date_type': 'relative',
                        'relative_option': 'last_30_days',
                        'include_nulls': False
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'trans_date']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify WHERE clause with DATE_SUB
        self.assertIn('DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)', query)
        self.assertIn('IS NOT NULL', query)

    def test_customer_date_filter_range(self):
        """Test customer date filter with date range."""
        filters = {
            'customer_filter': {
                'date_filters': [
                    {
                        'column': 'transactions.trans_date',
                        'date_type': 'range',
                        'start_date': '2024-01-01',
                        'end_date': '2024-12-31',
                        'include_nulls': True
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'trans_date']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify WHERE clause with date range
        self.assertIn("'2024-01-01'", query)
        self.assertIn("'2024-12-31'", query)
        self.assertIn('IS NULL', query)  # include_nulls=True

    def test_combined_customer_filters(self):
        """Test multiple customer filters combined (AND logic)."""
        filters = {
            'customer_filter': {
                'top_revenue': {
                    'customer_column': 'transactions.customer_id',
                    'revenue_column': 'transactions.amount',
                    'percent': 90
                },
                'aggregation_filters': [
                    {
                        'type': 'transaction_count',
                        'customer_column': 'transactions.customer_id',
                        'filter_type': 'greater_than',
                        'value': 3
                    }
                ],
                'category_filters': [
                    {
                        'column': 'transactions.category',
                        'mode': 'include',
                        'values': ['Premium']
                    }
                ]
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount', 'category']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify all filters are present
        self.assertIn('top_customers AS', query)  # Top revenue CTE
        self.assertIn('customer_agg_1 AS', query)  # Transaction count CTE
        self.assertIn("IN ('Premium')", query)  # Category filter

        # Verify applied_filters has all 3 filters
        self.assertEqual(applied_filters['customers']['count'], 3)

    def test_legacy_min_transactions_filter(self):
        """Test legacy min_transactions format still works."""
        filters = {
            'customer_filter': {
                'type': 'min_transactions',
                'column': 'customer_id',
                'value': 2
            }
        }

        query, applied_filters = self.service._build_filtered_query(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount']},
            secondary_tables=[],
            join_config={},
            filters=filters
        )

        # Verify legacy CTE is generated
        self.assertIn('active_customers AS', query)
        self.assertIn('HAVING COUNT(*) >= 2', query)

        # Verify applied_filters
        self.assertEqual(applied_filters['customers']['filters'][0]['type'], 'min_transactions')


class TestCustomerFilterWithBigQuery(unittest.TestCase):
    """
    Integration tests that actually run queries against BigQuery.

    These tests require:
    1. Valid GCP credentials
    2. Access to raw_data.transactions table

    Skip these tests if BigQuery is not available.
    """

    @classmethod
    def setUpClass(cls):
        """Check if BigQuery is available."""
        try:
            from google.cloud import bigquery
            from ml_platform.models import ModelEndpoint

            # Try to get a model endpoint with GCP config
            endpoint = ModelEndpoint.objects.filter(
                gcp_project_id__isnull=False
            ).first()

            if not endpoint:
                raise unittest.SkipTest("No model endpoint with GCP config found")

            cls.endpoint = endpoint
            cls.bq_available = True
        except Exception as e:
            cls.bq_available = False
            raise unittest.SkipTest(f"BigQuery not available: {e}")

    def test_customer_filter_query_executes(self):
        """Test that generated query actually executes in BigQuery."""
        if not self.bq_available:
            self.skipTest("BigQuery not available")

        from ml_platform.datasets.services import DatasetStatsService

        service = DatasetStatsService(self.endpoint)

        # Test with transaction count filter
        result = service.get_dataset_stats(
            primary_table='raw_data.transactions',
            selected_columns={'raw_data.transactions': ['customer_id', 'amount', 'trans_date']},
            filters={
                'customer_filter': {
                    'aggregation_filters': [
                        {
                            'type': 'transaction_count',
                            'customer_column': 'transactions.customer_id',
                            'filter_type': 'greater_than',
                            'value': 2
                        }
                    ]
                }
            }
        )

        self.assertEqual(result['status'], 'success')
        self.assertIn('summary', result)
        self.assertIn('total_rows', result['summary'])
        print(f"\nTransaction count > 2 filter: {result['summary']['total_rows']} rows")


if __name__ == '__main__':
    unittest.main()
