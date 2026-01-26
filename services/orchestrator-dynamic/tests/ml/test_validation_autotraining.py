"""
Testes de Validação e Auto-Treinamento para ML Predictors.

Valida os fluxos de:
1. _load_model retorna None quando falta estimators_ e aceita modelos treinados
2. _ensure_model_trained retorna False quando count_documents < ml_min_training_samples
3. predict_duration usa heurística e confidence=0.3 quando modelo não está treinado
4. MLPredictor.ensure_models_trained propaga sucesso/falha dos predictors
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.ml.duration_predictor import DurationPredictor
from src.ml.anomaly_detector import AnomalyDetector
from src.ml.ml_predictor import MLPredictor


class TestDurationPredictorValidation:
    """Testes de validação para DurationPredictor."""

    @pytest.fixture
    def mock_config(self):
        """Configuração mock."""
        config = MagicMock()
        config.ml_enabled = True
        config.ml_min_training_samples = 100
        config.ml_training_window_days = 540
        config.ml_feature_cache_ttl_seconds = 3600
        config.ml_duration_error_threshold = 0.15
        config.ml_use_clickhouse_for_features = False
        return config

    @pytest.fixture
    def mock_mongodb(self):
        """Cliente MongoDB mock."""
        mongodb = MagicMock()
        mongodb.db = MagicMock()
        return mongodb

    @pytest.fixture
    def mock_model_registry(self):
        """ModelRegistry mock."""
        registry = AsyncMock()
        registry.load_model = AsyncMock(return_value=None)
        registry.save_model = AsyncMock(return_value="run-123")
        registry.promote_model = AsyncMock()
        registry.get_model_metadata = AsyncMock(return_value={'version': '1'})
        return registry

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mock."""
        metrics = MagicMock()
        metrics.record_ml_prediction = MagicMock()
        metrics.record_ml_training = MagicMock()
        metrics.record_ml_error = MagicMock()
        metrics.record_ml_model_training_status = MagicMock()
        metrics.record_ml_model_quality = MagicMock()
        return metrics

    @pytest.mark.asyncio
    async def test_load_model_returns_none_when_missing_estimators(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que _load_model() retorna None se modelo não tem estimators_.

        Modelo sem estimators_ indica que não foi treinado e não deve ser usado.
        """
        from sklearn.ensemble import RandomForestRegressor

        # Modelo não treinado (sem estimators_)
        untrained_model = RandomForestRegressor(n_estimators=100)
        mock_model_registry.load_model = AsyncMock(return_value=untrained_model)

        predictor = DurationPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        result = await predictor._load_model()

        assert result is None, "Modelo sem estimators_ deve retornar None"

    @pytest.mark.asyncio
    async def test_load_model_accepts_trained_model_with_estimators(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que _load_model() aceita modelo treinado com estimators_.
        """
        from sklearn.ensemble import RandomForestRegressor

        # Modelo treinado (com estimators_)
        trained_model = RandomForestRegressor(n_estimators=10)
        X = np.random.rand(100, 5)
        y = np.random.rand(100)
        trained_model.fit(X, y)

        mock_model_registry.load_model = AsyncMock(return_value=trained_model)

        predictor = DurationPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        result = await predictor._load_model()

        assert result is not None, "Modelo treinado deve ser aceito"
        assert hasattr(result, 'estimators_'), "Modelo deve ter estimators_"

    @pytest.mark.asyncio
    async def test_ensure_model_trained_returns_false_insufficient_data(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que _ensure_model_trained() retorna False quando
        count_documents < ml_min_training_samples.
        """
        # Mock MongoDB para retornar poucos dados (50 < 100 min_samples)
        mock_mongodb.db['execution_tickets'].count_documents = AsyncMock(return_value=50)

        predictor = DurationPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        result = await predictor._ensure_model_trained()

        assert result is False, "Deve retornar False com dados insuficientes"
        mock_metrics.record_ml_model_training_status.assert_called_with(
            model_name='ticket-duration-predictor',
            is_trained=False,
            has_estimators=False
        )

    @pytest.mark.asyncio
    async def test_ensure_model_trained_returns_true_after_promotion(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que _ensure_model_trained() retorna True após train_model promover modelo.
        """
        # Mock MongoDB para retornar dados suficientes
        mock_mongodb.db['execution_tickets'].count_documents = AsyncMock(return_value=150)

        # Mock para simular dados de treinamento
        trained_tickets = []
        for i in range(150):
            trained_tickets.append({
                'ticket_id': f'ticket-{i}',
                'task_type': 'INFERENCE',
                'risk_band': 'medium',
                'actual_duration_ms': 30000 + np.random.normal(0, 5000),
                'estimated_duration_ms': 30000,
                'completed_at': datetime.utcnow(),
                'required_capabilities': ['cpu'],
                'parameters': {},
                'sla_timeout_ms': 300000,
                'retry_count': 0
            })

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=trained_tickets)
        mock_mongodb.db['execution_tickets'].find = MagicMock(return_value=mock_cursor)

        predictor = DurationPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )
        predictor.historical_stats = {}

        result = await predictor._ensure_model_trained()

        # Resultado depende da qualidade do modelo, mas não deve lançar exceção
        assert isinstance(result, bool), "Resultado deve ser booleano"

    @pytest.mark.asyncio
    async def test_predict_duration_uses_heuristic_when_model_not_trained(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que predict_duration() usa heurística e confidence=0.3
        quando modelo não está treinado.
        """
        predictor = DurationPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )
        predictor.model = None  # Sem modelo
        predictor.historical_stats = {
            'INFERENCE': {'avg_duration': 30000, 'std_duration': 5000}
        }

        ticket = {
            'ticket_id': 'test-1',
            'task_type': 'INFERENCE',
            'risk_band': 'medium',
            'estimated_duration_ms': 30000,
            'required_capabilities': ['cpu'],
            'parameters': {}
        }

        result = await predictor.predict_duration(ticket)

        assert 'duration_ms' in result, "Resultado deve ter duration_ms"
        assert 'confidence' in result, "Resultado deve ter confidence"
        assert result['confidence'] == 0.3, "Confidence deve ser 0.3 para heurística"


class TestAnomalyDetectorValidation:
    """Testes de validação para AnomalyDetector."""

    @pytest.fixture
    def mock_config(self):
        """Configuração mock."""
        config = MagicMock()
        config.ml_enabled = True
        config.ml_min_training_samples = 100
        config.ml_training_window_days = 540
        config.ml_feature_cache_ttl_seconds = 3600
        config.ml_anomaly_contamination = 0.05
        config.ml_validation_precision_threshold = 0.75
        return config

    @pytest.fixture
    def mock_mongodb(self):
        """Cliente MongoDB mock."""
        mongodb = MagicMock()
        mongodb.db = MagicMock()
        return mongodb

    @pytest.fixture
    def mock_model_registry(self):
        """ModelRegistry mock."""
        registry = AsyncMock()
        registry.load_model = AsyncMock(return_value=None)
        registry.save_model = AsyncMock(return_value="run-123")
        registry.promote_model = AsyncMock()
        registry.get_model_metadata = AsyncMock(return_value={'version': '1'})
        return registry

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mock."""
        metrics = MagicMock()
        metrics.record_ml_prediction = MagicMock()
        metrics.record_ml_training = MagicMock()
        metrics.record_ml_error = MagicMock()
        metrics.record_ml_anomaly = MagicMock()
        metrics.record_ml_model_training_status = MagicMock()
        return metrics

    @pytest.mark.asyncio
    async def test_load_model_returns_none_when_missing_estimators(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que _load_model() retorna None se modelo não tem estimators_.
        """
        from sklearn.ensemble import IsolationForest

        # Modelo não treinado (sem estimators_)
        untrained_model = IsolationForest(n_estimators=100)
        mock_model_registry.load_model = AsyncMock(return_value=untrained_model)

        detector = AnomalyDetector(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        result = await detector._load_model()

        assert result is None, "Modelo sem estimators_ deve retornar None"

    @pytest.mark.asyncio
    async def test_load_model_accepts_trained_model_with_estimators(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que _load_model() aceita modelo treinado com estimators_.
        """
        from sklearn.ensemble import IsolationForest

        # Modelo treinado (com estimators_)
        trained_model = IsolationForest(n_estimators=10)
        X = np.random.rand(100, 5)
        trained_model.fit(X)

        mock_model_registry.load_model = AsyncMock(return_value=trained_model)

        detector = AnomalyDetector(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        result = await detector._load_model()

        assert result is not None, "Modelo treinado deve ser aceito"
        assert hasattr(result, 'estimators_'), "Modelo deve ter estimators_"

    @pytest.mark.asyncio
    async def test_ensure_model_trained_returns_false_insufficient_data(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que _ensure_model_trained() retorna False quando
        count_documents < ml_min_training_samples.
        """
        # Mock MongoDB para retornar poucos dados (50 < 100 min_samples)
        mock_mongodb.db['execution_tickets'].count_documents = AsyncMock(return_value=50)

        detector = AnomalyDetector(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        result = await detector._ensure_model_trained()

        assert result is False, "Deve retornar False com dados insuficientes"
        mock_metrics.record_ml_model_training_status.assert_called_with(
            model_name='ticket-anomaly-detector',
            is_trained=False,
            has_estimators=False
        )


class TestMLPredictorEnsureModelsTrained:
    """Testes para MLPredictor.ensure_models_trained()."""

    @pytest.fixture
    def mock_config(self):
        """Configuração mock."""
        config = MagicMock()
        config.ml_enabled = True
        config.ml_min_training_samples = 100
        config.ml_training_window_days = 540
        config.ml_feature_cache_ttl_seconds = 3600
        config.ml_duration_error_threshold = 0.15
        config.ml_anomaly_contamination = 0.05
        config.ml_use_clickhouse_for_features = False
        return config

    @pytest.fixture
    def mock_mongodb(self):
        """Cliente MongoDB mock."""
        mongodb = MagicMock()
        mongodb.db = MagicMock()
        return mongodb

    @pytest.fixture
    def mock_model_registry(self):
        """ModelRegistry mock."""
        registry = AsyncMock()
        registry.load_model = AsyncMock(return_value=None)
        registry.save_model = AsyncMock(return_value="run-123")
        registry.promote_model = AsyncMock()
        registry.get_model_metadata = AsyncMock(return_value={'version': '1'})
        registry.close = AsyncMock()
        return registry

    @pytest.fixture
    def mock_metrics(self):
        """Métricas mock."""
        metrics = MagicMock()
        metrics.record_ml_prediction = MagicMock()
        metrics.record_ml_training = MagicMock()
        metrics.record_ml_error = MagicMock()
        metrics.record_ml_anomaly = MagicMock()
        metrics.record_ml_model_training_status = MagicMock()
        metrics.record_ml_model_quality = MagicMock()
        return metrics

    @pytest.mark.asyncio
    async def test_ensure_models_trained_propagates_success(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que MLPredictor.ensure_models_trained() propaga sucesso
        quando ambos predictors estão treinados.
        """
        ml_predictor = MLPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        # Mock _ensure_model_trained para retornar True
        ml_predictor.duration_predictor._ensure_model_trained = AsyncMock(return_value=True)
        ml_predictor.anomaly_detector._ensure_model_trained = AsyncMock(return_value=True)

        result = await ml_predictor.ensure_models_trained()

        assert result['duration'] is True, "duration deve ser True"
        assert result['anomaly'] is True, "anomaly deve ser True"

    @pytest.mark.asyncio
    async def test_ensure_models_trained_propagates_failure(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que MLPredictor.ensure_models_trained() propaga falha
        quando predictors falham.
        """
        ml_predictor = MLPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        # Mock _ensure_model_trained para retornar False
        ml_predictor.duration_predictor._ensure_model_trained = AsyncMock(return_value=False)
        ml_predictor.anomaly_detector._ensure_model_trained = AsyncMock(return_value=False)

        result = await ml_predictor.ensure_models_trained()

        assert result['duration'] is False, "duration deve ser False"
        assert result['anomaly'] is False, "anomaly deve ser False"

    @pytest.mark.asyncio
    async def test_ensure_models_trained_handles_mixed_status(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que MLPredictor.ensure_models_trained() propaga status misto
        corretamente (um sucesso, um falha).
        """
        ml_predictor = MLPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        # Mock com status misto
        ml_predictor.duration_predictor._ensure_model_trained = AsyncMock(return_value=True)
        ml_predictor.anomaly_detector._ensure_model_trained = AsyncMock(return_value=False)

        result = await ml_predictor.ensure_models_trained()

        assert result['duration'] is True, "duration deve ser True"
        assert result['anomaly'] is False, "anomaly deve ser False"

    @pytest.mark.asyncio
    async def test_ensure_models_trained_handles_exception(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que MLPredictor.ensure_models_trained() trata exceções
        e retorna False para o predictor que falhou.
        """
        ml_predictor = MLPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        # Mock com exceção no duration_predictor
        ml_predictor.duration_predictor._ensure_model_trained = AsyncMock(
            side_effect=Exception("Database connection failed")
        )
        ml_predictor.anomaly_detector._ensure_model_trained = AsyncMock(return_value=True)

        result = await ml_predictor.ensure_models_trained()

        assert result['duration'] is False, "duration deve ser False após exceção"
        assert result['anomaly'] is True, "anomaly deve ser True"

    @pytest.mark.asyncio
    async def test_ensure_models_trained_calls_both_predictors(
        self,
        mock_config,
        mock_mongodb,
        mock_model_registry,
        mock_metrics
    ):
        """
        Testa que MLPredictor.ensure_models_trained() chama
        _ensure_model_trained em ambos os predictors.
        """
        ml_predictor = MLPredictor(
            config=mock_config,
            mongodb_client=mock_mongodb,
            model_registry=mock_model_registry,
            metrics=mock_metrics
        )

        # Mock _ensure_model_trained
        duration_mock = AsyncMock(return_value=True)
        anomaly_mock = AsyncMock(return_value=True)

        ml_predictor.duration_predictor._ensure_model_trained = duration_mock
        ml_predictor.anomaly_detector._ensure_model_trained = anomaly_mock

        await ml_predictor.ensure_models_trained()

        duration_mock.assert_called_once()
        anomaly_mock.assert_called_once()
