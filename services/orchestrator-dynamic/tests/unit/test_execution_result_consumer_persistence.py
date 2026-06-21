"""
Unit tests para persistência de duração no ExecutionResultConsumer.

Cobre o fix fundacional (Task 12 da spec caminho-real-first-class):
o consumer deve persistir actual_duration_ms + completed_at + started_at
no MongoDB execution_tickets quando o resultado chega, desbloqueando a
acumulação de dados reais para treino do DurationPredictor.

Princípios:
- Persistência real quando há duração válida.
- Fail-open: o signal Temporal nunca é bloqueado por falha no Mongo write.
- Skip quando não há duração (não escreve None por cima).
- Compatibilidade retro quando mongodb_client é None.
"""

import json
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

UTC = timezone.utc

import pytest
from src.consumers.execution_result_consumer import ExecutionResultConsumer


@pytest.fixture()
def mock_config():
    config = MagicMock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.execution_result_consumer_group = "test-group"
    config.kafka_security_protocol = "PLAINTEXT"
    return config


@pytest.fixture()
def mock_temporal_client():
    """Temporal client mock (get_workflow_handle é async)."""
    client = MagicMock()
    handle = MagicMock()
    handle.signal = AsyncMock()
    client.get_workflow_handle = AsyncMock(return_value=handle)
    return client


@pytest.fixture()
def mock_redis_client():
    return AsyncMock()


@pytest.fixture()
def mock_metrics():
    metrics = MagicMock()
    metrics.execution_results_processed_total = MagicMock()
    metrics.execution_results_processed_total.labels.return_value = MagicMock()
    metrics.workflow_signals_sent_total = MagicMock()
    return metrics


@pytest.fixture()
def mock_mongodb_client():
    mongo = MagicMock()
    mongo.update_ticket_status = AsyncMock()
    return mongo


def _build_message(payload: dict):
    message = MagicMock()
    message.topic = "execution.results"
    message.partition = 0
    message.offset = 100
    message.value = json.dumps(payload).encode("utf-8")
    return message


def _make_consumer(
    mock_config,
    mock_temporal_client,
    mock_redis_client,
    mock_metrics,
    mongodb_client,
):
    return ExecutionResultConsumer(
        config=mock_config,
        temporal_client=mock_temporal_client,
        redis_client=mock_redis_client,
        metrics=mock_metrics,
        mongodb_client=mongodb_client,
    )


