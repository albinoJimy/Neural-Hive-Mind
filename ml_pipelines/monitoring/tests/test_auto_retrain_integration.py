"""
Testes de integração para Auto-Retrain Orchestrator.

Valida o fluxo completo de:
- Detecção de degradação de performance via ModelPerformanceMonitor
- Disparo de retreinamento via RetrainingTrigger quando thresholds são excedidos
- Geração e merge de datasets com feedback
- Envio de notificações (Slack/Email)
- Exportação de métricas para Prometheus
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime, timedelta
import time
import os
import sys

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../libraries/python'))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_performance_metrics_degraded():
    """Mock PerformanceMetrics com degradação crítica."""
    from model_performance_monitor import PerformanceMetrics
    return PerformanceMetrics(
        precision=0.68,  # Abaixo do threshold 0.75
        recall=0.72,     # Abaixo do threshold 0.70
        f1_score=0.65,   # Abaixo do threshold 0.72
        accuracy=0.70,
        run_id='baseline-run-123',
        timestamp=datetime.utcnow() - timedelta(days=7)
    )


@pytest.fixture
def mock_performance_metrics_ok():
    """Mock PerformanceMetrics com performance OK."""
    from model_performance_monitor import PerformanceMetrics
    return PerformanceMetrics(
        precision=0.82,
        recall=0.78,
        f1_score=0.80,
        accuracy=0.81,
        run_id='baseline-run-456',
        timestamp=datetime.utcnow() - timedelta(days=7)
    )


@pytest.fixture
def mock_feedback_stats():
    """Mock FeedbackStats."""
    from model_performance_monitor import FeedbackStats
    return FeedbackStats(
        avg_rating=0.55,  # Abaixo do threshold 0.6
        total_count=150,
        positive_count=50,
        negative_count=70,
        neutral_count=30
    )


@pytest.fixture
def mock_performance_report_degraded(mock_performance_metrics_degraded, mock_feedback_stats):
    """Mock PerformanceReport com degradação."""
    from model_performance_monitor import PerformanceReport
    return PerformanceReport(
        specialist_type='technical',
        mlflow_metrics=mock_performance_metrics_degraded,
        feedback_stats=mock_feedback_stats,
        aggregate_score=0.65,
        is_degraded=True,
        degradation_reasons=[
            'Precision (0.68) abaixo do threshold (0.75)',
            'F1 Score (0.65) abaixo do threshold (0.72)',
            'Feedback médio (0.55) abaixo do threshold (0.6)'
        ],
        timestamp=datetime.utcnow(),
        recommendations=[
            'Retreinamento urgente recomendado',
            'Revisar feedback recente para identificar problemas'
        ]
    )


@pytest.fixture
def mock_performance_report_ok(mock_performance_metrics_ok):
    """Mock PerformanceReport sem degradação."""
    from model_performance_monitor import PerformanceReport, FeedbackStats
    return PerformanceReport(
        specialist_type='technical',
        mlflow_metrics=mock_performance_metrics_ok,
        feedback_stats=FeedbackStats(
            avg_rating=0.75,
            total_count=100,
            positive_count=60,
            negative_count=20,
            neutral_count=20
        ),
        aggregate_score=0.78,
        is_degraded=False,
        degradation_reasons=[],
        timestamp=datetime.utcnow(),
        recommendations=['Performance dentro dos thresholds esperados']
    )


@pytest.fixture
def mock_mlflow_client():
    """Mock MLflow client."""
    client = Mock()
    client.get_run = Mock(return_value=Mock(
        info=Mock(
            run_id='new-run-123',
            status='FINISHED',
            start_time=int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000),
            end_time=int(datetime.utcnow().timestamp() * 1000)
        ),
        data=Mock(
            metrics={
                'precision': 0.85,
                'recall': 0.82,
                'f1_score': 0.83,
                'accuracy': 0.84
            }
        )
    ))
    return client


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDB client."""
    client = Mock()
    client.feedback = Mock()
    client.retraining_triggers = Mock()
    return client


# =============================================================================
# Test Cases - Auto-Retrain on Critical Drift
# =============================================================================

