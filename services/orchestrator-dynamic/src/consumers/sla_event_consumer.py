"""
Consumer Kafka para eventos de SLA - Dispara re-prioritização dinâmica.

Processa eventos do SLA Management System e aciona o SLARePrioritizer
para ajustar prioridade de tickets quando necessário.

Eventos processados:
  - sla.warning: Deadline se aproximando
  - sla.breach: SLA violado
  - sla.risk_band_changed: Mudança de risk_band
  - sla.deadline_approaching: Deadline próximo
"""

import contextlib
import json
from typing import Any

import structlog
from aiokafka import AIOKafkaConsumer

from src.scheduler.sla_reprioritizer import SLARePrioritizer

logger = structlog.get_logger(__name__)


class SLAEventConsumer:
    """Consumer Kafka para eventos de SLA"""

    TOPIC = "sla.events"
    EVENTS_SUBSCRIBED = [
        "sla.warning",
        "sla.breach",
        "sla.risk_band_changed",
        "sla.deadline_approaching",
    ]

    def __init__(self, config, sla_reprioritizer: SLARePrioritizer, queue_manager, metrics=None):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            sla_reprioritizer: SLARePrioritizer para executar re-priorização
            queue_manager: Gerenciador de filas para mover tickets
            metrics: Instância de métricas (opcional)
        """
        self.config = config
        self.sla_reprioritizer = sla_reprioritizer
        self.queue_manager = queue_manager
        self.metrics = metrics
        self.consumer: AIOKafkaConsumer | None = None
        self.running = False

    async def initialize(self):
        """Inicializa consumer Kafka."""
        logger.info(
            "sla_event_consumer_initializing",
            topic=self.TOPIC,
            events_subscribed=self.EVENTS_SUBSCRIBED,
        )

        consumer_config = {
            "bootstrap_servers": self.config.kafka_bootstrap_servers,
            "group_id": getattr(self.config, "sla_event_consumer_group", "orchestrator-sla-events"),
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

        logger.info("sla_event_consumer_initialized")

    async def start(self):
        """Loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError("Consumer não foi inicializado. Chame initialize() primeiro.")

        logger.info("sla_event_consumer_starting", topic=self.TOPIC)
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_event(message)
                except Exception as e:
                    logger.exception(
                        "sla_event_processing_error",
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=False,
                    )
                    # Commit mesmo assim para não bloquear tópico
                    await self.consumer.commit()

        except Exception as e:
            logger.error("sla_event_consumer_loop_error", error=str(e), exc_info=True)
            raise
        finally:
            await self.stop()

    async def _process_event(self, message):
        """
        Processa evento SLA e dispara re-prioritização.

        Fluxo:
        1. Deserializar mensagem
        2. Identificar tipo de evento
        3. Verificar se deve re-priorizar
        4. Executar re-priorização se necessário
        5. Mover ticket entre filas
        6. Commit offset
        """
        try:
            # Deserializar mensagem
            event_data = self._deserialize(message)

            event_type = event_data.get("event_type")
            ticket_id = event_data.get("ticket_id")

            if not event_type or not ticket_id:
                logger.warning(
                    "sla_event_missing_fields",
                    message_offset=message.offset,
                    event_type=event_type,
                    ticket_id=ticket_id,
                )
                await self.consumer.commit()
                return

            # Verificar se evento é relevante
            if event_type not in self.EVENTS_SUBSCRIBED:
                logger.debug("sla_event_not_subscribed", event_type=event_type, ticket_id=ticket_id)
                await self.consumer.commit()
                return

            # Verificar se deve re-priorizar
            if not self.sla_reprioritizer.should_reprioritize_on_sla_event(event_type, event_data):
                logger.debug(
                    "sla_event_no_reprioritization", event_type=event_type, ticket_id=ticket_id
                )
                await self.consumer.commit()
                return

            # Executar re-priorização baseado no tipo de evento
            result = await self._handle_sla_event(event_type, event_data)

            # Mover ticket entre filas se necessário
            if result.get("action") == "reprioritize":
                await self._move_ticket_to_priority_queue(
                    ticket_id, result.get("new_priority"), event_data
                )

            # Commit offset após processamento bem-sucedido
            await self.consumer.commit()

            logger.info(
                "sla_event_processed",
                ticket_id=ticket_id,
                event_type=event_type,
                action=result.get("action"),
                new_priority=result.get("new_priority"),
                offset=message.offset,
            )

            # Métricas
            if self.metrics:
                self.metrics.sla_events_processed_total.labels(
                    event_type=event_type, action=result.get("action", "none")
                ).inc()

        except Exception as e:
            logger.error(
                "sla_event_process_exception",
                ticket_id=event_data.get("ticket_id") if "event_data" in locals() else "unknown",
                error=str(e),
                exc_info=True,
            )
            # Commit mesmo assim para não bloquear tópico
            with contextlib.suppress(Exception):
                await self.consumer.commit()
            raise

    async def _handle_sla_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Encaminha evento para handler apropriado.

        Args:
            event_type: Tipo do evento
            event_data: Dados do evento

        Returns:
            Resultado da re-priorização
        """
        if event_type == "sla.warning":
            return await self.sla_reprioritizer.on_sla_warning(event_data)
        if event_type == "sla.breach":
            return await self.sla_reprioritizer.on_sla_breach(event_data)
        if event_type == "sla.risk_band_changed":
            return await self.sla_reprioritizer.on_risk_band_changed(event_data)
        if event_type == "sla.deadline_approaching":
            return await self.sla_reprioritizer.on_deadline_approaching(event_data)
        logger.warning("sla_event_unhandled_type", event_type=event_type)
        return {"action": "none", "reason": "unhandled_event_type"}

    async def _move_ticket_to_priority_queue(
        self, ticket_id: str, new_priority: str, event_data: dict[str, Any]
    ):
        """
        Move ticket para fila de prioridade apropriada.

        Nota: Esta é uma implementação simplificada. Em produção,
        o ticket deve ser obtido da fila atual e reenfileirado.

        Args:
            ticket_id: ID do ticket
            new_priority: Nova prioridade (CRITICAL/HIGH/NORMAL/LOW)
            event_data: Dados do evento (para contexto)
        """
        # Aqui seria implementada a lógica de mover o ticket
        # entre filas. Por enquanto, apenas logamos.
        logger.info(
            "ticket_priority_update_requested",
            ticket_id=ticket_id,
            new_priority=new_priority,
            note="ticket_movement_to_be_implemented_by_queue_manager",
        )

        # Na implementação completa, seria algo como:
        # 1. Obter ticket da fila atual
        # 2. Remover da fila atual
        # 3. Enfileirar na nova fila de prioridade
        # ticket = await self.queue_manager.remove_ticket_from_any_queue(ticket_id)
        # if ticket:
        #     await self.queue_manager.enqueue_by_risk(ticket, new_priority)

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
                logger.exception("sla_event_deserialization_failed", error=str(e))
                raise ValueError(f"Failed to deserialize SLA event: {e}") from e
        return raw_value

    async def stop(self):
        """Para o consumer gracefulmente."""
        logger.info("sla_event_consumer_stopping")
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info("sla_event_consumer_stopped")
