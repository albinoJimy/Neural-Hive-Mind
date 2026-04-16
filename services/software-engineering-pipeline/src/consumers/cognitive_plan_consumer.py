"""Consumidor Kafka para planos cognitivos do Software Engineering Pipeline."""

import asyncio
import json
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.config.settings import settings
from src.generators.github_actions import GitHubActionsGenerator
from src.models.stack import ProjectStack

logger = structlog.get_logger(__name__)


class CognitivePlanConsumer:
    """Consome eventos cognitive.plans.created e gera pipelines CI/CD."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "cognitive.plans.created",
        group_id: str = "software-engineering-pipeline",
    ):
        """Inicializa o consumidor.

        Args:
            bootstrap_servers: Endereço do Kafka
            topic: Tópico para consumir
            group_id: ID do grupo consumidor
        """
        self._bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self._topic = topic
        self._group_id = group_id or settings.kafka_group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._generator = GitHubActionsGenerator()
        self._running = False
        self._logger = logger

    async def start(self) -> None:
        """Inicia o consumidor Kafka."""
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self._consumer.start()
        self._running = True

        self._logger.info(
            "cognitive_plan_consumer_started",
            topic=self._topic,
            group_id=self._group_id,
            bootstrap_servers=self._bootstrap_servers,
        )

        # Iniciar task de processamento
        asyncio.create_task(self._process_messages())

    async def stop(self) -> None:
        """Para o consumidor Kafka."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._logger.info("cognitive_plan_consumer_stopped")

    async def _process_messages(self) -> None:
        """Processa mensagens do Kafka em loop."""
        try:
            async for msg in self._consumer:
                await self._handle_message(msg.value)
        except KafkaError as e:
            self._logger.error("kafka_error", error=str(e))
        except Exception as e:
            self._logger.error("consumer_error", error=str(e))
        finally:
            # Backoff antes de reconectar
            if self._running:
                await asyncio.sleep(1)

    async def _handle_message(self, message: bytes) -> None:
        """Handle uma mensagem do Kafka.

        Args:
            message: Mensagem em bytes (JSON)
        """
        try:
            data = json.loads(message.decode("utf-8"))
        except json.JSONDecodeError as e:
            self._logger.warning("invalid_json", error=str(e))
            return

        # Extrair informações do plano
        plan_id = data.get("plan_id", "unknown")
        intent = data.get("intent", "")
        nlp_features = data.get("nlp_features", {})

        self._logger.info(
            "cognitive_plan_received",
            plan_id=plan_id,
            intent=intent[:100] if intent else "",
        )

        # Verificar se o plano é relevante para DevOps
        domain_devops = nlp_features.get("domain_devops", 0.0)
        domain_infrastructure = nlp_features.get("domain_infrastructure", 0.0)
        action_create = nlp_features.get("action_create", 0.0)
        action_deploy = nlp_features.get("action_deploy", 0.0)

        # Calcular score de relevância
        relevance_score = max(
            domain_devops,
            domain_infrastructure * 0.9,
            action_create * 0.7 if domain_devops > 0.3 else 0.0,
            action_deploy * 0.8,
        )

        if relevance_score < 0.5:
            self._logger.debug(
                "plan_not_relevant_for_pipeline",
                plan_id=plan_id,
                relevance_score=relevance_score,
            )
            return

        self._logger.info(
            "processing_cognitive_plan_for_pipeline",
            plan_id=plan_id,
            relevance_score=relevance_score,
        )

        # Gerar pipeline manifest
        try:
            # Configurar gerador
            config = {
                "repo_name": self._extract_repo_name(intent),
                "stack": self._detect_stack(intent, data),
                "stages": {
                    "pre_flight": True,
                    "build": True,
                    "test": True,
                    "security": domain_devops > 0.7,
                },
                "docker_registry": "ghcr.io",
            }

            generated = await self._generator.generate(config)

            self._logger.info(
                "pipeline_manifest_generated",
                plan_id=plan_id,
                manifest_filename=generated.filename,
                content_length=len(generated.content),
            )

            # TODO: Persistir manifesto no repositório
            # TODO: Publicar evento pipelines.generated

        except Exception as e:
            self._logger.error(
                "pipeline_generation_failed",
                plan_id=plan_id,
                error=str(e),
            )

    def _extract_repo_name(self, intent: str) -> str:
        """Extrai nome do repositório do intent.

        Args:
            intent: Texto do intent

        Returns:
            Nome do repositório
        """
        # Simplificado - usa primeira palavra ou default
        words = intent.split()
        if words:
            # Remove caracteres especiais
            first_word = words[0].strip(".,!?-").lower()
            return first_word if first_word else "app"
        return "app"

    def _detect_stack(self, intent: str, data: dict) -> ProjectStack:
        """Detecta stack tecnológica do intent.

        Args:
            intent: Texto do intent
            data: Dados completos do plano

        Returns:
            ProjectStack detectado
        """
        # Stack padrão - poderia usar LLM para detecção mais precisa
        return ProjectStack(
            language="python",
            framework="fastapi",
            has_dockerfile=True,
            has_tests=True,
        )