class TestAutoRetrainOnCriticalDrift:
    """Testes para retreinamento automático quando drift crítico é detectado."""

    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_auto_retrain_triggered_on_critical_drift(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_performance_report_degraded
    ):
        """
        Test that auto-retrain is triggered when critical drift is detected.

        Scenario:
        - Performance monitor reports is_degraded=True
        - Precision (0.68) below threshold (0.75)
        - F1 Score (0.65) below threshold (0.72)

        Expected:
        - trigger_retraining() is called
        - Result has success=True
        - MLflow run ID is returned
        """
        from auto_retrain import AutoRetrainOrchestrator, RetrainResult

        # Setup mocks
        mock_monitor = Mock()
        mock_monitor.get_performance_report.return_value = mock_performance_report_degraded
        MockPerformanceMonitor.return_value = mock_monitor

        mock_trigger = Mock()
        mock_trigger.trigger_retraining.return_value = 'mlflow-run-123'
        mock_trigger.monitor_run_status.return_value = {'status': 'FINISHED'}
        MockRetrainingTrigger.return_value = mock_trigger

        mock_feedback = Mock()
        mock_feedback.get_recent_feedback.return_value = []
        MockFeedbackCollector.return_value = mock_feedback

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017',
            notification_channels=['slack']
        )

        # Override internal components with mocks
        orchestrator.performance_monitor = mock_monitor
        orchestrator.retraining_trigger = mock_trigger
        orchestrator.feedback_collector = mock_feedback

        # Mock internal methods
        with patch.object(orchestrator, '_generate_datasets', return_value='/data/test.parquet'):
            with patch.object(orchestrator, '_merge_with_feedback', return_value='/data/merged.parquet'):
                with patch.object(orchestrator, '_trigger_training', return_value='mlflow-run-123'):
                    with patch.object(orchestrator, '_monitor_training', return_value=True):
                        with patch.object(orchestrator, '_compare_metrics', return_value=({'f1_score': 0.85}, {'f1_score': 0.65}, True)):
                            with patch.object(orchestrator, '_send_notification'):
                                with patch.object(orchestrator, '_export_metrics'):
                                    # Execute
                                    result = orchestrator.check_performance_and_retrain(
                                        specialist_type='technical',
                                        force=False,
                                        skip_dataset_generation=False
                                    )

        # Assertions
        assert result.success is True
        assert result.specialist_type == 'technical'
        assert result.mlflow_run_id == 'mlflow-run-123'
        assert result.improved is True
        assert result.error_message is None

        # Verify performance check was called
        mock_monitor.get_performance_report.assert_called_once_with('technical')


    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_no_retrain_when_performance_ok(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_performance_report_ok
    ):
        """
        Test that no retraining is triggered when performance is OK.

        Scenario:
        - Performance monitor reports is_degraded=False
        - All metrics above thresholds

        Expected:
        - trigger_retraining() is NOT called
        - Result has success=True, mlflow_run_id=None
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mocks
        mock_monitor = Mock()
        mock_monitor.get_performance_report.return_value = mock_performance_report_ok
        MockPerformanceMonitor.return_value = mock_monitor

        mock_trigger = Mock()
        MockRetrainingTrigger.return_value = mock_trigger

        mock_feedback = Mock()
        MockFeedbackCollector.return_value = mock_feedback

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        orchestrator.performance_monitor = mock_monitor
        orchestrator.retraining_trigger = mock_trigger
        orchestrator.feedback_collector = mock_feedback

        # Execute
        result = orchestrator.check_performance_and_retrain(
            specialist_type='technical',
            force=False
        )

        # Assertions
        assert result.success is True
        assert result.mlflow_run_id is None
        assert result.improved is False
        assert result.error_message is None

        # Verify trigger_retraining was NOT called
        mock_trigger.trigger_retraining.assert_not_called()


    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_force_retrain_even_when_performance_ok(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_performance_report_ok
    ):
        """
        Test that retraining is triggered when force=True, even if performance is OK.

        Scenario:
        - Performance is OK (is_degraded=False)
        - force=True is passed

        Expected:
        - Retraining is triggered despite good performance
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mocks
        mock_monitor = Mock()
        mock_monitor.get_performance_report.return_value = mock_performance_report_ok
        MockPerformanceMonitor.return_value = mock_monitor

        mock_trigger = Mock()
        mock_trigger.trigger_retraining.return_value = 'forced-run-123'
        mock_trigger.monitor_run_status.return_value = {'status': 'FINISHED'}
        MockRetrainingTrigger.return_value = mock_trigger

        mock_feedback = Mock()
        mock_feedback.get_recent_feedback.return_value = []
        MockFeedbackCollector.return_value = mock_feedback

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        orchestrator.performance_monitor = mock_monitor
        orchestrator.retraining_trigger = mock_trigger
        orchestrator.feedback_collector = mock_feedback

        # Mock internal methods
        with patch.object(orchestrator, '_generate_datasets', return_value='/data/test.parquet'):
            with patch.object(orchestrator, '_merge_with_feedback', return_value='/data/merged.parquet'):
                with patch.object(orchestrator, '_trigger_training', return_value='forced-run-123'):
                    with patch.object(orchestrator, '_monitor_training', return_value=True):
                        with patch.object(orchestrator, '_compare_metrics', return_value=({'f1_score': 0.82}, {'f1_score': 0.80}, True)):
                            with patch.object(orchestrator, '_send_notification'):
                                with patch.object(orchestrator, '_export_metrics'):
                                    # Execute with force=True
                                    result = orchestrator.check_performance_and_retrain(
                                        specialist_type='technical',
                                        force=True,
                                        skip_dataset_generation=False
                                    )

        # Assertions
        assert result.success is True
        assert result.mlflow_run_id == 'forced-run-123'


