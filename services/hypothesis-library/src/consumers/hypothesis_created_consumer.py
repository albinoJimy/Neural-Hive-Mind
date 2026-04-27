"""Consumidor Kafka para hipóteses criadas."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.config.settings import get_settings
from src.services.hypothesis_service import HypothesisService

logger = structlog.get_logger(__name__)


class HypothesisCreatedConsumer:
    """Consome eventos hypotheses.created e persiste hipóteses."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "hypotheses.created",
        group_id: str = "hypothesis-library",
        hypothesis_service: HypothesisService | None = None,
        producer=None,
    ):
        """Inicializa o consumidor.

        Args:
            bootstrap_servers: Endereço do Kafka
            topic: Tópico para consumir
            group_id: ID do grupo consumidor
            hypothesis_service: Instância do HypothesisService
            producer: HypothesisValidatedProducer opcional para publicar eventos
        """
        settings = get_settings()
        self._bootstrap_servers = bootstrap_servers or getattr(
            settings, "kafka_bootstrap_servers", "localhost:9092"
        )
        self._topic = topic
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._hypothesis_service = hypothesis_service
        self._producer = producer
        self._running = False
        self._logger = logger

    def set_hypothesis_service(self, service: HypothesisService) -> None:
        """Define o serviço de hipóteses (injetado no startup).

        Args:
            service: Instância do HypothesisService
        """
        self._hypothesis_service = service

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
            "hypothesis_created_consumer_started",
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
            self._logger.info("hypothesis_created_consumer_stopped")

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

        # Extrair informações da hipótese
        hypothesis_id = data.get("hypothesis_id") or str(uuid4())
        statement = data.get("statement", "")
        context = data.get("context", {})
        source = data.get("source", "optimizer_agent")
        experiment_id = context.get("experiment_id")

        self._logger.info(
            "hypothesis_created_received",
            hypothesis_id=hypothesis_id,
            source=source,
            experiment_id=experiment_id,
            statement=statement[:100] if statement else "",
        )

        if not self._hypothesis_service:
            self._logger.warning("hypothesis_service_not_available")
            return

        # Persistir hipótese
        try:
            from src.models.hypothesis import Hypothesis, HypothesisStatus

            # Criar modelo de hipótese
            hypothesis = Hypothesis(
                hypothesis_id=hypothesis_id,
                statement=statement,
                context=context,
                source=source,
                experiment_id=experiment_id,
                status=HypothesisStatus.PENDING,
                priority=self._extract_priority(context),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            # Salvar via serviço
            saved = await self._hypothesis_service.create_hypothesis(hypothesis)

            self._logger.info(
                "hypothesis_saved",
                hypothesis_id=saved.hypothesis_id,
                status=saved.status.value,
            )

            # Publicar evento hypotheses.validated
            if self._producer:
                await self._producer.publish_hypothesis_validated(
                    hypothesis_id=saved.hypothesis_id,
                    statement=saved.statement,
                    status=saved.status.value,
                    priority=saved.priority.value,
                    source=saved.source,
                    experiment_id=saved.experiment_id,
                    validation_score=1.0,  # Padrão, pode ser calculado depois
                )

        except Exception as e:
            self._logger.error(
                "hypothesis_creation_failed",
                hypothesis_id=hypothesis_id,
                error=str(e),
            )

    def _extract_priority(self, context: dict) -> Any:
        """Extrai prioridade da hipótese baseado no contexto.

        Args:
            context: Contexto da hipótese

        Returns:
            Prioridade detectada
        """
        # Verificar se há menção de otimização
        statement = str(context.get("statement", "")).lower()
        if any(word in statement for word in ["improve", "optimize", "reduce", "increase"]):
            from src.models.hypothesis import HypothesisPriority

            return HypothesisPriority.HIGH

        from src.models.hypothesis import HypothesisPriority

        return HypothesisPriority.MEDIUM

    async def _validate_and_publish(self, hypothesis: Any) -> None:
        """Valida hipótese e publica evento hypotheses.validated.

        Args:
            hypothesis: Hipótese a validar
        """
        # TODO: Implementar validação automática
        # - Verificar duplicatas
        # - Analizar similaridade com hipóteses existentes
        # - Calcular prioridade baseada em evidências

        self._logger.info(
            "hypothesis_validated",
            hypothesis_id=hypothesis.hypothesis_id,
        )

        # TODO: Publicar hypotheses.validated
