import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from confluent_kafka import Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from clients.kafka_result_producer import KafkaResultProducer  # noqa: E402


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_KAFKA_INTEGRATION_TESTS"),
    reason="Set RUN_KAFKA_INTEGRATION_TESTS=1 to enable Kafka + Schema Registry integration tests",
)


def _avro_deserializer(schema_path: Path, registry_url: str):
    registry = SchemaRegistryClient({"url": registry_url})
    schema_str = schema_path.read_text()
    return registry, AvroDeserializer(registry, schema_str)


@pytest.fixture
def result_config():
    return SimpleNamespace(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_results_topic=os.getenv("KAFKA_RESULTS_TOPIC", "execution.results"),
        kafka_schema_registry_url=os.getenv("KAFKA_SCHEMA_REGISTRY_URL", "http://localhost:8081"),
        schemas_base_path=str(ROOT.parent / "schemas"),
        kafka_security_protocol="PLAINTEXT",
        kafka_sasl_mechanism="SCRAM-SHA-512",
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_ssl_ca_location=None,
        kafka_ssl_certificate_location=None,
        kafka_ssl_key_location=None,
        agent_id="worker-test",
    )


@pytest.fixture
def avro_consumer(result_config):
    schema_path = ROOT.parent / "schemas" / "execution-result" / "execution-result.avsc"
    registry, deserializer = _avro_deserializer(schema_path, result_config.kafka_schema_registry_url)
    consumer = Consumer(
        {
            "bootstrap.servers": result_config.kafka_bootstrap_servers,
            "group.id": "worker-agents-result-test",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([result_config.kafka_results_topic])

    yield consumer, deserializer
    consumer.close()
    registry.close() if hasattr(registry, "close") else None


@pytest.mark.asyncio
async def test_publish_result_with_avro(result_config, avro_consumer):
    producer = KafkaResultProducer(result_config)
    await producer.initialize()

    payload_result = {
        "success": True,
        "output": {"artifact": "demo"},
        "metadata": {"executor": "test"},
        "logs": ["ok"],
    }
    await producer.publish_result("ticket-avro-1", "COMPLETED", payload_result)

    consumer, deserializer = avro_consumer

    async def _poll():
        loop = asyncio.get_running_loop()

        def _inner():
            return consumer.poll(timeout=10)

        msg = await loop.run_in_executor(None, _inner)
        assert msg is not None
        context = SerializationContext(msg.topic(), MessageField.VALUE)
        return deserializer(msg.value(), context)

    decoded = await _poll()
    assert decoded["ticket_id"] == "ticket-avro-1"
    assert decoded["status"] == "COMPLETED"
    assert decoded["result"]["success"] is True

    await producer.stop()


@pytest.mark.asyncio
async def test_publish_result_fallback_json(result_config):
    producer = KafkaResultProducer(result_config)
    await producer.initialize()
    # Forçar fallback removendo serializer
    producer.avro_serializer = None

    payload_result = {
        "success": True,
        "output": {"artifact": "demo"},
        "metadata": {"executor": "test"},
        "logs": ["ok"],
    }
    await producer.publish_result("ticket-json-1", "COMPLETED", payload_result)

    consumer = Consumer(
        {
            "bootstrap.servers": result_config.kafka_bootstrap_servers,
            "group.id": "worker-agents-result-json-test",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([result_config.kafka_results_topic])

    loop = asyncio.get_running_loop()

    def _poll():
        return consumer.poll(timeout=10)

    msg = await loop.run_in_executor(None, _poll)
    consumer.close()
    assert msg is not None
    decoded = json.loads(msg.value().decode("utf-8"))
    assert decoded["ticket_id"] == "ticket-json-1"
    assert decoded["status"] == "COMPLETED"

    await producer.stop()


def test_normalize_requires_success(result_config):
    producer = KafkaResultProducer(result_config)
    with pytest.raises(ValueError):
        producer._normalize_result({"output": {"artifact": "demo"}})