# =============================================================================
# Test Cases - Dataset Generation
# =============================================================================

class TestDatasetGeneration:
    """Testes para geração de datasets."""

    @patch('subprocess.run')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_generate_datasets_success(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_subprocess
    ):
        """
        Test successful dataset generation via subprocess.

        Scenario:
        - subprocess.run executes generate_training_datasets.py
        - Returns success with dataset path in stdout

        Expected:
        - _generate_datasets() returns correct path
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup subprocess mock
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout='Processing specialist: technical\nDataset salvo em: /data/training/technical_specialist_dataset.parquet\nDone.',
            stderr=''
        )

        # Setup other mocks
        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        # Execute
        result = orchestrator._generate_datasets('technical')

        # Assertions
        assert result == '/data/training/technical_specialist_dataset.parquet'
        mock_subprocess.assert_called_once()


    @patch('subprocess.run')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_generate_datasets_success_english_format(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_subprocess
    ):
        """
        Test successful dataset generation with English 'saved to' format.

        Scenario:
        - subprocess.run executes generate_training_datasets.py
        - Returns success with English format: "Dataset saved to /path/to/file.parquet"

        Expected:
        - _generate_datasets() correctly parses and returns the path
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup subprocess mock with English format output
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout='Processing specialist: technical\nDataset saved to /data/training/technical_specialist_dataset.parquet\nDone.',
            stderr=''
        )

        # Setup other mocks
        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        # Execute
        result = orchestrator._generate_datasets('technical')

        # Assertions - path should be extracted correctly from "saved to" format
        assert result == '/data/training/technical_specialist_dataset.parquet', \
            f"Expected '/data/training/technical_specialist_dataset.parquet', got '{result}'"
        mock_subprocess.assert_called_once()


    @patch('subprocess.run')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_generate_datasets_success_mixed_case_saved_to(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_subprocess
    ):
        """
        Test dataset generation with mixed case 'Saved To' format.

        Scenario:
        - Output contains "Saved To" with different capitalization

        Expected:
        - _generate_datasets() correctly handles case-insensitive matching
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup subprocess mock with mixed case
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout='Processing...\nDataset Successfully Saved To /algum/caminho/dataset.parquet\nComplete.',
            stderr=''
        )

        # Setup other mocks
        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        # Execute
        result = orchestrator._generate_datasets('technical')

        # Assertions - should handle mixed case
        assert result == '/algum/caminho/dataset.parquet', \
            f"Expected '/algum/caminho/dataset.parquet', got '{result}'"


    @patch('subprocess.run')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_generate_datasets_failure(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_subprocess
    ):
        """
        Test dataset generation failure handling.

        Scenario:
        - subprocess.run returns non-zero exit code

        Expected:
        - _generate_datasets() returns None
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup subprocess mock with failure
        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout='',
            stderr='Error: Failed to connect to LLM provider'
        )

        # Setup other mocks
        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        # Execute
        result = orchestrator._generate_datasets('technical')

        # Assertions
        assert result is None


    @patch('subprocess.run')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_generate_datasets_timeout(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_subprocess
    ):
        """
        Test dataset generation timeout handling.

        Scenario:
        - subprocess.run raises TimeoutExpired

        Expected:
        - _generate_datasets() returns None gracefully
        """
        import subprocess
        from auto_retrain import AutoRetrainOrchestrator

        # Setup subprocess mock with timeout
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd=['python', 'generate_training_datasets.py'],
            timeout=1800
        )

        # Setup other mocks
        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        # Create orchestrator with short timeout
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017',
            dataset_generation_timeout=1800
        )

        # Execute
        result = orchestrator._generate_datasets('technical')

        # Assertions
        assert result is None


