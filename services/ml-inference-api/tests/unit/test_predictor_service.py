"""
Unit Tests para Predictor Service - ML Inference API

Testes unitários para o serviço de predição que encapsula o ApprovalPredictor.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.observability.metrics import MLInferenceMetrics
from src.services.predictor_service import PredictorService

# ===== FIXTURES =====


@pytest.fixture
def mock_metrics():
    """Métricas mockadas para testes."""
    metrics = MagicMock(spec=MLInferenceMetrics)

    # Mock counters
    metrics.predictions_total = MagicMock()
    metrics.predictions_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    metrics.prediction_duration_seconds = MagicMock()
    metrics.prediction_duration_seconds.observe = MagicMock()

    metrics.prediction_confidence = MagicMock()
    metrics.prediction_confidence.observe = MagicMock()

    metrics.api_errors_total = MagicMock()
    metrics.api_errors_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

    # Mock gauges
    metrics.model_loaded = MagicMock()
    metrics.model_loaded.set = MagicMock()

    metrics.model_loading_duration_seconds = MagicMock()
    metrics.model_loading_duration_seconds.observe = MagicMock()

    metrics.model_version_info = MagicMock()
    metrics.model_version_info.info = MagicMock()

    return metrics


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    settings = SimpleNamespace(
        mlflow_tracking_uri="http://localhost:5000",
        mlflow_model_name="approval_model",
        local_model_path="/app/ml_models",
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
        prometheus_port=9090,
        log_level="INFO",
        environment="test",
        service_name="ml-inference-api",
        batch_default_size=10,
        batch_max_size=100,
        batch_timeout_seconds=5.0,
        circuit_breaker_threshold=5,
        circuit_breaker_timeout_seconds=60,
        enable_gpu=False,
        is_public_api=True,
    )
    return settings


@pytest.fixture
def mock_approval_predictor():
    """Mock do ApprovalPredictor."""
    predictor = MagicMock()

    # Mock predict_from_text
    predictor.predict_from_text.return_value = {
        "decision": "approve",
        "confidence": 0.85,
        "probabilities": {"approve": 0.85, "reject": 0.15},
        "model_version": "v7",
    }

    # Mock predict_from_nlp_features
    predictor.predict_from_nlp_features.return_value = {
        "decision": "approve",
        "confidence": 0.82,
        "probabilities": {"approve": 0.82, "reject": 0.18},
        "model_version": "v7",
    }

    # Mock get_model_info
    predictor.get_model_info.return_value = {
        "version": "v7",
        "trained_at": "2026-03-15T10:00:00Z",
        "features": ["specialist_confidence", "domain_security", "domain_performance"],
        "metrics": {"f1_score": 0.9120, "accuracy": 0.8933},
        "training_samples": 75,
    }

    # Mock model_path
    predictor.model_path = "/app/ml_models/nhm_approval_model.pkl"
    predictor.model = MagicMock()

    return predictor


@pytest.fixture
def sample_nlp_features():
    """Features NLP de exemplo."""
    return {
        "specialist_confidence": 0.75,
        "domain_security": 1.0,
        "domain_performance": 0.0,
        "domain_database": 0.0,
        "domain_devops": 0.0,
        "domain_testing": 0.0,
        "action_create": 1.0,
        "action_update": 0.0,
        "action_delete": 0.0,
        "action_read": 0.0,
        "action_deploy": 0.0,
        "has_backup": 1.0,
        "has_verification": 1.0,
        "has_all": 0.0,
        "text_length_chars": 45,
        "text_length_words": 7,
        "risk_high": 0.0,
        "risk_medium": 0.0,
        "risk_low": 1.0,
        "simple_risk_score": 0.0,
        "primary_domain_security": 1.0,
        "primary_domain_performance": 0.0,
        "primary_domain_database": 0.0,
        "primary_domain_devops": 0.0,
        "primary_domain_testing": 0.0,
        "primary_action_create": 1.0,
        "primary_action_update": 0.0,
        "primary_action_delete": 0.0,
        "primary_action_read": 0.0,
        "primary_action_deploy": 0.0,
    }


# ===== TESTES: Initialization =====


class TestPredictorServiceInit:
    """Testes de inicialização do PredictorService."""

    def test_init_creates_service(self, mock_metrics):
        """
        DADO: Métricas válidas
        QUANDO: Crio PredictorService
        ENTÃO: Deve inicializar corretamente
        """
        service = PredictorService(metrics=mock_metrics)

        assert service.metrics is not None
        assert service.approval_predictor is None  # Não carregado ainda
        assert service.model_info == {}

    def test_init_with_circuit_breaker(self, mock_metrics, mock_settings):
        """
        DADO: Métricas e configurações
        QUANDO: Crio PredictorService
        ENTÃO: Deve criar circuit breaker com configurações corretas
        """
        with patch("src.services.predictor_service.settings", mock_settings):
            service = PredictorService(metrics=mock_metrics)

        assert service._circuit_breaker is not None
        assert service._load_lock is not None


# ===== TESTES: Load Model =====


class TestLoadModel:
    """Testes do método load_model."""

    @pytest.mark.asyncio
    async def test_load_model_success(self, mock_metrics, mock_approval_predictor, mock_settings):
        """
        DADO: ApprovalPredictor disponível
        QUANDO: Carrego modelo
        ENTÃO: Deve carregar corretamente e preencher model_info
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            await service.load_model()

        assert service.approval_predictor is not None
        assert service.model_info["version"] == "v7"
        assert service.model_info["training_samples"] == 75

    @pytest.mark.asyncio
    async def test_load_model_idempotent(
        self, mock_metrics, mock_approval_predictor, mock_settings
    ):
        """
        DADO: Modelo já carregado
        QUANDO: Chamo load_model novamente
        ENTÃO: Não deve recarregar
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            await service.load_model()

            # Chamar novamente - deve usar lock e não recarregar
            first_predictor = service.approval_predictor
            await service.load_model()

            assert service.approval_predictor is first_predictor

    @pytest.mark.asyncio
    async def test_load_model_file_not_found(self, mock_metrics, mock_settings):
        """
        DADO: Modelo não existe no disco
        QUANDO: Carrego modelo
        ENTÃO: Deve levantar RuntimeError
        """
        # Mock que levanta FileNotFoundError
        mock_ap_class = MagicMock(side_effect=FileNotFoundError("Model not found"))

        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", mock_ap_class
        ):
            service = PredictorService(metrics=mock_metrics)

            with pytest.raises(RuntimeError, match="Failed to load ML model"):
                await service.load_model()


# ===== TESTES: Predict =====


class TestPredict:
    """Testes do método predict."""

    @pytest.mark.asyncio
    async def test_predict_success(self, mock_metrics, mock_approval_predictor, mock_settings):
        """
        DADO: Um request válido com intent_text
        QUANDO: Chamo predict
        ENTÃO: Deve retornar predição com decision e confidence
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            service.approval_predictor = mock_approval_predictor

            result = await service.predict(
                intent_text="Create new user with email verification", specialist_confidence=0.75
            )

        assert result["decision"] == "approve"
        assert result["confidence"] == 0.85
        assert "probabilities" in result
        assert result["model_version"] == "v7"

    @pytest.mark.asyncio
    async def test_predict_with_specialist_confidence(
        self, mock_metrics, mock_approval_predictor, mock_settings
    ):
        """
        DADO: Um request com specialist_confidence específico
        QUANDO: Chamo predict
        ENTÃO: Deve passar a confiança para o predictor
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            service.approval_predictor = mock_approval_predictor
            specialist_confidence = 0.92

            await service.predict(
                intent_text="Deploy to production", specialist_confidence=specialist_confidence
            )

        # Verificar que o predictor foi chamado com a confiança correta
        call_args = mock_approval_predictor.predict_from_text.call_args
        assert call_args[1]["specialist_confidence"] == specialist_confidence

    @pytest.mark.asyncio
    async def test_predict_triggers_model_load(
        self, mock_metrics, mock_approval_predictor, mock_settings
    ):
        """
        DADO: Serviço sem modelo carregado
        QUANDO: Chamo predict
        ENTÃO: Deve carregar o modelo automaticamente
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            # approval_predictor é None inicialmente

            result = await service.predict(intent_text="Test intent", specialist_confidence=0.5)

        assert service.approval_predictor is not None
        assert result["decision"] == "approve"


