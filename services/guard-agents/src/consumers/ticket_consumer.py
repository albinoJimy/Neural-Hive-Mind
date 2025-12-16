"""
TicketConsumer - Consumer Kafka para validação proativa de ExecutionTickets.

Responsável por:
- Consumir tickets do tópico execution.tickets
- Validar tickets com SecurityValidator
- Enforçar guardrails com GuardrailEnforcer
- Publicar resultados em tópicos apropriados (validated/rejected/pending_approval)
- Persistir validações no MongoDB
"""

from typing import Optional
import structlog
import json
import asyncio
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from neural_hive_observability import instrument_kafka_consumer
from neural_hive_observability.context import (
    extract_context_from_headers,
    set_baggage
)

from src.models.security_validation import ValidationStatus

logger = structlog.get_logger(__name__)


class TicketConsumer:
    """
    Consumer Kafka para validação proativa de execution tickets.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        security_validator,
        guardrail_enforcer,
        validation_producer,
        tickets_topic: str,
        tickets_validated_topic: str,
        tickets_rejected_topic: str,
        tickets_pending_approval_topic: str
    ):
        """
        Inicializa o TicketConsumer.

        Args:
            bootstrap_servers: Servidores Kafka
            group_id: ID do consumer group
            security_validator: SecurityValidator para validação
            guardrail_enforcer: GuardrailEnforcer para enforcement
            validation_producer: Producer para publicar validações
            tickets_topic: Tópico de entrada de tickets
            tickets_validated_topic: Tópico para tickets validados
            tickets_rejected_topic: Tópico para tickets rejeitados
            tickets_pending_approval_topic: Tópico para tickets pendentes de aprovação
        """
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.security_validator = security_validator
        self.guardrail_enforcer = guardrail_enforcer
        self.validation_producer = validation_producer
        self.tickets_topic = tickets_topic
        self.tickets_validated_topic = tickets_validated_topic
        self.tickets_rejected_topic = tickets_rejected_topic
        self.tickets_pending_approval_topic = tickets_pending_approval_topic
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._consuming = False
        self._consumer_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """
        Inicializa consumer Kafka.

        Raises:
            Exception se falhar ao conectar
        """
        try:
            self.consumer = AIOKafkaConsumer(
                self.tickets_topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=False,  # Commit manual
                max_poll_records=10,  # Processar em batches pequenos
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )

            self.consumer = instrument_kafka_consumer(self.consumer)
            await self.consumer.start()

            logger.info(
                "ticket_consumer.connected",
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id
            )

        except Exception as e:
            logger.error(
                "ticket_consumer.connection_failed",
                error=str(e)
            )
            raise

    async def start_consuming(self) -> None:
        """
        Inicia loop de consumo de mensagens em background.
        """
        if self._consuming:
            logger.warning("ticket_consumer.already_consuming")
            return

        self._consuming = True
        self._consumer_task = asyncio.create_task(self._consume_loop())

        logger.info("ticket_consumer.started")

    async def stop(self) -> None:
        """
        Para consumo e fecha consumer.
        """
        logger.info("ticket_consumer.stopping")

        self._consuming = False

        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        if self.consumer:
            await self.consumer.stop()

        logger.info("ticket_consumer.stopped")

    async def _consume_loop(self) -> None:
        """
        Loop principal de consumo de mensagens.
        """
        try:
            while self._consuming:
                try:
                    # Buscar mensagens (timeout 1s)
                    messages = await asyncio.wait_for(
                        self.consumer.getmany(timeout_ms=1000),
                        timeout=2.0
                    )

                    # Processar mensagens
                    for tp, msgs in messages.items():
                        for message in msgs:
                            try:
                                headers_dict = {k: v for k, v in (message.headers or [])}
                                extract_context_from_headers(headers_dict)
                                await self.handle_ticket(message.value)

                                # Commit offset após processamento bem-sucedido
                                await self.consumer.commit()

                            except Exception as e:
                                logger.error(
                                    "ticket_consumer.message_processing_failed",
                                    error=str(e),
                                    partition=tp.partition,
                                    offset=message.offset
                                )
                                # Não commitar offset em caso de erro
                                # Mensagem será reprocessada

                except asyncio.TimeoutError:
                    # Timeout normal, continuar loop
                    continue

                except KafkaError as e:
                    logger.error(
                        "ticket_consumer.kafka_error",
                        error=str(e)
                    )
                    await asyncio.sleep(5)  # Backoff

        except asyncio.CancelledError:
            logger.info("ticket_consumer.consume_loop_cancelled")
            raise

        except Exception as e:
            logger.error(
                "ticket_consumer.consume_loop_error",
                error=str(e)
            )
            self._consuming = False

    async def handle_ticket(self, ticket: dict) -> None:
        """
        Processa e valida um ExecutionTicket.

        Args:
            ticket: Dicionário com dados do ExecutionTicket
        """
        ticket_id = ticket.get("ticket_id", "unknown")
        plan_id = ticket.get("plan_id")
        if plan_id:
            set_baggage("plan_id", plan_id)
        if ticket_id:
            set_baggage("ticket_id", ticket_id)

        logger.info(
            "ticket_consumer.handling_ticket",
            ticket_id=ticket_id,
            task_type=ticket.get("task_type")
        )

        try:
            # 1. Validar ticket com SecurityValidator
            validation = await self.security_validator.validate_ticket(ticket)

            # 2. Enforçar guardrails adicionais
            guardrail_violations = await self.guardrail_enforcer.enforce_guardrails(ticket)

            # Adicionar violations do guardrail enforcer
            if guardrail_violations:
                validation.violations.extend(guardrail_violations)

                # Recalcular risk assessment com novas violations
                validation.risk_assessment = await self.security_validator._calculate_risk_assessment(
                    validation.violations,
                    ticket
                )

                # Re-determinar status
                validation.validation_status = self.security_validator._determine_validation_status(
                    validation.risk_assessment,
                    validation.violations
                )

                # Recalcular hash após mutações
                validation.refresh_hash()

            # 3. Publicar em tópico apropriado baseado no status
            await self._publish_validation_result(ticket, validation)

            # 4. Atualizar métricas
            await self._update_metrics(validation)

            logger.info(
                "ticket_consumer.ticket_processed",
                ticket_id=ticket_id,
                status=validation.validation_status.value,
                violations_count=len(validation.violations),
                risk_score=validation.risk_assessment.risk_score
            )

        except Exception as e:
            logger.error(
                "ticket_consumer.handle_ticket_failed",
                ticket_id=ticket_id,
                error=str(e)
            )
            raise

    async def _publish_validation_result(
        self,
        ticket: dict,
        validation
    ) -> None:
        """
        Publica resultado da validação no tópico apropriado.

        Args:
            ticket: ExecutionTicket original
            validation: SecurityValidation resultado
        """
        try:
            # Sempre publicar em security.validations
            await self.validation_producer.publish_validation(validation)

            # Publicar em tópico específico baseado no status
            if validation.validation_status == ValidationStatus.APPROVED:
                # Ticket aprovado: publicar em tópico configurado
                await self.validation_producer.publish_to_topic(
                    topic=self.tickets_validated_topic,
                    key=ticket["ticket_id"],
                    value={
                        **ticket,
                        "validation": validation.to_avro_dict()
                    }
                )

                logger.info(
                    "ticket_consumer.ticket_approved",
                    ticket_id=ticket["ticket_id"]
                )

            elif validation.validation_status == ValidationStatus.REJECTED:
                # Ticket rejeitado: publicar em tópico configurado
                await self.validation_producer.publish_to_topic(
                    topic=self.tickets_rejected_topic,
                    key=ticket["ticket_id"],
                    value={
                        "ticket_id": ticket["ticket_id"],
                        "validation": validation.to_avro_dict(),
                        "violations": [v.to_dict() for v in validation.violations]
                    }
                )

                logger.warning(
                    "ticket_consumer.ticket_rejected",
                    ticket_id=ticket["ticket_id"],
                    violations_count=len(validation.violations)
                )

            elif validation.validation_status == ValidationStatus.REQUIRES_APPROVAL:
                # Ticket requer aprovação: publicar em tópico configurado
                await self.validation_producer.publish_to_topic(
                    topic=self.tickets_pending_approval_topic,
                    key=ticket["ticket_id"],
                    value={
                        **ticket,
                        "validation": validation.to_avro_dict(),
                        "approval_reason": validation.approval_reason
                    }
                )

                # TODO: Notificar Queen Agent sobre aprovação pendente

                logger.info(
                    "ticket_consumer.ticket_requires_approval",
                    ticket_id=ticket["ticket_id"],
                    approval_reason=validation.approval_reason
                )

        except Exception as e:
            logger.error(
                "ticket_consumer.publish_result_failed",
                ticket_id=ticket.get("ticket_id"),
                error=str(e)
            )
            raise

    async def _update_metrics(self, validation) -> None:
        """
        Atualiza métricas Prometheus.

        Args:
            validation: SecurityValidation
        """
        try:
            from src.observability.metrics import (
                guard_agent_tickets_validated_total,
                guard_agent_validation_duration_seconds,
                guard_agent_violations_detected_total,
                guard_agent_secrets_detected_total,
                guard_agent_approvals_pending,
                guard_agent_approval_rate,
                guard_agent_risk_score_avg
            )

            # Incrementar tickets validados
            guard_agent_tickets_validated_total.labels(
                status=validation.validation_status.value,
                validator_type=validation.validator_type.value
            ).inc()

            # Contabilizar violations
            for violation in validation.violations:
                guard_agent_violations_detected_total.labels(
                    violation_type=violation.violation_type.value,
                    severity=violation.severity.value
                ).inc()

                # Secrets detectados
                if violation.violation_type.value == "SECRET_EXPOSED":
                    secret_type = violation.evidence.get("secret_type", "unknown")
                    guard_agent_secrets_detected_total.labels(
                        secret_type=secret_type
                    ).inc()

            # Atualizar gauge de aprovações pendentes
            if validation.validation_status == ValidationStatus.REQUIRES_APPROVAL:
                guard_agent_approvals_pending.inc()

            # Atualizar risk score médio (simplificado)
            guard_agent_risk_score_avg.set(validation.risk_assessment.risk_score)

        except Exception as e:
            logger.warning(
                "ticket_consumer.update_metrics_failed",
                error=str(e)
            )
