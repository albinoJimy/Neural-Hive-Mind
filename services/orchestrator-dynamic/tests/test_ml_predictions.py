"""
Testes unitários para componentes de ML Predictions.

Testa DurationPredictor, AnomalyDetector, ModelRegistry, MLPredictor,
FeatureEngineering e TrainingPipeline com mocks de dependências externas.
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from src.ml import (
    DurationPredictor,
    AnomalyDetector,
    ModelRegistry,
    MLPredictor,
    TrainingPipeline,
    extract_ticket_features,
    encode_risk_band,
    encode_qos,
    normalize_features
)


# Fixtures

@pytest.fixture
def mock_config():
    """Mock de configuração."""
    config = Mock()
    config.ml_predictions_enabled = True
    config.mlflow_tracking_uri = 'http://mlflow:5000'
    config.mlflow_experiment_name = 'test-experiment'
    config.ml_training_window_days = 30
    config.ml_training_interval_hours = 24
    config.ml_min_training_samples = 10  # Menor para testes
    config.ml_duration_error_threshold = 0.15
    config.ml_anomaly_contamination = 0.05
    config.ml_model_cache_ttl_seconds = 3600
    config.ml_feature_cache_ttl_seconds = 3600
    return config


@pytest.fixture
def mock_mongodb():
    """Mock de MongoDB client."""
    client = AsyncMock()
    client.db = {'execution_tickets': AsyncMock()}
    return client


@pytest.fixture
def mock_model_registry():
    """Mock de ModelRegistry."""
    registry = AsyncMock()
    registry.initialize = AsyncMock()
    registry.load_model = AsyncMock(return_value=None)
    registry.save_model = AsyncMock(return_value='test-run-id')
    registry.promote_model = AsyncMock()
    registry.get_model_metadata = AsyncMock(return_value={})
    return registry


@pytest.fixture
def mock_metrics():
    """Mock de métricas."""
    metrics = Mock()
    metrics.record_ml_prediction = Mock()
    metrics.record_ml_anomaly = Mock()
    metrics.record_ml_training = Mock()
    metrics.record_ml_error = Mock()
    return metrics


@pytest.fixture
def sample_ticket():
    """Ticket de exemplo para testes."""
    return {
        'ticket_id': 'test-ticket-123',
        'task_type': 'BUILD',
        'risk_band': 'high',
        'qos': {
            'delivery_guarantee': 'exactly_once',
            'consistency_level': 'strong',
            'durability': 'persistent'
        },
        'sla': {
            'timeout_ms': 300000
        },
        'required_capabilities': ['python', 'docker', 'k8s'],
        'parameters': {'key1': 'value1', 'key2': 'value2'},
        'estimated_duration_ms': 60000,
        'actual_duration_ms': 75000,
        'retry_count': 0,
        'created_at': datetime.utcnow().isoformat(),
        'status': 'COMPLETED'
    }


# Tests - Feature Engineering

class TestFeatureEngineering:
    """Testes para feature engineering."""

    def test_encode_risk_band(self):
        """Testa codificação de risk_band."""
        assert encode_risk_band('critical') == 1.0
        assert encode_risk_band('high') == 0.7
        assert encode_risk_band('medium') == 0.5
        assert encode_risk_band('low') == 0.3
        assert encode_risk_band('unknown') == 0.5  # default

    def test_encode_qos(self):
        """Testa codificação de QoS."""
        qos = {
            'delivery_guarantee': 'exactly_once',
            'consistency_level': 'strong',
            'durability': 'persistent'
        }
        result = encode_qos(qos)
        assert result['delivery_score'] == 1.0
        assert result['consistency_score'] == 1.0
        assert result['durability_score'] == 1.0

    def test_extract_ticket_features(self, sample_ticket):
        """Testa extração de features de ticket."""
        features = extract_ticket_features(sample_ticket)

        assert 'risk_weight' in features
        assert 'qos_delivery_score' in features
        assert 'capabilities_count' in features
        assert 'task_type_encoded' in features
        assert 'estimated_duration_ms' in features

        # Valida valores específicos
        assert features['risk_weight'] == 0.7  # high
        assert features['capabilities_count'] == 3.0
        assert features['task_type_encoded'] == 0.0  # BUILD

    def test_extract_ticket_features_with_historical_stats(self, sample_ticket):
        """Testa extração com estatísticas históricas."""
        historical_stats = {
            'BUILD': {
                'high': {
                    'avg_duration_ms': 70000.0,
                    'std_duration_ms': 10000.0,
                    'success_rate': 0.95
                }
            }
        }

        features = extract_ticket_features(sample_ticket, historical_stats)

        assert features['avg_duration_by_task'] == 70000.0
        assert features['std_duration_by_task'] == 10000.0
        assert features['success_rate_by_task'] == 0.95

    def test_normalize_features(self, sample_ticket):
        """Testa normalização de features."""
        features_dict = extract_ticket_features(sample_ticket)
        features_array = normalize_features(features_dict)

        assert isinstance(features_array, np.ndarray)
        assert features_array.shape == (1, 15)  # 15 features


# Tests - DurationPredictor

@pytest.mark.asyncio
class TestDurationPredictor:
    """Testes para DurationPredictor."""

    async def test_initialization(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics):
        """Testa inicialização do predictor."""
        predictor = DurationPredictor(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        with patch('src.ml.duration_predictor.compute_historical_stats', return_value={}):
            await predictor.initialize()

        assert predictor.model is not None
        mock_model_registry.load_model.assert_called_once()

    async def test_predict_duration_without_model(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics, sample_ticket):
        """Testa predição sem modelo treinado (heurística)."""
        predictor = DurationPredictor(mock_config, mock_mongodb, mock_model_registry, mock_metrics)
        predictor.model = None  # Sem modelo treinado

        result = await predictor.predict_duration(sample_ticket)

        assert 'duration_ms' in result
        assert 'confidence' in result
        assert result['duration_ms'] > 0
        assert 0 <= result['confidence'] <= 1

    async def test_predict_duration_with_model(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics, sample_ticket):
        """Testa predição com modelo treinado."""
        predictor = DurationPredictor(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        # Mock do modelo
        mock_model = Mock()
        mock_model.predict = Mock(return_value=np.array([75000.0]))
        predictor.model = mock_model
        predictor.historical_stats = {}

        result = await predictor.predict_duration(sample_ticket)

        assert result['duration_ms'] == 75000.0
        assert result['confidence'] > 0
        mock_model.predict.assert_called_once()
        mock_metrics.record_ml_prediction.assert_called_once()


# Tests - AnomalyDetector

@pytest.mark.asyncio
class TestAnomalyDetector:
    """Testes para AnomalyDetector."""

    async def test_initialization(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics):
        """Testa inicialização do detector."""
        detector = AnomalyDetector(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        with patch('src.ml.anomaly_detector.compute_historical_stats', return_value={}):
            await detector.initialize()

        assert detector.model is not None
        assert detector.contamination == 0.05

    async def test_detect_anomaly_normal_ticket(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics, sample_ticket):
        """Testa detecção em ticket normal."""
        detector = AnomalyDetector(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        # Mock modelo retornando ticket normal
        mock_model = Mock()
        mock_model.predict = Mock(return_value=np.array([1]))  # 1 = normal
        mock_model.score_samples = Mock(return_value=np.array([0.5]))
        detector.model = mock_model
        detector.historical_stats = {}

        result = await detector.detect_anomaly(sample_ticket)

        assert result['is_anomaly'] is False
        assert result['anomaly_score'] == 0.5
        assert result['anomaly_type'] is None

    async def test_detect_anomaly_anomalous_ticket(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics):
        """Testa detecção de ticket anômalo."""
        detector = AnomalyDetector(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        # Ticket com resource mismatch
        anomalous_ticket = {
            'ticket_id': 'anomaly-123',
            'task_type': 'TEST',
            'risk_band': 'low',
            'required_capabilities': ['cap1', 'cap2', 'cap3', 'cap4', 'cap5', 'cap6'],  # Muitas caps
            'qos': {},
            'sla': {},
            'parameters': {},
            'estimated_duration_ms': 10000,
            'created_at': datetime.utcnow().isoformat()
        }

        # Mock modelo retornando anomalia
        mock_model = Mock()
        mock_model.predict = Mock(return_value=np.array([-1]))  # -1 = anomalia
        mock_model.score_samples = Mock(return_value=np.array([-0.8]))
        detector.model = mock_model
        detector.historical_stats = {}

        result = await detector.detect_anomaly(anomalous_ticket)

        assert result['is_anomaly'] is True
        assert result['anomaly_score'] == -0.8
        assert result['anomaly_type'] in AnomalyDetector.ANOMALY_TYPES
        assert 'explanation' in result


# Tests - MLPredictor

@pytest.mark.asyncio
class TestMLPredictor:
    """Testes para MLPredictor facade."""

    async def test_initialization(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics):
        """Testa inicialização do MLPredictor."""
        predictor = MLPredictor(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        with patch.object(predictor.duration_predictor, 'initialize', new_callable=AsyncMock):
            with patch.object(predictor.anomaly_detector, 'initialize', new_callable=AsyncMock):
                await predictor.initialize()

        mock_model_registry.initialize.assert_called_once()

    async def test_predict_and_enrich(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics, sample_ticket):
        """Testa predição e enriquecimento de ticket."""
        predictor = MLPredictor(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        # Mock dos predictors
        predictor.duration_predictor.predict_duration = AsyncMock(return_value={
            'duration_ms': 75000.0,
            'confidence': 0.85
        })
        predictor.anomaly_detector.detect_anomaly = AsyncMock(return_value={
            'is_anomaly': False,
            'anomaly_score': 0.2,
            'anomaly_type': None,
            'explanation': 'Normal'
        })

        enriched_ticket = await predictor.predict_and_enrich(sample_ticket.copy())

        assert 'predictions' in enriched_ticket
        assert enriched_ticket['predictions']['duration_ms'] == 75000.0
        assert enriched_ticket['predictions']['duration_confidence'] == 0.85
        assert 'resource_estimate' in enriched_ticket['predictions']
        assert 'anomaly' in enriched_ticket['predictions']

    def test_estimate_resources(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics):
        """Testa estimativa de recursos."""
        predictor = MLPredictor(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        # BUILD task, high risk, 2 min duration
        resources = predictor._estimate_resources(
            duration_ms=120000.0,
            task_type='BUILD',
            risk_band='high'
        )

        assert 'cpu_m' in resources
        assert 'memory_mb' in resources
        assert 100 <= resources['cpu_m'] <= 4000
        assert 128 <= resources['memory_mb'] <= 4096


# Tests - TrainingPipeline

@pytest.mark.asyncio
class TestTrainingPipeline:
    """Testes para TrainingPipeline."""

    async def test_query_training_data(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics):
        """Testa query de dados de treino."""
        duration_predictor = Mock()
        anomaly_detector = Mock()

        pipeline = TrainingPipeline(
            mock_config,
            mock_mongodb,
            mock_model_registry,
            duration_predictor,
            anomaly_detector,
            mock_metrics
        )

        # Mock retorno do MongoDB
        mock_tickets = [
            {'ticket_id': 'test1', 'status': 'COMPLETED'},
            {'ticket_id': 'test2', 'status': 'COMPLETED'}
        ]
        mock_mongodb.db['execution_tickets'].find = Mock(return_value=Mock(
            to_list=AsyncMock(return_value=mock_tickets)
        ))

        df = await pipeline._query_training_data(window_days=30)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    async def test_run_training_cycle_insufficient_data(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics):
        """Testa ciclo de treino com dados insuficientes."""
        duration_predictor = Mock()
        anomaly_detector = Mock()

        pipeline = TrainingPipeline(
            mock_config,
            mock_mongodb,
            mock_model_registry,
            duration_predictor,
            anomaly_detector,
            mock_metrics
        )

        # Mock retorno vazio do MongoDB
        mock_mongodb.db['execution_tickets'].find = Mock(return_value=Mock(
            to_list=AsyncMock(return_value=[])
        ))

        result = await pipeline.run_training_cycle()

        assert result['status'] == 'skipped'
        assert result['reason'] == 'insufficient_data'


# Tests integrados

@pytest.mark.asyncio
class TestMLIntegration:
    """Testes de integração entre componentes ML."""

    async def test_end_to_end_prediction_flow(self, mock_config, mock_mongodb, mock_model_registry, mock_metrics, sample_ticket):
        """Testa fluxo completo de predição."""
        predictor = MLPredictor(mock_config, mock_mongodb, mock_model_registry, mock_metrics)

        # Mock predictors para retornar valores realistas
        predictor.duration_predictor.predict_duration = AsyncMock(return_value={
            'duration_ms': 75000.0,
            'confidence': 0.85
        })
        predictor.anomaly_detector.detect_anomaly = AsyncMock(return_value={
            'is_anomaly': False,
            'anomaly_score': 0.2,
            'anomaly_type': None,
            'explanation': 'Ticket dentro do padrão esperado'
        })

        # Enriquece ticket
        enriched = await predictor.predict_and_enrich(sample_ticket.copy())

        # Valida estrutura de predições
        assert 'predictions' in enriched
        predictions = enriched['predictions']

        assert predictions['duration_ms'] == 75000.0
        assert predictions['duration_confidence'] == 0.85
        assert predictions['resource_estimate']['cpu_m'] > 0
        assert predictions['resource_estimate']['memory_mb'] > 0
        assert predictions['anomaly']['is_anomaly'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