# ===== TESTES: Predict from NLP Features =====


class TestPredictFromNLPFeatures:
    """Testes do método predict_from_nlp_features."""

    @pytest.mark.asyncio
    async def test_predict_from_features_success(
        self, mock_metrics, mock_approval_predictor, sample_nlp_features, mock_settings
    ):
        """
        DADO: Um request com features NLP válidas
        QUANDO: Chamo predict_from_nlp_features
        ENTÃO: Deve retornar predição com decision e confidence
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            service.approval_predictor = mock_approval_predictor

            result = await service.predict_from_nlp_features(
                nlp_features=sample_nlp_features, specialist_confidence=0.75
            )

        assert result["decision"] == "approve"
        assert result["confidence"] == 0.82
        mock_approval_predictor.predict_from_nlp_features.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_from_features_triggers_model_load(
        self, mock_metrics, mock_approval_predictor, sample_nlp_features, mock_settings
    ):
        """
        DADO: Serviço sem modelo carregado
        QUANDO: Chamo predict_from_nlp_features
        ENTÃO: Deve carregar o modelo automaticamente
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            # approval_predictor é None inicialmente

            result = await service.predict_from_nlp_features(
                nlp_features=sample_nlp_features, specialist_confidence=0.5
            )

        assert service.approval_predictor is not None
        assert result["decision"] == "approve"