# =============================================================================
# Test Cases - Feedback Merge
# =============================================================================

class TestFeedbackMerge:
    """Testes para merge de datasets com feedback."""

    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_merge_with_feedback_success(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger
    ):
        """
        Test successful merge of new dataset with feedback data.

        Scenario:
        - New dataset exists at given path
        - FeedbackCollector returns feedback data
        - Merge produces combined dataset

        Expected:
        - Returns path to merged dataset
        - Merged dataset contains both sources
        """
        import pandas as pd
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mock feedback collector
        mock_feedback = Mock()
        mock_feedback.get_recent_feedback.return_value = [
            {
                'context': {
                    'cognitive_plan': 'Test plan 1',
                    'opinion': 'Good analysis'
                },
                'rating': 0.8,
                'feedback_text': 'Excellent work'
            },
            {
                'context': {
                    'cognitive_plan': 'Test plan 2',
                    'opinion': 'Needs improvement'
                },
                'rating': 0.4,
                'feedback_text': 'Could be better'
            }
        ]
        MockFeedbackCollector.return_value = mock_feedback

        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )
        orchestrator.feedback_collector = mock_feedback

        # Mock pandas operations
        with patch('pandas.read_parquet') as mock_read:
            with patch('pandas.DataFrame.to_parquet') as mock_write:
                with patch('pathlib.Path.exists', return_value=True):
                    # Setup mock DataFrame
                    mock_df = pd.DataFrame({
                        'cognitive_plan': ['Plan A', 'Plan B'],
                        'opinion': ['Opinion A', 'Opinion B'],
                        'rating': [0.7, 0.6]
                    })
                    mock_read.return_value = mock_df

                    # Execute
                    result = orchestrator._merge_with_feedback(
                        specialist_type='technical',
                        new_dataset_path='/data/test.parquet'
                    )

        # Assertions
        assert result is not None
        assert 'merged' in result
        mock_feedback.get_recent_feedback.assert_called_once_with(
            specialist_type='technical',
            limit=1000
        )


    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_merge_without_feedback_data(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger
    ):
        """
        Test merge when no feedback data is available.

        Scenario:
        - FeedbackCollector returns empty list

        Expected:
        - Returns path to original dataset (no merge needed)
        """
        import pandas as pd
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mock feedback collector with no data
        mock_feedback = Mock()
        mock_feedback.get_recent_feedback.return_value = []
        MockFeedbackCollector.return_value = mock_feedback

        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )
        orchestrator.feedback_collector = mock_feedback

        # Mock pandas operations
        with patch('pandas.read_parquet') as mock_read:
            with patch('pandas.DataFrame.to_parquet') as mock_write:
                with patch('pathlib.Path.exists', return_value=True):
                    mock_df = pd.DataFrame({
                        'cognitive_plan': ['Plan A'],
                        'opinion': ['Opinion A'],
                        'rating': [0.7]
                    })
                    mock_read.return_value = mock_df

                    # Execute
                    result = orchestrator._merge_with_feedback(
                        specialist_type='technical',
                        new_dataset_path='/data/test.parquet'
                    )

        # Assertions
        assert result is not None


# =============================================================================
# Test Cases - Notifications
# =============================================================================

