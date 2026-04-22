"""Configuração e fixtures para testes de integração Kafka."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic

# Configurações
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
TEST_TOPICS = [
    "cognitive.plans.created",
    "architecture.plans.generated",
    "pipelines.generated",
    "hypotheses.created",
    "hypotheses.validated",
    "experiments.completed",
    "impact.analyzed",
    "inference.requests",
    "inference.results",
]


@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def kafka_bootstrap_servers() -> AsyncGenerator[str, None]:
    """Retorna endereço do Kafka para testes."""
    # Em produção, verificaríamos se Kafka está rodando
    # Para testes locais, assume localhost:9092
    return KAFKA_BOOTSTRAP_SERVERS


@pytest.fixture(scope="function")
async def kafka_admin(kafka_bootstrap_servers: str) -> AsyncGenerator[AIOKafkaAdminClient, None]:
    """Cria admin client para gerenciar tópicos de teste."""
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka_bootstrap_servers)
    await admin.start()

    # Criar tópicos de teste
    topics = [NewTopic(name=topic, num_partitions=1, replication_factor=1) for topic in TEST_TOPICS]
    try:
        await admin.create_topics(topics)
    except Exception:
        # Tópicos podem já existir
        pass

    yield admin

    # Limpar tópicos após testes
    try:
        await admin.delete_topics(TEST_TOPICS)
    except Exception:
        pass
    finally:
        await admin.stop()


@pytest.fixture(scope="function")
async def kafka_producer(kafka_bootstrap_servers: str) -> AsyncGenerator[AIOKafkaProducer, None]:
    """Producer para enviar mensagens de teste."""
    producer = AIOKafkaProducer(
        bootstrap_servers=kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    yield producer
    await producer.stop()


@pytest.fixture(scope="function")
async def kafka_consumer(kafka_bootstrap_servers: str) -> AsyncGenerator[AIOKafkaConsumer, None]:
    """Consumer para ler mensagens de teste."""
    consumer = AIOKafkaConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        group_id=f"test-consumer-{uuid.uuid4()}",
    )
    await consumer.start()
    yield consumer
    await consumer.stop()


@pytest.fixture()
def sample_cognitive_plan() -> dict[str, Any]:
    """Retorna um plano cognitivo de exemplo."""
    return {
        "plan_id": str(uuid.uuid4()),
        "intent": "Criar uma API REST para gerenciar usuários",
        "context": {
            "project": "user-management-api",
            "domain": "backend",
            "priority": "high",
        },
        "nlp_features": {
            "domain_devops": 0.3,
            "domain_backend": 0.8,
            "action_create": 0.9,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@pytest.fixture()
def sample_hypothesis() -> dict[str, Any]:
    """Retorna uma hipótese de exemplo."""
    return {
        "hypothesis_id": str(uuid.uuid4()),
        "statement": "Otimizar queries do MongoDB reduz latência em 30%",
        "context": {
            "experiment_id": str(uuid.uuid4()),
            "domain": "database",
        },
        "source": "optimizer_agent",
        "priority": "high",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@pytest.fixture()
def sample_experiment_completed() -> dict[str, Any]:
    """Retorna um experimento completado de exemplo."""
    return {
        "experiment_id": str(uuid.uuid4()),
        "variant": "A",
        "status": "completed",
        "metrics": {
            "latency_p50": 45,
            "latency_p95": 120,
            "throughput": 1000,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@pytest.fixture()
def sample_inference_request() -> dict[str, Any]:
    """Retorna uma requisição de inferência de exemplo."""
    return {
        "request_id": str(uuid.uuid4()),
        "model_name": "classification_model",
        "model_version": "1.0.0",
        "model_type": "classification",
        "features": {
            "feature_1": 0.7,
            "feature_2": "text_input",
            "categorical_feature": "category_a",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@pytest.fixture(scope="function")
async def consume_from_topic(kafka_consumer: AIOKafkaConsumer, kafka_bootstrap_servers: str):
    """Factory para consumer de um tópico específico."""

    async def _consume(topic: str, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Consome mensagens de um tópico.

        Args:
            topic: Tópico para consumir
            timeout_ms: Timeout em milissegundos

        Returns:
            Lista de mensagens consumidas
        """
        kafka_consumer.subscribe([topic])
        messages = []

        # Aguardar mensagens
        started_at = datetime.now()
        while (datetime.now() - started_at).total_seconds() * 1000 < timeout_ms:
            async for msg in kafka_consumer:
                try:
                    value = json.loads(msg.value.decode("utf-8"))
                    messages.append(value)
                    if len(messages) >= 10:  # Limite para evitar loop infinito
                        break
                except Exception:
                    continue
            if messages:
                break
            await asyncio.sleep(0.1)

        return messages

    return _consume


@pytest.fixture(scope="function")
async def publish_to_topic(kafka_producer: AIOKafkaProducer):
    """Factory para publicar em um tópico específico."""

    async def _publish(topic: str, message: dict[str, Any]) -> None:
        """Publica mensagem em um tópico.

        Args:
            topic: Tópico para publicar
            message: Mensagem para publicar
        """
        await kafka_producer.send_and_wait(topic, message)

    return _publish
