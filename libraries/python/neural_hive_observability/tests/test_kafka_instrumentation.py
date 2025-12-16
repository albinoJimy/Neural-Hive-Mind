import sys
import types
import pytest

from opentelemetry import trace
from opentelemetry.baggage import set_baggage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from neural_hive_observability.config import ObservabilityConfig
from neural_hive_observability.kafka_instrumentation import (
    InstrumentedAIOKafkaConsumer,
    InstrumentedKafkaProducer,
    instrument_kafka_consumer,
    instrument_kafka_producer,
)
import neural_hive_observability.tracing as tracing


def _setup_tracer():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)
    tracing._tracer = tracer
    return tracer, exporter


class DummyProducer:
    def __init__(self):
        self.produced = []

    def produce(self, **kwargs):
        self.produced.append(kwargs)

    def flush(self, *args, **kwargs):
        return None

    def poll(self, *args, **kwargs):
        return None


def test_instrumented_kafka_producer_injects_headers():
    tracer, exporter = _setup_tracer()
    config = ObservabilityConfig(
        service_name="gateway",
        neural_hive_component="gateway",
        neural_hive_layer="experiencia",
    )

    producer = InstrumentedKafkaProducer(DummyProducer(), config)

    set_baggage("neural.hive.intent.id", "intent-123")
    with tracer.start_as_current_span("parent-span"):
        producer.produce(topic="demo-topic", value=b"payload")

    produced_call = producer._producer.produced[0]
    header_dict = {k: v for k, v in produced_call["headers"]}

    assert header_dict["x-neural-hive-intent-id"] == "intent-123"

    spans = exporter.get_finished_spans()
    assert spans
    span = spans[-1]
    assert span.attributes["messaging.destination"] == "demo-topic"
    assert span.attributes["neural.hive.intent.id"] == "intent-123"


class DummyKafkaMessage:
    def __init__(self):
        self.topic = "demo-topic"
        self.partition = 1
        self.offset = 10
        self.headers = [
            ("x-neural-hive-intent-id", b"intent-ctx"),
            ("x-neural-hive-plan-id", b"plan-ctx"),
        ]


class DummyAIOKafkaConsumer:
    def __init__(self):
        self.group_id = "demo-group"
        self._consumed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._consumed:
            raise StopAsyncIteration
        self._consumed = True
        return DummyKafkaMessage()

    async def start(self):
        return None

    async def stop(self):
        return None

    async def commit(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_instrumented_aiokafka_consumer_extracts_context():
    tracer, exporter = _setup_tracer()
    config = ObservabilityConfig(
        service_name="worker",
        neural_hive_component="worker",
        neural_hive_layer="orquestracao",
    )

    consumer = InstrumentedAIOKafkaConsumer(DummyAIOKafkaConsumer(), config)

    async for _ in consumer:
        break

    spans = exporter.get_finished_spans()
    assert spans
    span = spans[-1]
    assert span.attributes["messaging.source"] == "demo-topic"
    assert span.attributes["messaging.kafka.offset"] == 10
    assert span.attributes["neural.hive.intent.id"] == "intent-ctx"
    assert span.attributes["neural.hive.plan.id"] == "plan-ctx"


def test_instrument_kafka_wrapper_detection_for_confluent():
    class FakeConfluentProducer:
        pass

    fake_module = types.SimpleNamespace(Producer=FakeConfluentProducer)
    sys.modules["confluent_kafka"] = fake_module

    config = ObservabilityConfig(
        service_name="gateway",
        neural_hive_component="gateway",
        neural_hive_layer="experiencia",
    )

    wrapped = instrument_kafka_producer(FakeConfluentProducer(), config)
    assert isinstance(wrapped, InstrumentedKafkaProducer)

    sys.modules.pop("confluent_kafka")


def test_instrument_kafka_wrapper_detection_for_aiokafka():
    class FakeAIOKafkaConsumer:
        pass

    fake_module = types.SimpleNamespace(AIOKafkaConsumer=FakeAIOKafkaConsumer)
    sys.modules["aiokafka"] = fake_module

    config = ObservabilityConfig(
        service_name="worker",
        neural_hive_component="worker",
        neural_hive_layer="orquestracao",
    )

    wrapped = instrument_kafka_consumer(FakeAIOKafkaConsumer(), config)
    assert isinstance(wrapped, InstrumentedAIOKafkaConsumer)

    sys.modules.pop("aiokafka")