class TestNotifications:
    """Testes para envio de notificações."""

    @patch('requests.post')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_slack_notification_success(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_requests_post
    ):
        """
        Test successful Slack notification on retrain completion.

        Scenario:
        - SLACK_WEBHOOK_URL is configured
        - Retraining completed successfully

        Expected:
        - requests.post called with correct payload
        - Notification contains specialist_type, run_id, improved status
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mock
        mock_requests_post.return_value = Mock(status_code=200)
        mock_requests_post.return_value.raise_for_status = Mock()

        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        # Set environment variable
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            orchestrator = AutoRetrainOrchestrator(
                mlflow_tracking_uri='http://localhost:5000',
                mongodb_uri='mongodb://localhost:27017',
                notification_channels=['slack']
            )

            # Execute
            orchestrator._send_slack_notification(
                status='success',
                details={
                    'specialist_type': 'technical',
                    'mlflow_run_id': 'run-123',
                    'improved': True
                }
            )

        # Assertions
        mock_requests_post.assert_called_once()
        call_args = mock_requests_post.call_args

        # Verify payload contains expected content
        payload = call_args[1]['json']
        assert 'text' in payload
        assert 'technical' in payload['text']
        assert 'run-123' in payload['text']
        assert 'SUCCESS' in payload['text']


    @patch('requests.post')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_slack_notification_failure_logged(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_requests_post
    ):
        """
        Test Slack notification failure is logged but doesn't raise exception.

        Scenario:
        - requests.post raises exception

        Expected:
        - Exception is caught and logged
        - No exception propagates
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mock to raise exception
        mock_requests_post.side_effect = Exception('Connection failed')

        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/test'}):
            orchestrator = AutoRetrainOrchestrator(
                mlflow_tracking_uri='http://localhost:5000',
                mongodb_uri='mongodb://localhost:27017',
                notification_channels=['slack']
            )

            # Should not raise exception
            orchestrator._send_slack_notification(
                status='success',
                details={'specialist_type': 'technical'}
            )


# =============================================================================
# Test Cases - Prometheus Metrics Export
# =============================================================================

class TestPrometheusExport:
    """Testes para exportação de métricas para Prometheus."""

    @patch('prometheus_client.push_to_gateway')
    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_export_metrics_success(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_push_to_gateway
    ):
        """
        Test successful metrics export to Prometheus Pushgateway.

        Scenario:
        - PROMETHEUS_PUSHGATEWAY_URL is configured
        - RetrainResult with success=True

        Expected:
        - push_to_gateway called
        - Counters and gauges registered
        """
        from auto_retrain import AutoRetrainOrchestrator, RetrainResult

        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        with patch.dict(os.environ, {'PROMETHEUS_PUSHGATEWAY_URL': 'http://pushgateway:9091'}):
            orchestrator = AutoRetrainOrchestrator(
                mlflow_tracking_uri='http://localhost:5000',
                mongodb_uri='mongodb://localhost:27017'
            )

            result = RetrainResult(
                success=True,
                specialist_type='technical',
                mlflow_run_id='run-123',
                new_metrics={'f1_score': 0.85},
                baseline_metrics={'f1_score': 0.65},
                improved=True,
                duration_seconds=3600.0
            )

            # Execute
            orchestrator._export_metrics(result)

        # Assertions
        mock_push_to_gateway.assert_called_once()


# =============================================================================
# Test Cases - Dry Run Mode
# =============================================================================

