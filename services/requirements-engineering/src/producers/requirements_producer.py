"""Kafka producer para Requirements events."""

import json
from datetime import UTC, datetime

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class RequirementsProducer:
    """Produz eventos Requirements para o Kafka."""

    def __init__(self):
        """Inicializa o producer."""
        settings = get_settings()
        self._producer: AIOKafkaProducer | None = None
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._output_topic = settings.kafka_output_topic
        self._dlq_topic = settings.kafka_dlq_topic
        self._logger = logger
        self._running = False

    async def start(self) -> None:
        """Inicia o producer Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            compression_type="gzip",
            acks="all",
            enable_idempotence=True,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()
        self._running = True
        self._logger.info(
            "requirements_producer_started",
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o producer Kafka."""
        self._running = False
        if self._producer:
            await self._producer.stop()
            self._logger.info("requirements_producer_stopped")

    async def publish_requirements_generated(
        self,
        requirements_set_id: str,
        cognitive_plan_id: str,
        requirements_count: int,
        functional_count: int,
        non_functional_count: int,
    ) -> None:
        """Publica evento de requisitos gerados.

        Args:
            requirements_set_id: ID do RequirementsSet
            cognitive_plan_id: ID do CognitivePlan de origem
            requirements_count: Total de requisitos gerados
            functional_count: Requisitos funcionais
            non_functional_count: Requisitos não-funcionais
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = {
            "event_type": "requirements.generated",
            "event_id": f"evt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.now(UTC).isoformat(),
            "requirements_set_id": requirements_set_id,
            "cognitive_plan_id": cognitive_plan_id,
            "requirements_count": requirements_count,
            "functional_count": functional_count,
            "non_functional_count": non_functional_count,
        }

        try:
            await self._producer.send_and_wait(
                self._output_topic,
                value=event,
            )
            self._logger.info(
                "requirements_generated_published",
                requirements_set_id=requirements_set_id,
                cognitive_plan_id=cognitive_plan_id,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_requirements", error=str(e))
            raise

    async def publish_user_stories_generated(
        self,
        user_story_set_id: str,
        requirements_set_id: str,
        stories_count: int,
        total_story_points: int,
    ) -> None:
        """Publica evento de user stories geradas.

        Args:
            user_story_set_id: ID do UserStorySet
            requirements_set_id: ID do RequirementsSet
            stories_count: Total de histórias
            total_story_points: Soma de story points
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event = {
            "event_type": "user_stories.generated",
            "event_id": f"evt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.now(UTC).isoformat(),
            "user_story_set_id": user_story_set_id,
            "requirements_set_id": requirements_set_id,
            "stories_count": stories_count,
            "total_story_points": total_story_points,
        }

        try:
            await self._producer.send_and_wait(
                self._output_topic,
                value=event,
            )
            self._logger.info(
                "user_stories_generated_published",
                user_story_set_id=user_story_set_id,
            )

        except KafkaError as e:
            self._logger.error("failed_to_publish_user_stories", error=str(e))
            raise

    async def send_to_dlq(
        self,
        topic: str,
        value: bytes,
        reason: str,
    ) -> None:
        """Envia mensagem para Dead Letter Queue.

        Args:
            topic: Tópico DLQ
            value: Valor bruto da mensagem
            reason: Razão do envio para DLQ
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        dlq_event = {
            "original_topic": self._output_topic,
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
            "original_value": value.decode("utf-8", errors="replace"),
        }

        try:
            await self._producer.send_and_wait(topic, value=dlq_event)
            self._logger.info("sent_to_dlq", reason=reason)

        except KafkaError as e:
            self._logger.error("failed_to_send_to_dlq", error=str(e))
