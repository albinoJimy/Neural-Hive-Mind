"""Producer Kafka para pipelines CI/CD gerados."""

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config.settings import settings

logger = structlog.get_logger(__name__)


class PipelineGeneratedProducer:
    """Publica eventos pipelines.generated quando manifests CI/CD são criados."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "pipelines.generated",
    ):
        """Inicializa o produtor.

        Args:
            bootstrap_servers: Endereço do Kafka (padrão: settings)
            topic: Tópico para publicar
        """
        self._bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self._topic = topic
        self._producer: AIOKafkaProducer | None = None
        self._logger = logger

    async def start(self) -> None:
        """Inicia o produtor Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            compression_type="gzip",
            enable_idempotence=True,
        )
        await self._producer.start()
        self._logger.info(
            "pipeline_producer_started",
            topic=self._topic,
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Para o produtor Kafka."""
        if self._producer:
            await self._producer.stop()
            self._logger.info("pipeline_producer_stopped")

    async def publish_pipeline_generated(
        self,
        plan_id: str,
        manifest_filename: str,
        manifest_content: str,
        repo_name: str,
        stack: dict[str, Any],
    ) -> None:
        """Publica evento de pipeline CI/CD gerado.

        Args:
            plan_id: ID do CognitivePlan de origem
            manifest_filename: Nome do arquivo de manifesto
            manifest_content: Conteúdo do manifesto
            repo_name: Nome do repositório
            stack: Stack tecnológica detectada
        """
        if not self._producer:
            self._logger.warning("producer_not_started", action="skip_publish")
            return

        event = {
            "event_type": "pipelines.generated",
            "plan_id": plan_id,
            "manifest_filename": manifest_filename,
            "manifest_content_length": len(manifest_content),
            "repo_name": repo_name,
            "stack_language": stack.get("language", "unknown"),
            "stack_framework": stack.get("framework", "unknown"),
            "has_dockerfile": stack.get("has_dockerfile", False),
            "has_tests": stack.get("has_tests", False),
            "timestamp": structlog.get_logger().bind().info("event_timestamp"),  # type: ignore
        }

        try:
            await self._producer.send_and_wait(self._topic, event)
            self._logger.info(
                "pipeline_generated_published",
                plan_id=plan_id,
                topic=self._topic,
            )
        except KafkaError as e:
            self._logger.error(
                "failed_to_publish_pipeline_generated",
                plan_id=plan_id,
                error=str(e),
            )
            raise
