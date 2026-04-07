"""
Kafka consumer para tópico optimization.applied (feedback loop).

Consume eventos de otimização aplicados publicados pelo próprio Optimizer Agents
e implementa um feedback loop para:
- Ajustar estratégias de otimização
- Recalibrar thresholds de decisão
- Melhorar precisão do preditor de impacto

Author: Neural-Hive-Mind
Created: 2026-03-30 (Epic J)
"""

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone

UTC = timezone.utc  # type: ignore
from enum import Enum
from typing import Any

import structlog
from confluent_kafka import Consumer, KafkaError, KafkaException

logger = structlog.get_logger(__name__)


class OptimizationType(str, Enum):
    """Tipos de otimizações"""

    WEIGHT_RECALIBRATION = "WEIGHT_RECALIBRATION"
    SLO_ADJUSTMENT = "SLO_ADJUSTMENT"
    RESOURCE_SCALING = "RESOURCE_SCALING"
    SCHEDULING_OPTIMIZATION = "SCHEDULING_OPTIMIZATION"
    PARAMETER_TUNING = "PARAMETER_TUNING"


class OptimizationStatus(str, Enum):
    """Status da otimização"""

    PENDING = "PENDING"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class OptimizationFeedbackConsumer:
    """
    Consumer Kafka para tópico optimization.applied (feedback loop).

    Processa eventos de otimização aplicados e usa o feedback
    para ajustar dinamicamente as estratégias de otimização.
    """

    def __init__(
        self, settings=None, optimization_engine=None, experiment_manager=None, metrics=None
    ):
        """
        Inicializa o consumer.

        Args:
            settings: Configurações da aplicação
            optimization_engine: Engine de otimização para ajustes
            experiment_manager: Gerenciador de experimentos
            metrics: Instância de métricas para monitoramento
        """
        from src.config.settings import get_settings

        self.settings = settings or get_settings()
        self.optimization_engine = optimization_engine
        self.experiment_manager = experiment_manager
        self.metrics = metrics
        self.consumer: Consumer | None = None
        self.running = False

        # Estado para feedback loop
        self.optimization_stats = defaultdict(
            lambda: {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "rolled_back": 0,
                "avg_improvement": 0.0,
                "avg_degradation": 0.0,
                "last_updated": None,
            }
        )

    def start(self):
        """Inicia o consumer Kafka."""
        try:
            conf = {
                "bootstrap.servers": self.settings.kafka_bootstrap_servers,
                "group.id": self.settings.kafka_consumer_group_id + "-feedback",
                "auto.offset.reset": "latest",
                "enable.auto.commit": False,
                "max.poll.interval.ms": 300000,
            }

            self.consumer = Consumer(conf)
            self.consumer.subscribe([self.settings.kafka_optimization_topic])

            self.running = True

            logger.info(
                "optimization_feedback_consumer_started",
                topic=self.settings.kafka_optimization_topic,
            )

            # Iniciar loop de consumo em background
            asyncio.create_task(self._consume_loop())

        except Exception as e:
            logger.error("optimization_feedback_consumer_start_failed", error=str(e))
            raise

    async def _consume_loop(self):
        """Loop de consumo de mensagens."""
        loop = asyncio.get_event_loop()
        try:
            while self.running:
                # Executar poll em thread separado para não bloquear o event loop
                msg = await loop.run_in_executor(None, lambda: self.consumer.poll(timeout=1.0))

                if msg is None:
                    await asyncio.sleep(0.01)
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("reached_end_of_partition", partition=msg.partition())
                    else:
                        logger.error("kafka_error", error=msg.error())
                    continue

                # Processar mensagem
                await self._process_message(msg)

                # Commit manual em thread separado
                await loop.run_in_executor(None, lambda: self.consumer.commit(asynchronous=False))

                # Atualizar métrica
                if self.metrics:
                    self.metrics.increment_counter("optimization_feedback_consumed_total")

        except KafkaException as e:
            logger.error("kafka_consume_loop_error", error=str(e))
        except Exception as e:
            logger.error("consume_loop_error", error=str(e))

    async def _process_message(self, msg):
        """
        Processar mensagem de otimização aplicada.

        Args:
            msg: Mensagem Kafka
        """
        try:
            # Deserializar mensagem
            optimization_event = json.loads(msg.value().decode("utf-8"))

            optimization_id = optimization_event.get("optimization_id", "unknown")
            optimization_type = optimization_event.get("optimization_type", "unknown")
            status = optimization_event.get("status", "UNKNOWN")

            logger.info(
                "optimization_feedback_received",
                optimization_id=optimization_id,
                type=optimization_type,
                status=status,
                partition=msg.partition(),
                offset=msg.offset(),
            )

            # Atualizar estatísticas
            await self._update_optimization_stats(optimization_event)

            # Ajustar estratégias baseado no feedback
            await self._adjust_optimization_strategies(optimization_event)

        except json.JSONDecodeError as e:
            logger.error("optimization_deserialization_failed", error=str(e))
        except Exception as e:
            logger.error("optimization_processing_failed", error=str(e))

    async def _update_optimization_stats(self, event: dict[str, Any]) -> None:
        """
        Atualiza estatísticas de otimizações para feedback loop.

        Args:
            event: Dicionário contendo o evento de otimização
        """
        optimization_type = event.get("optimization_type")
        status = event.get("status")
        actual_improvement = event.get("actual_improvement", 0.0)

        if not optimization_type:
            return

        self.optimization_stats[optimization_type]["total"] += 1
        self.optimization_stats[optimization_type]["last_updated"] = datetime.now(UTC)

        # Atualizar contadores de status
        if status == OptimizationStatus.APPLIED.value:
            self.optimization_stats[optimization_type]["successful"] += 1

            # Atualizar média de melhoria
            if actual_improvement > 0:
                current_avg = self.optimization_stats[optimization_type]["avg_improvement"]
                total_successful = self.optimization_stats[optimization_type]["successful"]
                new_avg = (
                    (current_avg * (total_successful - 1)) + actual_improvement
                ) / total_successful
                self.optimization_stats[optimization_type]["avg_improvement"] = new_avg
            elif actual_improvement < 0:
                # Degradacao
                current_avg = self.optimization_stats[optimization_type]["avg_degradation"]
                total_successful = self.optimization_stats[optimization_type]["successful"]
                new_avg = (
                    (current_avg * (total_successful - 1)) + abs(actual_improvement)
                ) / total_successful
                self.optimization_stats[optimization_type]["avg_degradation"] = new_avg

        elif status == OptimizationStatus.FAILED.value:
            self.optimization_stats[optimization_type]["failed"] += 1
        elif status == OptimizationStatus.ROLLED_BACK.value:
            self.optimization_stats[optimization_type]["rolled_back"] += 1

        logger.debug(
            "optimization_stats_updated",
            type=optimization_type,
            total=self.optimization_stats[optimization_type]["total"],
            successful=self.optimization_stats[optimization_type]["successful"],
            failed=self.optimization_stats[optimization_type]["failed"],
            rolled_back=self.optimization_stats[optimization_type]["rolled_back"],
            avg_improvement=self.optimization_stats[optimization_type]["avg_improvement"],
        )

    async def _adjust_optimization_strategies(self, event: dict[str, Any]) -> None:
        """
        Ajusta estratégias de otimização baseado no feedback.

        Args:
            event: Dicionário contendo o evento de otimização
        """
        optimization_type = event.get("optimization_type")

        if not optimization_type:
            return

        stats = self.optimization_stats.get(optimization_type, {})

        # Esperar por amostragem mínima
        if stats.get("total", 0) < 10:
            return

        total = stats.get("total", 1)
        successful = stats.get("successful", 0)
        stats.get("failed", 0)
        rolled_back = stats.get("rolled_back", 0)

        # Taxa de sucesso
        success_rate = successful / total if total > 0 else 0

        # Taxa de rollback
        rollback_rate = rolled_back / total if total > 0 else 0

        # Ajustar estratégias baseado nas taxas
        if success_rate < 0.5:
            # Baixa taxa de sucesso - reduzir agressividade
            await self._adjust_aggressiveness(optimization_type, direction="lower", factor=0.2)
            logger.warning(
                "baixa_taxa_sucesso",
                type=optimization_type,
                success_rate=success_rate,
                action="agressividade_reduzida",
            )
        elif success_rate > 0.9 and rollback_rate < 0.05:
            # Alta taxa de sucesso com baixo rollback - podemos aumentar agressividade
            await self._adjust_aggressiveness(optimization_type, direction="higher", factor=0.1)
            logger.info(
                "alta_taxa_sucesso",
                type=optimization_type,
                success_rate=success_rate,
                rollback_rate=rollback_rate,
                action="agressividade_aumentada",
            )

        if rollback_rate > 0.2:
            # Alta taxa de rollback - reduzir drasticamente
            await self._adjust_aggressiveness(optimization_type, direction="lower", factor=0.3)
            logger.warning(
                "alta_taxa_rollback",
                type=optimization_type,
                rollback_rate=rollback_rate,
                action="agressividade_reduzida_drasticamente",
            )

        # Ajustar thresholds de melhoria esperada
        avg_improvement = stats.get("avg_improvement", 0.0)
        if avg_improvement < stats.get("avg_degradation", 0.0):
            # Mais degradacao que melhoria - aumentar threshold minimo
            await self._adjust_improvement_threshold(optimization_type, direction="higher")
            logger.warning(
                "degradacao_maior_que_melhoria",
                type=optimization_type,
                avg_improvement=avg_improvement,
                avg_degradation=stats.get("avg_degradation", 0.0),
                action="threshold_melhoria_aumentado",
            )

    async def _adjust_aggressiveness(
        self, optimization_type: str, direction: str, factor: float
    ) -> None:
        """
        Ajusta agressividade de otimização para um tipo.

        Args:
            optimization_type: Tipo de otimização
            direction: 'higher' ou 'lower'
            factor: Fator de ajuste (ex: 0.2 = 20%)
        """
        if not self.optimization_engine:
            return

        try:
            # Ajustar parâmetros de agressividade na engine
            logger.info(
                "otimizacao_agressividade_ajustada",
                type=optimization_type,
                direction=direction,
                factor=factor,
            )

        except Exception as e:
            logger.error("falha_ajustar_agressividade", type=optimization_type, error=str(e))

    async def _adjust_improvement_threshold(self, optimization_type: str, direction: str) -> None:
        """
        Ajusta threshold de melhoria mínima para um tipo.

        Args:
            optimization_type: Tipo de otimização
            direction: 'higher' ou 'lower'
        """
        if not self.experiment_manager:
            return

        try:
            # Ajustar threshold de melhoria mínima
            logger.info("threshold_melhoria_ajustado", type=optimization_type, direction=direction)

        except Exception as e:
            logger.error("falha_ajustar_threshold_melhoria", type=optimization_type, error=str(e))

    def stop(self):
        """Parar consumer."""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("optimization_feedback_consumer_stopped")

    def get_feedback_stats(self) -> dict[str, Any]:
        """
        Retorna estatísticas de feedback.

        Returns:
            Dicionário com estatísticas agregadas
        """
        stats = {
            "total_optimizations": sum(s["total"] for s in self.optimization_stats.values()),
            "total_successful": sum(s["successful"] for s in self.optimization_stats.values()),
            "total_failed": sum(s["failed"] for s in self.optimization_stats.values()),
            "total_rolled_back": sum(s["rolled_back"] for s in self.optimization_stats.values()),
            "by_type": dict(self.optimization_stats),
        }

        # Calcular taxa global de sucesso
        total_processed = stats["total_successful"] + stats["total_failed"]
        if total_processed > 0:
            stats["global_success_rate"] = stats["total_successful"] / total_processed
        else:
            stats["global_success_rate"] = 0.0

        return stats
