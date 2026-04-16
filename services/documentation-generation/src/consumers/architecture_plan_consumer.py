"""Kafka consumer para ArchitecturePlan events."""

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from src.config.settings import get_settings
from src.services.code_doc_generator import CodeDocGenerator
from src.services.readme_generator import ReadmeGenerator

logger = structlog.get_logger(__name__)


class ArchitecturePlanConsumer:
    """Consome eventos ArchitecturePlan do Kafka."""

    def __init__(
        self,
        readme_generator: ReadmeGenerator | None = None,
        code_doc_generator: CodeDocGenerator | None = None,
        producer: Any | None = None,
    ):
        """Inicializa o consumer.

        Args:
            readme_generator: Gerador de README
            code_doc_generator: Gerador de documentação de código
            producer: Kafka producer para publicar resultados (opcional)
        """
        settings = get_settings()
        self._readme_generator = readme_generator or ReadmeGenerator()
        self._code_doc_generator = code_doc_generator or CodeDocGenerator()
        self._producer = producer
        self._consumer: AIOKafkaConsumer | None = None
        self._bootstrap_servers = settings.kafka_bootstrap_servers
        self._group_id = getattr(
            settings, "kafka_consumer_group", "documentation-generation-consumers"
        )
        self._input_topic = "architecture.plans.generated"
        self._dlq_topic = getattr(settings, "kafka_dlq_topic", "documentation.dlq")
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
            "architecture_plan_consumer_started",
            topic=self._input_topic,
            group_id=self._group_id,
        )

    async def stop(self) -> None:
        """Para o consumer Kafka."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._logger.info("architecture_plan_consumer_stopped")

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

            await self._handle_architecture_plan(data)

        except json.JSONDecodeError as e:
            self._logger.error("invalid_json", error=str(e))

        except Exception as e:
            self._logger.error("message_processing_error", error=str(e))

    async def _handle_architecture_plan(self, data: dict[str, Any]) -> None:
        """Processa um evento ArchitecturePlan.

        Args:
            data: Dados do evento
        """
        plan_id = data.get("plan_id", "")
        cognitive_plan_id = data.get("cognitive_plan_id", "")

        if not plan_id:
            self._logger.warning("missing_plan_id")
            return

        self._logger.info("processing_architecture_plan", plan_id=plan_id)

        try:
            # Gerar README baseado no plano de arquitetura
            project_name = data.get("project_name", f"Project-{plan_id}")
            features = [c.get("name", "") for c in data.get("components", [])]

            readme_request = {
                "project_name": project_name,
                "project_description": data.get("description", ""),
                "features": features,
                "installation": data.get("installation", "See documentation"),
                "usage": data.get("usage", "See documentation"),
                "tech_stack": data.get("tech_stack", "Microservices"),
            }

            readme_doc = await self._readme_generator.generate_from_dict(readme_request)

            # Gerar documentação de código para cada componente
            for component in data.get("components", []):
                component_name = component.get("name", "")
                if component_name:
                    # Mock geração de documentação para componente
                    self._logger.info("generating_component_docs", component=component_name)

            # Publicar eventos de documentação gerada
            if self._producer:
                await self._producer.publish_documentation_generated(
                    document_id=f"doc-{plan_id}-readme",
                    doc_type="readme",
                    source_type="architecture",
                    source_id=plan_id,
                    title=f"{project_name} README",
                    file_path=f"docs/README_{plan_id}.md",
                )

            self._logger.info(
                "documentation_generated",
                plan_id=plan_id,
                components_count=len(data.get("components", [])),
            )

        except Exception as e:
            self._logger.error("failed_to_process_architecture_plan", plan_id=plan_id, error=str(e))
            raise
