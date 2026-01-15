"""Kafka helpers for E2E testing of Phase 2 Flow C.

Provides message validation and topic management functions.
"""

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic

logger = logging.getLogger(__name__)

# Default Kafka configuration
DEFAULT_KAFKA_BOOTSTRAP = "neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092"


@dataclass
class KafkaMessageValidation:
    """Result of Kafka message validation."""

    topic: str
    messages_found: int
    expected_count: Optional[int]
    valid: bool
    correlation_ids: List[str]
    trace_ids: List[str]
    sample_messages: List[Dict[str, Any]]


class KafkaTestHelper:
    """Helper class for Kafka testing."""

    def __init__(
        self,
        bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP,
        group_id: str = "e2e-test-consumer",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self._consumer: Optional[Consumer] = None
        self._producer: Optional[Producer] = None
        self._admin: Optional[AdminClient] = None

    def get_consumer(self, group_id: Optional[str] = None) -> Consumer:
        """Get or create a Kafka consumer."""
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id or self.group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
        return Consumer(config)

    def get_producer(self) -> Producer:
        """Get or create a Kafka producer."""
        if self._producer is None:
            config = {
                "bootstrap.servers": self.bootstrap_servers,
            }
            self._producer = Producer(config)
        return self._producer

    def get_admin(self) -> AdminClient:
        """Get or create a Kafka admin client."""
        if self._admin is None:
            config = {
                "bootstrap.servers": self.bootstrap_servers,
            }
            self._admin = AdminClient(config)
        return self._admin

    def close(self) -> None:
        """Close all Kafka clients."""
        if self._consumer:
            self._consumer.close()
            self._consumer = None
        if self._producer:
            self._producer.flush()
            self._producer = None
        self._admin = None

    async def validate_topic_messages(
        self,
        topic: str,
        filter_fn: Callable[[Dict[str, Any]], bool],
        timeout_seconds: int = 60,
        expected_count: Optional[int] = None,
        max_messages: int = 100,
    ) -> KafkaMessageValidation:
        """
        Validate messages in a Kafka topic.

        Args:
            topic: Topic name to consume from
            filter_fn: Function to filter messages
            timeout_seconds: Timeout for consumption
            expected_count: Expected number of matching messages
            max_messages: Maximum messages to process

        Returns:
            KafkaMessageValidation result
        """
        consumer = self.get_consumer(group_id=f"e2e-test-{topic}-{time.time()}")
        consumer.subscribe([topic])

        messages: List[Dict[str, Any]] = []
        correlation_ids: List[str] = []
        trace_ids: List[str] = []

        start_time = time.time()

        try:
            while time.time() - start_time < timeout_seconds:
                msg = await asyncio.to_thread(consumer.poll, 1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.warning(f"Kafka message error: {msg.error()}")
                    continue

                try:
                    value = msg.value()
                    if isinstance(value, bytes):
                        value = json.loads(value.decode("utf-8"))

                    if filter_fn(value):
                        messages.append(value)

                        # Extract correlation_id and trace_id
                        if "correlation_id" in value:
                            correlation_ids.append(value["correlation_id"])
                        if "trace_id" in value:
                            trace_ids.append(value["trace_id"])

                        # Check if we have enough messages
                        if expected_count and len(messages) >= expected_count:
                            break

                        if len(messages) >= max_messages:
                            break

                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.warning(f"Failed to decode message: {e}")
                    continue

        finally:
            consumer.close()

        valid = True
        if expected_count is not None:
            valid = len(messages) >= expected_count

        return KafkaMessageValidation(
            topic=topic,
            messages_found=len(messages),
            expected_count=expected_count,
            valid=valid,
            correlation_ids=correlation_ids,
            trace_ids=trace_ids,
            sample_messages=messages[:5],  # First 5 messages as sample
        )


async def wait_for_kafka_message(
    consumer, topic: str, filter_fn: Callable[[dict], bool], timeout: int = 30
):
    """Wait for a specific message in a Kafka topic."""
    consumer.subscribe([topic])
    start = time.time()
    while time.time() - start < timeout:
        msg = await asyncio.to_thread(consumer.poll, 1.0)
        if msg is None or msg.error():
            continue
        value = msg.value()
        if isinstance(value, bytes):
            try:
                value = json.loads(value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        if filter_fn(value):
            return value
    return None


async def collect_kafka_messages(
    consumer,
    topic: str,
    filter_fn: Callable[[dict], bool],
    timeout: int = 60,
    expected_count: Optional[int] = None,
) -> List[dict]:
    """Collect messages from a Kafka topic."""
    consumer.subscribe([topic])
    results: List[dict] = []
    start = time.time()
    while time.time() - start < timeout:
        msg = await asyncio.to_thread(consumer.poll, 1.0)
        if msg is None or msg.error():
            continue
        value = msg.value()
        if isinstance(value, bytes):
            try:
                value = json.loads(value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        if filter_fn(value):
            results.append(value)
            if expected_count and len(results) >= expected_count:
                break
    return results


# ============================================
# Helpers para Avro
# ============================================


async def wait_for_avro_message(
    consumer,
    topic: str,
    filter_fn: Callable[[dict], bool],
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Aguarda mensagem Avro específica em tópico.

    AvroConsumer deserializa automaticamente as mensagens.

    Args:
        consumer: AvroConsumer configurado
        topic: Nome do tópico
        filter_fn: Função para filtrar mensagem desejada
        timeout: Timeout em segundos

    Returns:
        Mensagem deserializada ou None se timeout
    """
    consumer.subscribe([topic])
    start = time.time()

    while time.time() - start < timeout:
        msg = await asyncio.to_thread(consumer.poll, 1.0)

        if msg is None:
            continue

        if msg.error():
            logger.warning(f"Erro ao consumir mensagem Avro: {msg.error()}")
            continue

        # AvroConsumer já deserializa automaticamente
        value = msg.value()
        if isinstance(value, dict) and filter_fn(value):
            return value

    return None


async def collect_avro_messages(
    consumer,
    topic: str,
    filter_fn: Callable[[dict], bool],
    timeout: int = 60,
    expected_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Coleta múltiplas mensagens Avro de tópico.

    Args:
        consumer: AvroConsumer configurado
        topic: Nome do tópico
        filter_fn: Função para filtrar mensagens
        timeout: Timeout em segundos
        expected_count: Número esperado de mensagens (para encerrar antes do timeout)

    Returns:
        Lista de mensagens deserializadas
    """
    consumer.subscribe([topic])
    results: List[Dict[str, Any]] = []
    start = time.time()

    while time.time() - start < timeout:
        msg = await asyncio.to_thread(consumer.poll, 1.0)

        if msg is None:
            continue

        if msg.error():
            logger.warning(f"Erro ao consumir mensagem Avro: {msg.error()}")
            continue

        value = msg.value()
        if isinstance(value, dict) and filter_fn(value):
            results.append(value)
            if expected_count and len(results) >= expected_count:
                break

    return results


async def get_schema_from_registry(
    schema_registry_url: str,
    subject: str,
    version: str = "latest",
) -> Dict[str, Any]:
    """
    Busca schema do Schema Registry (Apicurio).

    Args:
        schema_registry_url: URL base do Schema Registry
        subject: Nome do subject (ex: plans.ready-value)
        version: Versão do schema (default: latest)

    Returns:
        Dict com informações do schema
    """
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"{schema_registry_url}/apis/ccompat/v6/subjects/{subject}/versions/{version}"
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def get_schema_by_id(
    schema_registry_url: str,
    schema_id: int,
) -> Dict[str, Any]:
    """
    Busca schema por ID do Schema Registry.

    Args:
        schema_registry_url: URL base do Schema Registry
        schema_id: ID do schema

    Returns:
        Dict com definição do schema
    """
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"{schema_registry_url}/apis/ccompat/v6/schemas/ids/{schema_id}"
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def extract_schema_id_from_avro_message(message: bytes) -> int:
    """
    Extrai schema ID de mensagem Avro.

    Formato: magic byte (0x00) + 4 bytes de schema ID (big-endian)

    Args:
        message: Bytes da mensagem Avro

    Returns:
        Schema ID como inteiro
    """
    if len(message) < 5:
        raise ValueError(f"Mensagem muito curta: {len(message)} bytes")

    if message[0] != 0x00:
        raise ValueError(f"Magic byte inválido: {hex(message[0])}")

    return int.from_bytes(message[1:5], byteorder="big")


def create_test_topic(
    admin_client: AdminClient,
    topic_name: str,
    num_partitions: int = 3,
    replication_factor: int = 1,
):
    """Create a test topic."""
    new_topic = NewTopic(
        topic_name, num_partitions=num_partitions, replication_factor=replication_factor
    )
    futures = admin_client.create_topics([new_topic])
    for fut in futures.values():
        try:
            fut.result()
        except KafkaException:
            pass


def delete_test_topic(admin_client: AdminClient, topic_name: str):
    """Delete a test topic."""
    futures = admin_client.delete_topics([topic_name])
    for fut in futures.values():
        with suppress_exception():
            fut.result()


class suppress_exception(contextlib.AbstractContextManager):
    """Context manager to suppress exceptions."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return True


async def validate_kafka_messages(
    plan_id: str,
    topics: Optional[List[str]] = None,
    bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP,
    timeout_seconds: int = 60,
) -> Dict[str, Any]:
    """
    Validate Kafka messages for a plan across multiple topics.

    Args:
        plan_id: The plan ID to filter messages
        topics: List of topics to check (defaults to standard Flow C topics)
        bootstrap_servers: Kafka bootstrap servers
        timeout_seconds: Timeout for each topic

    Returns:
        Comprehensive validation result
    """
    if topics is None:
        topics = [
            "execution.tickets",
            "telemetry.orchestration",
            "orchestration.incidents",
        ]

    helper = KafkaTestHelper(bootstrap_servers=bootstrap_servers)

    results = {
        "valid": True,
        "plan_id": plan_id,
        "topics": {},
    }

    for topic in topics:
        try:
            validation = await helper.validate_topic_messages(
                topic=topic,
                filter_fn=lambda msg: msg.get("plan_id") == plan_id,
                timeout_seconds=timeout_seconds,
                expected_count=1 if topic != "orchestration.incidents" else 0,
            )

            results["topics"][topic] = {
                "valid": validation.valid,
                "messages_found": validation.messages_found,
                "correlation_ids": validation.correlation_ids[:3],
                "trace_ids": validation.trace_ids[:3],
            }

            # For incidents topic, no messages is actually valid (no errors)
            if topic == "orchestration.incidents":
                results["topics"][topic]["valid"] = validation.messages_found == 0
            else:
                if not validation.valid:
                    results["valid"] = False

        except Exception as e:
            logger.error(f"Failed to validate topic {topic}: {e}")
            results["topics"][topic] = {
                "valid": False,
                "error": str(e),
            }
            if topic != "orchestration.incidents":
                results["valid"] = False

    helper.close()
    return results
