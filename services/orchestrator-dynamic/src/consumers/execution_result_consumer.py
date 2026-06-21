"""
Consumer Kafka para execution.results - Fecha feedback loop de execução.

Processa resultados publicados pelos Worker Agents e envia signals
para workflows Temporal, permitindo que workflows continuem sem aguardar timeout.

Fluxo:
  Worker Agent → execution.results → Consumer → signal(ticket_completed) → Workflow Temporal
"""

import contextlib
import json
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer

logger = structlog.get_logger(__name__)

# Estados terminais de um ticket — só estes podem ser propagados ao persistir a
# duração, para não regredir um estado terminal por replay/duplicado.
_TERMINAL_TICKET_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"}


class ExecutionResultConsumer:
    """Consumer Kafka para execution.results"""

    TOPIC = "execution.results"
    WORKFLOW_CACHE_PREFIX = "workflow:by:ticket:"
    WORKFLOW_CACHE_TTL = 86400  # 24h

    def __init__(self, config, temporal_client, redis_client, metrics=None, mongodb_client=None):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal para enviar signals
            redis_client: Cliente Redis para cache de workflow_id
            metrics: Instância de métricas (opcional)
            mongodb_client: Cliente MongoDB para persistir duração real do
                ticket (opcional; fail-open). Quando ausente, a persistência
                de duração é ignorada graciosamente (compatibilidade retro).
        """
        self.config = config
        self.temporal_client = temporal_client
        self.redis_client = redis_client
        self.metrics = metrics
        self.mongodb_client = mongodb_client
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
            raise RuntimeError("Consumer não foi inicializado. Chame initialize() primeiro.")

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
            logger.error("execution_result_consumer_loop_error", error=str(e), exc_info=True)
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
                logger.warning("execution_result_missing_ticket_id", message_offset=message.offset)
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

            # Persistir duração real no MongoDB (fail-open: nunca bloqueia o
            # signal Temporal). Desbloqueia a acumulação de dados reais para
            # treino do DurationPredictor — sem isto, execution_tickets fica
            # com actual_duration_ms=None e o modelo nunca treina.
            await self._persist_duration(result_data)

            # Enviar signal para Temporal
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
                self.metrics.execution_results_processed_total.labels(status=status).inc()

        except Exception as e:
            logger.error(
                "execution_result_process_exception",
                ticket_id=result_data.get("ticket_id") if "result_data" in locals() else "unknown",
                error=str(e),
                exc_info=True,
            )
            # Commit mesmo assim para não bloquear tópico
            with contextlib.suppress(Exception):
                await self.consumer.commit()
            raise

    async def _get_workflow_for_ticket(self, ticket_id: str, plan_id: str) -> str | None:
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

            logger.debug("workflow_id_not_in_cache", ticket_id=ticket_id, plan_id=plan_id)
            return None

        except Exception as e:
            logger.exception("workflow_cache_lookup_error", ticket_id=ticket_id, error=str(e))
            return None

    async def _send_workflow_signal(self, workflow_id: str, ticket_id: str, result: dict[str, Any]):
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

    async def _persist_duration(self, result_data: dict[str, Any]) -> None:
        """
        Persiste actual_duration_ms + completed_at + started_at no MongoDB.

        Fail-open: qualquer falha aqui é logada mas NÃO propaga — o signal
        Temporal e o commit do offset têm de continuar a funcionar mesmo que
        o write no Mongo falhe.

        Args:
            result_data: Resultado deserializado do worker (ticket_id, status,
                actual_duration_ms, timestamp em epoch ms).
        """
        # Compatibilidade retro: sem cliente Mongo, skip silencioso.
        if self.mongodb_client is None:
            logger.debug("duration_persist_skipped_no_mongodb_client")
            return

        ticket_id = result_data.get("ticket_id")
        status = result_data.get("status")
        duration_ms = result_data.get("actual_duration_ms")

        # Só persiste com duração válida (>0). Nunca escreve None por cima.
        if not ticket_id or not isinstance(duration_ms, int | float) or duration_ms <= 0:
            logger.debug(
                "duration_persist_skipped_no_valid_duration",
                ticket_id=ticket_id,
                actual_duration_ms=duration_ms,
            )
            return

        duration_ms = int(duration_ms)
        # Cast explícito para int (epoch ms) — garante BSON Int64 e não Double,
        # para queries de range (completed_at >= cutoff) baterem com tickets Int64.
        completed_at = result_data.get("timestamp")
        if isinstance(completed_at, int | float):
            completed_at = int(completed_at)
            started_at = completed_at - duration_ms
        else:
            completed_at = None
            started_at = None

        update_fields: dict[str, Any] = {"actual_duration_ms": duration_ms}
        if completed_at is not None:
            update_fields["completed_at"] = completed_at
        if started_at is not None:
            update_fields["started_at"] = started_at

        # Só propaga `status` se for terminal — evita regredir um estado já
        # terminal no Mongo por um resultado duplicado/tardio (replay Kafka).
        # A persistência da DURAÇÃO é o objetivo; o status é incidental.
        terminal_status = status if status in _TERMINAL_TICKET_STATUSES else "COMPLETED"

        try:
            await self.mongodb_client.update_ticket_status(
                ticket_id, terminal_status, **update_fields
            )
            logger.info(
                "duration_persisted",
                ticket_id=ticket_id,
                actual_duration_ms=duration_ms,
            )
        except Exception as e:
            logger.warning(
                "duration_persist_failed",
                ticket_id=ticket_id,
                error=str(e),
                degraded=True,
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
                        raw_value[:100].hex() if len(raw_value) >= 100 else raw_value.hex()
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
