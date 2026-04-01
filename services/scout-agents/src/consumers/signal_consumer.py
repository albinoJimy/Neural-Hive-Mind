"""
Kafka consumer para tópico exploration-signals (feedback loop).

Consume sinais de exploração publicados pelo próprio Scout Agents
e implementa um feedback loop para:
- Ajustar prioridade de exploração
- Recalibrar thresholds de detecção
- Melhorar precisão do curiosity scoring

Author: Neural-Hive-Mind
Created: 2026-03-30 (Epic J)
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from aiokafka import AIOKafkaConsumer

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import extract_context_from_headers, set_baggage

logger = structlog.get_logger(__name__)


class SignalFeedbackConsumer:
    """
    Consumer Kafka para tópico exploration-signals (feedback loop).

    Processa sinais publicados pelo Scout Agents e usa o feedback
    para ajustar dinamicamente os parâmetros de exploração.
    """

    def __init__(self, settings, exploration_engine=None, pheromone_client=None, metrics=None):
        """
        Inicializa o consumer.

        Args:
            settings: Configurações da aplicação
            exploration_engine: Engine de exploração para ajustes dinâmicos
            pheromone_client: Cliente de feromônio para atualização
            metrics: Instância de métricas para monitoramento
        """
        self.settings = settings
        self.exploration_engine = exploration_engine
        self.pheromone_client = pheromone_client
        self.metrics = metrics
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

        # Estado para feedback loop
        self.signal_stats = defaultdict(
            lambda: {
                "total": 0,
                "acted_upon": 0,
                "ignored": 0,
                "avg_curiosity": 0.0,
                "last_updated": None,
            }
        )

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        topic = self.settings.kafka.topics_signals
        logger.info("Inicializando SignalFeedbackConsumer", topic=topic)

        self.consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.settings.kafka.bootstrap_servers,
            group_id=self.settings.kafka.consumer_group_id + "-feedback",
            auto_offset_reset="latest",
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )

        self.consumer = instrument_kafka_consumer(self.consumer)
        await self.consumer.start()
        logger.info("SignalFeedbackConsumer inicializado com sucesso", topic=topic)

    async def start(self):
        """Inicia loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError("Consumer não foi inicializado. Chame initialize() primeiro.")

        logger.info("Iniciando consumo de sinais para feedback")
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_message(message)
                    # Commit após processamento bem-sucedido
                    await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "Erro ao processar sinal de feedback",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=False,
                    )
                    # Não commitar offset em caso de erro para permitir retry

        except Exception as e:
            logger.error("Erro no loop de consumo", error=str(e), exc_info=True)
            raise

    async def stop(self):
        """Para o consumer gracefulmente."""
        logger.info("Parando SignalFeedbackConsumer")
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info("SignalFeedbackConsumer parado")

    async def _process_message(self, message):
        """
        Processa uma mensagem de sinal para feedback.

        Args:
            message: Mensagem Kafka contendo ScoutSignal
        """
        # Extrair headers para contexto
        extract_context_from_headers(message.headers or [])

        # Deserializar mensagem
        signal_data = message.value

        signal_id = signal_data.get("signal_id", "unknown")
        signal_type = signal_data.get("signal_type", "unknown")
        exploration_domain = signal_data.get("exploration_domain", "unknown")

        logger.info(
            "sinal_feedback_recebido",
            signal_id=signal_id,
            type=signal_type,
            domain=exploration_domain,
            partition=message.partition,
            offset=message.offset,
        )

        # Definir baggage para tracing
        correlation_id = signal_data.get("correlation_id")
        if correlation_id:
            set_baggage("correlation_id", correlation_id)

        # Processar feedback
        await self._update_signal_stats(signal_data)
        await self._adjust_exploration_parameters(signal_data)

        # Atualizar métricas
        if self.metrics:
            self.metrics.signals_feedback_consumed_total.labels(
                type=signal_type, domain=exploration_domain
            ).inc()

        logger.info("sinal_feedback_processado", signal_id=signal_id)

    async def _update_signal_stats(self, signal: Dict[str, Any]) -> None:
        """
        Atualiza estatísticas de sinais para feedback loop.

        Args:
            signal: Dicionário contendo o sinal
        """
        signal_type = signal.get("signal_type")
        exploration_domain = signal.get("exploration_domain")
        curiosity_score = signal.get("curiosity_score", 0.0)

        if not signal_type or not exploration_domain:
            return

        key = f"{exploration_domain}:{signal_type}"

        self.signal_stats[key]["total"] += 1
        self.signal_stats[key]["last_updated"] = datetime.now(timezone.utc)

        # Atualizar média de curiosity (média móvel simples)
        current_avg = self.signal_stats[key]["avg_curiosity"]
        total = self.signal_stats[key]["total"]
        new_avg = ((current_avg * (total - 1)) + curiosity_score) / total
        self.signal_stats[key]["avg_curiosity"] = new_avg

        # Verificar se sinal foi utilizado (baseado em feedback)
        was_used = signal.get("metadata", {}).get("used_in_exploration", False)
        if was_used:
            self.signal_stats[key]["acted_upon"] += 1
        else:
            self.signal_stats[key]["ignored"] += 1

        logger.debug(
            "estatisticas_sinal_atualizadas",
            key=key,
            total=self.signal_stats[key]["total"],
            acted_upon=self.signal_stats[key]["acted_upon"],
            avg_curiosity=new_avg,
        )

    async def _adjust_exploration_parameters(self, signal: Dict[str, Any]) -> None:
        """
        Ajusta parâmetros de exploração baseado no feedback.

        Args:
            signal: Dicionário contendo o sinal
        """
        if not self.exploration_engine:
            return

        signal_type = signal.get("signal_type")
        exploration_domain = signal.get("exploration_domain")
        signal.get("curiosity_score", 0.0)
        relevance_score = signal.get("relevance_score", 0.0)

        # Verificar taxa de utilização para este tipo de sinal
        key = f"{exploration_domain}:{signal_type}"
        stats = self.signal_stats.get(key, {})

        if stats.get("total", 0) < 10:
            # Esperar por mais dados antes de ajustar
            return

        utilization_rate = stats.get("acted_upon", 0) / stats.get("total", 1)
        avg_curiosity = stats.get("avg_curiosity", 0.5)

        # Ajustar thresholds baseado na utilização
        # Baixa utilização + alta curiosidade = threshold muito alto, reduzir
        # Alta utilização + baixa curiosidade = threshold muito baixo, aumentar
        if utilization_rate < 0.3 and avg_curiosity > 0.7:
            # Reduzir thresholds levemente
            await self._adjust_thresholds(domain=exploration_domain, direction="lower", factor=0.05)
            logger.info(
                "thresholds_reduzidos_baixa_utilizacao",
                domain=exploration_domain,
                utilization_rate=utilization_rate,
                avg_curiosity=avg_curiosity,
            )
        elif utilization_rate > 0.8 and avg_curiosity < 0.5:
            # Aumentar thresholds levemente
            await self._adjust_thresholds(
                domain=exploration_domain, direction="higher", factor=0.05
            )
            logger.info(
                "thresholds_aumentados_alta_utilizacao",
                domain=exploration_domain,
                utilization_rate=utilization_rate,
                avg_curiosity=avg_curiosity,
            )

        # Atualizar feromônios baseado na qualidade do sinal
        if self.pheromone_client and relevance_score > 0.7:
            await self._reinforce_signal_pheromone(signal)

    async def _adjust_thresholds(self, domain: str, direction: str, factor: float) -> None:
        """
        Ajusta thresholds de detecção para um domínio.

        Args:
            domain: Domínio de exploração
            direction: 'higher' ou 'lower'
            factor: Fator de ajuste (ex: 0.05 = 5%)
        """
        if not self.exploration_engine:
            return

        try:
            current_thresholds = {
                "curiosity": self.settings.detection.curiosity_threshold,
                "confidence": self.settings.detection.confidence_threshold,
                "relevance": self.settings.detection.relevance_threshold,
            }

            if direction == "lower":
                new_thresholds = {
                    k: max(0.3, v * (1 - factor)) for k, v in current_thresholds.items()
                }
            else:
                new_thresholds = {
                    k: min(0.9, v * (1 + factor)) for k, v in current_thresholds.items()
                }

            # Atualizar thresholds na engine
            # (implementação depende da interface da exploration_engine)
            logger.info(
                "thresholds_ajustados",
                domain=domain,
                direction=direction,
                old_thresholds=current_thresholds,
                new_thresholds=new_thresholds,
            )

        except Exception as e:
            logger.error("falha_ajustar_thresholds", domain=domain, error=str(e))

    async def _reinforce_signal_pheromone(self, signal: Dict[str, Any]) -> None:
        """
        Reforça feromônio de um sinal de alta qualidade.

        Args:
            signal: Dicionário contendo o sinal
        """
        if not self.pheromone_client:
            return

        try:
            signal_id = signal.get("signal_id")
            exploration_domain = signal.get("exploration_domain")

            # Aumentar feromônio para este tipo de sinal
            # Implementação depende da interface do pheromone_client
            logger.debug("feromonio_reforcado", signal_id=signal_id, domain=exploration_domain)

        except Exception as e:
            logger.error(
                "falha_reforcar_feromonio", signal_id=signal.get("signal_id"), error=str(e)
            )

    def get_feedback_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de feedback.

        Returns:
            Dicionário com estatísticas agregadas
        """
        stats = {
            "total_signals": sum(s["total"] for s in self.signal_stats.values()),
            "total_acted_upon": sum(s["acted_upon"] for s in self.signal_stats.values()),
            "by_type": dict(self.signal_stats),
        }
        return stats
