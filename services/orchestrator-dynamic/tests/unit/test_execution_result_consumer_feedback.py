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
    # Payload REAL do worker (kafka_result_producer.publish_result):
    # metadata vive DENTRO de "result"; timestamp (millis) no topo; NÃO há
    # started_at/completed_at/trace_id no payload.
    base = {
        "ticket_id": "t1",
        "plan_id": "p1",
        "workflow_id": "wf1",
        "status": "COMPLETED",
        "actual_duration_ms": 1500,
        "timestamp": 1700000000000,  # worker timestamp (millis) → completed_at
        "result": {"metadata": {"simulated": False}},
        "correlation_id": "c1",
    }
    base.update(overrides)
    return base


def _with_simulated(value: bool) -> dict:
    r = _result()
    r["result"]["metadata"]["simulated"] = value
    return r


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
        # completed_at deriva do timestamp do worker (millis)
        assert fb.completed_at == 1700000000000
        # started_at derivado: completed_at - actual_duration_ms
        assert fb.started_at == 1700000000000 - 1500

    @pytest.mark.asyncio()
    async def test_maps_simulated_from_result_metadata(
        self, mock_config, mock_temporal_client, mock_sink
    ):
        # C1: simulated vive em result["metadata"], NÃO no topo do payload.
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=mock_sink,
        )

        await consumer._emit_feedback(_with_simulated(True))

        fb = mock_sink.record.call_args[0][0]
        assert fb.simulated is True

    @pytest.mark.asyncio()
    async def test_top_level_metadata_is_not_the_source(
        self, mock_config, mock_temporal_client, mock_sink
    ):
        # Guarda anti-regressão de C1: metadata no TOPO não deve marcar simulated
        # (o caminho real põe-no em result.metadata). result.metadata vence.
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=mock_sink,
        )
        payload = _result()  # result.metadata.simulated = False
        payload["metadata"] = {"simulated": True}  # ruído no topo

        await consumer._emit_feedback(payload)

        fb = mock_sink.record.call_args[0][0]
        assert fb.simulated is False

    @pytest.mark.asyncio()
    async def test_completed_at_falls_back_to_now_when_no_timestamp(
        self, mock_config, mock_temporal_client, mock_sink
    ):
        consumer = ExecutionResultConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            redis_client=AsyncMock(),
            feedback_sink=mock_sink,
        )

        await consumer._emit_feedback(_result(timestamp=None))

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
