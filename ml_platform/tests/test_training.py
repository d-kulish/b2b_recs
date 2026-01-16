"""
Training Domain Tests

Tests for TrainingRun model, TrainingService, and Training API endpoints.

Usage:
    python manage.py test ml_platform.tests.test_training -v 2
"""
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from ml_platform.models import (
    ModelEndpoint,
    Dataset,
    FeatureConfig,
    ModelConfig,
    QuickTest,
)
from ml_platform.training.models import TrainingRun
from ml_platform.training.services import TrainingService, TrainingServiceError


class TrainingRunModelTests(TestCase):
    """Tests for TrainingRun model properties and methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class."""
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        cls.model_endpoint = ModelEndpoint.objects.create(
            name='Test Model',
            description='Test model for training tests',
            created_by=cls.user,
            status='draft',
            gcp_project_id='test-project',
            gcp_region='us-central1'
        )
        cls.dataset = Dataset.objects.create(
            model_endpoint=cls.model_endpoint,
            name='Test Dataset',
            bq_dataset='test_dataset',
            created_by=cls.user
        )
        cls.feature_config = FeatureConfig.objects.create(
            dataset=cls.dataset,
            name='Test Features',
            feature_type='retrieval',
            version=1,
            created_by=cls.user
        )
        cls.model_config = ModelConfig.objects.create(
            model_endpoint=cls.model_endpoint,
            name='Test Model Config',
            model_type='retrieval',
            created_by=cls.user
        )

    def test_training_run_creation(self):
        """Test TrainingRun can be created with required fields."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-training-v1',
            run_number=1,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            model_type='retrieval',
            created_by=self.user
        )

        self.assertIsNotNone(training_run.id)
        self.assertEqual(training_run.name, 'test-training-v1')
        self.assertEqual(training_run.run_number, 1)
        self.assertEqual(training_run.status, TrainingRun.STATUS_PENDING)
        self.assertEqual(training_run.model_type, TrainingRun.MODEL_TYPE_RETRIEVAL)

    def test_is_terminal_property(self):
        """Test is_terminal property for different statuses."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-terminal',
            run_number=2,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_PENDING
        )

        # Non-terminal statuses
        self.assertFalse(training_run.is_terminal)

        training_run.status = TrainingRun.STATUS_RUNNING
        self.assertFalse(training_run.is_terminal)

        training_run.status = TrainingRun.STATUS_SUBMITTING
        self.assertFalse(training_run.is_terminal)

        # Terminal statuses
        training_run.status = TrainingRun.STATUS_COMPLETED
        self.assertTrue(training_run.is_terminal)

        training_run.status = TrainingRun.STATUS_FAILED
        self.assertTrue(training_run.is_terminal)

        training_run.status = TrainingRun.STATUS_CANCELLED
        self.assertTrue(training_run.is_terminal)

        training_run.status = TrainingRun.STATUS_NOT_BLESSED
        self.assertTrue(training_run.is_terminal)

    def test_is_cancellable_property(self):
        """Test is_cancellable property for different statuses."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-cancellable',
            run_number=3,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_PENDING
        )

        # Not cancellable statuses
        self.assertFalse(training_run.is_cancellable)

        training_run.status = TrainingRun.STATUS_COMPLETED
        self.assertFalse(training_run.is_cancellable)

        # Cancellable statuses
        training_run.status = TrainingRun.STATUS_RUNNING
        self.assertTrue(training_run.is_cancellable)

        training_run.status = TrainingRun.STATUS_SUBMITTING
        self.assertTrue(training_run.is_cancellable)

    def test_display_name_property(self):
        """Test display_name property."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-display',
            run_number=5,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config
        )

        self.assertEqual(training_run.display_name, 'Training #5')

    def test_elapsed_seconds_property(self):
        """Test elapsed_seconds property calculation."""
        now = timezone.now()
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-elapsed',
            run_number=6,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            started_at=now - timedelta(seconds=120)
        )

        # Should be approximately 120 seconds (allow for small timing differences)
        elapsed = training_run.elapsed_seconds
        self.assertIsNotNone(elapsed)
        self.assertGreaterEqual(elapsed, 119)
        self.assertLessEqual(elapsed, 125)

    def test_elapsed_seconds_with_completed_run(self):
        """Test elapsed_seconds for completed run uses completed_at."""
        now = timezone.now()
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-elapsed-completed',
            run_number=7,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            started_at=now - timedelta(seconds=300),
            completed_at=now - timedelta(seconds=60)
        )

        # Should be 240 seconds (300 - 60)
        elapsed = training_run.elapsed_seconds
        self.assertEqual(elapsed, 240)

    def test_unique_together_constraint(self):
        """Test unique_together constraint for ml_model and run_number."""
        TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-unique-1',
            run_number=100,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config
        )

        # Creating another with same ml_model and run_number should fail
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            TrainingRun.objects.create(
                ml_model=self.model_endpoint,
                name='test-unique-2',
                run_number=100,
                dataset=self.dataset,
                feature_config=self.feature_config,
                model_config=self.model_config
            )

    def test_str_representation(self):
        """Test string representation of TrainingRun."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='test-str',
            run_number=8,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_RUNNING
        )

        self.assertIn('TrainingRun #8', str(training_run))
        self.assertIn('test-str', str(training_run))
        self.assertIn('running', str(training_run))


class TrainingServiceTests(TestCase):
    """Tests for TrainingService methods (with mocked GCP calls)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class."""
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='serviceuser',
            email='service@example.com',
            password='testpass123'
        )
        cls.model_endpoint = ModelEndpoint.objects.create(
            name='Service Test Model',
            description='Test model for service tests',
            created_by=cls.user,
            status='draft',
            gcp_project_id='test-project',
            gcp_region='us-central1',
            gcs_bucket='gs://test-bucket'
        )
        cls.dataset = Dataset.objects.create(
            model_endpoint=cls.model_endpoint,
            name='Service Test Dataset',
            bq_dataset='test_dataset',
            created_by=cls.user
        )
        cls.feature_config = FeatureConfig.objects.create(
            dataset=cls.dataset,
            name='Service Test Features',
            feature_type='retrieval',
            version=1,
            created_by=cls.user
        )
        cls.model_config = ModelConfig.objects.create(
            model_endpoint=cls.model_endpoint,
            name='Service Test Model Config',
            model_type='retrieval',
            created_by=cls.user
        )

    def test_create_training_run(self):
        """Test TrainingService.create_training_run creates run with correct fields."""
        service = TrainingService(self.model_endpoint)

        training_run = service.create_training_run(
            name='service-test-run',
            description='Test run from service',
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            training_params={'epochs': 100, 'batch_size': 8192},
            gpu_config={'accelerator_type': 'NVIDIA_L4', 'accelerator_count': 2},
            evaluator_config={'enabled': True, 'blessing_threshold': 0.40},
            created_by=self.user
        )

        self.assertIsNotNone(training_run.id)
        self.assertEqual(training_run.name, 'service-test-run')
        self.assertEqual(training_run.description, 'Test run from service')
        self.assertEqual(training_run.ml_model, self.model_endpoint)
        self.assertEqual(training_run.status, TrainingRun.STATUS_PENDING)
        self.assertEqual(training_run.training_params['epochs'], 100)
        self.assertEqual(training_run.gpu_config['accelerator_type'], 'NVIDIA_L4')
        self.assertEqual(training_run.created_by, self.user)

    def test_create_training_run_auto_increments_run_number(self):
        """Test that run_number auto-increments for each model endpoint."""
        service = TrainingService(self.model_endpoint)

        run1 = service.create_training_run(
            name='run-1',
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config
        )

        run2 = service.create_training_run(
            name='run-2',
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config
        )

        self.assertEqual(run2.run_number, run1.run_number + 1)

    @patch('ml_platform.training.services.TrainingService._cancel_vertex_pipeline')
    def test_cancel_training_run(self, mock_cancel_vertex):
        """Test TrainingService.cancel_training_run updates status."""
        mock_cancel_vertex.return_value = None

        service = TrainingService(self.model_endpoint)

        # Create a running training run
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='cancel-test',
            run_number=50,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_RUNNING,
            vertex_pipeline_job_name='projects/test/locations/us-central1/pipelineJobs/test-job'
        )

        result = service.cancel_training_run(training_run)

        self.assertEqual(result.status, TrainingRun.STATUS_CANCELLED)
        self.assertIsNotNone(result.completed_at)

    @patch('ml_platform.training.services.TrainingService._delete_gcs_artifacts')
    def test_delete_training_run(self, mock_delete_gcs):
        """Test TrainingService.delete_training_run deletes the run."""
        mock_delete_gcs.return_value = None

        service = TrainingService(self.model_endpoint)

        # Create a completed training run
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='delete-test',
            run_number=51,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_COMPLETED,
            gcs_artifacts_path='gs://test-bucket/artifacts/delete-test'
        )
        run_id = training_run.id

        service.delete_training_run(training_run)

        # Verify the run was deleted
        self.assertFalse(TrainingRun.objects.filter(id=run_id).exists())


class TrainingAPITests(TestCase):
    """Tests for Training API endpoints."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class."""
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='apiuser',
            email='api@example.com',
            password='testpass123'
        )
        cls.model_endpoint = ModelEndpoint.objects.create(
            name='API Test Model',
            description='Test model for API tests',
            created_by=cls.user,
            status='draft',
            gcp_project_id='test-project',
            gcp_region='us-central1'
        )
        cls.dataset = Dataset.objects.create(
            model_endpoint=cls.model_endpoint,
            name='API Test Dataset',
            bq_dataset='test_dataset',
            created_by=cls.user
        )
        cls.feature_config = FeatureConfig.objects.create(
            dataset=cls.dataset,
            name='API Test Features',
            feature_type='retrieval',
            version=1,
            created_by=cls.user
        )
        cls.model_config = ModelConfig.objects.create(
            model_endpoint=cls.model_endpoint,
            name='API Test Model Config',
            model_type='retrieval',
            created_by=cls.user
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = Client()
        self.client.login(username='apiuser', password='testpass123')
        # Set model endpoint in session
        session = self.client.session
        session['model_endpoint_id'] = self.model_endpoint.id
        session.save()

    def test_list_training_runs_empty(self):
        """Test GET /api/training-runs/ returns empty list when no runs."""
        response = self.client.get('/api/training-runs/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['training_runs']), 0)
        self.assertEqual(data['pagination']['total_count'], 0)

    def test_list_training_runs_with_data(self):
        """Test GET /api/training-runs/ returns training runs."""
        # Create some training runs
        for i in range(3):
            TrainingRun.objects.create(
                ml_model=self.model_endpoint,
                name=f'test-run-{i}',
                run_number=i + 1,
                dataset=self.dataset,
                feature_config=self.feature_config,
                model_config=self.model_config,
                status=TrainingRun.STATUS_COMPLETED
            )

        response = self.client.get('/api/training-runs/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['training_runs']), 3)
        self.assertEqual(data['pagination']['total_count'], 3)

    def test_list_training_runs_with_status_filter(self):
        """Test GET /api/training-runs/?status=completed filters by status."""
        # Create runs with different statuses
        TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='completed-run',
            run_number=10,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_COMPLETED
        )
        TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='running-run',
            run_number=11,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_RUNNING
        )

        response = self.client.get('/api/training-runs/?status=completed')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['training_runs']), 1)
        self.assertEqual(data['training_runs'][0]['status'], 'completed')

    def test_list_training_runs_pagination(self):
        """Test GET /api/training-runs/ pagination works."""
        # Create 15 training runs
        for i in range(15):
            TrainingRun.objects.create(
                ml_model=self.model_endpoint,
                name=f'page-test-{i}',
                run_number=100 + i,
                dataset=self.dataset,
                feature_config=self.feature_config,
                model_config=self.model_config
            )

        # Get first page
        response = self.client.get('/api/training-runs/?page=1&page_size=10')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data['training_runs']), 10)
        self.assertEqual(data['pagination']['page'], 1)
        self.assertEqual(data['pagination']['total_pages'], 2)
        self.assertTrue(data['pagination']['has_next'])
        self.assertFalse(data['pagination']['has_prev'])

        # Get second page
        response = self.client.get('/api/training-runs/?page=2&page_size=10')
        data = response.json()
        self.assertEqual(len(data['training_runs']), 5)
        self.assertEqual(data['pagination']['page'], 2)
        self.assertFalse(data['pagination']['has_next'])
        self.assertTrue(data['pagination']['has_prev'])

    @patch('ml_platform.training.services.TrainingService.submit_training_pipeline')
    def test_create_training_run(self, mock_submit):
        """Test POST /api/training-runs/ creates a new training run."""
        mock_submit.return_value = None

        payload = {
            'name': 'new-training-run',
            'description': 'Test training run',
            'dataset_id': self.dataset.id,
            'feature_config_id': self.feature_config.id,
            'model_config_id': self.model_config.id,
            'training_params': {
                'epochs': 100,
                'batch_size': 8192
            },
            'gpu_config': {
                'accelerator_type': 'NVIDIA_L4',
                'accelerator_count': 2
            },
            'auto_submit': False  # Don't submit to avoid GCP calls
        }

        response = self.client.post(
            '/api/training-runs/',
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['training_run']['name'], 'new-training-run')
        self.assertEqual(data['training_run']['status'], 'pending')

    def test_create_training_run_missing_fields(self):
        """Test POST /api/training-runs/ returns error for missing fields."""
        payload = {
            'name': 'incomplete-run'
            # Missing required fields
        }

        response = self.client.post(
            '/api/training-runs/',
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Missing required fields', data['error'])

    def test_get_training_run_detail(self):
        """Test GET /api/training-runs/<id>/ returns run details."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='detail-test',
            run_number=200,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_COMPLETED,
            recall_at_100=0.456
        )

        response = self.client.get(f'/api/training-runs/{training_run.id}/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['training_run']['id'], training_run.id)
        self.assertEqual(data['training_run']['name'], 'detail-test')
        self.assertEqual(data['training_run']['recall_at_100'], 0.456)
        # Should include details
        self.assertIn('training_params', data['training_run'])

    def test_get_training_run_not_found(self):
        """Test GET /api/training-runs/<id>/ returns 404 for non-existent run."""
        response = self.client.get('/api/training-runs/99999/')
        self.assertEqual(response.status_code, 404)

        data = response.json()
        self.assertFalse(data['success'])

    @patch('ml_platform.training.services.TrainingService._cancel_vertex_pipeline')
    def test_cancel_training_run(self, mock_cancel):
        """Test POST /api/training-runs/<id>/cancel/ cancels a running run."""
        mock_cancel.return_value = None

        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='cancel-api-test',
            run_number=300,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_RUNNING
        )

        response = self.client.post(f'/api/training-runs/{training_run.id}/cancel/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['training_run']['status'], 'cancelled')

    def test_cancel_completed_training_run_fails(self):
        """Test POST /api/training-runs/<id>/cancel/ returns error for completed run."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='cancel-completed-test',
            run_number=301,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_COMPLETED
        )

        response = self.client.post(f'/api/training-runs/{training_run.id}/cancel/')
        self.assertEqual(response.status_code, 400)

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('not running', data['error'])

    @patch('ml_platform.training.services.TrainingService._delete_gcs_artifacts')
    def test_delete_training_run(self, mock_delete_gcs):
        """Test DELETE /api/training-runs/<id>/delete/ deletes a terminal run."""
        mock_delete_gcs.return_value = None

        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='delete-api-test',
            run_number=400,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_FAILED
        )
        run_id = training_run.id

        response = self.client.delete(f'/api/training-runs/{run_id}/delete/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(TrainingRun.objects.filter(id=run_id).exists())

    def test_delete_running_training_run_fails(self):
        """Test DELETE /api/training-runs/<id>/delete/ returns error for running run."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='delete-running-test',
            run_number=401,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            status=TrainingRun.STATUS_RUNNING
        )

        response = self.client.delete(f'/api/training-runs/{training_run.id}/delete/')
        self.assertEqual(response.status_code, 400)

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Cannot delete', data['error'])

    def test_list_training_runs_requires_model_endpoint(self):
        """Test API returns error when no model endpoint in session."""
        # Clear session
        session = self.client.session
        session['model_endpoint_id'] = None
        session.save()

        response = self.client.get('/api/training-runs/')
        self.assertEqual(response.status_code, 400)

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('No model endpoint', data['error'])


class TrainingRunSerializationTests(TestCase):
    """Tests for TrainingRun serialization in API responses."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class."""
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='serializeuser',
            email='serialize@example.com',
            password='testpass123'
        )
        cls.model_endpoint = ModelEndpoint.objects.create(
            name='Serialize Test Model',
            created_by=cls.user,
            status='draft',
            gcp_project_id='test-project'
        )
        cls.dataset = Dataset.objects.create(
            model_endpoint=cls.model_endpoint,
            name='Serialize Dataset',
            bq_dataset='test_dataset',
            created_by=cls.user
        )
        cls.feature_config = FeatureConfig.objects.create(
            dataset=cls.dataset,
            name='Serialize Features',
            feature_type='retrieval',
            version=1,
            created_by=cls.user
        )
        cls.model_config = ModelConfig.objects.create(
            model_endpoint=cls.model_endpoint,
            name='Serialize Model Config',
            model_type='retrieval',
            created_by=cls.user
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = Client()
        self.client.login(username='serializeuser', password='testpass123')
        session = self.client.session
        session['model_endpoint_id'] = self.model_endpoint.id
        session.save()

    def test_retrieval_model_metrics_serialization(self):
        """Test retrieval model includes recall metrics in response."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='retrieval-metrics-test',
            run_number=500,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            model_type='retrieval',
            status=TrainingRun.STATUS_COMPLETED,
            recall_at_5=0.123,
            recall_at_10=0.234,
            recall_at_50=0.345,
            recall_at_100=0.456,
            loss=0.567
        )

        response = self.client.get(f'/api/training-runs/{training_run.id}/')
        data = response.json()

        self.assertEqual(data['training_run']['recall_at_5'], 0.123)
        self.assertEqual(data['training_run']['recall_at_10'], 0.234)
        self.assertEqual(data['training_run']['recall_at_50'], 0.345)
        self.assertEqual(data['training_run']['recall_at_100'], 0.456)
        self.assertEqual(data['training_run']['loss'], 0.567)
        # Ranking metrics should be None
        self.assertIsNone(data['training_run']['rmse'])
        self.assertIsNone(data['training_run']['mae'])

    def test_ranking_model_metrics_serialization(self):
        """Test ranking model includes RMSE/MAE metrics in response."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='ranking-metrics-test',
            run_number=501,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            model_type='ranking',
            status=TrainingRun.STATUS_COMPLETED,
            rmse=0.987,
            mae=0.654,
            test_rmse=1.123,
            test_mae=0.876
        )

        response = self.client.get(f'/api/training-runs/{training_run.id}/')
        data = response.json()

        self.assertEqual(data['training_run']['rmse'], 0.987)
        self.assertEqual(data['training_run']['mae'], 0.654)
        self.assertEqual(data['training_run']['test_rmse'], 1.123)
        self.assertEqual(data['training_run']['test_mae'], 0.876)
        # Recall metrics should be None
        self.assertIsNone(data['training_run']['recall_at_5'])

    def test_multitask_model_metrics_serialization(self):
        """Test multitask model includes both retrieval and ranking metrics."""
        training_run = TrainingRun.objects.create(
            ml_model=self.model_endpoint,
            name='multitask-metrics-test',
            run_number=502,
            dataset=self.dataset,
            feature_config=self.feature_config,
            model_config=self.model_config,
            model_type='multitask',
            status=TrainingRun.STATUS_COMPLETED,
            recall_at_100=0.456,
            rmse=0.987
        )

        response = self.client.get(f'/api/training-runs/{training_run.id}/')
        data = response.json()

        # Should include both retrieval and ranking metrics
        self.assertEqual(data['training_run']['recall_at_100'], 0.456)
        self.assertEqual(data['training_run']['rmse'], 0.987)
