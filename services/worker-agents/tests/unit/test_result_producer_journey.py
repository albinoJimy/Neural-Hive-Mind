"""Teste: o producer inclui `journey` (ENUM) no payload de execution.results.

Spec journey-router Fase 4 (Crítico 2). `publish_result(..., journey=...)` deve
escrever o ENUM `journey` no payload, em paralelo com `journey_id`. Campo opcional
(default None) -> retrocompat.
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clients.kafka_result_producer import KafkaResultProducer


def _make_producer():
    config = SimpleNamespace(
        kafka_results_topic="execution.results",
        agent_id="worker-test",
    )
    producer = KafkaResultProducer.__new__(KafkaResultProducer)
    producer.config = config
    producer.logger = MagicMock()
    producer.metrics = None
    producer.avro_serializer = None  # caminho JSON: payload inspecionável

    captured = {}

    class _FakeMsg:
        def topic(self):
            return "execution.results"

        def partition(self):
            return 0

        def offset(self):
            return 1

    def _produce(topic, key, value, on_delivery):
        captured["value"] = value
        on_delivery(None, _FakeMsg())

    fake_kafka = MagicMock()
    fake_kafka.produce.side_effect = _produce
    fake_kafka.poll = MagicMock()
    fake_kafka.flush = MagicMock()
    producer.producer = fake_kafka
    return producer, captured


def test_payload_includes_journey_enum():
    producer, captured = _make_producer()
    result = {"success": True, "output": {}, "metadata": {}, "logs": []}
    asyncio.run(
        producer.publish_result(
            "ticket-1",
            "COMPLETED",
            result,
            journey_id="JID-1",
            journey="J3_BUILD",
        )
    )
    payload = json.loads(captured["value"].decode("utf-8"))
    assert payload["journey"] == "J3_BUILD"
    assert payload["journey_id"] == "JID-1"


def test_payload_journey_defaults_none():
    """Sem journey -> campo presente como None (compat schema/consumer)."""
    producer, captured = _make_producer()
    result = {"success": True, "output": {}, "metadata": {}, "logs": []}
    asyncio.run(producer.publish_result("ticket-2", "COMPLETED", result))
    payload = json.loads(captured["value"].decode("utf-8"))
    assert payload["journey"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
