"""
Baseline Tests for ETL Functionality

These tests establish the baseline behavior of ETL-related views and APIs.
Run BEFORE and AFTER migration to verify nothing broke during refactoring.

Usage:
    # Before migration - save baseline
    python manage.py test ml_platform.tests.test_etl_baseline -v 2

    # After migration - verify same behavior
    python manage.py test ml_platform.tests.test_etl_baseline -v 2
"""
from django.test import TestCase, Client
from django.urls import reverse, resolve
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import json

from ml_platform.models import (
    ModelEndpoint,
    ETLConfiguration,
    DataSource,
    DataSourceTable,
    Connection,
    ETLRun,
)


class ETLPageViewsTests(TestCase):
    """Tests for ETL page views (HTML rendering)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class."""
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        cls.model = ModelEndpoint.objects.create(
            name='Test Model',
            description='Test model for ETL baseline tests',
            created_by=cls.user,
            status='draft'
        )
        cls.etl_config = ETLConfiguration.objects.create(
            model_endpoint=cls.model,
            schedule_type='manual'
        )

        # Create a connection for testing
        cls.connection = Connection.objects.create(
            model_endpoint=cls.model,
            name='Test PostgreSQL Connection',
            source_type='postgresql',
            source_host='localhost',
            source_port=5432,
            source_database='testdb',
            source_username='testuser'
        )

        # Create a data source
        cls.data_source = DataSource.objects.create(
            etl_config=cls.etl_config,
            connection=cls.connection,
            name='Test ETL Job',
            source_type='postgresql',
            is_enabled=True
        )

        # Create a table configuration
        cls.table = DataSourceTable.objects.create(
            data_source=cls.data_source,
            source_table_name='users',
            dest_table_name='raw_users',
            dest_dataset='raw_data',
            sync_mode='replace',
            is_enabled=True
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    # === PAGE LOAD TESTS ===

    def test_etl_page_loads_successfully(self):
        """ETL page should return 200 status code."""
        response = self.client.get(reverse('model_etl', args=[self.model.id]))
        self.assertEqual(response.status_code, 200)

    def test_etl_page_contains_expected_content(self):
        """ETL page should contain key elements."""
        response = self.client.get(reverse('model_etl', args=[self.model.id]))
        # Check for ETL-related content
        self.assertContains(response, 'ETL')
        # Check that model context is passed
        self.assertEqual(response.context['model'], self.model)

    def test_etl_page_requires_authentication(self):
        """ETL page should redirect unauthenticated users to login."""
        self.client.logout()
        response = self.client.get(reverse('model_etl', args=[self.model.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_etl_page_404_for_invalid_model(self):
        """ETL page should return 404 for non-existent model."""
        response = self.client.get(reverse('model_etl', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_etl_page_shows_data_sources(self):
        """ETL page should display configured data sources."""
        response = self.client.get(reverse('model_etl', args=[self.model.id]))
        self.assertIn('data_sources', response.context)

    def test_etl_page_shows_recent_runs(self):
        """ETL page should display recent ETL runs."""
        # Create an ETL run
        ETLRun.objects.create(
            etl_config=self.etl_config,
            model_endpoint=self.model,
            data_source=self.data_source,
            status='completed',
            started_at=timezone.now() - timedelta(hours=1),
            completed_at=timezone.now()
        )

        response = self.client.get(reverse('model_etl', args=[self.model.id]))
        self.assertIn('recent_runs', response.context)


class ETLAPIEndpointsTests(TestCase):
    """Tests for ETL REST API endpoints (JSON responses)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        cls.model = ModelEndpoint.objects.create(
            name='Test Model API',
            description='Test model for API tests',
            created_by=cls.user,
            status='draft'
        )
        cls.etl_config = ETLConfiguration.objects.create(
            model_endpoint=cls.model,
            schedule_type='manual'
        )
        cls.connection = Connection.objects.create(
            model_endpoint=cls.model,
            name='Test Connection',
            source_type='postgresql',
            source_host='localhost',
            source_port=5432,
            source_database='testdb'
        )
        cls.data_source = DataSource.objects.create(
            etl_config=cls.etl_config,
            connection=cls.connection,
            name='API Test Job',
            source_type='postgresql',
            is_enabled=True
        )
        cls.table = DataSourceTable.objects.create(
            data_source=cls.data_source,
            source_table_name='orders',
            dest_table_name='raw_orders',
            dest_dataset='raw_data',
            sync_mode='replace'
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    # === JOB NAME CHECK API ===

    def test_check_job_name_returns_json(self):
        """Job name check API should return JSON response."""
        response = self.client.post(
            reverse('api_etl_check_job_name', args=[self.model.id]),
            data=json.dumps({'name': 'unique_test_job'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['exists'])

    def test_check_job_name_detects_duplicate(self):
        """Job name check API should detect existing job names."""
        response = self.client.post(
            reverse('api_etl_check_job_name', args=[self.model.id]),
            data=json.dumps({'name': 'API Test Job'}),  # Existing job name
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertTrue(data['exists'])

    def test_check_job_name_requires_name(self):
        """Job name check API should require name parameter."""
        response = self.client.post(
            reverse('api_etl_check_job_name', args=[self.model.id]),
            data=json.dumps({'name': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    # === TOGGLE ENABLED API ===

    def test_toggle_enabled_works(self):
        """Toggle enabled API should update ETL config."""
        response = self.client.post(
            reverse('api_etl_toggle_enabled', args=[self.model.id]),
            data=json.dumps({'enabled': True}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['is_enabled'])

        # Verify in database
        self.etl_config.refresh_from_db()
        self.assertTrue(self.etl_config.is_enabled)

    # === GET SOURCE API ===

    def test_get_source_returns_details(self):
        """Get source API should return source details."""
        response = self.client.get(
            reverse('api_etl_get_source', args=[self.data_source.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('source', data)
        self.assertEqual(data['source']['name'], 'API Test Job')
        self.assertEqual(data['source']['source_type'], 'postgresql')

    def test_get_source_includes_tables(self):
        """Get source API should include table configurations."""
        response = self.client.get(
            reverse('api_etl_get_source', args=[self.data_source.id])
        )
        data = response.json()
        self.assertIn('tables', data['source'])
        self.assertEqual(len(data['source']['tables']), 1)
        self.assertEqual(data['source']['tables'][0]['source_table_name'], 'orders')

    def test_get_source_error_for_invalid_id(self):
        """Get source API should return error for non-existent source."""
        response = self.client.get(
            reverse('api_etl_get_source', args=[99999])
        )
        # API catches Http404 and returns 400 with error message
        self.assertIn(response.status_code, [400, 404])
        if response.status_code == 400:
            data = response.json()
            self.assertEqual(data['status'], 'error')

    # === RUN STATUS API ===

    def test_run_status_returns_details(self):
        """Run status API should return run details."""
        run = ETLRun.objects.create(
            etl_config=self.etl_config,
            model_endpoint=self.model,
            data_source=self.data_source,
            status='completed',
            started_at=timezone.now() - timedelta(minutes=10),
            completed_at=timezone.now(),
            total_rows_extracted=1000,
            rows_loaded=1000
        )

        response = self.client.get(
            reverse('api_etl_run_status', args=[run.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(data['total_rows_extracted'], 1000)

    # === API AUTHENTICATION ===

    def test_api_requires_authentication(self):
        """API endpoints should require authentication."""
        self.client.logout()

        endpoints = [
            ('api_etl_check_job_name', [self.model.id], 'POST'),
            ('api_etl_toggle_enabled', [self.model.id], 'POST'),
            ('api_etl_get_source', [self.data_source.id], 'GET'),
        ]

        for url_name, args, method in endpoints:
            if method == 'POST':
                response = self.client.post(
                    reverse(url_name, args=args),
                    data='{}',
                    content_type='application/json'
                )
            else:
                response = self.client.get(reverse(url_name, args=args))

            # Should redirect to login (302) or return 401/403
            self.assertIn(response.status_code, [302, 401, 403],
                f"{url_name} should require authentication")


class ETLURLResolutionTests(TestCase):
    """Tests to verify all ETL URLs resolve correctly."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        cls.model = ModelEndpoint.objects.create(
            name='URL Test Model',
            created_by=cls.user
        )
        cls.etl_config = ETLConfiguration.objects.create(
            model_endpoint=cls.model
        )
        cls.data_source = DataSource.objects.create(
            etl_config=cls.etl_config,
            name='URL Test Source',
            source_type='postgresql'
        )

    def test_etl_page_urls_resolve(self):
        """ETL page URLs should resolve to correct view."""
        url = reverse('model_etl', args=[self.model.id])
        self.assertIsNotNone(url)
        self.assertIn(f'/models/{self.model.id}/etl/', url)

    def test_etl_api_urls_resolve(self):
        """All ETL API URLs should resolve correctly."""
        api_urls = [
            ('api_etl_add_source', [self.model.id]),
            ('api_etl_save_draft_source', [self.model.id]),
            ('api_etl_check_job_name', [self.model.id]),
            ('api_etl_toggle_enabled', [self.model.id]),
            ('api_etl_run_now', [self.model.id]),
            ('api_etl_get_source', [self.data_source.id]),
            ('api_etl_update_source', [self.data_source.id]),
            ('api_etl_run_source', [self.data_source.id]),
            ('api_etl_delete_source', [self.data_source.id]),
            ('api_etl_toggle_pause', [self.data_source.id]),
            ('api_etl_edit_source', [self.data_source.id]),
            ('api_etl_available_columns', [self.data_source.id]),
        ]

        for url_name, args in api_urls:
            try:
                url = reverse(url_name, args=args)
                self.assertIsNotNone(url, f"{url_name} should resolve")
            except Exception as e:
                self.fail(f"Failed to resolve {url_name}: {e}")

    def test_etl_runner_api_urls_resolve(self):
        """ETL Runner API URLs should resolve correctly."""
        runner_urls = [
            ('api_etl_job_config', [self.data_source.id]),
            ('api_etl_trigger_now', [self.data_source.id]),
            ('api_etl_scheduler_webhook', [self.data_source.id]),
        ]

        for url_name, args in runner_urls:
            try:
                url = reverse(url_name, args=args)
                self.assertIsNotNone(url, f"{url_name} should resolve")
            except Exception as e:
                self.fail(f"Failed to resolve {url_name}: {e}")


class ConnectionAPIBaselineTests(TestCase):
    """Baseline tests for connection management API."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        cls.model = ModelEndpoint.objects.create(
            name='Connection Test Model',
            created_by=cls.user,
            status='draft'
        )
        cls.connection = Connection.objects.create(
            model_endpoint=cls.model,
            name='Test DB Connection',
            source_type='postgresql',
            source_host='localhost',
            source_port=5432,
            source_database='testdb',
            source_username='testuser'
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    # === CONNECTION LIST API ===

    def test_connection_list_returns_connections(self):
        """Connection list API should return all connections for model."""
        response = self.client.get(
            reverse('api_connection_list', args=[self.model.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('connections', data)
        self.assertEqual(len(data['connections']), 1)
        self.assertEqual(data['connections'][0]['name'], 'Test DB Connection')

    def test_connection_list_empty_for_model_without_connections(self):
        """Connection list should return empty array for model without connections."""
        new_model = ModelEndpoint.objects.create(
            name='Empty Model',
            created_by=self.user
        )

        response = self.client.get(
            reverse('api_connection_list', args=[new_model.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['connections']), 0)

    # === CONNECTION GET API ===

    def test_connection_get_returns_details(self):
        """Connection get API should return connection details."""
        response = self.client.get(
            reverse('api_connection_get', args=[self.connection.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Response wraps connection in 'status' and fields at root level
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['connection']['name'], 'Test DB Connection')
        self.assertEqual(data['connection']['source_type'], 'postgresql')
        self.assertEqual(data['connection']['source_host'], 'localhost')

    def test_connection_get_error_for_invalid_id(self):
        """Connection get API should return error for non-existent connection."""
        response = self.client.get(
            reverse('api_connection_get', args=[99999])
        )
        # API catches exception and returns 400 with error message
        self.assertIn(response.status_code, [400, 404])

    # === CONNECTION URL RESOLUTION ===

    def test_connection_urls_resolve(self):
        """All connection URLs should resolve correctly."""
        connection_urls = [
            ('api_connection_list', [self.model.id]),
            ('api_connection_create', [self.model.id]),
            ('api_connection_test_wizard', [self.model.id]),
            ('api_connection_get', [self.connection.id]),
            ('api_connection_test', [self.connection.id]),
            ('api_connection_update', [self.connection.id]),
            ('api_connection_delete', [self.connection.id]),
            ('api_connection_fetch_schemas', [self.connection.id]),
            ('api_connection_fetch_tables_for_schema', [self.connection.id]),
        ]

        for url_name, args in connection_urls:
            try:
                url = reverse(url_name, args=args)
                self.assertIsNotNone(url, f"{url_name} should resolve")
            except Exception as e:
                self.fail(f"Failed to resolve {url_name}: {e}")


class ETLRunModelTests(TestCase):
    """Tests for ETL run model behavior."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        cls.model = ModelEndpoint.objects.create(
            name='Run Test Model',
            created_by=cls.user
        )
        cls.etl_config = ETLConfiguration.objects.create(
            model_endpoint=cls.model
        )
        cls.data_source = DataSource.objects.create(
            etl_config=cls.etl_config,
            name='Run Test Source',
            source_type='postgresql'
        )

    def test_create_etl_run(self):
        """Should be able to create ETL run records."""
        run = ETLRun.objects.create(
            etl_config=self.etl_config,
            model_endpoint=self.model,
            data_source=self.data_source,
            status='pending'
        )
        self.assertIsNotNone(run.id)
        self.assertEqual(run.status, 'pending')

    def test_etl_run_status_transitions(self):
        """ETL run should support status transitions."""
        run = ETLRun.objects.create(
            etl_config=self.etl_config,
            model_endpoint=self.model,
            status='pending'
        )

        # Transition to running
        run.status = 'running'
        run.started_at = timezone.now()
        run.save()

        run.refresh_from_db()
        self.assertEqual(run.status, 'running')
        self.assertIsNotNone(run.started_at)

        # Transition to completed
        run.status = 'completed'
        run.completed_at = timezone.now()
        run.save()

        run.refresh_from_db()
        self.assertEqual(run.status, 'completed')

    def test_etl_run_linked_to_data_source(self):
        """ETL run should be linked to data source."""
        run = ETLRun.objects.create(
            etl_config=self.etl_config,
            model_endpoint=self.model,
            data_source=self.data_source,
            status='completed'
        )

        self.assertEqual(run.data_source, self.data_source)
        self.assertEqual(run.data_source.name, 'Run Test Source')
