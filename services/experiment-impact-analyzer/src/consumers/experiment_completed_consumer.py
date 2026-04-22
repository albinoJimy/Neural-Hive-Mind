"""Consumidor Kafka para experimentos completados."""

import asyncio
import json
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.config.settings import get_settings
from src.services.impact_analyzer import ImpactAnalyzer

logger = structlog.get_logger(__name__)


class ExperimentCompletedConsumer:
    """Consume eventos experiments.completed e analisa impacto."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = "experiments.completed",
        group_id: str = "experiment-impact-analyzer",
        impact_analyzer: ImpactAnalyzer | None = None,
        producer=None,
    ):
        """Inicializa o consumidor.

        Args:
            bootstrap_servers: Endereço do Kafka
            topic: Tópico para consumir
            group_id: ID do grupo consumidor
            impact_analyzer: Instância do ImpactAnalyzer
            producer: ImpactAnalyzedProducer opcional para publicar eventos
        """
        settings = get_settings()
        self._bootstrap_servers = bootstrap_servers or getattr(
            settings, "kafka_bootstrap_servers", "localhost:9092"
        )
        self._topic = topic
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._impact_analyzer = impact_analyzer
        self._producer = producer
        self._running = False
        self._logger = logger

    def set_impact_analyzer(self, analyzer: ImpactAnalyzer) -> None:
        """Define o analisador de impacto (injetado no startup).

        Args:
            analyzer: Instância do ImpactAnalyzer
        """
        self._impact_analyzer = analyzer

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
            "experiment_completed_consumer_started",
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
            self._logger.info("experiment_completed_consumer_stopped")

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

        # Extrair informações do experimento
        experiment_id = data.get("experiment_id")
        variant = data.get("variant")
        status = data.get("status")

        self._logger.info(
            "experiment_completed_received",
            experiment_id=experiment_id,
            variant=variant,
            status=status,
        )

        # Verificar se o experimento foi completado com sucesso
        if status != "completed":
            self._logger.debug(
                "experiment_not_completed_successfully",
                experiment_id=experiment_id,
                status=status,
            )
            return

        if not self._impact_analyzer:
            self._logger.warning("impact_analyzer_not_available")
            return

        # Analisar impacto do experimento
        try:
            self._logger.info(
                "analyzing_experiment_impact",
                experiment_id=experiment_id,
            )

            # Analisar curto e longo prazo
            impact = await self._impact_analyzer.analyze_experiment_impact(
                experiment_id=experiment_id,
                timeframes=["short_term", "long_term"],
                include_correlations=True,
                force_refresh=True,
            )

            self._logger.info(
                "experiment_impact_analyzed",
                experiment_id=experiment_id,
                short_term_impacts=(
                    len(impact.short_term.metric_impacts) if impact.short_term else 0
                ),
                long_term_available=impact.long_term is not None,
            )

            # Publicar evento impact.analyzed
            if self._producer:
                await self._producer.publish_impact_analyzed(
                    experiment_id=experiment_id,
                    variant=variant,
                    short_term_impacts=(
                        len(impact.short_term.metric_impacts) if impact.short_term else 0
                    ),
                    long_term_available=impact.long_term is not None,
                    overall_impact_score=(
                        impact.short_term.overall_impact if impact.short_term else 0.0
                    ),
                    key_metrics=[],
                )

            # TODO: Persistir análise no MongoDB
            # await self._impact_analyzer.mongodb.save_impact(impact)

        except ValueError as e:
            self._logger.warning(
                "experiment_not_found_for_analysis",
                experiment_id=experiment_id,
                error=str(e),
            )
        except Exception as e:
            self._logger.error(
                "impact_analysis_failed",
                experiment_id=experiment_id,
                error=str(e),
            )

    async def _publish_impact_analyzed(self, impact: Any) -> None:
        """Publica evento de impacto analisado.

        Args:
            impact: Resultado da análise de impacto
        """
        # TODO: Implementar producer Kafka
        self._logger.info(
            "impact_analyzed_ready_to_publish",
            experiment_id=impact.experiment_id,
        )
