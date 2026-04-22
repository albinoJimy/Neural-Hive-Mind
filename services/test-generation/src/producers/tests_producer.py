"""Producer para eventos de testes gerados.

Autor: Neural Hive Mind
Criado: 2026-04-19 (FEAT-G-001)

Publica eventos tests.generated no Kafka após
a geração de testes.
"""

import json
from typing import Any, Optional

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

from src.config.settings import get_settings
from src.models.tests import TestSuite

logger = structlog.get_logger(__name__)


class TestsProducer:
    """Produtor de eventos de testes gerados."""

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        output_topic: Optional[str] = None,
    ):
        """Inicializa o produtor.

        Args:
            bootstrap_servers: Endereço do Kafka cluster
            output_topic: Tópico de saída (tests.generated)
        """
        settings = get_settings()

        self._bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self._output_topic = output_topic or settings.kafka_output_topic

        self._producer: Optional[AIOKafkaProducer] = None
        self._logger = logger
        self._running = False

    async def start(self) -> None:
        """Inicia o produtor Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )

        try:
            await self._producer.start()
            self._running = True
            self._logger.info(
                "kafka_producer_started",
                topic=self._output_topic,
                bootstrap_servers=self._bootstrap_servers,
            )
        except KafkaConnectionError as e:
            self._logger.error(
                "kafka_producer_start_failed",
                error=str(e),
                bootstrap_servers=self._bootstrap_servers,
            )
            raise

    async def stop(self) -> None:
        """Para o produtor Kafka."""
        if self._producer:
            await self._producer.stop()
            self._running = False
            self._logger.info("kafka_producer_stopped")

    async def publish_tests_generated(
        self,
        test_suite_id: str,
        requirements_set_id: str,
        plan_id: str,
        tests_count: int,
        test_types: list[str],
        test_suite: Optional[TestSuite] = None,
    ) -> None:
        """Publica evento tests.generated.

        Args:
            test_suite_id: ID da suíte de testes
            requirements_set_id: ID do conjunto de requisitos
            plan_id: ID do plano
            tests_count: Número de testes gerados
            test_types: Tipos de testes gerados
            test_suite: Suíte de testes completa (opcional)
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        event_data = {
            "event_type": "tests.generated",
            "test_suite_id": test_suite_id,
            "requirements_set_id": requirements_set_id,
            "plan_id": plan_id,
            "tests_count": tests_count,
            "test_types": test_types,
            "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, {}, {}),
        }

        # Adicionar dados da suíte se fornecido
        if test_suite:
            event_data.update(
                {
                    "test_suite_name": test_suite.name,
                    "test_suite_description": test_suite.description,
                    "framework": test_suite.framework.value,
                    "language": test_suite.language,
                }
            )

        try:
            await self._producer.send_and_wait(
                topic=self._output_topic,
                value=event_data,
                key=test_suite_id,
            )

            self._logger.info(
                "tests_generated_event_published",
                test_suite_id=test_suite_id,
                tests_count=tests_count,
                topic=self._output_topic,
            )

        except Exception as e:
            self._logger.error(
                "publish_tests_generated_failed",
                error=str(e),
                test_suite_id=test_suite_id,
            )
            raise

    @property
    def is_connected(self) -> bool:
        """Verifica se o produtor está conectado."""
        return self._running and self._producer is not None

    async def health_check(self) -> dict[str, Any]:
        """Retorna status de saúde do produtor.

        Returns:
            Dicionário com status de conexão
        """
        return {
            "kafka_connected": self.is_connected,
            "topic": self._output_topic,
            "bootstrap_servers": self._bootstrap_servers,
        }
