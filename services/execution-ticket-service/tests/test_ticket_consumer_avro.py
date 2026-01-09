import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from confluent_kafka import Producer
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from consumers.ticket_consumer import TicketConsumer  # noqa: E402
from models import ExecutionTicket  # noqa: E402


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_KAFKA_INTEGRATION_TESTS"),
    reason="Set RUN_KAFKA_INTEGRATION_TESTS=1 to enable Kafka + Schema Registry integration tests",
)


class _Counter:
    def __init__(self):
        self.count = 0

    def inc(self):
        self.count += 1


class _Gauge:
    def __init__(self):
        self.value = None
        self.labels_args = None

    def labels(self, **kwargs):
        self.labels_args = kwargs
        return self

    def set(self, value):
        self.value = value


class _Histogram:
    def __init__(self):
        self.observed_values = []

    def observe(self, value):
        self.observed_values.append(value)


def _build_metrics():
    return SimpleNamespace(
        tickets_consumed_total=_Counter(),
        kafka_messages_consumed_total=_Counter(),
        tickets_processing_errors_total=_Counter(),
        tickets_persisted_total=_Counter(),
        tickets_by_status=_Gauge(),
        jwt_tokens_generated_total=_Counter(),
        ticket_processing_duration_seconds=_Histogram(),
    )


def _settings():
    return SimpleNamespace(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_consumer_group_id="execution-ticket-service-test",
        kafka_tickets_topic=os.getenv("KAFKA_TICKETS_TOPIC", "execution.tickets"),
        kafka_auto_offset_reset="earliest",
        kafka_enable_auto_commit=False,
        kafka_schema_registry_url=os.getenv("KAFKA_SCHEMA_REGISTRY_URL", "http://localhost:8081"),
        kafka_security_protocol="PLAINTEXT",
        kafka_sasl_mechanism="SCRAM-SHA-512",
        kafka_sasl_username=None,
        kafka_sasl_password=None,
        kafka_ssl_ca_location=None,
        kafka_ssl_certificate_location=None,
        kafka_ssl_key_location=None,
        schemas_base_path=str(ROOT.parent / "schemas"),
        enable_audit_trail=False,
        enable_jwt_tokens=False,
        jwt_secret_key="secret",
        jwt_algorithm="HS256",
        jwt_token_expiration_seconds=3600,
        environment="test",
    )


def _schema_components(schema_registry_url: str):
    schema_path = ROOT.parent / "schemas" / "execution-ticket" / "execution-ticket.avsc"
    schema_str = schema_path.read_text()
    registry = SchemaRegistryClient({"url": schema_registry_url})
    serializer = AvroSerializer(registry, schema_str)
    return registry, serializer


@pytest.fixture
def sample_ticket():
    return {
        "ticket_id": "ticket-avro-1",
        "plan_id": "plan-111",
        "task_id": "task-222",
        "task_type": "BUILD",
        "status": "PENDING",
        "dependencies": [],
        "metadata": {"source": "test"},
    }


@pytest.fixture
def avro_producer():
    settings = _settings()
    _, serializer = _schema_components(settings.kafka_schema_registry_url)
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})

    def _send(topic, value, key=None):
        serialized = serializer(value, SerializationContext(topic, MessageField.VALUE))
        producer.produce(topic=topic, key=key.encode("utf-8") if key else None, value=serialized)
        producer.flush()

    return SimpleNamespace(raw=producer, send=_send, serializer=serializer)


@pytest.mark.asyncio
async def test_consumer_deserializes_avro_ticket(monkeypatch, avro_producer, sample_ticket):
    settings = _settings()
    metrics = _build_metrics()
    consumer = TicketConsumer(settings, metrics)
    await consumer.start()

    processed = asyncio.Event()

    async def _process(ticket: ExecutionTicket):
        assert isinstance(ticket, ExecutionTicket)
        processed.set()
        consumer.running = False

    monkeypatch.setattr(consumer, "_process_ticket", _process)

    avro_producer.send(settings.kafka_tickets_topic, sample_ticket, key=sample_ticket["ticket_id"])

    await asyncio.wait_for(asyncio.create_task(consumer.consume()), timeout=15)
    await asyncio.wait_for(processed.wait(), timeout=15)
    await consumer.stop()


@pytest.mark.asyncio
async def test_consumer_persists_to_postgres(monkeypatch, sample_ticket):
    settings = _settings()
    metrics = _build_metrics()
    consumer = TicketConsumer(settings, metrics)

    postgres_called = asyncio.Event()
    mongo_called = asyncio.Event()

    class _FakePostgres:
        async def create_ticket(self, ticket):
            postgres_called.set()

    class _FakeMongo:
        async def save_ticket_audit(self, ticket):
            mongo_called.set()

    async def _fake_postgres_client():
        return _FakePostgres()

    async def _fake_mongo_client():
        return _FakeMongo()

    monkeypatch.setattr("consumers.ticket_consumer.get_postgres_client", _fake_postgres_client)
    monkeypatch.setattr("consumers.ticket_consumer.get_mongodb_client", _fake_mongo_client)
    monkeypatch.setattr("consumers.ticket_consumer.generate_token", lambda *args, **kwargs: SimpleNamespace(expires_at=0))

    ticket_model = ExecutionTicket.from_avro_dict(sample_ticket)
    await consumer._process_ticket(ticket_model)

    assert postgres_called.is_set()
    assert not mongo_called.is_set()  # audit trail desabilitado por padrão


@pytest.mark.asyncio
async def test_consumer_handles_invalid_avro(monkeypatch):
    settings = _settings()
    metrics = _build_metrics()
    consumer = TicketConsumer(settings, metrics)
    await consumer.start()

    # Forçar deserializer a retornar None para simular payload inválido
    consumer.avro_deserializer = lambda *_args, **_kwargs: {"ticket_id": None}
    consumer.running = False
    await consumer.stop()

    assert consumer.consumer is not None


@pytest.mark.asyncio
async def test_consumer_commits_offset_after_success(monkeypatch, sample_ticket):
    settings = _settings()
    metrics = _build_metrics()
    consumer = TicketConsumer(settings, metrics)
    registry, serializer = _schema_components(settings.kafka_schema_registry_url)
    consumer.avro_deserializer = AvroDeserializer(registry, (ROOT.parent / "schemas" / "execution-ticket" / "execution-ticket.avsc").read_text())

    message_value = serializer(
        sample_ticket,
        SerializationContext(settings.kafka_tickets_topic, MessageField.VALUE),
    )

    committed = asyncio.Event()

    class _StubMessage:
        def __init__(self, value):
            self._value = value

        def value(self):
            return self._value

        def topic(self):
            return settings.kafka_tickets_topic

        def error(self):
            return None

        def partition(self):
            return 0

        def offset(self):
            return 0

    class _StubConsumer:
        def __init__(self, msg):
            self._msg = msg
            self._delivered = False

        def poll(self, timeout=None):
            if self._delivered:
                return None
            self._delivered = True
            return self._msg

        def commit(self, *_args, **_kwargs):
            committed.set()

        def close(self):
            return None

        def subscribe(self, *_args, **_kwargs):
            return None

    consumer.consumer = _StubConsumer(_StubMessage(message_value))

    async def _process(ticket: ExecutionTicket):
        consumer.running = False

    monkeypatch.setattr(consumer, "_process_ticket", _process)

    consumer.running = True
    await consumer.consume()

    assert committed.is_set()
