"""
Kafka consumer para tópico strategic.decisions.

Consome decisões estratégicas publicadas pelo Queen Agent e:
- Atualiza workflows de orquestração
- Persiste decisões para histórico
- Notifica componentes afetados

Author: Neural-Hive-Mind
Created: 2026-03-30 (Epic J)
"""

import json
from datetime import datetime, timezone
UTC = timezone.utc

UTC = timezone.utc  # type: ignore
import sys
from enum import Enum

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum as _StrEnum
else:

    class _StrEnum(str, Enum):
        """Polyfill for StrEnum on Python 3.10"""

        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name


from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import extract_context_from_headers, set_baggage

logger = structlog.get_logger(__name__)


class StrategicDecisionType(_StrEnum):
    """Tipos de decisões estratégicas"""

    WORKFLOW_ADJUSTMENT = "WORKFLOW_ADJUSTMENT"
    RESOURCE_REALLOCATION = "RESOURCE_REALLOCATION"
    PRIORITY_CHANGE = "PRIORITY_CHANGE"
    ESCALATION = "ESCALATION"
    CANCELLATION = "CANCELLATION"
    POLICY_UPDATE = "POLICY_UPDATE"


class StrategicDecisionConsumer:
    """
    Consumer Kafka para tópico strategic.decisions.

    Processa decisões estratégicas do Queen Agent e as aplica
    aos workflows em execução no Orchestrator.
    """

    def __init__(
        self,
        config,
        mongodb_client=None,
        temporal_client=None,
        metrics=None,
        sasl_username_override: str | None = None,
        sasl_password_override: str | None = None,
    ):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            mongodb_client: Cliente MongoDB para persistência
            temporal_client: Cliente Temporal para manipular workflows
            metrics: Instância de métricas para monitoramento
            sasl_username_override: Username SASL (ex: obtido do Vault)
            sasl_password_override: Password SASL (ex: obtido do Vault)
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.temporal_client = temporal_client
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
        topic = getattr(self.config, "kafka_strategic_topic", "strategic.decisions")
        logger.info("Inicializando StrategicDecisionConsumer", topic=topic)

        consumer_config = {
            "bootstrap_servers": self.config.kafka_bootstrap_servers,
            "group_id": self.config.kafka_consumer_group_id + "-strategic",
            "auto_offset_reset": "earliest",
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
            logger.info(
                "StrategicDecisionConsumer configurado com SASL", mechanism=self.sasl_mechanism
            )

        self.consumer = instrument_kafka_consumer(AIOKafkaConsumer(topic, **consumer_config))

        await self.consumer.start()
        logger.info("StrategicDecisionConsumer inicializado com sucesso", topic=topic)

    async def start(self):
        """Inicia loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError("Consumer não foi inicializado. Chame initialize() primeiro.")

        logger.info("Iniciando consumo de decisões estratégicas")
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
                        "Erro ao processar decisão estratégica",
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
        logger.info("Parando StrategicDecisionConsumer")
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info("StrategicDecisionConsumer parado")

    async def _process_message(self, message):
        """
        Processa uma mensagem de decisão estratégica.

        Args:
            message: Mensagem Kafka contendo StrategicDecision
        """
        # Extrair headers para contexto
        extract_context_from_headers(message.headers or [])

        # Deserializar mensagem
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                decision = json.loads(raw_value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.exception("falha_deserializar_decisao", error=str(e))
                return
        else:
            decision = raw_value

        decision_id = decision.get("decision_id", "unknown")
        decision_type = decision.get("decision_type", "unknown")

        logger.info(
            "decisao_estrategica_recebida",
            decision_id=decision_id,
            type=decision_type,
            partition=message.partition,
            offset=message.offset,
        )

        # Definir baggage para tracing
        correlation_id = decision.get("correlation_id")
        plan_id = decision.get("plan_id")

        if correlation_id:
            set_baggage("correlation_id", correlation_id)
        if plan_id:
            set_baggage("plan_id", plan_id)

        # Processar decisão
        await self._apply_strategic_decision(decision)
        await self._store_decision(decision)

        # Atualizar métricas
        if self.metrics:
            self.metrics.strategic_decisions_consumed_total.labels(type=decision_type).inc()

        logger.info("decisao_estrategica_processada", decision_id=decision_id)

    async def _apply_strategic_decision(self, decision: dict[str, Any]) -> None:
        """
        Aplica decisão estratégica ao workflow ou plano.

        Args:
            decision: Dicionário contendo a decisão estratégica
        """
        decision_type = decision.get("decision_type")
        plan_id = decision.get("plan_id")

        if not plan_id:
            logger.debug("decisao_sem_plan_id", decision_id=decision.get("decision_id"))
            return

        try:
            # Buscar Cognitive Plan
            if self.mongodb_client:
                cognitive_plan = await self.mongodb_client.get_cognitive_plan(plan_id)

                if not cognitive_plan:
                    logger.debug("plano_nao_encontrado_para_decisao", plan_id=plan_id)
                    return

                status = cognitive_plan.get("status", "unknown")

                # Aplicar ação baseada no tipo de decisão
                if decision_type == StrategicDecisionType.PRIORITY_CHANGE.value:
                    await self._apply_priority_change(plan_id, decision)
                elif decision_type == StrategicDecisionType.ESCALATION.value:
                    await self._apply_escalation(plan_id, decision)
                elif decision_type == StrategicDecisionType.CANCELLATION.value:
                    await self._apply_cancellation(plan_id, decision, status)
                elif decision_type == StrategicDecisionType.WORKFLOW_ADJUSTMENT.value:
                    await self._apply_workflow_adjustment(plan_id, decision)
                elif decision_type == StrategicDecisionType.RESOURCE_REALLOCATION.value:
                    await self._apply_resource_reallocation(plan_id, decision)
                elif decision_type == StrategicDecisionType.POLICY_UPDATE.value:
                    await self._apply_policy_update(plan_id, decision)
                else:
                    logger.warning("tipo_decisao_desconhecido", type=decision_type)

        except Exception as e:
            logger.exception(
                "falha_aplicar_decisao_estrategica",
                plan_id=plan_id,
                decision_type=decision_type,
                error=str(e),
            )

    async def _apply_priority_change(self, plan_id: str, decision: dict[str, Any]) -> None:
        """Aplica mudança de prioridade ao plano."""
        new_priority = decision.get("parameters", {}).get("priority")
        if not new_priority:
            logger.warning("prioridade_nao_fornecida", plan_id=plan_id)
            return

        if self.mongodb_client:
            await self.mongodb_client.update_cognitive_plan(
                plan_id=plan_id, updates={"priority": new_priority}
            )
            logger.info("prioridade_atualizada", plan_id=plan_id, priority=new_priority)

    async def _apply_escalation(self, plan_id: str, decision: dict[str, Any]) -> None:
        """Aplica escalada do plano."""
        escalation_reason = decision.get("parameters", {}).get("reason", "unknown")

        if self.mongodb_client:
            await self.mongodb_client.update_cognitive_plan(
                plan_id=plan_id,
                updates={
                    "escalated": True,
                    "escalation_reason": escalation_reason,
                    "escalated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info("plano_escalado", plan_id=plan_id, reason=escalation_reason)

    async def _apply_cancellation(
        self, plan_id: str, decision: dict[str, Any], current_status: str
    ) -> None:
        """Aplica cancelamento do plano/workflow."""
        if current_status in ["COMPLETED", "FAILED", "CANCELLED"]:
            logger.debug("plano_ja_finalizado_nao_cancelar", plan_id=plan_id, status=current_status)
            return

        # Cancelar workflow Temporal se disponível
        if self.temporal_client:
            try:
                workflow_id = f"orchestration-{plan_id}"
                await self.temporal_client.cancel_workflow(workflow_id)
                logger.info("workflow_cancelado", workflow_id=workflow_id)
            except Exception as e:
                logger.warning("falha_cancelar_workflow_temporal", error=str(e))

        # Atualizar status no MongoDB
        if self.mongodb_client:
            await self.mongodb_client.update_cognitive_plan(
                plan_id=plan_id,
                updates={
                    "status": "CANCELLED",
                    "cancelled_at": datetime.now(timezone.utc).isoformat(),
                    "cancellation_reason": decision.get("parameters", {}).get(
                        "reason", "Strategic decision"
                    ),
                },
            )
            logger.info("plano_cancelado", plan_id=plan_id)

    async def _apply_workflow_adjustment(self, plan_id: str, decision: dict[str, Any]) -> None:
        """Aplica ajustes ao workflow."""
        adjustments = decision.get("parameters", {}).get("adjustments", [])

        if self.mongodb_client:
            # Atualizar plano com ajustes
            existing_adjustments = []
            cognitive_plan = await self.mongodb_client.get_cognitive_plan(plan_id)
            if cognitive_plan:
                existing_adjustments = cognitive_plan.get("workflow_adjustments", [])

            existing_adjustments.extend(adjustments)

            await self.mongodb_client.update_cognitive_plan(
                plan_id=plan_id, updates={"workflow_adjustments": existing_adjustments}
            )
            logger.info("workflow_ajustado", plan_id=plan_id, adjustments_count=len(adjustments))

    async def _apply_resource_reallocation(self, plan_id: str, decision: dict[str, Any]) -> None:
        """Aplica realocação de recursos."""
        resources = decision.get("parameters", {}).get("resources", {})

        if self.mongodb_client:
            await self.mongodb_client.update_cognitive_plan(
                plan_id=plan_id, updates={"resource_allocation": resources}
            )
            logger.info("recursos_realocados", plan_id=plan_id, resources=resources)

    async def _apply_policy_update(self, plan_id: str, decision: dict[str, Any]) -> None:
        """Aplica atualização de políticas."""
        policies = decision.get("parameters", {}).get("policies", {})

        if self.mongodb_client:
            await self.mongodb_client.update_cognitive_plan(
                plan_id=plan_id, updates={"policies": policies}
            )
            logger.info("politicas_atualizadas", plan_id=plan_id, policies=list(policies.keys()))

    async def _store_decision(self, decision: dict[str, Any]) -> None:
        """
        Armazena decisão estratégica no MongoDB para histórico.

        Args:
            decision: Dicionário contendo a decisão estratégica
        """
        if not self.mongodb_client:
            return

        try:
            # Adicionar timestamp de recebimento
            decision["received_at"] = datetime.now(timezone.utc).isoformat()
            decision["consumer"] = "orchestrator-dynamic"

            # Armazenar na coleção de decisões estratégicas
            await self.mongodb_client.insert_strategic_decision(decision)

            logger.debug("decisao_estrategica_armazenada", decision_id=decision.get("decision_id"))

        except Exception as e:
            logger.exception(
                "falha_armazenar_decisao_estrategica",
                decision_id=decision.get("decision_id"),
                error=str(e),
            )
