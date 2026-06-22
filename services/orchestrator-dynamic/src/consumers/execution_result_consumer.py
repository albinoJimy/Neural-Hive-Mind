"""
Consumer Kafka para execution.results - Fecha feedback loop de execução.

Processa resultados publicados pelos Worker Agents e envia signals
para workflows Temporal, permitindo que workflows continuem sem aguardar timeout.

Fluxo:
  Worker Agent → execution.results → Consumer → signal(ticket_completed) → Workflow Temporal
"""

import contextlib
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer

from src.models.execution_feedback import ExecutionFeedback

logger = structlog.get_logger(__name__)


class ExecutionResultConsumer:
    """Consumer Kafka para execution.results"""

    TOPIC = "execution.results"
    WORKFLOW_CACHE_PREFIX = "workflow:by:ticket:"
    WORKFLOW_CACHE_TTL = 86400  # 24h

    def __init__(
        self, config, temporal_client, redis_client, feedback_sink=None, metrics=None
    ):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal para enviar signals
            redis_client: Cliente Redis para cache de workflow_id
            feedback_sink: FeedbackSink do loop OBSERVE→LEARN (plano-Z); opcional
            metrics: Instância de métricas (opcional)
        """
        self.config = config
        self.temporal_client = temporal_client
        self.redis_client = redis_client
        self.feedback_sink = feedback_sink
        self.metrics = metrics
        self.consumer: AIOKafkaConsumer | None = None
        self.running = False

    async def initialize(self):
        """Inicializa consumer Kafka."""
        logger.info(
            "execution_result_consumer_initializing",
            topic=self.TOPIC,
            group_id=getattr(
                self.config,
                "execution_result_consumer_group",
                "orchestrator-execution-results",
            ),
        )

        consumer_config = {
            "bootstrap_servers": self.config.kafka_bootstrap_servers,
            "group_id": getattr(
                self.config,
                "execution_result_consumer_group",
                "orchestrator-execution-results",
            ),
            "auto_offset_reset": "latest",
            "enable_auto_commit": False,
        }

        # Configurar segurança se necessário
        security_protocol = getattr(self.config, "kafka_security_protocol", "PLAINTEXT")
        if security_protocol != "PLAINTEXT":
            consumer_config["security_protocol"] = security_protocol
            consumer_config["sasl_mechanism"] = getattr(
                self.config, "kafka_sasl_mechanism", "PLAIN"
            )
            consumer_config["sasl_plain_username"] = self.config.kafka_sasl_username
            consumer_config["sasl_plain_password"] = self.config.kafka_sasl_password

        self.consumer = AIOKafkaConsumer(self.TOPIC, **consumer_config)
        await self.consumer.start()

        logger.info("execution_result_consumer_initialized")

    async def start(self):
        """Loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError(
                "Consumer não foi inicializado. Chame initialize() primeiro."
            )

        logger.info("execution_result_consumer_starting", topic=self.TOPIC)
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_result(message)
                except Exception as e:
                    logger.exception(
                        "execution_result_processing_error",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=False,
                    )
                    # Commit mesmo assim para não bloquear tópico
                    await self.consumer.commit()

        except Exception as e:
            logger.error(
                "execution_result_consumer_loop_error", error=str(e), exc_info=True
            )
            raise
        finally:
            await self.stop()

    async def _process_result(self, message):
        """
        Processa ExecutionResult e envia signal para Temporal Workflow.

        Fluxo:
        1. Deserializar mensagem (JSON/Avro)
        2. Recuperar workflow_id (da mensagem ou cache Redis)
        3. Enviar signal ticket_completed para workflow
        4. Atualizar métricas e commit offset
        """
        try:
            # Deserializar mensagem
            result_data = self._deserialize(message)

            ticket_id = result_data.get("ticket_id")
            plan_id = result_data.get("plan_id")
            status = result_data.get("status")

            if not ticket_id:
                logger.warning(
                    "execution_result_missing_ticket_id", message_offset=message.offset
                )
                await self.consumer.commit()
                return

            # Recuperar workflow_id (da mensagem ou cache)
            workflow_id = result_data.get("workflow_id")
            if not workflow_id:
                workflow_id = await self._get_workflow_for_ticket(ticket_id, plan_id)

            if not workflow_id:
                logger.warning(
                    "workflow_id_not_found_for_result",
                    ticket_id=ticket_id,
                    plan_id=plan_id,
                    action="result_processed_but_no_signal_sent",
                )
                await self.consumer.commit()
                return

            # Fechar o loop LEARN (plano-Z) ANTES do signal: o feedback é
            # independente e não pode ser perdido se o signal falhar (ex.: workflow
            # inexistente/expirado). Internamente protegido — nunca bloqueia o fluxo.
            await self._emit_feedback(result_data)

            # Enviar signal para Temporal (capacidade EXECUTE)
            await self._send_workflow_signal(
                workflow_id=workflow_id, ticket_id=ticket_id, result=result_data
            )

            # Commit offset após processamento bem-sucedido
            await self.consumer.commit()

            logger.info(
                "execution_result_processed",
                ticket_id=ticket_id,
                workflow_id=workflow_id,
                status=status,
                offset=message.offset,
            )

            # Métricas
            if self.metrics:
                self.metrics.execution_results_processed_total.labels(
                    status=status
                ).inc()

        except Exception as e:
            logger.error(
                "execution_result_process_exception",
                ticket_id=result_data.get("ticket_id")
                if "result_data" in locals()
                else "unknown",
                error=str(e),
                exc_info=True,
            )
            # Commit mesmo assim para não bloquear tópico
            with contextlib.suppress(Exception):
                await self.consumer.commit()
            raise

    async def _get_workflow_for_ticket(
        self, ticket_id: str, plan_id: str
    ) -> str | None:
        """
        Recupera workflow_id do cache Redis.

        Args:
            ticket_id: ID do ticket de execução
            plan_id: ID do plano (para logging)

        Returns:
            workflow_id se encontrado, None caso contrário
        """
        if not self.redis_client:
            logger.warning(
                "redis_client_unavailable_for_workflow_lookup",
                ticket_id=ticket_id,
                plan_id=plan_id,
            )
            return None

        try:
            cache_key = f"{self.WORKFLOW_CACHE_PREFIX}{ticket_id}"
            workflow_id = await self.redis_client.get(cache_key)

            if workflow_id:
                logger.debug(
                    "workflow_id_found_in_cache",
                    ticket_id=ticket_id,
                    workflow_id=workflow_id,
                )
                return workflow_id

            logger.debug(
                "workflow_id_not_in_cache", ticket_id=ticket_id, plan_id=plan_id
            )
            return None

        except Exception as e:
            logger.exception(
                "workflow_cache_lookup_error", ticket_id=ticket_id, error=str(e)
            )
            return None

    async def _send_workflow_signal(
        self, workflow_id: str, ticket_id: str, result: dict[str, Any]
    ):
        """
        Envia signal ticket_completed para workflow Temporal.

        Args:
            workflow_id: ID do workflow Temporal
            ticket_id: ID do ticket completado
            result: Resultado da execução
        """
        try:
            # TemporalClientWrapper.get_workflow_handle é async (protegido por
            # circuit breaker) — é obrigatório await, senão `handle` é uma
            # coroutine e handle.signal(...) falha com AttributeError.
            handle = await self.temporal_client.get_workflow_handle(workflow_id)
            # WorkflowHandle.signal() do Temporal SDK nao aceita kwargs arbitrarios;
            # os argumentos do handler (ticket_completed(self, ticket_id, result))
            # sao passados posicionalmente via args=[...]. Com kwargs dava
            # "WorkflowHandle.signal() got an unexpected keyword argument 'ticket_id'".
            await handle.signal(
                "ticket_completed",  # Nome do signal definido no workflow
                args=[ticket_id, result],
            )
            logger.info(
                "workflow_signal_sent",
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                status=result.get("status"),
            )

            if self.metrics:
                self.metrics.workflow_signals_sent_total.inc()

        except Exception as e:
            logger.error(
                "workflow_signal_failed",
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _emit_feedback(self, result_data: dict[str, Any]) -> None:
        """
        Adapter EXECUTE: traduz o ExecutionResult para o contrato canónico
        ExecutionFeedback e delega ao FeedbackSink (plano-Z do loop LEARN).

        Sem lógica de Mongo aqui — a persistência vive no sink. Desacoplado e
        defensivo: uma falha de telemetria nunca bloqueia o workflow.
        """
        if not self.feedback_sink:
            return

        try:
            ticket_id = result_data.get("ticket_id")
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            # O worker põe metadata DENTRO de "result" (não no topo do payload).
            inner = result_data.get("result")
            metadata = (
                inner.get("metadata") if isinstance(inner, dict) else None
            ) or {}
            simulated = bool(metadata.get("simulated", False))

            actual_duration_ms = result_data.get("actual_duration_ms")

            # completed_at: o payload não traz; usa o timestamp (millis) do worker.
            completed_at = result_data.get("completed_at")
            if completed_at is None:
                worker_ts = result_data.get("timestamp")
                completed_at = (
                    worker_ts
                    if isinstance(worker_ts, int) and worker_ts > 0
                    else now_ms
                )

            # started_at: derivado de completed_at - duração quando possível.
            started_at = result_data.get("started_at")
            if (
                started_at is None
                and isinstance(actual_duration_ms, int)
                and actual_duration_ms > 0
            ):
                started_at = completed_at - actual_duration_ms

            feedback = ExecutionFeedback(
                feedback_id=f"{ticket_id}:{now_ms}",
                feedback_persisted_at=now_ms,
                capability="EXECUTE",
                journey_id=result_data.get("journey_id"),
                ticket_id=ticket_id,
                plan_id=result_data.get("plan_id", ""),
                trace_id=result_data.get("trace_id")
                or result_data.get("correlation_id"),
                status=result_data.get("status", ""),
                actual_duration_ms=actual_duration_ms,
                started_at=started_at,
                completed_at=completed_at,
                simulated=simulated,
            )
            await self.feedback_sink.record(feedback)
        except Exception as e:
            logger.warning(
                "execution_feedback_emit_failed",
                ticket_id=result_data.get("ticket_id"),
                error=str(e),
            )

    def _deserialize(self, message) -> dict[str, Any]:
        """
        Deserializa mensagem Kafka (JSON com fallback).

        Args:
            message: Mensagem Kafka

        Returns:
            Dados deserializados
        """
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                return json.loads(raw_value.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.exception(
                    "execution_result_deserialization_failed",
                    error=str(e),
                    raw_bytes_preview=(
                        raw_value[:100].hex()
                        if len(raw_value) >= 100
                        else raw_value.hex()
                    ),
                )
                raise ValueError(f"Failed to deserialize execution result: {e}") from e
        return raw_value

    async def stop(self):
        """Para o consumer gracefulmente."""
        logger.info("execution_result_consumer_stopping")
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info("execution_result_consumer_stopped")
