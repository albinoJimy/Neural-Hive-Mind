import uuid
from typing import Dict

import pytest
from confluent_kafka import avro
from confluent_kafka.admin import AdminClient
from confluent_kafka.avro import AvroConsumer, AvroProducer


@pytest.fixture(scope="session")
def kafka_admin_client(k8s_service_endpoints: Dict[str, str]) -> AdminClient:
    return AdminClient({"bootstrap.servers": k8s_service_endpoints["kafka"]})


@pytest.fixture(scope="function")
def test_kafka_topics() -> Dict[str, str]:
    # Use production topics to observe real pipeline behavior
    return {
        "intentions": "intentions",
        "plans.ready": "plans.ready",
        "plans.consensus": "plans.consensus",
        "execution.tickets": "execution.tickets",
        "telemetry.orchestration": "telemetry.orchestration",
    }


def _load_schema(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return avro.loads(f.read())


@pytest.fixture(scope="function")
def avro_producer(k8s_service_endpoints: Dict[str, str]):
    value_schema = _load_schema("schemas/execution-ticket/execution-ticket.avsc")
    producer = AvroProducer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": k8s_service_endpoints["schema_registry"],
        },
        default_value_schema=value_schema,
    )
    yield producer
    producer.flush()


@pytest.fixture(scope="function")
def avro_consumer(k8s_service_endpoints: Dict[str, str]):
    consumer = AvroConsumer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": k8s_service_endpoints["schema_registry"],
            "group.id": f"e2e-test-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
        }
    )
    yield consumer
    consumer.close()
