import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from confluent_kafka import Consumer
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from clients.kafka_producer import KafkaProducerClient  # noqa: E402


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_KAFKA_INTEGRATION_TESTS"),
    reason="Set RUN_KAFKA_INTEGRATION_TESTS=1 to enable Kafka + Schema Registry integration tests",
)


def _default_kafka_config():
    """Criar configuração mínima para o producer em testes."""
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    schema_registry = os.getenv(
        "KAFKA_SCHEMA_REGISTRY_URL",
        "http://localhost:8081",
    )

    return SimpleNamespace(
        kafka_bootstrap_servers=bootstrap,
        kafka_tickets_topic=os.getenv("KAFKA_TICKETS_TOPIC", "execution.tickets"),
        kafka_enable_idempotence=True,
        kafka_schema_registry_url=schema_registry,
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_security_protocol="PLAINTEXT",
        kafka_sasl_mechanism="SCRAM-SHA-512",
        kafka_ssl_ca_location=None,
        kafka_ssl_certificate_location=None,
        kafka_ssl_key_location=None,
        schemas_base_path=str(ROOT.parent / "schemas"),
    )


@pytest.fixture
def sample_ticket():
    return {
        "ticket_id": "test-ticket-1",
        "plan_id": "plan-123",
        "task_id": "task-xyz",
        "task_type": "BUILD",
        "status": "PENDING",
        "dependencies": [],
        "metadata": {"source": "test"},
    }


@pytest.fixture
async def producer():
    config = _default_kafka_config()
    client = KafkaProducerClient(config)
    await client.initialize()
    yield client
    await client.close()


def _build_avro_deserializer(schema_registry_url: str):
    schema_path = ROOT.parent / "schemas" / "execution-ticket" / "execution-ticket.avsc"
    schema_str = schema_path.read_text()
    registry = SchemaRegistryClient({"url": schema_registry_url})
    return AvroDeserializer(registry, schema_str)


@pytest.mark.asyncio
async def test_avro_serialization_with_schema_registry(producer, sample_ticket):
    assert producer.avro_serializer is not None
    serialized = producer._serialize_value(sample_ticket, producer.config.kafka_tickets_topic)
    assert isinstance(serialized, (bytes, bytearray))


@pytest.mark.asyncio
async def test_avro_deserialization_roundtrip(producer, sample_ticket):
    await producer.publish_ticket(sample_ticket)

    consumer_config = {
        "bootstrap.servers": producer.config.kafka_bootstrap_servers,
        "group.id": "orchestrator-dynamic-test",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
    consumer = Consumer(consumer_config)
    consumer.subscribe([producer.config.kafka_tickets_topic])

    avro_deserializer = _build_avro_deserializer(producer.config.kafka_schema_registry_url)

    message = await asyncio.get_event_loop().run_in_executor(
        None, lambda: consumer.poll(timeout=10.0)
    )
    consumer.close()

    assert message is not None
    assert message.value() is not None

    decoded = avro_deserializer(
        message.value(),
        SerializationContext(message.topic(), MessageField.VALUE),
    )
    assert decoded["ticket_id"] == sample_ticket["ticket_id"]
    assert decoded["plan_id"] == sample_ticket["plan_id"]


@pytest.mark.asyncio
async def test_json_fallback_when_schema_registry_unavailable(monkeypatch, sample_ticket):
    config = _default_kafka_config()
    config.kafka_schema_registry_url = "http://localhost:0"

    # Forçar falha na criação do cliente para acionar fallback
    monkeypatch.setattr(
        "clients.kafka_producer.SchemaRegistryClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(Exception("registry down")),
    )

    producer = KafkaProducerClient(config)
    await producer.initialize()

    assert producer.avro_serializer is None
    serialized = producer._serialize_value(sample_ticket, config.kafka_tickets_topic)
    assert json.loads(serialized.decode("utf-8"))["ticket_id"] == sample_ticket["ticket_id"]


@pytest.mark.asyncio
async def test_idempotence_with_same_ticket_id(producer, sample_ticket):
    first = await producer.publish_ticket(sample_ticket)
    second = await producer.publish_ticket(sample_ticket)

    assert first["ticket_id"] == second["ticket_id"] == sample_ticket["ticket_id"]
    assert first["topic"] == second["topic"]
