"""
Kafka consumer para tópico insights.analyzed.

Consome insights analíticos publicados pelo Analyst Agents e:
- Enriquece cognitive plans com insights relevantes
- Armazena insights no MongoDB para histórico
- Atualiza workflows em execução com novos insights

Author: Neural-Hive-Mind
Created: 2026-03-30 (Epic J)
"""
import json
from datetime import datetime, timezone
from neural_hive_domain import UTC
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import extract_context_from_headers, set_baggage

logger = structlog.get_logger(__name__)


class InsightsConsumer:
    """
    Consumer Kafka para tópico insights.analyzed.

    Processa insights analíticos do Analyst Agents e os integra
    com os Cognitive Plans em execução no Orchestrator.
    """

    def __init__(
        self,
        config,
        mongodb_client=None,
        metrics=None,
        sasl_username_override: str | None = None,
        sasl_password_override: str | None = None,
    ):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            mongodb_client: Cliente MongoDB para persistência
            metrics: Instância de métricas para monitoramento
            sasl_username_override: Username SASL (ex: obtido do Vault)
            sasl_password_override: Password SASL (ex: obtido do Vault)
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.metrics = metrics
        self.consumer: AIOKafkaConsumer | None = None
        self.running = False
        self.sasl_username = (
            sasl_username_override
            if sasl_username_override is not None
            else getattr(config, "kafka_sasl_username", None)
        )
        self.sasl_password = (
            sasl_password_override
            if sasl_password_override is not None
            else getattr(config, "kafka_sasl_password", None)
        )
        self.security_protocol = getattr(config, "kafka_security_protocol", "PLAINTEXT")
        self.sasl_mechanism = getattr(config, "kafka_sasl_mechanism", "PLAIN")

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        topic = getattr(self.config, "kafka_insights_topic", "insights.analyzed")
        logger.info("Inicializando InsightsConsumer", topic=topic)

        consumer_config = {
            "bootstrap_servers": self.config.kafka_bootstrap_servers,
            "group_id": self.config.kafka_consumer_group_id + "-insights",
            "auto_offset_reset": "latest",
            "enable_auto_commit": False,
        }

        if self.security_protocol and self.security_protocol != "PLAINTEXT":
            consumer_config.update(
                {
                    "security_protocol": self.security_protocol,
                    "sasl_mechanism": self.sasl_mechanism,
                    "sasl_plain_username": self.sasl_username,
                    "sasl_plain_password": self.sasl_password,
                }
            )
            logger.info("InsightsConsumer configurado com SASL", mechanism=self.sasl_mechanism)

        self.consumer = instrument_kafka_consumer(AIOKafkaConsumer(topic, **consumer_config))

        await self.consumer.start()
        logger.info("InsightsConsumer inicializado com sucesso", topic=topic)

    async def start(self):
        """Inicia loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError("Consumer não foi inicializado. Chame initialize() primeiro.")

        logger.info("Iniciando consumo de insights")
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
                    logger.exception(
                        "Erro ao processar insight",
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
        logger.info("Parando InsightsConsumer")
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info("InsightsConsumer parado")

    async def _process_message(self, message):
        """
        Processa uma mensagem de insight.

        Args:
            message: Mensagem Kafka contendo AnalystInsight
        """
        # Extrair headers para contexto
        extract_context_from_headers(message.headers or [])

        # Deserializar mensagem
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                insight = json.loads(raw_value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.exception("falha_deserializar_insight", error=str(e))
                return
        else:
            insight = raw_value

        insight_id = insight.get("insight_id", "unknown")
        insight_type = insight.get("insight_type", "unknown")
        priority = insight.get("priority", "MEDIUM")

        logger.info(
            "insight_recebido",
            insight_id=insight_id,
            type=insight_type,
            priority=priority,
            partition=message.partition,
            offset=message.offset,
        )

        # Definir baggage para tracing
        correlation_id = insight.get("correlation_id")
        plan_id = insight.get("plan_id")

        if correlation_id:
            set_baggage("correlation_id", correlation_id)
        if plan_id:
            set_baggage("plan_id", plan_id)

        # Filtrar insights de baixa prioridade
        if priority not in ["HIGH", "CRITICAL"]:
            logger.debug(
                "insight_filtrado_baixa_prioridade", insight_id=insight_id, priority=priority
            )
            return

        # Processar insight
        await self._enrich_cognitive_plan(insight)
        await self._store_insight(insight)

        # Atualizar métricas
        if self.metrics:
            self.metrics.insights_consumed_total.labels(type=insight_type, priority=priority).inc()

        logger.info("insight_processado", insight_id=insight_id)

    async def _enrich_cognitive_plan(self, insight: dict[str, Any]) -> None:
        """
        Enriquece Cognitive Plan com insights relevantes.

        Args:
            insight: Dicionário contendo o insight analítico
        """
        plan_id = insight.get("plan_id")

        if not plan_id:
            logger.debug("insight_sem_plan_id", insight_id=insight.get("insight_id"))
            return

        if not self.mongodb_client:
            logger.warning("mongodb_client_nao_disponivel")
            return

        try:
            # Buscar Cognitive Plan
            cognitive_plan = await self.mongodb_client.get_cognitive_plan(plan_id)

            if not cognitive_plan:
                logger.debug("plano_nao_encontrado", plan_id=plan_id)
                return

            # Verificar se plano ainda está ativo
            status = cognitive_plan.get("status", "unknown")
            if status in ["COMPLETED", "FAILED", "CANCELLED"]:
                logger.debug("plano_inativo", plan_id=plan_id, status=status)
                return

            # Enriquecer plano com insights
            insights = cognitive_plan.get("insights", [])

            # Evitar duplicatas
            insight_id = insight.get("insight_id")
            if any(i.get("insight_id") == insight_id for i in insights):
                logger.debug("insight_ja_existe_no_plano", insight_id=insight_id, plan_id=plan_id)
                return

            # Adicionar insight ao plano
            insights.append(
                {
                    "insight_id": insight_id,
                    "insight_type": insight.get("insight_type"),
                    "priority": insight.get("priority"),
                    "description": insight.get("description", ""),
                    "recommendations": insight.get("recommendations", []),
                    "received_at": datetime.now(UTC).isoformat(),
                }
            )

            # Atualizar plano no MongoDB
            await self.mongodb_client.update_cognitive_plan(
                plan_id=plan_id, updates={"insights": insights}
            )

            logger.info(
                "plano_enriquecido_com_insight",
                plan_id=plan_id,
                insight_id=insight_id,
                total_insights=len(insights),
            )

        except Exception as e:
            logger.exception(
                "falha_enriquecer_plano",
                plan_id=plan_id,
                insight_id=insight.get("insight_id"),
                error=str(e),
            )

    async def _store_insight(self, insight: dict[str, Any]) -> None:
        """
        Armazena insight no MongoDB para histórico.

        Args:
            insight: Dicionário contendo o insight analítico
        """
        if not self.mongodb_client:
            return

        try:
            # Adicionar timestamp de recebimento
            insight["received_at"] = datetime.now(UTC).isoformat()
            insight["consumer"] = "orchestrator-dynamic"

            # Armazenar na coleção de insights
            await self.mongodb_client.insert_insight(insight)

            logger.debug("insight_armazenado", insight_id=insight.get("insight_id"))

        except Exception as e:
            logger.exception(
                "falha_armazenar_insight", insight_id=insight.get("insight_id"), error=str(e)
            )