class TestDryRunMode:
    """Testes para modo dry-run."""

    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_dry_run_no_actual_retrain(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_performance_report_degraded
    ):
        """
        Test that dry_run mode doesn't trigger actual retraining.

        Scenario:
        - Performance degraded (would normally trigger retrain)
        - dry_run=True

        Expected:
        - No actual retraining triggered
        - Result has mlflow_run_id="dry-run"
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mocks
        mock_monitor = Mock()
        mock_monitor.get_performance_report.return_value = mock_performance_report_degraded
        MockPerformanceMonitor.return_value = mock_monitor

        mock_trigger = Mock()
        MockRetrainingTrigger.return_value = mock_trigger

        mock_feedback = Mock()
        MockFeedbackCollector.return_value = mock_feedback

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        orchestrator.performance_monitor = mock_monitor
        orchestrator.retraining_trigger = mock_trigger
        orchestrator.feedback_collector = mock_feedback

        # Execute with dry_run=True
        result = orchestrator.check_performance_and_retrain(
            specialist_type='technical',
            force=False,
            dry_run=True
        )

        # Assertions
        assert result.success is True
        assert result.mlflow_run_id == 'dry-run'
        assert result.improved is False

        # Verify actual training was NOT triggered
        mock_trigger.trigger_retraining.assert_not_called()


# =============================================================================
# Test Cases - Error Handling
# =============================================================================

class TestErrorHandling:
    """Testes para tratamento de erros."""

    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_training_failure_returns_error_result(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger,
        mock_performance_report_degraded
    ):
        """
        Test that training failure returns proper error result.

        Scenario:
        - Performance degraded
        - Training fails with exception

        Expected:
        - Result has success=False
        - error_message contains failure reason
        """
        from auto_retrain import AutoRetrainOrchestrator

        # Setup mocks
        mock_monitor = Mock()
        mock_monitor.get_performance_report.return_value = mock_performance_report_degraded
        MockPerformanceMonitor.return_value = mock_monitor

        mock_trigger = Mock()
        MockRetrainingTrigger.return_value = mock_trigger

        mock_feedback = Mock()
        mock_feedback.get_recent_feedback.return_value = []
        MockFeedbackCollector.return_value = mock_feedback

        # Create orchestrator
        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        orchestrator.performance_monitor = mock_monitor
        orchestrator.retraining_trigger = mock_trigger
        orchestrator.feedback_collector = mock_feedback

        # Mock training to fail
        with patch.object(orchestrator, '_generate_datasets', return_value='/data/test.parquet'):
            with patch.object(orchestrator, '_merge_with_feedback', return_value='/data/merged.parquet'):
                with patch.object(orchestrator, '_trigger_training', side_effect=Exception('MLflow connection failed')):
                    with patch.object(orchestrator, '_send_notification'):
                        # Execute
                        result = orchestrator.check_performance_and_retrain(
                            specialist_type='technical',
                            force=False
                        )

        # Assertions
        assert result.success is False
        assert result.error_message is not None
        assert 'MLflow connection failed' in result.error_message


# =============================================================================
# Test Cases - Convert Feedback to Dataset
# =============================================================================

class TestConvertFeedbackToDataset:
    """Testes para conversão de feedback para formato de dataset."""

    @patch('auto_retrain.RetrainingTrigger')
    @patch('auto_retrain.FeedbackCollector')
    @patch('auto_retrain.ModelPerformanceMonitor')
    def test_convert_feedback_structure(
        self,
        MockPerformanceMonitor,
        MockFeedbackCollector,
        MockRetrainingTrigger
    ):
        """
        Test that feedback data is correctly converted to dataset format.

        Expected:
        - DataFrame contains cognitive_plan, opinion, rating, feedback_text, source
        - Source is 'human_feedback'
        """
        from auto_retrain import AutoRetrainOrchestrator

        MockPerformanceMonitor.return_value = Mock()
        MockRetrainingTrigger.return_value = Mock()
        MockFeedbackCollector.return_value = Mock()

        orchestrator = AutoRetrainOrchestrator(
            mlflow_tracking_uri='http://localhost:5000',
            mongodb_uri='mongodb://localhost:27017'
        )

        feedback_data = [
            {
                'context': {
                    'cognitive_plan': 'Plan for task A',
                    'opinion': 'Well structured approach'
                },
                'rating': 0.85,
                'feedback_text': 'Great analysis'
            },
            {
                'context': {
                    'cognitive_plan': 'Plan for task B',
                    'opinion': 'Missing edge cases'
                },
                'rating': 0.45,
                'feedback_text': 'Needs improvement'
            }
        ]

        # Execute
        df = orchestrator._convert_feedback_to_dataset(feedback_data)

        # Assertions
        assert len(df) == 2
        assert 'cognitive_plan' in df.columns
        assert 'opinion' in df.columns
        assert 'rating' in df.columns
        assert 'feedback_text' in df.columns
        assert 'source' in df.columns

        # Verify source is set correctly
        assert df['source'].iloc[0] == 'human_feedback'
        assert df['source'].iloc[1] == 'human_feedback'

        # Verify values
        assert df['rating'].iloc[0] == 0.85
        assert df['rating'].iloc[1] == 0.45
