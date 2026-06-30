"""Teste: a métrica do consumer recebe o ENUM `journey` real do result.

Spec journey-router Fase 4 (Crítico 2). O `ExecutionResultConsumer._process_result`
já lê `result_data.get("journey")` e chama `record_execution_result_processed(...)`.
Estes testes provam o fim da cadeia: com journey no payload, a métrica recebe o
valor real (J1-J4); sem journey, cai em "unknown" (retrocompat).
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.consumers.execution_result_consumer import ExecutionResultConsumer


def _build_consumer():
    consumer = ExecutionResultConsumer.__new__(ExecutionResultConsumer)

    # Metrics: spy só no método que nos interessa.
    metrics = MagicMock()
    metrics.record_execution_result_processed = MagicMock()
    consumer.metrics = metrics

    # Kafka consumer (commit é awaited).
    kafka_consumer = MagicMock()
    kafka_consumer.commit = AsyncMock()
    consumer.consumer = kafka_consumer

    # Dependências internas usadas no fluxo feliz.
    consumer._deserialize = lambda message: json.loads(message.value.decode("utf-8"))
    consumer._get_workflow_for_ticket = AsyncMock(return_value="wf-1")
    consumer._emit_feedback = AsyncMock()
    consumer._send_workflow_signal = AsyncMock()
    return consumer, metrics


def _message(payload: dict):
    msg = MagicMock()
    msg.topic = "execution.results"
    msg.partition = 0
    msg.offset = 1
    msg.value = json.dumps(payload).encode("utf-8")
    return msg


@pytest.mark.asyncio()
async def test_metric_receives_real_journey():
    consumer, metrics = _build_consumer()
    msg = _message(
        {
            "ticket_id": "T-1",
            "workflow_id": "wf-1",
            "status": "COMPLETED",
            "result": {"success": True},
            "journey": "J3_BUILD",
        }
    )
    await consumer._process_result(msg)
    metrics.record_execution_result_processed.assert_called_once_with(
        status="COMPLETED", journey="J3_BUILD"
    )


@pytest.mark.asyncio()
async def test_metric_falls_back_to_unknown_without_journey():
    consumer, metrics = _build_consumer()
    msg = _message(
        {
            "ticket_id": "T-2",
            "workflow_id": "wf-1",
            "status": "COMPLETED",
            "result": {"success": True},
        }
    )
    await consumer._process_result(msg)
    metrics.record_execution_result_processed.assert_called_once_with(
        status="COMPLETED", journey="unknown"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
