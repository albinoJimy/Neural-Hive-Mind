"""
Unit tests para IncidentFeedbackConsumer.

Testa o consumer que processa security-incidents do Guard Agents,
implementando feedback loop para ajuste de políticas de segurança.
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from collections import defaultdict

from src.consumers.incident_feedback_consumer import (
    IncidentFeedbackConsumer,
    IncidentSeverity,
    IncidentClassification,
)


@pytest.fixture
def mock_settings():
    """Settings mock para testes."""
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.kafka_consumer_group = "test-group"
    settings.kafka_incidents_topic = "security-incidents"
    settings.kafka_enable_sasl = False
    settings.kafka_sasl_mechanism = "PLAIN"
    settings.kafka_sasl_username = ""
    settings.kafka_sasl_password = ""
    settings.mongodb_incidents_collection = "security_incidents"
    return settings


@pytest.fixture
def mock_incident_classifier():
    """Incident classifier mock."""
    classifier = AsyncMock()
    return classifier


@pytest.fixture
def mock_security_validator():
    """Security validator mock."""
    validator = AsyncMock()
    return validator


@pytest.fixture
def mock_policy_enforcer():
    """Policy enforcer mock."""
    enforcer = AsyncMock()
    return enforcer


@pytest.fixture
def mock_mongodb_client():
    """MongoDB client mock."""
    mongodb = AsyncMock()
    return mongodb


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.incidents_feedback_consumed_total = MagicMock()
    metrics.incidents_feedback_consumed_total.labels.return_value = MagicMock()
    metrics.incidents_feedback_consumed_total.labels.return_value.inc = MagicMock()
    return metrics


@pytest.fixture
def consumer(
    mock_settings,
    mock_incident_classifier,
    mock_security_validator,
    mock_policy_enforcer,
    mock_mongodb_client,
    mock_metrics,
):
    """Consumer instance para testes."""
    return IncidentFeedbackConsumer(
        settings=mock_settings,
        incident_classifier=mock_incident_classifier,
        security_validator=mock_security_validator,
        policy_enforcer=mock_policy_enforcer,
        mongodb_client=mock_mongodb_client,
        metrics=mock_metrics,
    )


class TestIncidentFeedbackConsumerInitialization:
    """Testes de inicialização do consumer."""

    def test_consumer_initialization(self, consumer):
        """Consumer deve ter atributos corretos após criação."""
        assert consumer.settings is not None
        assert consumer.incident_classifier is not None
        assert consumer.security_validator is not None
        assert consumer.policy_enforcer is not None
        assert consumer.mongodb_client is not None
        assert consumer.metrics is not None
        assert consumer.consumer is None
        assert consumer.running is False
        assert isinstance(consumer.incident_stats, defaultdict)

    @pytest.mark.asyncio
    async def test_consumer_initialize(self, consumer):
        """Consumer deve inicializar corretamente."""
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()

        with patch(
            "src.consumers.incident_feedback_consumer.instrument_kafka_consumer"
        ) as mock_instrument:
            mock_instrument.return_value = mock_producer

            await consumer.initialize()

            assert consumer.consumer is not None
            mock_producer.start.assert_called_once()


class TestProcessMessage:
    """Testes de processamento de mensagens."""

    @pytest.mark.asyncio
    async def test_process_incident_feedback(self, consumer):
        """Deve processar feedback de incidente."""
        incident_data = {
            "incident_id": "incident-123",
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": IncidentSeverity.HIGH.value,
            "correlation_id": "corr-789",
            "resolution": {"status": "CONFIRMED"},
        }

        message = MagicMock()
        message.value = json.dumps(incident_data).encode("utf-8")
        message.headers = []
        message.topic = "security-incidents"
        message.partition = 0
        message.offset = 0

        # Mock MongoDB
        consumer.mongodb_client = AsyncMock()

        # Mock commit
        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar estatísticas atualizadas
        assert consumer.incident_stats["THREAT_DETECTED"]["total"] == 1
        assert consumer.incident_stats["THREAT_DETECTED"]["true_positives"] == 1

    @pytest.mark.asyncio
    async def test_process_false_positive(self, consumer):
        """Deve processar falso positivo."""
        incident_data = {
            "incident_id": "incident-123",
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": IncidentSeverity.MEDIUM.value,
            "resolution": {"status": "FALSE_POSITIVE"},
        }

        message = MagicMock()
        message.value = json.dumps(incident_data).encode("utf-8")
        message.headers = []

        consumer.mongodb_client = AsyncMock()
        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message)

        # Verificar falso positivo contabilizado
        assert consumer.incident_stats["THREAT_DETECTED"]["false_positives"] == 1

    @pytest.mark.asyncio
    async def test_update_incident_stats_severity_averaging(self, consumer):
        """Deve calcular média de severidade corretamente."""
        # Primeiro incidente (HIGH = 3.0)
        incident_data_1 = {
            "incident_id": "incident-1",
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": IncidentSeverity.HIGH.value,
            "resolution": {"status": "CONFIRMED"},
        }

        message_1 = MagicMock()
        message_1.value = json.dumps(incident_data_1).encode("utf-8")
        message_1.headers = []

        consumer.mongodb_client = AsyncMock()
        consumer.consumer = AsyncMock()
        consumer.consumer.commit = AsyncMock()

        await consumer._process_message(message_1)

        # Segundo incidente (CRITICAL = 4.0)
        incident_data_2 = {
            "incident_id": "incident-2",
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": IncidentSeverity.CRITICAL.value,
            "resolution": {"status": "CONFIRMED"},
        }

        message_2 = MagicMock()
        message_2.value = json.dumps(incident_data_2).encode("utf-8")
        message_2.headers = []

        await consumer._process_message(message_2)

        # Média deve ser (3.0 + 4.0) / 2 = 3.5
        assert abs(consumer.incident_stats["THREAT_DETECTED"]["avg_severity"] - 3.5) < 0.01


class TestAdjustSecurityParameters:
    """Testes de ajuste de parâmetros de segurança."""

    @pytest.mark.asyncio
    async def test_increase_thresholds_high_fp_rate(self, consumer):
        """Deve aumentar thresholds quando taxa de FP é alta."""
        # Preparar estatísticas
        consumer.incident_stats["THREAT_DETECTED"] = {
            "total": 30,
            "true_positives": 15,
            "false_positives": 15,  # 50% FP (alta)
            "false_negatives": 0,
            "avg_severity": 2.5,
            "last_updated": datetime.now(timezone.utc),
        }

        incident = {
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": "HIGH",
        }

        with patch.object(consumer, "_adjust_detection_thresholds", new=AsyncMock()) as mock_adjust:
            await consumer._adjust_security_parameters(incident)

            # Deve aumentar thresholds
            mock_adjust.assert_called_once_with("THREAT_DETECTED", "higher", 0.1)

    @pytest.mark.asyncio
    async def test_decrease_thresholds_low_fp_rate(self, consumer):
        """Deve reduzir thresholds quando taxa de FP é baixa."""
        consumer.incident_stats["THREAT_DETECTED"] = {
            "total": 30,
            "true_positives": 29,
            "false_positives": 1,  # ~3% FP (baixa)
            "false_negatives": 0,
            "avg_severity": 2.5,
            "last_updated": datetime.now(timezone.utc),
        }

        incident = {
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": "HIGH",
        }

        with patch.object(consumer, "_adjust_detection_thresholds", new=AsyncMock()) as mock_adjust:
            await consumer._adjust_security_parameters(incident)

            # Deve reduzir thresholds
            mock_adjust.assert_called_once_with("THREAT_DETECTED", "lower", 0.05)

    @pytest.mark.asyncio
    async def test_reinforce_policies_high_severity(self, consumer):
        """Deve reforçar políticas quando severidade média é alta."""
        consumer.incident_stats["THREAT_DETECTED"] = {
            "total": 30,
            "true_positives": 20,
            "false_positives": 5,
            "false_negatives": 5,
            "avg_severity": 3.5,  # Alta severidade
            "last_updated": datetime.now(timezone.utc),
        }

        incident = {
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": "HIGH",
        }

        with patch.object(consumer, "_reinforce_policies", new=AsyncMock()) as mock_reinforce:
            await consumer._adjust_security_parameters(incident)

            # Deve reforçar políticas
            mock_reinforce.assert_called_once_with("THREAT_DETECTED")

    @pytest.mark.asyncio
    async def test_wait_for_minimum_samples(self, consumer):
        """Deve esperar por amostragem mínima antes de ajustar."""
        consumer.incident_stats["THREAT_DETECTED"] = {
            "total": 10,  # Menos que 20
            "true_positives": 5,
            "false_positives": 5,
            "false_negatives": 0,
            "avg_severity": 2.5,
            "last_updated": datetime.now(timezone.utc),
        }

        incident = {
            "classification": IncidentClassification.THREAT_DETECTED.value,
            "severity": "HIGH",
        }

        with patch.object(consumer, "_adjust_detection_thresholds", new=AsyncMock()) as mock_adjust:
            await consumer._adjust_security_parameters(incident)

            # Não deve ajustar
            mock_adjust.assert_not_called()


class TestStoreFeedback:
    """Testes de armazenamento de feedback."""

    @pytest.mark.asyncio
    async def test_store_feedback_in_mongodb(self, consumer):
        """Deve armazenar feedback no MongoDB."""
        incident = {
            "incident_id": "incident-123",
            "classification": "THREAT_DETECTED",
            "severity": "HIGH",
        }

        consumer.mongodb_client = AsyncMock()

        await consumer._store_feedback(incident)

        # Deve armazenar com metadados
        consumer.mongodb_client.__getitem__.assert_called()

    @pytest.mark.asyncio
    async def test_store_without_mongodb(self, consumer):
        """Deve lidar gracefully com MongoDB indisponível."""
        consumer.mongodb_client = None

        incident = {"incident_id": "incident-123"}

        # Não deve lançar exceção
        await consumer._store_feedback(incident)


class TestGetFeedbackStats:
    """Testes de recuperação de estatísticas."""

    def test_get_feedback_stats_empty(self, consumer):
        """Deve retornar estatísticas vazias quando não há dados."""
        stats = consumer.get_feedback_stats()

        assert stats["total_incidents"] == 0
        assert stats["total_true_positives"] == 0
        assert stats["total_false_positives"] == 0
        assert stats["global_precision"] == 0.0

    def test_get_feedback_stats_with_data(self, consumer):
        """Deve retornar estatísticas corretas."""
        consumer.incident_stats["THREAT_DETECTED"] = {
            "total": 20,
            "true_positives": 15,
            "false_positives": 3,
            "false_negatives": 2,
            "avg_severity": 2.5,
            "last_updated": datetime.now(timezone.utc),
        }
        consumer.incident_stats["POLICY_VIOLATION"] = {
            "total": 10,
            "true_positives": 8,
            "false_positives": 1,
            "false_negatives": 1,
            "avg_severity": 2.0,
            "last_updated": datetime.now(timezone.utc),
        }

        stats = consumer.get_feedback_stats()

        assert stats["total_incidents"] == 30
        assert stats["total_true_positives"] == 23
        assert stats["total_false_positives"] == 4
        # Precisão global = 23 / (23 + 4) ≈ 0.85
        assert abs(stats["global_precision"] - 0.85) < 0.01


class TestConsumerLifecycle:
    """Testes de ciclo de vida do consumer."""

    @pytest.mark.asyncio
    async def test_start_stop_consumer(self, consumer):
        """Deve iniciar e parar consumer corretamente."""
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()
        mock_producer.stop = AsyncMock()
        mock_producer.__aiter__ = AsyncMock(return_value=iter([]))

        with patch(
            "src.consumers.incident_feedback_consumer.instrument_kafka_consumer"
        ) as mock_instrument:
            mock_instrument.return_value = mock_producer

            await consumer.initialize()
            assert consumer.consumer is not None

            # Simular start (loop vazio)
            start_task = asyncio.create_task(consumer.start())
            await asyncio.sleep(0.1)
            consumer.running = False
            await start_task

            await consumer.stop()
            mock_producer.stop.assert_called_once()
