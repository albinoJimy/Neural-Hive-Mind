"""Consumer para eventos de requisitos gerados.

Autor: Neural Hive Mind
Criado: 2026-04-19 (FEAT-G-001)
Atualizado: 2026-04-20 (REFACTOR-G-003)

Consome eventos requirements.generated do Kafka, dispara
a geração de testes e publica eventos tests.generated.
"""

import json
from typing import TYPE_CHECKING, Any, Optional

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from src.config.settings import get_settings
from src.services.test_generator import (
    TestFramework,
    TestGenerationRequest,
    TestGenerator,
    TestType,
)

if TYPE_CHECKING:
    from src.producers.tests_producer import TestsProducer

logger = structlog.get_logger(__name__)


class RequirementsConsumer:
    """Consumidor de eventos de requisitos gerados."""

    def __init__(
        self,
        test_generator: Optional[TestGenerator] = None,
        producer: Optional["TestsProducer"] = None,
        bootstrap_servers: Optional[str] = None,
        group_id: Optional[str] = None,
        input_topic: Optional[str] = None,
    ):
        """Inicializa o consumidor.

        Args:
            test_generator: Instância do TestGenerator
            producer: Instância do TestsProducer para publicar resultados
            bootstrap_servers: Endereço do Kafka cluster
            group_id: ID do grupo de consumidores
            input_topic: Tópico de entrada (requirements.generated)
        """
        settings = get_settings()

        self._bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self._group_id = group_id or settings.kafka_consumer_group
        self._input_topic = input_topic or settings.kafka_input_topic
        self._test_generator = test_generator or TestGenerator()
        self._producer = producer

        self._consumer: Optional[AIOKafkaConsumer] = None
        self._logger = logger
        self._running = False

    async def start(self) -> None:
        """Inicia o consumidor Kafka."""
        self._consumer = AIOKafkaConsumer(
            self._input_topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )

        try:
            await self._consumer.start()
            self._running = True
            self._logger.info(
                "kafka_consumer_started",
                topic=self._input_topic,
                group_id=self._group_id,
                bootstrap_servers=self._bootstrap_servers,
            )
        except KafkaConnectionError as e:
            self._logger.error(
                "kafka_consumer_start_failed",
                error=str(e),
                bootstrap_servers=self._bootstrap_servers,
            )
            raise

    async def stop(self) -> None:
        """Para o consumidor Kafka."""
        if self._consumer:
            await self._consumer.stop()
            self._running = False
            self._logger.info("kafka_consumer_stopped")

    async def consume(self) -> None:
        """Consome mensagens do Kafka em loop."""
        if not self._consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        self._logger.info("starting_consume_loop", topic=self._input_topic)

        try:
            async for msg in self._consumer:
                await self._process_message(msg)
        except Exception as e:
            self._logger.error("consume_loop_error", error=str(e))
            raise

    async def _process_message(self, msg: Any) -> None:
        """Processa uma mensagem individual.

        Args:
            msg: Mensagem Kafka
        """
        try:
            # Decodificar mensagem
            data = json.loads(msg.value.decode("utf-8"))

            self._logger.info(
                "message_received",
                topic=msg.topic,
                partition=msg.partition,
                offset=msg.offset,
                key=msg.key.decode("utf-8") if msg.key else None,
            )

            # Extrair dados do evento
            requirements_set_id = data.get("requirements_set_id")
            plan_id = data.get("plan_id")
            requirements = data.get("requirements", [])

            if not requirements:
                self._logger.warning("empty_requirements", msg_offset=msg.offset)
                return

            # Criar request de geração
            request = TestGenerationRequest(
                source_type="requirements",
                source_data={"requirements": requirements},
                plan_id=plan_id,
                framework=TestFramework.PYTEST,
                language="python",
                test_types=[TestType.UNIT, TestType.INTEGRATION],
            )

            # Gerar testes
            result = await self._test_generator.generate_tests(request)

            self._logger.info(
                "tests_generated_from_requirements",
                requirements_set_id=requirements_set_id,
                total_tests=result.total_tests_generated,
                test_suite_id=result.test_suite.id,
            )

            # Publicar evento tests.generated via producer
            if self._producer:
                try:
                    await self._producer.publish_tests_generated(
                        test_suite_id=result.test_suite.id,
                        requirements_set_id=requirements_set_id,
                        plan_id=plan_id or "",
                        tests_count=result.total_tests_generated,
                        test_types=[tc.test_type.value for tc in result.test_suite.test_cases],
                        test_suite=result.test_suite,
                    )
                    self._logger.info(
                        "tests_generated_event_published",
                        test_suite_id=result.test_suite.id,
                    )
                except Exception as e:
                    self._logger.error(
                        "publish_tests_generated_failed",
                        error=str(e),
                        test_suite_id=result.test_suite.id,
                    )
                    # Não falhar o processamento se publicação falhar
            else:
                self._logger.warning(
                    "producer_not_configured",
                    test_suite_id=result.test_suite.id,
                )

        except json.JSONDecodeError as e:
            self._logger.error("json_decode_error", error=str(e), msg_offset=msg.offset)
        except Exception as e:
            self._logger.error("message_processing_error", error=str(e), msg_offset=msg.offset)

    @property
    def is_connected(self) -> bool:
        """Verifica se o consumidor está conectado."""
        return self._running and self._consumer is not None

    async def health_check(self) -> dict[str, Any]:
        """Retorna status de saúde do consumidor.

        Returns:
            Dicionário com status de conexão
        """
        return {
            "kafka_connected": self.is_connected,
            "topic": self._input_topic,
            "group_id": self._group_id,
            "bootstrap_servers": self._bootstrap_servers,
        }