# ===== TESTES: Get Model Info =====


class TestGetModelInfo:
    """Testes do método get_model_info."""

    @pytest.mark.asyncio
    async def test_get_model_info_not_loaded(self, mock_metrics):
        """
        DADO: Serviço sem modelo carregado
        QUANDO: Chamo get_model_info
        ENTÃO: Deve retornar info com is_loaded=False
        """
        service = PredictorService(metrics=mock_metrics)
        # Não carregar modelo

        result = service.get_model_info()

        assert result["is_loaded"] is False
        assert "name" in result

    @pytest.mark.asyncio
    async def test_get_model_info_loaded(
        self, mock_metrics, mock_approval_predictor, mock_settings
    ):
        """
        DADO: Um serviço com modelo carregado
        QUANDO: Chamo get_model_info
        ENTÃO: Deve retornar informações do modelo
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            service.approval_predictor = mock_approval_predictor
            service.model_info = mock_approval_predictor.get_model_info()

            result = service.get_model_info()

        assert result["is_loaded"] is True
        assert result["version"] == "v7"
        assert result["training_samples"] == 75
        assert "metrics" in result


# ===== TESTES: Circuit Breaker State =====


class TestCircuitBreaker:
    """Testes do circuit breaker."""

    def test_get_circuit_breaker_state(self, mock_metrics):
        """
        DADO: Serviço inicializado
        QUANDO: Chamo get_circuit_breaker_state
        ENTÃO: Deve retornar estado do circuit breaker
        """
        service = PredictorService(metrics=mock_metrics)
        state = service.get_circuit_breaker_state()

        assert "state" in state
        assert "failure_count" in state

    def test_reset_circuit_breaker(self, mock_metrics):
        """
        DADO: Serviço inicializado
        QUANDO: Chamo reset_circuit_breaker
        ENTÃO: Deve resetar o circuit breaker
        """
        service = PredictorService(metrics=mock_metrics)
        service.reset_circuit_breaker()

        # Verificar que estado foi resetado
        state = service.get_circuit_breaker_state()
        assert state["failure_count"] == 0


# ===== TESTES: Health Check =====


class TestHealthCheck:
    """Testes do health check."""

    @pytest.mark.asyncio
    async def test_is_healthy_with_model_loaded(
        self, mock_metrics, mock_approval_predictor, mock_settings
    ):
        """
        DADO: Serviço com modelo carregado
        QUANDO: Verifico is_healthy
        ENTÃO: Deve retornar True
        """
        with patch("src.services.predictor_service.settings", mock_settings), patch(
            "src.services.predictor_service.ApprovalPredictor", return_value=mock_approval_predictor
        ):
            service = PredictorService(metrics=mock_metrics)
            service.approval_predictor = mock_approval_predictor

        assert service.is_healthy is True

    def test_is_healthy_without_model(self, mock_metrics):
        """
        DADO: Serviço sem modelo carregado
        QUANDO: Verifico is_healthy
        ENTÃO: Deve retornar False
        """
        service = PredictorService(metrics=mock_metrics)

        assert service.is_healthy is False
