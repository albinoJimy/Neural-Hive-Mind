"""
Fixtures para Avro Producers e Consumers especializados em testes E2E.

Fornece producers/consumers configurados para cada tipo de schema do pipeline.
"""

import uuid
from typing import Dict

import pytest
from confluent_kafka import avro
from confluent_kafka.avro import AvroConsumer, AvroProducer


def _load_schema(path: str):
    """Carrega schema Avro de arquivo."""
    with open(path, "r", encoding="utf-8") as f:
        return avro.loads(f.read())


# ============================================
# CognitivePlan Avro Fixtures
# ============================================


@pytest.fixture(scope="function")
def cognitive_plan_avro_producer(k8s_service_endpoints: Dict[str, str]):
    """
    Producer Avro configurado para CognitivePlan.

    Publica no tópico plans.ready com schema registrado.
    """
    value_schema = _load_schema("schemas/cognitive-plan/cognitive-plan.avsc")

    producer = AvroProducer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
        },
        default_value_schema=value_schema,
    )
    yield producer
    producer.flush()


@pytest.fixture(scope="function")
def cognitive_plan_avro_consumer(k8s_service_endpoints: Dict[str, str]):
    """
    Consumer Avro configurado para CognitivePlan.

    Consome do tópico plans.ready com deserialização automática.
    """
    consumer = AvroConsumer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
            "group.id": f"e2e-avro-plan-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    yield consumer
    consumer.close()


# ============================================
# ConsolidatedDecision Avro Fixtures
# ============================================


@pytest.fixture(scope="function")
def consolidated_decision_avro_producer(k8s_service_endpoints: Dict[str, str]):
    """
    Producer Avro configurado para ConsolidatedDecision.

    Publica no tópico plans.consensus com schema registrado.
    """
    value_schema = _load_schema("schemas/consolidated-decision/consolidated-decision.avsc")

    producer = AvroProducer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
        },
        default_value_schema=value_schema,
    )
    yield producer
    producer.flush()


@pytest.fixture(scope="function")
def consolidated_decision_avro_consumer(k8s_service_endpoints: Dict[str, str]):
    """
    Consumer Avro configurado para ConsolidatedDecision.

    Consome do tópico plans.consensus com deserialização automática.
    """
    consumer = AvroConsumer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
            "group.id": f"e2e-avro-decision-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    yield consumer
    consumer.close()


# ============================================
# ExecutionTicket Avro Fixtures
# ============================================


@pytest.fixture(scope="function")
def execution_ticket_avro_producer(k8s_service_endpoints: Dict[str, str]):
    """
    Producer Avro configurado para ExecutionTicket.

    Publica no tópico execution.tickets com schema registrado.
    """
    value_schema = _load_schema("schemas/execution-ticket/execution-ticket.avsc")

    producer = AvroProducer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
        },
        default_value_schema=value_schema,
    )
    yield producer
    producer.flush()


@pytest.fixture(scope="function")
def execution_ticket_avro_consumer(k8s_service_endpoints: Dict[str, str]):
    """
    Consumer Avro configurado para ExecutionTicket.

    Consome do tópico execution.tickets com deserialização automática.
    """
    consumer = AvroConsumer(
        {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
            "group.id": f"e2e-avro-ticket-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    yield consumer
    consumer.close()
