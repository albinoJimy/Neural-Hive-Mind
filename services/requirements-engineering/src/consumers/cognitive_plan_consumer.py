"""Kafka consumer para CognitivePlan events."""

import json
import uuid
from typing import Any, Dict

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.config.settings import get_settings
from src.models.requirements import RequirementsSet
from src.services.requirements_engineer import RequirementsEngineer

logger = structlog.get_logger(__name__)


class CognitivePlanConsumer:
    """Consome eventos CognitivePlan do Kafka."""

    def __init__(
        self,
        requirements_engineer: RequirementsEngineer,
        producer: Any | None = None,
    ):
        """Inicializa o consumer.

        Args:
            requirements_engineer: Serviço de engenharia de requisitos
            producer: Kafka producer para publicar resultados (opcional)
        """
        settings = get_settings()
        self._requirements_engineer = requirements_engineer
        self._producer = producer
        self._consumer: AIOKafkaConsumer | None = None
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._group_id = settings.kafka_consumer_group
        self._input_topic = settings.kafka_input_topic
        self._dlq_topic = settings.kafka_dlq_topic
        self._logger = logger
        self._running = False

    async def start(self) -> None:
        """Inicia o consumer Kafka."""
        self._consumer = AIOKafkaConsumer(
            self._input_topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        await self._consumer.start()
        self._running = True
        self._logger.info(
            "cognitive_plan_consumer_started",
            topic=self._input_topic,
            group_id=self._group_id,
        )

    async def stop(self) -> None:
        """Para o consumer Kafka."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._logger.info("cognitive_plan_consumer_stopped")

    async def consume(self) -> None:
        """Consome mensagens do Kafka em loop."""
        if not self._consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        self._logger.info("starting_consume_loop", topic=self._input_topic)

        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                await self._process_message(msg)
        except KafkaError as e:
            self._logger.error("kafka_consumer_error", error=str(e))
        except Exception as e:
            self._logger.error("consume_loop_error", error=str(e))

    async def _process_message(self, msg: Any) -> None:
        """Processa uma mensagem individual.

        Args:
            msg: Mensagem Kafka
        """
        try:
            data = json.loads(msg.value.decode("utf-8"))
            self._logger.info(
                "message_received",
                topic=msg.topic,
                partition=msg.partition,
                offset=msg.offset,
            )

            await self._handle_cognitive_plan(data)

        except json.JSONDecodeError as e:
            self._logger.error("invalid_json", error=str(e))
            await self._send_to_dlq(msg.value, reason="invalid_json")

        except Exception as e:
            self._logger.error("message_processing_error", error=str(e))
            await self._send_to_dlq(msg.value, reason=str(e))

    async def _handle_cognitive_plan(self, data: Dict[str, Any]) -> None:
        """Processa um evento CognitivePlan.

        Args:
            data: Dados do evento
        """
        plan_id = data.get("plan_id", "")
        intent = data.get("intent", {})
        plan_text = data.get("plan_text", "")

        if not plan_id:
            self._logger.warning("missing_plan_id")
            return

        self._logger.info("processing_cognitive_plan", plan_id=plan_id)

        try:
            # Gerar requisitos a partir do plano cognitivo
            requirements_set = await self._requirements_engineer.generate_from_cognitive_plan(
                plan_id=plan_id,
                plan_text=plan_text or json.dumps(intent, ensure_ascii=False),
                context=data.get("context"),
            )

            # Analisar dependências
            requirements = await self._requirements_engineer.analyze_dependencies(
                requirements_set.requirements
            )
            requirements_set.requirements = requirements

            # Publicar evento de requisitos gerados
            if self._producer:
                await self._producer.publish_requirements_generated(
                    requirements_set_id=requirements_set.id,
                    cognitive_plan_id=plan_id,
                    requirements_count=len(requirements),
                    functional_count=requirements_set.functional_count,
                    non_functional_count=requirements_set.non_functional,
                )

            self._logger.info(
                "requirements_generated",
                plan_id=plan_id,
                requirements_set_id=requirements_set.id,
                total=len(requirements),
            )

        except Exception as e:
            self._logger.error("failed_to_process_cognitive_plan", plan_id=plan_id, error=str(e))
            raise

    async def _send_to_dlq(self, raw_value: bytes, reason: str) -> None:
        """Envia mensagem para DLQ.

        Args:
            raw_value: Valor bruto da mensagem
            reason: Razão do envio para DLQ
        """
        if not self._producer:
            return

        try:
            await self._producer.send_to_dlq(
                topic=self._dlq_topic,
                value=raw_value,
                reason=reason,
            )
        except Exception as e:
            self._logger.error("failed_to_send_to_dlq", error=str(e))