class TestDurationPersistence:
    """Persistência de actual_duration_ms no MongoDB."""

    @pytest.mark.asyncio()
    async def test_persists_duration_and_sends_signal(
        self,
        mock_config,
        mock_temporal_client,
        mock_redis_client,
        mock_metrics,
        mock_mongodb_client,
    ):
        """Deve persistir duração no Mongo E enviar signal Temporal."""
        consumer = _make_consumer(
            mock_config,
            mock_temporal_client,
            mock_redis_client,
            mock_metrics,
            mock_mongodb_client,
        )

        timestamp_ms = 1_700_000_000_000
        message = _build_message(
            {
                "ticket_id": "ticket-123",
                "plan_id": "plan-456",
                "workflow_id": "workflow-789",
                "status": "COMPLETED",
                "actual_duration_ms": 1234,
                "timestamp": timestamp_ms,
                "result": {"success": True},
            }
        )

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, "consumer", mock_consumer):
            await consumer._process_result(message)

        # Persistência no Mongo com campos corretos.
        # completed_at/started_at são datetime (BSON Date), NÃO epoch ms: os três
        # filtros de treino/stats comparam `completed_at >= cutoff_date:datetime`
        # e em BSON um Int64 nunca é >= um Date — persistir epoch ms deixaria o
        # treino a ver 0 amostras (bug verificado empiricamente na auditoria da
        # Task 9 da spec caminho-real-first-class).
        from datetime import datetime

        mock_mongodb_client.update_ticket_status.assert_called_once()
        call = mock_mongodb_client.update_ticket_status.call_args
        assert call.args[0] == "ticket-123"
        assert call.args[1] == "COMPLETED"
        assert call.kwargs["actual_duration_ms"] == 1234
        expected_completed = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=UTC)
        expected_started = datetime.fromtimestamp((timestamp_ms - 1234) / 1000.0, tz=UTC)
        assert call.kwargs["completed_at"] == expected_completed
        assert isinstance(call.kwargs["completed_at"], datetime)
        assert call.kwargs["started_at"] == expected_started

        # Signal Temporal continua a ser enviado
        mock_temporal_client.get_workflow_handle.assert_awaited_once_with("workflow-789")
        handle = mock_temporal_client.get_workflow_handle.return_value
        handle.signal.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_fail_open_mongo_error_does_not_block_signal(
        self,
        mock_config,
        mock_temporal_client,
        mock_redis_client,
        mock_metrics,
        mock_mongodb_client,
    ):
        """Falha no Mongo write NÃO deve bloquear signal Temporal nem commit."""
        mock_mongodb_client.update_ticket_status.side_effect = RuntimeError("mongo down")

        consumer = _make_consumer(
            mock_config,
            mock_temporal_client,
            mock_redis_client,
            mock_metrics,
            mock_mongodb_client,
        )

        message = _build_message(
            {
                "ticket_id": "ticket-123",
                "workflow_id": "workflow-789",
                "status": "COMPLETED",
                "actual_duration_ms": 500,
                "timestamp": 1_700_000_000_000,
                "result": {"success": True},
            }
        )

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, "consumer", mock_consumer):
            # Não deve levantar — fail-open
            await consumer._process_result(message)

        # Mongo foi tentado
        mock_mongodb_client.update_ticket_status.assert_awaited_once()
        # Signal Temporal AINDA é enviado
        mock_temporal_client.get_workflow_handle.assert_awaited_once_with("workflow-789")
        handle = mock_temporal_client.get_workflow_handle.return_value
        handle.signal.assert_awaited_once()
        # Commit feito
        mock_consumer.commit.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_skip_persistence_without_duration(
        self,
        mock_config,
        mock_temporal_client,
        mock_redis_client,
        mock_metrics,
        mock_mongodb_client,
    ):
        """Sem actual_duration_ms (None) NÃO deve chamar update_ticket_status."""
        consumer = _make_consumer(
            mock_config,
            mock_temporal_client,
            mock_redis_client,
            mock_metrics,
            mock_mongodb_client,
        )

        message = _build_message(
            {
                "ticket_id": "ticket-123",
                "workflow_id": "workflow-789",
                "status": "COMPLETED",
                "actual_duration_ms": None,
                "timestamp": 1_700_000_000_000,
                "result": {"success": True},
            }
        )

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, "consumer", mock_consumer):
            await consumer._process_result(message)

        # Não escreve None por cima
        mock_mongodb_client.update_ticket_status.assert_not_called()
        # Signal segue
        mock_temporal_client.get_workflow_handle.assert_awaited_once_with("workflow-789")

    @pytest.mark.asyncio()
    async def test_skip_persistence_with_zero_duration(
        self,
        mock_config,
        mock_temporal_client,
        mock_redis_client,
        mock_metrics,
        mock_mongodb_client,
    ):
        """Duração <= 0 deve ser tratada como inválida (skip)."""
        consumer = _make_consumer(
            mock_config,
            mock_temporal_client,
            mock_redis_client,
            mock_metrics,
            mock_mongodb_client,
        )

        message = _build_message(
            {
                "ticket_id": "ticket-123",
                "workflow_id": "workflow-789",
                "status": "COMPLETED",
                "actual_duration_ms": 0,
                "timestamp": 1_700_000_000_000,
                "result": {"success": True},
            }
        )

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, "consumer", mock_consumer):
            await consumer._process_result(message)

        mock_mongodb_client.update_ticket_status.assert_not_called()
        mock_temporal_client.get_workflow_handle.assert_awaited_once_with("workflow-789")

    @pytest.mark.asyncio()
    async def test_mongodb_client_none_skips_gracefully(
        self,
        mock_config,
        mock_temporal_client,
        mock_redis_client,
        mock_metrics,
    ):
        """Sem mongodb_client (None) deve fazer skip gracioso; signal segue."""
        consumer = _make_consumer(
            mock_config,
            mock_temporal_client,
            mock_redis_client,
            mock_metrics,
            None,
        )

        message = _build_message(
            {
                "ticket_id": "ticket-123",
                "workflow_id": "workflow-789",
                "status": "COMPLETED",
                "actual_duration_ms": 1234,
                "timestamp": 1_700_000_000_000,
                "result": {"success": True},
            }
        )

        mock_consumer = AsyncMock()
        mock_consumer.commit = AsyncMock()

        with patch.object(consumer, "consumer", mock_consumer):
            # Não deve levantar
            await consumer._process_result(message)

        # Signal segue normalmente
        mock_temporal_client.get_workflow_handle.assert_awaited_once_with("workflow-789")
        mock_consumer.commit.assert_awaited_once()
