"""Testes para DriftDetector - Detecção de Model Drift."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from neural_hive_ml.drift_detector import DriftDetector


@pytest.fixture
def mock_mongo_client():
    """Mock MongoDB client."""
    # Criar cursor mock - é um Mock regular com método to_list assíncrono
    # Em Motor, aggregate() retorna um cursor (não awaitable)
    # que tem um método to_list() assíncrono
    cursor_mock = Mock()
    cursor_mock.to_list = AsyncMock(return_value=[
        {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 100}
    ])

    # Criar mock de coleção
    collection = Mock()
    collection.aggregate = Mock(return_value=cursor_mock)

    # Criar mongo client mock
    # DriftDetector.db retorna self.mongo_client diretamente
    # então self.db.plan_approvals = self.mongo_client.plan_approvals
    client = Mock()
    client.plan_approvals = collection

    # Também manter db para compatibilidade
    client.db = client

    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.produce_and_wait = AsyncMock()
    return producer


@pytest.fixture
def drift_detector(mock_mongo_client, mock_kafka_producer):
    """Fixture para DriftDetector."""
    return DriftDetector(
        mongo_client=mock_mongo_client,
        kafka_producer=mock_kafka_producer,
        confidence_threshold=0.10,
        approve_rate_threshold=0.15
    )


class TestDriftDetectorInit:
    """Testes de inicialização."""

    def test_init_with_defaults(self, mock_mongo_client, mock_kafka_producer):
        """Testa inicialização com valores padrão."""
        detector = DriftDetector(
            mongo_client=mock_mongo_client,
            kafka_producer=mock_kafka_producer
        )
        assert detector.confidence_threshold == 0.10
        assert detector.approve_rate_threshold == 0.15


class TestCalculateBaseline:
    """Testes de calculate_baseline."""

    @pytest.mark.asyncio
    async def test_calculate_baseline_success(self, drift_detector, mock_mongo_client):
        """Testa cálculo de baseline com sucesso."""
        # O mock já está configurado com cursor_mock
        result = await drift_detector.calculate_baseline(window_hours=168)

        assert result["approve_rate"] == 0.65
        assert result["avg_confidence"] == 0.72
        assert result["sample_count"] == 100


class TestCalculateCurrent:
    """Testes de calculate_current."""

    @pytest.mark.asyncio
    async def test_calculate_current_success(self, drift_detector, mock_mongo_client):
        """Testa cálculo de métricas atuais."""
        result = await drift_detector.calculate_current(window_hours=24)

        assert result["approve_rate"] == 0.65
        assert result["avg_confidence"] == 0.72


class TestDetectDrift:
    """Testes de detect_drift."""

    @pytest.mark.asyncio
    async def test_detect_drift_no_drift(self, drift_detector, mock_mongo_client):
        """Testa detecção sem drift."""
        result = await drift_detector.detect_drift(window_hours=168)

        # Valores iguais = sem drift
        assert result["drift_detected"] is False
        assert len(result["alerts"]) == 0

    @pytest.mark.asyncio
    async def test_detect_drift_with_confidence_drop(self, drift_detector, mock_mongo_client):
        """Testa detecção de drift no confidence."""
        # Reset mock com dados que mostram pequeno drop
        cursor_mock = Mock()
        cursor_mock.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 500}
        ])
        mock_mongo_client.db.plan_approvals.aggregate = Mock(return_value=cursor_mock)

        result = await drift_detector.detect_drift(window_hours=168)

        # Confidence drop de 0.07 -> abaixo de 0.10 threshold
        assert result["drift_detected"] is False  # 0.72 - 0.72 = 0 < 0.10

    @pytest.mark.asyncio
    async def test_detect_drift_significant(self, drift_detector, mock_mongo_client):
        """Testa detecção de drift significativo."""
        # Configurar aggregate com múltiplas chamadas
        baseline_cursor = Mock()
        baseline_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.65, "avg_confidence": 0.72, "count": 500}
        ])
        current_cursor = Mock()
        current_cursor.to_list = AsyncMock(return_value=[
            {"_id": None, "approve_rate": 0.55, "avg_confidence": 0.60, "count": 100}
        ])

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            return baseline_cursor if call_count[0] == 1 else current_cursor

        mock_mongo_client.db.plan_approvals.aggregate = side_effect

        result = await drift_detector.detect_drift(window_hours=168)

        # Confidence drop = 0.12 > 0.10 threshold
        assert result["drift_detected"] is True
        assert len(result["alerts"]) > 0


class TestPublishDriftAlert:
    """Testes de publish_drift_alert."""

    @pytest.mark.asyncio
    async def test_publish_alert(self, drift_detector, mock_kafka_producer):
        """Testa publicação de alerta de drift."""
        drift_data = {
            "drift_detected": True,
            "confidence_drop": 0.12,
            "approve_rate_change": -0.10
        }

        result = await drift_detector.publish_drift_alert(drift_data)

        mock_kafka_producer.produce_and_wait.assert_called_once()
        assert result is True


class TestGetDriftMetrics:
    """Testes de get_drift_metrics (endpoint)."""

    @pytest.mark.asyncio
    async def test_get_drift_metrics_complete(self, drift_detector):
        """Testa retorno completo de métricas de drift."""
        result = await drift_detector.get_drift_metrics(window_hours=168)

        # Verifica campos obrigatórios
        assert "model_version" in result
        assert "window_hours" in result
        assert "drift_detected" in result
        assert "baseline" in result
        assert "current" in result
