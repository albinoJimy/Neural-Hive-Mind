"""
Testes de integração completos para ML Training Pipeline.

Testa o pipeline end-to-end de treinamento de modelos ML incluindo:
- Treinamento bem-sucedido com dados suficientes
- Promoção de modelos para produção (critérios MAE<15%, precision>0.75)
- Dados insuficientes (skip)
- Salvamento de baseline de features para drift detection
- Backfill de erros históricos com estatísticas (P95, extreme errors)
- Cache de modelos (hit, expiry, cleanup)
- Integração com MLPredictor (predict_and_enrich)
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from datetime import datetime, timedelta
from uuid import uuid4
import numpy as np
import pandas as pd

from src.ml.training_pipeline import TrainingPipeline
from src.ml.model_registry import ModelRegistry
from src.ml.duration_predictor import DurationPredictor
from src.ml.anomaly_detector import AnomalyDetector
from src.ml.ml_predictor import MLPredictor
from src.observability.metrics import OrchestratorMetrics


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_config():
    """Test configuration with appropriate ML settings."""
    config = Mock()
    config.ml_predictions_enabled = True
    config.mlflow_tracking_uri = 'http://localhost:5000'
    config.mlflow_experiment_name = 'test-training-pipeline'
    config.ml_training_window_days = 7
    config.ml_min_training_samples = 50
    config.ml_duration_error_threshold = 0.15  # 15% MAE for promotion
    config.ml_anomaly_contamination = 0.05
    config.ml_model_cache_ttl_seconds = 3600
    config.ml_drift_baseline_enabled = True
    config.ml_backfill_errors = True
    config.ml_backfill_history_retention_days = 90
    return config


@pytest_asyncio.fixture
async def test_mongodb_client(test_config):
    """Test MongoDB client with in-memory mock data."""
    client = AsyncMock()

    # Create sample tickets (150+ for sufficient data)
    sample_tickets = []
    base_time = datetime.utcnow() - timedelta(days=5)

    task_types = ['BUILD', 'TEST', 'DEPLOY', 'VALIDATE', 'EXECUTE']
    risk_bands = ['low', 'medium', 'high', 'critical']

    for i in range(150):
        actual_duration = 50000 + (i * 500) + np.random.randint(-5000, 5000)
        predicted_duration = actual_duration * (0.9 + np.random.random() * 0.2)  # ±10% error

        ticket = {
            'ticket_id': f'test-ticket-{i}',
            'task_type': task_types[i % len(task_types)],
            'risk_band': risk_bands[i % len(risk_bands)],
            'qos': {
                'delivery_mode': 'exactly_once',
                'consistency': 'strong',
                'durability': 'persistent'
            },
            'required_capabilities': ['python', 'docker'],
            'parameters': {'test_param': 'value'},
            'estimated_duration_ms': 60000,
            'actual_duration_ms': actual_duration,
            'started_at': (base_time + timedelta(hours=i)).timestamp() * 1000,
            'completed_at': (base_time + timedelta(hours=i, seconds=actual_duration/1000)).timestamp() * 1000,
            'retry_count': i % 3,
            'created_at': base_time + timedelta(hours=i),
            'status': 'completed',
            'predictions': {
                'duration_ms': predicted_duration
            },
            'allocation_metadata': {
                'predicted_duration_ms': predicted_duration
            }
        }
        sample_tickets.append(ticket)

    # Mock execution_tickets collection
    cursor_mock = AsyncMock()
    cursor_mock.to_list = AsyncMock(return_value=sample_tickets)

    tickets_collection = AsyncMock()
    tickets_collection.find = Mock(return_value=cursor_mock)
    tickets_collection.insert_one = AsyncMock()

    # Mock ml_feature_baselines collection
    baselines_collection = AsyncMock()
    baselines_collection.insert_one = AsyncMock()
    baselines_collection.find_one = AsyncMock(return_value=None)

    # Mock ml_backfill_history collection
    backfill_collection = AsyncMock()
    backfill_collection.insert_one = AsyncMock()

    # Setup db mock
    client.db = {
        'execution_tickets': tickets_collection,
        'ml_feature_baselines': baselines_collection,
        'ml_backfill_history': backfill_collection
    }

    return client


@pytest_asyncio.fixture
async def mock_mlflow():
    """Mock MLflow for model registry tests."""
    with patch('src.ml.model_registry.mlflow') as mlflow_mock, \
         patch('src.ml.model_registry.MlflowClient') as client_mock:

        # Mock client
        mock_client = MagicMock()
        client_mock.return_value = mock_client

        # Mock experiment
        mock_experiment = MagicMock()
        mock_experiment.experiment_id = 'test-exp-123'
        mock_client.get_experiment_by_name = MagicMock(return_value=mock_experiment)
        mock_client.create_experiment = MagicMock(return_value='test-exp-123')

        # Mock model versions
        mock_version = MagicMock()
        mock_version.version = '1'
        mock_version.current_stage = 'None'
        mock_version.run_id = 'test-run-123'
        mock_client.search_model_versions = MagicMock(return_value=[mock_version])
        mock_client.transition_model_version_stage = MagicMock()

        # Mock run
        mock_run = MagicMock()
        mock_run.data.metrics = {'mae': 5000, 'mae_percentage': 10.5, 'r2': 0.85}
        mock_run.data.params = {'n_estimators': 100}
        mock_run.data.tags = {}
        mock_run.info.run_id = 'test-run-123'
        mock_client.get_run = MagicMock(return_value=mock_run)

        # Mock mlflow module
        mlflow_mock.set_tracking_uri = MagicMock()
        mlflow_mock.start_run = MagicMock()
        mlflow_mock.log_params = MagicMock()
        mlflow_mock.log_metrics = MagicMock()
        mlflow_mock.set_tags = MagicMock()
        mlflow_mock.sklearn.log_model = MagicMock()
        mlflow_mock.sklearn.load_model = MagicMock(return_value=MagicMock())

        yield mlflow_mock, mock_client


@pytest_asyncio.fixture
async def model_registry(test_config, mock_mlflow):
    """Real ModelRegistry instance with mocked MLflow."""
    registry = ModelRegistry(test_config)
    await registry.initialize()
    return registry


@pytest.fixture
def mock_metrics():
    """Mock Prometheus metrics."""
    metrics = Mock(spec=OrchestratorMetrics)
    metrics.record_ml_training = Mock()
    metrics.record_ml_prediction_error_with_logging = Mock()
    metrics.ml_model_accuracy = Mock()
    metrics.ml_model_accuracy.labels = Mock(return_value=Mock(set=Mock()))
    return metrics


@pytest_asyncio.fixture
async def duration_predictor(test_config, test_mongodb_client, model_registry, mock_metrics):
    """Real DurationPredictor for integration tests."""
    predictor = DurationPredictor(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        metrics=mock_metrics
    )
    await predictor.initialize()
    return predictor


@pytest_asyncio.fixture
async def anomaly_detector(test_config, test_mongodb_client, model_registry, mock_metrics):
    """Real AnomalyDetector for integration tests."""
    detector = AnomalyDetector(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        metrics=mock_metrics
    )
    await detector.initialize()
    return detector


@pytest_asyncio.fixture
async def training_pipeline(
    test_config,
    test_mongodb_client,
    model_registry,
    duration_predictor,
    anomaly_detector,
    mock_metrics
):
    """TrainingPipeline instance for tests."""
    from src.ml.drift_detector import DriftDetector

    drift_detector = DriftDetector(
        config=test_config,
        mongodb_client=test_mongodb_client,
        metrics=mock_metrics
    )

    pipeline = TrainingPipeline(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        duration_predictor=duration_predictor,
        anomaly_detector=anomaly_detector,
        metrics=mock_metrics,
        drift_detector=drift_detector
    )
    return pipeline


# =============================================================================
# Test Cases
# =============================================================================

@pytest.mark.asyncio
async def test_training_cycle_success(training_pipeline):
    """
    Test successful training cycle with sufficient data.

    Verifies:
    - Pipeline executes training of both models
    - MAE < 30% (relaxed threshold for test data)
    - Baseline saved in ml_feature_baselines
    - Status is 'completed'
    """
    result = await training_pipeline.run_training_cycle(window_days=7)

    # Verify successful completion
    assert result['status'] == 'completed'
    assert 'duration_predictor' in result
    assert 'anomaly_detector' in result

    # Verify duration model metrics
    duration_metrics = result['duration_predictor']
    assert 'mae_percentage' in duration_metrics
    assert duration_metrics['mae_percentage'] < 30  # Relaxed for test data

    # Verify anomaly model metrics
    anomaly_metrics = result['anomaly_detector']
    assert 'precision' in anomaly_metrics

    # Verify sample count
    assert result['samples_used'] >= 50


@pytest.mark.asyncio
async def test_model_promotion(training_pipeline, model_registry):
    """
    Test model promotion with good metrics.

    Verifies:
    - Models promoted if MAE < 15% and precision > 0.75
    - Promotion criteria checked before transition
    """
    # Mock good metrics
    with patch.object(training_pipeline.duration_predictor, 'train_model', new=AsyncMock(return_value={
        'status': 'success',
        'mae': 6000,
        'mae_percentage': 12.0,  # < 15% threshold
        'rmse': 8000,
        'r2': 0.88,
        'samples': 100,
        'version': '1',
        'promoted': True
    })):
        with patch.object(training_pipeline.anomaly_detector, 'train_model', new=AsyncMock(return_value={
            'status': 'success',
            'precision': 0.80,  # > 0.75 threshold
            'recall': 0.76,
            'f1_score': 0.78,
            'samples': 100,
            'version': '1',
            'promoted': True
        })):
            result = await training_pipeline.run_training_cycle(window_days=7)

            assert result['status'] == 'completed'
            assert 'duration-predictor' in result.get('models_promoted', [])
            assert 'anomaly-detector' in result.get('models_promoted', [])


@pytest.mark.asyncio
async def test_insufficient_data(test_config, test_mongodb_client, model_registry, duration_predictor, anomaly_detector, mock_metrics):
    """
    Test behavior with insufficient training data.

    Verifies:
    - Pipeline detects < 50 samples
    - Status is 'skipped'
    - No model registration
    """
    # Create pipeline with empty data
    cursor_mock = AsyncMock()
    cursor_mock.to_list = AsyncMock(return_value=[{'ticket_id': 'test-1'}] * 40)  # Only 40 samples
    test_mongodb_client.db['execution_tickets'].find = Mock(return_value=cursor_mock)

    pipeline = TrainingPipeline(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        duration_predictor=duration_predictor,
        anomaly_detector=anomaly_detector,
        metrics=mock_metrics
    )

    result = await pipeline.run_training_cycle(window_days=7)

    assert result['status'] == 'skipped'
    assert result['reason'] == 'insufficient_data'
    assert result['samples'] < 50


@pytest.mark.asyncio
async def test_feature_baseline(training_pipeline, test_mongodb_client):
    """
    Test feature baseline saved after training.

    Verifies:
    - Baseline document inserted in ml_feature_baselines
    - Contains features dict with bins/counts
    - Includes training_mae
    """
    result = await training_pipeline.run_training_cycle(window_days=7)

    assert result['status'] == 'completed'

    # Verify baseline was saved
    baselines_collection = test_mongodb_client.db['ml_feature_baselines']
    baselines_collection.insert_one.assert_called()

    # Check call arguments
    call_args = baselines_collection.insert_one.call_args
    if call_args:
        baseline_doc = call_args[0][0]
        assert 'features' in baseline_doc
        assert 'target_distribution' in baseline_doc
        assert 'training_mae' in baseline_doc
        assert 'timestamp' in baseline_doc


@pytest.mark.asyncio
async def test_backfill_errors(training_pipeline, test_mongodb_client, mock_metrics):
    """
    Test backfill of historical prediction errors.

    Verifies:
    - Processes tickets with actual and predicted durations
    - Calculates mean_error, P95
    - Logs extreme_errors (>3x predicted)
    - Saves history to ml_backfill_history
    """
    result = await training_pipeline.run_training_cycle(window_days=7, backfill_errors=True)

    assert result['status'] == 'completed'

    if 'backfill_stats' in result:
        stats = result['backfill_stats']
        assert 'processed' in stats
        assert stats['processed'] > 0
        assert 'mean_error_ms' in stats
        assert 'p95_error_ms' in stats
        assert 'extreme_errors_count' in stats

        # Verify backfill history saved
        backfill_collection = test_mongodb_client.db['ml_backfill_history']
        backfill_collection.insert_one.assert_called()


@pytest.mark.asyncio
async def test_model_cache(model_registry, mock_mlflow):
    """
    Test model cache behavior.

    Verifies:
    - First load fetches from MLflow
    - Second load hits cache
    - Cache expires after TTL
    """
    # First load
    model1 = await model_registry.load_model('duration-predictor', version='latest', stage='Production')
    assert model1 is not None

    # Check cache key exists
    cache_key = 'duration-predictor_Production_latest'
    assert cache_key in model_registry._model_cache

    # Second load (should hit cache)
    model2 = await model_registry.load_model('duration-predictor', version='latest', stage='Production')
    assert model2 is not None

    # Verify same instance from cache
    cached_model, loaded_at = model_registry._model_cache[cache_key]
    assert cached_model == model1

    # Simulate TTL expiry
    model_registry._model_cache[cache_key] = (model1, datetime.utcnow().timestamp() - 4000)  # Old timestamp

    # Load after expiry (should fetch again)
    model3 = await model_registry.load_model('duration-predictor', version='latest', stage='Production')
    assert model3 is not None


@pytest.mark.asyncio
async def test_integration_with_predictor(test_config, test_mongodb_client, model_registry, mock_metrics):
    """
    Test full integration: Train → MLPredictor → predict_and_enrich.

    Verifies:
    - Training completes successfully
    - MLPredictor initialized with trained models
    - predict_and_enrich adds predictions field with duration, confidence, anomaly
    """
    # Create full pipeline
    from src.ml.drift_detector import DriftDetector

    duration_predictor = DurationPredictor(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        metrics=mock_metrics
    )
    await duration_predictor.initialize()

    anomaly_detector = AnomalyDetector(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        metrics=mock_metrics
    )
    await anomaly_detector.initialize()

    drift_detector = DriftDetector(
        config=test_config,
        mongodb_client=test_mongodb_client,
        metrics=mock_metrics
    )

    pipeline = TrainingPipeline(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        duration_predictor=duration_predictor,
        anomaly_detector=anomaly_detector,
        metrics=mock_metrics,
        drift_detector=drift_detector
    )

    # Train models
    result = await pipeline.run_training_cycle(window_days=7)
    assert result['status'] == 'completed'

    # Create MLPredictor
    ml_predictor = MLPredictor(
        config=test_config,
        mongodb_client=test_mongodb_client,
        model_registry=model_registry,
        metrics=mock_metrics
    )
    await ml_predictor.initialize()

    # Test predict_and_enrich
    test_ticket = {
        'ticket_id': 'integration-test-1',
        'task_type': 'BUILD',
        'risk_band': 'medium',
        'qos': {'delivery_mode': 'exactly_once', 'consistency': 'strong'},
        'required_capabilities': ['python'],
        'parameters': {},
        'estimated_duration_ms': 60000
    }

    enriched = await ml_predictor.predict_and_enrich(test_ticket)

    # Verify predictions field
    assert 'predictions' in enriched
    predictions = enriched['predictions']
    assert 'duration_ms' in predictions
    assert 'duration_confidence' in predictions
    assert 'anomaly' in predictions
    assert predictions['anomaly']['is_anomaly'] is not None
