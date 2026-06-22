"""
Unit tests para o adapter EXECUTE do loop OBSERVE→LEARN.

Spec: docs/specs/2026-06-22-fundacao-loop-learn — Fase 1 (Adapter EXECUTE).

O ExecutionResultConsumer é a capacidade EXECUTE: traduz o ExecutionResult
(formato do worker) para o contrato canónico ExecutionFeedback e delega ao
FeedbackSink (plano-Z). NÃO contém lógica de Mongo. A persistência é
desacoplada do signal Temporal: falha de feedback nunca impede o workflow.

NOTA: ficheiro novo — não toca o test_execution_result_consumer.py (contrato).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.consumers.execution_result_consumer import ExecutionResultConsumer
from src.models.execution_feedback import ExecutionFeedback


@pytest.fixture()
def mock_config():
    config = MagicMock()
    config.kafka_bootstrap_servers = "localhost:9092"
    config.execution_result_consumer_group = "test-group"
    config.kafka_security_protocol = "PLAINTEXT"
    return config


@pytest.fixture()
def mock_temporal_client():
    client = MagicMock()
    handle = MagicMock()
    handle.signal = AsyncMock()
    client.get_workflow_handle = AsyncMock(return_value=handle)
    return client


@pytest.fixture()
def mock_sink():
    sink = MagicMock()
    sink.record = AsyncMock()
    return sink


def _result(**overrides):
    base = {
        "ticket_id": "t1",
        "plan_id": "p1",
        "workflow_id": "wf1",
        "status": "COMPLETED",
        "actual_duration_ms": 1500,
        "started_at": 100,
        "completed_at": 1600,
        "trace_id": "tr1",
        "metadata": {"simulated": False},
    }
    base.update(overrides)
    return base


class TestEmitFeedbackAdapter:
    @pytest.mark.asyncio()
    async def test_translates_result_to_execution_feedback(
        self, mock_config, mock_temporal_client, mock_sink
    ):
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=mock_sink,
        )

        await consumer._emit_feedback(_result())

        mock_sink.record.assert_awaited_once()
        fb = mock_sink.record.call_args[0][0]
        assert isinstance(fb, ExecutionFeedback)
        assert fb.capability == "EXECUTE"
        assert fb.ticket_id == "t1"
        assert fb.plan_id == "p1"
        assert fb.status == "COMPLETED"
        assert fb.actual_duration_ms == 1500
        assert fb.completed_at == 1600
        assert fb.trace_id == "tr1"

    @pytest.mark.asyncio()
    async def test_maps_simulated_from_metadata(
        self, mock_config, mock_temporal_client, mock_sink
    ):
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=mock_sink,
        )

        await consumer._emit_feedback(_result(metadata={"simulated": True}))

        fb = mock_sink.record.call_args[0][0]
        assert fb.simulated is True

    @pytest.mark.asyncio()
    async def test_completed_at_falls_back_to_now_millis(
        self, mock_config, mock_temporal_client, mock_sink
    ):
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=mock_sink,
        )

        await consumer._emit_feedback(_result(completed_at=None))

        fb = mock_sink.record.call_args[0][0]
        assert isinstance(fb.completed_at, int)
        assert fb.completed_at > 0

    @pytest.mark.asyncio()
    async def test_no_sink_is_noop(self, mock_config, mock_temporal_client):
        # feedback_sink ausente (DI opcional) não deve rebentar
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
        )
        await consumer._emit_feedback(_result())  # não levanta


class TestProcessResultEmitsFeedback:
    @pytest.mark.asyncio()
    async def test_process_result_emits_feedback_and_signals(
        self, mock_config, mock_temporal_client, mock_sink
    ):
        # Integração: _process_result envia o signal E emite feedback.
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=mock_sink,
        )
        consumer.consumer = AsyncMock()  # commit()

        message = MagicMock()
        import json

        message.value = json.dumps(_result()).encode("utf-8")
        message.offset = 1

        await consumer._process_result(message)

        # signal enviado (loop Temporal) E feedback persistido (loop LEARN)
        mock_temporal_client.get_workflow_handle.assert_awaited()
        mock_sink.record.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_feedback_failure_does_not_block_signal_or_commit(
        self, mock_config, mock_temporal_client
    ):
        # O workflow não pode ficar refém da telemetria: se o feedback rebentar,
        # o signal e o commit têm de ocorrer na mesma. (Sink real engole, mas
        # garantimos que o consumer não propaga mesmo num sink defeituoso.)
        broken_sink = MagicMock()
        broken_sink.record = AsyncMock(side_effect=RuntimeError("boom"))
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=broken_sink,
        )
        consumer.consumer = AsyncMock()

        message = MagicMock()
        import json

        message.value = json.dumps(_result()).encode("utf-8")
        message.offset = 1

        await consumer._process_result(message)  # não levanta

        mock_temporal_client.get_workflow_handle.assert_awaited()
        consumer.consumer.commit.assert_awaited()
