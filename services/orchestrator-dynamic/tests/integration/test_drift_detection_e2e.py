"""
Testes E2E de Drift Detection - TICKET 2.5

Estes testes validam a integração completa do drift detector com o orchestrator.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.ml.drift_detector import DriftDetector
from src.consumers.decision_consumer import DecisionConsumer
from src.config.settings import OrchestratorSettings
from src.clients.mongodb_client import MongoDBClient
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
async def mock_mongo_client():
    """Mock do MongoDB client."""
    client = AsyncMock(spec=MongoDBClient)
    return client


@pytest.fixture
def drift_settings():
    """Configurações para drift detector."""
    settings = OrchestratorSettings()
    settings.ml_drift_psi_threshold = 0.25
    settings.ml_drift_mae_ratio_threshold = 1.5
    settings.ml_drift_ks_pvalue_threshold = 0.05
    settings.ml_drift_check_window_days = 7
    return settings


@pytest.fixture
async def drift_detector(drift_settings, mock_mongo_client):
    """Instância do DriftDetector para testes."""
    metrics = OrchestratorMetrics()
    detector = DriftDetector(
        config=drift_settings, mongodb_client=mock_mongo_client, metrics=metrics
    )
    return detector


class TestDriftDetectionNoDrift:
    """Testes: drift não detectado com dados normais."""

    @pytest.mark.asyncio
    async def test_no_drift_with_normal_data(self, drift_detector, mock_mongo_client):
        """Com dados normais, drift não deve ser detectado."""
        # Setup mock para retornar dados normais
        mock_mongo_client.aggregate.return_value.to_list = AsyncMock(
            return_value=[
                {"duration_ms": 50000, "complexity": 0.4},
                {"duration_ms": 48000, "complexity": 0.35},
            ]
        )

        # Executar check de drift
        report = await drift_detector.run_drift_check()

        # Validar que não há drift crítico
        assert report["overall_status"] in ["ok", "warning"]
        assert report["overall_status"] != "critical"


class TestDriftDetectionWithDrift:
    """Testes: drift detectado com dados desbalanceados."""

    @pytest.mark.asyncio
    async def test_drift_detected_with_imbalanced_data(self, drift_detector, mock_mongo_client):
        """Com dados desbalanceados, drift deve ser detectado."""

        # Setup mock para retornar dados desbalanceados
        async def mock_aggregate(*args, **kwargs):
            class Result:
                async def to_list(self, length):
                    return [
                        {"duration_ms": 90000, "complexity": 0.95},
                        {"duration_ms": 85000, "complexity": 0.9},
                    ]

            return Result()

        mock_mongo_client.aggregate.return_value = mock_aggregate()

        # Executar check de drift
        report = await drift_detector.run_drift_check()

        # Validar detecção de drift
        assert report["overall_status"] in ["warning", "critical"]


class TestDecisionMarkingWithDrift:
    """Testes: marcação de decisões quando drift detectado."""

    @pytest.mark.asyncio
    async def test_decision_marked_when_drift_detected(self, drift_settings, mock_mongo_client):
        """Quando drift detectado, decisões devem ser marcadas."""
        metrics = OrchestratorMetrics()
        drift_detector = DriftDetector(
            config=drift_settings, mongodb_client=mock_mongo_client, metrics=metrics
        )

        consumer = DecisionConsumer(
            settings=drift_settings, metrics=metrics, drift_detector=drift_detector
        )

        # Mock drift check para retornar warning
        with patch.object(
            drift_detector,
            "run_drift_check",
            return_value={
                "overall_status": "warning",
                "recommendations": ["Feature drift detectado"],
            },
        ):
            result = await consumer._check_ml_drift()

        # Validar marcação
        assert result["drift_detected"] == True
        assert result["drift_status"] == "warning"
        assert "drift_timestamp" in result


class TestE2EOrchestratorWithDrift:
    """Testes E2E: mensagem Kafka até workflow com drift check."""

    @pytest.mark.asyncio
    async def test_e2e_message_with_drift_check_enabled(self, drift_settings, mock_mongo_client):
        """Teste E2E: mensagem processada com drift check ativo."""
        metrics = OrchestratorMetrics()
        drift_detector = DriftDetector(
            config=drift_settings, mongodb_client=mock_mongo_client, metrics=metrics
        )

        consumer = DecisionConsumer(
            settings=drift_settings, metrics=metrics, drift_detector=drift_detector
        )

        # Mock drift check
        with patch.object(
            drift_detector,
            "run_drift_check",
            return_value={
                "overall_status": "ok",
                "feature_drift": {},
                "prediction_drift": {},
                "target_drift": {},
            },
        ):
            drift_result = await consumer._check_ml_drift()

        # Validar processamento
        assert drift_result["drift_detected"] == False
        assert drift_result["drift_status"] == "ok"


class TestDriftDetectorGracefulDegradation:
    """Testes: graceful degradation quando drift detector falha."""

    @pytest.mark.asyncio
    async def test_consumer_works_without_drift_detector(self, drift_settings, mock_mongo_client):
        """Consumer deve funcionar mesmo sem drift detector."""
        metrics = OrchestratorMetrics()

        # Criar consumer SEM drift detector
        consumer = DecisionConsumer(settings=drift_settings, metrics=metrics, drift_detector=None)

        # Executar check sem detector
        result = await consumer._check_ml_drift()

        # Validar graceful degradation
        assert result["drift_detected"] == False
        assert result["drift_status"] == "not_available"
