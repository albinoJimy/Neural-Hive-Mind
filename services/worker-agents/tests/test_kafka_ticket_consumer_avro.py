import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from confluent_kafka import Producer
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from clients.kafka_ticket_consumer import KafkaTicketConsumer  # noqa: E402


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_KAFKA_INTEGRATION_TESTS"),
    reason="Set RUN_KAFKA_INTEGRATION_TESTS=1 to enable Kafka + Schema Registry integration tests",
)


def _schema_serializer():
    schema_path = ROOT.parent / "schemas" / "execution-ticket" / "execution-ticket.avsc"
    registry = SchemaRegistryClient(
        {"url": os.getenv("KAFKA_SCHEMA_REGISTRY_URL", "http://localhost:8081")}
    )
    schema_str = schema_path.read_text()
    serializer = AvroSerializer(registry, schema_str)
    return registry, serializer


@pytest.fixture
def worker_config():
    return SimpleNamespace(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_tickets_topic=os.getenv("KAFKA_TICKETS_TOPIC", "execution.tickets"),
        kafka_consumer_group_id="worker-agents-test",
        kafka_auto_offset_reset="earliest",
        kafka_enable_auto_commit=False,
        kafka_schema_registry_url=os.getenv("KAFKA_SCHEMA_REGISTRY_URL", "http://localhost:8081"),
        supported_task_types=["BUILD", "DEPLOY", "TEST", "VALIDATE", "EXECUTE"],
        kafka_security_protocol="PLAINTEXT",
        kafka_sasl_mechanism="SCRAM-SHA-512",
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_ssl_ca_location=None,
        kafka_ssl_certificate_location=None,
        kafka_ssl_key_location=None,
        schemas_base_path=str(ROOT.parent / "schemas"),
    )


@pytest.fixture
def avro_producer():
    _, serializer = _schema_serializer()
    producer = Producer({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")})

    def _send(topic, ticket):
        serialized = serializer(ticket, SerializationContext(topic, MessageField.VALUE))
        producer.produce(topic=topic, key=ticket["ticket_id"].encode("utf-8"), value=serialized)
        producer.flush()

    return _send


@pytest.fixture
def sample_ticket():
    return {
        "ticket_id": "worker-ticket-1",
        "plan_id": "plan-worker",
        "task_id": "task-worker",
        "task_type": "BUILD",
        "status": "PENDING",
        "dependencies": [],
        "metadata": {"origin": "test"},
    }


@pytest.fixture
def execution_engine_mock():
    called = asyncio.Event()

    class _Engine:
        async def process_ticket(self, ticket):
            called.set()

    return SimpleNamespace(engine=_Engine(), called=called)


@pytest.mark.asyncio
async def test_worker_consumes_avro_ticket(worker_config, avro_producer, sample_ticket, execution_engine_mock):
    consumer = KafkaTicketConsumer(worker_config, execution_engine_mock.engine)
    await consumer.initialize()
    consumer_task = asyncio.create_task(consumer.start())

    avro_producer(worker_config.kafka_tickets_topic, sample_ticket)

    await asyncio.wait_for(execution_engine_mock.called.wait(), timeout=15)
    consumer.running = False
    consumer_task.cancel()
    await consumer.stop()


@pytest.mark.asyncio
async def test_worker_validates_required_fields(worker_config, avro_producer, execution_engine_mock):
    consumer = KafkaTicketConsumer(worker_config, execution_engine_mock.engine)
    await consumer.initialize()
    consumer_task = asyncio.create_task(consumer.start())

    bad_ticket = {"ticket_id": "missing-fields"}
    avro_producer(worker_config.kafka_tickets_topic, bad_ticket)

    await asyncio.sleep(2)
    assert not execution_engine_mock.called.is_set()
    consumer.running = False
    consumer_task.cancel()
    await consumer.stop()


@pytest.mark.asyncio
async def test_worker_filters_by_task_type(worker_config, avro_producer, execution_engine_mock, sample_ticket):
    consumer = KafkaTicketConsumer(worker_config, execution_engine_mock.engine)
    await consumer.initialize()
    consumer_task = asyncio.create_task(consumer.start())

    sample_ticket["task_type"] = "UNSUPPORTED"
    avro_producer(worker_config.kafka_tickets_topic, sample_ticket)

    await asyncio.sleep(2)
    assert not execution_engine_mock.called.is_set()
    consumer.running = False
    consumer_task.cancel()
    await consumer.stop()


@pytest.mark.asyncio
async def test_worker_skips_non_pending_tickets(worker_config, avro_producer, execution_engine_mock, sample_ticket):
    consumer = KafkaTicketConsumer(worker_config, execution_engine_mock.engine)
    await consumer.initialize()
    consumer_task = asyncio.create_task(consumer.start())

    sample_ticket["status"] = "DONE"
    avro_producer(worker_config.kafka_tickets_topic, sample_ticket)

    await asyncio.sleep(2)
    assert not execution_engine_mock.called.is_set()
    consumer.running = False
    consumer_task.cancel()
    await consumer.stop()


@pytest.mark.asyncio
async def test_worker_calls_execution_engine(worker_config, avro_producer, execution_engine_mock, sample_ticket):
    consumer = KafkaTicketConsumer(worker_config, execution_engine_mock.engine)
    await consumer.initialize()
    consumer_task = asyncio.create_task(consumer.start())

    avro_producer(worker_config.kafka_tickets_topic, sample_ticket)

    await asyncio.wait_for(execution_engine_mock.called.wait(), timeout=15)
    consumer.running = False
    consumer_task.cancel()
    await consumer.stop()
